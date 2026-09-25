# Copyright (c) 2026, Architect Coding and contributors
# For license information, please see license.txt

"""PPh 21 rate sets: one regulation's TER, PTKP and Pasal 17 tables, verified as
a unit.

Why sets exist: the verification used to be ONE site-wide tick, so rates for a
new regulation went live on the strength of a check made against the old one.
Now every set is verified on its own, payroll computes only on a verified set
(tables.require_verified_tables), and a verified set is frozen -- changing it
means unlocking it, which is refused once payroll or a BPA1 certificate used it.

The rules live here and in the doctypes' controllers, so they hold on every path:
the tax app's pages, Desk, an import, the rate loader.
"""

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, nowdate

DOCTYPE = "EIL PPh 21 Rate Set"
ROW_DOCTYPES = ("EIL TER Bracket", "EIL PTKP Rate", "EIL PPh 21 Bracket")
SETTINGS = "EIL PPh 21 Settings"


# ------------------------------------------------------------------ lookups
def in_force(on_date=None):
	"""The newest set whose effective date is on or before `on_date`, whatever
	its status (the gate decides what a Draft in force means), or None."""
	rows = frappe.get_all(
		DOCTYPE,
		filters={"effective_from": ("<=", getdate(on_date or nowdate()))},
		fields=["name", "effective_from", "regulation", "status", "verified_by", "verified_on", "source_file"],
		order_by="effective_from desc",
		limit=1,
	)
	return rows[0] if rows else None


def upcoming(on_date=None):
	"""Sets that take effect after `on_date`, soonest first."""
	return frappe.get_all(
		DOCTYPE,
		filters={"effective_from": (">", getdate(on_date or nowdate()))},
		fields=["name", "effective_from", "regulation", "status"],
		order_by="effective_from asc",
	)


def in_force_verified(on_date=None):
	current = in_force(on_date)
	return bool(current and current.status == "Verified")


def next_after(name):
	"""The effective date of the set that follows `name`, or None."""
	effective = frappe.db.get_value(DOCTYPE, name, "effective_from")
	nxt = frappe.get_all(
		DOCTYPE, filters={"effective_from": (">", effective)}, pluck="effective_from", order_by="effective_from asc", limit=1
	)
	return nxt[0] if nxt else None


def usage(name):
	"""What payroll has already computed with this set: submitted Salary Slips
	carrying the PPh 21 component, and submitted BPA1 certificates, whose period
	ends inside the set's validity. Changing the set would silently re-state them."""
	start = frappe.db.get_value(DOCTYPE, name, "effective_from")
	end = next_after(name)
	component = frappe.db.get_single_value(SETTINGS, "pph21_component")
	slips = 0
	if component:
		slips = frappe.db.sql(
			"""
			select count(distinct ss.name) from `tabSalary Slip` ss
			join `tabSalary Detail` sd on sd.parent = ss.name and sd.parenttype = 'Salary Slip'
			where ss.docstatus = 1 and sd.salary_component = %(component)s
				and ss.end_date >= %(start)s and (%(end)s is null or ss.end_date < %(end)s)
			""",
			{"component": component, "start": start, "end": end},
		)[0][0]
	certificates = frappe.db.sql(
		"""
		select count(*) from `tabEIL Bukti Potong A1` a
		join `tabPayroll Period` p on p.name = a.payroll_period
		where a.docstatus = 1 and p.end_date >= %(start)s and (%(end)s is null or p.end_date < %(end)s)
		""",
		{"start": start, "end": end},
	)[0][0]
	return {"salary_slips": int(slips or 0), "certificates": int(certificates or 0)}


# ------------------------------------------------------------------ actions
def verify(name):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	if doc.status == "Verified":
		return doc
	from erpbio_indonesia_localization.pph21 import tables

	problems = tables.validate_tables(rate_set=name)
	if problems:
		frappe.throw(
			_("These rates do not pass their own structural checks yet:<br>{0}").format("<br>".join(problems[:8]))
		)
	if not doc.source_file:
		frappe.throw(_("Attach the regulation PDF first — a verification is only as good as what it was checked against."))
	if frappe.db.get_single_value(SETTINGS, "require_four_eyes") and doc.last_edited_by == frappe.session.user:
		frappe.throw(_("Four-eyes is on: you last edited these rates, so someone else has to verify them."))
	doc.status = "Verified"
	doc.verified_by = frappe.session.user
	doc.verified_on = now_datetime()
	doc.flags.status_change = True
	doc.save(ignore_version=False)
	after_change()
	return doc


def unlock(name, reason):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	if doc.status != "Verified":
		return doc
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Say why the verified rates are being unlocked."))
	used = usage(name)
	if used["salary_slips"] or used["certificates"]:
		frappe.throw(
			_(
				"Payroll already computed with these rates ({0} salary slips, {1} BPA1 certificates). "
				"Changing them would re-state those documents — create a new rate set instead."
			).format(used["salary_slips"], used["certificates"])
		)
	doc.status = "Draft"
	doc.unlock_reason = reason
	doc.verified_by = None
	doc.verified_on = None
	doc.flags.status_change = True
	doc.save(ignore_version=False)
	after_change()
	return doc


def create(effective_from, regulation, copy_from=None, notes=None):
	"""A new Draft set, starting as a copy of `copy_from` (default: the set in
	force on its date), so a typical change is a few edits, not 140 rows."""
	frappe.has_permission(DOCTYPE, "create", throw=True)
	source = copy_from or (in_force(effective_from) or {}).get("name")
	doc = frappe.get_doc(
		{"doctype": DOCTYPE, "effective_from": effective_from, "regulation": regulation, "notes": notes}
	).insert()
	if source:
		replace_rows(doc.name, rows_of(source))
	return doc


def rows_of(name):
	"""A set's rows in the shape replace_rows takes."""
	fields = {"EIL TER Bracket": ["category", "from_amount", "to_amount", "rate"],
	          "EIL PTKP Rate": ["ptkp_status", "annual_amount", "ter_category"],
	          "EIL PPh 21 Bracket": ["from_amount", "to_amount", "rate"]}
	order = {"EIL TER Bracket": "category asc, from_amount asc", "EIL PTKP Rate": "annual_amount asc",
	         "EIL PPh 21 Bracket": "from_amount asc"}
	return {
		"ter": frappe.get_all("EIL TER Bracket", filters={"rate_set": name}, fields=fields["EIL TER Bracket"], order_by=order["EIL TER Bracket"]),
		"ptkp": frappe.get_all("EIL PTKP Rate", filters={"rate_set": name}, fields=fields["EIL PTKP Rate"], order_by=order["EIL PTKP Rate"]),
		"pasal17": frappe.get_all("EIL PPh 21 Bracket", filters={"rate_set": name}, fields=fields["EIL PPh 21 Bracket"], order_by=order["EIL PPh 21 Bracket"]),
	}


def replace_rows(name, rows):
	"""Replace a Draft set's rows wholesale -- what an editor grid saves. The row
	controllers refuse this on a Verified set."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	if doc.status == "Verified":
		frappe.throw(_("Rate set {0} is verified. Unlock it before changing its rates.").format(name))
	# One stamp and one cache/flag refresh for the whole replace, not one per row.
	frappe.flags.eil_rate_rows_bulk = True
	try:
		for doctype in ROW_DOCTYPES:
			for row_name in frappe.get_all(doctype, filters={"rate_set": name}, pluck="name"):
				frappe.delete_doc(doctype, row_name, ignore_permissions=True, force=True)
		for row in rows.get("ter") or []:
			_insert("EIL TER Bracket", doc, category=row.get("category"), from_amount=row.get("from_amount"),
			        to_amount=row.get("to_amount") or 0, rate=row.get("rate"))
		for row in rows.get("ptkp") or []:
			_insert("EIL PTKP Rate", doc, ptkp_status=row.get("ptkp_status"), annual_amount=row.get("annual_amount"),
			        ter_category=row.get("ter_category"))
		for row in rows.get("pasal17") or []:
			_insert("EIL PPh 21 Bracket", doc, from_amount=row.get("from_amount"), to_amount=row.get("to_amount") or 0,
			        rate=row.get("rate"))
	finally:
		frappe.flags.eil_rate_rows_bulk = False
	frappe.db.set_value(DOCTYPE, name, "last_edited_by", frappe.session.user, update_modified=False)
	after_change()


def _insert(doctype, rate_set, **values):
	frappe.get_doc({"doctype": doctype, "rate_set": rate_set.name, "effective_from": rate_set.effective_from, **values}).insert(
		ignore_permissions=True
	)


# ------------------------------------------------------------------ guards (row controllers)
def guard_row(row, deleting=False):
	"""A row belongs to a set, takes the set's date, and cannot change once the
	set is verified -- from any path."""
	if not row.rate_set:
		frappe.throw(_("Choose the rate set this row belongs to."))
	status, effective = frappe.db.get_value(DOCTYPE, row.rate_set, ["status", "effective_from"]) or (None, None)
	if status is None:
		frappe.throw(_("Rate set {0} does not exist.").format(row.rate_set))
	if status == "Verified":
		frappe.throw(
			_("Rate set {0} is verified, so its rates are frozen. Unlock it first.").format(row.rate_set),
			title=_("Verified rates"),
		)
	if not deleting:
		row.effective_from = effective


def stamp_edit(row):
	"""Remember who last changed a set's rates (four-eyes). A bulk replace stamps
	once itself."""
	if frappe.flags.get("eil_rate_rows_bulk"):
		return
	if row.rate_set:
		frappe.db.set_value(DOCTYPE, row.rate_set, "last_edited_by", frappe.session.user, update_modified=False)
	after_change()


# ------------------------------------------------------------------ housekeeping
def after_change():
	"""Drop the per-request table cache and mirror the in-force status onto the
	settings' read-only flag (Desk and older readers look at it)."""
	frappe.local._eil_pph21_tables = {}
	current = in_force()
	frappe.db.set_single_value(SETTINGS, "tables_verified", 1 if current and current.status == "Verified" else 0)
	frappe.clear_cache(doctype=SETTINGS)


def adopt_unlinked_rows():
	"""Before rate sets, rows were grouped only by effective_from. Give each such
	group a set -- Verified if the site had ticked the old site-wide flag, with
	who and when taken from its change history where there is one. Idempotent:
	only rows without a set are touched. Runs from setup_eil (after_migrate)."""
	dates = set()
	for doctype in ROW_DOCTYPES:
		dates |= set(frappe.get_all(doctype, filters={"rate_set": ("is", "not set")}, pluck="effective_from", distinct=True))
	if not dates:
		return
	# The old site-wide tick vouched for the rows it was ticked against -- the
	# legacy ones, adopted the first time. Rows that turn up unlinked later were
	# never checked by anyone, so they become a Draft like any other new set.
	was_verified = not frappe.db.count(DOCTYPE) and bool(frappe.db.get_single_value(SETTINGS, "tables_verified"))
	source = frappe.db.get_single_value(SETTINGS, "tables_source") or ""
	for effective in sorted(d for d in dates if d):
		name = frappe.db.get_value(DOCTYPE, {"effective_from": effective}, "name")
		if not name:
			doc = frappe.get_doc({
				"doctype": DOCTYPE,
				"effective_from": effective,
				"regulation": "PMK 168/2023" if "168/2023" in source else (source or "Unknown")[:140],
				"notes": _("Created from the rows loaded before rate sets existed. Source: {0}").format(source or "-"),
			})
			doc.flags.ignore_permissions = True
			doc.insert()
			name = doc.name
			if was_verified:
				who, when = _last_verification()
				frappe.db.set_value(DOCTYPE, name, {"status": "Verified", "verified_by": who, "verified_on": when},
				                    update_modified=False)
		for doctype in ROW_DOCTYPES:
			frappe.db.sql(
				f"update `tab{doctype}` set rate_set = %s where effective_from = %s and ifnull(rate_set, '') = ''",
				(name, effective),
			)
	after_change()


def _last_verification():
	"""Who ticked the old site-wide flag, from its Version log; else Administrator now."""
	for v in frappe.get_all(
		"Version", filters={"ref_doctype": SETTINGS, "docname": SETTINGS}, fields=["owner", "creation", "data"],
		order_by="creation desc", limit=100,
	):
		for row in (frappe.parse_json(v.data or "{}") or {}).get("changed") or []:
			if row and row[0] == "tables_verified" and str(row[2]) in ("1", "True"):
				return v.owner, v.creation
	return "Administrator", now_datetime()


def ensure_fixture_set(effective_from, regulation, source):
	"""The set a shipped fixture loads into. A new date becomes a Draft someone
	must verify; an existing Verified set is left alone (returns None)."""
	name = frappe.db.get_value(DOCTYPE, {"effective_from": effective_from}, "name")
	if name:
		return None if frappe.db.get_value(DOCTYPE, name, "status") == "Verified" else name
	doc = frappe.get_doc({"doctype": DOCTYPE, "effective_from": effective_from, "regulation": regulation,
	                      "notes": _("Shipped with the app. Source: {0}").format(source)})
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name
