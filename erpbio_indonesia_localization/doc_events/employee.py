# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""Keep the employee's derived PPh 21 fields honest.

Only the PTKP status is entered; the TER category follows from it exactly as
PMK 168 maps it, so it is derived here rather than asked for twice.
"""

from erpbio_indonesia_localization.pph21 import tables


def validate(doc, method=None):
	if not doc.meta.has_field("eil_ptkp_status"):
		return  # fields not installed yet
	# Never blocks saving an employee: the rate tables may be unloaded or
	# unverified, and refusing to compute belongs in the calculation, not here.
	doc.eil_ter_category = tables.ter_category_or_none(doc.get("eil_ptkp_status"))
