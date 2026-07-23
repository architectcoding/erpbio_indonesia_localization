import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BuktiPotong(Document):
	def validate(self):
		if self.direction == "Issued":
			if not self.supplier:
				frappe.throw(_("An issued Bukti Potong needs the Supplier it was issued to."))
		elif not self.customer:
			frappe.throw(_("A received Bukti Potong needs the Customer who withheld."))

		if not self.tax_amount and self.gross_amount and self.rate:
			self.tax_amount = flt(self.gross_amount) * flt(self.rate) / 100.0

		# the certificate number is what advances the lifecycle in both directions
		if self.direction == "Issued":
			self.status = "Reported" if self.bp_number else "To Report"
		else:
			self.status = "Received" if self.bp_number else "Expected"
