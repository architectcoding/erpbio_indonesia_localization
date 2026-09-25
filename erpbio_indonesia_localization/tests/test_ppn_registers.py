# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""The PPN registers say what the SPT Masa may rely on.

PPN Masukan (input VAT):
- the input VAT is what the invoice's input-VAT rows charged -- a PPh 23 row
  withheld from the supplier on the same invoice is not input VAT and must not
  shrink it (T-011: the register took `base_total_taxes_and_charges`, which nets
  the withholding out);
- it is creditable only with a supplier faktur behind it, inside the crediting
  window (T-006: `eil_creditable` defaults to 1 and nothing else was checked, so
  a purchase with no faktur at all was credited on the SPT).

Fixtures are Purchase Invoices on the site's own company, rolled back with the
class. Outside the doctype folder on purpose (see test_coretax_faktur_export).

    bench --site develop.localhost run-tests \
        --module erpbio_indonesia_localization.tests.test_ppn_registers
"""

import frappe
from frappe.utils import flt

try:  # Frappe v16
	from frappe.tests import IntegrationTestCase as _TestCase
except ImportError:  # older Frappe
	from frappe.tests.utils import FrappeTestCase as _TestCase

from erpbio_indonesia_localization.erpbio_indonesia_localization.report.ppn_masukan import ppn_masukan

PREFIX = "_TEST_PPNREG_"
POSTING = "2026-03-16"
PERIOD = frappe._dict(from_date="2026-03-01", to_date="2026-03-31")


class TestPpnMasukan(_TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from erpnext import get_default_company

		cls.company = get_default_company() or frappe.get_all("Company", pluck="name", order_by="name")[0]
		PERIOD.company = cls.company
		cls.input_vat = frappe.db.get_value(
			"Account", {"company": cls.company, "account_type": "Tax", "root_type": "Asset", "is_group": 0}, "name"
		)
		cls.pph23 = frappe.db.get_value(
			"Account", {"company": cls.company, "account_type": "Tax", "root_type": "Liability", "is_group": 0}, "name"
		)
		cls.expense = frappe.db.get_value("Company", cls.company, "default_expense_account") or frappe.db.get_value(
			"Account", {"company": cls.company, "root_type": "Expense", "is_group": 0}, "name"
		)
		cls.cost_center = frappe.db.get_value("Company", cls.company, "cost_center")
		cls.ready = bool(cls.input_vat and cls.pph23 and cls.expense)
		if not cls.ready:
			return
		cls.supplier = PREFIX + "Supplier"
		if not frappe.db.exists("Supplier", cls.supplier):
			frappe.get_doc({
				"doctype": "Supplier", "supplier_name": cls.supplier,
				"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
				"tax_id": "0123456789012345",
			}).insert(ignore_permissions=True)
		cls.item = PREFIX + "service"
		if not frappe.db.exists("Item", cls.item):
			frappe.get_doc({
				"doctype": "Item", "item_code": cls.item, "item_name": "PPN register service",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": "Nos", "is_stock_item": 0, "is_purchase_item": 1,
			}).insert(ignore_permissions=True)

	def setUp(self):
		super().setUp()
		if not self.ready:
			self.skipTest("the company has no input-VAT (Tax/Asset) or Tax/Liability account")

	def _pi(self, net, *, pph23=0.0, faktur_number="04002600000001", faktur_date=POSTING, **kw):
		taxes = [{
			"category": "Total", "add_deduct_tax": "Add", "charge_type": "On Net Total",
			"account_head": self.input_vat, "rate": 11, "description": "PPN Masukan 11%", "cost_center": self.cost_center,
		}]
		if pph23:
			taxes.append({
				"category": "Total", "add_deduct_tax": "Deduct", "charge_type": "On Net Total",
				"account_head": self.pph23, "rate": pph23, "description": "PPh 23", "cost_center": self.cost_center,
			})
		doc = frappe.get_doc({
			"doctype": "Purchase Invoice", "company": self.company, "supplier": self.supplier,
			"posting_date": POSTING, "set_posting_time": 1, "bill_date": POSTING,
			"items": [{"item_code": self.item, "qty": 1, "rate": net, "expense_account": self.expense, "cost_center": self.cost_center}],
			"taxes": taxes,
			"eil_faktur_number": faktur_number, "eil_faktur_date": faktur_date,
			**kw,
		})
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def _row(self, name):
		rows = [r for r in ppn_masukan.get_data(PERIOD) if r["purchase_invoice"] == name]
		self.assertEqual(len(rows), 1, f"{name} not in the register")
		return rows[0]

	# --- T-011 ------------------------------------------------------------------

	def test_a_pph23_withholding_does_not_shrink_the_input_vat(self):
		pi = self._pi(10_000_000, pph23=2)
		self.assertAlmostEqual(flt(pi.base_total_taxes_and_charges), 900_000, places=0, msg="fixture: PPN 1.1M less PPh 23 200k")
		row = self._row(pi.name)
		self.assertAlmostEqual(row["ppn"], 1_100_000, places=2,
			msg=f"input VAT reads {row['ppn']}: the PPh 23 withheld from the supplier was netted out of it (T-011)")

	def test_an_explicit_ppn_amount_still_wins(self):
		pi = self._pi(10_000_000, eil_ppn_amount=1_000_000)
		self.assertAlmostEqual(self._row(pi.name)["ppn"], 1_000_000, places=2)

	# --- T-006 ------------------------------------------------------------------

	def test_input_vat_without_a_supplier_faktur_is_not_creditable(self):
		pi = self._pi(10_000_000, faktur_number="")
		row = self._row(pi.name)
		self.assertEqual(row["creditable"], 0, "a purchase with no faktur was counted as creditable input VAT (T-006)")
		self.assertIn("faktur", row["not_creditable_reason"].lower())

	def test_a_faktur_older_than_the_crediting_window_is_not_creditable(self):
		pi = self._pi(10_000_000, faktur_date="2025-11-20")  # four periods before March
		row = self._row(pi.name)
		self.assertEqual(row["creditable"], 0)
		self.assertIn("3", row["not_creditable_reason"])

	def test_a_faktur_inside_the_window_is_creditable(self):
		pi = self._pi(10_000_000, faktur_date="2025-12-20")  # three periods before March
		row = self._row(pi.name)
		self.assertEqual((row["creditable"], row["not_creditable_reason"]), (1, ""))

	def test_the_spt_counts_only_creditable_input_vat(self):
		from erpbio_indonesia_localization.api import tax

		before = tax.spt_masa(self.company, PERIOD.from_date, PERIOD.to_date)["masukan"]
		self._pi(10_000_000, faktur_number="")
		self._pi(20_000_000)
		after = tax.spt_masa(self.company, PERIOD.from_date, PERIOD.to_date)["masukan"]
		self.assertAlmostEqual(after - before, 2_200_000, places=2,
			msg="only the invoice with a faktur is credited on the SPT (T-006)")
