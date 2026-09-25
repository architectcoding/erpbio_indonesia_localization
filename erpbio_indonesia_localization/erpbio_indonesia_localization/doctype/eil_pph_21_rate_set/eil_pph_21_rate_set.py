# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class EILPPh21RateSet(Document):
	"""One regulation's PPh 21 rates. The status moves only through
	pph21.rate_sets.verify / unlock, which set flags.status_change -- a plain save
	(Desk, the settings editor, an import) cannot mark rates verified."""

	def validate(self):
		before = self.get_doc_before_save()
		was = before.status if before else "Draft"
		if (self.status or "Draft") != was and not self.flags.status_change:
			frappe.throw(_("A rate set is verified or unlocked with its Verify and Unlock actions, not by editing the status."))
		if before and was == "Verified" and before.regulation != self.regulation:
			frappe.throw(_("Rate set {0} is verified; unlock it before changing its regulation.").format(self.name))

	def on_trash(self):
		# Runs before Frappe's link check, so the set's own rows can go with it.
		from erpbio_indonesia_localization.pph21 import rate_sets

		if self.status == "Verified":
			frappe.throw(_("Rate set {0} is verified. Unlock it before deleting it.").format(self.name))
		for doctype in rate_sets.ROW_DOCTYPES:
			frappe.db.delete(doctype, {"rate_set": self.name})
		frappe.local._eil_pph21_tables = {}
