# Sales Taxes and Charges Template — the government (pemungut/WAPU) variant.
#
# The government treatment lives on the same master the sales team already
# picks, so one template says both "charge PPN 12% to an ordinary buyer" and
# "for a government buyer, treat 12% as PPN dipungut instead". Keeping the pair
# together is the point: when they were separate masters, a rep quoting 12%
# could produce a faktur showing 11%, and nothing in the system noticed.

import frappe
from frappe.utils import flt

from erpbio_indonesia_localization.doc_events.sales_invoice import (
	PPN_TREATMENT,
	_output_vat_accounts,
	apply_treatment_rules,
)


def validate(doc, method=None):
	rows = doc.get("eil_govt_charges") or []
	if not rows:
		return
	for row in rows:
		apply_treatment_rules(row)
	_warn_on_rate_mismatch(doc, rows)


def _warn_on_rate_mismatch(doc, rows):
	"""The PPN a government buyer is charged should be the same rate an ordinary
	buyer is charged on this template. Warn rather than block: a template may
	legitimately exist for a rate transition, and refusing to save would be a
	poor trade for what is really an authoring slip."""
	ppn = next((r for r in rows if r.get("treatment") == PPN_TREATMENT and flt(r.rate)), None)
	if not ppn:
		return
	accounts = _output_vat_accounts(doc.get("company"))
	output_vat = next(
		(t for t in (doc.get("taxes") or []) if t.account_head in accounts and flt(t.rate)), None
	)
	if not output_vat or flt(output_vat.rate) == flt(ppn.rate):
		return
	frappe.msgprint(
		frappe._(
			"This template charges an ordinary buyer {0}% output VAT but treats a government buyer's PPN as {1}%. "
			"A customer quoted {0}% would receive a faktur showing {1}%."
		).format(flt(output_vat.rate), flt(ppn.rate)),
		title=frappe._("Government PPN rate differs"),
		indicator="orange",
	)
