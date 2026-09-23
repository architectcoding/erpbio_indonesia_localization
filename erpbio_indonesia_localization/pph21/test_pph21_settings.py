# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""EIL PPh 21 Settings' own rules, and the PPh 21 page's endpoints.

The rules live on the document, so they hold on every save path -- the tax app's
page, the consolidated Settings editor, Desk.

    bench --site develop.localhost run-tests \
        --module erpbio_indonesia_localization.pph21.test_pph21_settings
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from erpbio_indonesia_localization.api import tax
from erpbio_indonesia_localization.pph21 import tables

DOCTYPE = "EIL PPh 21 Settings"


class TestPPh21Settings(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Singles live in tabSingles; put the site's exact rows back afterwards
		# rather than trusting the class rollback with them.
		cls._saved = frappe.db.sql("select field, value from tabSingles where doctype=%s", DOCTYPE, as_dict=True)
		cls.component = _component("_Test EIL PPh 21")
		cls.variable_component = _component("_Test EIL PPh 21 Variable", variable=1)

	@classmethod
	def tearDownClass(cls):
		frappe.db.delete("Singles", {"doctype": DOCTYPE})
		for row in cls._saved:
			frappe.db.sql(
				"insert into tabSingles (doctype, field, value) values (%s, %s, %s)", (DOCTYPE, row.field, row.value)
			)
		frappe.clear_cache(doctype=DOCTYPE)
		super().tearDownClass()

	def setUp(self):
		_set(enabled=0, tables_verified=0, pph21_component=self.component)

	def test_tables_failing_their_checks_cannot_be_verified_on_any_path(self):
		doc = frappe.get_single(DOCTYPE)
		doc.tables_verified = 1
		with patch.object(tables, "validate_tables", return_value=["TER A: gap at 5,400,001"]):
			with self.assertRaises(frappe.ValidationError):
				doc.save()

	def test_enabling_needs_verified_tables(self):
		with self.assertRaises(frappe.ValidationError):
			tax.save_pph21_settings(frappe.as_json({"enabled": 1}))

	def test_enabling_needs_a_component(self):
		_set(tables_verified=1, pph21_component=None)
		with self.assertRaises(frappe.ValidationError):
			tax.save_pph21_settings(frappe.as_json({"enabled": 1}))

	def test_enabling_once_ready(self):
		_set(tables_verified=1)
		out = tax.save_pph21_settings(frappe.as_json({"enabled": 1}))
		self.assertEqual(out["settings"]["enabled"], 1)
		self.assertEqual(out["enabled_change"]["value"], 1)

	def test_a_variable_based_component_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			tax.save_pph21_settings(frappe.as_json({"pph21_component": self.variable_component}))

	def test_an_existing_bad_component_does_not_block_other_saves(self):
		# The rates loader saves this record on every migrate; a site that already
		# holds a bad component must still migrate.
		_set(pph21_component=self.variable_component)
		doc = frappe.get_single(DOCTYPE)
		doc.tables_source = "re-recorded by the loader"
		doc.save()

	def test_verification_records_who_and_when(self):
		out = tax.set_pph21_tables_verified(1)
		self.assertEqual(out["verified_change"]["value"], 1)
		self.assertEqual(out["verified_change"]["by"], frappe.utils.get_fullname("Administrator"))

	def test_preview_runs_before_verification_and_matches_djp(self):
		# DJP's worked example: K/1 (TER B) on Rp 15,000,000 a month -> 6% -> 900,000.
		out = tax.preview_pph21("K/1", 15_000_000)
		self.assertEqual((out["category"], out["rate"], out["withholding"], out["verified"]), ("B", 6.0, 900_000.0, 0))
		# ...and the gate still holds outside the preview.
		with self.assertRaises(frappe.ValidationError):
			tables.ter_rate("B", 15_000_000)


def _set(**values):
	for field, value in values.items():
		frappe.db.set_single_value(DOCTYPE, field, value)
	frappe.clear_cache(doctype=DOCTYPE)
	frappe.local._eil_pph21_tables = {}


def _component(name, variable=0):
	if not frappe.db.exists("Salary Component", name):
		frappe.get_doc({
			"doctype": "Salary Component",
			"salary_component": name,
			"salary_component_abbr": ("TV" if variable else "TP") + frappe.generate_hash(length=4),
			"type": "Deduction",
			"variable_based_on_taxable_salary": variable,
		}).insert(ignore_permissions=True)
	return name
