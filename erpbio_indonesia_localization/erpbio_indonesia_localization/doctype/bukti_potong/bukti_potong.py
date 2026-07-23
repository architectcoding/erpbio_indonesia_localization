import frappe  # noqa: F401
from frappe.model.document import Document
from frappe.utils import flt


class BuktiPotong(Document):
	def validate(self):
		if not self.tax_amount and self.gross_amount and self.rate:
			self.tax_amount = flt(self.gross_amount) * flt(self.rate) / 100.0
		# the certificate number arriving is what makes it Received
		self.status = "Received" if self.bp_number else "Expected"
