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
		if not self.company:
			from exportflow.company import exportflow_company

			self.company = exportflow_company()
		if not self.trade_type:
			from exportflow.mtt import DEFAULT_TRADE_TYPE

			self.trade_type = DEFAULT_TRADE_TYPE
		self.apply_merchanting_cha()
		self.seed_milestones()
		self.validate_items()
		self.apply_mtt_import_facts()
		self.validate_lc()
		self.validate_milestone_blockers()
		self.set_current_milestone()

	def apply_merchanting_cha(self):
		"""Optional rule (ExportFlow Settings): a merchanting trade has no Indian
		CHA, so stamp the placeholder "Third Country" CHA on it automatically."""
		from exportflow.mtt import is_merchanting

		if not is_merchanting(self.trade_type):
			return
		if not frappe.db.get_single_value("ExportFlow Settings", "auto_cha_third_country"):
			return
		from exportflow.exportflow.doctype.cha.cha import ensure_third_country_cha

		self.cha = ensure_third_country_cha()

	def _effective_po(self, row):
		"""(purchase_order, po_detail) sourcing a shipment line — its own link when
		set and still submitted, else the submitted PO Item for its SO line. Mirrors
		the fallback get_shipment_detail uses for shipments booked before the PO
		existed, so the two views can never disagree."""
		if row.po_detail:
			if frappe.db.get_value("Purchase Order Item", row.po_detail, "docstatus") == 1:
				return row.purchase_order, row.po_detail
			return None, None
		# no po_detail: resolve the submitted PO Item for this SO line, preferring a
		# purchase_order already recorded on the row (a partial link) so the derived
		# PO can never diverge from one the row names
		filters = {"sales_order_item": row.so_detail, "docstatus": 1}
		if row.purchase_order:
			filters["parent"] = row.purchase_order
		poi = frappe.db.get_value(
			"Purchase Order Item", filters, ["name", "parent"], as_dict=True
		)
		return (poi.parent, poi.name) if poi else (None, None)

	def computed_import_facts(self) -> dict:
		"""Derive the merchanting import leg from the shipment's linked POs:
		outlay = Σ (shipped qty × PO line buying rate), in INR (POs are stored in
		company currency, so base_rate is already INR — no FX needed), plus the
		distinct PO suppliers. A line with no submitted sourcing PO contributes
		nothing (nothing bought yet); a line that HAS one is 'costed' even at a
		zero rate."""
		total = 0.0
		costed = uncosted = 0
		suppliers: set[str] = set()
		for row in self.items:
			po_name, po_detail = self._effective_po(row)
			if not po_detail:
				uncosted += 1
				continue
			supplier = frappe.db.get_value("Purchase Order", po_name, "supplier")
			if supplier:
				suppliers.add(supplier)
			total += flt(row.qty) * flt(
				frappe.db.get_value("Purchase Order Item", po_detail, "base_rate")
			)
			costed += 1
		return {
			"outlay_inr": flt(total, 2),
			"costed_lines": costed,
			"uncosted_lines": uncosted,
			"suppliers": sorted(suppliers),
		}

	def apply_mtt_import_facts(self):
		"""When 'Auto-derive from purchase orders' is on (default for merchanting),
		the controller OWNS the import outlay and import-leg supplier: outlay from
		the linked POs, supplier when they share a SINGLE vendor (else cleared — an
		ambiguous/empty set never leaves a stale guess). A manual override (toggle
		off) is left untouched."""
		from exportflow.mtt import is_merchanting

		if not is_merchanting(self.trade_type) or not self.mtt_import_value_auto:
			return
		facts = self.computed_import_facts()
		self.mtt_import_value_inr = facts["outlay_inr"] or None
		self.mtt_import_supplier = facts["suppliers"][0] if len(facts["suppliers"]) == 1 else None

	def validate_milestone_blockers(self):
		"""The UI completes milestones via set_milestone, but a direct document
		save (desk, REST) can flip the completed flag too — gate that path."""
		before = self.get_doc_before_save()
		if not before:
			return
		was_done = {m.name: m.completed for m in before.milestones}
		for m in self.milestones:
			if m.completed and not was_done.get(m.name):
				self.assert_milestone_not_blocked(m.milestone)

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
			self.assert_milestone_not_blocked(rows[idx].milestone)
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

	def assert_milestone_not_blocked(self, milestone: str):
		"""§4.2/§5: an unresolved blocking Document Instance (default: ADC NOC,
		Shipping Bill) prevents completing its configured milestone."""
		from exportflow.checklist import milestone_blockers

		blockers = milestone_blockers(self.name, milestone)
		if blockers:
			frappe.throw(
				_("Cannot complete {0} — blocked by: {1}").format(
					milestone,
					", ".join(f"{b.document_type} ({b.status})" for b in blockers),
				)
			)

	def export_completed_on(self):
		"""Actual date of the export milestone (GST clock stop), if reached."""
		target = EXPORT_MILESTONE.get(self.mode)
		for m in self.milestones:
			if m.milestone == target and m.completed:
				return m.actual_date
		return None
