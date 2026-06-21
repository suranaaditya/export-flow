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

# Merchanting (third-country) trades never touch Indian customs, so they get a
# simpler chain with no Customs Filed / Let Export Order steps (client decision
# 2026-06-18). The goods still ship A→B on a B/L or AWB, so "Shipped from
# Origin" is the departure step that the bl/awb date completes.
MERCHANTING_MILESTONES = [
	"Booked",
	"Shipped from Origin",
	"Arrived at Destination",
	"Delivered",
]

# every standard seed set — used by the reseed guard to tell a mode/trade-type
# switch apart from a grid the user hand-edited (which must be left alone)
KNOWN_MILESTONE_SETS = (SEA_MILESTONES, AIR_MILESTONES, MERCHANTING_MILESTONES)

# the GST/FEMA export clock stops at this milestone (§4.3) — keyed by mode for an
# India export, fixed for merchanting (see export_milestone_name)
EXPORT_MILESTONE = {"Sea": "Shipped on Board", "Air": "Departed"}
MERCHANTING_EXPORT_MILESTONE = "Shipped from Origin"

# the pre-departure step a freshly-booked shipment has already reached (the
# client never books in advance — by booking, the goods are at the port/CFS or,
# for merchanting, booked at origin)
INITIAL_MILESTONE = {"Sea": "At Port/CFS", "Air": "At Airport/CFS"}
MERCHANTING_INITIAL_MILESTONE = "Booked"

# the pre-departure steps that seed_initial_progress auto-completes on creation —
# these are NOT real progress, so they must not freeze a mode / trade-type change
# (which reseeds the grid). Only a completion BEYOND this set blocks a reseed.
AUTO_SEEDED_MILESTONES = frozenset(
	{"Planned", "Goods Dispatched", "At Port/CFS", "At Airport/CFS", "Booked"}
)


def milestones_for(mode: str, trade_type=None) -> list[str]:
	from exportflow.mtt import is_merchanting

	if is_merchanting(trade_type):
		return MERCHANTING_MILESTONES
	return SEA_MILESTONES if mode == "Sea" else AIR_MILESTONES


class ExportShipment(Document):
	def validate(self):
		if not self.company:
			from exportflow.company import exportflow_company

			self.company = exportflow_company()
		if not self.trade_type:
			from exportflow.mtt import DEFAULT_TRADE_TYPE

			self.trade_type = DEFAULT_TRADE_TYPE
		self.derive_trade_type_from_pos()
		self.apply_merchanting_cha()
		self.seed_milestones()
		self.seed_initial_progress()
		self.validate_items()
		self.validate_packs()
		self.apply_mtt_import_facts()
		self.validate_lc()
		self.validate_milestone_blockers()
		self.set_current_milestone()

	def validate_packs(self):
		"""Every packing-detail row must reference one of this shipment's own line
		items — otherwise the invoice / packing-list weight rollup silently drops
		it (the rollup is keyed by line item_code)."""
		if not self.get("packs"):
			return
		line_items = {row.item_code for row in self.items}
		for p in self.packs:
			if p.item_code and p.item_code not in line_items:
				frappe.throw(
					_("Packing row references {0}, which is not a line item on this shipment.").format(
						frappe.bold(p.item_code)
					)
				)

	def classify_pos(self) -> tuple[bool, bool]:
		"""(has_merchanting_line, has_india_export_line) across the sourcing POs.
		The India leg is the LOGICAL COMPLEMENT of the foreign check used to build
		merchanting POs — a domestic supplier with a blank country (common from the
		MIS import, where domestic-ness is keyed off GST category) still counts as
		India, so an export line is never silently swept into a merchanting shipment."""
		from exportflow.api import _supplier_is_foreign

		mtt = india = False
		for row in self.items:
			po_name, _po_detail = self._effective_po(row)
			if not po_name:
				continue
			info = frappe.db.get_value(
				"Purchase Order", po_name, ["merchanting_trade", "supplier"], as_dict=True
			)
			if not info:
				continue
			if info.merchanting_trade:
				mtt = True
			elif not _supplier_is_foreign(info.supplier):
				india = True
		return mtt, india

	def derive_trade_type_from_pos(self):
		"""A shipment's trade type follows its sourcing POs. If any line is bought
		on a merchanting (third-country) PO it IS a merchanting shipment — and it
		can never mix with goods exported from India, since the two load at
		different ports (one foreign, one Indian). Enforced (authoritative) when a
		flagged PO is present; a shipment with no flagged PO is left untouched so
		MIS-imported / manually-set merchanting shipments are not disturbed."""
		from exportflow.mtt import MERCHANTING

		mtt, india = self.classify_pos()
		if mtt and india:
			frappe.throw(
				_(
					"This shipment mixes a third-country / merchanting purchase with goods "
					"exported from India — they load at different ports and must ship separately."
				)
			)
		if mtt:
			self.trade_type = MERCHANTING

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
		expected = milestones_for(self.mode, self.trade_type)
		current = [m.milestone for m in self.milestones]
		self._fresh_milestones = False
		if not current:
			for name in expected:
				self.append("milestones", {"milestone": name})
			# auto-advance the pre-departure steps only on a brand-new booking — an
			# EXISTING record that reached here with an empty grid (rows deleted in
			# the desk, a bulk import) gets its grid back but must NOT be
			# back-stamped with today's date
			self._fresh_milestones = self.is_new()
			return
		if current == expected:
			return
		if current not in KNOWN_MILESTONE_SETS:
			# a custom grid the user hand-edited — leave it alone
			return
		# a genuine mode / trade-type switch between standard sets: reseed, but
		# only while no REAL progress has been made (the auto-seeded pre-departure
		# steps don't count — they are re-applied on the new set below)
		if any(
			m.completed and m.milestone not in AUTO_SEEDED_MILESTONES for m in self.milestones
		):
			frappe.throw(
				_(
					"Cannot change mode or trade type after milestones are underway — "
					"create a new shipment instead"
				)
			)
		self.milestones = []
		for name in expected:
			self.append("milestones", {"milestone": name})
		self._fresh_milestones = True

	def seed_initial_progress(self):
		"""Client rule (2026-06-18): a shipment is never booked in advance — by
		booking, the goods are already at the port/CFS (India export) or booked at
		origin (merchanting). When the grid is first seeded (creation) OR reseeded
		by a mode / trade-type switch, auto-complete the pre-departure steps so the
		timeline opens realistically. Runs only on a fresh (re)seed and only when
		nothing is completed yet — never disturbs progress in flight.

		NB the pre-departure steps are completed directly (not via set_milestone),
		so they are not blocker-checked. This is safe with the default catalog
		(blocking docs gate only "Let Export Order"); a custom checklist rule must
		never set a pre-departure milestone as its blocked_milestone."""
		if not getattr(self, "_fresh_milestones", False):
			return
		if any(m.completed for m in self.milestones):
			return
		from exportflow.mtt import is_merchanting

		target = (
			MERCHANTING_INITIAL_MILESTONE
			if is_merchanting(self.trade_type)
			else INITIAL_MILESTONE.get(self.mode)
		)
		names = [m.milestone for m in self.milestones]
		if target not in names:
			return
		booked = frappe.utils.nowdate()
		for m in self.milestones[: names.index(target) + 1]:
			m.completed = 1
			if not m.actual_date:
				m.actual_date = booked
		self.set_current_milestone()

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
			self._assert_goods_received(rows[idx].milestone)
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
		self.sync_shipment_stock()

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

	def export_milestone_name(self) -> str | None:
		"""The departure milestone that stops the export clock — fixed for a
		merchanting trade (no Indian customs), mode-dependent otherwise."""
		from exportflow.mtt import is_merchanting

		if is_merchanting(self.trade_type):
			return MERCHANTING_EXPORT_MILESTONE
		return EXPORT_MILESTONE.get(self.mode)

	def export_completed_on(self):
		"""Actual date of the export milestone (GST clock stop), if reached."""
		target = self.export_milestone_name()
		for m in self.milestones:
			if m.milestone == target and m.completed:
				return m.actual_date
		return None

	# --- stock-OUT (quantity-only; gated on ExportFlow Settings.maintain_stock) ---

	def _grn_warehouse_for_line(self, line):
		"""The warehouse holding this line's received stock — from a Received Goods
		Receipt Note of the line's purchase order (the line's own PO link, else the
		SO-line's submitted PO via the same fallback get_shipment_detail uses)."""
		po = line.purchase_order or self._effective_po(line)[0]
		if not po:
			return None
		return frappe.db.get_value(
			"Goods Receipt Note",
			{"purchase_order": po, "status": "Received"},
			"warehouse",
			order_by="creation desc",
		)

	def _assert_goods_received(self, milestone):
		"""Hard, opt-in gate: when grn_required_for_shipment is on, a non-merchanting
		shipment cannot complete its departure milestone until every line has enough
		received (un-shipped) stock. The stock post itself never blocks — this guard
		is the only thing that does."""
		from exportflow import stock
		from exportflow.mtt import is_merchanting

		if is_merchanting(self.trade_type) or not stock.maintain_stock_enabled():
			return
		if milestone != self.export_milestone_name():
			return
		if not frappe.db.get_single_value("ExportFlow Settings", "grn_required_for_shipment"):
			return
		short = []
		for line in self.items:
			wh = self._grn_warehouse_for_line(line)
			if not wh or stock.balance(line.item_code, wh) + QTY_EPSILON < flt(line.qty):
				short.append(line.item_code)
		if short:
			frappe.throw(
				_(
					"No goods received for: {0}. Create a Goods Receipt Note that receives them "
					"before this shipment can depart."
				).format(", ".join(dict.fromkeys(short)))
			)

	def sync_shipment_stock(self, force_resync=False):
		"""Reconcile the shipment's stock-OUT with its current state: once the
		shipment has departed (export milestone complete) post the shipped quantity
		OUT of each line's GRN warehouse; otherwise reverse it. Idempotent and never
		blocks (allow_negative — the optional hard gate is _assert_goods_received).
		No-op for merchanting and when the stock regime is off."""
		from exportflow import stock
		from exportflow.mtt import is_merchanting

		voucher = stock.SHIPMENT_VOUCHER
		eligible = (
			stock.maintain_stock_enabled()
			and not is_merchanting(self.trade_type)
			and self.export_completed_on() is not None
		)
		if not eligible:
			stock.reverse(voucher, self.name)
			return
		rows = []
		for line in self.items:
			wh = self._grn_warehouse_for_line(line)
			if wh:
				rows.append((line.item_code, wh, flt(line.qty)))
		if force_resync:
			stock.reverse(voucher, self.name)
		if rows:
			stock.post_out(rows, voucher, self.name, company=self.company, allow_negative=True)


def reverse_shipment_stock_on_trash(doc, method=None):
	"""Export Shipment on_trash: undo any stock-OUT this shipment posted."""
	from exportflow import stock

	stock.reverse(stock.SHIPMENT_VOUCHER, doc.name)


def sync_shipment_stock_on_update(doc, method=None):
	"""Export Shipment on_update: reconcile the stock-OUT on every full save (a
	departure flipped via a direct desk/REST save, or a line-qty edit on an
	already-departed shipment). set_milestone uses db_set and does NOT fire
	on_update, so it syncs separately — this closes the full-save path. Idempotent
	and reverses when ineligible; never blocks the save."""
	try:
		doc.sync_shipment_stock(force_resync=True)
	except Exception:
		frappe.log_error(title=f"Shipment stock sync failed: {doc.name}", message=frappe.get_traceback())


def advance_milestones_from_facts(doc, method=None):
	"""Export Shipment on_update: a document fact proves the goods passed a
	milestone, so complete it and every earlier still-pending step (the chain is
	strictly sequential — a late fact carries the earlier steps with it).

	Triggers, only when the date is newly set this save:
	  shipping_bill_date → Customs Filed      (India export only)
	  leo_date           → Let Export Order   (India export only)
	  bl_date  (Sea)     → Shipped on Board  / "Shipped from Origin" (merchanting)
	  awb_date (Air)     → Departed          / "Shipped from Origin" (merchanting)

	Routed through set_milestone so the sequential + blocking guards hold; a
	milestone gated by an unresolved blocking document is skipped silently (never
	blocks the save). Idempotent — already-completed steps are passed over."""
	before = doc.get_doc_before_save()
	if not before:
		return
	try:
		_advance_from_facts(doc, before)
	except Exception:
		frappe.log_error(
			title=f"Milestone auto-advance failed: {doc.name}", message=frappe.get_traceback()
		)


def _advance_from_facts(doc, before):
	from exportflow.mtt import is_merchanting

	merch = is_merchanting(doc.trade_type)
	names = [m.milestone for m in doc.milestones]

	def newly_set(field):
		return doc.get(field) and not before.get(field)

	# (target milestone, the date that proves it) for each fired trigger
	fired: list[tuple[str, str]] = []
	if not merch:
		if newly_set("shipping_bill_date"):
			fired.append(("Customs Filed", doc.shipping_bill_date))
		if newly_set("leo_date"):
			fired.append(("Let Export Order", doc.leo_date))
	dep_field = "awb_date" if doc.mode == "Air" else "bl_date"
	if newly_set(dep_field):
		departed = MERCHANTING_EXPORT_MILESTONE if merch else EXPORT_MILESTONE.get(doc.mode)
		if departed:
			fired.append((departed, doc.get(dep_field)))

	targets = [(t, d) for t, d in fired if t in names]
	if not targets:
		return

	# complete up to the furthest proven milestone, carrying earlier pending steps;
	# stamp each step with its own fact date when one fired for it, else the
	# furthest date (a safe upper bound — it happened no later). Index by POSITION,
	# not label — a hand-edited grid may repeat a milestone name, which would make
	# names.index() resolve the wrong row.
	fact_date = {t: d for t, d in targets}
	furthest_idx = max(i for i, m in enumerate(doc.milestones) if m.milestone in fact_date)
	furthest_date = fact_date[doc.milestones[furthest_idx].milestone]

	for i, m in enumerate(doc.milestones):
		if i > furthest_idx:
			break
		if m.completed:
			continue
		when = fact_date.get(m.milestone) or furthest_date
		try:
			doc.set_milestone(m.name, True, when)
		except frappe.ValidationError:
			# gated by an unresolved blocking document — stop here, never force it.
			# drop the throw's message so it doesn't surface as an error toast on an
			# otherwise-successful save
			if frappe.message_log:
				frappe.message_log.pop()
			break


def reseed_merchanting_milestones(name: str):
	"""A shipment can flip to merchanting after booking (a third-country PO is
	submitted later) — that path uses db_set without re-running validate, so the
	milestone grid still carries the India-export set. Bring it to the merchanting
	set, but only while nothing has been completed and the grid is still a
	recognised standard set (never disturb a hand-edited or in-progress grid)."""
	rows = frappe.get_all(
		"Shipment Milestone",
		filters={"parent": name, "parenttype": "Export Shipment"},
		fields=["milestone", "completed"],
		order_by="idx asc",
	)
	# real progress (beyond the auto-seeded pre-departure steps) means we cannot
	# safely remap the grid — leave it for the user
	if not rows or any(
		r.completed and r.milestone not in AUTO_SEEDED_MILESTONES for r in rows
	):
		return
	current = [r.milestone for r in rows]
	if current == MERCHANTING_MILESTONES or current not in (SEA_MILESTONES, AIR_MILESTONES):
		return

	created = frappe.db.get_value("Export Shipment", name, "creation")
	booked = frappe.utils.getdate(created) if created else frappe.utils.nowdate()
	frappe.db.delete("Shipment Milestone", {"parent": name, "parenttype": "Export Shipment"})
	for i, milestone in enumerate(MERCHANTING_MILESTONES):
		done = milestone == MERCHANTING_INITIAL_MILESTONE
		frappe.get_doc(
			{
				"doctype": "Shipment Milestone",
				"parent": name,
				"parenttype": "Export Shipment",
				"parentfield": "milestones",
				"idx": i + 1,
				"milestone": milestone,
				"completed": 1 if done else 0,
				"actual_date": booked if done else None,
			}
		).insert(ignore_permissions=True)
	# current milestone is the first still-pending step after the booked one
	frappe.db.set_value(
		"Export Shipment", name, "current_milestone", MERCHANTING_MILESTONES[1], update_modified=False
	)
