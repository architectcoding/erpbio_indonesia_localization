# Retire the standalone EIL Govt Tax Template.
#
# The government (WAPU) charges now live on the Sales Taxes and Charges Template
# the sales team already picks, so a template charging PPN 12% carries the 12%
# government variant beside it and the quoted rate cannot drift from the rate on
# the faktur. The standalone master, and the per-customer / per-invoice pointers
# to it, are removed here.
#
# There is deliberately NO data migration. A post_model_sync patch runs AFTER
# migrate has already dropped the doctype whose files were deleted, so it cannot
# read the old rows — copy logic here would be dead code that silently does
# nothing. The standalone master was short-lived and never carried a site's
# real configuration; templates are re-authored on the selling template instead.

import frappe


def execute():
	for dt, fieldname in (
		("Customer", "eil_govt_tax_template"),
		("Sales Invoice", "eil_govt_tax_template"),
	):
		name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=1)
	frappe.db.commit()

	if frappe.db.exists("DocType", "EIL Govt Tax Template"):
		frappe.db.delete("EIL Govt Tax Charge", {"parenttype": "EIL Govt Tax Template"})
		frappe.delete_doc("DocType", "EIL Govt Tax Template", ignore_permissions=True, force=1)
		frappe.db.commit()
