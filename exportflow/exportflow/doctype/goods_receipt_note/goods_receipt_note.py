# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate


class GoodsReceiptNote(Document):
	"""Goods received in India against a Purchase Order — the step between PO and
	Export Shipment. Receiving posts quantity-only stock IN at the warehouse (a
	virtual port, usually) and the shipment posts it OUT at departure. Merchanting
	purchases never get a GRN (the goods never enter India).

	A plain save only validates and defaults — the receipt itself (stock-in, PO
	invoice write-back, status → Received) is driven by exportflow.api.submit_grn,
	following the app's status-doc + API-action pattern.
	"""

	def validate(self):
		self._set_defaults()
		self._validate_po()
		self._validate_items()

	def _set_defaults(self):
		if not self.company:
			self.company = (
				frappe.db.get_value("Purchase Order", self.purchase_order, "company")
				if self.purchase_order
				else None
			)
		if not self.company:
			from exportflow.company import exportflow_company

			self.company = exportflow_company()
		if not self.posting_date:
			self.posting_date = nowdate()
		if not self.status:
			self.status = "Draft"

	def _validate_po(self):
		if not self.purchase_order:
			frappe.throw(_("A Goods Receipt Note must be linked to a Purchase Order."))
		po = frappe.db.get_value(
			"Purchase Order",
			self.purchase_order,
			["docstatus", "merchanting_trade"],
			as_dict=True,
		)
		if not po or po.docstatus != 1:
			frappe.throw(_("Purchase Order {0} is not submitted.").format(self.purchase_order))
		if po.merchanting_trade:
			frappe.throw(
				_(
					"{0} is a third-country / merchanting purchase — its goods never enter "
					"India, so no Goods Receipt Note applies."
				).format(self.purchase_order)
			)

	def assert_not_consumed(self):
		"""Refuse to reverse this receipt's stock-IN when a shipment has already
		shipped the goods OUT — reversing the IN while the OUT row survives would
		leave a permanent negative balance."""
		from exportflow import stock

		if self.status != "Received" or not stock.maintain_stock_enabled():
			return
		for r in self.items:
			if stock.balance(r.item_code, self.warehouse) - flt(r.received_qty) < -1e-6:
				frappe.throw(
					_(
						"Goods from this receipt ({0}) have already been shipped — reverse or delete "
						"that shipment before cancelling or deleting this Goods Receipt Note."
					).format(r.item_code)
				)

	def on_trash(self):
		"""Deleting a GRN must undo its stock-IN (mirrors the shipment's on_trash),
		and is refused once the goods have shipped."""
		from exportflow import stock

		self.assert_not_consumed()
		stock.reverse(stock.GRN_VOUCHER, self.name)

	def _validate_items(self):
		if not self.items:
			frappe.throw(_("Add at least one received line."))
		po_lines = {
			r.name: r
			for r in frappe.get_all(
				"Purchase Order Item",
				filters={"parent": self.purchase_order},
				fields=["name", "item_code"],
			)
		}
		for row in self.items:
			if row.po_detail and row.po_detail not in po_lines:
				frappe.throw(
					_("Received line {0} does not belong to {1}.").format(
						row.item_code, self.purchase_order
					)
				)
			if row.po_detail and row.item_code != po_lines[row.po_detail].item_code:
				frappe.throw(_("Received line {0} does not match its PO line.").format(row.idx))
			if flt(row.received_qty) <= 0:
				frappe.throw(_("Received qty must be greater than zero for {0}.").format(row.item_code))
