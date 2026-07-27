# Sales Order — carry the government (pemungut/WAPU) fact forward.
#
# A sales user shouldn't have to know about bendahara VAT mechanics; whether a
# buyer is a government treasurer is a property of the customer, not a decision
# taken per order. So the flag is derived here and travels with the document:
#
#     Customer (flag, or a group listed in Indonesia Tax Settings)
#         -> Sales Order.eil_is_pemungut
#             -> Sales Invoice.eil_is_pemungut  (same fieldname, so ERPNext's
#                own order-to-invoice mapping carries it)
#
# The invoice then materialises the actual charges from a template. Nothing here
# touches totals or GL — it only records what kind of buyer this is.

import frappe


def before_validate(doc, method=None):
	# Respect an explicit choice: only derive when the user hasn't set it.
	if doc.get("eil_is_pemungut"):
		return
	if doc.get("customer") and is_pemungut_customer(doc.customer):
		doc.eil_is_pemungut = 1


def is_pemungut_customer(customer):
	"""True when the customer is flagged, or sits in a customer group configured
	as pemungut. The group list is configuration rather than a hardcoded name, so
	renames, translations and BUMN-style groups don't quietly break the rule."""
	if not customer:
		return False
	row = frappe.db.get_value(
		"Customer", customer, ["eil_is_pemungut", "customer_group"], as_dict=True
	)
	if not row:
		return False
	if row.get("eil_is_pemungut"):
		return True
	if not row.get("customer_group"):
		return False
	groups = frappe.get_all(
		"EIL Pemungut Customer Group",
		filters={"parenttype": "Indonesia Tax Settings"},
		pluck="customer_group",
	)
	return row.customer_group in set(groups)
