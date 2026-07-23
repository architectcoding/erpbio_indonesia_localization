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


def _num(value):
	"""12 -> '12', 1833333.33 -> '1833333.33' — plain decimals, no trailing zeros."""
	text = f"{flt(value):.2f}".rstrip("0").rstrip(".")
	return text or "0"


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

	def _line_values(self, item, settings):
		"""One invoice line's tax figures, shared by the workbook and the XML."""
		tarif = flt(settings.tarif_ppn) or 12.0
		num = settings.dpp_numerator or 11
		den = settings.dpp_denominator or 12
		dpp = flt(item.net_amount, 2)
		dpp_lain = flt(dpp * num / den, 2) if settings.use_dpp_nilai_lain else dpp
		return {
			"opt": self._barang_jasa(item),
			"code": (item.item_code and frappe.db.get_value("Item", item.item_code, "eil_goods_code"))
			or "000000",
			"name": item.item_name or item.item_code,
			"unit": self._resolve_unit(item),
			"price": flt(item.net_rate, 2),
			"qty": flt(item.qty, 2),
			"discount": 0,
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
				line = self._line_values(item, settings)
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
		valid_rows = [r for r in self.invoices if r.ok and r.sales_invoice]
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

		for row in valid_rows:
			frappe.db.set_value(
				"Sales Invoice", row.sales_invoice, "eil_faktur_status", "Exported", update_modified=False
			)
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
			si = frappe.get_doc("Sales Invoice", row.sales_invoice)
			buyer = self._buyer_bits(si)
			inv = ET.SubElement(invoices_el, "TaxInvoice")
			ET.SubElement(inv, "TaxInvoiceDate").text = str(getdate(si.posting_date))
			ET.SubElement(inv, "TaxInvoiceOpt").text = "Pengganti" if si.eil_pengganti else "Normal"
			ET.SubElement(inv, "TrxCode").text = si.eil_kode_transaksi or settings.default_transaction_code
			ET.SubElement(inv, "AddInfo")
			ET.SubElement(inv, "CustomDoc")
			ET.SubElement(inv, "RefDesc").text = si.name
			ET.SubElement(inv, "FacilityStamp")
			ET.SubElement(inv, "SellerIDTKU").text = seller_idtku
			ET.SubElement(inv, "BuyerTin").text = buyer["npwp"]
			ET.SubElement(inv, "BuyerDocument").text = buyer["id_type"]
			ET.SubElement(inv, "BuyerCountry").text = buyer["country"]
			ET.SubElement(inv, "BuyerDocumentNumber").text = buyer["document_number"]
			ET.SubElement(inv, "BuyerName").text = si.customer_name or si.customer
			# sic: the DJP schema spells it "BuyerAdress"
			ET.SubElement(inv, "BuyerAdress").text = _strip_html(si.address_display) or "-"
			ET.SubElement(inv, "BuyerEmail").text = buyer["email"]
			ET.SubElement(inv, "BuyerIDTKU").text = buyer["idtku"]
			goods_el = ET.SubElement(inv, "ListOfGoodService")
			for item in si.items:
				line = self._line_values(item, settings)
				g = ET.SubElement(goods_el, "GoodService")
				ET.SubElement(g, "Opt").text = line["opt"]
				ET.SubElement(g, "Code").text = line["code"]
				ET.SubElement(g, "Name").text = line["name"]
				ET.SubElement(g, "Unit").text = line["unit"]
				ET.SubElement(g, "Price").text = _num(line["price"])
				ET.SubElement(g, "Qty").text = _num(line["qty"])
				ET.SubElement(g, "TotalDiscount").text = "0"
				ET.SubElement(g, "TaxBase").text = _num(line["dpp"])
				ET.SubElement(g, "OtherTaxBase").text = _num(line["dpp_lain"])
				ET.SubElement(g, "VATRate").text = _num(line["tarif"])
				ET.SubElement(g, "VAT").text = _num(line["ppn"])
				ET.SubElement(g, "STLGRate").text = "0"
				ET.SubElement(g, "STLG").text = "0"

		ET.indent(root)
		return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="utf-8")

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
