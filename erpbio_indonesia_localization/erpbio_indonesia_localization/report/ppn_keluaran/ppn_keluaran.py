# PPN Keluaran (output VAT) register: the period's Sales Invoices with their
# DPP / DPP Nilai Lain / PPN as the exporter computes them, alongside each
# invoice's e-Faktur number and status — the working paper an accountant
# reconciles against Coretax before (and after) filing the period.
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
	advance_ppn = _advance_ppn_taken_off([si.name for si in invoices])

	data = []
	for si in invoices:
		dpp = flt(flt(si.base_net_total) - advance_ppn.get(si.name, 0) / effective, 2)
		dpp_lain = flt(dpp * num / den, 2) if use_lain else dpp
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
				"ppn": flt(dpp_lain * tarif / 100.0, 2),
				"faktur_number": si.eil_faktur_number or "",
				"faktur_status": si.eil_faktur_status or _("Not Exported"),
				"bukti_setor_status": (si.eil_bukti_setor_status or _("Belum Diterima")) if si.eil_kode_transaksi == "02" else "",
			}
		)
	data.extend(_advance_rows(filters, settings, effective, num, den, use_lain))
	data.sort(key=lambda r: (str(r["posting_date"]), r["sales_invoice"]))
	return data


def _output_vat(company):
	from erpbio_indonesia_localization.doc_events.sales_invoice import _output_vat_accounts

	return _output_vat_accounts(company)


def _advance_ppn_taken_off(names):
	"""{invoice: PPN already booked on its advances} — the negative Actual rows
	on output-VAT accounts (see doc_events.sales_invoice.is_advance_vat_row)."""
	from erpbio_indonesia_localization.doc_events.sales_invoice import is_advance_vat_row

	if not names:
		return {}
	rows = frappe.get_all(
		"Sales Taxes and Charges",
		filters={"parenttype": "Sales Invoice", "parent": ["in", names], "charge_type": "Actual", "tax_amount": ["<", 0]},
		fields=["parent", "charge_type", "account_head", "tax_amount", "base_tax_amount"],
	)
	companies = dict(frappe.get_all("Sales Invoice", filters={"name": ["in", list({r.parent for r in rows})]}, fields=["name", "company"], as_list=True)) if rows else {}
	out = {}
	for r in rows:
		if is_advance_vat_row(r, _output_vat(companies.get(r.parent))):
			out[r.parent] = out.get(r.parent, 0) - flt(r.base_tax_amount or r.tax_amount)
	return out


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
