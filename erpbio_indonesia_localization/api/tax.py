# Whitelisted API for the /erpbio-tax SPA. Thin wrappers over the Coretax
# doctypes so the frontend never needs the generic frappe.client surface.
# Permission model: everything here requires rights on the underlying doctype
# (Accounts Manager per the doctype permissions).

import frappe
from frappe import _
from frappe.utils import flt


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
def list_bukti_potong(start=0, page_length=50):
	_check("Bukti Potong")
	return frappe.get_all(
		"Bukti Potong",
		fields=[
			"name",
			"customer",
			"tax_type",
			"sales_invoice",
			"payment_entry",
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
		"customer",
		"tax_type",
		"sales_invoice",
		"payment_entry",
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
		# common statutory rates offered as defaults; the user can override
		"default_rates": {"PPh 22": 1.5, "PPh 23": 2.0, "PPh 4(2)": 10.0},
	}


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
			{"account": r.account, "tax_type": r.tax_type, "rate": flt(r.rate)}
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
					{"account": row["account"], "tax_type": row.get("tax_type") or "PPh 22", "rate": row.get("rate")},
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
