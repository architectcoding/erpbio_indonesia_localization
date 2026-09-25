# PPN Keluaran (output VAT) register: the period's Sales Invoices with their
# DPP / DPP Nilai Lain / PPN as the exporter computes them -- its own faktur
# lines, one source, so a 12% template, a taxed freight charge or a faktur
# pelunasan reads here exactly as it files (T-008) -- beside the PPN the invoice
# itself charged, and each invoice's e-Faktur number and status: the working
# paper an accountant reconciles against Coretax before (and after) filing.
#
# A down payment that booked its own PPN (a termin paid from a Partial Invoice:
# Dr Bank / Cr Uang Muka / Cr PPN Keluaran) is output VAT of the month the money
# arrived — the faktur uang muka — so its Payment Entry is a row too. The final
# invoice then takes that PPN off its own (a negative first-row Actual line), and
# its row reports the DPP less the advance's — the faktur pelunasan.

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "voucher_type", "label": _("Voucher Type"), "fieldtype": "Data", "hidden": 1},
		{"fieldname": "sales_invoice", "label": _("Voucher"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 160},
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "customer_name", "label": _("Customer"), "fieldtype": "Data", "width": 180},
		{"fieldname": "buyer_npwp", "label": _("NPWP Pembeli"), "fieldtype": "Data", "width": 140},
		{"fieldname": "kode_transaksi", "label": _("Kode"), "fieldtype": "Data", "width": 60},
		{"fieldname": "dpp", "label": _("DPP"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "dpp_nilai_lain", "label": _("DPP Nilai Lain"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "ppn", "label": _("PPN"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "ppn_invoice", "label": _("PPN on Invoice"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "faktur_number", "label": _("Nomor Faktur"), "fieldtype": "Data", "width": 160},
		{"fieldname": "faktur_status", "label": _("e-Faktur Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "bukti_setor_status", "label": _("Bukti Setor"), "fieldtype": "Data", "width": 100},
	]


def get_data(filters):
	settings = frappe.get_single("Indonesia Tax Settings")
	tarif = flt(settings.tarif_ppn) or 12.0
	num = settings.dpp_numerator or 11
	den = settings.dpp_denominator or 12
	use_lain = bool(settings.use_dpp_nilai_lain)

	conditions = {"docstatus": 1, "is_return": 0, "eil_exclude": 0}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]

	invoices = frappe.get_all(
		"Sales Invoice",
		filters=conditions,
		fields=[
			"name",
			"posting_date",
			"customer",
			"customer_name",
			"tax_id",
			"base_net_total",
			"eil_kode_transaksi",
			"eil_faktur_number",
			"eil_faktur_status",
			"eil_bukti_setor_status",
		],
		order_by="posting_date asc, name asc",
	)

	effective = tarif / 100.0 * (num / den if use_lain else 1.0)
	exporter = frappe.new_doc("Coretax Faktur Export")

	data = []
	for si in invoices:
		doc = frappe.get_doc("Sales Invoice", si.name)
		dpp, dpp_lain, ppn = _faktur_figures(exporter, doc, settings)
		data.append(
			{
				"voucher_type": "Sales Invoice",
				"sales_invoice": si.name,
				"posting_date": si.posting_date,
				"customer_name": si.customer_name or si.customer,
				"buyer_npwp": si.tax_id or frappe.db.get_value("Customer", si.customer, "tax_id") or "",
				"kode_transaksi": si.eil_kode_transaksi or settings.default_transaction_code,
				"dpp": dpp,
				"dpp_nilai_lain": dpp_lain,
				"ppn": ppn,
				"ppn_invoice": _invoice_ppn(doc),
				"faktur_number": si.eil_faktur_number or "",
				"faktur_status": si.eil_faktur_status or _("Not Exported"),
				"bukti_setor_status": (si.eil_bukti_setor_status or _("Belum Diterima")) if si.eil_kode_transaksi == "02" else "",
			}
		)
	data.extend(_advance_rows(filters, settings, effective, num, den, use_lain))
	data.extend(_termin_rows(filters, settings, effective, num, den, use_lain))
	data.sort(key=lambda r: (str(r["posting_date"]), r["sales_invoice"]))
	return data


def _output_vat(company):
	from erpbio_indonesia_localization.doc_events.sales_invoice import _output_vat_accounts

	return _output_vat_accounts(company)


def _faktur_figures(exporter, si, settings):
	"""(DPP, DPP Nilai Lain, PPN) as the export files this invoice: the sum of
	its faktur lines -- items, taxed charges, a pelunasan's advance off."""
	lines = exporter._faktur_lines(si, settings)
	return (
		flt(sum(flt(line["dpp"]) for line in lines), 2),
		flt(sum(flt(line["dpp_lain"]) for line in lines), 2),
		flt(sum(flt(line["ppn"]) for line in lines), 2),
	)


def _invoice_ppn(si):
	from erpbio_indonesia_localization.erpbio_indonesia_localization.doctype.coretax_faktur_export.coretax_faktur_export import (
		_invoice_ppn as charged,
	)

	return charged(si)

def _advance_rows(filters, settings, effective, num, den, use_lain):
	"""Receipts that booked output VAT themselves: the faktur uang muka."""
	conditions = {"docstatus": 1, "payment_type": "Receive", "party_type": "Customer"}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	payments = {p.name: p for p in frappe.get_all(
		"Payment Entry", filters=conditions, fields=["name", "posting_date", "company", "party", "party_name"],
	)}
	if not payments:
		return []
	ppn = {}
	for t in frappe.get_all(
		"Advance Taxes and Charges",
		filters={"parenttype": "Payment Entry", "parent": ["in", list(payments)], "add_deduct_tax": "Add"},
		fields=["parent", "account_head", "base_tax_amount"],
	):
		if t.account_head in _output_vat(payments[t.parent].company):
			ppn[t.parent] = ppn.get(t.parent, 0) + flt(t.base_tax_amount)
	rows = []
	for name, amount in ppn.items():
		if not amount:
			continue
		p = payments[name]
		dpp = flt(amount / effective, 2)
		rows.append({
			"voucher_type": "Payment Entry",
			"sales_invoice": name,
			"posting_date": p.posting_date,
			"customer_name": p.party_name or p.party,
			"buyer_npwp": frappe.db.get_value("Customer", p.party, "tax_id") or "",
			"kode_transaksi": settings.default_transaction_code,
			"dpp": dpp,
			"dpp_nilai_lain": flt(dpp * num / den, 2) if use_lain else dpp,
			"ppn": flt(amount, 2),
			"faktur_number": "",
			"faktur_status": _("Uang Muka"),
			"bukti_setor_status": "",
		})
	return rows


def _termin_rows(filters, settings, effective, num, den, use_lain):
	"""A DP invoice's termin journal (erpbio_general's Partial Invoice: Dr Piutang
	Uang Muka / Cr Uang Muka / Cr PPN Out) is output VAT of the DP invoice's date
	— the faktur uang muka. An "Absorb" journal (an unpaid DP reversed into the
	final invoice) takes it back in its own month, as the ledger does."""
	meta = frappe.get_meta("Journal Entry")
	if not (meta.has_field("custom_termin_role") and meta.has_field("custom_partial_invoice")):
		return []
	conditions = {"docstatus": 1, "custom_termin_role": ["in", ["Termin", "Absorb"]]}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	journals = frappe.get_all(
		"Journal Entry", filters=conditions,
		fields=["name", "posting_date", "company", "custom_termin_role", "custom_partial_invoice"],
	)
	rows = []
	for je in journals:
		accounts = _output_vat(je.company)
		ppn = flt(frappe.db.sql(
			"select sum(credit - debit) from `tabJournal Entry Account` where parent=%s and account in %s",
			(je.name, list(accounts) or [""]),
		)[0][0], 2)
		if not ppn:
			continue
		pi = frappe.db.get_value(
			"Partial Invoice", je.custom_partial_invoice,
			["customer", "customer_name", "tax_id", "faktur_number", "faktur_status"], as_dict=True,
		) or frappe._dict()
		dpp = flt(ppn / effective, 2)
		rows.append({
			"voucher_type": "Journal Entry",
			"sales_invoice": je.name,
			"posting_date": je.posting_date,
			"customer_name": pi.customer_name or pi.customer or "",
			"buyer_npwp": pi.tax_id or (pi.customer and frappe.db.get_value("Customer", pi.customer, "tax_id")) or "",
			"kode_transaksi": settings.default_transaction_code,
			"dpp": dpp,
			"dpp_nilai_lain": flt(dpp * num / den, 2) if use_lain else dpp,
			"ppn": ppn,
			"faktur_number": pi.faktur_number or "",
			"faktur_status": pi.faktur_status or _("Not Exported") if je.custom_termin_role == "Termin" else _("Absorbed"),
			"bukti_setor_status": "",
		})
	return rows
