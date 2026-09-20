"""Tax-document reader: an NPWP card, KTP or SKT/SPPKP attached to a Customer or Supplier is read in the
background and offered on the Tax Identity card.

Lifecycle of a Tax Document Reading:
  attach -> Queued -> (job) Suggested | Auto-applied | Nothing found | Failed -> Applied / Dismissed / (Undo)

Two rules carried over from the slide-manager sidecar, plus the owner's extension (2026-09-21):
  * The machine read is kept apart from the accepted value, and a person's correction overwrites it.
  * A value already on the party is NEVER overwritten by the machine: a difference is a suggestion.
  * A BLANK field may be filled automatically, but only from a number the document states twice (or a
    born-digital PDF), and only while Indonesia Tax Settings allows it. Every automatic fill is undoable.
Raw OCR text is never persisted (a KTP carries religion, marital status and a birth date).
"""
import json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from erpbio_indonesia_localization.tax_ocr import parser as tax_parser
from erpbio_indonesia_localization.tax_ocr import reader as tax_reader
from erpbio_indonesia_localization.tax_ocr.segment import recover_name

PARTY_TYPES = ("Customer", "Supplier")
# reading field -> party field
FIELD_MAP = {"tax_id": "tax_id", "id_type": "eil_id_type", "tax_name": "eil_tax_name", "tax_address": "eil_tax_address"}
DOCTYPE = "Tax Document Reading"


# --- settings ---------------------------------------------------------------------

def _flag(fieldname, default=True):
	"""A Check on the settings that is ON until someone turns it off. Read raw on purpose:
	get_single_value casts a missing row to 0, which would read a never-saved settings
	doc (every site on the day the field arrived) as "switched off"."""
	row = frappe.db.sql("select value from `tabSingles` where doctype=%s and field=%s", ("Indonesia Tax Settings", fieldname))
	value = row[0][0] if row else None
	return default if value in (None, "") else bool(int(value))


def enabled():
	return _flag("tax_document_ocr")


def auto_fill_enabled():
	return _flag("tax_document_ocr_auto_fill")


@frappe.whitelist()
def status():
	"""What the card may show: is the reader on, is the OCR pack installed, does it fill blanks."""
	return {"enabled": enabled(), "engine": tax_reader.engine_available(), "auto_fill": auto_fill_enabled()}


# --- reads ------------------------------------------------------------------------

def _party_fields(party_type):
	meta = frappe.get_meta(party_type)
	return {k: v for k, v in FIELD_MAP.items() if meta.has_field(v)}


def _party_values(party_type, party):
	fields = _party_fields(party_type)
	row = frappe.db.get_value(party_type, party, list(fields.values()), as_dict=True) or {}
	return {k: (row.get(v) or None) for k, v in fields.items()}


@frappe.whitelist()
def readings(party_type, party):
	"""The party's readings, newest first, with what the party currently holds so the card can
	say "differs" / "same" / "blank" per field. Dismissed readings stay out of the way."""
	_check_party(party_type, party, "read")
	rows = frappe.get_all(
		DOCTYPE,
		filters={"party_type": party_type, "party": party, "status": ["!=", "Dismissed"]},
		fields=["name", "file", "file_name", "status", "kind", "source", "confidence", "verified", "tax_id", "id_type",
		        "tax_name", "tax_address", "legal_form", "applied_fields", "previous_values", "applied_by", "applied_on",
		        "read_on", "notes", "error", "creation"],
		order_by="creation desc",
		limit=20,
	)
	current = _party_values(party_type, party)
	for r in rows:
		r["applied_fields"] = json.loads(r.applied_fields or "[]")
		r["comparison"] = {
			k: ("blank" if not current.get(k) else "same" if _same(k, r.get(k), current.get(k)) else "differs")
			for k in FIELD_MAP if r.get(k)
		}
	return {"readings": rows, "party_values": current, "fields": list(_party_fields(party_type)),
	        "can_write": frappe.has_permission(party_type, "write", doc=party), **status()}


def _same(key, a, b):
	if key == "tax_id":
		return re.sub(r"\D", "", a or "") == re.sub(r"\D", "", b or "")
	return re.sub(r"\s+", " ", (a or "").strip().casefold()) == re.sub(r"\s+", " ", (b or "").strip().casefold())


@frappe.whitelist(methods=["POST"])
def read_file(party_type, party, file):
	"""Read (again) one of the party's attached files, by request. Runs in the background;
	the card learns of the result over realtime or by asking `readings` again."""
	_check_party(party_type, party, "write")
	f = frappe.db.get_value("File", file, ["name", "file_name", "file_url", "attached_to_doctype", "attached_to_name"], as_dict=True)
	if not f or f.attached_to_doctype != party_type or f.attached_to_name != party:
		frappe.throw(_("That file is not attached to this {0}.").format(_(party_type)))
	if not tax_reader.supported(f.file_name or f.file_url):
		frappe.throw(_("Only images and PDFs can be read."))
	name = queue_reading(party_type, party, f, manual=True)
	return {"reading": name}


def queue_reading(party_type, party, file_row, manual=False):
	"""One reading per file. An automatic pass skips a file already read; a manual one re-reads it."""
	if not enabled() and not manual:
		return None
	if not tax_reader.supported(file_row.get("file_name") or file_row.get("file_url")):
		return None
	existing = frappe.db.get_value(DOCTYPE, {"file": file_row.name, "party_type": party_type, "party": party}, ["name", "status"], as_dict=True)
	if existing and not manual and existing.status not in ("Failed",):
		return existing.name
	if existing:
		doc = frappe.get_doc(DOCTYPE, existing.name)
		doc.update({"status": "Queued", "error": None, "notes": None, "applied_fields": None, "previous_values": None,
		            "applied_by": None, "applied_on": None})
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": DOCTYPE, "party_type": party_type, "party": party, "file": file_row.name,
		                      "file_name": file_row.get("file_name") or file_row.get("file_url"), "status": "Queued"})
		doc.insert(ignore_permissions=True)
	if frappe.flags.in_test:
		run_reading(doc.name)
	else:
		frappe.enqueue("erpbio_indonesia_localization.api.tax_ocr.run_reading", queue="long", timeout=600,
		               reading=doc.name, enqueue_after_commit=True)
	return doc.name


def run_reading(reading):
	"""The background job: acquire text, parse, apply the blank-field rule, tell the uploader."""
	doc = frappe.get_doc(DOCTYPE, reading)
	try:
		path = frappe.get_doc("File", doc.file).get_full_path()
		lines, source, confidence = _read_lines(path)
		result = tax_parser.parse(lines, source=source)
		name, legal_form = recover_name(result["tax_name"]) if result["tax_name"] else ("", None)
		doc.update({
			"source": source, "confidence": round(confidence, 2), "kind": result["kind"] or None, "verified": int(result["verified"]),
			"tax_id": result["tax_id"], "id_type": result["id_type"], "tax_name": name or None,
			"tax_address": result["tax_address"], "legal_form": legal_form, "notes": "\n".join(result["notes"]) or None,
			"read_on": now_datetime(), "error": None,
		})
		if not any(doc.get(k) for k in FIELD_MAP):
			doc.status = "Nothing found"
		else:
			applied = _auto_fill(doc)
			doc.status = "Auto-applied" if applied else "Suggested"
	except tax_reader.EngineMissing as e:
		doc.update({"status": "Failed", "error": str(e), "read_on": now_datetime()})
	except Exception:
		doc.update({"status": "Failed", "error": frappe.get_traceback()[-900:], "read_on": now_datetime()})
		frappe.log_error(title="Tax document reading failed", message=frappe.get_traceback())
	doc.save(ignore_permissions=True)
	frappe.publish_realtime("tax_document_reading", {"party_type": doc.party_type, "party": doc.party, "reading": doc.name,
	                                                  "status": doc.status}, user=doc.owner, after_commit=True)
	return doc.status


def _read_lines(path):
	if path.lower().endswith(tax_reader.PDF_EXT):
		# a born-digital PDF needs no engine at all; only the scan fallback does
		lines, source, confidence = tax_reader.read(path) if tax_reader.engine_available() else tax_reader.read_pdf_text_only(path)
	else:
		if not tax_reader.engine_available():
			raise tax_reader.EngineMissing(_("OCR engine not installed on this server (pip install rapidocr-onnxruntime)"))
		lines, source, confidence = tax_reader.read(path)
	return lines, source, confidence


# --- the blank-field rule -----------------------------------------------------------

def _auto_fill(doc):
	"""Fill what is BLANK on the party from what the document PROVES. Returns the fields written.

	nothing at all   : when the document's number disagrees with the one on record (wrong upload?).
	number + id type : only a verified number (stated twice, or born-digital PDF).
	name             : verified number on the same document AND the name reads cleanly (no glued
	                   token the site's vocabulary could not split), or a born-digital PDF.
	address          : same conditions as the name.
	Nothing is written over an existing value, whatever the read says."""
	if not auto_fill_enabled():
		return {}
	fields = _party_fields(doc.party_type)
	current = _party_values(doc.party_type, doc.party)
	proven = bool(doc.verified) or doc.source == "pdf-text"
	if current.get("tax_id") and doc.tax_id and not _same("tax_id", doc.tax_id, current["tax_id"]):
		return {}  # a document that disagrees on the number is a question, not an answer -- not even for the blanks beside it
	values = {}
	if proven and doc.tax_id and not current.get("tax_id"):
		values["tax_id"] = doc.tax_id
		if doc.id_type and "id_type" in fields:
			values["id_type"] = doc.id_type  # the pair goes together; a default TIN on an empty record is not information
	if proven and doc.tax_name and not current.get("tax_name") and "tax_name" in fields and _clean_text(doc.tax_name):
		values["tax_name"] = doc.tax_name
	if proven and doc.tax_address and not current.get("tax_address") and "tax_address" in fields and _clean_text(doc.tax_address):
		values["tax_address"] = doc.tax_address
	if not values:
		return {}
	_write_party(doc, values, current, auto=True)
	return values


def _clean_text(text):
	"""No glued run the segmenter could not split: a 14+ character alphabetic token is one."""
	return not re.search(r"[A-Z]{14,}", (text or "").upper())


def _write_party(doc, values, current, auto=False):
	fields = _party_fields(doc.party_type)
	frappe.db.set_value(doc.party_type, doc.party, {fields[k]: v for k, v in values.items()})
	doc.update({
		"applied_fields": json.dumps(sorted(values)),
		"previous_values": json.dumps({k: current.get(k) for k in values}),
		"applied_by": frappe.session.user,
		"applied_on": now_datetime(),
	})
	if not auto:
		doc.status = "Applied"


# --- a person decides -------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def apply(reading, fields=None, values=None):
	"""Write the chosen fields to the party. `fields` limits which; `values` lets the person
	correct the read first (their correction overwrites the machine's, as on the slide labels)."""
	doc = frappe.get_doc(DOCTYPE, reading)
	_check_party(doc.party_type, doc.party, "write")
	chosen = frappe.parse_json(fields) if fields else [k for k in FIELD_MAP if doc.get(k)]
	corrections = frappe.parse_json(values) if values else {}
	party_fields = _party_fields(doc.party_type)
	to_write = {}
	for k in chosen:
		if k not in party_fields:
			continue
		v = (corrections.get(k) if k in corrections else doc.get(k)) or None
		if v is None:
			continue
		if k == "tax_id":
			v = re.sub(r"\D", "", v)
			if len(v) not in (15, 16):
				frappe.throw(_("A Tax ID is 15 or 16 digits."))
			if len(v) == 15:
				v = "0" + v
			if "id_type" in party_fields and "id_type" not in chosen:
				to_write["id_type"] = tax_parser.id_type_for(v)
		to_write[k] = v.strip() if isinstance(v, str) else v
	if not to_write:
		frappe.throw(_("Nothing to apply."))
	for k, v in corrections.items():
		if k in FIELD_MAP and v is not None:
			doc.set(k, v)  # the reading now shows what was accepted
	current = _party_values(doc.party_type, doc.party)
	_write_party(doc, to_write, current)
	doc.save(ignore_permissions=True)
	return {"applied": sorted(to_write), "party_values": _party_values(doc.party_type, doc.party)}


@frappe.whitelist(methods=["POST"])
def dismiss(reading):
	doc = frappe.get_doc(DOCTYPE, reading)
	_check_party(doc.party_type, doc.party, "write")
	doc.status = "Dismissed"
	doc.save(ignore_permissions=True)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def undo(reading):
	"""Put back what the party held before this reading was applied (automatically or by hand)."""
	doc = frappe.get_doc(DOCTYPE, reading)
	_check_party(doc.party_type, doc.party, "write")
	previous = json.loads(doc.previous_values or "{}")
	if not previous:
		frappe.throw(_("This reading was not applied."))
	fields = _party_fields(doc.party_type)
	frappe.db.set_value(doc.party_type, doc.party, {fields[k]: v for k, v in previous.items() if k in fields})
	doc.update({"status": "Suggested", "applied_fields": None, "previous_values": None, "applied_by": None, "applied_on": None})
	doc.save(ignore_permissions=True)
	return {"party_values": _party_values(doc.party_type, doc.party)}


# --- triggers -----------------------------------------------------------------------------

def on_file_after_insert(doc, method=None):
	"""Desk uploads arrive with attached_to_* already set."""
	if doc.attached_to_doctype in PARTY_TYPES and doc.attached_to_name and not doc.attached_to_field:
		queue_reading(doc.attached_to_doctype, doc.attached_to_name, doc)


def on_files_attached(doctype, name, files):
	"""erpbio_general's `erpbio_files_attached` hook: the SPA uploads first and attaches after."""
	if doctype not in PARTY_TYPES:
		return
	for fname in files or []:
		row = frappe.db.get_value("File", fname, ["name", "file_name", "file_url"], as_dict=True)
		if row:
			queue_reading(doctype, name, row)


def _check_party(party_type, party, ptype):
	if party_type not in PARTY_TYPES:
		frappe.throw(_("Not a party"))
	if not party or not frappe.has_permission(party_type, ptype, doc=party):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
