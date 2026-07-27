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


def apply_treatment_rules(row):
	"""Whether a charge is settled by the receipt follows from WHAT it is, so
	derive it rather than leaving it as a checkbox someone must remember.

	The PPN the buyer collects arrives as part of the cash and clears the PPN
	receivable. A withholding does the opposite: the buyer keeps it, hands over a
	bukti potong, and we carry a prepaid-tax asset until it is credited on the SPT
	— clearing it at payment would silently destroy that asset and leave the
	receipt short by exactly the withheld amount."""
	row.clear_on_payment = 1 if row.get("treatment") == PPN_TREATMENT else 0
	return row


def before_validate(doc, method=None):
	"""Populate the charges from a template the first time, so the accountant has
	rows to adjust rather than a blank table."""
	if doc.get("is_return"):
		return
	_derive_pemungut(doc)
	if not doc.get("eil_is_pemungut"):
		return
	_strip_output_vat(doc)
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


def _output_vat_accounts(company):
	"""Accounts that represent PPN Keluaran, as configured — else detected.

	The explicit list in Indonesia Tax Settings wins. With nothing configured we
	fall back to the shape output VAT actually has in a chart of accounts: type
	"Tax" AND root type "Liability". That distinction is what protects the other
	rows people legitimately put in Taxes and Charges — freight/Ongkos Kirim and
	handling sit on Expense/Income accounts (or carry an "Expenses Included In
	Valuation" type), and PPN Masukan / Piutang PPN Bendaharawan are Tax accounts
	but root type Asset. Only output VAT is Tax + Liability."""
	settings = frappe.get_cached_doc("Indonesia Tax Settings")
	configured = {r.account for r in (settings.get("output_vat_accounts") or []) if r.account}
	if configured:
		return configured
	return set(
		frappe.get_all(
			"Account",
			filters={"company": company, "account_type": "Tax", "root_type": "Liability", "is_group": 0},
			pluck="name",
		)
	)


def _strip_output_vat(doc):
	"""Remove output-VAT rows from a government invoice.

	On a WAPU sale the buyer deposits the PPN itself, so charging it in `taxes`
	as well as carrying it in `eil_govt_charges` counts it twice: the invoice
	ends up with an output-VAT liability we do not owe, and the receipt can no
	longer be balanced (the payment hook expects net + PPN, but the bendahara
	only ever pays net). A sales rep picking their usual "PPN 11%" template on
	the order is the normal way this arrives, so fix it here rather than asking
	them to know. Anything that is not output VAT is left exactly as it was."""
	rows = doc.get("taxes") or []
	if not rows:
		return
	accounts = _output_vat_accounts(doc.company)
	if not accounts:
		return
	removed = [r for r in rows if r.account_head in accounts]
	if not removed:
		return
	doc.set("taxes", [r for r in rows if r.account_head not in accounts])
	for i, row in enumerate(doc.get("taxes") or [], start=1):
		row.idx = i
	frappe.msgprint(
		frappe._("Removed {0} from Taxes and Charges: this is a government (pemungut/WAPU) buyer, so the PPN is collected by the buyer and is shown under Government Tax instead.").format(
			", ".join(sorted({r.account_head for r in removed}))
		),
		title=frappe._("Government buyer"),
		indicator="orange",
	)


def _dpp_base(doc):
	"""The value actually billed, excluding output VAT — the base for PPN/PPh 22.

	Not `base_net_total`: other charges in Taxes and Charges (freight/Ongkos
	Kirim, packing) are part of what the buyer is billed and therefore part of
	the DPP. Output VAT has already been stripped by this point, so the grand
	total is exactly that value. `eil_govt_charges` never touch the totals, so
	this cannot feed on itself."""
	return flt(doc.base_grand_total) or flt(doc.base_net_total)


def _derive_pemungut(doc):
	"""Set the flag from the buyer only when there is no decision on record yet.

	An invoice raised directly (no order to inherit it from) still needs the fact,
	but an accountant who deliberately UNticks WAPU must have that stick: the
	stored field can't tell an unticked box from an untouched one, so re-deriving
	on every save would flip it back on — and rebuild the charges with it."""
	from erpbio_indonesia_localization.doc_events.sales_order import is_pemungut_customer

	if not doc.get("customer"):
		return
	if doc.is_new():
		if not doc.get("eil_is_pemungut") and is_pemungut_customer(doc.customer):
			doc.eil_is_pemungut = 1
		return
	# Existing invoice: the flag describes the previous buyer only if the customer
	# changed — otherwise leave whatever is there alone.
	if frappe.db.get_value("Sales Invoice", doc.name, "customer") == doc.customer:
		return
	doc.eil_is_pemungut = 1 if is_pemungut_customer(doc.customer) else 0


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
	"""Runs after the totals are computed, so the DPP base is final.

	A row with a rate is computed from the DPP; a row with no rate keeps whatever
	amount was entered, which is how a one-off figure is overridden."""
	if doc.get("is_return"):
		return
	if not doc.get("eil_is_pemungut"):
		doc.set("eil_govt_charges", [])
		return
	base = _dpp_base(doc)
	for row in _charges(doc):
		apply_treatment_rules(row)
		if flt(row.rate):
			row.amount = flt(base * flt(row.rate) / 100.0, doc.precision("base_net_total"))


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
