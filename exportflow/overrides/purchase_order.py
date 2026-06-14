import frappe
from frappe.utils import add_days, flt, getdate

# Notification 41/2017 (merchant exports at 0.1% GST): goods must be exported
# within 90 days of the supplier's tax invoice.
GST_EXPORT_WINDOW_DAYS = 90


def before_insert(doc, method=None):
	# A third-country / merchanting purchase can NEVER use the 0.1% domestic
	# scheme — guard this before the supplier-default logic below, which would
	# otherwise re-enable it from the supplier's default.
	if doc.get("merchanting_trade"):
		doc.merchant_export_scheme = 0
		return
	# Default the scheme from the supplier on NEW POs only. Amendments must
	# keep whatever the user had chosen on the original (an unchecked box on
	# an amended PO would otherwise silently flip back to the supplier
	# default — a compliance-flag mutation).
	# Known limitation: an unchecked box on a brand-new unsaved PO is
	# indistinguishable from "not set", so it gets the supplier default once.
	if doc.get("amended_from"):
		return
	if not doc.get("merchant_export_scheme") and doc.get("supplier"):
		doc.merchant_export_scheme = (
			frappe.db.get_value("Supplier", doc.supplier, "default_merchant_export_scheme") or 0
		)


def validate(doc, method=None):
	# the domestic 0.1% scheme and merchanting are mutually exclusive — re-assert
	# on every save/amend/Update-Items path, not just insert
	if doc.get("merchanting_trade"):
		doc.merchant_export_scheme = 0
	set_gst_export_deadline(doc)


def on_submit(doc, method=None):
	backfill_shipment_links(doc)
	shipments = _linked_shipments(doc)
	# a shipment booked BEFORE its merchanting PO existed is still "Export from
	# India"; now that the PO is submitted and its line links are backfilled,
	# re-derive the trade type so the checklist / outlay / FEMA basis follow
	_resync_trade_types(shipments)
	_resync_mtt_outlay(shipments)
	from exportflow.checklist import rebuild_for_shipments

	rebuild_for_shipments(shipments)


def _resync_trade_types(shipments: list[str]):
	"""Flip a linked shipment to merchanting when every now-sourced PO is a
	merchanting (third-country) PO and none is a domestic-India leg. db_set only
	— the caller re-syncs the outlay and rebuilds the checklist, which read the
	updated trade_type. Per-shipment guarded so it never blocks the PO submit."""
	from exportflow.mtt import MERCHANTING, is_merchanting

	for name in shipments:
		if is_merchanting(frappe.db.get_value("Export Shipment", name, "trade_type")):
			continue
		try:
			shp = frappe.get_doc("Export Shipment", name)
			mtt, india = shp.classify_pos()
			if mtt and not india:
				frappe.db.set_value(
					"Export Shipment", name, "trade_type", MERCHANTING, update_modified=False
				)
		except Exception:
			frappe.log_error(title="MTT trade-type resync failed", message=name)


def on_update_after_submit(doc, method=None):
	"""Supplier invoice details arrive AFTER submission (that is the designed
	flow) — when they land, the GST clock moves, and the shipment's compliance
	pack must pick up its due date (or appear/retire if the scheme flag flips).
	A buying-rate change via ERPNext's "Update Items" on a submitted PO also lands
	here, so re-derive an auto merchanting shipment's import outlay too."""
	shipments = _linked_shipments(doc)
	_resync_mtt_outlay(shipments)
	if doc.has_value_changed("gst_export_deadline") or doc.has_value_changed(
		"merchant_export_scheme"
	):
		_rebuild_linked_checklists(doc)


def on_cancel(doc, method=None):
	# collect before the links are cleared, rebuild after — the lapsed
	# 0.1% compliance packs must see the PO gone
	shipments = _linked_shipments(doc)
	clear_shipment_links(doc)
	_resync_mtt_outlay(shipments)
	from exportflow.checklist import rebuild_for_shipments

	rebuild_for_shipments(shipments)


def mark_covered_pos_delivered(doc, method=None):
	"""Export Shipment on_update hook: once the cumulative shipped quantity (across
	ALL shipments) covers a linked drop-ship PO's full ordered qty, mark that PO
	'Delivered' — the supplier has delivered everything to the port of shipment.
	Only fully-covered POs flip (a partly-shipped PO stays open). Idempotent; a
	failure to flip one PO never blocks the shipment save."""
	from erpnext.buying.doctype.purchase_order.purchase_order import update_status

	for po_name in {row.purchase_order for row in doc.items if row.purchase_order}:
		try:
			if _po_fully_shipped(po_name):
				update_status("Delivered", po_name)
		except Exception:
			frappe.log_error(
				title="ExportFlow auto-deliver PO",
				message=f"shipment {doc.name} → PO {po_name}\n{frappe.get_traceback()}",
			)


def _po_fully_shipped(po_name: str) -> bool:
	"""A submitted, not-yet-closed drop-ship PO whose every line's cumulative
	shipped qty (across all shipments) reaches its ordered qty."""
	po = frappe.db.get_value(
		"Purchase Order", po_name, ["docstatus", "status"], as_dict=True
	)
	if not po or po.docstatus != 1 or po.status in ("Delivered", "Closed", "Cancelled"):
		return False
	lines = frappe.get_all(
		"Purchase Order Item",
		filters={"parent": po_name},
		fields=["name", "qty", "delivered_by_supplier"],
	)
	# only drop-ship POs auto-deliver, and only when every line is fully shipped
	if not lines or not all(line.delivered_by_supplier for line in lines):
		return False
	for line in lines:
		shipped = flt(
			frappe.db.sql(
				"SELECT COALESCE(SUM(qty), 0) FROM `tabExport Shipment Item` WHERE po_detail = %s",
				(line.name,),
			)[0][0]
		)
		if shipped + 1e-6 < flt(line.qty):
			return False
	return True


def _resync_mtt_outlay(shipments: list[str]):
	"""Keep an auto merchanting shipment's stored import outlay (and single
	supplier) in step with its linked POs as those POs are submitted, amended or
	cancelled — the stored figure is what get_shipment_finance reads for the FEMA
	net-FX check, so it must not lag behind the PO data. db_set only (no validate
	recursion)."""
	from exportflow.mtt import is_merchanting

	for name in shipments:
		shp = frappe.get_doc("Export Shipment", name)
		if not is_merchanting(shp.trade_type) or not shp.mtt_import_value_auto:
			continue
		facts = shp.computed_import_facts()
		outlay = facts["outlay_inr"] or None
		supplier = facts["suppliers"][0] if len(facts["suppliers"]) == 1 else None
		changes = {}
		if flt(shp.mtt_import_value_inr) != flt(outlay or 0):
			changes["mtt_import_value_inr"] = outlay
		if shp.mtt_import_supplier != supplier:
			changes["mtt_import_supplier"] = supplier
		if changes:
			shp.db_set(changes, update_modified=False)


def _linked_shipments(doc) -> list[str]:
	"""Shipments this PO touches — by explicit FK, plus shipments attributed to it
	only through the SO-line fallback (item rows with no PO link whose SO line this
	PO sources). The fallback set matters on cancel: an unlinked shipment that was
	costing out against this PO must be re-derived once the PO leaves docstatus 1."""
	fk = frappe.get_all(
		"Export Shipment Item",
		filters={"purchase_order": doc.name},
		pluck="parent",
		distinct=True,
	)
	so_items = [r.sales_order_item for r in doc.items if r.sales_order_item]
	fallback = (
		frappe.get_all(
			"Export Shipment Item",
			filters={"so_detail": ["in", so_items], "purchase_order": ["is", "not set"]},
			pluck="parent",
			distinct=True,
		)
		if so_items
		else []
	)
	return list(dict.fromkeys([*fk, *fallback]))


def _rebuild_linked_checklists(doc):
	"""A scheme PO arriving (or leaving) changes the shipment's document
	requirements (§5.3: 0.1% PO → GST Supplier Compliance Pack)."""
	from exportflow.checklist import rebuild_for_shipments

	rebuild_for_shipments(_linked_shipments(doc))


def backfill_shipment_links(doc):
	"""Shipments may be booked before procurement exists — once the PO is
	submitted, claim the shipment item rows that ship its SO lines so the
	GST clock and PO↔shipment links work regardless of creation order."""
	for row in doc.items:
		if not row.sales_order_item:
			continue
		for esi in frappe.get_all(
			"Export Shipment Item",
			filters={"so_detail": row.sales_order_item, "purchase_order": ["is", "not set"]},
			pluck="name",
		):
			frappe.db.set_value(
				"Export Shipment Item",
				esi,
				{"purchase_order": doc.name, "po_detail": row.name},
				update_modified=False,
			)


def clear_shipment_links(doc):
	for esi in frappe.get_all(
		"Export Shipment Item", filters={"purchase_order": doc.name}, pluck="name"
	):
		frappe.db.set_value(
			"Export Shipment Item",
			esi,
			{"purchase_order": None, "po_detail": None},
			update_modified=False,
		)


def set_gst_export_deadline(doc):
	if doc.get("merchant_export_scheme") and doc.get("supplier_invoice_date"):
		doc.gst_export_deadline = add_days(getdate(doc.supplier_invoice_date), GST_EXPORT_WINDOW_DAYS)
	else:
		doc.gst_export_deadline = None
