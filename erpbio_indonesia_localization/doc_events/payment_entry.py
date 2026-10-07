# Bukti Potong automation, both directions of the withholding relationship:
#
#  Received — a customer (typically a government bendahara) withholds PPh from
#  a payment TO us; the PE deduction row hits a prepaid-tax asset account, and
#  we're owed a certificate (the prepaid-tax credit evidence).
#
#  Issued — WE withhold PPh from a payment to a supplier (e.g. PPh 23 on
#  services); the PE deduction row hits a PPh-payable account, and we owe DJP
#  an e-Bupot report and the supplier a certificate.
#
# Which is which comes from the account mapping in Indonesia Tax Settings.
# These handlers only OBSERVE the Payment Entry: they never modify it or its
# GL, and every failure is swallowed into a log so a tracking bug can never
# block a real payment from being submitted or cancelled.

import frappe
from frappe.utils import cint, flt


def on_submit(doc, method=None):
	try:
		_create_bukti_potong(doc)
	except Exception:
		frappe.log_error(title="Bukti Potong auto-create failed", message=frappe.get_traceback())


def on_cancel(doc, method=None):
	"""Remove auto-created certificates that never materialized. A numbered one
	(Received/Reported) stays — the paper exists regardless of the payment."""
	try:
		for name in frappe.get_all(
			"Bukti Potong",
			filters={"payment_entry": doc.name, "auto_created": 1, "status": ["in", ["Expected", "To Report"]]},
			pluck="name",
		):
			frappe.delete_doc("Bukti Potong", name, force=1, ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Bukti Potong auto-cleanup failed", message=frappe.get_traceback())


def _create_bukti_potong(doc):
	if doc.party_type not in ("Customer", "Supplier") or not doc.get("deductions"):
		return
	wanted_direction = "Received" if doc.party_type == "Customer" else "Issued"
	mapping = _withholding_map(wanted_direction)
	if not mapping:
		return

	invoice_doctype = "Sales Invoice" if wanted_direction == "Received" else "Purchase Invoice"
	invoice_refs = [
		r.reference_name for r in (doc.get("references") or []) if r.reference_doctype == invoice_doctype
	]
	linked_invoice = invoice_refs[0] if len(invoice_refs) == 1 else None

	for row in doc.deductions:
		rule = mapping.get(row.account)
		if not rule:
			continue
		tax_amount = abs(flt(row.amount))
		if not tax_amount:
			continue
		if frappe.db.exists(
			"Bukti Potong",
			{"payment_entry": doc.name, "tax_type": rule["tax_type"], "tax_amount": tax_amount},
		):
			continue  # PE amended and resubmitted — don't double up
		rate = flt(rule.get("rate"))
		bp = frappe.new_doc("Bukti Potong")
		bp.company = doc.company
		bp.direction = wanted_direction
		if wanted_direction == "Received":
			bp.customer = doc.party
			bp.sales_invoice = linked_invoice
		else:
			bp.supplier = doc.party
		bp.tax_type = rule["tax_type"]
		bp.tax_object_code = rule.get("tax_object_code")
		bp.payment_entry = doc.name
		bp.withholding_date = doc.posting_date
		bp.rate = rate
		bp.tax_amount = tax_amount
		bp.gross_amount = flt(tax_amount * 100.0 / rate, 2) if rate else 0
		bp.auto_created = 1
		bp.notes = frappe._("Auto-created from Payment Entry {0} deduction ({1}).").format(doc.name, row.account)
		bp.flags.ignore_permissions = True
		bp.insert()


def _withholding_map(direction):
	settings = frappe.get_single("Indonesia Tax Settings")
	return {
		row.account: {
			"tax_type": row.tax_type,
			"rate": row.rate,
			"tax_object_code": row.get("tax_object_code"),
		}
		for row in (settings.withholding_accounts or [])
		if row.account and (row.get("direction") or "Received") == direction
	}


# --- WAPU/Bendahara: Piutang PPN Bendahara on the receipt -------------------
# The invoice's reclassification carves its PPN out of the receivable into
# Piutang PPN Bendahara, so the outstanding is already net of it. What the
# treasurer then sends varies, and only the bank statement says which:
#
#  - net, the usual WAPU case: the treasurer deposits the PPN to the state
#    itself and sends the outstanding. The receipt is the outstanding, and
#    Piutang PPN Bendahara stays open for the bukti setor to account for.
#  - gross: the treasurer sends the outstanding PLUS the PPN. The receipt clears
#    the PPN receivable with a NEGATIVE deduction on its account, and the bank
#    gets both.
#
# The receipt states which in `eil_ppn_received`. This used to be inferred: an
# amount still equal to the allocation was raised to allocation + PPN, on the
# theory that it was ERPNext's untouched default. But a net receipt typed from
# the statement equals the allocation too, so every net receipt was booked
# gross -- the bank overstated by the PPN, and the PPN receivable cleared with
# no bukti setor behind it. Now the box is ticked by the accountant, or by a
# fact that can only mean gross: a negative row on the PPN account put there on
# purpose (erpbio_general's cash/bank form sends one), or an amount of exactly
# allocation + PPN. Unticking it takes the clearing back out.
#
# Only a reference that settles its invoice in FULL is cleared. A part payment
# would otherwise clear the whole PPN receivable against a fraction of the
# cash, so the accountant splits that one by hand. PPh 22 is never touched here;
# it is booked at invoice time as a prepaid asset the company later claims.

PPN_RECEIVED = "eil_ppn_received"


def before_validate(doc, method=None):
	if doc.payment_type != "Receive" or doc.party_type != "Customer":
		return
	to_clear, accounts = _government_ppn(doc)
	if not accounts:
		return
	if _unticked(doc):
		_withdraw_clearing(doc, accounts)
		return
	if not cint(doc.get(PPN_RECEIVED)) and _says_ppn_received(doc, accounts, sum(to_clear.values())):
		doc.set(PPN_RECEIVED, 1)
	if not cint(doc.get(PPN_RECEIVED)):
		return  # net: the bukti setor accounts for the PPN, not this receipt
	for acc, amt in to_clear.items():
		have = sum(-flt(d.amount) for d in (doc.get("deductions") or [])
				   if d.account == acc and flt(d.amount) < 0)
		delta = flt(amt) - have
		if abs(delta) < 0.005:
			continue
		doc.append("deductions", {
			"account": acc,
			"cost_center": frappe.get_cached_value("Company", doc.company, "cost_center"),
			"amount": -delta,
		})
	_prefill_amount(doc, sum(to_clear.values()))


def _government_ppn(doc):
	"""({account: amount} the receipt clears, every PPN account its invoices use).

	The first holds only the invoices this receipt settles in full. The second
	takes part payments too: a clearing row the accountant split onto one is
	still a statement that the PPN came with the cash."""
	to_clear, accounts = {}, set()
	for ref in doc.get("references") or []:
		if ref.reference_doctype != "Sales Invoice" or not ref.reference_name:
			continue
		ppn = _pemungut_ppn(ref.reference_name)
		if not ppn:
			continue
		accounts.update(ppn)
		outstanding = flt(
			frappe.db.get_value("Sales Invoice", ref.reference_name, "outstanding_amount")
		)
		if flt(ref.allocated_amount) + 0.005 < outstanding:
			continue  # a part payment — the accountant splits the PPN by hand
		for acc, amt in ppn.items():
			to_clear[acc] = to_clear.get(acc, 0.0) + amt
	return to_clear, accounts


def _says_ppn_received(doc, accounts, ppn):
	"""Whether the receipt itself already says the PPN came with the cash.

	Only facts that cannot mean net count. A receipt whose amount equals the
	allocation does NOT: that is both ERPNext's default and a net transfer typed
	from the statement, and reading it as gross is the bug this replaced."""
	if any(d.account in accounts and flt(d.amount) < 0 for d in doc.get("deductions") or []):
		return True
	if not ppn or doc.docstatus != 0:
		return False
	return abs(flt(doc.paid_amount) - (_allocated(doc) + ppn)) < 0.005


def _unticked(doc):
	"""The accountant just took the tick off a saved draft."""
	if doc.docstatus != 0 or cint(doc.get(PPN_RECEIVED)):
		return False
	before = doc.get_doc_before_save()
	return bool(before and cint(before.get(PPN_RECEIVED)))


def _withdraw_clearing(doc, accounts):
	"""Undo what the tick did: the PPN clearing rows go, and an amount that is
	exactly allocation + their PPN comes back down to the allocation. Left in
	place, either one would read as gross again on the next save."""
	rows = [d for d in doc.get("deductions") or [] if d.account in accounts and flt(d.amount) < 0]
	if not rows:
		return
	ppn = -sum(flt(d.amount) for d in rows)
	for d in rows:
		doc.remove(d)
	allocated = _allocated(doc)
	if abs(flt(doc.paid_amount) - (allocated + ppn)) < 0.005:
		_set_amount(doc, allocated)


def _prefill_amount(doc, ppn):
	"""Raise the untouched default to the cash a gross treasurer sends.

	Only reached on a receipt marked gross. ERPNext prefills the amount from the
	allocation, which is then short by exactly the PPN — leaving the entry
	unbalanced until the accountant types the real figure. Corrected only while
	the figure is still that default, so a real receipt that differs (a transfer
	fee, a rounding) is never overwritten."""
	if not ppn or doc.docstatus != 0:
		return
	allocated = _allocated(doc)
	if abs(flt(doc.paid_amount) - allocated) >= 0.005:
		return
	_set_amount(doc, allocated + ppn)


def _allocated(doc):
	return sum(flt(r.allocated_amount) for r in doc.get("references") or [])


def _set_amount(doc, amount):
	same_currency = abs(flt(doc.received_amount) - flt(doc.paid_amount)) < 0.005
	doc.paid_amount = flt(amount, doc.precision("paid_amount"))
	if same_currency:
		doc.received_amount = flt(doc.paid_amount, doc.precision("received_amount"))


def _pemungut_ppn(si_name):
	"""{receivable_account: amount} for the invoice's government charges that clear
	when the money arrives.

	`clear_on_payment` is what separates the two treatments: the PPN receivable is
	settled by the receipt (the government keeps that portion), whereas a
	withholding like PPh 22 stays on the books as a prepaid-tax asset and must NOT
	be cleared here.

	Read from the reclassification entry rather than the charge row, because the
	entry is capped at what the receivable could hold: an invoice largely settled
	by an advance books less PPN than the row nominally shows, and clearing the
	nominal figure would credit a receivable that was never debited."""
	accounts = frappe.get_all(
		"EIL Govt Tax Charge",
		filters={"parent": si_name, "parenttype": "Sales Invoice", "clear_on_payment": 1},
		pluck="account",
	)
	if not accounts:
		return {}
	je = frappe.db.get_value("Sales Invoice", si_name, "eil_wapu_journal_entry")
	if not je or frappe.db.get_value("Journal Entry", je, "docstatus") != 1:
		return {}
	out = {}
	for r in frappe.get_all(
		"Journal Entry Account",
		filters={"parent": je, "account": ["in", set(accounts)]},
		fields=["account", "debit_in_account_currency"],
	):
		amount = flt(r.debit_in_account_currency)
		if amount:
			out[r.account] = out.get(r.account, 0.0) + amount
	return out
