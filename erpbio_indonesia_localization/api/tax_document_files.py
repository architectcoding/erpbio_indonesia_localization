"""File hooks for tax documents. Kept apart from api/tax_ocr.py, and importing
nothing from it, so a worker that loaded tax_ocr before a deploy still imports
this fresh when the new hook first fires."""

import frappe


def on_file_trash(doc, method=None):
	"""The reading is only ever about its file: once the document is removed there is
	nothing left for it to describe, and its link would block the removal. Values it
	already applied stay on the party; only the Undo for them goes with it."""
	for reading in frappe.get_all("Tax Document Reading", filters={"file": doc.name}, pluck="name"):
		frappe.delete_doc("Tax Document Reading", reading, ignore_permissions=True, force=True)
