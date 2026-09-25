# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""PPh 21 rate sets: payroll computes only on a verified set, a verified set is
frozen, and unlocking stops once payroll used it.

    bench --site develop.localhost run-tests \
        --module erpbio_indonesia_localization.pph21.test_rate_sets
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_years, nowdate

from erpbio_indonesia_localization.api import tax
from erpbio_indonesia_localization.pph21 import rate_sets, rates_loader, tables

DOCTYPE = rate_sets.DOCTYPE
SETTINGS = rate_sets.SETTINGS


class TestRateSets(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._singles = frappe.db.sql("select field, value from tabSingles where doctype=%s", SETTINGS, as_dict=True)
		cls.base = rate_sets.in_force().name
		cls._base_status = frappe.db.get_value(DOCTYPE, cls.base, "status")

	@classmethod
	def tearDownClass(cls):
		frappe.db.delete("Singles", {"doctype": SETTINGS})
		for row in cls._singles:
			frappe.db.sql("insert into tabSingles (doctype, field, value) values (%s, %s, %s)", (SETTINGS, row.field, row.value))
		frappe.db.set_value(DOCTYPE, cls.base, "status", cls._base_status, update_modified=False)
		frappe.clear_cache(doctype=SETTINGS)
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.set_value(DOCTYPE, self.base, "status", "Verified", update_modified=False)
		frappe.db.set_single_value(SETTINGS, "require_four_eyes", 0)
		frappe.local._eil_pph21_tables = {}

	def tearDown(self):
		for name in frappe.get_all(DOCTYPE, filters={"name": ("!=", self.base)}, pluck="name"):
			frappe.db.set_value(DOCTYPE, name, "status", "Draft", update_modified=False)
			frappe.delete_doc(DOCTYPE, name, force=True, ignore_permissions=True)
		frappe.local._eil_pph21_tables = {}

	# ------------------------------------------------------------ lookups + D1
	def test_payroll_uses_the_verified_set_in_force(self):
		self.assertEqual(tables.ter_rate("B", 15_000_000), 6.0)

	def test_a_newer_draft_in_force_stops_payroll(self):
		# D1: an unverified set that has reached its date blocks -- the older
		# verified set is NOT used in its place.
		rate_sets.create(add_days(nowdate(), -1), "PMK test/2026")
		frappe.local._eil_pph21_tables = {}
		with self.assertRaisesRegex(frappe.ValidationError, "loaded but not verified"):
			tables.ter_rate("B", 15_000_000)

	def test_a_future_draft_does_not_touch_today(self):
		rate_sets.create(add_years(nowdate(), 1), "PMK next/2027")
		frappe.local._eil_pph21_tables = {}
		self.assertEqual(tables.ter_rate("B", 15_000_000), 6.0)

	def test_a_new_set_starts_as_a_copy_of_the_one_in_force(self):
		new = rate_sets.create(add_years(nowdate(), 1), "PMK next/2027")
		rows = rate_sets.rows_of(new.name)
		self.assertEqual((len(rows["ter"]), len(rows["ptkp"]), len(rows["pasal17"])), (127, 8, 5))
		self.assertEqual(frappe.db.get_value(DOCTYPE, new.name, ["status", "last_edited_by"]), ("Draft", "Administrator"))

	def test_preview_reads_a_draft_set(self):
		new = rate_sets.create(add_years(nowdate(), 1), "PMK next/2027")
		rows = rate_sets.rows_of(new.name)
		for r in rows["ter"]:
			if r.category == "B" and r.rate == 6.0:
				r.rate = 7.0
		rate_sets.replace_rows(new.name, rows)
		out = tax.preview_pph21("K/1", 15_000_000, rate_set=new.name)
		self.assertEqual((out["rate"], out["verified"]), (7.0, 0))
		# ...while payroll today still reads the verified set.
		self.assertEqual(tables.ter_rate("B", 15_000_000), 6.0)

	# ------------------------------------------------------------ frozen
	def test_a_verified_sets_rows_are_frozen_on_every_path(self):
		row = frappe.get_doc("EIL TER Bracket", frappe.get_all("EIL TER Bracket", filters={"rate_set": self.base}, pluck="name", limit=1)[0])
		row.rate = 99
		with self.assertRaisesRegex(frappe.ValidationError, "frozen"):
			row.save(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("EIL TER Bracket", row.name, ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			rate_sets.replace_rows(self.base, rate_sets.rows_of(self.base))

	def test_status_moves_only_through_verify_and_unlock(self):
		new = rate_sets.create(add_years(nowdate(), 1), "PMK next/2027")
		doc = frappe.get_doc(DOCTYPE, new.name)
		doc.status = "Verified"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	# ------------------------------------------------------------ verify
	def test_verify_needs_clean_checks(self):
		new = _with_pdf(rate_sets.create(add_years(nowdate(), 1), "PMK next/2027"))
		with patch.object(tables, "validate_tables", return_value=["TER A: gap"]):
			with self.assertRaisesRegex(frappe.ValidationError, "structural checks"):
				rate_sets.verify(new)

	def test_verify_needs_the_regulation_pdf(self):
		new = rate_sets.create(add_years(nowdate(), 1), "PMK next/2027")
		with self.assertRaisesRegex(frappe.ValidationError, "PDF"):
			rate_sets.verify(new.name)

	def test_four_eyes_stops_the_last_editor(self):
		new = _with_pdf(rate_sets.create(add_years(nowdate(), 1), "PMK next/2027"))
		frappe.db.set_single_value(SETTINGS, "require_four_eyes", 1)
		with self.assertRaisesRegex(frappe.ValidationError, "Four-eyes"):
			rate_sets.verify(new)
		frappe.db.set_single_value(SETTINGS, "require_four_eyes", 0)
		self.assertEqual(rate_sets.verify(new).status, "Verified")

	def test_verify_records_who_and_when(self):
		new = _with_pdf(rate_sets.create(add_years(nowdate(), 1), "PMK next/2027"))
		doc = rate_sets.verify(new)
		self.assertEqual((doc.status, doc.verified_by), ("Verified", "Administrator"))
		self.assertTrue(doc.verified_on)

	# ------------------------------------------------------------ unlock
	def test_unlock_needs_a_reason(self):
		with self.assertRaises(frappe.ValidationError):
			rate_sets.unlock(self.base, "  ")

	def test_unlock_is_refused_once_payroll_used_the_set(self):
		with patch.object(rate_sets, "usage", return_value={"salary_slips": 3, "certificates": 0}):
			with self.assertRaisesRegex(frappe.ValidationError, "already computed"):
				rate_sets.unlock(self.base, "typo in TER B")

	def test_unlock_returns_the_set_to_draft_with_its_reason(self):
		with patch.object(rate_sets, "usage", return_value={"salary_slips": 0, "certificates": 0}):
			doc = rate_sets.unlock(self.base, "typo in TER B")
		self.assertEqual((doc.status, doc.unlock_reason, doc.verified_by), ("Draft", "typo in TER B", None))

	def test_usage_counts_submitted_pph21_slips_in_the_sets_window(self):
		frappe.db.set_single_value(SETTINGS, "pph21_component", "_Test Rate Set PPh 21")
		before = rate_sets.usage(self.base)["salary_slips"]
		slip = frappe.generate_hash(length=10)
		frappe.db.sql(
			"insert into `tabSalary Slip` (name, docstatus, end_date, start_date, posting_date) values (%s, 1, %s, %s, %s)",
			(slip, nowdate(), nowdate(), nowdate()),
		)
		frappe.db.sql(
			"insert into `tabSalary Detail` (name, parent, parenttype, parentfield, salary_component) "
			"values (%s, %s, 'Salary Slip', 'deductions', '_Test Rate Set PPh 21')",
			(frappe.generate_hash(length=10), slip),
		)
		self.assertEqual(rate_sets.usage(self.base)["salary_slips"], before + 1)

	# ------------------------------------------------------------ shipped fixtures + adoption
	def test_a_shipped_fixture_never_touches_a_verified_set(self):
		self.assertIsNone(rate_sets.ensure_fixture_set(frappe.db.get_value(DOCTYPE, self.base, "effective_from"), "x", "y"))
		self.assertEqual(rates_loader.load_rates(), {})

	def test_a_shipped_fixture_for_a_new_date_arrives_as_a_draft(self):
		name = rate_sets.ensure_fixture_set(add_years(nowdate(), 1), "PMK next/2027", "shipped")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Draft")

	def test_later_unlinked_rows_are_adopted_as_a_draft(self):
		effective = add_years(nowdate(), 2)
		frappe.db.sql(
			"insert into `tabEIL PPh 21 Bracket` (name, from_amount, to_amount, rate, effective_from) values (%s, 0, 0, 5, %s)",
			(frappe.generate_hash(length=10), effective),
		)
		rate_sets.adopt_unlinked_rows()
		name = frappe.db.get_value(DOCTYPE, {"effective_from": effective}, "name")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Draft")
		rate_sets.adopt_unlinked_rows()  # idempotent
		self.assertEqual(frappe.db.count(DOCTYPE, {"effective_from": effective}), 1)


def _with_pdf(doc):
	frappe.db.set_value(DOCTYPE, doc.name, "source_file", "/private/files/regulation.pdf", update_modified=False)
	return doc.name
