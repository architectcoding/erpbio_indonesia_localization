# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""Would the Coretax export produce a file DJP accepts?

Until this file existed nothing tested the export at all, and it had never been
run: zero Coretax Faktur Export records on the live site, zero files generated.
A dry run of the validator over every submitted invoice there returned 0 of 3
exportable — so "it works" had never been anything but an assumption.

Three things are worth testing, in this order.

The **arithmetic**, because a wrong figure here is under-declared output tax.
The general rate since PMK 131/2024 is reached by reporting 12% on a DPP Nilai
Lain of 11/12 of the base, while the selling templates charge a flat 11% on the
whole base. Those must land on the same rupiah or the faktur contradicts the
invoice it is supposed to represent. `test_dpp_nilai_lain_reconciles_with_an_11_percent_template`
is that check, on the real figures from VBS26070008-1.

The **per-line identity**, because Coretax enforces DPP = Harga Satuan x Jumlah
- Total Diskon on every line and rejects the upload if it does not hold. Nothing
on the live site has a fractional unit price, so this had never once been
exercised.

The **file shape**, because the workbook feeds DJP's own Excel-to-XML converter
and the XML feeds Coretax directly. Sheet names, header order, the Baris linkage
between the two sheets and the END markers are a contract with someone else's
parser, not an internal detail.

Fixtures are built here rather than borrowed from the site: the live company has
no NPWP and none of its 171 customers has a tax ID, so every real invoice fails
validation before reaching any of the logic above.

Deliberately NOT inside the doctype folder. Frappe infers `cls.doctype` from a
"doctype" path component and then builds test records for every dependency of
it, which for Sales Invoice drags in ERPNext's whole standard fixture chain —
including a Quotation that erpbio_general's max-discount hook rejects, so the
suite errored before it ran a single test. Outside that folder no dependency
records are generated and the fixtures below are the only ones that exist.

    bench --site vantage-develop.localhost run-tests \
        --module erpbio_indonesia_localization.tests.test_coretax_faktur_export
"""

import os
from xml.etree import ElementTree as ET

import frappe
from frappe.utils import flt

try:  # Frappe v16
	from frappe.tests import IntegrationTestCase as _TestCase
except ImportError:  # older Frappe
	from frappe.tests.utils import FrappeTestCase as _TestCase

from erpbio_indonesia_localization.erpbio_indonesia_localization.doctype.coretax_faktur_export.coretax_faktur_export import (
	DETAIL_HEADERS,
	FAKTUR_HEADERS,
)

PREFIX = "_TEST_CT_"
PERIOD = ("2026-03-01", "2026-03-31")
POSTING = "2026-03-15"

# A well-formed NPWP as a person would type it: the export must reduce it to
# digits, because DJP rejects the punctuation.
SELLER_NPWP_TYPED = "01.234.567.8-901.000"
SELLER_NPWP = "012345678901000"
BUYER_NPWP_TYPED = "09.876.543.2-109.000"
BUYER_NPWP = "098765432109000"


class _ExportCase(_TestCase):
	"""Reference data once per class; invoices per test.

	Everything here runs inside the transaction Frappe rolls back when the class
	finishes, so nothing reaches the site — but only as long as no test commits.
	Nothing in the export path does: `save()`, `db_set()` and `File.insert()` all
	leave the commit to the caller. The one thing rollback cannot undo is the
	attachment written to disk, which is why `_forget_files` exists.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# The site's real company, not whatever sorts first: ERPNext's own
		# "_Test Company" is present here and has none of the Indonesian chart of
		# accounts these fixtures need.
		from erpnext import get_default_company

		cls.company = get_default_company() or frappe.get_all("Company", pluck="name", order_by="name")[0]
		cls.abbr = frappe.db.get_value("Company", cls.company, "abbr")
		cls.income_account = frappe.db.get_value("Company", cls.company, "default_income_account")
		cls.cost_center = frappe.db.get_value("Company", cls.company, "cost_center")

		# The live company has no NPWP at all; give the fixture one so the tests
		# reach the mapping instead of stopping at the identity gate.
		frappe.db.set_value("Company", cls.company, "tax_id", SELLER_NPWP_TYPED, update_modified=False)
		frappe.db.set_value("Company", cls.company, "eil_nitku", "", update_modified=False)

		# Units first: the charge mapping in settings links to one.
		cls._seed_units()
		cls._seed_settings()
		cls._seed_items()
		cls._seed_customers()
		cls._seed_templates()

	# ------------------------------------------------------------- fixtures
	@classmethod
	def _seed_settings(cls):
		settings = frappe.get_single("Indonesia Tax Settings")
		settings.tarif_ppn = 12
		settings.use_dpp_nilai_lain = 1
		settings.dpp_numerator = 11
		settings.dpp_denominator = 12
		settings.default_transaction_code = "01"
		settings.default_buyer_country = "IDN"

		cls.vat_account = next(
			(r.account for r in (settings.get("output_vat_accounts") or []) if r.account), None
		) or frappe.get_all(
			"Account",
			filters={
				"company": cls.company,
				"account_type": "Tax",
				"root_type": "Liability",
				"is_group": 0,
			},
			pluck="name",
		)[0]
		settings.set("output_vat_accounts", [{"account": cls.vat_account}])

		# Any ordinary expense account will do, but it must not be a Payable or
		# Receivable one: ERPNext demands a party against those, and a sales
		# invoice charging freight to Hutang Usaha fails with "Supplier is
		# required" long before the export is reached.
		cls.freight_account = frappe.get_all(
			"Account",
			filters={
				"company": cls.company,
				"is_group": 0,
				"root_type": "Expense",
				"account_type": ["not in", ["Payable", "Receivable"]],
			},
			pluck="name",
			order_by="name",
		)[0]
		settings.set(
			"taxable_charge_mappings",
			[
				{
					"account": cls.freight_account,
					"barang_jasa": "B - Jasa",
					"goods_code": "000000",
					"coretax_unit": PREFIX + "UM.0018",
					"description": "Ongkos Kirim",
				}
			],
		)
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)

	@classmethod
	def _seed_units(cls):
		for code, uom in ((PREFIX + "UM.0018", "Unit"), (PREFIX + "UM.0021", "Pcs")):
			if not frappe.db.exists("Coretax Unit", code):
				frappe.get_doc(
					{"doctype": "Coretax Unit", "code": code, "unit_name": uom, "uom": uom}
				).insert(ignore_permissions=True)
		# "Nos" is deliberately left unmapped: an item on an unmapped UOM is the
		# commonest reason a real export stalls, and something has to prove the
		# gate catches it.
		frappe.db.delete("Coretax Unit", {"uom": "Nos"})

	@classmethod
	def _seed_items(cls):
		group = frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name")[0]
		cls.goods = cls._item("goods", group, is_stock=1, uom="Unit", goods_code="123456")
		cls.service = cls._item("service", group, is_stock=0, uom="Unit", barang_jasa="B - Jasa")
		# No goods code, no explicit unit -- resolves by UOM, falls back to 000000.
		cls.plain = cls._item("plain", group, is_stock=1, uom="Pcs")
		# UOM that no Coretax Unit maps to.
		cls.unmapped = cls._item("unmapped", group, is_stock=0, uom="Nos")

	@classmethod
	def _item(cls, key, group, *, is_stock, uom, goods_code=None, barang_jasa=None):
		code = PREFIX + key
		if frappe.db.exists("Item", code):
			return code
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": "CT %s" % key,
				"item_group": group,
				"stock_uom": uom,
				"is_stock_item": is_stock,
				"is_purchase_item": 0,
				"eil_goods_code": goods_code,
				"eil_barang_jasa": barang_jasa,
			}
		).insert(ignore_permissions=True)
		return code

	@classmethod
	def _seed_customers(cls):
		ordinary = frappe.get_all(
			"Customer Group", filters={"is_group": 0, "name": ["!=", "Government"]}, pluck="name"
		)[0]
		territory = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name")[0]
		cls.customer_group = ordinary
		cls.territory = territory
		cls.addresses = {}

		cls.buyer = cls._customer("buyer", ordinary, tax_id=BUYER_NPWP_TYPED, id_type="TIN")
		cls.buyer_no_npwp = cls._customer("nonpwp", ordinary, tax_id=None, id_type="TIN")
		cls.buyer_passport = cls._customer(
			"passport", ordinary, tax_id=None, id_type="Passport", document_number="X1234567"
		)
		cls.buyer_nitku = cls._customer(
			"nitku", ordinary, tax_id=BUYER_NPWP_TYPED, id_type="TIN", nitku="098765432109001"
		)
		govt = frappe.db.exists("Customer Group", "Government")
		cls.buyer_govt = (
			cls._customer("govt", "Government", tax_id=BUYER_NPWP_TYPED, id_type="TIN") if govt else None
		)

	@classmethod
	def _customer(cls, key, group, *, tax_id, id_type, document_number=None, nitku=None):
		name = PREFIX + key
		if frappe.db.exists("Customer", name):
			return name
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": group,
				"territory": cls.territory,
				"tax_id": tax_id,
				"eil_id_type": id_type,
				"eil_document_number": document_number,
				"eil_nitku": nitku,
				"eil_country_code": "IDN",
			}
		).insert(ignore_permissions=True)
		# customer_address is mandatory on Sales Invoice here, and the faktur
		# carries the address anyway.
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": name,
				"address_type": "Billing",
				"address_line1": "Jl. Uji Coba No. 1",
				"city": "Jakarta",
				"country": "Indonesia",
				"links": [{"link_doctype": "Customer", "link_name": name}],
			}
		).insert(ignore_permissions=True)
		cls.addresses[name] = address.name
		return name

	@classmethod
	def _seed_templates(cls):
		"""Two selling templates: PPN on the items alone, and PPN on the items
		plus a freight charge — the shape that puts a charge inside the DPP."""
		cls.template_ppn = cls._template(
			"ppn",
			[{"charge_type": "On Net Total", "account_head": cls.vat_account, "rate": 11, "description": "PPN 11%"}],
		)
		cls.template_freight = cls._template(
			"freight",
			[
				{
					"charge_type": "Actual",
					"account_head": cls.freight_account,
					"rate": 0,
					"tax_amount": 500000,
					"description": "Ongkos Kirim",
				},
				{
					"charge_type": "On Previous Row Total",
					"row_id": 1,
					"account_head": cls.vat_account,
					"rate": 11,
					"description": "PPN 11%",
				},
			],
		)

	@classmethod
	def _template(cls, key, taxes):
		name = "%s%s - %s" % (PREFIX, key, cls.abbr)
		if frappe.db.exists("Sales Taxes and Charges Template", name):
			return name
		doc = frappe.get_doc(
			{
				"doctype": "Sales Taxes and Charges Template",
				"title": PREFIX + key,
				"company": cls.company,
				"taxes": taxes,
			}
		).insert(ignore_permissions=True)
		return doc.name

	# -------------------------------------------------------------- helpers
	def setUp(self):
		super().setUp()
		self._files = []
		self.addCleanup(self._forget_files)

	def _forget_files(self):
		"""Rollback restores the database but not the filesystem."""
		for path in self._files:
			try:
				os.remove(path)
			except OSError:
				pass

	def _invoice(
		self,
		lines,
		*,
		customer=None,
		template=None,
		posting_date=POSTING,
		currency="IDR",
		submit=True,
		discount_amount=0,
		**kw,
	):
		customer = customer or self.buyer
		doc = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": self.company,
				"customer": customer,
				"customer_address": self.addresses.get(customer),
				"posting_date": posting_date,
				"set_posting_time": 1,
				"due_date": posting_date,
				"currency": currency,
				"conversion_rate": 1 if currency == "IDR" else 16000,
				"update_stock": 0,
				"taxes_and_charges": template,
				"discount_amount": discount_amount,
				"items": [
					{
						"item_code": code,
						"qty": qty,
						"rate": rate,
						"uom": uom,
						"conversion_factor": 1,
						"income_account": self.income_account,
						"cost_center": self.cost_center,
					}
					for code, qty, rate, uom in lines
				],
				**kw,
			}
		)
		if template:
			from erpnext.controllers.accounts_controller import get_taxes_and_charges

			for row in get_taxes_and_charges("Sales Taxes and Charges Template", template):
				doc.append("taxes", row)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		if submit:
			doc.submit()
		return doc.reload() or doc

	def _export(self, from_date=PERIOD[0], to_date=PERIOD[1]):
		doc = frappe.get_doc(
			{
				"doctype": "Coretax Faktur Export",
				"company": self.company,
				"from_date": from_date,
				"to_date": to_date,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		return doc

	def _fetch(self, export=None):
		"""Fetch, and return the rows keyed by invoice so a test can name one."""
		export = export or self._export()
		export.fetch_invoices()
		return export, {r.sales_invoice: r for r in export.invoices}

	def _row_for(self, invoice_name, export=None):
		export, rows = self._fetch(export)
		self.assertIn(invoice_name, rows, "the export did not pick the invoice up at all")
		return export, rows[invoice_name]

	def _only_mine(self, export, keep):
		"""Drop every row except the invoices a test made.

		The period is shared with whatever the site already has, and generate()
		stamps every valid row it finds."""
		keep = set(keep)
		export.set("invoices", [r for r in export.invoices if r.sales_invoice in keep])
		return export

	def _lines(self, si):
		settings = frappe.get_single("Indonesia Tax Settings")
		return self._export()._faktur_lines(si, settings)

	def _workbook(self, export):
		import openpyxl

		result = export.generate()
		file_doc = frappe.get_doc("File", {"file_url": result["file_url"]})
		path = file_doc.get_full_path()
		self._files.append(path)
		return openpyxl.load_workbook(path), result

	def _xml(self, export):
		result = export.generate_xml()
		file_doc = frappe.get_doc("File", {"file_url": result["file_url"]})
		path = file_doc.get_full_path()
		self._files.append(path)
		with open(path, "rb") as fh:
			return ET.fromstring(fh.read()), result


# ===========================================================================
# The arithmetic
# ===========================================================================
class TestFakturArithmetic(_ExportCase):
	def test_dpp_nilai_lain_reconciles_with_an_11_percent_template(self):
		"""The figures from VBS26070008-1, the one live invoice whose faktur PPN
		already agrees with what it charged.

		The invoice charges a flat 11% of the base. The faktur reports 12% of
		11/12 of the base. Those are the same number by construction, and this is
		the test that notices if either side is changed alone."""
		si = self._invoice([(self.goods, 1, 1_170_000_000, "Unit")], template=self.template_ppn)
		(line,) = self._lines(si)

		self.assertEqual(line["dpp"], 1_170_000_000.0)
		self.assertEqual(line["dpp_lain"], 1_072_500_000.0)
		self.assertEqual(line["tarif"], 12.0)
		self.assertEqual(line["ppn"], 128_700_000.0)

		charged = flt(sum(t.tax_amount for t in si.taxes), 2)
		self.assertEqual(charged, 128_700_000.0)
		self.assertEqual(line["ppn"], charged, "the faktur and the invoice disagree on the PPN")

	def test_without_dpp_nilai_lain_the_full_rate_applies_to_the_full_base(self):
		"""The luxury-goods path: no 11/12 haircut, 12% on the whole DPP."""
		settings = frappe.get_single("Indonesia Tax Settings")
		settings.use_dpp_nilai_lain = 0
		settings.save(ignore_permissions=True)
		self.addCleanup(self._restore_nilai_lain)

		si = self._invoice([(self.goods, 1, 100_000_000, "Unit")], template=self.template_ppn)
		(line,) = self._lines(si)
		self.assertEqual(line["dpp_lain"], 100_000_000.0)
		self.assertEqual(line["ppn"], 12_000_000.0)

	def _restore_nilai_lain(self):
		settings = frappe.get_single("Indonesia Tax Settings")
		settings.use_dpp_nilai_lain = 1
		settings.save(ignore_permissions=True)

	def test_every_line_satisfies_coretax_s_dpp_identity(self):
		"""Coretax rejects an upload where DPP != Harga Satuan x Jumlah - Diskon.

		A quantity that does not divide the discounted amount cleanly leaves a
		unit price that cannot be stated in two decimals, and the residual has to
		go somewhere. Nothing on the live site has a fractional unit price, so
		this had never been exercised — the export would have been rejected the
		first time an invoice carried an invoice-level discount."""
		si = self._invoice(
			[(self.goods, 3, 10_000_000, "Unit")],
			template=self.template_ppn,
			apply_discount_on="Net Total",
			discount_amount=10_000,
		)
		for line in self._lines(si):
			self.assertEqual(
				flt(line["price"] * line["qty"] - line["discount"], 2),
				line["dpp"],
				"DPP must equal price x qty - discount, or Coretax rejects the line",
			)

	def test_the_identity_holds_for_a_clean_division_too(self):
		"""The control: where the arithmetic already closes, nothing is invented
		— no phantom discount on a line that has none."""
		si = self._invoice([(self.goods, 4, 2_500_000, "Unit")], template=self.template_ppn)
		(line,) = self._lines(si)
		self.assertEqual(line["discount"], 0)
		self.assertEqual(line["price"], 2_500_000.0)
		self.assertEqual(line["dpp"], 10_000_000.0)

	def test_the_residual_is_never_a_negative_discount(self):
		"""DJP has no meaning for a negative Total Diskon, so the unit price is
		rounded away from zero and the remainder is always something to take off.
		Several awkward quantities, because which way the division falls is the
		whole question."""
		for qty, rate in ((3, 10_000_000), (7, 1_000_000), (6, 333_333), (9, 111_111)):
			si = self._invoice(
				[(self.goods, qty, rate, "Unit")], template=self.template_ppn, apply_discount_on="Net Total", discount_amount=7_777
			)
			for line in self._lines(si):
				self.assertGreaterEqual(line["discount"], 0, "qty=%s rate=%s" % (qty, rate))
				self.assertEqual(flt(line["price"] * line["qty"] - line["discount"], 2), line["dpp"])

	def test_a_zero_quantity_line_does_not_divide_by_it(self):
		"""Not reachable through the UI, but the arithmetic must not be what
		stops an export."""
		from erpbio_indonesia_localization.erpbio_indonesia_localization.doctype.coretax_faktur_export.coretax_faktur_export import (
			_price_and_discount,
		)

		self.assertEqual(_price_and_discount(0, 0, 1234.0), (1234.0, 0))

	def test_line_ppn_sums_to_the_invoice_ppn_across_many_lines(self):
		"""Per-line rounding, summed. Rounding each line then adding is not the
		same as taxing the total, and DJP takes the per-line figures."""
		si = self._invoice(
			[
				(self.goods, 3, 333_333, "Unit"),
				(self.service, 7, 111_111, "Unit"),
				(self.plain, 1, 999_999, "Pcs"),
			],
			template=self.template_ppn,
		)
		lines = self._lines(si)
		self.assertEqual(len(lines), 3)
		faktur_ppn = flt(sum(l["ppn"] for l in lines), 2)
		charged = flt(sum(t.tax_amount for t in si.taxes), 2)
		self.assertLessEqual(
			abs(faktur_ppn - charged), 1, "per-line rounding drifted more than a rupiah from the invoice"
		)


# ===========================================================================
# Charges that sit inside the DPP
# ===========================================================================
class TestTaxableCharges(_ExportCase):
	def test_a_taxed_freight_charge_becomes_its_own_faktur_line(self):
		"""It is part of the base but is not an item, and it cannot be folded
		into an item's DPP without inventing that item's unit price."""
		si = self._invoice([(self.goods, 1, 10_000_000, "Unit")], template=self.template_freight)
		lines = self._lines(si)
		self.assertEqual(len(lines), 2, "expected the item plus a line for the freight charge")

		freight = lines[-1]
		self.assertEqual(freight["dpp"], 500_000.0)
		self.assertEqual(freight["qty"], 1.0)
		self.assertEqual(freight["price"], 500_000.0)
		self.assertEqual(freight["opt"], "B")
		self.assertEqual(freight["unit"], PREFIX + "UM.0018")

	def test_the_charge_line_is_what_makes_the_totals_reconcile(self):
		"""Drop the freight line and the faktur under-reports the PPN by the tax
		on the freight — which is the failure this whole mechanism exists for."""
		si = self._invoice([(self.goods, 1, 10_000_000, "Unit")], template=self.template_freight)
		lines = self._lines(si)
		charged = flt(sum(t.tax_amount for t in si.taxes if t.account_head == self.vat_account), 2)

		with_charge = flt(sum(l["ppn"] for l in lines), 2)
		items_only = flt(sum(l["ppn"] for l in lines[:-1]), 2)
		self.assertLessEqual(abs(with_charge - charged), 1)
		self.assertGreater(charged - items_only, 1, "the freight tax should be missing without the line")

	def test_an_unmapped_taxed_charge_blocks_the_invoice(self):
		"""Better a blocked invoice than a faktur that quietly reports less
		output tax than the invoice charged."""
		settings = frappe.get_single("Indonesia Tax Settings")
		settings.set("taxable_charge_mappings", [])
		settings.save(ignore_permissions=True)
		self.addCleanup(self._restore_mappings)

		si = self._invoice([(self.goods, 1, 10_000_000, "Unit")], template=self.template_freight)
		_, row = self._row_for(si.name)
		self.assertFalse(row.ok)
		self.assertIn("Taxable Charge Mapping", row.message)

	def _restore_mappings(self):
		settings = frappe.get_single("Indonesia Tax Settings")
		settings.set(
			"taxable_charge_mappings",
			[
				{
					"account": self.freight_account,
					"barang_jasa": "B - Jasa",
					"goods_code": "000000",
					"coretax_unit": PREFIX + "UM.0018",
					"description": "Ongkos Kirim",
				}
			],
		)
		settings.save(ignore_permissions=True)


# ===========================================================================
# Validation gates
# ===========================================================================
class TestValidationGates(_ExportCase):
	def test_a_clean_invoice_passes(self):
		"""The control. Without it every "is blocked" assertion below would pass
		just as well if the validator rejected everything."""
		si = self._invoice([(self.goods, 2, 5_000_000, "Unit")], template=self.template_ppn)
		_, row = self._row_for(si.name)
		self.assertTrue(row.ok, row.message)
		self.assertEqual(row.kode_transaksi, "01")

	def test_a_buyer_without_an_npwp_is_blocked(self):
		si = self._invoice(
			[(self.goods, 1, 1_000_000, "Unit")], customer=self.buyer_no_npwp, template=self.template_ppn
		)
		_, row = self._row_for(si.name)
		self.assertFalse(row.ok)
		self.assertIn("NPWP/NIK", row.message)

	def test_a_passport_buyer_needs_no_npwp(self):
		"""A foreign buyer has no NPWP to give, and demanding one would make
		export sales unfileable."""
		si = self._invoice(
			[(self.goods, 1, 1_000_000, "Unit")], customer=self.buyer_passport, template=self.template_ppn
		)
		_, row = self._row_for(si.name)
		self.assertTrue(row.ok, row.message)

	def test_a_foreign_currency_invoice_is_blocked(self):
		"""Coretax takes rupiah. A USD invoice would otherwise be filed with its
		foreign-currency figures read as rupiah."""
		si = self._invoice(
			[(self.goods, 1, 1_000, "Unit")], template=self.template_ppn, currency="USD", submit=True
		)
		_, row = self._row_for(si.name)
		self.assertFalse(row.ok)
		self.assertIn("only IDR", row.message)

	def test_an_item_on_an_unmapped_uom_is_blocked(self):
		"""DJP will not take a blank Nama Satuan Ukur."""
		si = self._invoice([(self.unmapped, 1, 1_000_000, "Nos")], template=self.template_ppn)
		_, row = self._row_for(si.name)
		self.assertFalse(row.ok)
		self.assertIn("Coretax Unit", row.message)

	def test_an_already_exported_invoice_is_not_offered_again(self):
		"""Filing the same faktur twice is a correction case, not a re-run."""
		si = self._invoice([(self.goods, 1, 1_000_000, "Unit")], template=self.template_ppn)
		frappe.db.set_value("Sales Invoice", si.name, "eil_faktur_status", "Exported")
		_, row = self._row_for(si.name)
		self.assertFalse(row.ok)
		self.assertIn("already", row.message)

	def test_an_excluded_invoice_is_not_fetched_at_all(self):
		"""eil_exclude is the accountant's override; it must drop the invoice
		rather than merely mark it invalid."""
		si = self._invoice([(self.goods, 1, 1_000_000, "Unit")], template=self.template_ppn)
		frappe.db.set_value("Sales Invoice", si.name, "eil_exclude", 1)
		_, rows = self._fetch()
		self.assertNotIn(si.name, rows)

	def test_a_credit_note_is_not_fetched(self):
		"""A return is a Nota Retur in Coretax, not a faktur."""
		si = self._invoice([(self.goods, 1, 1_000_000, "Unit")], template=self.template_ppn)
		doc = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": self.company,
				"customer": self.buyer,
				"posting_date": POSTING,
				"set_posting_time": 1,
				"is_return": 1,
				"return_against": si.name,
				"currency": "IDR",
				"conversion_rate": 1,
				"update_stock": 0,
				"items": [
					{
						"item_code": self.goods,
						"qty": -1,
						"rate": 1_000_000,
						"uom": "Unit",
						"conversion_factor": 1,
						"income_account": self.income_account,
						"cost_center": self.cost_center,
						"sales_invoice_item": si.items[0].name,
					}
				],
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		doc.submit()
		_, rows = self._fetch()
		self.assertNotIn(doc.name, rows)

	def test_an_invoice_outside_the_period_is_not_fetched(self):
		si = self._invoice(
			[(self.goods, 1, 1_000_000, "Unit")], template=self.template_ppn, posting_date="2026-02-15"
		)
		_, rows = self._fetch()
		self.assertNotIn(si.name, rows)

	def test_an_invoice_with_no_transaction_code_anywhere_is_blocked(self):
		"""Kode Transaksi says what kind of sale it is — 01 ordinary, 02/03
		government, 07/08 exempt. There is no neutral value, so a blank one
		cannot be defaulted at the point of writing the file; it has to stop the
		invoice here."""
		settings = frappe.get_single("Indonesia Tax Settings")
		settings.default_transaction_code = ""
		settings.save(ignore_permissions=True)
		self.addCleanup(self._restore_transaction_code)

		si = self._invoice([(self.goods, 1, 1_000_000, "Unit")], template=self.template_ppn)
		_, row = self._row_for(si.name)
		self.assertFalse(row.ok)
		self.assertIn("transaction code", row.message)

	def _restore_transaction_code(self):
		settings = frappe.get_single("Indonesia Tax Settings")
		settings.default_transaction_code = "01"
		settings.save(ignore_permissions=True)

	def test_an_invoice_s_own_transaction_code_beats_the_default(self):
		"""A government sale filed as 01 is the wrong kind of faktur, so the
		per-invoice value has to win."""
		si = self._invoice([(self.goods, 1, 1_000_000, "Unit")], template=self.template_ppn)
		frappe.db.set_value("Sales Invoice", si.name, "eil_kode_transaksi", "02")
		_, row = self._row_for(si.name)
		self.assertEqual(row.kode_transaksi, "02")

	def test_a_grand_total_discount_is_blocked_because_the_invoice_taxes_the_wrong_base(self):
		"""ERPNext's default, `Apply Discount On: Grand Total`, computes the PPN
		on the full net total and only then takes the discount off the grand
		total. The invoice therefore charges 11% of a base it did not sell at:
		on 3 x 10,000,000 less 10,000 the buyer is billed Rp 3,300,000 of PPN
		while the lines come to a DPP of 29,990,990.99, whose PPN is
		Rp 3,299,009.01.

		Filing that faktur would over-declare output tax and disagree with the
		invoice the buyer holds. Discounting on Net Total moves the base and the
		two agree again — which is what the rest of the discount tests use."""
		si = self._invoice(
			[(self.goods, 3, 10_000_000, "Unit")],
			template=self.template_ppn,
			apply_discount_on="Grand Total",
			discount_amount=10_000,
		)
		_, row = self._row_for(si.name)
		self.assertFalse(row.ok)
		self.assertIn("does not match", row.message)

	def test_a_faktur_that_reports_more_ppn_than_the_invoice_charged_is_blocked(self):
		"""An invoice with no PPN at all would still produce a faktur claiming
		12% of 11/12 of the base. VBS26070009 on the live site is exactly this.

		Over-reporting is caught for the same reason as under-reporting: the
		faktur has to be the invoice."""
		si = self._invoice([(self.goods, 1, 15_000_000, "Unit")])  # no tax template
		_, row = self._row_for(si.name)
		self.assertFalse(row.ok)
		self.assertIn("does not match", row.message)

	def test_the_seller_npwp_is_refreshed_before_the_invoices_are_judged(self):
		"""Fetch used to validate against the NPWP the export was created with
		and only then reload it, so filling in a missing company NPWP and
		clicking Fetch reported the same "NPWP is empty" against every invoice.

		The live company has no NPWP today, so this is the first thing anyone
		using the feature would hit."""
		self.addCleanup(
			frappe.db.set_value, "Company", self.company, "tax_id", SELLER_NPWP_TYPED, update_modified=False
		)
		si = self._invoice([(self.goods, 1, 1_000_000, "Unit")], template=self.template_ppn)

		# The state the live site is in: no company NPWP, so the export is
		# created carrying an empty one.
		frappe.db.set_value("Company", self.company, "tax_id", "", update_modified=False)
		export = self._export()
		export.fetch_invoices()
		row = {r.sales_invoice: r for r in export.invoices}[si.name]
		self.assertFalse(row.ok)
		self.assertIn("NPWP", row.message)

		# The accountant does what the message asks and fetches again. The same
		# export must notice, or the advice is unfollowable.
		frappe.db.set_value("Company", self.company, "tax_id", SELLER_NPWP_TYPED, update_modified=False)
		export.fetch_invoices()
		row = {r.sales_invoice: r for r in export.invoices}[si.name]
		self.assertTrue(row.ok, "Fetch judged the invoices against a stale company NPWP: %s" % row.message)

	def test_generate_refuses_when_nothing_is_valid(self):
		"""Silence would leave an empty workbook looking like a filed period."""
		si = self._invoice(
			[(self.goods, 1, 1_000_000, "Unit")], customer=self.buyer_no_npwp, template=self.template_ppn
		)
		export, _ = self._fetch()
		self._only_mine(export, [si.name])
		self.assertRaises(frappe.ValidationError, export.generate)

	def test_from_date_after_to_date_is_refused(self):
		self.assertRaises(frappe.ValidationError, self._export, PERIOD[1], PERIOD[0])


# ===========================================================================
# Buyer identity
# ===========================================================================
class TestBuyerIdentity(_ExportCase):
	def test_punctuation_is_stripped_from_both_npwps(self):
		"""People type an NPWP with dots and a dash. DJP takes digits."""
		si = self._invoice([(self.goods, 1, 1_000_000, "Unit")], template=self.template_ppn)
		export = self._export()
		bits = export._buyer_bits(si)
		self.assertEqual(bits["npwp"], BUYER_NPWP)
		self.assertEqual(export.npwp_penjual, SELLER_NPWP)

	def test_idtku_defaults_to_the_npwp_with_a_branch_suffix(self):
		"""000000 is the head-office branch. It is only a sane default because
		an NPWP is present — see the next test."""
		si = self._invoice([(self.goods, 1, 1_000_000, "Unit")], template=self.template_ppn)
		bits = self._export()._buyer_bits(si)
		self.assertEqual(bits["idtku"], BUYER_NPWP + "000000")

	def test_a_buyer_without_an_npwp_gets_no_idtku_rather_than_a_bare_suffix(self):
		"""Concatenating the suffix onto an empty NPWP would send DJP the literal
		string 000000 as a tax identity."""
		si = self._invoice(
			[(self.goods, 1, 1_000_000, "Unit")], customer=self.buyer_passport, template=self.template_ppn
		)
		bits = self._export()._buyer_bits(si)
		self.assertEqual(bits["idtku"], "")

	def test_an_explicit_nitku_wins_over_the_default(self):
		"""A branch that files under its own NITKU must not be reported as head
		office."""
		si = self._invoice(
			[(self.goods, 1, 1_000_000, "Unit")], customer=self.buyer_nitku, template=self.template_ppn
		)
		bits = self._export()._buyer_bits(si)
		self.assertEqual(bits["idtku"], "098765432109001")

	def test_the_seller_idtku_is_never_a_bare_branch_suffix(self):
		"""The live company has no NPWP, which would make the seller's own tax
		identity the string 000000."""
		frappe.db.set_value("Company", self.company, "tax_id", "", update_modified=False)
		self.addCleanup(
			frappe.db.set_value, "Company", self.company, "tax_id", SELLER_NPWP_TYPED, update_modified=False
		)
		export = self._export()
		self.assertNotEqual(export._seller_idtku(), "000000")


# ===========================================================================
# Item classification
# ===========================================================================
class TestItemClassification(_ExportCase):
	def test_a_stock_item_is_barang_and_a_service_is_jasa(self):
		"""Opt is A or B, and getting it wrong misclassifies the sale."""
		si = self._invoice(
			[(self.goods, 1, 1_000_000, "Unit"), (self.service, 1, 1_000_000, "Unit")],
			template=self.template_ppn,
		)
		goods_line, service_line = self._lines(si)
		self.assertEqual(goods_line["opt"], "A")
		self.assertEqual(service_line["opt"], "B")

	def test_an_explicit_goods_code_is_used_and_the_default_is_000000(self):
		si = self._invoice(
			[(self.goods, 1, 1_000_000, "Unit"), (self.plain, 1, 1_000_000, "Pcs")],
			template=self.template_ppn,
		)
		coded, uncoded = self._lines(si)
		self.assertEqual(coded["code"], "123456")
		self.assertEqual(uncoded["code"], "000000")

	def test_a_unit_resolves_from_the_row_uom(self):
		si = self._invoice([(self.plain, 1, 1_000_000, "Pcs")], template=self.template_ppn)
		(line,) = self._lines(si)
		self.assertEqual(line["unit"], PREFIX + "UM.0021")


# ===========================================================================
# The file DJP actually reads
# ===========================================================================
class TestWorkbookShape(_ExportCase):
	def _generate(self):
		si = self._invoice(
			[(self.goods, 2, 5_000_000, "Unit"), (self.service, 1, 3_000_000, "Unit")],
			template=self.template_ppn,
		)
		other = self._invoice([(self.plain, 1, 7_000_000, "Pcs")], template=self.template_ppn)
		export, _ = self._fetch()
		self._only_mine(export, [si.name, other.name])
		return si, other, export

	def test_the_workbook_has_the_two_sheets_the_converter_expects(self):
		_, _, export = self._generate()
		wb, _ = self._workbook(export)
		self.assertEqual(wb.sheetnames, ["Faktur", "DetailFaktur"])

	def test_the_headers_are_the_published_ones_in_order(self):
		"""DJP's converter reads by position. A reordered column is a silently
		wrong file, not an error."""
		_, _, export = self._generate()
		wb, _ = self._workbook(export)
		faktur = wb["Faktur"]
		self.assertEqual([c.value for c in faktur[1]][:2], ["NPWP Penjual", SELLER_NPWP])
		self.assertEqual([c.value for c in faktur[3]], FAKTUR_HEADERS)
		self.assertEqual([c.value for c in wb["DetailFaktur"][1]], DETAIL_HEADERS)

	def test_both_sheets_end_with_the_marker_the_converter_stops_at(self):
		"""Without END the converter reads past the data."""
		_, _, export = self._generate()
		wb, _ = self._workbook(export)
		for sheet in ("Faktur", "DetailFaktur"):
			self.assertEqual(wb[sheet].cell(row=wb[sheet].max_row, column=1).value, "END")

	def test_baris_ties_each_detail_line_to_its_invoice(self):
		"""The only link between the sheets. If it drifts, lines are filed
		against the wrong buyer."""
		si, other, export = self._generate()
		wb, result = self._workbook(export)
		self.assertEqual(result["invoices"], 2)

		faktur = wb["Faktur"]
		ref_col = FAKTUR_HEADERS.index("Referensi")
		by_baris = {}
		for row in faktur.iter_rows(min_row=4, values_only=True):
			if row[0] == "END":
				break
			by_baris[row[0]] = row[ref_col]
		self.assertEqual(set(by_baris.values()), {si.name, other.name})

		counts = {}
		for row in wb["DetailFaktur"].iter_rows(min_row=2, values_only=True):
			if row[0] == "END":
				break
			counts[row[0]] = counts.get(row[0], 0) + 1
		self.assertEqual({by_baris[b]: n for b, n in counts.items()}, {si.name: 2, other.name: 1})

	def test_a_discounted_line_keeps_the_identity_in_the_file_itself(self):
		"""End to end, in the cells DJP's converter reads. The computed figures
		agreeing is not the same as the workbook carrying them: Total Diskon has
		its own column, and writing a literal 0 there — which the XML path did —
		re-breaks the identity the moment the price is rounded."""
		si = self._invoice(
			[(self.goods, 3, 10_000_000, "Unit")], template=self.template_ppn, apply_discount_on="Net Total", discount_amount=10_000
		)
		export, rows = self._fetch()
		self.assertTrue(rows[si.name].ok, rows[si.name].message)
		self._only_mine(export, [si.name])
		wb, _ = self._workbook(export)

		price_col = DETAIL_HEADERS.index("Harga Satuan")
		qty_col = DETAIL_HEADERS.index("Jumlah Barang Jasa")
		disc_col = DETAIL_HEADERS.index("Total Diskon")
		dpp_col = DETAIL_HEADERS.index("DPP")

		seen = 0
		for row in wb["DetailFaktur"].iter_rows(min_row=2, values_only=True):
			if row[0] == "END":
				break
			seen += 1
			self.assertEqual(flt(row[price_col] * row[qty_col] - row[disc_col], 2), flt(row[dpp_col], 2))
		self.assertEqual(seen, 1)

	def test_the_xml_carries_the_discount_rather_than_a_literal_zero(self):
		si = self._invoice(
			[(self.goods, 3, 10_000_000, "Unit")], template=self.template_ppn, apply_discount_on="Net Total", discount_amount=10_000
		)
		export, rows = self._fetch()
		self.assertTrue(rows[si.name].ok, rows[si.name].message)
		self._only_mine(export, [si.name])
		root, _ = self._xml(export)
		good = root.find("ListOfTaxInvoice/TaxInvoice/ListOfGoodService/GoodService")
		price = flt(good.findtext("Price"))
		qty = flt(good.findtext("Qty"))
		discount = flt(good.findtext("TotalDiscount"))
		self.assertGreater(discount, 0, "this line needs a residual, or it proves nothing")
		self.assertEqual(flt(price * qty - discount, 2), flt(good.findtext("TaxBase")))

	def test_generating_stamps_the_invoices_exported(self):
		"""So the next period does not offer them again."""
		si, other, export = self._generate()
		self._workbook(export)
		for name in (si.name, other.name):
			self.assertEqual(frappe.db.get_value("Sales Invoice", name, "eil_faktur_status"), "Exported")


class TestXmlShape(_ExportCase):
	def _generate(self):
		si = self._invoice([(self.goods, 2, 5_000_000, "Unit")], template=self.template_ppn)
		export, _ = self._fetch()
		self._only_mine(export, [si.name])
		return si, export

	def test_the_document_is_a_taxinvoicebulk_carrying_the_seller_tin(self):
		_, export = self._generate()
		root, _ = self._xml(export)
		self.assertEqual(root.tag, "TaxInvoiceBulk")
		self.assertEqual(root.findtext("TIN"), SELLER_NPWP)

	def test_the_elements_are_in_the_schema_s_order(self):
		"""Including DJP's own misspelling of BuyerAdress: matching their schema
		matters more than spelling it correctly."""
		_, export = self._generate()
		root, _ = self._xml(export)
		invoice = root.find("ListOfTaxInvoice/TaxInvoice")
		self.assertEqual(
			[el.tag for el in invoice][:17],
			[
				"TaxInvoiceDate",
				"TaxInvoiceOpt",
				"TrxCode",
				"AddInfo",
				"CustomDoc",
				"RefDesc",
				"FacilityStamp",
				"SellerIDTKU",
				"BuyerTin",
				"BuyerDocument",
				"BuyerCountry",
				"BuyerDocumentNumber",
				"BuyerName",
				"BuyerAdress",
				"BuyerEmail",
				"BuyerIDTKU",
				"ListOfGoodService",
			],
		)

	def test_a_goods_line_carries_the_schema_s_fields_in_order(self):
		_, export = self._generate()
		root, _ = self._xml(export)
		good = root.find("ListOfTaxInvoice/TaxInvoice/ListOfGoodService/GoodService")
		self.assertEqual(
			[el.tag for el in good],
			[
				"Opt",
				"Code",
				"Name",
				"Unit",
				"Price",
				"Qty",
				"TotalDiscount",
				"TaxBase",
				"OtherTaxBase",
				"VATRate",
				"VAT",
				"STLGRate",
				"STLG",
			],
		)

	def test_amounts_are_plain_decimals(self):
		"""No thousands separators, no currency, no trailing zeros — the values
		are parsed, not read."""
		_, export = self._generate()
		root, _ = self._xml(export)
		good = root.find("ListOfTaxInvoice/TaxInvoice/ListOfGoodService/GoodService")
		self.assertEqual(good.findtext("Price"), "5000000")
		self.assertEqual(good.findtext("Qty"), "2")
		self.assertEqual(good.findtext("TaxBase"), "10000000")
		self.assertEqual(good.findtext("OtherTaxBase"), "9166666.67")
		self.assertEqual(good.findtext("VATRate"), "12")

	def test_the_reference_points_back_at_the_erp_invoice(self):
		"""The only way to trace a filed faktur to what it came from."""
		si, export = self._generate()
		root, _ = self._xml(export)
		self.assertEqual(root.findtext("ListOfTaxInvoice/TaxInvoice/RefDesc"), si.name)

	def test_the_html_address_is_flattened(self):
		"""address_display is HTML. Tags in the XML would be filed verbatim."""
		export = self._export()
		from erpbio_indonesia_localization.erpbio_indonesia_localization.doctype.coretax_faktur_export.coretax_faktur_export import (
			_strip_html,
		)

		self.assertEqual(_strip_html("Jl. Merdeka<br>Jakarta &amp; Co"), "Jl. Merdeka Jakarta & Co")

	def test_an_invoice_with_no_address_still_files(self):
		"""Coretax requires the element; an empty one is rejected."""
		_, export = self._generate()
		root, _ = self._xml(export)
		self.assertTrue(root.findtext("ListOfTaxInvoice/TaxInvoice/BuyerAdress"))
