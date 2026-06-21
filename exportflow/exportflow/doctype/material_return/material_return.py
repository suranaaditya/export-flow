# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate


class MaterialReturn(Document):
	"""Goods received on a GRN that are sent back to the supplier (off-spec,
	damaged, short). Returning posts the quantity OUT of the receiving warehouse
	and reduces the PO's net received — so the returned quantity reopens as
	remaining and can be re-received. Stock-out + status change are driven by the
	API action (exportflow.api.submit_return); a plain save only validates."""

	def validate(self):
		self._set_defaults()
		self._validate_grn()
		self._validate_items()

	def _set_defaults(self):
		grn = (
			frappe.db.get_value(
				"Goods Receipt Note",
				self.goods_receipt_note,
				["purchase_order", "supplier", "company", "warehouse"],
				as_dict=True,
			)
			if self.goods_receipt_note
			else None
		)
		if grn:
			self.purchase_order = self.purchase_order or grn.purchase_order
			self.supplier = self.supplier or grn.supplier
			self.company = self.company or grn.company
			self.warehouse = self.warehouse or grn.warehouse
		if not self.company:
			from exportflow.company import exportflow_company

			self.company = exportflow_company()
		if not self.posting_date:
			self.posting_date = nowdate()
		if not self.status:
			self.status = "Draft"

	def _validate_grn(self):
		if not self.goods_receipt_note:
			frappe.throw(_("A Material Return must be linked to a Goods Receipt Note."))
		if frappe.db.get_value("Goods Receipt Note", self.goods_receipt_note, "status") != "Received":
			frappe.throw(
				_("Goods Receipt Note {0} is not received.").format(self.goods_receipt_note)
			)

	def _validate_items(self):
		if not self.items:
			frappe.throw(_("Add at least one line to return."))
		for row in self.items:
			if flt(row.returned_qty) <= 0:
				frappe.throw(_("Return qty must be greater than zero for {0}.").format(row.item_code))
