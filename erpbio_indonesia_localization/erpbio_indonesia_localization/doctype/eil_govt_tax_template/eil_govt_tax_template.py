import frappe
from frappe.model.document import Document


class EILGovtTaxTemplate(Document):
	def validate(self):
		self._apply_treatment_rules()
		self._validate_accounts_belong_to_company()
		self._enforce_single_default()

	def _apply_treatment_rules(self):
		"""Keep the stored rows consistent with their treatment, so an invoice
		built from this template inherits the right settlement behaviour."""
		from erpbio_indonesia_localization.doc_events.sales_invoice import apply_treatment_rules

		for row in self.charges or []:
			apply_treatment_rules(row)

	def _validate_accounts_belong_to_company(self):
		"""An account carries its own company in ERPNext, so a template pointing at
		another company's CoA would post to the wrong books."""
		for row in self.charges or []:
			if not row.account:
				continue
			owner = frappe.db.get_value("Account", row.account, "company")
			if owner and owner != self.company:
				frappe.throw(
					frappe._("Row {0}: account {1} belongs to {2}, not {3}.").format(
						row.idx, row.account, owner, self.company
					)
				)

	def _enforce_single_default(self):
		if not self.is_default:
			return
		others = frappe.get_all(
			"EIL Govt Tax Template",
			filters={"company": self.company, "is_default": 1, "name": ["!=", self.name]},
			pluck="name",
		)
		for other in others:
			frappe.db.set_value("EIL Govt Tax Template", other, "is_default", 0, update_modified=False)
