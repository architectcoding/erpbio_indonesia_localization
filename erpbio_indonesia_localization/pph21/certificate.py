# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""Build the annual withholding certificate (BPA1) for a permanent employee.

Every figure comes from the same `annual_reconciliation` the December salary slip
used, over the same payroll period's submitted slips. The certificate never
re-derives the tax by another route — if it did, the employee's copy could
disagree with what was actually withheld, and only one of them can be right.

BPA1 is the Coretax-era name (PER-11/PJ/2025) for what used to be form 1721-A1;
BPA2 covers PNS/ASN/TNI/POLRI and is not built.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from erpbio_indonesia_localization.pph21 import calculator, salary_slip, tables


@frappe.whitelist()
def generate(employee, payroll_period, company=None):
	"""Create (or refresh a draft) BPA1 for one employee and period."""
	frappe.has_permission("EIL Bukti Potong A1", "create", throw=True)
	data = collect(employee, payroll_period, company)

	existing = frappe.db.exists(
		"EIL Bukti Potong A1",
		{"employee": employee, "payroll_period": payroll_period, "docstatus": 0},
	)
	doc = frappe.get_doc("EIL Bukti Potong A1", existing) if existing else frappe.new_doc(
		"EIL Bukti Potong A1"
	)
	doc.update(data)
	doc.save()
	return {"name": doc.name, "amended": bool(existing)}


def collect(employee, payroll_period, company=None):
	"""The certificate's figures, without touching the database."""
	employee_doc = frappe.get_cached_doc("Employee", employee)
	scheme = employee_doc.get("eil_pph21_scheme") or "Permanent"
	if not calculator.reconciles_annually(scheme):
		frappe.throw(
			_(
				"{0} is on the {1} scheme. An annual certificate settles the year on Pasal 17, "
				"which only applies to permanent employees — a non-permanent employee is taxed "
				"period by period and receives a certificate per payment instead."
			).format(employee_doc.employee_name or employee, scheme),
			title=_("Not a pegawai tetap"),
		)
	status = employee_doc.get("eil_ptkp_status")
	if not status:
		frappe.throw(_("Set the PTKP Status on employee {0} first.").format(employee))

	period = frappe.get_cached_doc("Payroll Period", payroll_period)
	slips = _submitted_slips(employee, period)
	if not slips:
		frappe.throw(
			_("{0} has no submitted salary slips in {1}, so there is nothing to certify.").format(
				employee_doc.employee_name or employee, payroll_period
			)
		)

	totals = _totals(slips)
	on_date = getdate(period.end_date)
	result = calculator.annual_reconciliation(
		status,
		gross_teratur=totals["gaji"] + totals["teratur"],
		gross_tidak_teratur=totals["tidak_teratur"],
		natura=totals["natura"],
		employer_premium=totals["premi"],
		iuran_pensiun=totals["iuran_pensiun"],
		zakat=totals["zakat"],
		months_worked=len(slips),
		withheld_earlier_periods=totals["withheld"],
		withheld_previous_employer=totals["previous_employer"],
		on_date=on_date,
	)
	ptkp = tables.ptkp_breakdown(status, on_date)

	return {
		"employee": employee,
		"payroll_period": payroll_period,
		"company": company or employee_doc.company,
		"tax_year": str(getdate(period.end_date).year),
		"ptkp_status": status,
		"ter_category": tables.ter_category_or_none(status, on_date),
		"npwp": employee_doc.get("eil_npwp"),
		"nik": employee_doc.get("eil_nik"),
		# income, on the certificate's own lines
		"gaji": totals["gaji"],
		"tunjangan": totals["teratur"],
		"natura": totals["natura"],
		"tantiem_bonus_thr": totals["tidak_teratur"],
		"premi_asuransi": totals["premi"],
		"gross": result["gross"],
		# deductions
		"biaya_jabatan": result["biaya_jabatan"],
		"iuran_pensiun": result["iuran_pensiun"],
		"zakat": result["zakat"],
		"total_pengurangan": result["deductions"],
		# taxable
		"neto": result["net"],
		"ptkp_self": ptkp["self"],
		"ptkp_married": ptkp["married"],
		"ptkp_dependants": ptkp["dependants_total"],
		"ptkp": result["ptkp"],
		"pkp": result["pkp"],
		"months_worked": result["months_worked"],
		"annualised": 1 if result["annualised"] else 0,
		"pasal17_detail": _pasal17_detail(result["pkp"], on_date),
		# tax
		"annual_tax": result["annual_tax"],
		# The whole year, final period included — by the time a certificate is
		# issued December has been paid, so "withheld before the final period"
		# would understate it.
		"tax_withheld_total": totals["withheld"],
		"withheld_previous_employer": result["withheld_previous_employer"],
		"dtp": result["dtp"],
		"difference": result["annual_tax"] - totals["withheld"] - result["withheld_previous_employer"],
		"salary_slips": ", ".join(s.name for s in slips),
	}


def _submitted_slips(employee, period):
	names = frappe.get_all(
		"Salary Slip",
		filters={
			"employee": employee,
			"docstatus": 1,
			"start_date": (">=", period.start_date),
			"end_date": ("<=", period.end_date),
		},
		order_by="start_date asc",
		pluck="name",
	)
	return [frappe.get_doc("Salary Slip", name) for name in names]


def _totals(slips):
	"""Sum the year exactly as the salary slip hook classifies components, so the
	certificate and the withholding cannot disagree about what was taxable."""
	treatments = salary_slip._component_treatments()
	settings = frappe.get_cached_doc("EIL PPh 21 Settings")
	totals = dict(gaji=0.0, teratur=0.0, tidak_teratur=0.0, natura=0.0, premi=0.0,
	              iuran_pensiun=0.0, zakat=0.0, withheld=0.0, previous_employer=0.0)
	for slip in slips:
		salary_slip._absorb(totals, slip, treatments, settings)
	# What a previous employer withheld, if the employee handed over their bupot.
	# HRMS keeps it on the structure assignment as an opening balance.
	assignment = frappe.get_all(
		"Salary Structure Assignment",
		filters={"employee": slips[0].employee, "docstatus": 1},
		fields=["tax_deducted_till_date"],
		order_by="from_date desc",
		limit=1,
	)
	if assignment:
		totals["previous_employer"] = flt(assignment[0].tax_deducted_till_date)
	return totals


def _pasal17_detail(pkp, on_date):
	lines = []
	for band in tables.pasal17_bands(pkp, on_date):
		if not band["taxed"]:
			continue
		lines.append(f"{band['rate']:g}% x {band['taxed']:,.0f} = {band['tax']:,.0f}")
	return "\n".join(lines)
