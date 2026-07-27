# Whitelisted API for the /erpbio-tax SPA. Thin wrappers over the Coretax
# doctypes so the frontend never needs the generic frappe.client surface.
# Permission model: everything here requires rights on the underlying doctype
# (Accounts Manager per the doctype permissions).

import re

import frappe
from frappe import _
from frappe.utils import cint, flt


def _check(doctype, ptype="read"):
	if not frappe.has_permission(doctype, ptype):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def get_context():
	"""Everything the shell needs on load."""
	_check("Coretax Faktur Export")
	return {
		"companies": frappe.get_all("Company", pluck="name", order_by="name"),
		"transaction_codes": frappe.get_all(
			"Coretax Transaction Code", fields=["name", "description"], order_by="name"
		),
		"can_write": frappe.has_permission("Coretax Faktur Export", "write"),
	}


# ------------------------------------------------------------------- exports
@frappe.whitelist()
def list_exports(start=0, page_length=20):
	_check("Coretax Faktur Export")
	return frappe.get_all(
		"Coretax Faktur Export",
		fields=["name", "company", "from_date", "to_date", "status", "export_file", "generated_on"],
		order_by="creation desc",
		start=int(start),
		page_length=int(page_length),
	)


@frappe.whitelist()
def get_export(name):
	_check("Coretax Faktur Export")
	doc = frappe.get_doc("Coretax Faktur Export", name)
	return {
		"doc": {
			"name": doc.name,
			"company": doc.company,
			"npwp_penjual": doc.npwp_penjual,
			"from_date": doc.from_date,
			"to_date": doc.to_date,
			"status": doc.status,
			"export_file": doc.export_file,
			"generated_on": doc.generated_on,
		},
		"invoices": [
			{
				"sales_invoice": r.sales_invoice,
				"customer": r.customer,
				"posting_date": r.posting_date,
				"grand_total": flt(r.grand_total),
				"kode_transaksi": r.kode_transaksi,
				"ok": r.ok,
				"message": r.message,
			}
			for r in doc.invoices
		],
	}


@frappe.whitelist(methods=["POST"])
def create_export(company, from_date, to_date):
	_check("Coretax Faktur Export", "create")
	doc = frappe.new_doc("Coretax Faktur Export")
	doc.company = company
	doc.from_date = from_date
	doc.to_date = to_date
	doc.insert()
	return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def fetch_export_invoices(name):
	_check("Coretax Faktur Export", "write")
	return frappe.get_doc("Coretax Faktur Export", name).fetch_invoices()


@frappe.whitelist(methods=["POST"])
def generate_export(name):
	_check("Coretax Faktur Export", "write")
	return frappe.get_doc("Coretax Faktur Export", name).generate()


@frappe.whitelist(methods=["POST"])
def generate_export_xml(name):
	_check("Coretax Faktur Export", "write")
	return frappe.get_doc("Coretax Faktur Export", name).generate_xml()


# ------------------------------------------------------------------- reports
@frappe.whitelist()
def ppn_keluaran(company, from_date, to_date):
	_check("Sales Invoice")
	from erpbio_indonesia_localization.erpbio_indonesia_localization.report.ppn_keluaran.ppn_keluaran import (
		get_columns,
		get_data,
	)

	filters = frappe._dict({"company": company, "from_date": from_date, "to_date": to_date})
	return {"columns": get_columns(), "data": get_data(filters)}


@frappe.whitelist()
def ppn_masukan(company, from_date, to_date):
	_check("Purchase Invoice")
	from erpbio_indonesia_localization.erpbio_indonesia_localization.report.ppn_masukan.ppn_masukan import (
		get_columns,
		get_data,
	)

	filters = frappe._dict({"company": company, "from_date": from_date, "to_date": to_date})
	return {"columns": get_columns(), "data": get_data(filters)}


@frappe.whitelist()
def spt_masa(company, from_date, to_date):
	"""The month's PPN position: Keluaran − creditable Masukan = kurang (pay) /
	lebih (carry forward) bayar."""
	_check("Sales Invoice")
	_check("Purchase Invoice")
	keluaran = ppn_keluaran(company, from_date, to_date)["data"]
	masukan = ppn_masukan(company, from_date, to_date)["data"]
	total_keluaran = sum(flt(r["ppn"]) for r in keluaran)
	total_masukan = sum(flt(r["ppn"]) for r in masukan if r.get("creditable"))
	return {
		"keluaran": total_keluaran,
		"keluaran_count": len(keluaran),
		"masukan": total_masukan,
		"masukan_count": len(masukan),
		"net": flt(total_keluaran - total_masukan, 2),
	}


# -------------------------------------------------------------- bukti potong
@frappe.whitelist()
def list_bukti_potong(direction=None, start=0, page_length=50):
	_check("Bukti Potong")
	filters = {"direction": direction} if direction else {}
	return frappe.get_all(
		"Bukti Potong",
		filters=filters,
		fields=[
			"name",
			"direction",
			"customer",
			"supplier",
			"tax_type",
			"tax_object_code",
			"sales_invoice",
			"payment_entry",
			"withholding_date",
			"gross_amount",
			"rate",
			"tax_amount",
			"bp_number",
			"bp_date",
			"status",
		],
		order_by="creation desc",
		start=int(start),
		page_length=int(page_length),
	)


@frappe.whitelist(methods=["POST"])
def save_bukti_potong(payload):
	payload = frappe.parse_json(payload)
	name = payload.pop("name", None)
	if name:
		_check("Bukti Potong", "write")
		doc = frappe.get_doc("Bukti Potong", name)
	else:
		_check("Bukti Potong", "create")
		doc = frappe.new_doc("Bukti Potong")
		if not payload.get("company"):
			payload["company"] = frappe.defaults.get_user_default("Company") or frappe.get_all(
				"Company", pluck="name", limit=1
			)[0]
	for field in (
		"company",
		"direction",
		"customer",
		"supplier",
		"tax_type",
		"tax_object_code",
		"sales_invoice",
		"payment_entry",
		"withholding_date",
		"gross_amount",
		"rate",
		"tax_amount",
		"bp_number",
		"bp_date",
		"notes",
	):
		if field in payload:
			doc.set(field, payload[field])
	doc.save()
	return {"name": doc.name, "status": doc.status, "tax_amount": flt(doc.tax_amount)}


@frappe.whitelist()
def bukti_potong_lookups():
	_check("Bukti Potong")
	return {
		"customers": frappe.get_all("Customer", filters={"disabled": 0}, pluck="name", order_by="name"),
		"suppliers": frappe.get_all("Supplier", filters={"disabled": 0}, pluck="name", order_by="name"),
		# common statutory rates offered as defaults; the user can override
		"default_rates": {"PPh 22": 1.5, "PPh 23": 2.0, "PPh 4(2)": 10.0},
	}


@frappe.whitelist(methods=["POST"])
def export_ebupot(from_date, to_date, company=None):
	"""The period's ISSUED certificates as a working Excel for Coretax's e-Bupot
	(SPT Masa PPh Unifikasi) bulk entry — one row per certificate with the NPWP,
	object code, DPP, rate and PPh. Map it onto DJP's current template; like the
	faktur side, validate the first real filing carefully."""
	_check("Bukti Potong")
	import io

	import openpyxl

	filters = {"direction": "Issued", "withholding_date": ["between", [from_date, to_date]]}
	if company:
		filters["company"] = company
	rows = frappe.get_all(
		"Bukti Potong",
		filters=filters,
		fields=[
			"name",
			"company",
			"supplier",
			"tax_type",
			"tax_object_code",
			"withholding_date",
			"gross_amount",
			"rate",
			"tax_amount",
			"bp_number",
			"payment_entry",
		],
		order_by="withholding_date asc, name asc",
	)
	if not rows:
		frappe.throw(_("No issued Bukti Potong in this period."))

	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = "eBupot"
	ws.append(
		[
			"NPWP Pemotong",
			"Masa Pajak",
			"NPWP Dipotong",
			"Nama Dipotong",
			"Jenis Pajak",
			"Kode Objek Pajak",
			"DPP",
			"Tarif (%)",
			"PPh Dipotong",
			"Tanggal Pemotongan",
			"Nomor Bukti Potong",
			"Referensi",
		]
	)
	for r in rows:
		npwp_pemotong = re.sub(r"\D", "", frappe.db.get_value("Company", r.company, "tax_id") or "")
		npwp_dipotong = re.sub(r"\D", "", frappe.db.get_value("Supplier", r.supplier, "tax_id") or "")
		masa = r.withholding_date.strftime("%m-%Y") if r.withholding_date else ""
		ws.append(
			[
				npwp_pemotong,
				masa,
				npwp_dipotong,
				r.supplier,
				r.tax_type,
				r.tax_object_code or "",
				flt(r.gross_amount, 2),
				flt(r.rate, 2),
				flt(r.tax_amount, 2),
				r.withholding_date.strftime("%d/%m/%Y") if r.withholding_date else "",
				r.bp_number or "",
				r.payment_entry or r.name,
			]
		)

	buf = io.BytesIO()
	wb.save(buf)
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"ebupot-{from_date}-to-{to_date}.xlsx",
			"is_private": 1,
			"content": buf.getvalue(),
		}
	).insert(ignore_permissions=True)
	return {"file_url": file_doc.file_url, "rows": len(rows)}


# ------------------------------------------------------------------- imports
@frappe.whitelist()
def list_imports(start=0, page_length=20):
	_check("Coretax Faktur Import")
	return frappe.get_all(
		"Coretax Faktur Import",
		fields=["name", "import_file", "status", "summary", "creation"],
		order_by="creation desc",
		start=int(start),
		page_length=int(page_length),
	)


@frappe.whitelist()
def get_import(name):
	_check("Coretax Faktur Import")
	doc = frappe.get_doc("Coretax Faktur Import", name)
	return {
		"doc": {
			"name": doc.name,
			"import_file": doc.import_file,
			"status": doc.status,
			"summary": doc.summary,
		},
		"rows": [
			{
				"referensi": r.referensi,
				"sales_invoice": r.sales_invoice,
				"faktur_number": r.faktur_number,
				"faktur_date": r.faktur_date,
				"djp_status": r.djp_status,
				"mapped_status": r.mapped_status,
				"ok": r.ok,
				"message": r.message,
			}
			for r in doc.rows
		],
	}


@frappe.whitelist(methods=["POST"])
def create_import(file_url):
	_check("Coretax Faktur Import", "create")
	doc = frappe.new_doc("Coretax Faktur Import")
	doc.import_file = file_url
	doc.insert()
	return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def preview_import(name):
	_check("Coretax Faktur Import", "write")
	return frappe.get_doc("Coretax Faktur Import", name).preview()


@frappe.whitelist(methods=["POST"])
def apply_import(name):
	_check("Coretax Faktur Import", "write")
	return frappe.get_doc("Coretax Faktur Import", name).apply()


# ------------------------------------------------------------------ settings
@frappe.whitelist()
def get_settings():
	_check("Indonesia Tax Settings")
	s = frappe.get_single("Indonesia Tax Settings")
	return {
		"default_transaction_code": s.default_transaction_code,
		"default_buyer_country": s.default_buyer_country,
		"tarif_ppn": flt(s.tarif_ppn),
		"use_dpp_nilai_lain": s.use_dpp_nilai_lain,
		"dpp_numerator": s.dpp_numerator,
		"dpp_denominator": s.dpp_denominator,
		"withholding_accounts": [
			{
				"account": r.account,
				"direction": r.direction or "Received",
				"tax_type": r.tax_type,
				"rate": flt(r.rate),
				"tax_object_code": r.tax_object_code or "",
			}
			for r in (s.withholding_accounts or [])
		],
	}


@frappe.whitelist(methods=["POST"])
def save_settings(payload):
	_check("Indonesia Tax Settings", "write")
	payload = frappe.parse_json(payload)
	s = frappe.get_single("Indonesia Tax Settings")
	for field in (
		"default_transaction_code",
		"default_buyer_country",
		"tarif_ppn",
		"use_dpp_nilai_lain",
		"dpp_numerator",
		"dpp_denominator",
	):
		if field in payload:
			s.set(field, payload[field])
	if "withholding_accounts" in payload:
		s.set("withholding_accounts", [])
		for row in payload["withholding_accounts"]:
			if row.get("account"):
				s.append(
					"withholding_accounts",
					{
						"account": row["account"],
						"direction": row.get("direction") or "Received",
						"tax_type": row.get("tax_type") or "PPh 22",
						"rate": row.get("rate"),
						"tax_object_code": row.get("tax_object_code"),
					},
				)
	s.save()
	return get_settings()


@frappe.whitelist()
def account_options():
	"""Non-group accounts for the withholding-account picker."""
	_check("Indonesia Tax Settings")
	return frappe.get_all(
		"Account",
		filters={"is_group": 0, "disabled": 0},
		pluck="name",
		order_by="name",
		limit_page_length=0,
	)


# --- Government (pemungut/WAPU) charges on a Sales Invoice ---------------------
#
# Exposed for the accounting SPA, which has no other way to show WHY a pemungut
# invoice's outstanding is lower than its grand total. Editing is allowed after
# submit because the withheld PPh 22 is frequently only known exactly once the
# bukti potong arrives — but every write re-posts the reclassification entry, so
# the table and the ledger cannot drift apart.


@frappe.whitelist()
def get_invoice_govt_charges(sales_invoice):
	"""The invoice's government charges plus what the UI needs to decide whether
	they may still be edited."""
	if not sales_invoice or not frappe.db.exists("Sales Invoice", sales_invoice):
		return None
	if not frappe.has_permission("Sales Invoice", "read", sales_invoice):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("Sales Invoice", sales_invoice)
	blocker = _edit_blocker(doc)
	# Returned even when the invoice isn't flagged, so an accountant can add
	# government tax to an invoice raised by hand — the buyer being a bendahara
	# isn't always known when the customer record was set up.
	return {
		"sales_invoice": doc.name,
		"currency": doc.currency,
		"is_pemungut": cint(doc.get("eil_is_pemungut")),
		"treatments": _govt_treatments(),
		"defaults": govt_tax_defaults(doc.company),
		"template": doc.get("eil_govt_tax_template"),
		"journal_entry": doc.get("eil_wapu_journal_entry"),
		"docstatus": doc.docstatus,
		"net_total": flt(doc.base_net_total),
		"grand_total": flt(doc.base_grand_total),
		"outstanding": flt(doc.outstanding_amount),
		"can_edit": not blocker and frappe.has_permission("Sales Invoice", "write", sales_invoice),
		"blocked_reason": blocker,
		"charges": [
			{
				"name": r.name,
				"treatment": r.treatment,
				"account": r.account,
				"rate": flt(r.rate),
				"amount": flt(r.amount),
				"show_on_print": cint(r.show_on_print),
				"clear_on_payment": cint(r.clear_on_payment),
				"description": r.description,
			}
			for r in doc.get("eil_govt_charges") or []
		],
	}


def _govt_treatments():
	"""The accounting behaviours, read off the field rather than hardcoded here."""
	f = frappe.get_meta("EIL Govt Tax Charge").get_field("treatment")
	return [o for o in ((f.options or "").split("\n") if f else []) if o]


@frappe.whitelist()
def govt_tax_defaults(company=None):
	"""Per-company default account/rate per treatment, from Indonesia Tax Settings.
	These only pre-fill a new charge row; the invoice keeps its own copy, so
	changing a default never rewrites tax already booked."""
	rows = frappe.get_all(
		"EIL Govt Tax Default",
		filters={"parenttype": "Indonesia Tax Settings"},
		fields=["company", "treatment", "description", "account", "rate"],
		order_by="idx asc",
	)
	if company:
		rows = [r for r in rows if r.company == company]
	return rows


def _edit_blocker(doc):
	"""Why the charges are frozen, or None when they can still be changed.

	A receipt already cleared the PPN receivable using these figures, so changing
	them afterwards would leave the payment pointing at an amount that no longer
	exists. The payment has to be cancelled first."""
	if doc.docstatus == 2:
		return frappe._("This invoice is cancelled.")
	if doc.docstatus == 1:
		paid = frappe.get_all(
			"Payment Entry Reference",
			filters={"reference_doctype": "Sales Invoice", "reference_name": doc.name, "docstatus": 1},
			limit=1,
		)
		if paid:
			return frappe._(
				"A payment has already been applied to this invoice. Cancel it before changing the government tax."
			)
	return None


@frappe.whitelist(methods=["POST"])
def update_invoice_govt_charges(sales_invoice, charges):
	"""Replace the charges and, on a submitted invoice, re-post the
	reclassification entry so the ledger follows the table."""
	from erpbio_indonesia_localization.doc_events.sales_invoice import _build_reclassification

	if not frappe.has_permission("Sales Invoice", "write", sales_invoice):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
	doc = frappe.get_doc("Sales Invoice", sales_invoice)
	blocker = _edit_blocker(doc)
	if blocker:
		frappe.throw(blocker)

	rows = frappe.parse_json(charges) if isinstance(charges, str) else (charges or [])
	# Adding charges to an invoice raised by hand is how an accountant flags a
	# bendahara sale the customer record didn't know about; clearing them all
	# turns the invoice back into an ordinary one.
	doc.eil_is_pemungut = 1 if rows else 0
	from erpbio_indonesia_localization.doc_events.sales_invoice import (
		_dpp_base,
		apply_treatment_rules,
	)

	# Saving a SUBMITTED invoice does not re-run the validate hook, so this path
	# has to apply the invoice's own rules itself rather than rely on them.
	base = _dpp_base(doc)
	doc.set("eil_govt_charges", [])
	for r in rows:
		if not r.get("account"):
			continue
		amount = flt(r.get("amount"))
		rate = flt(r.get("rate"))
		# Same rule as the invoice hook: a rate recomputes the amount, a blank rate
		# keeps the figure that was typed (which is how an actual bukti potong is
		# entered when it differs from the standard rate).
		if rate:
			amount = flt(base * rate / 100.0, doc.precision("base_net_total"))
		row = doc.append(
			"eil_govt_charges",
			{
				"treatment": r.get("treatment") or "PPN Dipungut Pemungut",
				"account": r["account"],
				"rate": rate,
				"amount": amount,
				"show_on_print": cint(r.get("show_on_print")),
				"description": r.get("description"),
			},
		)
		apply_treatment_rules(row)

	if doc.docstatus == 0:
		doc.save()
	else:
		# allow_on_submit: write the rows, then rebuild the entry they justify.
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)
		_repost_reclassification(doc)

	return get_invoice_govt_charges(sales_invoice)


def _repost_reclassification(doc):
	"""Cancel the existing entry and post a fresh one. The cancelled entry is left
	in place: it is the audit trail for what the invoice used to claim."""
	from erpbio_indonesia_localization.doc_events.sales_invoice import _build_reclassification

	old = doc.get("eil_wapu_journal_entry")
	if old and frappe.db.exists("Journal Entry", old):
		# Drop the link before cancelling: while the submitted invoice still points
		# at the entry, Frappe's link check refuses to cancel it (LinkExistsError).
		doc.db_set("eil_wapu_journal_entry", None, update_modified=False)
		if frappe.db.get_value("Journal Entry", old, "docstatus") == 1:
			frappe.get_doc("Journal Entry", old).cancel()
	doc.reload()
	new = _build_reclassification(doc)
	doc.db_set("eil_wapu_journal_entry", new, update_modified=False)
	return new
