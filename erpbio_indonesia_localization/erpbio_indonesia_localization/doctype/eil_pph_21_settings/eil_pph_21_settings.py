# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class EILPPh21Settings(Document):
	"""The rules live here rather than in one endpoint, so they hold however the
	record is saved: the tax app's PPh 21 page, the consolidated Settings editor,
	Desk or an import."""

	def validate(self):
		# Each rule fires when its field CHANGES, not on every save: the rates
		# loader saves this record on every migrate, and a site that already holds
		# a bad value must still migrate -- it just cannot save a new bad one.
		if self._changed("pph21_component"):
			self._check_component()
		# tables_verified is a read-only mirror now: a rate set is verified on the
		# set itself (pph21/rate_sets.py), with its structural checks and PDF.
		if self._turned_on("enabled"):
			self._check_ready_to_enable()

	def _turned_on(self, field):
		before = self.get_doc_before_save()
		return bool(self.get(field)) and not (before and before.get(field))

	def _changed(self, field):
		before = self.get_doc_before_save()
		return (before.get(field) if before else None) != self.get(field)

	def _check_component(self):
		if not self.pph21_component:
			return
		if frappe.db.get_value("Salary Component", self.pph21_component, "variable_based_on_taxable_salary"):
			frappe.throw(
				_(
					"{0} is flagged “Variable Based On Taxable Salary”, which hands the calculation to "
					"HRMS's annual slab engine — that cannot express TER. Choose a component without it."
				).format(self.pph21_component)
			)

	def _check_ready_to_enable(self):
		if not self.pph21_component:
			frappe.throw(_("Choose the PPh 21 salary component before enabling PPh 21."))
		from erpbio_indonesia_localization.pph21 import rate_sets

		if not rate_sets.in_force_verified():
			frappe.throw(
				_(
					"Verify the rate tables before enabling PPh 21 — until then every salary slip "
					"carrying the component would refuse to compute."
				)
			)
