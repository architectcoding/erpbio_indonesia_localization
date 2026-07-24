# PPN Keluaran (output VAT) register: the period's Sales Invoices with their
# DPP / DPP Nilai Lain / PPN as the exporter computes them, alongside each
# invoice's e-Faktur number and status — the working paper an accountant
# reconciles against Coretax before (and after) filing the period.

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 160},
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

	data = []
	for si in invoices:
		dpp = flt(si.base_net_total, 2)
		dpp_lain = flt(dpp * num / den, 2) if use_lain else dpp
		data.append(
			{
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
	return data
