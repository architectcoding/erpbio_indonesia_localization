# Copyright (c) 2026, Biozatix and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TaxDocumentReading(Document):
	"""One document, one reading. The lifecycle lives in api/tax_ocr.py: queue -> read ->
	(auto-apply the blanks it can prove | suggest) -> a person applies, dismisses or undoes."""

	pass
