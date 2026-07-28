# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""Write the PPh 21 deduction onto a Salary Slip.

Hooked through HRMS's own `apply_regional_deductions` extension point rather than
a doc_events observer. That matters: HRMS calls it from inside
`calculate_net_pay()` *after* earnings and deductions are computed but *before*
`set_net_pay()` finalises the totals, so the deduction is picked up by net pay,
the rounded total and the base-currency figures without this app recomputing any
of them. A `validate` hook would run after all of that and leave stale totals.

Registered per region in hooks.py, so it only ever fires for an Indonesian
company.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from erpbio_indonesia_localization.pph21 import calculator

# How a component's PPh 21 treatment classifies it. Blank earnings count as
# regular pay, which is the common case and the safe default; blank deductions
# are ignored, because guessing that an arbitrary deduction is pension or zakat
# would silently change someone's tax.
EARNING_TREATMENTS = {"Gaji", "Teratur", "Tidak Teratur", "Natura", "Premi Pemberi Kerja"}
DEDUCTION_TREATMENTS = {"Iuran Pensiun", "Zakat"}


def apply_pph21_deduction(slip):
	"""HRMS regional hook: set the PPh 21 row on this slip, if it applies."""
	settings = frappe.get_cached_doc("EIL PPh 21 Settings")
	component = settings.pph21_component
	if not settings.enabled or not component:
		return
	# Opt-in per salary structure, so PPh 21 only touches employees whose
	# structure carries it. The row itself may not be on the slip yet: HRMS drops
	# a zero-valued deduction, and the whole point is that we supply the value.
	if not _structure_includes(slip, component):
		return

	employee = frappe.get_cached_doc("Employee", slip.employee)
	scheme = employee.get("eil_pph21_scheme")
	calculator.require_supported_scheme(scheme)
	status = employee.get("eil_ptkp_status")
	if not status:
		frappe.throw(
			_("Set the PTKP Status on employee {0} before calculating PPh 21.").format(
				frappe.bold(slip.employee_name or slip.employee)
			),
			title=_("PTKP status missing"),
		)

	amount = _amount_for_period(slip, employee, status, scheme)
	# HRMS's own routine, so the row picks up the component's flags and precision
	# exactly as any other deduction would. The component is seeded with
	# depends_on_payment_days = 0: a month's tax follows that month's gross, which
	# already reflects any unpaid days.
	slip.update_component_row(
		frappe.get_cached_doc("Salary Component", component),
		amount,
		"deductions",
		default_amount=amount,
	)


def _structure_includes(slip, component):
	if not slip.salary_structure:
		return False
	return bool(
		frappe.db.exists(
			"Salary Detail",
			{
				"parent": slip.salary_structure,
				"parenttype": "Salary Structure",
				"parentfield": "deductions",
				"salary_component": component,
			},
		)
	)


def _amount_for_period(slip, employee, status, scheme):
	on_date = getdate(slip.end_date)
	# A pegawai tidak tetap on monthly payroll is charged the monthly rate in
	# every period including the last — no year-end settlement.
	if not calculator.reconciles_annually(scheme) or not _is_final_period(slip):
		return calculator.monthly_withholding(status, _period_gross(slip), on_date)

	totals = _year_to_date(slip, employee)
	result = calculator.annual_reconciliation(
		status,
		gross_teratur=totals["gaji"] + totals["teratur"],
		gross_tidak_teratur=totals["tidak_teratur"],
		natura=totals["natura"],
		employer_premium=totals["premi"],
		iuran_pensiun=totals["iuran_pensiun"],
		zakat=totals["zakat"],
		months_worked=totals["months"],
		withheld_earlier_periods=totals["withheld"],
		withheld_previous_employer=flt(slip.get("tax_deducted_till_date")),
		on_date=on_date,
	)
	return result["payable_final_period"]


def _is_final_period(slip):
	"""The annual calculation belongs to the last period of the payroll period —
	December for a calendar year, or the employee's final month if they leave
	earlier."""
	if not slip.payroll_period:
		return False
	period_end = frappe.db.get_value("Payroll Period", slip.payroll_period, "end_date")
	if getdate(slip.end_date) >= getdate(period_end):
		return True
	relieving = frappe.db.get_value("Employee", slip.employee, "relieving_date")
	return bool(relieving and getdate(slip.end_date) >= getdate(relieving))


def _period_gross(slip):
	"""This period's gross for TER purposes: every earning the treatment counts,
	which is all of them unless a component is explicitly Excluded."""
	treatments = _component_treatments()
	total = 0.0
	for row in slip.get("earnings", []):
		if row.statistical_component:
			continue
		treatment = treatments.get(row.salary_component) or "Teratur"
		if treatment in EARNING_TREATMENTS:
			total += flt(row.amount)
	return total


def _year_to_date(slip, employee):
	"""Everything the annual calculation needs, gathered from this payroll
	period's submitted slips plus the one being calculated."""
	treatments = _component_treatments()
	settings = frappe.get_cached_doc("EIL PPh 21 Settings")
	period_start = frappe.db.get_value("Payroll Period", slip.payroll_period, "start_date")

	# `gaji` is tracked apart from the rest of the regular pay purely so the annual
	# certificate can print DJP's two separate lines; tax treats them the same.
	totals = dict(gaji=0.0, teratur=0.0, tidak_teratur=0.0, natura=0.0, premi=0.0,
	              iuran_pensiun=0.0, zakat=0.0, withheld=0.0, months=0)

	earlier = frappe.get_all(
		"Salary Slip",
		filters={
			"employee": slip.employee,
			"docstatus": 1,
			"start_date": (">=", period_start),
			"end_date": ("<", slip.start_date),
		},
		pluck="name",
	)
	for name in earlier:
		_absorb(totals, frappe.get_doc("Salary Slip", name), treatments, settings)
	_absorb(totals, slip, treatments, settings, count_withholding=False)
	totals["months"] = min(max(len(earlier) + 1, 1), 12)
	return totals


def _absorb(totals, slip, treatments, settings, count_withholding=True):
	for row in slip.get("earnings", []):
		if row.statistical_component:
			continue
		treatment = treatments.get(row.salary_component) or "Teratur"
		if treatment == "Tidak Teratur":
			totals["tidak_teratur"] += flt(row.amount)
		elif treatment == "Natura":
			totals["natura"] += flt(row.amount)
		elif treatment == "Premi Pemberi Kerja":
			totals["premi"] += flt(row.amount)
		elif treatment == "Gaji":
			totals["gaji"] += flt(row.amount)
		elif treatment == "Teratur":
			totals["teratur"] += flt(row.amount)

	for row in slip.get("deductions", []):
		if row.salary_component == settings.pph21_component:
			if count_withholding:
				totals["withheld"] += flt(row.amount)
			continue
		treatment = treatments.get(row.salary_component)
		if treatment == "Iuran Pensiun":
			totals["iuran_pensiun"] += flt(row.amount)
		elif treatment == "Zakat":
			totals["zakat"] += flt(row.amount)


def _component_treatments():
	if not hasattr(frappe.local, "_eil_pph21_treatments"):
		frappe.local._eil_pph21_treatments = {
			row.name: row.eil_pph21_treatment
			for row in frappe.get_all("Salary Component", fields=["name", "eil_pph21_treatment"])
		}
	return frappe.local._eil_pph21_treatments
