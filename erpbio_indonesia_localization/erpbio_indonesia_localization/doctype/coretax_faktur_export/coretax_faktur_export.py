# Turns a period's submitted Sales Invoices into the DJP Coretax import
# workbook: a "Faktur" sheet (one row per invoice) and a "DetailFaktur" sheet
# (one row per invoice line, keyed back by the Baris number), which DJP's own
# Excel-to-XML converter then turns into upload-ready XML. Letting DJP's
# converter produce the XML means the XML schema can never drift out from
# under us — this app only has to fill their template correctly.
#
# Layout follows the published template: the Faktur sheet carries the seller
# NPWP in its head rows, headers, data, and an END marker row that tells the
# converter where the data stops. Validate the generated file against the
# current official template before the first real upload — DJP revises it.

import io
import math
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, format_datetime, getdate, now_datetime

FAKTUR_HEADERS = [
	"Baris",
	"Tanggal Faktur",
	"Jenis Faktur",
	"Kode Transaksi",
	"Keterangan Tambahan",
	"Dokumen Pendukung",
	"Referensi",
	"Cap Fasilitas",
	"ID TKU Penjual",
	"NPWP/NIK Pembeli",
	"Jenis ID Pembeli",
	"Negara Pembeli",
	"Nomor Dokumen Pembeli",
	"Nama Pembeli",
	"Alamat Pembeli",
	"Email Pembeli",
	"ID TKU Pembeli",
]

DETAIL_HEADERS = [
	"Baris",
	"Barang/Jasa",
	"Kode Barang Jasa",
	"Nama Barang/Jasa",
	"Nama Satuan Ukur",
	"Harga Satuan",
	"Jumlah Barang Jasa",
	"Total Diskon",
	"DPP",
	"DPP Nilai Lain",
	"Tarif PPN",
	"PPN",
	"Tarif PPnBM",
	"PPnBM",
]


def _invoice_ppn(si):
	"""The PPN the invoice itself charges, whichever way it carries it.

	An ordinary invoice has output-VAT rows; a government one had them stripped
	and carries the figure in eil_govt_charges instead."""
	from erpbio_indonesia_localization.doc_events.sales_invoice import (
		PPN_TREATMENT,
		_output_vat_accounts,
	)

	if cint(si.get("eil_is_pemungut")):
		return flt(
			sum(
				flt(r.amount)
				for r in (si.get("eil_govt_charges") or [])
				if r.treatment == PPN_TREATMENT
			),
			2,
		)
	accounts = _output_vat_accounts(si.company)
	return flt(sum(_posted_tax(r) for r in (si.get("taxes") or []) if r.account_head in accounts), 2)


def _posted_tax(row):
	"""What a tax row posted: after a Grand-Total discount, which the ledger
	credits and the faktur lines (discounted net) state -- not the pre-discount
	figure, which refused every such invoice (T-010)."""
	after = row.get("base_tax_amount_after_discount_amount")
	if after is None:
		after = row.get("tax_amount_after_discount_amount")
	if after is not None:
		return flt(after)
	return flt(row.get("base_tax_amount") or row.get("tax_amount"))


# A facility faktur: kode 07 (PPN tidak dipungut) and 08 (dibebaskan). The
# invoice charges no PPN; the faktur still states the DPP and the PPN the
# facility covers, with the facility named (T-003).
FACILITY_CODES = ("07", "08")


def _faktur_code(si, settings):
	return str(si.get("eil_kode_transaksi") or settings.default_transaction_code or "").strip()


def _invoice_vat_rate(si):
	"""The rate the invoice's own PPN is charged at -- 11 on the full price
	(the flat template, filed as 12% on a DPP Nilai Lain of 11/12) or 12 (the
	full-DPP template, filed as 12% on the full price). None when it charges
	none, or cannot say."""
	from erpbio_indonesia_localization.doc_events.sales_invoice import (
		PPN_TREATMENT,
		_output_vat_accounts,
	)

	if cint(si.get("eil_is_pemungut")):
		rates = [flt(r.rate) for r in (si.get("eil_govt_charges") or []) if r.treatment == PPN_TREATMENT and flt(r.rate)]
	else:
		accounts = _output_vat_accounts(si.company) if si.get("company") else set()
		rates = [
			flt(r.rate)
			for r in (si.get("taxes") or [])
			if r.account_head in accounts and r.charge_type != "Actual" and flt(r.rate) > 0
		]
	return max(rates) if rates else None


def _charge_mappings():
	"""Charge account -> how it should appear as a faktur line."""
	return {
		r.account: r
		for r in frappe.get_all(
			"EIL Taxable Charge Mapping",
			filters={"parenttype": "Indonesia Tax Settings"},
			fields=["account", "barang_jasa", "goods_code", "coretax_unit", "description"],
		)
		if r.account
	}


def _digits(value):
	return re.sub(r"\D", "", value or "")


def _strip_html(value):
	return re.sub(r"<[^>]+>", " ", value or "").replace("&amp;", "&").strip()


def _one_line(value):
	"""A Small Text address as Coretax wants it: one line, single spaces."""
	return re.sub(r"\s+", " ", (value or "").replace("<br>", " ")).strip()


def _num(value):
	"""12 -> '12', 1833333.33 -> '1833333.33' — plain decimals, no trailing zeros."""
	text = f"{flt(value):.2f}".rstrip("0").rstrip(".")
	return text or "0"


def _price_and_discount(dpp, qty, net_rate):
	"""A Harga Satuan and Total Diskon that satisfy Coretax's per-line identity.

	Coretax recomputes DPP = Harga Satuan x Jumlah - Total Diskon on every line
	and rejects the upload when the three disagree. A unit price only fits in two
	decimals when the quantity divides the discounted amount, and an
	invoice-level discount routinely stops it doing so: three units of a
	29,990,990.99 line price at 9,996,997.00 each, which is a rupiah more than
	was invoiced.

	Reporting the price rounded AWAY from zero and carrying the remainder as the
	discount is how the official template is filled in by hand. Rounding that way
	round is what keeps the remainder non-negative — DJP has no meaning for a
	negative Total Diskon. Where the division is already exact the discount comes
	out at zero, so an ordinary line is untouched.
	"""
	if not qty:
		return net_rate, 0
	# In hundredths, so the rounding is a plain integer step. Damping to six
	# decimals first stops a value that is exactly representable in rupiah from
	# being pushed up a hundredth by float noise.
	units = flt(dpp / qty / 0.01, 6)
	price = flt((math.ceil(units) if qty > 0 else math.floor(units)) * 0.01, 2)
	return price, flt(price * qty - dpp, 2)


def _spread(total, weights):
	"""`total` split over `weights` pro rata, in whole hundredths that add up
	exactly (largest remainder), each share capped at its own weight."""
	if not total or not weights or sum(w for w in weights if w > 0) <= 0:
		return [0.0] * len(weights)
	base = sum(w for w in weights if w > 0)
	cents = round(min(total, base) * 100)
	raw = [(max(w, 0) / base) * cents for w in weights]
	shares = [math.floor(r) for r in raw]
	for i in sorted(range(len(raw)), key=lambda i: raw[i] - shares[i], reverse=True)[: cents - sum(shares)]:
		shares[i] += 1
	return [s / 100 for s in shares]


def faktur_sources():
	"""{doctype: module} — apps that issue a faktur from a document other than a
	Sales Invoice, by the `eil_faktur_sources` hook (erpbio_general: a DP
	invoice's faktur uang muka). Each module has DOCTYPE, NUMBER_FIELD,
	documents(company, from_date, to_date) -> [names], faktur_document(name) ->
	a dict shaped like the Sales Invoice this export reads (with `_problems`, and
	a line's `_less` for DPP not billed on it), and mark(name, status, number,
	date)."""
	out = {}
	for path in frappe.get_hooks("eil_faktur_sources") or []:
		module = frappe.get_module(path)
		out[module.DOCTYPE] = module
	return out


class CoretaxFakturExport(Document):
	def validate(self):
		if getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("From Date cannot be after To Date."))
		self.refresh_seller_npwp()

	def refresh_seller_npwp(self):
		"""Re-read the company's NPWP onto the export.

		Called from validate AND from the top of fetch_invoices. Only validate
		would be too late: fetch judges every invoice and then saves, so the
		checks ran against whatever NPWP the export was created with. On a
		company with none — which is the state this site is in — the accountant
		is told "Company Tax ID (NPWP) is empty" against every invoice, fills it
		in, fetches again, and is told exactly the same thing."""
		self.npwp_penjual = _digits(frappe.db.get_value("Company", self.company, "tax_id"))

	# ------------------------------------------------------------------ fetch
	@frappe.whitelist()
	def fetch_invoices(self):
		"""Fill the table with the period's exportable Sales Invoices, each
		validated so problems are visible before anything is generated."""
		self.refresh_seller_npwp()
		self.set("invoices", [])
		invoices = frappe.get_all(
			"Sales Invoice",
			filters={
				"company": self.company,
				"docstatus": 1,
				"posting_date": ["between", [self.from_date, self.to_date]],
				"is_return": 0,
				"eil_exclude": 0,
			},
			fields=["name"],
			order_by="posting_date asc, name asc",
		)
		settings = frappe.get_single("Indonesia Tax Settings")
		for row in invoices:
			si = frappe.get_doc("Sales Invoice", row.name)
			ok, message = self._validate_invoice(si, settings)
			self.append(
				"invoices",
				{
					"sales_invoice": si.name,
					"customer": si.customer_name or si.customer,
					"posting_date": si.posting_date,
					"grand_total": si.grand_total,
					"kode_transaksi": si.eil_kode_transaksi or settings.default_transaction_code,
					"ok": 1 if ok else 0,
					"message": message,
				},
			)
		for doctype, source in faktur_sources().items():
			for name in source.documents(self.company, self.from_date, self.to_date):
				doc = source.faktur_document(name)
				ok, message = self._validate_invoice(doc, settings)
				self.append(
					"invoices",
					{
						"reference_doctype": doctype,
						"reference_name": name,
						"customer": doc.customer_name or doc.customer,
						"posting_date": doc.posting_date,
						"grand_total": doc.grand_total,
						"kode_transaksi": doc.eil_kode_transaksi or settings.default_transaction_code,
						"ok": 1 if ok else 0,
						"message": message,
					},
				)
		self.status = "Draft"
		self.save()
		valid = sum(1 for r in self.invoices if r.ok)
		return {"total": len(self.invoices), "valid": valid}

	def _validate_invoice(self, si, settings):
		problems = list(si.get("_problems") or [])
		if not self.npwp_penjual:
			problems.append(_("Company Tax ID (NPWP) is empty"))
		if si.currency != "IDR":
			problems.append(_("currency is {0}, only IDR is supported").format(si.currency))
		if si.eil_faktur_status in ("Exported", "Approved"):
			problems.append(_("already {0}").format(si.eil_faktur_status))
		if not (si.eil_kode_transaksi or settings.default_transaction_code):
			problems.append(_("no transaction code"))
		if _faktur_code(si, settings) in FACILITY_CODES and not (
			(si.get("eil_add_info") or "").strip() and (si.get("eil_facility_stamp") or "").strip()
		):
			problems.append(_("kode {0} needs its Keterangan Tambahan and Cap Fasilitas (from Coretax's list)").format(
				_faktur_code(si, settings)
			))

		buyer = self._buyer_bits(si)
		id_type, buyer_npwp = buyer["id_type"], buyer["npwp"]
		if id_type in ("TIN", "NIK") and not buyer_npwp:
			problems.append(_("buyer has no NPWP/NIK (Customer Tax ID)"))

		for item in si.items:
			unit = self._resolve_unit(item)
			if not unit:
				problems.append(_("no Coretax Unit for {0} (uom {1})").format(item.item_code, item.uom))
				break  # one unit message is enough

		# a Faktur Pengganti names the approved faktur it replaces (T-004)
		replaces = (si.get("eil_replaces_faktur_number") or "").strip()
		if si.get("eil_pengganti") and not replaces:
			problems.append(_("a Faktur Pengganti needs the number of the faktur it replaces"))

		problems.extend(self._charge_problems(si, settings))
		if problems:
			return False, "; ".join(problems)
		return True, _("Ready — Pengganti for {0}").format(replaces) if si.get("eil_pengganti") else _("Ready")

	def _charge_problems(self, si, settings):
		"""A charge inside the DPP that the faktur cannot state, and any residual
		gap between the faktur's PPN and the invoice's own.

		The reconciliation is the real guard: a faktur that reports less PPN than
		the invoice charged is under-declared output tax, and no amount of
		per-case reasoning about tax templates is worth trusting on its own."""
		from erpbio_indonesia_localization.doc_events.sales_invoice import taxable_charge_rows

		problems = []
		mappings = _charge_mappings()
		for row in taxable_charge_rows(si):
			if not flt(row.base_tax_amount or row.tax_amount):
				continue
			m = mappings.get(row.account_head)
			if not m or not m.coretax_unit:
				problems.append(
					_("{0} is charged PPN but has no Taxable Charge Mapping in Indonesia Tax Settings").format(
						row.description or row.account_head
					)
				)
		if problems:
			return problems  # the totals cannot balance while a line is missing
		if _faktur_code(si, settings) in FACILITY_CODES:
			return problems  # the faktur states the PPN the facility covers; the invoice charges none

		invoice_ppn = _invoice_ppn(si)
		faktur_ppn = flt(sum(line["ppn"] for line in self._faktur_lines(si, settings)), 2)
		if abs(faktur_ppn - invoice_ppn) > 1:
			problems.append(
				_("faktur PPN {0} does not match the invoice's {1} — check the tax template").format(
					frappe.format_value(faktur_ppn, {"fieldtype": "Currency"}),
					frappe.format_value(invoice_ppn, {"fieldtype": "Currency"}),
				)
			)
		return problems

	def _resolve_unit(self, item_row):
		"""Item's explicit Coretax Unit, else the Coretax Unit mapped to the
		row's UOM, else the one mapped to the item's stock UOM."""
		if item_row.item_code:
			explicit = frappe.db.get_value("Item", item_row.item_code, "eil_coretax_unit")
			if explicit:
				return explicit
		by_uom = frappe.db.get_value("Coretax Unit", {"uom": item_row.uom})
		if by_uom:
			return by_uom
		if item_row.item_code:
			stock_uom = frappe.db.get_value("Item", item_row.item_code, "stock_uom")
			if stock_uom and stock_uom != item_row.uom:
				return frappe.db.get_value("Coretax Unit", {"uom": stock_uom})
		return None

	# --------------------------------------------------------------- generate
	@frappe.whitelist()
	def generate(self):
		"""Build the Faktur/DetailFaktur workbook from the valid rows, attach
		it, and stamp those invoices Exported."""
		valid_rows = [r for r in self.invoices if r.ok and (r.sales_invoice or r.reference_name)]
		if not valid_rows:
			frappe.throw(_("No valid invoices — run Fetch Invoices and resolve the validation messages."))

		settings = frappe.get_single("Indonesia Tax Settings")
		content = self._build_workbook(valid_rows, settings)

		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{self.name}-coretax.xlsx",
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"is_private": 1,
				"content": content,
			}
		).insert(ignore_permissions=True)

		self._mark_exported(valid_rows)

		self.db_set("export_file", file_doc.file_url)
		self.db_set("generated_on", now_datetime())
		self.db_set("status", "Generated")
		return {"file_url": file_doc.file_url, "invoices": len(valid_rows)}

	def release(self):
		"""Put this export's documents that are still "Exported" back to "Not
		Exported", so a file Coretax rejected -- a wrong unit code, a bad NPWP --
		can be fixed and exported again. A faktur Coretax already approved is
		never touched; only the import moves that (T-005). Returns what moved."""
		sources = faktur_sources()
		released = []
		for row in self.invoices:
			if row.sales_invoice:
				if frappe.db.get_value("Sales Invoice", row.sales_invoice, "eil_faktur_status") == "Exported":
					frappe.db.set_value(
						"Sales Invoice", row.sales_invoice, "eil_faktur_status", "Not Exported", update_modified=False
					)
					released.append(row.sales_invoice)
			elif row.reference_name and row.reference_doctype in sources:
				source = sources[row.reference_doctype]
				if (source.faktur_document(row.reference_name) or {}).get("eil_faktur_status") == "Exported":
					source.mark(row.reference_name, "Not Exported")
					released.append(row.reference_name)
		if self.status == "Generated":
			self.db_set("status", "Draft")
		return released

	def on_trash(self):
		# a deleted export leaves no file behind to have filed its documents
		self.release()

	def _faktur_doc(self, row):
		if row.sales_invoice:
			return frappe.get_doc("Sales Invoice", row.sales_invoice)
		return faktur_sources()[row.reference_doctype].faktur_document(row.reference_name)

	def _mark_exported(self, rows):
		sources = faktur_sources()
		for row in rows:
			if row.sales_invoice:
				frappe.db.set_value(
					"Sales Invoice", row.sales_invoice, "eil_faktur_status", "Exported", update_modified=False
				)
			else:
				sources[row.reference_doctype].mark(row.reference_name, "Exported")

	def _faktur_lines(self, si, settings):
		"""Every line the faktur carries: the items, then one line per charge that
		sits inside the DPP.

		A taxed charge is part of the base but is not an item, and Coretax checks
		DPP = Harga Satuan x Jumlah - Diskon on each line, so it cannot be folded
		into an item's DPP without inventing that item's unit price. It gets its
		own line instead, priced at the charge itself.

		A faktur pelunasan: when the invoice takes PPN already booked on an
		advance off its own (the termin's faktur uang muka), that advance's DPP
		is not billed again. It comes off the item lines as Total Diskon, pro
		rata, so every line keeps Price x Qty - Diskon = DPP and the faktur's PPN
		is the invoice's.

		A faktur uang muka (a source document) states each line's `_less` — the
		part of the line not billed on this termin — the same way."""
		from erpbio_indonesia_localization.doc_events.sales_invoice import taxable_charge_rows

		settings = self._line_settings(si, settings)
		less = _spread(self._advance_dpp(si, settings), [flt(item.net_amount, 2) for item in si.items])
		lines = [
			self._line_values(item, settings, less=flt(share + flt(item.get("_less")), 2))
			for item, share in zip(si.items, less)
		]
		mappings = _charge_mappings()
		for row in taxable_charge_rows(si):
			amount = flt(row.base_tax_amount or row.tax_amount, 2)
			if not amount:
				continue
			m = mappings.get(row.account_head) or frappe._dict()
			lines.append(
				self._line_values(
					frappe._dict(
						{
							"item_code": None,
							"item_name": m.description or row.description or row.account_head,
							"uom": None,
							"qty": 1,
							"net_rate": amount,
							"net_amount": amount,
							"_charge_account": row.account_head,
							"_barang_jasa": m.barang_jasa,
							"_goods_code": m.goods_code,
							"_unit": m.coretax_unit,
						}
					),
					settings,
				)
			)
		return lines

	def _line_settings(self, si, settings):
		"""The settings this invoice's lines are computed with. DPP Nilai Lain
		(12% on 11/12) is how an 11% flat template reaches the right rupiah; an
		invoice already charging the full 12% files the full price, or its faktur
		would state 110 of PPN against the 120 it charged (T-003)."""
		rate = _invoice_vat_rate(si)
		tarif = flt(settings.tarif_ppn) or 12.0
		if not settings.use_dpp_nilai_lain or not rate or rate < tarif - 0.001:
			return settings
		plain = frappe._dict(settings.as_dict() if hasattr(settings, "as_dict") else settings)
		plain.use_dpp_nilai_lain = 0
		return plain

	def _advance_dpp(self, si, settings):
		"""The DPP of advances whose PPN this invoice takes off its own, read back
		from those rows at the faktur's effective rate (11% as 12% on 11/12)."""
		from erpbio_indonesia_localization.doc_events.sales_invoice import (
			_output_vat_accounts,
			is_advance_vat_row,
		)

		accounts = _output_vat_accounts(si.company)
		ppn = -sum(flt(r.base_tax_amount or r.tax_amount) for r in (si.get("taxes") or []) if is_advance_vat_row(r, accounts))
		if ppn <= 0:
			return 0.0
		effective = (flt(settings.tarif_ppn) or 12.0) / 100.0
		if settings.use_dpp_nilai_lain:
			effective *= (settings.dpp_numerator or 11) / (settings.dpp_denominator or 12)
		return flt(ppn / effective, 2)

	def _line_values(self, item, settings, less=0.0):
		"""One invoice line's tax figures, shared by the workbook and the XML.
		`less` is this line's share of an advance's DPP already invoiced (a
		faktur pelunasan): it adds to the discount and comes off the DPP."""
		tarif = flt(settings.tarif_ppn) or 12.0
		num = settings.dpp_numerator or 11
		den = settings.dpp_denominator or 12
		dpp = flt(item.net_amount, 2)
		charge = item.get("_charge_account")
		qty = flt(item.qty, 2)
		price, discount = _price_and_discount(dpp, qty, flt(item.net_rate, 2))
		if less:
			dpp = flt(dpp - less, 2)
			discount = flt(discount + less, 2)
		dpp_lain = flt(dpp * num / den, 2) if settings.use_dpp_nilai_lain else dpp
		return {
			"opt": (item.get("_barang_jasa") or "B - Jasa")[0] if charge else self._barang_jasa(item),
			"code": (item.get("_goods_code") or "000000")
			if charge
			else (
				(item.item_code and frappe.db.get_value("Item", item.item_code, "eil_goods_code"))
				or "000000"
			),
			"name": item.item_name or item.item_code,
			"unit": item.get("_unit") if charge else self._resolve_unit(item),
			"price": price,
			"qty": qty,
			"discount": discount,
			"dpp": dpp,
			"dpp_lain": dpp_lain,
			"tarif": tarif,
			"ppn": flt(dpp_lain * tarif / 100.0, 2),
		}

	def _build_workbook(self, valid_rows, settings):
		import openpyxl

		wb = openpyxl.Workbook()
		ws_faktur = wb.active
		ws_faktur.title = "Faktur"
		ws_detail = wb.create_sheet("DetailFaktur")

		ws_faktur.append(["NPWP Penjual", self.npwp_penjual])
		ws_faktur.append([])
		ws_faktur.append(FAKTUR_HEADERS)
		ws_detail.append(DETAIL_HEADERS)

		seller_idtku = self._seller_idtku()
		for baris, row in enumerate(valid_rows, start=1):
			si = self._faktur_doc(row)
			buyer = self._buyer_bits(si)
			ws_faktur.append(
				[
					baris,
					getdate(si.posting_date).strftime("%d/%m/%Y"),
					"Pengganti" if si.eil_pengganti else "Normal",
					si.eil_kode_transaksi or settings.default_transaction_code,
					(si.get("eil_add_info") or "").strip(),  # Keterangan Tambahan (kode 07/08)
					"",  # Dokumen Pendukung
					si.name,  # Referensi: trace the faktur back to the ERP invoice
					(si.get("eil_facility_stamp") or "").strip(),  # Cap Fasilitas (kode 07/08)
					seller_idtku,
					buyer["npwp"],
					buyer["id_type"],
					buyer["country"],
					buyer["document_number"],
					buyer["name"],
					buyer["address"],
					buyer["email"],
					buyer["idtku"],
				]
			)
			for line in self._faktur_lines(si, settings):
				ws_detail.append(
					[
						baris,
						line["opt"],
						line["code"],
						line["name"],
						line["unit"],
						line["price"],
						line["qty"],
						line["discount"],
						line["dpp"],
						line["dpp_lain"],
						line["tarif"],
						line["ppn"],
						0,
						0,
					]
				)

		# the converter reads rows until it hits END
		ws_faktur.append(["END"])
		ws_detail.append(["END"])

		buf = io.BytesIO()
		wb.save(buf)
		return buf.getvalue()

	# ------------------------------------------------------------- direct XML
	@frappe.whitelist()
	def generate_xml(self):
		"""Build the Coretax TaxInvoiceBulk XML directly — the same document
		DJP's converter produces from the workbook. Element names and order
		follow the published DJP schema (including its literal 'BuyerAdress'
		spelling). Validate the first real file against Coretax before relying
		on this path; the workbook + official converter stays the safe route."""
		valid_rows = [r for r in self.invoices if r.ok and (r.sales_invoice or r.reference_name)]
		if not valid_rows:
			frappe.throw(_("No valid invoices — run Fetch Invoices and resolve the validation messages."))

		settings = frappe.get_single("Indonesia Tax Settings")
		content = self._build_xml(valid_rows, settings)

		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{self.name}-coretax.xml",
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"is_private": 1,
				"content": content,
			}
		).insert(ignore_permissions=True)

		self._mark_exported(valid_rows)
		self.db_set("generated_on", now_datetime())
		self.db_set("status", "Generated")
		return {"file_url": file_doc.file_url, "invoices": len(valid_rows)}

	def _build_xml(self, valid_rows, settings):
		from xml.etree import ElementTree as ET

		root = ET.Element("TaxInvoiceBulk")
		root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")
		root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
		ET.SubElement(root, "TIN").text = self.npwp_penjual
		invoices_el = ET.SubElement(root, "ListOfTaxInvoice")

		seller_idtku = self._seller_idtku()
		for row in valid_rows:
			si = self._faktur_doc(row)
			buyer = self._buyer_bits(si)
			inv = ET.SubElement(invoices_el, "TaxInvoice")
			ET.SubElement(inv, "TaxInvoiceDate").text = str(getdate(si.posting_date))
			ET.SubElement(inv, "TaxInvoiceOpt").text = "Pengganti" if si.eil_pengganti else "Normal"
			ET.SubElement(inv, "TrxCode").text = si.eil_kode_transaksi or settings.default_transaction_code
			ET.SubElement(inv, "AddInfo").text = (si.get("eil_add_info") or "").strip() or None
			ET.SubElement(inv, "CustomDoc")
			ET.SubElement(inv, "RefDesc").text = si.name
			ET.SubElement(inv, "FacilityStamp").text = (si.get("eil_facility_stamp") or "").strip() or None
			ET.SubElement(inv, "SellerIDTKU").text = seller_idtku
			ET.SubElement(inv, "BuyerTin").text = buyer["npwp"]
			ET.SubElement(inv, "BuyerDocument").text = buyer["id_type"]
			ET.SubElement(inv, "BuyerCountry").text = buyer["country"]
			ET.SubElement(inv, "BuyerDocumentNumber").text = buyer["document_number"]
			ET.SubElement(inv, "BuyerName").text = buyer["name"]
			# sic: the DJP schema spells it "BuyerAdress"
			ET.SubElement(inv, "BuyerAdress").text = buyer["address"]
			ET.SubElement(inv, "BuyerEmail").text = buyer["email"]
			ET.SubElement(inv, "BuyerIDTKU").text = buyer["idtku"]
			goods_el = ET.SubElement(inv, "ListOfGoodService")
			for line in self._faktur_lines(si, settings):
				g = ET.SubElement(goods_el, "GoodService")
				ET.SubElement(g, "Opt").text = line["opt"]
				ET.SubElement(g, "Code").text = line["code"]
				ET.SubElement(g, "Name").text = line["name"]
				ET.SubElement(g, "Unit").text = line["unit"]
				ET.SubElement(g, "Price").text = _num(line["price"])
				ET.SubElement(g, "Qty").text = _num(line["qty"])
				ET.SubElement(g, "TotalDiscount").text = _num(line["discount"])
				ET.SubElement(g, "TaxBase").text = _num(line["dpp"])
				ET.SubElement(g, "OtherTaxBase").text = _num(line["dpp_lain"])
				ET.SubElement(g, "VATRate").text = _num(line["tarif"])
				ET.SubElement(g, "VAT").text = _num(line["ppn"])
				ET.SubElement(g, "STLGRate").text = "0"
				ET.SubElement(g, "STLG").text = "0"

		ET.indent(root)
		return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="utf-8")

	def _seller_idtku(self):
		"""The company's NITKU, else its NPWP with the head-office branch suffix.

		The suffix is only a sane default when there is an NPWP to append it to.
		Concatenated onto an empty one it produces the literal string 000000 — a
		plausible-looking tax identity belonging to nobody. The company on this
		site has no NPWP today, so that is the value the first export would have
		carried."""
		nitku = _digits(frappe.db.get_value("Company", self.company, "eil_nitku"))
		if nitku:
			return nitku
		return self.npwp_penjual + "000000" if self.npwp_penjual else ""

	def _buyer_bits(self, si):
		customer = frappe.db.get_value(
			"Customer",
			si.customer,
			["tax_id", "eil_id_type", "eil_document_number", "eil_nitku", "eil_tax_email", "eil_country_code", "eil_tax_name", "eil_tax_address"],
			as_dict=True,
		) or frappe._dict()
		settings_country = frappe.db.get_single_value("Indonesia Tax Settings", "default_buyer_country")
		# The document wins over the master for all three parts of the identity,
		# because they have to agree: an invoice carrying a NIK while the customer
		# is still marked TIN would export a NIK labelled as an NPWP. Blank on the
		# document means "whatever the Customer says", which is the usual case.
		npwp = _digits(si.get("tax_id") or customer.tax_id)
		return {
			"npwp": npwp,
			# The registered name, not the trading name the reps use: "RS Columbia Asia
			# Semarang" is BELEFINA SARANA MEDIKA to the tax office. The document may
			# override the customer (a faktur issued to the payer's institution).
			"name": si.get("eil_tax_name") or customer.eil_tax_name or si.customer_name or si.customer,
			# The address as registered with the tax office, not the billing block
			# the invoice prints: a hospital under a foundation, a branch buying on
			# the head office's NPWP, a PT at a virtual office -- the faktur's trio
			# is name, address and NPWP as registered. Blank falls back to the
			# invoice's address, which is what went out before this field existed.
			"address": _one_line(si.get("eil_tax_address")) or _one_line(customer.eil_tax_address) or _strip_html(si.address_display) or "-",
			"id_type": si.get("eil_id_type") or customer.eil_id_type or "TIN",
			"document_number": si.get("eil_document_number") or customer.eil_document_number or "-",
			"country": customer.eil_country_code or settings_country or "IDN",
			"email": customer.eil_tax_email or "",
			"idtku": _digits(customer.eil_nitku) or (npwp + "000000" if npwp else ""),
		}

	def _barang_jasa(self, item_row):
		if item_row.item_code:
			explicit = frappe.db.get_value("Item", item_row.item_code, "eil_barang_jasa")
			if explicit:
				return explicit[0]  # "A - Barang" -> "A"
			if frappe.db.get_value("Item", item_row.item_code, "is_stock_item"):
				return "A"
		return "B"
