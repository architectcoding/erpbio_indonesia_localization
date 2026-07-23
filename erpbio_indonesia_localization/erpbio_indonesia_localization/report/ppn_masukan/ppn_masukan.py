# PPN Masukan (input VAT) register: the period's Purchase Invoices with the
# supplier's faktur number and the creditable PPN. PPN per invoice is the
# explicit eil_ppn_amount override when set, else the invoice's total taxes —
# right for the common case where PPN is the only purchase tax, overridable
# when it isn't.

import frappe
from frappe import _
from frappe.utils import flt


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
	]


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

	data = []
	for pi in invoices:
		ppn = flt(pi.eil_ppn_amount) or flt(pi.base_total_taxes_and_charges)
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
				"creditable": pi.eil_creditable,
			}
		)
	return data
