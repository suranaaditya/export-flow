# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

QTY_EPSILON = 1e-6

# Spec §4.2 — seeded per mode on creation
SEA_MILESTONES = [
	"Planned",
	"Goods Dispatched",
	"At Port/CFS",
	"Customs Filed",
	"Let Export Order",
	"Container Stuffed/Gated In",
	"Shipped on Board",
	"Arrived Destination",
	"Delivered",
]
AIR_MILESTONES = [
	"Planned",
	"Goods Dispatched",
	"At Airport/CFS",
	"Customs Filed",
	"Let Export Order",
	"Cargo Accepted",
	"Departed",
	"Arrived Destination",
	"Delivered",
]

# the GST export clock stops at this milestone (§4.3)
EXPORT_MILESTONE = {"Sea": "Shipped on Board", "Air": "Departed"}


def milestones_for(mode: str) -> list[str]:
	return SEA_MILESTONES if mode == "Sea" else AIR_MILESTONES


class ExportShipment(Document):
	def validate(self):
		self.seed_milestones()
		self.validate_items()
		self.validate_lc()
		self.set_current_milestone()

	def seed_milestones(self):
		expected = milestones_for(self.mode)
		other_mode = AIR_MILESTONES if expected is SEA_MILESTONES else SEA_MILESTONES
		current = [m.milestone for m in self.milestones]
		if not current:
			for name in expected:
				self.append("milestones", {"milestone": name})
		elif current == expected or current != other_mode:
			# matches this mode, or a custom grid the user edited — leave it
			return
		else:
			# a genuine mode switch before anything happened: reseed
			if any(m.completed for m in self.milestones):
				frappe.throw(
					_("Cannot change mode after milestones are underway — create a new shipment instead")
				)
			self.milestones = []
			for name in expected:
				self.append("milestones", {"milestone": name})

	def validate_items(self):
		if not self.items:
			frappe.throw(_("Add at least one item to the shipment"))

		# serialise competing shipments against the same SO lines (qty TOCTOU)
		details = tuple({row.so_detail for row in self.items if row.so_detail})
		if details:
			frappe.db.sql(
				"SELECT name FROM `tabSales Order Item` WHERE name IN %s FOR UPDATE", (details,)
			)

		so_rows: dict[str, dict] = {}
		for row in self.items:
			if flt(row.qty) <= 0:
				frappe.throw(_("Row {0}: quantity must be greater than zero").format(row.idx))
			so_row = frappe.db.get_value(
				"Sales Order Item",
				row.so_detail,
				["parent", "item_code", "qty"],
				as_dict=True,
			)
			if not so_row or so_row.parent != row.sales_order:
				frappe.throw(
					_("Row {0}: line reference does not belong to {1}").format(row.idx, row.sales_order)
				)
			if so_row.item_code != row.item_code:
				frappe.throw(_("Row {0}: item does not match the sales order line").format(row.idx))
			so_customer, so_docstatus = frappe.db.get_value(
				"Sales Order", row.sales_order, ["customer", "docstatus"]
			)
			if so_docstatus != 1:
				frappe.throw(_("Row {0}: {1} is not submitted").format(row.idx, row.sales_order))
			if so_customer != self.customer:
				frappe.throw(
					_("Row {0}: {1} belongs to a different customer").format(row.idx, row.sales_order)
				)
			self.validate_po_reference(row)
			so_rows[row.so_detail] = so_row

		# §3.2: cumulative shipped qty per SO line (across all shipments) ≤ ordered qty
		for so_detail, so_row in so_rows.items():
			this_doc = sum(flt(r.qty) for r in self.items if r.so_detail == so_detail)
			others = flt(
				frappe.db.sql(
					"""SELECT COALESCE(SUM(qty), 0) FROM `tabExport Shipment Item`
					   WHERE so_detail = %s AND parent != %s""",
					(so_detail, self.name or ""),
				)[0][0]
			)
			if this_doc + others > flt(so_row.qty) + QTY_EPSILON:
				frappe.throw(
					_(
						"Line {0}: shipping {1} but only {2} of {3} remains unshipped on the sales order"
					).format(
						so_row.item_code,
						frappe.format_value(this_doc, {"fieldtype": "Float"}),
						frappe.format_value(max(0, flt(so_row.qty) - others), {"fieldtype": "Float"}),
						frappe.format_value(flt(so_row.qty), {"fieldtype": "Float"}),
					)
				)

	def validate_po_reference(self, row):
		"""A claimed PO row must really source this SO line (no injection)."""
		if not row.purchase_order and not row.po_detail:
			return
		if not (row.purchase_order and row.po_detail):
			frappe.throw(_("Row {0}: purchase order reference is incomplete").format(row.idx))
		po_row = frappe.db.get_value(
			"Purchase Order Item",
			row.po_detail,
			["parent", "sales_order_item", "docstatus"],
			as_dict=True,
		)
		if not po_row or po_row.parent != row.purchase_order:
			frappe.throw(_("Row {0}: PO line does not belong to {1}").format(row.idx, row.purchase_order))
		if po_row.sales_order_item != row.so_detail:
			frappe.throw(
				_("Row {0}: {1} does not source this sales order line").format(row.idx, row.purchase_order)
			)
		if po_row.docstatus == 2:
			frappe.throw(_("Row {0}: {1} is cancelled").format(row.idx, row.purchase_order))

	def validate_lc(self):
		if not self.letter_of_credit:
			return
		lc_customer = frappe.db.get_value("Letter of Credit", self.letter_of_credit, "customer")
		if lc_customer != self.customer:
			frappe.throw(_("Letter of Credit {0} belongs to a different customer").format(self.letter_of_credit))

	def set_current_milestone(self):
		pending = [m.milestone for m in self.milestones if not m.completed]
		self.current_milestone = pending[0] if pending else "Completed"

	def set_milestone(self, row_name: str, completed: bool, actual_date=None):
		"""Sequential milestone engine: complete only the next pending step,
		un-complete only the latest completed one.

		Writes via db_set rather than a full save — a milestone update must
		never be blocked by unrelated validation state (e.g. an SO line that
		became over-shipped through later activity)."""
		rows = list(self.milestones)
		idx = next((i for i, m in enumerate(rows) if m.name == row_name), None)
		if idx is None:
			frappe.throw(_("Milestone not found"))

		if completed:
			if rows[idx].completed:
				return
			if any(not m.completed for m in rows[:idx]):
				frappe.throw(_("Complete earlier milestones first"))
			rows[idx].completed = 1
			rows[idx].actual_date = actual_date or frappe.utils.nowdate()
			rows[idx].db_set(
				{"completed": 1, "actual_date": rows[idx].actual_date}, update_modified=False
			)
		else:
			if not rows[idx].completed:
				return
			if any(m.completed for m in rows[idx + 1 :]):
				frappe.throw(_("Un-complete later milestones first"))
			rows[idx].completed = 0
			rows[idx].actual_date = None
			rows[idx].db_set({"completed": 0, "actual_date": None}, update_modified=False)

		self.set_current_milestone()
		self.db_set("current_milestone", self.current_milestone, notify=True)

	def export_completed_on(self):
		"""Actual date of the export milestone (GST clock stop), if reached."""
		target = EXPORT_MILESTONE.get(self.mode)
		for m in self.milestones:
			if m.milestone == target and m.completed:
				return m.actual_date
		return None
