# PPN Masukan (input VAT) register: the period's Purchase Invoices with the
# supplier's faktur number and the creditable PPN. PPN per invoice is the
# explicit eil_ppn_amount override when set, else what the invoice's input-VAT
# rows charged -- never its total taxes, which net a PPh 23 withholding out of
# the input VAT (T-011). An invoice's PPN is creditable only when it has one, a
# supplier faktur backs it and the faktur is within the crediting window
# (T-006); the row says why when it is not.

import frappe
from frappe import _
from frappe.utils import flt, getdate

# UU PPN art. 9(9) as amended by UU HPP: input tax may be credited in the tax
# period of the faktur or at the latest the third period after it.
CREDIT_WINDOW_PERIODS = 3


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "purchase_invoice", "label": _("Purchase Invoice"), "fieldtype": "Link", "options": "Purchase Invoice", "width": 160},
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "supplier_name", "label": _("Supplier"), "fieldtype": "Data", "width": 180},
		{"fieldname": "supplier_npwp", "label": _("NPWP Penjual"), "fieldtype": "Data", "width": 140},
		{"fieldname": "dpp", "label": _("DPP"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "ppn", "label": _("PPN Masukan"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "faktur_number", "label": _("Nomor Faktur"), "fieldtype": "Data", "width": 160},
		{"fieldname": "faktur_date", "label": _("Tanggal Faktur"), "fieldtype": "Date", "width": 110},
		{"fieldname": "creditable", "label": _("Creditable"), "fieldtype": "Check", "width": 80},
		{"fieldname": "not_creditable_reason", "label": _("Why not creditable"), "fieldtype": "Data", "width": 220},
	]


def _input_vat_accounts(company):
	"""PPN Masukan as it sits in a chart of accounts: type "Tax" on the ASSET
	side. The mirror of the output-VAT rule (Tax + Liability) -- and what keeps
	a PPh 23 row (a liability withheld from the supplier) out of the input VAT."""
	return set(
		frappe.get_all(
			"Account",
			filters={"company": company, "account_type": "Tax", "root_type": "Asset", "is_group": 0},
			pluck="name",
		)
	)


def _invoice_input_vat(pi_name, accounts):
	"""The PPN the invoice's input-VAT rows charged, after any discount."""
	total = 0.0
	for r in frappe.get_all(
		"Purchase Taxes and Charges",
		filters={"parent": pi_name, "parenttype": "Purchase Invoice", "account_head": ["in", list(accounts) or [""]]},
		fields=["add_deduct_tax", "base_tax_amount_after_discount_amount", "base_tax_amount"],
	):
		amount = flt(r.base_tax_amount_after_discount_amount) or flt(r.base_tax_amount)
		total += -amount if r.add_deduct_tax == "Deduct" else amount
	return total


def _periods_between(earlier, later):
	earlier, later = getdate(earlier), getdate(later)
	return (later.year - earlier.year) * 12 + later.month - earlier.month


def not_creditable_reason(pi, ppn):
	"""Why this invoice's PPN cannot be credited, or "" when it can."""
	if flt(ppn) <= 0:
		return _("No PPN on the invoice")
	if not pi.eil_creditable:
		return _("Marked not creditable")
	if not (pi.eil_faktur_number or "").strip():
		return _("No supplier faktur number")
	if pi.eil_faktur_date and _periods_between(pi.eil_faktur_date, pi.posting_date) > CREDIT_WINDOW_PERIODS:
		return _("Faktur is more than {0} tax periods old").format(CREDIT_WINDOW_PERIODS)
	return ""


def get_data(filters):
	conditions = {"docstatus": 1, "is_return": 0, "eil_exclude": 0}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]

	invoices = frappe.get_all(
		"Purchase Invoice",
		filters=conditions,
		fields=[
			"name",
			"posting_date",
			"company",
			"supplier",
			"supplier_name",
			"tax_id",
			"base_net_total",
			"base_taxes_and_charges_added",
			"base_total_taxes_and_charges",
			"eil_ppn_amount",
			"eil_faktur_number",
			"eil_faktur_date",
			"eil_creditable",
		],
		order_by="posting_date asc, name asc",
	)

	accounts = {}
	data = []
	for pi in invoices:
		if pi.company not in accounts:
			accounts[pi.company] = _input_vat_accounts(pi.company)
		ppn = flt(pi.eil_ppn_amount) or _invoice_input_vat(pi.name, accounts[pi.company])
		reason = not_creditable_reason(pi, ppn)
		data.append(
			{
				"purchase_invoice": pi.name,
				"posting_date": pi.posting_date,
				"supplier_name": pi.supplier_name or pi.supplier,
				"supplier_npwp": pi.tax_id or frappe.db.get_value("Supplier", pi.supplier, "tax_id") or "",
				"dpp": flt(pi.base_net_total, 2),
				"ppn": flt(ppn, 2),
				"faktur_number": pi.eil_faktur_number or "",
				"faktur_date": pi.eil_faktur_date,
				"creditable": 0 if reason else 1,
				"not_creditable_reason": reason,
			}
		)
	return data
