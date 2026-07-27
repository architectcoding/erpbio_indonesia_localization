# Sales Invoice — WAPU/Bendahara (government-collected PPN) + government withholding.
#
# On a sale to a government treasurer the PPN is deposited by the government and
# PPh 22 is withheld, so neither is cash we collect from the customer — but the
# sale itself is still the full DPP, and the invoice we hand over still shows the
# PPN. The books therefore read (DPP 100,000,000; PPN 11%; PPh 22 1.5%):
#
#   Sales Invoice   Dr Piutang Usaha            100,000,000
#                       Cr Penjualan               100,000,000
#   Reclassification Dr Piutang PPN Bendahara     11,000,000
#                    Dr PPh 22 Dibayar di Muka     1,500,000
#                       Cr Piutang Usaha            12,500,000
#
# i.e. the receivable is booked at the genuine sale value and the two
# government-handled portions are carved out as their own, auditable entry. The
# invoice's outstanding lands at 87,500,000 because the entry references the
# invoice, so the receipt still closes it.
#
# Mechanics: the charges live in their OWN table (`eil_govt_charges`), not in
# `taxes`. Keeping them out of ERPNext's tax engine is what lets them carry a
# real rate and amount while leaving the invoice totals — and therefore the
# receivable — at the genuine sale value. Output VAT is never credited: the PPN
# is the government's obligation, and it reaches the SPT through the PPN Keluaran
# report (computed from DPP x tarif), not through the ledger.

import frappe
from frappe.utils import flt

PPN_TREATMENT = "PPN Dipungut Pemungut"


def _charges(doc):
	return doc.get("eil_govt_charges") or []


def before_validate(doc, method=None):
	"""Populate the charges from a template the first time, so the accountant has
	rows to adjust rather than a blank table."""
	if doc.get("is_return"):
		return
	# An invoice raised directly (no order to inherit from) still needs the fact.
	if not doc.get("eil_is_pemungut") and doc.get("customer"):
		from erpbio_indonesia_localization.doc_events.sales_order import is_pemungut_customer

		if is_pemungut_customer(doc.customer):
			doc.eil_is_pemungut = 1
	if not doc.get("eil_is_pemungut"):
		return
	if _charges(doc):
		return  # already populated (or deliberately emptied on an existing doc)
	template = doc.get("eil_govt_tax_template") or _default_template(doc)
	if not template:
		return
	doc.eil_govt_tax_template = template
	for row in frappe.get_all(
		"EIL Govt Tax Charge",
		filters={"parent": template, "parenttype": "EIL Govt Tax Template"},
		fields=["treatment", "account", "rate", "amount", "show_on_print", "clear_on_payment", "description"],
		order_by="idx asc",
	):
		doc.append("eil_govt_charges", row)


def _default_template(doc):
	"""The customer's own template, else the company default."""
	if doc.get("customer"):
		own = frappe.db.get_value("Customer", doc.customer, "eil_govt_tax_template")
		if own:
			return own
	return frappe.db.get_value(
		"EIL Govt Tax Template", {"company": doc.company, "is_default": 1, "disabled": 0}, "name"
	)


def validate(doc, method=None):
	"""Runs after the totals are computed, so base_net_total is final.

	A row with a rate is computed from the net total; a row with no rate keeps
	whatever amount was entered, which is how a one-off figure is overridden."""
	if doc.get("is_return"):
		return
	if not doc.get("eil_is_pemungut"):
		doc.set("eil_govt_charges", [])
		return
	for row in _charges(doc):
		if flt(row.rate):
			row.amount = flt(
				flt(doc.base_net_total) * flt(row.rate) / 100.0, doc.precision("base_net_total")
			)


def on_submit(doc, method=None):
	je = _build_reclassification(doc)
	if je:
		doc.db_set("eil_wapu_journal_entry", je, update_modified=False)


def on_cancel(doc, method=None):
	"""The reclassification only exists to qualify this invoice — it goes with it."""
	name = doc.get("eil_wapu_journal_entry")
	if not name or not frappe.db.exists("Journal Entry", name):
		return
	if frappe.db.get_value("Journal Entry", name, "docstatus") == 1:
		frappe.get_doc("Journal Entry", name).cancel()


def _build_reclassification(doc):
	rows = [r for r in _charges(doc) if flt(r.amount)]
	if not rows or doc.get("is_return"):
		return None

	total = flt(sum(flt(r.amount) for r in rows), doc.precision("base_net_total"))
	if not total:
		return None

	je = frappe.new_doc("Journal Entry")
	je.company = doc.company
	je.posting_date = doc.posting_date
	je.voucher_type = "Journal Entry"
	je.user_remark = frappe._("Government-collected tax on {0}").format(doc.name)
	for r in rows:
		je.append(
			"accounts",
			{
				"account": r.account,
				"debit_in_account_currency": flt(r.amount),
				"cost_center": r.get("cost_center") or doc.get("cost_center"),
			},
		)
	je.append(
		"accounts",
		{
			"account": doc.debit_to,
			"credit_in_account_currency": total,
			"party_type": "Customer",
			"party": doc.customer,
			# referencing the invoice is what drops its outstanding to the
			# amount the customer will actually pay
			"reference_type": "Sales Invoice",
			"reference_name": doc.name,
			"cost_center": doc.get("cost_center"),
		},
	)
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return je.name
