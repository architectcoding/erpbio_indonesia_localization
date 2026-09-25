# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""Load the shipped statutory rate fixture into the rate doctypes.

The fixture in data/pph21_rates.json was machine-extracted from DJP's own
PMK 168/2023 PDF (see the plan and the extractor in scratchpad) — no figure in it
was typed by hand. This loader is idempotent and additive: it never deletes or
overwrites a row an administrator has corrected, it only inserts what is missing
for the fixture's effective_from. That way a correction survives every migrate.

It loads into the fixture's own rate set (EIL PPh 21 Rate Set). A date the site
has no set for becomes a new DRAFT set -- a human has to look at the numbers and
verify it; a set already verified is never touched, so a shipped update cannot go
live on an old verification.
"""

import json
import os

import frappe

DATA = os.path.join(os.path.dirname(__file__), "data", "pph21_rates.json")


def load_rates():
	from erpbio_indonesia_localization.pph21 import rate_sets

	fixture = json.loads(open(DATA).read())
	effective_from = fixture["effective_from"]
	rate_set = rate_sets.ensure_fixture_set(effective_from, fixture.get("regulation") or "PMK 168/2023", fixture["source"])
	if not rate_set:
		return {}  # the fixture's set is verified: leave it exactly as it was checked
	frappe.flags.eil_loading_rate_set = rate_set
	try:
		counts = {
			"EIL TER Bracket": _load_ter(fixture, effective_from),
			"EIL PTKP Rate": _load_ptkp(fixture, effective_from),
			"EIL PPh 21 Bracket": _load_pasal17(fixture, effective_from),
		}
	finally:
		frappe.flags.eil_loading_rate_set = None
	_record_source(fixture)
	return counts


def _load_ter(fixture, effective_from):
	inserted = 0
	bands = dict(fixture["ter_bulanan"])
	bands["Harian"] = fixture["ter_harian"]
	for category, rows in bands.items():
		for from_amount, to_amount, rate in rows:
			inserted += _ensure(
				"EIL TER Bracket",
				{"category": category, "from_amount": from_amount, "effective_from": effective_from},
				{"to_amount": to_amount, "rate": rate},
			)
	return inserted


def _load_ptkp(fixture, effective_from):
	inserted = 0
	for status, row in fixture["ptkp"].items():
		inserted += _ensure(
			"EIL PTKP Rate",
			{"ptkp_status": status, "effective_from": effective_from},
			{"annual_amount": row["annual_amount"], "ter_category": row["ter_category"]},
		)
	return inserted


def _load_pasal17(fixture, effective_from):
	inserted = 0
	for from_amount, to_amount, rate in fixture["pasal_17"]:
		inserted += _ensure(
			"EIL PPh 21 Bracket",
			{"from_amount": from_amount, "effective_from": effective_from},
			{"to_amount": to_amount, "rate": rate},
		)
	return inserted


def _ensure(doctype, identity, values):
	"""Insert the row when its identity is absent; leave an existing one alone."""
	if frappe.db.exists(doctype, identity):
		return 0
	frappe.get_doc(
		{"doctype": doctype, "rate_set": frappe.flags.eil_loading_rate_set, **identity, **values}
	).insert(ignore_permissions=True)
	return 1


def _record_source(fixture):
	settings = frappe.get_single("EIL PPh 21 Settings")
	source = f"{fixture['source']} — effective {fixture['effective_from']}"
	if settings.tables_source != source:
		settings.tables_source = source
		settings.save(ignore_permissions=True)
