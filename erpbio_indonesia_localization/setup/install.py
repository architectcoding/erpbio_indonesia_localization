# Everything here is additive and idempotent: create_custom_fields upserts by
# (dt, fieldname), and the seeds insert only what's missing. Runs after install
# and after every migrate, so field updates ship with the app. No core doctype
# behavior is overridden anywhere in this app — installing it changes nothing
# about how ERPNext posts documents.

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# All fieldnames carry the eil_ prefix so they can never collide with ERPNext
# core fields or another app's custom fields (erpbio_general also customizes
# Sales Invoice on some sites).
CUSTOM_FIELDS = {
	"Company": [
		{
			"fieldname": "eil_nitku",
			"label": "NITKU",
			"fieldtype": "Data",
			"insert_after": "tax_id",
			"description": "Nomor Identitas Tempat Kegiatan Usaha (22 digit). Blank = NPWP + 000000 (pusat).",
		},
	],
	"Customer": [
		{
			"fieldname": "eil_tax_section",
			"label": "Indonesia Tax (Coretax)",
			"fieldtype": "Section Break",
			"insert_after": "tax_id",
			"collapsible": 1,
		},
		{
			"fieldname": "eil_id_type",
			"label": "Buyer ID Type",
			"fieldtype": "Select",
			"options": "TIN\nNIK\nPassport\nOther",
			"default": "TIN",
			"insert_after": "eil_tax_section",
			"description": "TIN = NPWP. The NPWP/NIK itself goes in Tax ID above.",
		},
		{
			"fieldname": "eil_document_number",
			"label": "Buyer Document Number",
			"fieldtype": "Data",
			"insert_after": "eil_id_type",
			"depends_on": "eval:['Passport','Other'].includes(doc.eil_id_type)",
		},
		{
			"fieldname": "eil_tax_col",
			"fieldtype": "Column Break",
			"insert_after": "eil_document_number",
		},
		{
			"fieldname": "eil_nitku",
			"label": "Buyer NITKU / ID TKU",
			"fieldtype": "Data",
			"insert_after": "eil_tax_col",
			"description": "Blank = buyer NPWP + 000000.",
		},
		{
			"fieldname": "eil_tax_email",
			"label": "Tax Email",
			"fieldtype": "Data",
			"options": "Email",
			"insert_after": "eil_nitku",
		},
		{
			"fieldname": "eil_country_code",
			"label": "Buyer Country Code",
			"fieldtype": "Data",
			"default": "IDN",
			"insert_after": "eil_tax_email",
		},
	],
	"Item": [
		{
			"fieldname": "eil_tax_section",
			"label": "Indonesia Tax (Coretax)",
			"fieldtype": "Section Break",
			"insert_after": "is_stock_item",
			"collapsible": 1,
		},
		{
			"fieldname": "eil_barang_jasa",
			"label": "Coretax Classification",
			"fieldtype": "Select",
			"options": "\nA - Barang\nB - Jasa",
			"insert_after": "eil_tax_section",
			"description": "Blank = derived from Maintain Stock (stock item → Barang).",
		},
		{
			"fieldname": "eil_goods_code",
			"label": "Kode Barang/Jasa",
			"fieldtype": "Data",
			"default": "000000",
			"insert_after": "eil_barang_jasa",
			"description": "6-digit DJP goods/services code. 000000 is accepted for general items.",
		},
		{
			"fieldname": "eil_coretax_unit",
			"label": "Coretax Unit",
			"fieldtype": "Link",
			"options": "Coretax Unit",
			"insert_after": "eil_goods_code",
			"description": "Blank = looked up from a Coretax Unit mapped to this item's stock UOM.",
		},
	],
	"Purchase Invoice": [
		{
			"fieldname": "eil_efaktur_section",
			"label": "e-Faktur Masukan (Input VAT)",
			"fieldtype": "Section Break",
			"insert_after": "tax_id",
			"collapsible": 1,
		},
		{
			"fieldname": "eil_faktur_number",
			"label": "Nomor Faktur Pajak (Supplier)",
			"fieldtype": "Data",
			"insert_after": "eil_efaktur_section",
			"description": "The faktur number on the supplier's e-Faktur — the evidence for the input-VAT credit.",
		},
		{
			"fieldname": "eil_faktur_date",
			"label": "Tanggal Faktur Pajak",
			"fieldtype": "Date",
			"insert_after": "eil_faktur_number",
		},
		{
			"fieldname": "eil_efaktur_col",
			"fieldtype": "Column Break",
			"insert_after": "eil_faktur_date",
		},
		{
			"fieldname": "eil_ppn_amount",
			"label": "PPN Masukan Override",
			"fieldtype": "Currency",
			"insert_after": "eil_efaktur_col",
			"description": "Blank = the invoice's total taxes. Set it when the faktur's PPN differs.",
		},
		{
			"fieldname": "eil_creditable",
			"label": "Creditable (Dapat Dikreditkan)",
			"fieldtype": "Check",
			"default": "1",
			"insert_after": "eil_ppn_amount",
		},
		{
			"fieldname": "eil_exclude",
			"label": "Exclude from PPN Masukan",
			"fieldtype": "Check",
			"insert_after": "eil_creditable",
		},
	],
	"Sales Invoice": [
		{
			"fieldname": "eil_efaktur_section",
			"label": "e-Faktur (Coretax)",
			"fieldtype": "Section Break",
			"insert_after": "tax_id",
			"collapsible": 1,
		},
		{
			"fieldname": "eil_kode_transaksi",
			"label": "Kode Transaksi",
			"fieldtype": "Link",
			"options": "Coretax Transaction Code",
			"insert_after": "eil_efaktur_section",
			"description": "01 normal sale · 02 government treasurer (bendahara) · 07/08 facilities.",
		},
		{
			"fieldname": "eil_pengganti",
			"label": "Replacement Invoice (Faktur Pengganti)",
			"fieldtype": "Check",
			"insert_after": "eil_kode_transaksi",
		},
		{
			"fieldname": "eil_exclude",
			"label": "Exclude from e-Faktur Export",
			"fieldtype": "Check",
			"insert_after": "eil_pengganti",
		},
		{
			"fieldname": "eil_efaktur_col",
			"fieldtype": "Column Break",
			"insert_after": "eil_exclude",
		},
		{
			"fieldname": "eil_faktur_status",
			"label": "e-Faktur Status",
			"fieldtype": "Select",
			"options": "\nNot Exported\nExported\nApproved\nRejected\nCancelled",
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
			"insert_after": "eil_efaktur_col",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "eil_faktur_number",
			"label": "Nomor Faktur Pajak",
			"fieldtype": "Data",
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
			"insert_after": "eil_faktur_status",
		},
		{
			"fieldname": "eil_faktur_date",
			"label": "Tanggal Faktur Pajak",
			"fieldtype": "Date",
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
			"insert_after": "eil_faktur_number",
		},
	],
}

# The nine standard DJP transaction codes. Stable since the e-Faktur era and
# carried into Coretax; descriptions are the official short labels.
TRANSACTION_CODES = [
	("01", "Kepada pihak yang bukan pemungut PPN (penyerahan normal)"),
	("02", "Kepada pemungut bendaharawan / instansi pemerintah"),
	("03", "Kepada pemungut PPN lainnya (selain instansi pemerintah)"),
	("04", "DPP nilai lain (Pasal 8A ayat 1)"),
	("05", "Besaran tertentu (Pasal 9A ayat 1)"),
	("06", "Penyerahan lainnya"),
	("07", "Penyerahan yang PPN-nya tidak dipungut"),
	("08", "Penyerahan yang PPN-nya dibebaskan"),
	("09", "Penyerahan aktiva (Pasal 16D)"),
]


def setup_eil():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	seed_transaction_codes()
	seed_settings_defaults()


def seed_transaction_codes():
	for code, description in TRANSACTION_CODES:
		if not frappe.db.exists("Coretax Transaction Code", code):
			frappe.get_doc(
				{
					"doctype": "Coretax Transaction Code",
					"code": code,
					"description": description,
				}
			).insert(ignore_permissions=True)


def seed_settings_defaults():
	settings = frappe.get_single("Indonesia Tax Settings")
	if not settings.default_transaction_code and frappe.db.exists("Coretax Transaction Code", "01"):
		settings.default_transaction_code = "01"
		settings.flags.ignore_permissions = True
		settings.save()
