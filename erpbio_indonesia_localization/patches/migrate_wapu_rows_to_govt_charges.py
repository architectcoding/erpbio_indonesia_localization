# Move government-collected tax off the neutralised Sales Taxes and Charges rows
# and into the eil_govt_charges table.
#
# The old mechanism parked a real PPN row in ERPNext's tax table and then zeroed
# it (charge_type=Actual, rate=0, tax_amount=0), keeping the true figures in
# eil_wapu_rate / eil_wapu_amount. This converts each such row into an
# EIL Govt Tax Charge row, flags its invoice as pemungut, and then removes the
# three now-dead custom fields.
#
# Deliberately conservative: it writes the child rows straight to the database
# rather than re-saving the parent, because these invoices are typically
# submitted and the reclassification entry they already produced must not be
# rebuilt. The GL is untouched — this is a representation change only. It leaves
# the old tax rows in place (inert, amount 0) so nothing about a posted document
# silently changes; only the reading of it moves.

import frappe

OLD_FIELDS = [
	{"dt": "Sales Taxes and Charges", "fieldname": "eil_govt_tax_treatment"},
	{"dt": "Sales Taxes and Charges", "fieldname": "eil_wapu_rate"},
	{"dt": "Sales Taxes and Charges", "fieldname": "eil_wapu_amount"},
]
PPN = "PPN Dipungut Pemungut"


def execute():
	if not frappe.db.has_column("Sales Taxes and Charges", "eil_govt_tax_treatment"):
		_drop_old_fields()
		return

	rows = frappe.db.sql(
		"""
		select parent, account_head, eil_govt_tax_treatment, eil_wapu_rate, eil_wapu_amount, idx
		from `tabSales Taxes and Charges`
		where parenttype = 'Sales Invoice'
		  and ifnull(eil_govt_tax_treatment, '') != ''
		order by parent, idx
		""",
		as_dict=True,
	)
	moved, invoices = 0, set()
	for r in rows:
		if not frappe.db.exists("Sales Invoice", r.parent):
			continue
		# already migrated? (idempotent on re-run)
		if frappe.db.exists(
			"EIL Govt Tax Charge",
			{"parent": r.parent, "parenttype": "Sales Invoice", "account": r.account_head},
		):
			continue
		is_ppn = r.eil_govt_tax_treatment == PPN
		frappe.get_doc(
			{
				"doctype": "EIL Govt Tax Charge",
				"parenttype": "Sales Invoice",
				"parent": r.parent,
				"parentfield": "eil_govt_charges",
				"idx": r.idx,
				"treatment": r.eil_govt_tax_treatment,
				"account": r.account_head,
				"rate": r.eil_wapu_rate,
				"amount": r.eil_wapu_amount,
				# PPN shows on the faktur and clears when the money lands;
				# a withholding is hidden and stays a prepaid-tax asset.
				"show_on_print": 1 if is_ppn else 0,
				"clear_on_payment": 1 if is_ppn else 0,
			}
		).insert(ignore_permissions=True)
		moved += 1
		invoices.add(r.parent)

	for si in invoices:
		frappe.db.set_value("Sales Invoice", si, "eil_is_pemungut", 1, update_modified=False)

	if moved or invoices:
		frappe.db.commit()
	_drop_old_fields()


def _drop_old_fields():
	for f in OLD_FIELDS:
		name = frappe.db.get_value("Custom Field", f)
		if name:
			frappe.delete_doc("Custom Field", name, force=1, ignore_permissions=True)
	frappe.db.commit()
