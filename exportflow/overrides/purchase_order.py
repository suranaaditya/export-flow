import frappe
from frappe.utils import add_days, flt, getdate

# Notification 41/2017 (merchant exports at 0.1% GST): goods must be exported
# within 90 days of the supplier's tax invoice.
GST_EXPORT_WINDOW_DAYS = 90


def before_insert(doc, method=None):
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
	set_gst_export_deadline(doc)


def on_submit(doc, method=None):
	backfill_shipment_links(doc)
	shipments = _linked_shipments(doc)
	_resync_mtt_outlay(shipments)
	from exportflow.checklist import rebuild_for_shipments

	rebuild_for_shipments(shipments)


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
