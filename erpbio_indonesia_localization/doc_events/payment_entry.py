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
from frappe.utils import flt


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
