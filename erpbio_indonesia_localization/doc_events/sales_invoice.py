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
# government-handled portions are carved out as their own, auditable entry —
# rather than the invoice silently debiting a netted 87,500,000. The invoice's
# outstanding lands at 87,500,000 either way, because the entry references the
# invoice, so the receipt still closes it.
#
# Mechanics: a tax row tagged `eil_govt_tax_treatment` must not move the
# invoice's totals, so it is neutralised to an Actual charge of 0 and its
# percentage/amount are kept in eil_wapu_rate / eil_wapu_amount (ERPNext clears
# `rate` on an Actual row). Those fields drive both this entry and the faktur.
# Output VAT is never credited — the PPN is the government's obligation.

import frappe
from frappe.utils import flt

PPN_TREATMENT = "PPN Dipungut Pemungut"


def _tagged(doc):
	return [t for t in (doc.get("taxes") or []) if t.get("eil_govt_tax_treatment")]


def before_validate(doc, method=None):
	"""Neutralise tagged rows before the tax engine runs, preserving the rate."""
	for tax in _tagged(doc):
		rate = abs(flt(tax.get("eil_wapu_rate")) or flt(tax.rate))
		if rate:
			tax.eil_wapu_rate = rate
		tax.charge_type = "Actual"
		tax.rate = 0
		tax.tax_amount = 0


def validate(doc, method=None):
	"""Runs after the totals are computed, so base_net_total is final."""
	for tax in _tagged(doc):
		tax.eil_wapu_amount = flt(
			flt(doc.base_net_total) * flt(tax.eil_wapu_rate) / 100.0,
			doc.precision("base_net_total"),
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
	rows = [t for t in _tagged(doc) if flt(t.eil_wapu_amount)]
	if not rows or doc.get("is_return"):
		return None

	total = flt(sum(flt(t.eil_wapu_amount) for t in rows), doc.precision("base_net_total"))
	if not total:
		return None

	je = frappe.new_doc("Journal Entry")
	je.company = doc.company
	je.posting_date = doc.posting_date
	je.voucher_type = "Journal Entry"
	je.user_remark = frappe._("Government-collected tax on {0}").format(doc.name)
	for t in rows:
		je.append(
			"accounts",
			{
				"account": t.account_head,
				"debit_in_account_currency": flt(t.eil_wapu_amount),
				"cost_center": t.get("cost_center") or doc.get("cost_center"),
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
