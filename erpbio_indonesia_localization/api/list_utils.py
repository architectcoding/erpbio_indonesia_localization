"""
Filter / sort / count helpers for this app's SPA list endpoints, so the shared
ListView's panel filters, sortable headers and row counts have a backend to
talk to.

A trimmed copy of the equivalent in erpbio_general: this app is deliberately
self-contained (clean-room MIT, installs without erpbio_general), so it
carries its own rather than importing from there.
"""

import json

import frappe

# Operators the Frappe-style filter panel may send. Anything else is dropped.
ALLOWED_OPERATORS = {"like", "=", "!=", ">", "<", ">=", "<="}


def parse_filters(filters):
	"""Normalise the filter payload (JSON string or list) into a clean list of
	(field, operator, value) tuples -- skipping anything malformed or empty."""
	if isinstance(filters, str):
		filters = json.loads(filters or "[]")
	out = []
	for f in filters or []:
		field = f.get("field")
		operator = f.get("operator") or "like"
		value = f.get("value")
		if not field or operator not in ALLOWED_OPERATORS or value in (None, ""):
			continue
		out.append((field, operator, value))
	return out


def to_getlist_filters(filters, allowed_fields):
	"""Convert the panel payload into frappe.get_list filter tuples."""
	out = []
	for field, operator, value in parse_filters(filters):
		if field not in allowed_fields:
			continue
		out.append([field, operator, f"%{value}%" if operator == "like" else value])
	return out


def resolve_order_by(order_by, allowed, default):
	"""Validate a client-supplied 'field dir' sort against an allowlist so the
	sortable column headers can't inject arbitrary order_by SQL."""
	if not order_by:
		return default
	parts = str(order_by).split()
	field = parts[0]
	direction = "desc" if len(parts) > 1 and parts[1].lower() == "desc" else "asc"
	return f"{field} {direction}" if field in allowed else default


def capped_total(doctype, filters=None, or_filters=None, cap=1000):
	"""Permission-aware row count, capped at cap+1 (so the UI can show 'cap+')."""
	names = frappe.get_list(
		doctype, filters=filters or {}, or_filters=or_filters, pluck="name", limit=cap + 1
	)
	return len(names)
