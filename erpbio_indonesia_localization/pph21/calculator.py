# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""PPh 21 for permanent and non-permanent employees.

Three calculations, per PP 58/2023 and PMK 168/2023:

* any ordinary period — gross for the period x the TER effective rate;
* the final period, pegawai tetap only — the full annual calculation on
  Pasal 17, less what has already been withheld. The difference lands in that
  period, and can be negative when TER over-withheld.
* a non-monthly payment to a pegawai tidak tetap — the daily table, or, above
  its ceiling, Pasal 17 on half the gross.

A non-permanent employee paid monthly simply gets the monthly rate every month,
December included: there is no annual settlement for them.

Pure functions over plain numbers: no documents, no side effects. That keeps the
annual path testable without generating twelve salary slips, and it is what lets
the DJP worked examples serve as the test suite (see test_calculator.py).

Terms, because the mix of languages is unavoidable here:
  teratur / tidak teratur  regular pay vs bonus, THR, tantiem, gratifikasi
  biaya jabatan            standard occupational deduction, 5% capped
  PTKP                     personal allowance
  PKP                      taxable income after PTKP
  disetahunkan             annualised, for a part-year employment
"""

import math

import frappe
from frappe import _
from frappe.utils import flt

from erpbio_indonesia_localization.pph21 import tables

SUPPORTED_SCHEMES = ("Permanent", "Non-permanent")


def monthly_withholding(ptkp_status, period_gross, on_date=None):
	"""What to withhold in an ordinary (non-final) period."""
	category = tables.ter_category(ptkp_status, on_date)
	rate = tables.ter_rate(category, period_gross, on_date)
	return _round_rupiah(flt(period_gross) * rate / 100.0)


def daily_withholding(daily_gross, on_date=None):
	"""A non-monthly payment to a pegawai tidak tetap (PMK 168 Pasal 15).

	Two rules, split at the top of the TER Harian table:
	  * up to that, the daily effective rate on the day's gross;
	  * above it, the Pasal 17 brackets on *half* the gross — a different
	    mechanism, not a further band of the same table, which is why the daily
	    table is deliberately not open-ended.

	The threshold is read from the table rather than written here, so it moves
	when the regulation does.
	"""
	daily_gross = flt(daily_gross)
	threshold = _daily_threshold(on_date)
	if daily_gross <= threshold:
		rate = tables.ter_rate("Harian", daily_gross, on_date)
		return _round_rupiah(daily_gross * rate / 100.0)
	return _round_rupiah(tables.pasal17_tax(daily_gross * 0.5, on_date))


def average_daily_gross(total_gross, days):
	"""Piece and contract work is assessed on the average day, not the payment:
	Rp 4,500,000 for ten days' work is a Rp 450,000 day."""
	days = int(flt(days) or 0)
	if days < 1:
		frappe.throw(_("Days worked must be at least 1, got {0}.").format(days))
	return flt(total_gross) / days


def annual_reconciliation(
	ptkp_status,
	gross_teratur,
	gross_tidak_teratur=0,
	natura=0,
	employer_premium=0,
	iuran_pensiun=0,
	zakat=0,
	months_worked=12,
	annualise=False,
	withheld_earlier_periods=0,
	withheld_previous_employer=0,
	dtp=0,
	on_date=None,
):
	"""The final period's calculation, returned as a full breakdown.

	Every line the annual certificate (BPA1) has to show is in the result, so the
	form later reads this rather than recomputing and risking a different answer.

	`annualise` is the disetahunkan case — a part year that the regulation treats
	as if it were whole (a new expatriate hire, say). The tax is then scaled back
	down to the months actually worked. An ordinary joiner or leaver is NOT
	annualised: they simply have less gross.
	"""
	months = _months(months_worked)
	settings = frappe.get_cached_doc("EIL PPh 21 Settings")

	gross = flt(gross_teratur) + flt(gross_tidak_teratur) + flt(natura) + flt(employer_premium)
	biaya_jabatan = _biaya_jabatan(gross, months, settings)
	deductions = biaya_jabatan + flt(iuran_pensiun) + flt(zakat)
	net = gross - deductions

	# Annualise the NET, not the tax: PTKP is a full-year allowance either way.
	net_for_tax = net * 12.0 / months if annualise else net
	ptkp = tables.ptkp_annual(ptkp_status, on_date)
	pkp = _floor_thousand(max(0.0, net_for_tax - ptkp))

	tax = tables.pasal17_tax(pkp, on_date)
	if annualise:
		tax = tax * months / 12.0
	tax = _round_rupiah(tax)

	credited = flt(withheld_earlier_periods) + flt(withheld_previous_employer) + flt(dtp)
	return {
		"gross": gross,
		"gross_teratur": flt(gross_teratur),
		"gross_tidak_teratur": flt(gross_tidak_teratur),
		"natura": flt(natura),
		"employer_premium": flt(employer_premium),
		"biaya_jabatan": biaya_jabatan,
		"iuran_pensiun": flt(iuran_pensiun),
		"zakat": flt(zakat),
		"deductions": deductions,
		"net": net,
		"net_annualised": net_for_tax if annualise else None,
		"ptkp_status": ptkp_status,
		"ptkp": ptkp,
		"pkp": pkp,
		"annual_tax": tax,
		"withheld_earlier_periods": flt(withheld_earlier_periods),
		"withheld_previous_employer": flt(withheld_previous_employer),
		"dtp": flt(dtp),
		"months_worked": months,
		"annualised": bool(annualise),
		# Negative means TER took more than the year owed — a refund to settle,
		# not something to quietly clamp to zero.
		"payable_final_period": _round_rupiah(tax - credited),
	}


def reconciles_annually(scheme):
	"""Whether the final period settles the year on Pasal 17.

	Only pegawai tetap do. A non-permanent employee paid monthly is charged the
	monthly effective rate in December exactly as in every other month — PMK 168's
	own worked example ends the year with a plain 1.5% month, not a settlement.
	"""
	return (scheme or "Permanent") == "Permanent"


def require_supported_scheme(scheme):
	"""Expatriate and pensioner schemes are not implemented. They throw rather
	than silently borrowing another scheme's arithmetic."""
	if (scheme or "Permanent") not in SUPPORTED_SCHEMES:
		frappe.throw(
			_(
				"PPh 21 for the {0} scheme is not supported yet — permanent (pegawai tetap) and "
				"non-permanent (pegawai tidak tetap) employees are calculated. Clear the PPh 21 "
				"component for this employee, or compute it by hand."
			).format(scheme),
			title=_("PPh 21 scheme not supported"),
		)


# ------------------------------------------------------------------ internals
def _biaya_jabatan(gross, months, settings):
	"""PMK 168 Pasal 5(3): 5% of gross, capped per month worked — so a part year
	caps proportionally rather than at the full annual Rp 6,000,000."""
	percent = flt(settings.biaya_jabatan_percent) or 5.0
	monthly_cap = flt(settings.biaya_jabatan_monthly_cap) or 500_000.0
	return min(flt(gross) * percent / 100.0, monthly_cap * months)


def _daily_threshold(on_date=None):
	"""Top of the TER Harian table — above it a different rule applies."""
	rows = tables.daily_bands(on_date)
	if not rows or not flt(rows[-1].to_amount):
		frappe.throw(_("The TER Harian table has no upper bound; PPh 21 cannot be calculated daily."))
	return flt(rows[-1].to_amount)


def _months(months_worked):
	months = int(flt(months_worked) or 12)
	if not 1 <= months <= 12:
		frappe.throw(_("Months worked must be between 1 and 12, got {0}.").format(months_worked))
	return months


def _floor_thousand(amount):
	"""PKP is rounded down to whole thousands of rupiah before the brackets."""
	return math.floor(flt(amount) / 1000.0) * 1000


def _round_rupiah(amount):
	"""Rupiah has no subunit in practice. Centralised so the convention is one
	line to change if a filing ever disagrees with it."""
	return float(round(flt(amount)))
