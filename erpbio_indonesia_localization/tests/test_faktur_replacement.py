# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""After Coretax approves a faktur, cancelling or correcting its invoice is
followed through (T-004).

Before: the faktur fields are no_copy, so an amended invoice started blank and
exported as a second Normal faktur for the same sale; a cancelled invoice kept
its Approved faktur and nothing told the tax user to cancel it in Coretax; and
the import only matched submitted invoices, so a CANCELED row could not close
it.

The rules under test:
- amending an invoice whose faktur was approved flags the amendment as Faktur
  Pengganti carrying the replaced number, and the export says so;
- a Pengganti with no replaced number is held;
- an approved faktur on a cancelled invoice is listed "to cancel in Coretax"
  until an import brings its CANCELED status, or a live invoice replaces it.

    bench --site develop.localhost run-tests \
        --module erpbio_indonesia_localization.tests.test_faktur_replacement
"""

import frappe

from erpbio_indonesia_localization.api import tax
from erpbio_indonesia_localization.tests.test_coretax_faktur_export import _ExportCase

NUMBER = "04002600000777"


class TestFakturReplacement(_ExportCase):
	def _approved(self):
		si = self._invoice([(self.service, 1, 1_000_000, "Unit")], template=self.template_ppn)
		frappe.db.set_value("Sales Invoice", si.name, {"eil_faktur_status": "Approved", "eil_faktur_number": NUMBER})
		return frappe.get_doc("Sales Invoice", si.name)

	def _amend(self, si):
		si.cancel()
		amended = frappe.copy_doc(si, ignore_no_copy=False)  # as Amend does: no_copy fields dropped
		amended.docstatus = 0  # copy_doc keeps docstatus inside a test run
		if amended.meta.has_field("workflow_state"):
			amended.workflow_state = None  # an amendment starts at the workflow's draft state
		amended.amended_from = si.name
		amended.set_posting_time, amended.posting_date = 1, si.posting_date  # same sale, same period
		amended.flags.ignore_permissions = True
		amended.insert(ignore_permissions=True)
		return amended

	def _listed(self):
		return {r.name: r for r in tax.fakturs_to_cancel(self.company)}

	def test_an_amendment_of_an_approved_faktur_is_its_pengganti(self):
		original = self._approved()
		amended = self._amend(original)
		self.assertEqual((amended.eil_pengganti, amended.eil_replaces_faktur_number), (1, NUMBER),
			"the amendment starts blank and would export as a second Normal faktur (T-004)")
		amended.submit()
		_, row = self._row_for(amended.name)
		self.assertTrue(row.ok, row.message)
		self.assertIn(NUMBER, row.message)

	def test_a_pengganti_without_the_number_it_replaces_is_held(self):
		si = self._invoice([(self.service, 1, 1_000_000, "Unit")], template=self.template_ppn, eil_pengganti=1)
		_, row = self._row_for(si.name)
		self.assertFalse(row.ok)
		self.assertIn("replaces", row.message)

	def test_a_cancelled_invoice_s_approved_faktur_is_listed_until_cancelled_in_coretax(self):
		si = self._approved()
		si.cancel()
		self.assertIn(si.name, self._listed(), "nothing tells the tax user to cancel the faktur in Coretax (T-004)")
		ok, doctype, name, _msg = frappe.new_doc("Coretax Faktur Import")._match(si.name, NUMBER, "Cancelled", "CANCELED")
		self.assertTrue(ok, "an import's CANCELED row cannot reach the cancelled invoice")
		self.assertEqual((doctype, name), ("Sales Invoice", si.name))
		frappe.db.set_value("Sales Invoice", si.name, "eil_faktur_status", "Cancelled")  # what apply() writes
		self.assertNotIn(si.name, self._listed())

	def test_a_replaced_faktur_leaves_the_list(self):
		original = self._approved()
		amended = self._amend(original)
		self.assertNotIn(original.name, self._listed(), "a faktur its Pengganti replaces is not one to cancel")
		self.assertTrue(amended.name)
