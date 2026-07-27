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
		{
			"fieldname": "eil_is_pemungut",
			"label": "Government (Pemungut / WAPU)",
			"fieldtype": "Check",
			"insert_after": "eil_country_code",
			"description": "This buyer collects and deposits the PPN itself (bendahara/pemungut) and withholds PPh 22. Auto-set for the customer groups listed in Indonesia Tax Settings.",
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
		{
			"fieldname": "eil_ppn_bendahara_section",
			"label": "PPN Bendahara (WAPU)",
			"fieldtype": "Section Break",
			"insert_after": "eil_faktur_date",
			"depends_on": "eval:doc.eil_kode_transaksi=='02'",
			"collapsible": 1,
		},
		{
			"fieldname": "eil_bukti_setor_status",
			"label": "Bukti Setor Status",
			"fieldtype": "Select",
			"options": "\nBelum Diterima\nDiterima",
			"insert_after": "eil_ppn_bendahara_section",
			"allow_on_submit": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "eil_bukti_setor_no",
			"label": "No. Bukti Setor / SSP",
			"fieldtype": "Data",
			"insert_after": "eil_bukti_setor_status",
			"allow_on_submit": 1,
		},
		{
			"fieldname": "eil_bukti_setor_date",
			"label": "Tgl Bukti Setor",
			"fieldtype": "Date",
			"insert_after": "eil_bukti_setor_no",
			"allow_on_submit": 1,
		},
		{
			"fieldname": "eil_wapu_journal_entry",
			"label": "WAPU Reclassification Entry",
			"fieldtype": "Link",
			"options": "Journal Entry",
			"insert_after": "eil_bukti_setor_date",
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
		},
		# Government (pemungut/WAPU) charges. These deliberately live OUTSIDE
		# `taxes`: they must not move the invoice totals, so keeping them out of
		# ERPNext's tax engine lets them carry their real rate and amount instead
		# of a neutralised row plus shadow fields.
		{
			"fieldname": "eil_govt_section",
			"label": "Government Tax (WAPU)",
			"fieldtype": "Section Break",
			"insert_after": "eil_wapu_journal_entry",
			"depends_on": "eil_is_pemungut",
			"collapsible": 1,
		},
		{
			"fieldname": "eil_is_pemungut",
			"label": "Government (Pemungut / WAPU)",
			"fieldtype": "Check",
			"insert_after": "eil_govt_section",
			"description": "The buyer deposits the PPN itself and withholds PPh 22. Defaults from the customer / the source order, and can be set on an invoice raised by hand.",
			# Set alongside the charges, which are themselves allow_on_submit.
			"allow_on_submit": 1,
		},
		{
			"fieldname": "eil_govt_charges",
			"label": "Government Tax Charges",
			"fieldtype": "Table",
			"options": "EIL Govt Tax Charge",
			"insert_after": "eil_is_pemungut",
			"depends_on": "eil_is_pemungut",
			# The withheld PPh 22 is often only known exactly when the bukti potong
			# arrives, which is after the invoice is submitted. Editing is therefore
			# allowed post-submit, but only through update_invoice_govt_charges,
			# which re-posts the reclassification entry so the ledger cannot drift
			# away from this table.
			"allow_on_submit": 1,
			"description": "Populated from the template, then editable per invoice. A row with a rate recomputes its amount from the net total; a row with no rate keeps the amount you type. Carved out of the receivable by the reclassification entry, never added to the totals.",
		},
	],
	# Government (pemungut/WAPU) sales. The flag travels with the document so a
	# sales user only ever answers "is this a government customer?"; the charges
	# themselves are derived on the invoice from Indonesia Tax Settings.
	"Sales Order": [
		{
			"fieldname": "eil_is_pemungut",
			"label": "Government (Pemungut / WAPU)",
			"fieldtype": "Check",
			"insert_after": "taxes_and_charges",
			"description": "The buyer deposits the PPN itself and withholds PPh 22. Defaults from the customer; the accountant applies the actual charges on the invoice.",
		},
	],
	# The government treatment lives on the SAME master the sales team already
	# picks. A template that charges PPN 12% carries the 12% government variant
	# beside it, so the rate a customer was quoted and the rate on their faktur
	# cannot drift apart — which they could when the two were separate masters.
	"Sales Taxes and Charges Template": [
		{
			"fieldname": "eil_govt_section",
			"label": "Government (Pemungut / WAPU)",
			"fieldtype": "Section Break",
			"insert_after": "taxes",
			"collapsible": 1,
		},
		{
			"fieldname": "eil_govt_charges",
			"label": "Government Tax Charges",
			"fieldtype": "Table",
			"options": "EIL Govt Tax Charge",
			"insert_after": "eil_govt_section",
			"description": "Applied instead of the output VAT above when the buyer is a government treasurer (pemungut/WAPU). The PPN row should carry the same rate as the output-VAT row in this template. Other charges here — freight, handling — are unaffected and still apply.",
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
