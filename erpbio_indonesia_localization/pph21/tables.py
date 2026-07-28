# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""Statutory table lookups for PPh 21.

Every rate resolves by `effective_from`, so a future change to the regulation is
data — a new set of rows — rather than a code change.

Nothing here will compute against unverified tables: `require_verified_tables()`
throws until an administrator has ticked the gate in EIL PPh 21 Settings. A
blocked payroll run is a far better failure than a silently wrong withholding.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

TER_CATEGORIES = ("A", "B", "C", "Harian")
PTKP_STATUSES = ("TK/0", "TK/1", "TK/2", "TK/3", "K/0", "K/1", "K/2", "K/3")


# --------------------------------------------------------------------- lookups
def ter_rate(category, monthly_gross, on_date=None):
	"""The effective rate (percent) for one period's gross income."""
	if category not in TER_CATEGORIES:
		frappe.throw(_("Unknown TER category {0}.").format(category))
	return _band_rate("EIL TER Bracket", monthly_gross, on_date, filters={"category": category},
	                  label=_("TER {0}").format(category))


def ptkp_annual(status, on_date=None):
	"""Annual Penghasilan Tidak Kena Pajak for a marital/dependant status."""
	return flt(_ptkp_row(status, on_date).annual_amount)


def ter_category(status, on_date=None):
	"""Which TER Bulanan table a PTKP status uses — stated by PMK 168 itself
	rather than inferred here, so the mapping cannot drift from the regulation."""
	return _ptkp_row(status, on_date).ter_category


def ter_category_or_none(status, on_date=None):
	"""The TER category, or None when the tables cannot answer.

	For display only. frappe.throw queues its message even when the exception is
	caught, so it must be cleared too — otherwise a page that merely *shows* a
	category reports "rate tables have not been verified" as if the user's action
	failed, which is how this masked a real error.
	"""
	if not status:
		return None
	try:
		return ter_category(status, on_date)
	except Exception:
		frappe.clear_last_message()
		return None


def ptkp_annual_or_none(status, on_date=None):
	"""Annual PTKP, or None when the tables cannot answer. See above."""
	if not status:
		return None
	try:
		return ptkp_annual(status, on_date)
	except Exception:
		frappe.clear_last_message()
		return None


def pasal17_tax(taxable_income, on_date=None):
	"""Annual tax from the Pasal 17 ayat (1) huruf a progressive brackets.

	Progressive, so every band below the top one is charged in full — unlike the
	TER lookup, which picks a single band's rate.
	"""
	require_verified_tables()
	brackets = _rows("EIL PPh 21 Bracket", on_date)
	if not brackets:
		frappe.throw(_("No PPh 21 (Pasal 17) brackets are loaded for {0}.").format(on_date or nowdate()))

	remaining, tax = flt(taxable_income), 0.0
	for row in brackets:
		if remaining <= 0:
			break
		# Bands are stored with an inclusive lower bound (0, then 60,000,001, …).
		# The income a band actually taxes is measured from the rupiah *below* its
		# lower bound, so the first band covers 60,000,000 — not 60,000,001.
		floor = flt(row.from_amount) - 1 if flt(row.from_amount) else 0
		upper = flt(row.to_amount)
		width = (upper - floor) if upper else remaining
		taxed = min(remaining, width)
		tax += taxed * flt(row.rate) / 100.0
		remaining -= taxed
	return tax


# ------------------------------------------------------------------ the gate
def require_verified_tables():
	settings = frappe.get_cached_doc("EIL PPh 21 Settings")
	if not settings.tables_verified:
		frappe.throw(
			_(
				"PPh 21 rate tables have not been verified. Open EIL PPh 21 Settings, check the "
				"loaded TER, PTKP and Pasal 17 tables against the regulation, then tick "
				"“Rate tables verified against the regulation”."
			),
			title=_("PPh 21 tables unverified"),
		)


def validate_tables(on_date=None):
	"""Structural problems in the loaded tables, as a list of strings.

	A bracket table that overlaps, leaves a gap, or whose rates fall is wrong
	whatever its source — these caught a bad published rate and two bugs in the
	extractor that produced the shipped fixture.
	"""
	problems = []
	for category in TER_CATEGORIES:
		rows = _rows("EIL TER Bracket", on_date, filters={"category": category})
		# TER Harian stops at Rp 2,500,000 by design — above that the daily rate no
		# longer applies at all (gross x 50% x Pasal 17), so it must NOT be open-ended.
		problems += _band_problems(rows, f"TER {category}", open_ended=category != "Harian")
	problems += _band_problems(_rows("EIL PPh 21 Bracket", on_date), "Pasal 17")

	statuses = {r.ptkp_status for r in _rows("EIL PTKP Rate", on_date)}
	missing = [s for s in PTKP_STATUSES if s not in statuses]
	if missing:
		problems.append(f"PTKP: no rate for {', '.join(missing)}")
	return problems


def _band_problems(rows, label, open_ended=True):
	if not rows:
		return [f"{label}: no bands loaded"]
	problems = []
	if flt(rows[0].from_amount) != 0:
		problems.append(f"{label}: first band starts at {rows[0].from_amount}, not 0")
	if open_ended and flt(rows[-1].to_amount) != 0:
		problems.append(f"{label}: top band is not open-ended")
	if not open_ended and not flt(rows[-1].to_amount):
		problems.append(f"{label}: top band should be bounded, not open-ended")
	for i, row in enumerate(rows):
		if not 0 <= flt(row.rate) <= 100:
			problems.append(f"{label} band {i + 1}: rate {row.rate} out of range")
		if flt(row.to_amount) and flt(row.to_amount) < flt(row.from_amount):
			problems.append(f"{label} band {i + 1}: to < from")
		if i:
			previous = rows[i - 1]
			if flt(previous.to_amount) and flt(row.from_amount) != flt(previous.to_amount) + 1:
				problems.append(
					f"{label} band {i + 1}: starts {row.from_amount}, previous ended {previous.to_amount}"
				)
			if flt(row.rate) < flt(previous.rate):
				problems.append(f"{label} band {i + 1}: rate falls {previous.rate} → {row.rate}")
	return problems


# ------------------------------------------------------------------ internals
def _band_rate(doctype, amount, on_date, filters, label):
	require_verified_tables()
	rows = _rows(doctype, on_date, filters=filters)
	if not rows:
		frappe.throw(_("No {0} bands are loaded for {1}.").format(label, on_date or nowdate()))
	amount = flt(amount)
	for row in rows:
		upper = flt(row.to_amount)
		if amount >= flt(row.from_amount) and (not upper or amount <= upper):
			return flt(row.rate)
	# Reachable only if the table has a gap, which validate_tables() would flag.
	frappe.throw(_("No {0} band covers {1}.").format(label, amount))


def _ptkp_row(status, on_date=None):
	require_verified_tables()
	rows = [r for r in _rows("EIL PTKP Rate", on_date) if r.ptkp_status == status]
	if not rows:
		frappe.throw(_("No PTKP rate is loaded for status {0}.").format(status or "?"))
	return rows[0]


def _rows(doctype, on_date=None, filters=None):
	"""Rows in force on a date, ordered by band. Cached per request: fast within a
	payroll run, never stale across one, so an administrator's correction takes
	effect on the next request without a cache flush."""
	on_date = getdate(on_date or nowdate())
	key = (doctype, str(on_date), tuple(sorted((filters or {}).items())))
	cache = getattr(frappe.local, "_eil_pph21_tables", None)
	if cache is None:
		cache = frappe.local._eil_pph21_tables = {}
	if key in cache:
		return cache[key]

	conditions = dict(filters or {})
	conditions["effective_from"] = ("<=", on_date)
	rows = frappe.get_all(doctype, filters=conditions, fields=["*"], order_by="effective_from desc")
	if rows:
		# Only the newest set in force applies; older ones are history.
		newest = rows[0].effective_from
		rows = [frappe._dict(r) for r in rows if r.effective_from == newest]
		rows.sort(key=lambda r: flt(r.from_amount))
	cache[key] = rows
	return rows
