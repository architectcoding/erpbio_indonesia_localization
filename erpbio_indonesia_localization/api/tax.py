# Whitelisted API for the /erpbio-tax SPA. Thin wrappers over the Coretax
# doctypes so the frontend never needs the generic frappe.client surface.
# Permission model: everything here requires rights on the underlying doctype
# (Accounts Manager per the doctype permissions).

import re

import frappe

from erpbio_indonesia_localization.api.list_utils import (
	capped_total,
	resolve_order_by,
	to_getlist_filters,
)
from frappe import _
from frappe.utils import cint, flt


def _check(doctype, ptype="read"):
	if not frappe.has_permission(doctype, ptype):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


EXPORT_FILTER_FIELDS = {"name", "company", "status"}
EXPORT_ORDER_FIELDS = {"name", "company", "from_date", "to_date", "status", "generated_on", "creation"}
IMPORT_FILTER_FIELDS = {"name", "status"}
IMPORT_ORDER_FIELDS = {"name", "status", "creation"}


@frappe.whitelist()
def get_context():
	"""Everything the shell needs on load."""
	_check("Coretax Faktur Export")
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	return {
		"companies": frappe.get_all("Company", pluck="name", order_by="name"),
		"transaction_codes": frappe.get_all(
			"Coretax Transaction Code", fields=["name", "description"], order_by="name"
		),
		"can_write": frappe.has_permission("Coretax Faktur Export", "write"),
		# So amounts render the way Desk renders them (Indonesian 1.234.567,89
		# rather than the JS default). Read from core settings — nothing here
		# depends on erpbio_general.
		"number_format": frappe.db.get_single_value("System Settings", "number_format") or "#.###,##",
		"float_precision": frappe.db.get_single_value("System Settings", "float_precision") or 2,
		"currency": (frappe.get_cached_value("Company", company, "default_currency") if company else "IDR"),
		# For the sidebar account menu (avatar + name). Rides this existing call
		# rather than adding a round-trip at boot.
		"user": frappe.db.get_value(
			"User", frappe.session.user, ["name", "full_name", "user_image"], as_dict=True
		),
	}


# ------------------------------------------------------------------- exports
@frappe.whitelist()
def list_exports(txt=None, filters=None, order_by=None, start=0, page_length=20):
	"""Exports for the shared ListView: panel/quick filters, sortable headers and
	a capped total so the footer can show "N of M"."""
	_check("Coretax Faktur Export")
	flt_list = to_getlist_filters(filters, EXPORT_FILTER_FIELDS)
	or_filters = {"name": ["like", f"%{txt}%"]} if txt else None
	rows = frappe.get_all(
		"Coretax Faktur Export",
		filters=flt_list,
		or_filters=or_filters,
		fields=["name", "company", "from_date", "to_date", "status", "export_file", "generated_on"],
		order_by=resolve_order_by(order_by, EXPORT_ORDER_FIELDS, "creation desc"),
		start=int(start),
		page_length=int(page_length),
	)
	total = capped_total("Coretax Faktur Export", filters=flt_list, or_filters=or_filters)
	return {"items": rows, "total": total, "has_next": int(start) + len(rows) < total, "meta": {}}


@frappe.whitelist()
def get_export(name):
	_check("Coretax Faktur Export")
	doc = frappe.get_doc("Coretax Faktur Export", name)
	# The stored grand_total is the invoice's OWN currency total (si.grand_total,
	# not base), so the frontend needs each row's currency or a foreign-currency
	# invoice gets labelled with the company's — a USD 1,200 reading "IDR 1.200".
	# Derived here rather than stored: it's the invoice's own field, always current.
	names = [r.sales_invoice for r in doc.invoices if r.sales_invoice]
	currencies = (
		dict(
			frappe.get_all(
				"Sales Invoice", filters={"name": ["in", names]}, fields=["name", "currency"], as_list=True
			)
		)
		if names
		else {}
	)
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
				"currency": currencies.get(r.sales_invoice),
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
			"bp_file",
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
		"bp_file",
		"notes",
	):
		if field in payload:
			doc.set(field, payload[field])
	doc.save()
	return {"name": doc.name, "status": doc.status, "tax_amount": flt(doc.tax_amount)}


BP_FIELDS = (
	"company",
	"direction",
	"customer",
	"supplier",
	"tax_type",
	"tax_object_code",
	"sales_invoice",
	"payment_entry",
	"withholding_date",
	"status",
	"gross_amount",
	"rate",
	"tax_amount",
	"bp_number",
	"bp_date",
	"bp_file",
	"notes",
	"auto_created",
)


def _bp_attachments(name):
	"""Every file filed against the certificate — the scan itself plus whatever
	else came with it (a corrected bupot, proof of payment)."""
	return frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Bukti Potong", "attached_to_name": name},
		fields=["name", "file_name", "file_url", "is_private", "file_size", "creation"],
		order_by="creation asc",
	)


@frappe.whitelist()
def get_bukti_potong(name):
	_check("Bukti Potong")
	doc = frappe.get_doc("Bukti Potong", name)
	out = {"name": doc.name, "docstatus": doc.docstatus}
	for field in BP_FIELDS:
		value = doc.get(field)
		out[field] = flt(value) if field in ("gross_amount", "rate", "tax_amount") else value
	return {
		"doc": out,
		"attachments": _bp_attachments(name),
		"can_write": frappe.has_permission("Bukti Potong", "write", doc=doc),
	}


@frappe.whitelist(methods=["POST"])
def remove_bukti_potong_attachment(name, file):
	"""Detach a file. Gated on write of the *certificate*, not of File, so the
	frontend never needs the generic delete surface."""
	_check("Bukti Potong", "write")
	row = frappe.db.get_value(
		"File",
		{"name": file, "attached_to_doctype": "Bukti Potong", "attached_to_name": name},
		["name", "file_url"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("That file is not attached to {0}.").format(name))
	# Don't leave bp_file pointing at a file that no longer exists.
	if frappe.db.get_value("Bukti Potong", name, "bp_file") == row.file_url:
		frappe.db.set_value("Bukti Potong", name, "bp_file", None)
	frappe.delete_doc("File", row.name, ignore_permissions=True)
	return {"attachments": _bp_attachments(name), "bp_file": frappe.db.get_value("Bukti Potong", name, "bp_file")}


@frappe.whitelist(methods=["POST"])
def set_bukti_potong_certificate(name, file_url=None):
	"""Promote one of the attached files to *the* certificate (what prints and
	what the list flags)."""
	_check("Bukti Potong", "write")
	if file_url and not frappe.db.exists(
		"File", {"file_url": file_url, "attached_to_doctype": "Bukti Potong", "attached_to_name": name}
	):
		frappe.throw(_("That file is not attached to {0}.").format(name))
	frappe.db.set_value("Bukti Potong", name, "bp_file", file_url or None)
	return {"bp_file": file_url or None}


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
def list_imports(txt=None, filters=None, order_by=None, start=0, page_length=20):
	"""Imports for the shared ListView — same contract as list_exports."""
	_check("Coretax Faktur Import")
	flt_list = to_getlist_filters(filters, IMPORT_FILTER_FIELDS)
	or_filters = {"name": ["like", f"%{txt}%"]} if txt else None
	rows = frappe.get_all(
		"Coretax Faktur Import",
		filters=flt_list,
		or_filters=or_filters,
		fields=["name", "import_file", "status", "summary", "creation"],
		order_by=resolve_order_by(order_by, IMPORT_ORDER_FIELDS, "creation desc"),
		start=int(start),
		page_length=int(page_length),
	)
	total = capped_total("Coretax Faktur Import", filters=flt_list, or_filters=or_filters)
	return {"items": rows, "total": total, "has_next": int(start) + len(rows) < total, "meta": {}}


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
	from erpbio_indonesia_localization.doc_events.sales_invoice import (
		PPN_TREATMENT,
		dpp_base_for,
		govt_notes,
	)

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
		"journal_entry": doc.get("eil_wapu_journal_entry"),
		"docstatus": doc.docstatus,
		"net_total": flt(doc.base_net_total),
		"grand_total": flt(doc.base_grand_total),
		# The two bases a rate can apply to, so the panel previews the figure the
		# server will actually save. See dpp_base_for().
		"vat_base": flt(dpp_base_for(doc, {"treatment": PPN_TREATMENT})),
		"billed_base": flt(dpp_base_for(doc, {"base": "Net Total + Charges"})),
		"bases": _govt_bases(),
		"outstanding": flt(doc.outstanding_amount),
		"can_edit": not blocker and frappe.has_permission("Sales Invoice", "write", sales_invoice),
		"blocked_reason": blocker,
		"notes": govt_notes(doc),
		"charges": [
			{
				"name": r.name,
				"treatment": r.treatment,
				"account": r.account,
				"rate": flt(r.rate),
				"amount": flt(r.amount),
				"base": r.base or "Automatic",
				"show_on_print": cint(r.show_on_print),
				"clear_on_payment": cint(r.clear_on_payment),
				"description": r.description,
			}
			for r in doc.get("eil_govt_charges") or []
		],
	}


def _govt_bases():
	f = frappe.get_meta("EIL Govt Tax Charge").get_field("base")
	return [o for o in (f.options or "").split("\n") if o]


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
	was_pemungut = cint(doc.get("eil_is_pemungut"))
	doc.eil_is_pemungut = 1 if rows else 0
	from erpbio_indonesia_localization.doc_events.sales_invoice import (
		apply_treatment_rules,
		dpp_base_for,
		restore_output_vat,
	)

	if was_pemungut and not rows:
		# Back to an ordinary sale: give it back the output VAT the government
		# strip removed, or it goes out carrying no tax at all.
		restored = restore_output_vat(doc)
		if restored:
			frappe.msgprint(
				_("Restored {0} to Taxes and Charges: this is no longer a government sale, so the PPN applies normally.").format(
					", ".join(sorted(restored))
				),
				title=_("Ordinary sale"),
				indicator="blue",
			)

	# Saving a SUBMITTED invoice does not re-run the validate hook, so this path
	# has to apply the invoice's own rules itself rather than rely on them.
	doc.set("eil_govt_charges", [])
	for r in rows:
		if not r.get("account"):
			continue
		amount = flt(r.get("amount"))
		rate = flt(r.get("rate"))
		base = dpp_base_for(doc, r)
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
				"base": r.get("base") or "Automatic",
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


# ----------------------------------------------------- hover previews + DocActions
#
# Backends for the shared DocPreview directive and DocActions menu. Both are
# parameterised by module on the frontend, so they point here rather than at
# erpbio_general — this app keeps working with that app absent.

# Allowlisted so a link can never be used to read an arbitrary doctype.
_PREVIEW_DOCTYPES = {
	"Sales Invoice",
	"Purchase Invoice",
	"Customer",
	"Supplier",
	"Coretax Faktur Export",
	"Coretax Faktur Import",
	"Bukti Potong",
}


@frappe.whitelist()
def get_doc_preview(doctype, name):
	"""Small hover card for a document link — the tax-relevant fields for each."""
	if doctype not in _PREVIEW_DOCTYPES:
		frappe.throw(_("Preview not available for {0}").format(doctype))
	if not frappe.has_permission(doctype, "read", doc=name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	meta = frappe.get_meta(doctype)
	title_field = meta.title_field if meta.title_field else None
	base = frappe.db.get_value(doctype, name, ["name"] + ([title_field] if title_field else []), as_dict=True)
	if not base:
		frappe.throw(_("{0} not found").format(doctype), frappe.DoesNotExistError)

	fields = []
	if doctype == "Sales Invoice":
		# The faktur fields are the whole point of a preview here.
		d = frappe.db.get_value(
			doctype, name,
			["status", "grand_total", "currency", "eil_faktur_number", "eil_faktur_status", "eil_kode_transaksi"],
			as_dict=True,
		)
		fields = [
			("Status", d.status),
			("Total", f"{d.currency} {flt(d.grand_total):,.2f}"),
			("Kode", d.eil_kode_transaksi),
			("Faktur", d.eil_faktur_number),
			("e-Faktur", d.eil_faktur_status),
		]
	elif doctype == "Purchase Invoice":
		d = frappe.db.get_value(doctype, name, ["status", "grand_total", "currency", "bill_no"], as_dict=True)
		fields = [("Status", d.status), ("Total", f"{d.currency} {flt(d.grand_total):,.2f}"), ("Supplier Bill", d.bill_no)]
	elif doctype in ("Customer", "Supplier"):
		party_field = "customer_name" if doctype == "Customer" else "supplier_name"
		d = frappe.db.get_value(doctype, name, [party_field, "tax_id"], as_dict=True)
		fields = [("Name", d.get(party_field)), ("NPWP", d.tax_id)]
	elif doctype == "Coretax Faktur Export":
		d = frappe.db.get_value(doctype, name, ["company", "from_date", "to_date", "status"], as_dict=True)
		fields = [("Company", d.company), ("Period", f"{d.from_date} → {d.to_date}"), ("Status", d.status)]
	elif doctype == "Coretax Faktur Import":
		d = frappe.db.get_value(doctype, name, ["status", "summary"], as_dict=True)
		fields = [("Status", d.status), ("Result", d.summary)]
	elif doctype == "Bukti Potong":
		d = frappe.db.get_value(
			doctype, name, ["direction", "tax_type", "tax_amount", "bp_number", "status"], as_dict=True
		)
		fields = [
			("Direction", d.direction),
			("Type", d.tax_type),
			("Withheld", f"{flt(d.tax_amount):,.2f}"),
			("No", d.bp_number),
			("Status", d.status),
		]

	return {
		"doctype": doctype,
		"name": name,
		"title": (base.get(title_field) if title_field else None) or name,
		"image": None,
		"fields": [{"label": label, "value": value} for label, value in fields if value],
	}


# Only the app's own documents are printable/emailable from here.
DOCACTION_DOCTYPES = {"Coretax Faktur Export", "Coretax Faktur Import", "Bukti Potong"}


@frappe.whitelist()
def get_print_formats(doctype):
	"""Enabled print formats for a doctype, the default first, then Standard."""
	if doctype not in DOCACTION_DOCTYPES:
		frappe.throw(_("Unsupported doctype"))
	frappe.has_permission(doctype, "read", throw=True)
	default = (
		frappe.db.get_value(
			"Property Setter", {"doc_type": doctype, "property": "default_print_format"}, "value"
		)
		or frappe.get_meta(doctype).default_print_format
	)
	formats = frappe.get_all(
		"Print Format", filters={"doc_type": doctype, "disabled": 0}, pluck="name", order_by="name asc"
	)
	ordered = ([default] if default and default in formats else []) + [f for f in formats if f != default]
	# Frappe's built-in renderer, so there's always something to print.
	return ordered + ["Standard"]


@frappe.whitelist(methods=["POST"])
def email_document(doctype, name, recipient, subject=None, message=None, print_format=None):
	"""Email the document as a PDF attachment — e.g. sending a counterparty their
	bukti potong."""
	if doctype not in DOCACTION_DOCTYPES:
		frappe.throw(_("Unsupported doctype"))
	frappe.has_permission(doctype, "email", doc=name, throw=True)
	if not (recipient or "").strip():
		frappe.throw(_("Recipient is required"))
	frappe.sendmail(
		recipients=[recipient.strip()],
		subject=subject or f"{doctype} {name}",
		message=message or _("Please find {0} {1} attached.").format(_(doctype), name),
		reference_doctype=doctype,
		reference_name=name,
		attachments=[frappe.attach_print(doctype, name, print_format=print_format or None)],
	)
	return {"sent": True, "to": recipient.strip()}


# ------------------------------------------------------------------ notifications
# The bell reads core's own Notification Log — deliberately NOT erpbio_general's
# equivalent endpoint, which would make this app depend at runtime on that app
# being installed. Scoped to the session user, so no doctype permission applies.
@frappe.whitelist()
def get_notifications(limit=20):
	"""The user's recent Notification Log entries + unread count."""
	rows = frappe.get_all(
		"Notification Log",
		filters={"for_user": frappe.session.user},
		fields=["name", "subject", "type", "document_type", "document_name", "read", "creation", "from_user"],
		order_by="creation desc",
		limit=cint(limit) or 20,
	)
	unread = frappe.db.count("Notification Log", {"for_user": frappe.session.user, "read": 0})
	return {"items": rows, "unread": unread}


@frappe.whitelist(methods=["POST"])
def mark_notifications_read(names=None):
	"""Mark the given notifications (or all unread) as read."""
	if isinstance(names, str):
		names = frappe.parse_json(names or "null")
	filters = {"for_user": frappe.session.user, "read": 0}
	if names:
		filters["name"] = ["in", names]
	for n in frappe.get_all("Notification Log", filters=filters, pluck="name"):
		frappe.db.set_value("Notification Log", n, "read", 1, update_modified=False)
	return {"ok": True}


# ------------------------------------------------------------------- language
# Ported from erpbio_general.api.i18n rather than called, for the same reason as
# the notification endpoints: the mechanism is pure core (an enabled Language
# record + User.language, which frappe/translate.py::get_user_lang reads), so
# this app can offer the switch without depending on that app being installed.
# The preference follows the user everywhere they sign in, Desk included.
SUPPORTED_LANGUAGES = ("en", "id")


@frappe.whitelist()
def get_languages():
	"""What the switcher offers, in UI order — skipping any not enabled on the
	site, so we never offer a language with no catalog."""
	rows = frappe.get_all(
		"Language",
		filters={"name": ("in", SUPPORTED_LANGUAGES), "enabled": 1},
		fields=["name", "language_name"],
	)
	by_name = {r.name: r.language_name for r in rows}
	return [{"value": code, "label": by_name[code]} for code in SUPPORTED_LANGUAGES if code in by_name]


@frappe.whitelist(methods=["POST"])
def set_language(lang):
	"""Set the session user's UI language. The caller must reload afterwards —
	the catalog is baked into the server-rendered boot.

	Whitelisted because a plain user cannot write User.language themselves (that
	needs System Manager); this is scoped to frappe.session.user, so it only ever
	changes the caller's own preference.
	"""
	lang = (lang or "").strip()
	if not frappe.db.exists("Language", {"name": lang, "enabled": 1}):
		frappe.throw(_("{0} is not an enabled language.").format(frappe.bold(lang or "?")))
	# set_value, not get_doc().save(): User.on_update reacts to a language change
	# by overwriting the user's date_format/time_format/number_format defaults from
	# the Language record. Those are empty on the records shipped today, but a value
	# added there later would silently change how every amount renders.
	frappe.db.set_value("User", frappe.session.user, "language", lang)
	return {"lang": lang}
