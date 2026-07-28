# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""Tests for the PPh 21 tables and calculator.

The important ones reproduce the worked examples DJP publishes in PMK 168/2023
and its December-2025 BPA1 guidance. Matching an official example end to end is
the only check that proves the rate tables, the deduction rules and the rounding
all at once — a self-consistent implementation can still be confidently wrong.

    bench --site develop.localhost run-tests \
        --module erpbio_indonesia_localization.pph21.test_pph21
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from erpbio_indonesia_localization.pph21 import calculator, tables


class TestPPh21Tables(FrappeTestCase):
	def setUp(self):
		_verify_tables()

	def test_loaded_tables_pass_their_invariants(self):
		self.assertEqual(tables.validate_tables(), [])

	def test_ter_category_mapping_is_the_regulation_s(self):
		# PMK 168 states these groupings itself; they are not inferred.
		for status in ("TK/0", "TK/1", "K/0"):
			self.assertEqual(tables.ter_category(status), "A")
		for status in ("TK/2", "TK/3", "K/1", "K/2"):
			self.assertEqual(tables.ter_category(status), "B")
		self.assertEqual(tables.ter_category("K/3"), "C")

	def test_ptkp_ladder(self):
		self.assertEqual(tables.ptkp_annual("TK/0"), 54_000_000)
		self.assertEqual(tables.ptkp_annual("K/0"), 58_500_000)
		self.assertEqual(tables.ptkp_annual("K/3"), 72_000_000)

	def test_ter_band_boundaries(self):
		# Both sides of a boundary, where an off-by-one would hide.
		self.assertEqual(tables.ter_rate("A", 5_400_000), 0.0)
		self.assertEqual(tables.ter_rate("A", 5_400_001), 0.25)
		self.assertEqual(tables.ter_rate("A", 8_000_000), 1.5)
		self.assertEqual(tables.ter_rate("A", 2_000_000_000), 34.0)

	def test_ter_c_band_7_is_the_regulation_s_rate(self):
		"""A widely-published transcription gives 2.0% here. The regulation says
		1.5%, which is also the only value that keeps the table monotonic."""
		self.assertEqual(tables.ter_rate("C", 10_000_000), 1.5)

	def test_pasal_17_is_progressive_across_bands(self):
		self.assertEqual(tables.pasal17_tax(36_000_000), 1_800_000)
		# Exactly on the first boundary: 60,000,000 taxed at 5%, not 60,000,001.
		self.assertEqual(tables.pasal17_tax(60_000_000), 3_000_000)
		# 60m@5% + 190m@15% + 50m@25%
		self.assertEqual(tables.pasal17_tax(300_000_000), 44_000_000)

	def test_unverified_tables_refuse_to_compute(self):
		frappe.db.set_single_value("EIL PPh 21 Settings", "tables_verified", 0)
		frappe.clear_cache(doctype="EIL PPh 21 Settings")
		with self.assertRaises(frappe.ValidationError):
			tables.ter_rate("A", 8_000_000)


class TestPPh21Calculator(FrappeTestCase):
	def setUp(self):
		_verify_tables()

	def test_djp_example_monthly_and_december(self):
		"""Rp 8,000,000/month, TK/0, pension Rp 100,000/month.

		DJP's own example: Rp 120,000 a month January-November, then Rp 480,000 in
		December to settle an annual liability of Rp 1,800,000.
		"""
		monthly = calculator.monthly_withholding("TK/0", 8_000_000)
		self.assertEqual(monthly, 120_000)

		result = calculator.annual_reconciliation(
			"TK/0",
			gross_teratur=96_000_000,
			iuran_pensiun=1_200_000,
			withheld_earlier_periods=11 * monthly,
		)
		self.assertEqual(result["biaya_jabatan"], 4_800_000)
		self.assertEqual(result["deductions"], 6_000_000)
		self.assertEqual(result["net"], 90_000_000)
		self.assertEqual(result["pkp"], 36_000_000)
		self.assertEqual(result["annual_tax"], 1_800_000)
		self.assertEqual(result["payable_final_period"], 480_000)

	def test_djp_deck_example_deductions(self):
		result = calculator.annual_reconciliation(
			"TK/0", gross_teratur=81_600_000, iuran_pensiun=1_200_000
		)
		self.assertEqual(result["biaya_jabatan"], 4_080_000)
		self.assertEqual(result["deductions"], 5_280_000)
		self.assertEqual(result["net"], 76_320_000)

	def test_biaya_jabatan_cap(self):
		capped = calculator.annual_reconciliation("TK/0", gross_teratur=782_765_464)
		self.assertEqual(capped["biaya_jabatan"], 6_000_000)
		self.assertEqual(capped["net"], 776_765_464)

	def test_biaya_jabatan_cap_is_per_month_worked(self):
		"""A part year caps proportionally, not at the full annual 6,000,000."""
		part = calculator.annual_reconciliation("TK/0", gross_teratur=300_000_000, months_worked=4)
		self.assertEqual(part["biaya_jabatan"], 2_000_000)

	def test_irregular_income_counts_as_gross(self):
		result = calculator.annual_reconciliation(
			"TK/0", gross_teratur=180_000_000, gross_tidak_teratur=17_000_000
		)
		self.assertEqual(result["gross"], 197_000_000)
		self.assertEqual(result["biaya_jabatan"], 6_000_000)

	def test_benefits_in_kind_and_employer_premium_count_as_gross(self):
		result = calculator.annual_reconciliation(
			"TK/0", gross_teratur=100_000_000, natura=5_000_000, employer_premium=1_000_000
		)
		self.assertEqual(result["gross"], 106_000_000)

	def test_zakat_through_employer_is_deductible(self):
		without = calculator.annual_reconciliation("TK/0", gross_teratur=120_000_000)
		with_zakat = calculator.annual_reconciliation(
			"TK/0", gross_teratur=120_000_000, zakat=3_000_000
		)
		self.assertEqual(with_zakat["net"], without["net"] - 3_000_000)

	def test_pkp_is_floored_to_whole_thousands(self):
		result = calculator.annual_reconciliation("TK/0", gross_teratur=100_000_777)
		self.assertEqual(result["pkp"] % 1000, 0)

	def test_over_withheld_year_reports_a_negative_settlement(self):
		"""TER can take more than the year owes. That is a refund to deal with,
		not something to clamp to zero and hide."""
		result = calculator.annual_reconciliation(
			"TK/0", gross_teratur=96_000_000, iuran_pensiun=1_200_000,
			withheld_earlier_periods=2_500_000,
		)
		self.assertLess(result["payable_final_period"], 0)

	def test_previous_employer_withholding_is_credited(self):
		result = calculator.annual_reconciliation(
			"TK/0", gross_teratur=96_000_000, iuran_pensiun=1_200_000,
			withheld_previous_employer=500_000,
		)
		self.assertEqual(result["payable_final_period"], 1_800_000 - 500_000)

	def test_dtp_is_credited(self):
		result = calculator.annual_reconciliation(
			"TK/0", gross_teratur=96_000_000, iuran_pensiun=1_200_000, dtp=1_800_000
		)
		self.assertEqual(result["payable_final_period"], 0)

	def test_annualisation_scales_the_tax_back_down(self):
		"""Disetahunkan: tax the annualised net, then scale to months worked. The
		result must sit below the full-year tax on the same annualised figure."""
		months = 6
		part = calculator.annual_reconciliation(
			"TK/0", gross_teratur=48_000_000, months_worked=months, annualise=True
		)
		full = calculator.annual_reconciliation("TK/0", gross_teratur=96_000_000)
		self.assertIsNotNone(part["net_annualised"])
		self.assertTrue(part["annualised"])
		self.assertLess(part["annual_tax"], full["annual_tax"])

	def test_part_year_without_annualisation_just_has_less_gross(self):
		part = calculator.annual_reconciliation(
			"TK/0", gross_teratur=48_000_000, months_worked=6, annualise=False
		)
		self.assertIsNone(part["net_annualised"])
		self.assertFalse(part["annualised"])

	def test_unsupported_scheme_throws(self):
		for scheme in ("Non-permanent", "Expatriate", "Pensioner"):
			with self.assertRaises(frappe.ValidationError):
				calculator.require_supported_scheme(scheme)
		calculator.require_supported_scheme("Permanent")  # must not raise

	def test_months_worked_is_bounded(self):
		with self.assertRaises(frappe.ValidationError):
			calculator.annual_reconciliation("TK/0", gross_teratur=1_000_000, months_worked=13)


def _verify_tables():
	"""The gate is a deliberate obstacle; tests tick it explicitly so it is
	obvious that computing at all depends on it."""
	frappe.db.set_single_value("EIL PPh 21 Settings", "tables_verified", 1)
	frappe.clear_cache(doctype="EIL PPh 21 Settings")
	frappe.local._eil_pph21_tables = {}
