# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""T-001: the buyer identity a single invoice carries wins over the Customer's.

A person buying under a NIK is often on a Customer record that says TIN (the
company's NPWP was typed there first). The faktur has to say what THIS sale
was: `eil_id_type` / `eil_document_number` on the invoice, blank meaning
"whatever the Customer says" -- and the number, type and document have to come
from the same place, or a NIK goes out labelled as an NPWP.

Shipped with it, from the same 2026-09-21 work:
- a tax-inclusive price is refused on a sale to a pemungut (the buyer pays the
  PPN itself; stripping an inclusive PPN row bills VAT on the VAT);
- the tax app's customer list no longer crashes when "missing Tax ID" is
  combined with another filter.

    bench --site develop.localhost run-tests \
        --module erpbio_indonesia_localization.tests.test_invoice_buyer_identity
"""

import json

import frappe

from erpbio_indonesia_localization.tests.test_coretax_faktur_export import (
	BUYER_NPWP,
	_ExportCase,
)

NIK = "3171234567890123"


class TestInvoiceBuyerIdentity(_ExportCase):
	def _bits(self, si):
		return self._export()._buyer_bits(si)

	def test_a_blank_invoice_takes_the_customer_s_identity(self):
		si = self._invoice([(self.service, 1, 1_000_000, "Unit")], template=self.template_ppn)
		bits = self._bits(si)
		self.assertEqual((bits["id_type"], bits["npwp"]), ("TIN", BUYER_NPWP))

	def test_a_nik_on_the_invoice_wins_over_the_customer(self):
		if not frappe.get_meta("Sales Invoice").has_field("eil_id_type"):
			self.fail("Sales Invoice has no eil_id_type: the per-invoice identity fields were not installed (T-001)")
		si = self._invoice(
			[(self.service, 1, 1_000_000, "Unit")], template=self.template_ppn, tax_id=NIK, eil_id_type="NIK"
		)
		bits = self._bits(si)
		self.assertEqual((bits["id_type"], bits["npwp"]), ("NIK", NIK),
			"the invoice says NIK but the faktur would carry the Customer's type")

	def test_a_passport_on_the_invoice_carries_its_document_number(self):
		si = self._invoice(
			[(self.service, 1, 1_000_000, "Unit")], template=self.template_ppn,
			eil_id_type="Passport", eil_document_number="B7654321",
		)
		bits = self._bits(si)
		self.assertEqual((bits["id_type"], bits["document_number"]), ("Passport", "B7654321"))

	def test_a_tax_inclusive_price_is_refused_for_a_pemungut(self):
		frappe.db.set_value("Customer", self.buyer_nitku, "eil_is_pemungut", 1, update_modified=False)
		from erpnext.controllers.accounts_controller import get_taxes_and_charges

		doc = frappe.get_doc({
			"doctype": "Sales Invoice", "company": self.company, "customer": self.buyer_nitku,
			"customer_address": self.addresses.get(self.buyer_nitku), "posting_date": "2026-03-15",
			"set_posting_time": 1, "due_date": "2026-03-15", "currency": "IDR", "conversion_rate": 1,
			"items": [{"item_code": self.service, "qty": 1, "rate": 11_100_000, "uom": "Unit", "conversion_factor": 1,
				"income_account": self.income_account, "cost_center": self.cost_center}],
		})
		for row in get_taxes_and_charges("Sales Taxes and Charges Template", self.template_ppn):
			row["included_in_print_rate"] = 1
			doc.append("taxes", row)
		with self.assertRaisesRegex(frappe.ValidationError, "tax-inclusive"):
			doc.insert(ignore_permissions=True)

	def test_the_customer_list_takes_missing_tax_id_with_another_filter(self):
		from erpbio_indonesia_localization.api import tax

		result = tax.list_customers(filters=json.dumps([
			{"field": "missing_tax_id", "operator": "=", "value": "1"},
			{"field": "customer_group", "operator": "=", "value": self.customer_group},
		]))
		self.assertIn("items", result if isinstance(result, dict) else {"items": result})
