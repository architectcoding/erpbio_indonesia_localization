# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""Keep the employee's derived PPh 21 fields honest.

Only the PTKP status is entered; the TER category follows from it exactly as
PMK 168 maps it, so it is derived here rather than asked for twice.
"""

import frappe

from erpbio_indonesia_localization.pph21 import tables


def validate(doc, method=None):
	if not doc.meta.has_field("eil_ptkp_status"):
		return  # fields not installed yet
	status = doc.get("eil_ptkp_status")
	if not status:
		doc.eil_ter_category = None
		return
	try:
		doc.eil_ter_category = tables.ter_category(status)
	except Exception:
		# The mapping lives in a rate table that may be unverified or not yet
		# loaded. Never block saving an employee over it — the calculation itself
		# refuses loudly when the tables aren't ready.
		doc.eil_ter_category = None
