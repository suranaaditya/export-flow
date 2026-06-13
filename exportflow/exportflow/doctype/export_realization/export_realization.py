# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_months, getdate

# FEMA realization window (RBI raised it from 9 to 15 months in late 2025;
# 18 months when the export is invoiced/settled in INR)
REALIZATION_MONTHS = 15
REALIZATION_MONTHS_INR = 18


class ExportRealization(Document):
	def validate(self):
		if not self.company and self.shipment:
			self.company = frappe.db.get_value("Export Shipment", self.shipment, "company")
		if not self.company:
			from exportflow.company import exportflow_company

			self.company = exportflow_company()
		self.pull_shipment_facts()
		self.set_due_date()

	def pull_shipment_facts(self):
		if not self.shipment:
			return
		shp = frappe.db.get_value(
			"Export Shipment", self.shipment, ["customer", "mode", "bl_date", "awb_date"], as_dict=True
		)
		if not shp:
			return
		if not self.customer:
			self.customer = shp.customer
		if not self.export_date:
			self.export_date = shp.awb_date if shp.mode == "Air" else shp.bl_date

	def set_due_date(self):
		if self.export_date and not self.due_date:
			months = REALIZATION_MONTHS_INR if self.currency == "INR" else REALIZATION_MONTHS
			self.due_date = add_months(getdate(self.export_date), months)

	def is_overdue(self, today=None) -> bool:
		from frappe.utils import nowdate

		if self.status in ("Realized", "eBRC Closed", "Written Off", "Cancelled"):
			return False
		return bool(self.due_date and getdate(self.due_date) < getdate(today or nowdate()))
