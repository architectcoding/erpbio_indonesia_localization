"""The reading lifecycle end to end, with the OCR engine stubbed: attach -> read -> the blank-field
rule -> a person applies, corrects, undoes. What is pinned here is the POLICY, not the engine:
a verified number fills a blank; nothing ever overwrites; an unverified read only suggests;
the settings switch both off.
"""
import io
import json
from unittest import mock

import frappe

try:
	from frappe.tests import IntegrationTestCase as _TestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as _TestCase

from erpbio_indonesia_localization.api import tax_ocr
from erpbio_indonesia_localization.tax_ocr import reader as tax_reader
from erpbio_indonesia_localization.tests.test_tax_ocr_parser import KTP, NEW_CARD, OLD_CARD, SKT

CUSTOMER = "_Test OCR Customer Sam Jaya Perkasa"


def _bytes_for(name):
	"""Frappe strips EXIF on image uploads, so an image file needs real image bytes."""
	ext = name.rsplit(".", 1)[-1].lower()
	if ext in ("png", "jpg", "jpeg", "pdf"):  # Frappe also opens a PDF with pypdf on insert
		from PIL import Image

		buf = io.BytesIO()
		Image.new("RGB", (4, 4), (250, 220, 120)).save(buf, {"png": "PNG", "pdf": "PDF"}.get(ext, "JPEG"))
		return buf.getvalue()
	return b"x"


IDENTITY = ("tax_id", "eil_id_type", "eil_tax_name", "eil_tax_address")


class TestTaxDocumentReading(_TestCase):
	def setUp(self):
		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc({"doctype": "Customer", "customer_name": CUSTOMER, "customer_type": "Company",
			                "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
			                "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name")}).insert(ignore_permissions=True)
		frappe.db.set_value("Customer", CUSTOMER, {f: None for f in IDENTITY})
		frappe.db.delete("Tax Document Reading", {"party": CUSTOMER})
		frappe.cache.delete_value("eil_tax_ocr_vocabulary")  # the customer's own name teaches SAM / JAYA / PERKASA
		# Singles writes outlive the test transaction on some benches: put the switches back.
		for flag in ("tax_document_ocr", "tax_document_ocr_auto_fill"):
			before = frappe.db.get_single_value("Indonesia Tax Settings", flag)
			self.addCleanup(frappe.db.set_single_value, "Indonesia Tax Settings", flag, 1 if before is None else before)
			frappe.db.set_single_value("Indonesia Tax Settings", flag, 1)
		frappe.set_user("Administrator")

	def _attach(self, lines, source="ocr", name="npwp.png", engine=True):
		"""A File attached from the Desk (attached_to_* set on insert), read through the stub."""
		with mock.patch.object(tax_reader, "engine_available", return_value=engine), \
				mock.patch.object(tax_reader, "read", return_value=(lines, source, 0.9)), \
				mock.patch.object(tax_reader, "read_pdf_text_only", return_value=(lines, "pdf-text", 1.0)):
			f = frappe.get_doc({"doctype": "File", "file_name": name, "is_private": 1, "content": _bytes_for(name),
			                    "attached_to_doctype": "Customer", "attached_to_name": CUSTOMER}).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("File", f.name, force=True, ignore_permissions=True))
		reading = frappe.db.get_value("Tax Document Reading", {"file": f.name}, "name")
		return frappe.get_doc("Tax Document Reading", reading) if reading else None

	def _customer(self):
		return frappe.db.get_value("Customer", CUSTOMER, IDENTITY, as_dict=True)

	# --- the blank-field rule ---------------------------------------------------------

	def test_a_verified_card_fills_the_blank_identity_and_can_be_undone(self):
		r = self._attach(NEW_CARD)
		self.assertEqual(r.status, "Auto-applied")
		self.assertTrue(r.verified)
		c = self._customer()
		self.assertEqual((c.tax_id, c.eil_id_type, c.eil_tax_name), ("0708958483428001", "TIN", "SAM JAYA PERKASA"))
		self.assertEqual(r.legal_form, "PERSEROAN TERBATAS - BADAN")
		self.assertIn("40172", c.eil_tax_address)
		self.assertEqual(set(json.loads(r.applied_fields)), {"tax_id", "id_type", "tax_name", "tax_address"})
		tax_ocr.undo(r.name)
		self.assertEqual(self._customer(), {f: None for f in IDENTITY})
		self.assertEqual(frappe.db.get_value("Tax Document Reading", r.name, "status"), "Suggested")

	def test_a_value_already_on_the_customer_is_never_overwritten(self):
		frappe.db.set_value("Customer", CUSTOMER, {"tax_id": "1234567890123456", "eil_id_type": "TIN"})
		r = self._attach(NEW_CARD)
		self.assertEqual(r.status, "Suggested")
		self.assertEqual(self._customer().tax_id, "1234567890123456")
		# the blanks beside it are filled? No: a card that disagrees on the number is a question, not an answer
		self.assertIsNone(self._customer().eil_tax_name)
		listing = tax_ocr.readings("Customer", CUSTOMER)
		self.assertEqual(listing["readings"][0]["comparison"]["tax_id"], "differs")

	def test_an_unverified_read_is_only_a_suggestion(self):
		r = self._attach(OLD_CARD)
		self.assertEqual(r.status, "Suggested")
		self.assertFalse(r.verified)
		self.assertEqual(r.tax_id, "0012345678901000")
		self.assertIsNone(self._customer().tax_id)

	def test_a_ktp_is_a_suggestion_typed_nik(self):
		r = self._attach(KTP, name="ktp.jpg")
		self.assertEqual((r.status, r.kind, r.id_type, r.tax_name), ("Suggested", "KTP", "NIK", "ANDI CONTOH PRATAMA"))
		self.assertIsNone(self._customer().tax_id)

	def test_a_born_digital_pdf_reads_without_the_engine_and_is_trusted(self):
		r = self._attach(SKT, source="pdf-text", name="skt.pdf", engine=False)
		self.assertEqual((r.status, r.source, r.kind), ("Auto-applied", "pdf-text", "Letter"))
		self.assertEqual(self._customer().tax_id, "0987654321012000")

	def test_an_image_without_the_engine_fails_loudly_not_silently(self):
		r = self._attach(NEW_CARD, engine=False)
		self.assertEqual(r.status, "Failed")
		self.assertIn("OCR engine", r.error)
		self.assertIsNone(self._customer().tax_id)

	# --- a person decides -------------------------------------------------------------------

	def test_apply_takes_the_persons_correction_over_the_machine_read(self):
		r = self._attach(OLD_CARD)
		out = tax_ocr.apply(r.name, values=json.dumps({"tax_name": "PT Contoh Sejahtera Abadi Tbk", "tax_id": "01.234.567.8-901.000"}))
		self.assertEqual(set(out["applied"]), {"tax_id", "id_type", "tax_name", "tax_address"})
		c = self._customer()
		self.assertEqual((c.tax_id, c.eil_id_type, c.eil_tax_name), ("0012345678901000", "TIN", "PT Contoh Sejahtera Abadi Tbk"))
		r.reload()
		self.assertEqual((r.status, r.tax_name), ("Applied", "PT Contoh Sejahtera Abadi Tbk"))

	def test_dismissed_readings_leave_the_card(self):
		r = self._attach(OLD_CARD)
		tax_ocr.dismiss(r.name)
		self.assertEqual(tax_ocr.readings("Customer", CUSTOMER)["readings"], [])

	def test_a_manual_re_read_replaces_the_earlier_reading_of_the_same_file(self):
		r = self._attach(OLD_CARD)
		with mock.patch.object(tax_reader, "engine_available", return_value=True), \
				mock.patch.object(tax_reader, "read", return_value=(NEW_CARD, "ocr", 0.9)):
			tax_ocr.read_file("Customer", CUSTOMER, r.file)
		self.assertEqual(frappe.db.count("Tax Document Reading", {"file": r.file}), 1)
		self.assertEqual(frappe.db.get_value("Tax Document Reading", r.name, "status"), "Auto-applied")

	# --- switches and boundaries -------------------------------------------------------------

	def test_the_reader_switch_stops_automatic_reads(self):
		frappe.db.set_single_value("Indonesia Tax Settings", "tax_document_ocr", 0)
		self.assertIsNone(self._attach(NEW_CARD))

	def test_the_auto_fill_switch_leaves_a_verified_card_as_a_suggestion(self):
		frappe.db.set_single_value("Indonesia Tax Settings", "tax_document_ocr_auto_fill", 0)
		r = self._attach(NEW_CARD)
		self.assertEqual(r.status, "Suggested")
		self.assertIsNone(self._customer().tax_id)

	def test_files_that_are_not_documents_are_ignored(self):
		self.assertIsNone(self._attach(NEW_CARD, name="price list.xlsx"))

	def test_the_spa_attach_hook_reaches_the_same_reader(self):
		"""erpbio_general attaches by a db write after upload; it tells us through erpbio_files_attached."""
		f = frappe.get_doc({"doctype": "File", "file_name": "npwp2.png", "is_private": 1, "content": _bytes_for("npwp2.png")}).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("File", f.name, force=True, ignore_permissions=True))
		frappe.db.set_value("File", f.name, {"attached_to_doctype": "Customer", "attached_to_name": CUSTOMER})
		with mock.patch.object(tax_reader, "engine_available", return_value=True), \
				mock.patch.object(tax_reader, "read", return_value=(NEW_CARD, "ocr", 0.9)):
			tax_ocr.on_files_attached("Customer", CUSTOMER, [f.name])
		self.assertEqual(frappe.db.get_value("Tax Document Reading", {"file": f.name}, "status"), "Auto-applied")

	def test_readings_need_read_and_apply_needs_write_on_the_party(self):
		r = self._attach(OLD_CARD)
		guest = "_test_ocr_outsider@example.com"
		if not frappe.db.exists("User", guest):
			frappe.get_doc({"doctype": "User", "email": guest, "first_name": "OCR Outsider", "user_type": "Website User",
			                "send_welcome_email": 0}).insert(ignore_permissions=True)
			self.addCleanup(lambda: frappe.delete_doc("User", guest, force=True, ignore_permissions=True))
		frappe.set_user(guest)
		self.addCleanup(frappe.set_user, "Administrator")
		with self.assertRaises(frappe.PermissionError):
			tax_ocr.readings("Customer", CUSTOMER)
		with self.assertRaises(frappe.PermissionError):
			tax_ocr.apply(r.name)

	def test_a_document_that_was_read_can_still_be_removed(self):
		# not force=True (which skips the link check, as the cleanup does): the panel's remove button
		r = self._attach(NEW_CARD)
		frappe.delete_doc("File", r.file, ignore_permissions=True)
		self.assertFalse(frappe.db.exists("File", r.file))
		self.assertFalse(frappe.db.exists("Tax Document Reading", r.name))
		# what it already filled stays on the customer
		self.assertEqual(self._customer().tax_id, "0708958483428001")
		# and a job still queued for it finds nothing to do rather than failing
		tax_ocr.run_reading(r.name)
