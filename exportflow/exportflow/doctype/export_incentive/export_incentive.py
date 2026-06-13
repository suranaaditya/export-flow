# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_years, flt, getdate


class ExportIncentive(Document):
	def validate(self):
		if not self.company:
			self.company = (
				frappe.db.get_value("Export Shipment", self.shipment, "company")
				if self.shipment
				else None
			)
		if not self.company:
			from exportflow.company import exportflow_company

			self.company = exportflow_company()
		self.pull_shipment_basis()
		self.compute_amount()
		self.set_scrip_expiry()

	def pull_shipment_basis(self):
		"""Default the shipping-bill identifiers from the linked shipment when
		blank — the incentive is claimed against that bill."""
		if self.shipment and not self.shipping_bill_no:
			sb = frappe.db.get_value(
				"Export Shipment", self.shipment, ["shipping_bill_number", "shipping_bill_date"]
			)
			if sb:
				self.shipping_bill_no, self.shipping_bill_date = sb

	def compute_amount(self):
		"""FOB × applied rate. Recomputes when the basis changes so a corrected
		rate flows through, but leaves a scroll-pinned override (amount typed
		while basis unchanged) alone. A non-earning claim carries no amount."""
		if self.status in ("Not Applicable", "Cancelled"):
			return
		if not (self.fob_value and self.rate_pct):
			return
		formula = flt(flt(self.fob_value) * flt(self.rate_pct) / 100.0, 2)
		if not self.amount:
			self.amount = formula
			return
		before = self.get_doc_before_save()
		if before and (flt(before.fob_value) != flt(self.fob_value) or flt(before.rate_pct) != flt(self.rate_pct)):
			prev = flt(flt(before.fob_value) * flt(before.rate_pct) / 100.0, 2)
			if flt(self.amount) == prev:  # was formula-driven, not a manual override
				self.amount = formula

	def set_scrip_expiry(self):
		"""RoDTEP scrips are valid 2 years; recompute when the scrip date is
		corrected (keep a deliberate manual expiry otherwise)."""
		if self.scheme != "RoDTEP" or not self.scrip_date:
			return
		if self.is_new() or self.has_value_changed("scrip_date") or not self.scrip_expiry:
			self.scrip_expiry = add_years(getdate(self.scrip_date), 2)
