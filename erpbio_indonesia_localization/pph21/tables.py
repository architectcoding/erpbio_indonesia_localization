# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""Statutory table lookups for PPh 21.

Every rate belongs to a rate set (EIL PPh 21 Rate Set, see rate_sets.py), and a
lookup reads the set in force on its date -- the newest set whose effective date
is on or before it. A change to the regulation is a new set: data, not code.

Nothing here computes on an unverified set: `require_verified_tables(on_date)`
throws when the set in force is still a Draft, even if an older verified set
exists -- a blocked payroll run is a far better failure than a silently wrong
withholding.
"""

from contextlib import contextmanager

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


def daily_bands(on_date=None):
	"""The TER Harian bands in force, so callers can read the threshold above
	which the daily rate stops applying instead of hardcoding it."""
	require_verified_tables(on_date)
	return _rows("EIL TER Bracket", on_date, filters={"category": "Harian"})


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
	require_verified_tables(on_date)
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


def pasal17_bands(taxable_income, on_date=None):
	"""The Pasal 17 calculation band by band, as the certificate prints it
	("5% x 60.000.000 = 3.000.000"). Same arithmetic as pasal17_tax, kept
	together so a fix to one cannot leave the other stating something else."""
	require_verified_tables(on_date)
	remaining = flt(taxable_income)
	out = []
	for row in _rows("EIL PPh 21 Bracket", on_date):
		floor = flt(row.from_amount) - 1 if flt(row.from_amount) else 0
		upper = flt(row.to_amount)
		width = (upper - floor) if upper else max(remaining, 0.0)
		taxed = min(max(remaining, 0.0), width)
		out.append({
			"rate": flt(row.rate),
			"from_amount": flt(row.from_amount),
			"to_amount": upper,
			"taxed": taxed,
			"tax": taxed * flt(row.rate) / 100.0,
		})
		remaining -= taxed
	return out


def ptkp_breakdown(status, on_date=None):
	"""PTKP split into the lines the certificate shows: the taxpayer, the marriage
	supplement, and one line per dependant.

	Derived from the loaded rates rather than the well-known Rp 4,500,000 step, so
	it follows the table. The parts must add up to the status's own PTKP — if a
	table edit breaks the ladder, that is a real inconsistency and it throws here
	rather than printing a certificate whose lines do not sum to its total.
	"""
	total = ptkp_annual(status, on_date)
	base = ptkp_annual("TK/0", on_date)
	married_extra = ptkp_annual("K/0", on_date) - base
	per_dependant = ptkp_annual("TK/1", on_date) - base

	married = status.startswith("K/")
	dependants = int(status.split("/")[1])
	parts = {
		"self": base,
		"married": married_extra if married else 0.0,
		"dependants": dependants,
		"per_dependant": per_dependant,
		"dependants_total": per_dependant * dependants,
		"total": total,
	}
	summed = parts["self"] + parts["married"] + parts["dependants_total"]
	if round(summed) != round(total):
		frappe.throw(
			_("PTKP for {0} is {1} but its parts add up to {2}. Check the PTKP rate table.").format(
				status, total, summed
			)
		)
	return parts


# ------------------------------------------------------------------ the gate
@contextmanager
def preview_unverified(rate_set=None):
	"""Let a read-only preview compute before a set is verified: reading an
	answer against the regulation's worked examples is part of checking the
	rates, so refusing it would make the gate harder to open honestly. With
	`rate_set`, lookups read that set instead of the one in force (previewing a
	draft). Scoped to the current request and restored on exit; payroll never
	enters it."""
	previous = getattr(frappe.local, "_eil_pph21_preview", None)
	frappe.local._eil_pph21_preview = {"set": rate_set}
	try:
		yield
	finally:
		frappe.local._eil_pph21_preview = previous


def _preview():
	return getattr(frappe.local, "_eil_pph21_preview", None)


def require_verified_tables(on_date=None):
	if _preview():
		return
	from erpbio_indonesia_localization.pph21 import rate_sets

	current = rate_sets.in_force(on_date)
	day = getdate(on_date or nowdate())
	if not current:
		frappe.throw(
			_("No PPh 21 rate set is in force on {0}. Create or load one under ERPbio Tax > PPh 21 > Rate Sets.").format(day),
			title=_("PPh 21 rates missing"),
		)
	if current.status != "Verified":
		frappe.throw(
			_(
				"The PPh 21 rates in force on {0} ({1}, effective {2}) are loaded but not verified. "
				"Verify that rate set under ERPbio Tax > PPh 21 > Rate Sets (EIL PPh 21 Rate Set in Desk) "
				"before running payroll."
			).format(day, current.regulation, current.effective_from),
			title=_("PPh 21 tables unverified"),
		)


def validate_tables(on_date=None, rate_set=None):
	"""Structural problems in a set's tables (default: the set in force), as a
	list of strings.

	A bracket table that overlaps, leaves a gap, or whose rates fall is wrong
	whatever its source — these caught a bad published rate and two bugs in the
	extractor that produced the shipped fixture.
	"""
	ter = {c: _rows("EIL TER Bracket", on_date, filters={"category": c}, rate_set=rate_set) for c in TER_CATEGORIES}
	return _problems(ter, _rows("EIL PPh 21 Bracket", on_date, rate_set=rate_set),
	                 _rows("EIL PTKP Rate", on_date, rate_set=rate_set))


def validate_rows(rows):
	"""The same checks on rows that are not saved yet -- an editor's grid:
	{"ter": [{category, from_amount, to_amount, rate}], "ptkp": [...], "pasal17": [...]}."""
	def bands(items):
		return sorted((frappe._dict(r) for r in items or []), key=lambda r: flt(r.from_amount))

	ter = {c: bands([r for r in rows.get("ter") or [] if r.get("category") == c]) for c in TER_CATEGORIES}
	return _problems(ter, bands(rows.get("pasal17")), [frappe._dict(r) for r in rows.get("ptkp") or []])


def _problems(ter, pasal17, ptkp):
	problems = []
	for category in TER_CATEGORIES:
		# TER Harian stops at Rp 2,500,000 by design — above that the daily rate no
		# longer applies at all (gross x 50% x Pasal 17), so it must NOT be open-ended.
		problems += _band_problems(ter[category], f"TER {category}", open_ended=category != "Harian")
	problems += _band_problems(pasal17, "Pasal 17")

	statuses = {r.ptkp_status for r in ptkp}
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
	require_verified_tables(on_date)
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
	require_verified_tables(on_date)
	rows = [r for r in _rows("EIL PTKP Rate", on_date) if r.ptkp_status == status]
	if not rows:
		frappe.throw(_("No PTKP rate is loaded for status {0}.").format(status or "?"))
	return rows[0]


def _rows(doctype, on_date=None, filters=None, rate_set=None):
	"""One set's rows, ordered by band: `rate_set`, else the set a preview pinned,
	else the set in force on `on_date`. Cached per request: fast within a payroll
	run, never stale across one."""
	if not rate_set:
		pinned = _preview()
		rate_set = pinned.get("set") if pinned else None
	if not rate_set:
		from erpbio_indonesia_localization.pph21 import rate_sets

		current = rate_sets.in_force(on_date)
		rate_set = current.name if current else None
	if not rate_set:
		return []
	key = (doctype, rate_set, tuple(sorted((filters or {}).items())))
	cache = getattr(frappe.local, "_eil_pph21_tables", None)
	if cache is None:
		cache = frappe.local._eil_pph21_tables = {}
	if key in cache:
		return cache[key]

	rows = [frappe._dict(r) for r in frappe.get_all(doctype, filters={**(filters or {}), "rate_set": rate_set}, fields=["*"])]
	rows.sort(key=lambda r: flt(r.from_amount))
	cache[key] = rows
	return rows
