# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""Customer and supplier tax identity as the /erpbio-tax pages edit it.

    bench --site develop.localhost run-tests \
        --module erpbio_indonesia_localization.tests.test_tax_identity_pages
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from erpbio_indonesia_localization.api import tax


class TestCustomerTaxIdentity(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.customer = frappe.get_all("Customer", pluck="name", limit=1, order_by="name")[0]

	def _save(self, **values):
		return tax.save_customer_tax(frappe.as_json({"name": self.customer, **values}))

	def test_a_changed_npwp_must_have_15_or_16_digits(self):
		with self.assertRaises(frappe.ValidationError):
			self._save(eil_id_type="TIN", tax_id="12.345.678")

	def test_a_nik_must_have_16_digits(self):
		with self.assertRaises(frappe.ValidationError):
			self._save(eil_id_type="NIK", tax_id="3171 2345 6789 012")

	def test_an_old_malformed_number_does_not_block_an_address_fix(self):
		frappe.db.set_value("Customer", self.customer, {"eil_id_type": "TIN", "tax_id": "PT SAM MEDIKA"})
		out = self._save(eil_tax_address="Jl. Pajajaran 1, Bogor")
		self.assertEqual(out["doc"]["eil_tax_address"], "Jl. Pajajaran 1, Bogor")

	def test_a_malformed_number_reads_incomplete_not_ready(self):
		frappe.db.set_value("Customer", self.customer, {"eil_id_type": "TIN", "tax_id": "PT SAM MEDIKA 123"})
		out = tax.get_customer_tax(self.customer)
		self.assertEqual(out["tax_status"], "Incomplete")

	def test_the_preview_sends_the_registered_name_and_address(self):
		self._save(eil_id_type="TIN", tax_id="01.234.567.8-901.000", eil_tax_name="PT REGISTERED NAME",
			eil_tax_address="Jl. Satu\nNo. 2")
		preview = tax.get_customer_tax(self.customer)["faktur_preview"]
		self.assertEqual(preview["name"], "PT REGISTERED NAME")
		self.assertEqual(preview["address"], "Jl. Satu No. 2")


class TestSupplierTaxIdentity(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.supplier = frappe.get_all("Supplier", pluck="name", limit=1, order_by="name")[0]
		# a domestic supplier: the NPWP rules below do not apply to a foreign one
		frappe.db.set_value("Supplier", cls.supplier, "country", "Indonesia")

	def test_list_reports_status_and_sortable_columns(self):
		page = tax.list_suppliers(page_length=5)
		self.assertIn("supplier_name", page["sortable"])
		self.assertTrue(all(r["tax_status"] in ("Ready", "Incomplete", "Blocked", "Foreign") for r in page["items"]))

	def test_save_writes_the_identity_and_refuses_a_short_npwp(self):
		out = tax.save_supplier_tax(frappe.as_json({"name": self.supplier, "tax_id": "0123456789012340",
			"eil_tax_name": "PT SUPPLIER TERDAFTAR"}))
		self.assertEqual(out["tax_status"], "Ready")
		self.assertEqual(out["doc"]["eil_tax_name"], "PT SUPPLIER TERDAFTAR")
		with self.assertRaises(frappe.ValidationError):
			tax.save_supplier_tax(frappe.as_json({"name": self.supplier, "tax_id": "12345"}))

	def test_missing_npwp_filter(self):
		missing = tax.supplier_tax_summary(filters=frappe.as_json([{"field": "missing_tax_id", "value": "1"}]))
		self.assertEqual(missing["total"], missing["Blocked"])


class TestForeignSupplier(FrappeTestCase):
	"""A supplier outside Indonesia has no NPWP to collect -- it must not read as
	Blocked or swell the "without NPWP" count, whatever group it is filed under."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.supplier = frappe.get_all("Supplier", pluck="name", limit=1, order_by="name")[0]
		frappe.db.set_value("Supplier", cls.supplier, {"country": "Germany", "tax_id": None})

	def test_reads_foreign_not_blocked(self):
		out = tax.get_supplier_tax(self.supplier)
		self.assertEqual(out["tax_status"], "Foreign")

	def test_not_counted_or_listed_as_missing(self):
		missing = frappe.as_json([{"field": "missing_tax_id", "value": "1"}])
		names = [r["name"] for r in tax.list_suppliers(filters=missing, page_length=500)["items"]]
		self.assertNotIn(self.supplier, names)
		self.assertGreaterEqual(tax.supplier_tax_summary()["Foreign"], 1)

	def test_its_own_tin_is_not_held_to_npwp_length(self):
		out = tax.save_supplier_tax(frappe.as_json({"name": self.supplier, "tax_id": "DE 123456789"}))
		self.assertEqual(out["tax_status"], "Foreign")

	def test_a_blank_country_stays_domestic(self):
		frappe.db.set_value("Supplier", self.supplier, "country", None)
		self.assertEqual(tax.get_supplier_tax(self.supplier)["tax_status"], "Blocked")
		frappe.db.set_value("Supplier", self.supplier, "country", "Germany")
