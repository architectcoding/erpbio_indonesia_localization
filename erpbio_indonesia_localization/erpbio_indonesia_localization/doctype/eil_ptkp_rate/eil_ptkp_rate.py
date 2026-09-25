# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from erpbio_indonesia_localization.pph21 import rate_sets


class EILPTKPRate(Document):
	# A row belongs to a rate set, takes its date, and is frozen once the set is
	# verified -- whichever path saves it (see pph21/rate_sets.py).
	def validate(self):
		rate_sets.guard_row(self)

	def on_update(self):
		rate_sets.stamp_edit(self)

	def on_trash(self):
		rate_sets.guard_row(self, deleting=True)

	def after_delete(self):
		rate_sets.stamp_edit(self)
