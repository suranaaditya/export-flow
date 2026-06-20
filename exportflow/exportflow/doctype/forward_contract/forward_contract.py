"""Forward (FX) contract — an exporter's hedge: a bank agreement to sell foreign
currency at a locked rate on a future date. Realizations DRAW DOWN against it; the
contract tracks utilization, the locked INR value, and its status lifecycle."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate

EPS = 0.01
# realization statuses that do NOT consume forward cover
NON_DRAWING = ("Cancelled", "Written Off")


class ForwardContract(Document):
	def validate(self):
		if not self.company:
			from exportflow.company import exportflow_company

			self.company = exportflow_company()
		if flt(self.contract_amount) <= 0:
			frappe.throw(_("Contract amount must be greater than zero."))
		if flt(self.forward_rate) <= 0:
			frappe.throw(_("Forward rate must be greater than zero."))
		if self.booking_date and self.maturity_date and getdate(self.maturity_date) < getdate(self.booking_date):
			frappe.throw(_("Maturity date cannot be before the booking date."))
		self.inr_value = flt(flt(self.contract_amount) * flt(self.forward_rate), 2)
		self.recompute_utilization()
		if flt(self.utilized_amount) > flt(self.contract_amount) + EPS:
			frappe.msgprint(
				_("This forward is over-utilized: {0} {1} drawn against {2} of cover. Review the linked realizations or raise the contract amount.").format(
					self.currency or "", flt(self.utilized_amount), flt(self.contract_amount)
				),
				indicator="orange",
				title=_("Over-utilized forward"),
			)

	def recompute_utilization(self, exclude: str | None = None):
		"""Σ realized FCY of the realizations linked to this contract → utilized /
		outstanding cover / status. `exclude` drops a realization about to be deleted."""
		drawn = 0.0
		if not self.is_new():
			for r in frappe.get_all(
				"Export Realization",
				filters={"forward_contract": self.name},
				fields=["name", "amount_received", "status"],
			):
				if r.name != exclude and r.status not in NON_DRAWING:
					drawn += flt(r.amount_received)
		self.utilized_amount = flt(drawn, 2)
		self.outstanding_amount = flt(max(0.0, flt(self.contract_amount) - drawn), 2)
		self.status = self._derive_status(drawn)
		self.hedge_note = f"{self.currency or ''} {self.utilized_amount:,.2f} of {flt(self.contract_amount):,.2f} drawn".strip()

	def _derive_status(self, drawn: float) -> str:
		# Cancelled is a deliberate manual state and wins; otherwise derive
		if self.status == "Cancelled":
			return "Cancelled"
		if drawn + EPS >= flt(self.contract_amount):
			return "Fully Utilized"
		if self.maturity_date and getdate(self.maturity_date) < getdate(nowdate()):
			return "Matured"
		if drawn > EPS:
			return "Partially Utilized"
		return "Open"


def recompute_for_realization(doc, method=None):
	"""Export Realization on_update / on_trash → keep its forward contract's utilization
	current (recompute the new link AND a previous one when the link was changed)."""
	names = set()
	if doc.get("forward_contract"):
		names.add(doc.forward_contract)
	before = doc.get_doc_before_save()
	if before and before.get("forward_contract"):
		names.add(before.forward_contract)
	exclude = doc.name if method == "on_trash" else None
	for name in filter(None, names):
		if not frappe.db.exists("Forward Contract", name):
			continue
		fc = frappe.get_doc("Forward Contract", name)
		fc.recompute_utilization(exclude=exclude)
		frappe.db.set_value(
			"Forward Contract", name,
			{
				"utilized_amount": fc.utilized_amount,
				"outstanding_amount": fc.outstanding_amount,
				"status": fc.status,
				"hedge_note": fc.hedge_note,
			},
			update_modified=False,
		)
