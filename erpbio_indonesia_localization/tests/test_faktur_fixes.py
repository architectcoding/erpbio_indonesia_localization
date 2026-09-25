# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""The export files what the invoice charged, whatever shape the invoice has.

- T-003: DPP Nilai Lain (12% on 11/12) is how an 11% flat template reaches its
  rupiah; an invoice already charging 12% files the full price at 12%. A
  facility faktur (kode 07 tidak dipungut / 08 dibebaskan) names its facility
  and is not reconciled against a PPN it does not charge. Both were refused.
- T-005: a file Coretax rejected can be released: its still-Exported invoices go
  back to Not Exported, so they can be corrected and exported again; deleting
  an export does the same. An approved faktur is never released.
- T-008: the PPN Keluaran register reads the export's own faktur lines, so it
  states what is filed -- not DPP x 11/12 x 12% recomputed for every invoice.
- T-013: a SAVED_INVALID faktur in a Coretax import is a problem to fix, not a
  status "not final yet".

    bench --site develop.localhost run-tests \
        --module erpbio_indonesia_localization.tests.test_faktur_fixes
"""

import frappe
from frappe.utils import flt

from erpbio_indonesia_localization.tests.test_coretax_faktur_export import PERIOD, _ExportCase

ADD_INFO = "TD.00501"
STAMP = "TD.01105"


class TestFakturFixes(_ExportCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.template_ppn12 = cls._template(
			"ppn12",
			[{"charge_type": "On Net Total", "account_head": cls.vat_account, "rate": 12, "description": "PPN 12%"}],
		)

	# --- T-003: a 12% invoice -------------------------------------------------

	def test_a_12_percent_invoice_files_the_full_price_at_12(self):
		si = self._invoice([(self.goods, 1, 100_000_000, "Unit")], template=self.template_ppn12)
		self.assertAlmostEqual(flt(sum(t.tax_amount for t in si.taxes)), 12_000_000, places=0, msg="fixture: charges 12%")
		(line,) = self._lines(si)
		self.assertEqual((line["dpp"], line["dpp_lain"], line["tarif"], line["ppn"]), (100_000_000.0, 100_000_000.0, 12.0, 12_000_000.0))
		_, row = self._row_for(si.name)
		self.assertTrue(row.ok, f"a 12% invoice is refused (T-003): {row.message}")

	def test_an_11_percent_invoice_still_files_nilai_lain(self):
		si = self._invoice([(self.goods, 1, 12_000_000, "Unit")], template=self.template_ppn)
		(line,) = self._lines(si)
		self.assertEqual((line["dpp_lain"], line["ppn"]), (11_000_000.0, 1_320_000.0))

	# --- T-003: a facility faktur ---------------------------------------------

	def _exempt(self, **kw):
		return self._invoice([(self.service, 1, 5_000_000, "Unit")], eil_kode_transaksi="08", **kw)

	def test_a_kode_08_invoice_without_its_facility_is_held(self):
		_, row = self._row_for(self._exempt().name)
		self.assertFalse(row.ok)
		self.assertIn("Cap Fasilitas", row.message)

	def test_a_kode_08_invoice_with_its_facility_is_ready_and_states_it(self):
		si = self._exempt(eil_add_info=ADD_INFO, eil_facility_stamp=STAMP)
		export, row = self._row_for(si.name)
		self.assertTrue(row.ok, f"an exempt invoice is refused against a PPN it does not charge (T-003): {row.message}")
		root, _ = self._xml(self._only_mine(export, [si.name]))
		inv = root.find(".//TaxInvoice")
		self.assertEqual((inv.findtext("TrxCode"), inv.findtext("AddInfo"), inv.findtext("FacilityStamp")), ("08", ADD_INFO, STAMP))

	# --- T-005: release -------------------------------------------------------

	def _generated(self, si):
		export, row = self._row_for(si.name)
		self.assertTrue(row.ok, row.message)
		self._workbook(self._only_mine(export, [si.name]))
		self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "eil_faktur_status"), "Exported")
		return export

	def test_release_puts_an_exported_invoice_back(self):
		from erpbio_indonesia_localization.api import tax

		si = self._invoice([(self.goods, 1, 1_000_000, "Unit")], template=self.template_ppn)
		export = self._generated(si)
		result = tax.release_export(export.name)
		self.assertEqual(result["released"], [si.name])
		self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "eil_faktur_status"), "Not Exported")
		_, row = self._row_for(si.name)  # a new export offers it again
		self.assertTrue(row.ok, row.message)

	def test_release_never_touches_an_approved_faktur(self):
		si = self._invoice([(self.goods, 1, 1_000_000, "Unit")], template=self.template_ppn)
		export = self._generated(si)
		frappe.db.set_value("Sales Invoice", si.name, "eil_faktur_status", "Approved")
		self.assertEqual(export.release(), [])
		self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "eil_faktur_status"), "Approved")

	def test_deleting_an_export_releases_its_invoices(self):
		si = self._invoice([(self.goods, 1, 1_000_000, "Unit")], template=self.template_ppn)
		export = self._generated(si)
		frappe.delete_doc("Coretax Faktur Export", export.name, force=1, ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "eil_faktur_status"), "Not Exported")

	# --- T-008: the register --------------------------------------------------

	def _register_row(self, si):
		from erpbio_indonesia_localization.erpbio_indonesia_localization.report.ppn_keluaran import ppn_keluaran

		rows = [
			r for r in ppn_keluaran.get_data(frappe._dict(company=self.company, from_date=PERIOD[0], to_date=PERIOD[1]))
			if r["sales_invoice"] == si.name
		]
		self.assertEqual(len(rows), 1)
		return rows[0]

	def test_the_register_states_what_a_12_percent_invoice_files(self):
		si = self._invoice([(self.goods, 1, 100_000_000, "Unit")], template=self.template_ppn12)
		row = self._register_row(si)
		self.assertAlmostEqual(row["ppn"], 12_000_000, places=0,
			msg=f"the register reads {row['ppn']} for an invoice that charged and files 12,000,000 (T-008)")
		self.assertAlmostEqual(row["ppn_invoice"], 12_000_000, places=0)

	def test_the_register_counts_a_taxed_freight_charge_in_the_dpp(self):
		si = self._invoice([(self.goods, 1, 10_000_000, "Unit")], template=self.template_freight)
		row = self._register_row(si)
		filed = sum(line["dpp"] for line in self._lines(si))
		self.assertAlmostEqual(row["dpp"], filed, places=2, msg="the register leaves the freight out of the DPP it files (T-008)")
		self.assertAlmostEqual(row["dpp"], 10_500_000, places=0)

	# --- T-013 ----------------------------------------------------------------

	def test_a_saved_invalid_faktur_reads_as_a_problem_to_fix(self):
		si = self._invoice([(self.goods, 1, 1_000_000, "Unit")], template=self.template_ppn)
		doc = frappe.new_doc("Coretax Faktur Import")
		ok, _doctype, _name, message = doc._match(si.name, "04002600000123", None, "SAVED_INVALID")
		self.assertFalse(ok)
		self.assertIn("invalid", message.lower(), f"SAVED_INVALID reads as '{message}' (T-013)")
		self.assertNotIn("not final", message.lower())
