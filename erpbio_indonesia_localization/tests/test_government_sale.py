# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""A sale to a government treasurer (pemungut / WAPU) is filed as one.

- T-002: the invoice takes the pemungut transaction code (02 by default) when
  the flag is derived; left blank it exported as 01, declaring the PPN the
  bendahara deposits as PPN we collected.
- T-007: SPT Masa owes only the PPN we collected ourselves. A pemungut sale
  (02/03), a sale whose PPN is not collected (07) and an exempt one (08) are
  reported on their own lines and never added to kurang bayar.
- T-009: the PPh 22 the buyer withholds on the invoice is a certificate we are
  owed -- an Expected Bukti Potong linked to the invoice, gone again if the
  invoice is cancelled while it is still unnumbered.

Built on the export suite's fixtures (company, settings, items, templates and
the invoice helper). The WAPU cases need the company's government charge
defaults (Indonesia Tax Settings › Government tax defaults) and skip without.

    bench --site develop.localhost run-tests \
        --module erpbio_indonesia_localization.tests.test_government_sale
"""

import frappe
from frappe.utils import flt

from erpbio_indonesia_localization.tests.test_coretax_faktur_export import (
	BUYER_NPWP_TYPED,
	PERIOD,
	_ExportCase,
)


class TestGovernmentSale(_ExportCase):
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
		settings = frappe.get_single("Indonesia Tax Settings")
		cls._saved_pemungut_code = settings.get("pemungut_transaction_code")
		if settings.meta.has_field("pemungut_transaction_code"):
			settings.pemungut_transaction_code = "02"
			settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Indonesia Tax Settings", "Indonesia Tax Settings")

	def _wapu(self):
		if not self.wapu_ready:
			self.skipTest("the company has no government tax defaults")

	def _sale(self, customer, net=100_000_000, **kw):
		return self._invoice([(self.service, 1, net, "Unit")], customer=customer, template=self.template_ppn, **kw)

	# --- T-002 ------------------------------------------------------------------

	def test_a_pemungut_invoice_takes_kode_02(self):
		self._wapu()
		si = self._sale(self.treasurer)
		self.assertEqual(si.eil_is_pemungut, 1, "fixture: the treasurer is a pemungut")
		self.assertEqual(si.eil_kode_transaksi, "02",
			"a sale to a bendahara went out with no code and would export as 01 (T-002)")

	def test_a_code_the_accountant_chose_stays(self):
		self._wapu()
		si = self._sale(self.treasurer, eil_kode_transaksi="03")
		self.assertEqual(si.eil_kode_transaksi, "03")

	def test_an_ordinary_sale_is_left_to_the_default(self):
		si = self._sale(self.buyer, net=1_000_000)
		self.assertFalse(si.eil_kode_transaksi)

	# --- T-007 ------------------------------------------------------------------

	def _spt(self):
		from erpbio_indonesia_localization.api import tax

		return tax.spt_masa(self.company, *PERIOD)

	def _line(self, spt, key):
		return next(line for line in spt["keluaran_lines"] if line["key"] == key)

	def test_only_ppn_we_collect_ourselves_is_payable(self):
		self._wapu()
		before = self._spt()
		self._sale(self.buyer, net=10_000_000)                            # 01: PPN 1.1M, ours to pay
		self._sale(self.treasurer, net=100_000_000)                       # 02: the bendahara deposits it
		self._invoice([(self.service, 1, 5_000_000, "Unit")], customer=self.buyer, eil_kode_transaksi="08")  # exempt
		after = self._spt()
		self.assertAlmostEqual(after["keluaran"] - before["keluaran"], 1_100_000, places=0,
			msg="SPT kurang bayar counts PPN it does not owe: the bendahara's and/or an exempt sale's (T-007)")
		self.assertEqual(self._line(after, "pemungut")["count"] - self._line(before, "pemungut")["count"], 1)
		self.assertEqual(self._line(after, "exempt")["count"] - self._line(before, "exempt")["count"], 1)
		self.assertFalse(self._line(after, "pemungut")["payable"])
		self.assertAlmostEqual(after["net"] - before["net"], 1_100_000, places=0)

	def test_an_old_pemungut_invoice_with_no_code_is_still_not_payable(self):
		self._wapu()
		before = self._spt()
		si = self._sale(self.treasurer, net=50_000_000)
		frappe.db.set_value("Sales Invoice", si.name, "eil_kode_transaksi", None)  # raised before T-002
		after = self._spt()
		self.assertAlmostEqual(after["keluaran"], before["keluaran"], places=0)

	# --- T-009 ------------------------------------------------------------------

	def _bps(self, si):
		return frappe.get_all(
			"Bukti Potong", filters={"sales_invoice": si},
			fields=["name", "direction", "tax_type", "tax_amount", "gross_amount", "status", "customer", "payment_entry"],
		)

	def test_the_government_s_pph22_makes_an_expected_bukti_potong(self):
		self._wapu()
		si = self._sale(self.treasurer, net=100_000_000)
		self.assertTrue(si.eil_wapu_journal_entry, "fixture: the reclassification posted")
		bps = self._bps(si.name)
		self.assertEqual(len(bps), 1, "the PPh 22 withheld on a government sale has no Bukti Potong (T-009)")
		bp = bps[0]
		self.assertEqual((bp.direction, bp.tax_type, bp.status, bp.customer), ("Received", "PPh 22", "Expected", self.treasurer))
		self.assertAlmostEqual(flt(bp.tax_amount), 1_500_000, places=0)
		self.assertAlmostEqual(flt(bp.gross_amount), 100_000_000, places=0)
		self.assertFalse(bp.payment_entry)

	def test_cancelling_the_invoice_takes_its_unnumbered_bukti_potong(self):
		self._wapu()
		si = self._sale(self.treasurer, net=100_000_000)
		si.cancel()
		self.assertEqual(self._bps(si.name), [])

	def test_a_numbered_bukti_potong_outlives_the_invoice(self):
		self._wapu()
		si = self._sale(self.treasurer, net=100_000_000)
		bp = frappe.get_doc("Bukti Potong", self._bps(si.name)[0].name)
		bp.bp_number = "BP-TEST-0001"
		bp.save(ignore_permissions=True)
		si.cancel()
		self.assertEqual(len(self._bps(si.name)), 1)
