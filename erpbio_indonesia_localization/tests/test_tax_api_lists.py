# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""The list/detail contract api/tax.py gives the /erpbio-tax SPA.

Three things the shared ListView and a restricted user rely on, each of which
was broken until 2026-09-23:

- the response names its sortable columns, or every header is inert;
- has_next comes from one extra row, not from the capped total, or paging
  stops at 1,001 rows;
- rows and single documents honour user permissions, not just doctype rights.

    bench --site develop.localhost run-tests \
        --module erpbio_indonesia_localization.tests.test_tax_api_lists
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from erpbio_indonesia_localization.api import tax

USER = "tax-list-audit@example.com"


class TestTaxListContract(FrappeTestCase):
	def test_lists_report_their_sortable_columns(self):
		for fn in (tax.list_exports, tax.list_imports, tax.list_customers):
			with self.subTest(fn=fn.__name__):
				self.assertIn("name", fn(page_length=5)["sortable"])

	def test_has_next_does_not_stop_at_the_capped_total(self):
		if frappe.db.count("Customer") < 6:
			self.skipTest("needs at least 6 customers")
		# The total reads as if the count had capped below the rows still to come.
		with patch.object(tax, "capped_total", return_value=3):
			page = tax.list_customers(start=0, page_length=5)
		self.assertEqual(len(page["items"]), 5)
		self.assertTrue(page["has_next"])

	def test_last_page_has_no_next(self):
		count = frappe.db.count("Customer")
		page = tax.list_customers(start=max(count - 2, 0), page_length=5)
		self.assertFalse(page["has_next"])


class TestTaxPermissions(FrappeTestCase):
	"""A user restricted to one customer sees that customer and no other."""

	@classmethod
	def setUpClass(cls):
		# FrappeTestCase rolls back once per class, so the fixture is built once.
		super().setUpClass()
		customers = frappe.get_all("Customer", pluck="name", limit=2, order_by="name")
		if len(customers) < 2:
			raise cls.failureException("needs two customers")
		cls.allowed, cls.other = customers
		if not frappe.db.exists("User", USER):
			user = frappe.get_doc(
				{"doctype": "User", "email": USER, "first_name": "Tax List Audit", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
			user.add_roles("Accounts Manager")
		frappe.get_doc(
			{"doctype": "User Permission", "user": USER, "allow": "Customer", "for_value": cls.allowed}
		).insert(ignore_permissions=True)

	def setUp(self):
		frappe.set_user(USER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_list_rows_follow_user_permissions(self):
		names = [r["name"] for r in tax.list_customers(page_length=500)["items"]]
		self.assertEqual(names, [self.allowed])

	def test_summary_counts_what_the_list_can_show(self):
		self.assertEqual(tax.customer_tax_summary()["total"], 1)

	def test_a_customer_outside_the_permission_is_refused(self):
		self.assertEqual(tax.get_customer_tax(self.allowed)["doc"]["name"], self.allowed)
		with self.assertRaises(frappe.PermissionError):
			tax.get_customer_tax(self.other)
