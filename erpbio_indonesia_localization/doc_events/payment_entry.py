# Bukti Potong automation for the bendahara withholding flow: when a customer
# (typically a government treasurer) withholds PPh from a payment, the Payment
# Entry carries the withheld amount as a deduction row against a prepaid-tax
# account. If that account is mapped in Indonesia Tax Settings, submitting the
# PE creates the Expected Bukti Potong automatically — the certificate to chase.
#
# These handlers only OBSERVE the Payment Entry: they never modify it or its GL,
# and every failure is swallowed into a log so a tracking bug can never block a
# real payment from being submitted or cancelled.

import frappe
from frappe.utils import flt


def on_submit(doc, method=None):
	try:
		_create_expected_bukti_potong(doc)
	except Exception:
		frappe.log_error(title="Bukti Potong auto-create failed", message=frappe.get_traceback())


def on_cancel(doc, method=None):
	"""Remove auto-created certificates that never materialized. A Received one
	stays — the paper exists regardless of what happened to the payment."""
	try:
		for name in frappe.get_all(
			"Bukti Potong",
			filters={"payment_entry": doc.name, "auto_created": 1, "status": "Expected"},
			pluck="name",
		):
			frappe.delete_doc("Bukti Potong", name, force=1, ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Bukti Potong auto-cleanup failed", message=frappe.get_traceback())


def _create_expected_bukti_potong(doc):
	if doc.party_type != "Customer" or not doc.get("deductions"):
		return
	mapping = _withholding_map()
	if not mapping:
		return

	# one linked Sales Invoice → carry it onto the certificate; several → leave blank
	si_refs = [r.reference_name for r in (doc.get("references") or []) if r.reference_doctype == "Sales Invoice"]
	sales_invoice = si_refs[0] if len(si_refs) == 1 else None

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
		bp.customer = doc.party
		bp.tax_type = rule["tax_type"]
		bp.sales_invoice = sales_invoice
		bp.payment_entry = doc.name
		bp.rate = rate
		bp.tax_amount = tax_amount
		bp.gross_amount = flt(tax_amount * 100.0 / rate, 2) if rate else 0
		bp.auto_created = 1
		bp.notes = frappe._("Auto-created from Payment Entry {0} deduction ({1}).").format(doc.name, row.account)
		bp.flags.ignore_permissions = True
		bp.insert()


def _withholding_map():
	settings = frappe.get_single("Indonesia Tax Settings")
	return {
		row.account: {"tax_type": row.tax_type, "rate": row.rate}
		for row in (settings.withholding_accounts or [])
		if row.account
	}
