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
from frappe.utils import cint, flt

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
	for row in govt_rows_for(doc.get("taxes_and_charges"), doc.company):
		doc.append("eil_govt_charges", row)


def govt_rows_for(taxes_and_charges, company):
	"""The government charges to apply, in priority order.

	The selling template the sales team already picked owns them, so the PPN they
	quoted and the PPN on the faktur are the same number by construction. An
	invoice raised by hand has no template to inherit from, so it falls back to
	the per-company defaults in Indonesia Tax Settings — that path is what lets an
	accountant produce a WAPU invoice with no order behind it."""
	if taxes_and_charges:
		rows = frappe.get_all(
			"EIL Govt Tax Charge",
			filters={"parent": taxes_and_charges, "parenttype": "Sales Taxes and Charges Template"},
			fields=[
				"treatment",
				"account",
				"rate",
				"base",
				"show_on_print",
				"clear_on_payment",
				"description",
			],
			order_by="idx asc",
		)
		if rows:
			return rows
	settings = frappe.get_cached_doc("Indonesia Tax Settings")
	return [
		{
			"treatment": d.treatment,
			"account": d.account,
			"rate": d.rate,
			"description": d.description,
			"show_on_print": 1,
		}
		for d in (settings.get("govt_tax_defaults") or [])
		if d.account and (not d.get("company") or d.company == company)
	]


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


def restore_output_vat(doc):
	"""Put the output-VAT rows back when an invoice stops being a government sale.

	The strip is not symmetric on its own: a doctor from a government hospital
	buying in a personal capacity sits under a Government-group customer, so the
	invoice is flagged and its PPN removed — but that purchase is an ordinary
	sale and must carry PPN. Turning the government treatment off has to restore
	what the strip took, or the invoice quietly goes out with no tax at all.

	Only ever called on the deliberate WAPU-off transition, never from validate:
	an ordinary invoice whose PPN row was removed on purpose must stay that way."""
	if doc.docstatus != 0 or not doc.get("taxes_and_charges"):
		return []
	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	accounts = _output_vat_accounts(doc.company)
	present = {t.account_head for t in (doc.get("taxes") or [])}
	restored = []
	for row in get_taxes_and_charges("Sales Taxes and Charges Template", doc.taxes_and_charges):
		head = row.get("account_head")
		if head in accounts and head not in present:
			doc.append("taxes", row)
			restored.append(head)
	return restored


def _billed_base(doc):
	"""Everything the buyer is billed, excluding output VAT.

	Output VAT has already been stripped by this point, so the grand total is
	exactly that value. `eil_govt_charges` never touch the totals, so this cannot
	feed on itself."""
	return flt(doc.base_grand_total) or flt(doc.base_net_total)


def _vat_base(doc):
	"""The base the stripped output-VAT row would itself have used, or None.

	Whether a charge in Taxes and Charges is inside the DPP is not something we
	get to decide: freight is usually billed outside the PPN, sometimes inside,
	and the selling template the sales team picked already says which — a PPN row
	computed `On Net Total` taxes the items alone, one computed `On Previous Row
	Total` taxes the charges beneath it too. Reading that back gives the invariant
	worth having: the same sale is taxed on the same base whether the buyer is a
	government treasurer or not.

	The row itself is gone by the time this runs, so the answer comes from the
	template. `On Previous Row Total` points at a row that by definition sits
	ABOVE the VAT row and therefore survived the strip, and ERPNext has already
	accumulated exactly the base we want into that row's `base_total`."""
	inside = _template_inside_count(doc, _output_vat_accounts(doc.company))
	if inside is None:
		return None
	if inside <= 0:
		return flt(doc.base_net_total)
	surviving = doc.get("taxes") or []
	if not 1 <= inside <= len(surviving):
		return None
	return flt(surviving[inside - 1].base_total)


def taxable_charge_rows(doc):
	"""The Taxes and Charges rows that sit INSIDE the PPN base.

	They are part of the DPP but are not items, so the faktur needs a line for
	each — Coretax checks DPP = price x qty - discount per line, which no share
	folded into an item's DPP could satisfy. Derived here rather than in the
	export so the figure the invoice charges and the figure the faktur reports
	come from one decision.

	Government and ordinary invoices reach the same answer by different routes:
	the government one has had its PPN row removed, so it asks the charge row
	that replaced it; an ordinary one still has the row and is read directly."""
	rows = doc.get("taxes") or []
	if not rows:
		return []
	accounts = _output_vat_accounts(doc.company)

	if cint(doc.get("eil_is_pemungut")):
		ppn = next((r for r in _charges(doc) if r.get("treatment") == PPN_TREATMENT), None)
		base = (ppn.get("base") if ppn else None) or "Automatic"
		if base == "Net Total":
			return []
		if base == "Net Total + Charges":
			return [r for r in rows if r.account_head not in accounts]
		inside = _template_inside_count(doc, accounts)
	else:
		vat = next((r for r in rows if r.account_head in accounts), None)
		if not vat:
			return []
		if vat.charge_type == "On Net Total":
			inside = 0
		elif vat.charge_type == "On Previous Row Total":
			inside = cint(vat.row_id)
		else:
			inside = None

	charges = [r for r in rows if r.account_head not in accounts]
	if inside is None:
		# Same fallback as dpp_base_for: the whole billed value, so the faktur
		# reports every charge the base was widened by.
		return charges
	if inside <= 0:
		return []
	return [r for r in rows[:inside] if r.account_head not in accounts]


def _template_inside_count(doc, accounts):
	"""How many leading charge rows the template's PPN row taxes.

	0 = the items alone, n = the first n charge rows as well, None = the template
	does not say (no template, a hand-entered PPN, or a shape whose positions
	cannot be trusted). None is not 0: the callers fall back to the whole billed
	value rather than silently narrowing the base."""
	if not doc.get("taxes_and_charges"):
		return None
	tpl = frappe.get_all(
		"Sales Taxes and Charges",
		filters={"parent": doc.taxes_and_charges, "parenttype": "Sales Taxes and Charges Template"},
		fields=["idx", "charge_type", "row_id", "account_head"],
		order_by="idx asc",
	)
	vat = next((r for r in tpl if r.account_head in accounts), None)
	if not vat:
		return None
	if vat.charge_type == "On Net Total":
		return 0
	if vat.charge_type != "On Previous Row Total":
		return None
	idx = cint(vat.row_id)
	# Positional only holds while nothing below `idx` was stripped out.
	if any(r.account_head in accounts for r in tpl if r.idx <= idx):
		return None
	return idx


def dpp_base_for(doc, row=None):
	"""The base a government charge is computed on, from the charge row itself.

	The row states it because the tax table cannot always be trusted to: the PPN
	row is stripped from a government invoice, and an accountant who edits the
	remaining rows by hand leaves the picked template no longer describing the
	invoice. Stating it on the row that carries the tax removes the inference —
	and because this child table is used on the selling template as well as the
	invoice, the same field authors the default and overrides it per invoice.

	`Automatic` keeps the derivation: PPN follows the template's own PPN row,
	while a withholding takes the full billed amount — PPh 22 is taken on the
	purchase price the treasurer actually pays, which includes the freight and
	handling billed alongside the goods. Rows written before this field existed
	come back empty and are read as Automatic, so nothing changes under them."""
	base = (row.get("base") if row else None) or "Automatic"
	if base == "Net Total":
		return flt(doc.base_net_total)
	if base == "Net Total + Charges":
		return _billed_base(doc)
	if (row.get("treatment") if row else None) == PPN_TREATMENT:
		derived = _vat_base(doc)
		if derived is not None:
			return derived
	return _billed_base(doc)


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


def validate(doc, method=None):
	"""Runs after the totals are computed, so the DPP base is final.

	A row with a rate is computed from the DPP; a row with no rate keeps whatever
	amount was entered, which is how a one-off figure is overridden."""
	if doc.get("is_return"):
		return
	if not doc.get("eil_is_pemungut"):
		doc.set("eil_govt_charges", [])
		return
	for row in _charges(doc):
		apply_treatment_rules(row)
		if not flt(row.rate):
			continue  # a hand-entered figure from the bukti potong — leave it alone
		base = dpp_base_for(doc, row)
		row.amount = flt(base * flt(row.rate) / 100.0, doc.precision("base_net_total"))
		if not cint(row.clear_on_payment):
			# A withholding may already have been taken when an advance was paid:
			# the bendahara withholds when the money moves, which can be before
			# this invoice exists. Book only what is left, or it is counted twice.
			already = withheld_on_advances(doc, row.account)
			if already:
				row.amount = max(0.0, flt(row.amount) - already)


def withheld_on_advances(doc, account):
	"""How much of `account` the advances allocated to this invoice already took.

	Matched on the ACCOUNT rather than on any new configuration: a deduction that
	posted where this charge would post is the same tax by definition. Whether the
	bendahara withholds at the advance or leaves it to the invoice is their choice,
	so this has to be detected, never assumed."""
	if not account:
		return 0.0
	names = [
		a.reference_name
		for a in (doc.get("advances") or [])
		if a.get("reference_type") == "Payment Entry" and a.get("reference_name")
	]
	if not names:
		return 0.0
	return sum(
		flt(r.amount)
		for r in frappe.get_all(
			"Payment Entry Deduction",
			filters={"parent": ["in", names], "account": account},
			fields=["amount"],
		)
		if flt(r.amount) > 0
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


def _postable_rows(doc):
	"""[(row, amount)] to post, capped at what is still in the receivable.

	The entry carves the government-handled portions OUT of the receivable, so it
	can only ever move what the receivable still holds. An advance may already
	have settled most (or all) of the invoice, and then there is nothing left to
	carve — nor anything to carve it FOR: the cash is in, so no PPN claim is
	pending. Without the cap the entry simply fails, because it references the
	invoice and ERPNext refuses a reference larger than the outstanding amount.

	The withholding is taken first. It is genuinely uncollectible — the buyer
	keeps it — whereas the PPN receivable is a presentation of money still to
	arrive, so it is the part that should give way when room runs out."""
	if doc.get("is_return"):
		return []
	rows = [r for r in _charges(doc) if flt(r.amount)]
	if not rows:
		return []

	room = flt(frappe.db.get_value("Sales Invoice", doc.name, "outstanding_amount"))
	out = []
	for r in sorted(rows, key=lambda r: cint(r.clear_on_payment)):
		if room <= 0:
			break
		amount = min(flt(r.amount), room)
		if amount <= 0:
			continue
		out.append((r, flt(amount, doc.precision("base_net_total"))))
		room -= amount
	return out


def govt_notes(doc):
	"""Plain-language reasons the posted figures differ from the nominal rates.

	Both adjustments below are silent arithmetic otherwise: an accountant looking
	at a 0 where they expected 1,500,000 should be told why without having to
	reconstruct it from the advance."""
	notes = []
	fmt = frappe.format_value
	currency = {"fieldtype": "Currency", "options": "currency"}

	for row in _charges(doc):
		if cint(row.clear_on_payment) or not flt(row.rate):
			continue
		already = withheld_on_advances(doc, row.account)
		if already:
			notes.append(
				frappe._("{0}: {1} was already withheld on the advance, so this invoice books {2}.").format(
					row.description or row.treatment,
					fmt(already, currency),
					fmt(flt(row.amount), currency),
				)
			)

	# Only meaningful once posted. A FULLY capped invoice has no entry at all, so
	# an empty `posted` is the interesting case, not a reason to skip.
	if doc.docstatus == 1:
		posted = {}
		je = doc.get("eil_wapu_journal_entry")
		if je and frappe.db.get_value("Journal Entry", je, "docstatus") == 1:
			posted = {
				r.account: flt(r.debit_in_account_currency)
				for r in frappe.get_all(
					"Journal Entry Account",
					filters={"parent": je},
					fields=["account", "debit_in_account_currency"],
				)
			}
		for row in _charges(doc):
			if not cint(row.clear_on_payment):
				continue
			booked = posted.get(row.account, 0.0)
			if booked < flt(row.amount) - 0.5:
				notes.append(
					frappe._(
						"{0}: {1} of {2} carried to the receivable — an advance had already settled the rest of this invoice."
					).format(
						row.description or row.treatment,
						fmt(booked, currency),
						fmt(flt(row.amount), currency),
					)
				)
	return notes


def _build_reclassification(doc):
	rows = _postable_rows(doc)
	if not rows:
		return None

	total = flt(sum(amount for _r, amount in rows), doc.precision("base_net_total"))
	if not total:
		return None

	je = frappe.new_doc("Journal Entry")
	je.company = doc.company
	je.posting_date = doc.posting_date
	je.voucher_type = "Journal Entry"
	je.user_remark = frappe._("Government-collected tax on {0}").format(doc.name)
	for r, amount in rows:
		je.append(
			"accounts",
			{
				"account": r.account,
				"debit_in_account_currency": amount,
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
