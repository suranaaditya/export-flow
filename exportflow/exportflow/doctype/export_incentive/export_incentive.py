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
		"""FOB × applied rate, unless the user pinned an explicit amount (the
		scroll value can differ from the formula due to per-unit caps)."""
		if not self.amount and self.fob_value and self.rate_pct:
			self.amount = flt(flt(self.fob_value) * flt(self.rate_pct) / 100.0, 2)

	def set_scrip_expiry(self):
		if self.scheme == "RoDTEP" and self.scrip_date and not self.scrip_expiry:
			self.scrip_expiry = add_years(getdate(self.scrip_date), 2)
