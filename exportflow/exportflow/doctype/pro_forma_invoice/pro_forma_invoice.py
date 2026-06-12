# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

# Settlement tolerance: receipts recorded in company currency convert back at
# the PFI's fixed deal rate, while the bank credits at the day's rate — allow
# 0.5% relative drift (minimum half a cent) before insisting on more money.
RELATIVE_TOLERANCE = 0.005
MIN_TOLERANCE = 0.005


class ProFormaInvoice(Document):
	def validate(self):
		self.validate_sales_order()
		self.set_defaults_from_so()
		self.compute_amount()
		self.compute_item_amounts()

	def validate_sales_order(self):
		if not self.sales_order:
			frappe.throw(_("Sales Order is required"))
		docstatus = frappe.db.get_value("Sales Order", self.sales_order, "docstatus")
		if docstatus is None:
			frappe.throw(_("Sales Order {0} not found").format(self.sales_order))
		if docstatus != 1:
			frappe.throw(_("Sales Order {0} must be submitted before raising a PFI").format(self.sales_order))

	def set_defaults_from_so(self):
		so = frappe.db.get_value(
			"Sales Order", self.sales_order, ["currency", "conversion_rate"], as_dict=True
		)
		# the PFI always settles in the deal currency
		self.currency = so.currency
		if not flt(self.conversion_rate):
			self.conversion_rate = so.conversion_rate

	def compute_amount(self):
		if self.basis == "Percentage of SO":
			if not (0 < flt(self.percentage) <= 100):
				frappe.throw(_("Percentage must be between 0 and 100"))
			so_value = flt(frappe.db.get_value("Sales Order", self.sales_order, "grand_total"))
			self.amount = flt(so_value * flt(self.percentage) / 100, 2)
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero"))

	def compute_item_amounts(self):
		for row in self.items:
			row.amount = flt(flt(row.qty) * flt(row.rate), 2)

	def settlement_tolerance(self) -> float:
		return max(MIN_TOLERANCE, flt(self.amount) * RELATIVE_TOLERANCE)

	def update_payment_status(self):
		"""Recompute received amount and status from submitted Payment Entries.

		Called from Payment Entry on_submit/on_cancel — uses db_set because the
		linked PE may still be inside its own save cycle.
		"""
		if self.status == "Cancelled":
			return

		paid = self.get_paid_amount()
		if paid >= flt(self.amount) - self.settlement_tolerance():
			status = "Paid"
		elif paid > MIN_TOLERANCE:
			status = "Partially Paid"
		elif self.was_sent:
			status = "Sent"
		else:
			status = "Draft"

		self.db_set({"paid_amount": paid, "status": status}, notify=True)

	def get_paid_amount(self) -> float:
		paid = 0.0
		entries = frappe.get_all(
			"Payment Entry",
			filters={"pro_forma_invoice": self.name, "docstatus": 1, "payment_type": "Receive"},
			fields=["name", "paid_amount", "base_paid_amount", "paid_from_account_currency"],
		)
		for pe in entries:
			if pe.paid_from_account_currency == self.currency:
				paid += flt(pe.paid_amount)
			elif flt(self.conversion_rate):
				# fall back through company currency when the receivable
				# account is not denominated in the deal currency
				paid += flt(pe.base_paid_amount) / flt(self.conversion_rate)
			else:
				frappe.log_error(
					title="PFI payment skipped: no conversion rate",
					message=f"Payment Entry {pe.name} against {self.name} could not be converted",
				)
		return flt(paid, 2)

	def mark_sent(self):
		if self.status != "Draft":
			frappe.throw(_("Only Draft pro forma invoices can be marked as Sent"))
		self.db_set({"status": "Sent", "was_sent": 1}, notify=True)

	def mark_cancelled(self):
		if flt(self.paid_amount) > MIN_TOLERANCE:
			frappe.throw(_("Cannot cancel: payments are already recorded against this PFI"))
		self.db_set("status", "Cancelled", notify=True)
