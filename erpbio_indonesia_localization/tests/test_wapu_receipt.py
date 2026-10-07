# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""A receipt against a government (pemungut / WAPU) invoice books what the
treasurer actually sent.

The invoice's reclassification moves its PPN off the receivable into Piutang
PPN Bendaharawan, so the outstanding is already net of it. Usually the
treasurer deposits the PPN to the state and sends that outstanding; some send
the PPN to us as well. The receipt says which (`eil_ppn_received`):

- net: the bank gets the outstanding, no clearing row, and Piutang PPN
  Bendaharawan stays open for the bukti setor. The hook used to raise any
  amount equal to the allocation by the PPN, so every net receipt was booked
  gross -- 52 receipts on Biozatix, Jan-Jul 2026, overstated the bank by
  Rp 194,542,645 (PAY26010022: bank line 3,355,950, booked 3,768,120).
- gross: the PPN is cleared on the receipt as a negative deduction and the bank
  gets outstanding + PPN (PAY25060046: 1,610,000 + 202,400 = 1,812,400).

Built on the export suite's fixtures; needs the company's government charge
defaults (Indonesia Tax Settings > Government tax defaults) and skips without.

    bench --site develop.localhost run-tests \
        --module erpbio_indonesia_localization.tests.test_wapu_receipt
"""

import frappe
from frappe.utils import flt

from erpbio_indonesia_localization.tests.test_coretax_faktur_export import (
	BUYER_NPWP_TYPED,
	POSTING,
	_ExportCase,
)


class TestWapuReceipt(_ExportCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.wapu_ready = bool(
			frappe.get_all(
				"EIL Govt Tax Default", filters={"parenttype": "Indonesia Tax Settings", "company": cls.company}, limit=1
			)
		)
		cls.treasurer = cls._customer("treasurer", cls.customer_group, tax_id=BUYER_NPWP_TYPED, id_type="TIN")
		frappe.db.set_value("Customer", cls.treasurer, "eil_is_pemungut", 1, update_modified=False)
		cls.bank = frappe.db.get_value(
			"Account", {"company": cls.company, "account_type": "Bank", "is_group": 0, "disabled": 0}, "name", order_by="name asc"
		)

	def setUp(self):
		super().setUp()
		if not self.wapu_ready:
			self.skipTest("the company has no government tax defaults")
		if not self.bank:
			self.skipTest("the company has no bank account")
		if not frappe.get_meta("Payment Entry").has_field("eil_ppn_received"):
			self.skipTest("migrate first: Payment Entry has no eil_ppn_received")
		self.si = self._invoice([(self.service, 1, 10_000_000, "Unit")], customer=self.treasurer, template=self.template_ppn)
		self.assertTrue(self.si.eil_wapu_journal_entry, "fixture: the reclassification posted")
		self.outstanding = flt(frappe.db.get_value("Sales Invoice", self.si.name, "outstanding_amount"))
		ppn_row = next(r for r in self.si.eil_govt_charges if r.clear_on_payment)
		self.ppn_account, self.ppn = ppn_row.account, flt(ppn_row.amount)
		self.assertAlmostEqual(self.ppn, 1_100_000, places=0, msg="fixture: PPN 11% of 10,000,000")

	# ------------------------------------------------------------- helpers
	def _receipt(self, amount=None, allocate=None, ppn_received=None, deductions=(), insert=True):
		"""A receipt as ERPNext's own "Create > Payment" builds it: the amount
		prefilled from the outstanding until a real figure is typed over it."""
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		pe = get_payment_entry("Sales Invoice", self.si.name, bank_account=self.bank)
		pe.posting_date = POSTING
		pe.reference_no = "SP2D-TEST-WAPU"
		pe.reference_date = POSTING
		if allocate is not None:
			pe.references[0].allocated_amount = allocate
		if amount is not None:
			pe.paid_amount = pe.received_amount = amount
		if ppn_received is not None:
			pe.eil_ppn_received = ppn_received
		for row in deductions:
			pe.append("deductions", {"cost_center": self.cost_center, **row})
		if insert:
			pe.insert(ignore_permissions=True)
		return pe

	def _ppn_rows(self, pe):
		return [(d.account, flt(d.amount)) for d in pe.deductions if d.account == self.ppn_account]

	def _ppn_balance(self, *vouchers):
		return flt(
			frappe.db.sql(
				"""select sum(debit - credit) from `tabGL Entry`
				where account=%s and is_cancelled=0 and voucher_no in %s""",
				(self.ppn_account, (self.si.eil_wapu_journal_entry, *vouchers)),
			)[0][0]
		)

	def _bank_debit(self, pe):
		return flt(
			frappe.db.sql(
				"select sum(debit - credit) from `tabGL Entry` where account=%s and is_cancelled=0 and voucher_no=%s",
				(self.bank, pe.name),
			)[0][0]
		)

	# --------------------------------------------------------------- net
	def test_a_net_receipt_stays_net(self):
		"""The treasurer sent the outstanding and deposited the PPN itself."""
		pe = self._receipt()
		self.assertFalse(pe.eil_ppn_received)
		self.assertEqual(self._ppn_rows(pe), [], "a net receipt cleared the PPN with no bukti setor")
		self.assertAlmostEqual(flt(pe.paid_amount), self.outstanding, places=2,
			msg="a net receipt was raised by the PPN: the bank is overstated")
		pe.submit()
		self.assertAlmostEqual(self._bank_debit(pe), self.outstanding, places=2)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", self.si.name, "outstanding_amount")), 0)
		self.assertAlmostEqual(self._ppn_balance(pe.name), self.ppn, places=2,
			msg="Piutang PPN Bendaharawan must stay open for the bukti setor")

	def test_a_net_amount_typed_from_the_statement_stays_net(self):
		pe = self._receipt(amount=self.outstanding)
		self.assertEqual(self._ppn_rows(pe), [])
		self.assertAlmostEqual(flt(pe.paid_amount), self.outstanding, places=2)

	# ------------------------------------------------------------- gross
	def test_a_gross_receipt_clears_the_ppn(self):
		"""The treasurer sent the outstanding plus the PPN."""
		pe = self._receipt(ppn_received=1)
		self.assertEqual(self._ppn_rows(pe), [(self.ppn_account, -self.ppn)])
		self.assertAlmostEqual(flt(pe.paid_amount), self.outstanding + self.ppn, places=2)
		self.assertAlmostEqual(flt(pe.unallocated_amount), 0, places=2)
		pe.submit()
		self.assertAlmostEqual(self._bank_debit(pe), self.outstanding + self.ppn, places=2)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", self.si.name, "outstanding_amount")), 0)
		self.assertAlmostEqual(self._ppn_balance(pe.name), 0, places=2)

	def test_a_gross_amount_typed_from_the_statement_is_gross(self):
		"""Exactly outstanding + PPN cannot mean net: without the clearing row the
		PPN would sit on the customer as an unallocated advance."""
		pe = self._receipt(amount=self.outstanding + self.ppn)
		self.assertEqual(pe.eil_ppn_received, 1)
		self.assertEqual(self._ppn_rows(pe), [(self.ppn_account, -self.ppn)])
		self.assertAlmostEqual(flt(pe.unallocated_amount), 0, places=2)

	def test_a_clearing_row_sent_with_the_receipt_is_kept_once(self):
		"""erpbio_general's cash/bank form sends the row and the gross amount
		itself; the hook records that as gross and adds nothing."""
		pe = self._receipt(amount=self.outstanding + self.ppn,
			deductions=[{"account": self.ppn_account, "amount": -self.ppn}])
		self.assertEqual(pe.eil_ppn_received, 1)
		self.assertEqual(self._ppn_rows(pe), [(self.ppn_account, -self.ppn)])

	def test_a_gross_receipt_with_a_bank_fee_keeps_its_amount(self):
		pe = self._receipt(amount=self.outstanding + self.ppn - 6_500, ppn_received=1,
			deductions=[{"account": self.freight_account, "amount": 6_500}])
		self.assertAlmostEqual(flt(pe.paid_amount), self.outstanding + self.ppn - 6_500, places=2)
		self.assertEqual(self._ppn_rows(pe), [(self.ppn_account, -self.ppn)])
		self.assertAlmostEqual(flt(pe.difference_amount), 0, places=2)

	# ------------------------------------------------- changing one's mind
	def test_unticking_takes_the_clearing_back_out(self):
		pe = self._receipt(ppn_received=1)
		self.assertTrue(self._ppn_rows(pe), "fixture: the tick cleared the PPN")
		pe.eil_ppn_received = 0
		pe.save(ignore_permissions=True)
		self.assertEqual(self._ppn_rows(pe), [])
		self.assertAlmostEqual(flt(pe.paid_amount), self.outstanding, places=2)
		pe.save(ignore_permissions=True)  # and it stays net
		self.assertFalse(pe.eil_ppn_received)
		self.assertEqual(self._ppn_rows(pe), [])

	def test_ticking_a_saved_net_receipt_makes_it_gross(self):
		pe = self._receipt()
		pe.eil_ppn_received = 1
		pe.save(ignore_permissions=True)
		self.assertEqual(self._ppn_rows(pe), [(self.ppn_account, -self.ppn)])
		self.assertAlmostEqual(flt(pe.paid_amount), self.outstanding + self.ppn, places=2)

	# ------------------------------------------------------ part payment
	def test_a_part_payment_is_left_to_the_accountant_even_when_ticked(self):
		half = flt(self.outstanding / 2, 2)
		pe = self._receipt(amount=half, allocate=half, ppn_received=1)
		self.assertEqual(self._ppn_rows(pe), [])
		self.assertAlmostEqual(flt(pe.paid_amount), half, places=2)
