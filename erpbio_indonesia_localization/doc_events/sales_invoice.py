# Sales Invoice — WAPU/Bendahara (government-collected PPN) + government withholding.
#
# A tax row tagged `eil_govt_tax_treatment` is money the government handles, not
# money we bill the customer: it must DEDUCT from the receivable and DEBIT its
# own asset account (Piutang PPN Bendahara / PPh 22 Dibayar di Muka) — never
# credit output VAT. ERPNext's native way to make a *sales* tax deduct is a
# negative rate (the `add_deduct_tax="Deduct"` toggle is gated to purchase
# doctypes in erpnext/controllers/taxes_and_totals.py), so we normalise these
# rows to a negative rate *before* the tax engine runs. The result, verified:
#
#     net_total 100M ─ PPN 11M ─ PPh22 1.5M = grand_total 87.5M (= Piutang Usaha)
#     Dr Piutang PPN Bendahara / Dr PPh 22 / Dr Piutang Usaha / Cr Penjualan
#
# The printed faktur re-displays these rows positive (see the print format) so
# the government still sees Sub Total 100M / PPN 11% / Grand Total 111M.
#
# Idempotent: -abs(rate) is stable across re-saves.

from frappe.utils import flt


def before_validate(doc, method=None):
	for tax in doc.get("taxes") or []:
		if tax.get("eil_govt_tax_treatment"):
			tax.rate = -abs(flt(tax.rate))
