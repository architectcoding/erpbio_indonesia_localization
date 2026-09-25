# Closes the e-Faktur loop: after the exported workbook is converted and
# uploaded, Coretax issues official faktur numbers. The taxpayer downloads the
# faktur list (Excel/CSV) from Coretax, and this tool writes those numbers,
# dates and statuses back onto the Sales Invoices.
#
# Matching keys on the Referensi column — the exporter stamps every faktur's
# Referensi with the Sales Invoice name precisely so DJP's data carries its own
# way home. Columns are found by header hints rather than fixed positions, so
# cosmetic changes to Coretax's download format don't break the import.

import datetime
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

# lowercase substrings that identify each column in the downloaded file
_REFERENSI_HINTS = ("referensi", "reference")
_NUMBER_HINTS = ("nomor faktur", "nomor seri", "tax invoice number", "taxinvoicenumber")
_DATE_HINTS = ("tanggal faktur", "tax invoice date", "taxinvoicedate")
_STATUS_HINTS = ("status",)

# DJP status → our Sales Invoice eil_faktur_status. AMENDED still means the
# faktur exists and is valid (it was replaced by a pengganti), so Approved.
_STATUS_MAP = [
	("APPROV", "Approved"),
	("AMEND", "Approved"),
	("CANCEL", "Cancelled"),
	("BATAL", "Cancelled"),
	("REJECT", "Rejected"),
	("TOLAK", "Rejected"),
]


class CoretaxFakturImport(Document):
	# ----------------------------------------------------------------- preview
	@frappe.whitelist()
	def preview(self):
		"""Parse the uploaded file, match every row to its Sales Invoice, and
		show what Apply would do — nothing is written yet."""
		rows = self._read_rows()
		header_idx, cols = self._detect_columns(rows)
		if cols["referensi"] is None or cols["number"] is None:
			frappe.throw(
				_(
					"Could not find the Referensi and Nomor Faktur columns. "
					"Upload the faktur list downloaded from Coretax (Excel or CSV)."
				)
			)

		self.set("rows", [])
		matched = 0
		for raw in rows[header_idx + 1 :]:
			referensi = _cell(raw, cols["referensi"])
			number = _cell(raw, cols["number"])
			if not (referensi or number):
				continue
			date = _parse_date(_cell(raw, cols["date"]))
			djp_status = _cell(raw, cols["status"])
			mapped = _map_status(djp_status, number)

			ok, doctype, si_name, message = self._match(referensi, number, mapped, djp_status)
			if ok:
				matched += 1
			self.append(
				"rows",
				{
					"referensi": referensi,
					"sales_invoice": si_name if doctype == "Sales Invoice" else None,
					"reference_doctype": doctype if doctype != "Sales Invoice" else None,
					"reference_name": si_name if doctype != "Sales Invoice" else None,
					"faktur_number": number,
					"faktur_date": date,
					"djp_status": djp_status,
					"mapped_status": mapped or "",
					"ok": 1 if ok else 0,
					"message": message,
				},
			)

		if not self.rows:
			frappe.throw(_("No data rows found below the header."))
		self.status = "Previewed"
		self.summary = _("{0} of {1} rows matched a Sales Invoice.").format(matched, len(self.rows))
		self.save()
		return {"total": len(self.rows), "matched": matched}

	def _match(self, referensi, number, mapped, djp_status=None):
		"""(ok, doctype, name, message). The Referensi is a Sales Invoice's name,
		or a source document's (a DP invoice's faktur uang muka — eil_faktur_sources)."""
		from erpbio_indonesia_localization.erpbio_indonesia_localization.doctype.coretax_faktur_export.coretax_faktur_export import (
			faktur_sources,
		)

		if not referensi:
			return False, None, None, _("no Referensi — cannot match to a Sales Invoice")
		doctype, number_field = "Sales Invoice", "eil_faktur_number"
		# a faktur cancelled in Coretax (Pembatalan) closes the approved faktur of an
		# invoice already cancelled here: the one import that may touch it (T-004)
		if mapped == "Cancelled" and number and frappe.db.exists(
			"Sales Invoice", {"name": referensi, "docstatus": 2, "eil_faktur_number": number}
		):
			return True, doctype, referensi, _("closes the faktur of the cancelled invoice")
		if not frappe.db.exists("Sales Invoice", {"name": referensi, "docstatus": 1}):
			doctype = next(
				(d for d in faktur_sources() if frappe.db.exists(d, {"name": referensi, "docstatus": 1})), None
			)
			if not doctype:
				return False, None, None, _("no submitted Sales Invoice named {0}").format(referensi)
			number_field = faktur_sources()[doctype].NUMBER_FIELD
		if not number:
			return False, doctype, referensi, _("row has no faktur number")
		if not mapped:
			# SAVED_INVALID never becomes final: Coretax refused the faktur as
			# saved, so it is a problem to fix and export again, not a wait (T-013)
			if "INVALID" in str(djp_status or "").upper():
				return False, doctype, referensi, _(
					"Coretax marked this faktur invalid ({0}) — correct the invoice, then release and export it again"
				).format(djp_status)
			return False, doctype, referensi, _("status not final yet — skipped")
		existing = frappe.db.get_value(doctype, referensi, number_field)
		if existing and existing != number:
			return True, doctype, referensi, _("will replace faktur number {0}").format(existing)
		return True, doctype, referensi, _("Ready")

	# ------------------------------------------------------------------- apply
	@frappe.whitelist()
	def apply(self):
		"""Write faktur number/date/status onto every matched Sales Invoice."""
		if self.status != "Previewed":
			frappe.throw(_("Run Preview first."))
		from erpbio_indonesia_localization.erpbio_indonesia_localization.doctype.coretax_faktur_export.coretax_faktur_export import (
			faktur_sources,
		)

		applied = 0
		for row in self.rows:
			if row.ok and row.reference_name and not row.sales_invoice:
				faktur_sources()[row.reference_doctype].mark(
					row.reference_name, row.mapped_status, row.faktur_number, row.faktur_date
				)
				row.db_set("message", _("Applied"))
				applied += 1
				continue
			if not (row.ok and row.sales_invoice):
				continue
			values = {"eil_faktur_number": row.faktur_number, "eil_faktur_status": row.mapped_status}
			if row.faktur_date:
				values["eil_faktur_date"] = row.faktur_date
			frappe.db.set_value("Sales Invoice", row.sales_invoice, values, update_modified=False)
			row.db_set("message", _("Applied"))
			applied += 1
		self.db_set("status", "Applied")
		self.db_set("summary", _("Applied to {0} Sales Invoices.").format(applied))
		return {"applied": applied}

	# ------------------------------------------------------------- file reading
	def _read_rows(self):
		if not self.import_file:
			frappe.throw(_("Attach the file downloaded from Coretax first."))
		f = frappe.get_doc("File", {"file_url": self.import_file})
		lower = (f.file_name or self.import_file).lower()
		if lower.endswith((".xlsx", ".xls")):
			from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

			rows = read_xlsx_file_from_attached_file(fcontent=f.get_content())
		elif lower.endswith(".csv"):
			from frappe.utils.csvutils import read_csv_content

			rows = read_csv_content(f.get_content(), use_sniffer=True)
		else:
			frappe.throw(_("Only .xlsx and .csv files are supported."))
		return [r for r in rows if any(c not in (None, "") for c in r)]

	def _detect_columns(self, rows):
		"""First row that carries a Referensi-ish and a Nomor-Faktur-ish cell is
		the header; return its index and each target column's position."""
		for idx, row in enumerate(rows[:20]):
			low = [str(c or "").lower().strip() for c in row]
			cols = {
				"referensi": _find(low, _REFERENSI_HINTS),
				"number": _find(low, _NUMBER_HINTS),
				"date": _find(low, _DATE_HINTS),
				"status": _find(low, _STATUS_HINTS),
			}
			if cols["referensi"] is not None and cols["number"] is not None:
				return idx, cols
		return 0, {"referensi": None, "number": None, "date": None, "status": None}


def _find(low_row, hints):
	for i, cell in enumerate(low_row):
		if any(h in cell for h in hints):
			return i
	return None


def _cell(row, idx):
	if idx is None or idx >= len(row):
		return ""
	value = row[idx]
	if isinstance(value, (datetime.date, datetime.datetime)):
		return value
	return str(value).strip() if value is not None else ""


def _parse_date(value):
	if not value:
		return None
	if isinstance(value, (datetime.date, datetime.datetime)):
		return getdate(value)
	text = str(value).strip()
	text = re.sub(r"[ T]\d{1,2}:\d{2}(:\d{2})?\s*$", "", text)  # drop a clock time
	for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
		try:
			return datetime.datetime.strptime(text, fmt).date()
		except ValueError:
			continue
	try:
		return getdate(text)
	except Exception:
		return None


def _map_status(djp_status, number):
	upper = str(djp_status or "").upper()
	for needle, mapped in _STATUS_MAP:
		if needle in upper:
			return mapped
	# a faktur list without a status column is a list of issued fakturs
	return "Approved" if number and not upper else None
