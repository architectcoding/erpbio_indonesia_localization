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

			ok, si_name, message = self._match(referensi, number, mapped)
			if ok:
				matched += 1
			self.append(
				"rows",
				{
					"referensi": referensi,
					"sales_invoice": si_name,
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

	def _match(self, referensi, number, mapped):
		if not referensi:
			return False, None, _("no Referensi — cannot match to a Sales Invoice")
		if not frappe.db.exists("Sales Invoice", {"name": referensi, "docstatus": 1}):
			return False, None, _("no submitted Sales Invoice named {0}").format(referensi)
		if not number:
			return False, referensi, _("row has no faktur number")
		if not mapped:
			return False, referensi, _("status not final yet — skipped")
		existing = frappe.db.get_value("Sales Invoice", referensi, "eil_faktur_number")
		if existing and existing != number:
			return True, referensi, _("will replace faktur number {0}").format(existing)
		return True, referensi, _("Ready")

	# ------------------------------------------------------------------- apply
	@frappe.whitelist()
	def apply(self):
		"""Write faktur number/date/status onto every matched Sales Invoice."""
		if self.status != "Previewed":
			frappe.throw(_("Run Preview first."))
		applied = 0
		for row in self.rows:
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
