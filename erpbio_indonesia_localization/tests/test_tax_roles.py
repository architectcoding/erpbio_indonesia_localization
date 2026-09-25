# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""Who can work the tax books (T-012).

The tax app used to open for Accounts Manager only: `get_context` checked
Coretax Faktur Export, which only Accounts Manager could read, so the finance
staff who hold Accounts User -- and who could already file a Bukti Potong --
met "Not permitted" at the door. Now:

- Accounts User opens the app, runs the registers and the SPT, prepares
  exports and imports;
- Tax User -- a role of this app -- does the same without any accounting or
  sales role, reads the invoices and parties the books are drawn from, and
  keeps a party's tax identity through the tax app's own endpoints;
- neither changes Indonesia Tax Settings: that stays Accounts Manager.

Throwaway users, never a shared persona; their role caches are cleared after.

    bench --site develop.localhost run-tests \
        --module erpbio_indonesia_localization.tests.test_tax_roles
"""

import frappe

try:  # Frappe v16
	from frappe.tests import IntegrationTestCase as _TestCase
except ImportError:  # older Frappe
	from frappe.tests.utils import FrappeTestCase as _TestCase

from erpbio_indonesia_localization.api import tax
from erpbio_indonesia_localization.setup import install

DOMAIN = "t012.test"


class TestTaxRoles(_TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install.seed_tax_user_role()
		from erpnext import get_default_company

		cls.company = get_default_company() or frappe.get_all("Company", pluck="name", order_by="name")[0]
		cls.tax_user = cls._user("tax", ["Tax User"])
		cls.accounts_user = cls._user("acct", ["Accounts User"])
		cls.customer = frappe.db.get_value("Customer", {"disabled": 0}, "name", order_by="name asc")

	@classmethod
	def _user(cls, tag, roles):
		email = f"{tag}-{frappe.generate_hash(length=6)}@{DOMAIN}"
		frappe.get_doc({
			"doctype": "User", "email": email, "first_name": tag, "send_welcome_email": 0,
			"user_type": "System User", "roles": [{"role": r} for r in roles],
		}).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for user in (getattr(cls, "tax_user", None), getattr(cls, "accounts_user", None)):
			if user:
				frappe.clear_cache(user=user)
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _as(self, user):
		frappe.set_user(user)
		self.assertEqual(frappe.session.user, user)

	def _period(self):
		return self.company, "2026-03-01", "2026-03-31"

	# --- the role -------------------------------------------------------------

	def test_the_tax_user_role_exists_and_reads_the_source_documents(self):
		self.assertTrue(frappe.db.exists("Role", "Tax User"))
		for doctype in install.TAX_USER_READS:
			self.assertTrue(
				frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": "Tax User", "read": 1}),
				f"Tax User cannot read {doctype}",
			)

	def test_seeding_twice_does_not_add_a_second_row(self):
		install.seed_tax_user_role()
		self.assertEqual(frappe.db.count("Custom DocPerm", {"parent": "Sales Invoice", "role": "Tax User"}), 1)

	# --- Tax User -------------------------------------------------------------

	def test_a_tax_user_opens_the_app_and_runs_the_books(self):
		self._as(self.tax_user)
		self.assertIn("companies", tax.get_context(), "the tax app refused a Tax User at the door (T-012)")
		tax.ppn_keluaran(*self._period())
		tax.ppn_masukan(*self._period())
		self.assertIn("keluaran", tax.spt_masa(*self._period()))
		export = tax.create_export(*self._period())["name"]
		self.assertTrue(export)

	def test_a_tax_user_keeps_a_customer_s_tax_identity(self):
		if not self.customer:
			self.skipTest("no customer on the site")
		self._as(self.tax_user)
		detail = tax.get_customer_tax(self.customer)
		self.assertTrue(detail["can_write"], "the page would show a Tax User the form read-only")
		saved = tax.save_customer_tax({"name": self.customer, "eil_tax_name": "PT UJI PAJAK"})
		self.assertEqual(frappe.db.get_value("Customer", self.customer, "eil_tax_name"), "PT UJI PAJAK")
		self.assertTrue(saved)

	def test_a_tax_user_cannot_change_the_tax_settings(self):
		self._as(self.tax_user)
		tax.get_settings()  # reading them is fine
		with self.assertRaises(frappe.PermissionError):
			tax.save_settings({"tarif_ppn": 11})

	# --- Accounts User --------------------------------------------------------

	def test_an_accounts_user_opens_the_app_and_prepares_an_export(self):
		self._as(self.accounts_user)
		self.assertIn("companies", tax.get_context(), "the tax app refused an Accounts User at the door (T-012)")
		self.assertTrue(tax.create_export(*self._period())["name"])
		self.assertIn("keluaran", tax.spt_masa(*self._period()))

	def test_an_accounts_user_cannot_change_the_tax_settings(self):
		self._as(self.accounts_user)
		with self.assertRaises(frappe.PermissionError):
			tax.save_settings({"tarif_ppn": 11})
