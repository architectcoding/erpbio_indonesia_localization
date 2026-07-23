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
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, format_datetime, getdate, now_datetime

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


def _digits(value):
	return re.sub(r"\D", "", value or "")


def _strip_html(value):
	return re.sub(r"<[^>]+>", " ", value or "").replace("&amp;", "&").strip()


class CoretaxFakturExport(Document):
	def validate(self):
		if getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("From Date cannot be after To Date."))
		self.npwp_penjual = _digits(frappe.db.get_value("Company", self.company, "tax_id"))

	# ------------------------------------------------------------------ fetch
	@frappe.whitelist()
	def fetch_invoices(self):
		"""Fill the table with the period's exportable Sales Invoices, each
		validated so problems are visible before anything is generated."""
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
		self.status = "Draft"
		self.save()
		valid = sum(1 for r in self.invoices if r.ok)
		return {"total": len(self.invoices), "valid": valid}

	def _validate_invoice(self, si, settings):
		problems = []
		if not self.npwp_penjual:
			problems.append(_("Company Tax ID (NPWP) is empty"))
		if si.currency != "IDR":
			problems.append(_("currency is {0}, only IDR is supported").format(si.currency))
		if si.eil_faktur_status in ("Exported", "Approved"):
			problems.append(_("already {0}").format(si.eil_faktur_status))
		if not (si.eil_kode_transaksi or settings.default_transaction_code):
			problems.append(_("no transaction code"))

		id_type = frappe.db.get_value("Customer", si.customer, "eil_id_type") or "TIN"
		buyer_npwp = _digits(si.tax_id or frappe.db.get_value("Customer", si.customer, "tax_id"))
		if id_type in ("TIN", "NIK") and not buyer_npwp:
			problems.append(_("buyer has no NPWP/NIK (Customer Tax ID)"))

		for item in si.items:
			unit = self._resolve_unit(item)
			if not unit:
				problems.append(_("no Coretax Unit for {0} (uom {1})").format(item.item_code, item.uom))
				break  # one unit message is enough

		return (False, "; ".join(problems)) if problems else (True, _("Ready"))

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
		valid_rows = [r for r in self.invoices if r.ok and r.sales_invoice]
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

		for row in valid_rows:
			frappe.db.set_value(
				"Sales Invoice", row.sales_invoice, "eil_faktur_status", "Exported", update_modified=False
			)

		self.db_set("export_file", file_doc.file_url)
		self.db_set("generated_on", now_datetime())
		self.db_set("status", "Generated")
		return {"file_url": file_doc.file_url, "invoices": len(valid_rows)}

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
		tarif = flt(settings.tarif_ppn) or 12.0
		use_lain = bool(settings.use_dpp_nilai_lain)
		num = settings.dpp_numerator or 11
		den = settings.dpp_denominator or 12

		for baris, row in enumerate(valid_rows, start=1):
			si = frappe.get_doc("Sales Invoice", row.sales_invoice)
			buyer = self._buyer_bits(si)
			ws_faktur.append(
				[
					baris,
					getdate(si.posting_date).strftime("%d/%m/%Y"),
					"Pengganti" if si.eil_pengganti else "Normal",
					si.eil_kode_transaksi or settings.default_transaction_code,
					"",  # Keterangan Tambahan (facility invoices — later phase)
					"",  # Dokumen Pendukung
					si.name,  # Referensi: trace the faktur back to the ERP invoice
					"",  # Cap Fasilitas
					seller_idtku,
					buyer["npwp"],
					buyer["id_type"],
					buyer["country"],
					buyer["document_number"],
					si.customer_name or si.customer,
					_strip_html(si.address_display) or "-",
					buyer["email"],
					buyer["idtku"],
				]
			)
			for item in si.items:
				dpp = flt(item.net_amount, 2)
				dpp_lain = flt(dpp * num / den, 2) if use_lain else dpp
				ppn = flt(dpp_lain * tarif / 100.0, 2)
				ws_detail.append(
					[
						baris,
						self._barang_jasa(item),
						(item.item_code and frappe.db.get_value("Item", item.item_code, "eil_goods_code"))
						or "000000",
						item.item_name or item.item_code,
						self._resolve_unit(item),
						flt(item.net_rate, 2),
						flt(item.qty, 2),
						0,
						dpp,
						dpp_lain,
						tarif,
						ppn,
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

	def _seller_idtku(self):
		nitku = frappe.db.get_value("Company", self.company, "eil_nitku")
		return _digits(nitku) or (self.npwp_penjual + "000000")

	def _buyer_bits(self, si):
		customer = frappe.db.get_value(
			"Customer",
			si.customer,
			["tax_id", "eil_id_type", "eil_document_number", "eil_nitku", "eil_tax_email", "eil_country_code"],
			as_dict=True,
		) or frappe._dict()
		settings_country = frappe.db.get_single_value("Indonesia Tax Settings", "default_buyer_country")
		npwp = _digits(si.tax_id or customer.tax_id)
		return {
			"npwp": npwp,
			"id_type": customer.eil_id_type or "TIN",
			"document_number": customer.eil_document_number or "-",
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
