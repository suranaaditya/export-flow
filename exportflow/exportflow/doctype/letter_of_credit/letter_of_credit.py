# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

DEFAULT_ALERT_THRESHOLDS = (15, 7, 3)

# statuses in which date alerts are still relevant
OPEN_STATUSES = ("Received", "Active")


class LetterofCredit(Document):  # noqa: N801 — frappe derives "LetterofCredit" from the doctype name
	def validate(self):
		self.validate_sales_order()
		self.set_currency_from_so()
		self.validate_dates()
		self.validate_tolerance()
		self.get_alert_days()  # throws early on a malformed thresholds string

	def validate_sales_order(self):
		if not self.sales_order:
			frappe.throw(_("Sales Order is required"))
		docstatus = frappe.db.get_value("Sales Order", self.sales_order, "docstatus")
		if docstatus is None:
			frappe.throw(_("Sales Order {0} not found").format(self.sales_order))
		if docstatus != 1:
			frappe.throw(
				_("Sales Order {0} must be submitted before recording an LC").format(self.sales_order)
			)

	def set_currency_from_so(self):
		self.currency = frappe.db.get_value("Sales Order", self.sales_order, "currency")

	def validate_dates(self):
		if self.expiry_date and self.latest_shipment_date:
			if getdate(self.expiry_date) < getdate(self.latest_shipment_date):
				frappe.throw(_("Expiry date cannot be before the latest shipment date"))
		if self.issue_date and self.expiry_date and getdate(self.expiry_date) < getdate(self.issue_date):
			frappe.throw(_("Expiry date cannot be before the issue date"))

	def validate_tolerance(self):
		if not (0 <= flt(self.tolerance_percentage) <= 100):
			frappe.throw(_("Tolerance % must be between 0 and 100"))

	def get_alert_days(self, strict: bool = True) -> list[int]:
		"""Parse the comma-separated thresholds, e.g. '15,7,3' -> [15, 7, 3].

		strict=True (validate) throws on malformed input; strict=False
		(scheduler) falls back to the defaults so one bad row cannot blind
		the whole alert run.
		"""
		raw = (self.alert_thresholds or "").strip()
		if not raw:
			return list(DEFAULT_ALERT_THRESHOLDS)
		try:
			days = sorted({int(part.strip()) for part in raw.split(",") if part.strip()}, reverse=True)
			if any(d < 0 for d in days):
				raise ValueError("negative threshold")
		except ValueError:
			if strict:
				frappe.throw(_("Alert thresholds must be comma-separated whole numbers, e.g. 15,7,3"))
			return list(DEFAULT_ALERT_THRESHOLDS)
		return days or list(DEFAULT_ALERT_THRESHOLDS)
