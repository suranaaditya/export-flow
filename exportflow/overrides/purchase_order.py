import json

import frappe
from frappe.utils import add_days, flt, getdate

# Notification 41/2017 (merchant exports at 0.1% GST): goods must be exported
# within 90 days of the supplier's tax invoice.
GST_EXPORT_WINDOW_DAYS = 90

# Concessional total GST a registered supplier charges a merchant exporter under
# Notifications 40/2017-CT(R) (intra-state: 0.05% CGST + 0.05% SGST) and
# 41/2017-IT(R) (inter-state: 0.1% IGST). The 0.1% is split across whichever
# heads actually apply for the place of supply.
MERCHANT_EXPORT_TOTAL_RATE = 0.1


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
				# the db_set flip skips validate, so bring the milestone grid to the
				# simpler merchanting set too (only when nothing has been completed)
				from exportflow.exportflow.doctype.export_shipment.export_shipment import (
					reseed_merchanting_milestones,
				)

				reseed_merchanting_milestones(name)
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


# --- Merchant-export 0.1% concessional GST -------------------------------------
# The "Merchant export scheme (0.1% GST)" flag is more than a label: under the
# scheme the registered supplier charges the merchant exporter a concessional
# 0.1% (not the item's normal rate). ERPNext re-derives each line's
# item_tax_rate from its Item Tax Template on EVERY recompute, so a one-off rate
# override would be wiped — we rescale inside the calculation itself, after the
# normal derivation and before the tax rows are built, by overriding the PO's
# calculate_taxes_and_totals (registered via override_doctype_class in hooks).
#
# SCOPE: the concessional rate is applied on the Purchase Order only — the sole
# scheme artifact ExportFlow creates, prints and tracks (the supplier invoice no/
# date are captured as PO fields, not a Purchase Invoice). ExportFlow never makes
# a Purchase Receipt / Purchase Invoice in its flow; if one is created from the
# desk it reverts to the item's full rate (those doctypes have no scheme field).

from erpnext.controllers.taxes_and_totals import (  # noqa: E402
	calculate_taxes_and_totals as _CalculateTaxesAndTotals,
)


def _gst_account_map() -> dict:
	"""{gst_account_head: gst_tax_type} for the site — the set of TRUE GST
	accounts. ERPNext writes every taxes-table account head (including freight /
	cartage charge accounts) into item_tax_rate, so the scheme must scale/relabel
	only the heads in this map and never a charge row. Empty (a no-op) where
	india_compliance is absent, e.g. the test site."""
	try:
		from india_compliance.gst_india.utils import get_gst_account_gst_tax_type_map

		return get_gst_account_gst_tax_type_map() or {}
	except Exception:
		return {}


class _MerchantExportTaxes(_CalculateTaxesAndTotals):
	"""Same engine as stock ERPNext, but after item_tax_rate is derived from the
	Item Tax Template it rescales the GST heads that ACTUALLY apply (the ones in
	the document's taxes table — CGST+SGST for an intra-state supplier, IGST for
	an inter-state one) so the per-line GST totals the concessional 0.1%. Only
	real GST accounts are touched: a freight/cartage charge row is left at its
	full amount even though ERPNext also lists its account in item_tax_rate."""

	def update_item_tax_map(self):
		super().update_item_tax_map()
		gst_map = _gst_account_map()
		applied = [
			t.account_head
			for t in (self.doc.get("taxes") or [])
			if t.account_head and gst_map.get(t.account_head)
		]
		if not applied:
			# GST rows not on the taxes table yet (an early pass), or no GST at
			# all — a later recompute, once india_compliance has added them, does
			# the scaling
			return
		for item in self.doc.items:
			try:
				rates = json.loads(item.item_tax_rate or "{}")
			except (ValueError, TypeError):
				continue
			heads = {h: flt(rates.get(h)) for h in applied if flt(rates.get(h)) > 0}
			total = sum(heads.values())
			if total <= 0:
				continue
			for head in heads:
				rates[head] = flt(heads[head] * MERCHANT_EXPORT_TOTAL_RATE / total, 6)
			item.item_tax_rate = json.dumps(rates)


from erpnext.buying.doctype.purchase_order.purchase_order import (  # noqa: E402
	PurchaseOrder,
)


class ExportFlowPurchaseOrder(PurchaseOrder):
	"""Stock Purchase Order in every respect except that, when the 0.1%
	merchant-export scheme is on, taxes compute at the concessional rate.
	Registered as the Purchase Order class via override_doctype_class.

	NB merchant_export_scheme can default from the supplier on desk-created POs
	(before_insert) — which now changes the charged tax, so the field is meant to
	be set deliberately; ExportFlow's own PO form always sets it before computing,
	so its preview and the saved PO agree."""

	def calculate_taxes_and_totals(self):
		if self.get("merchant_export_scheme") and not self.get("merchanting_trade"):
			_MerchantExportTaxes(self)
			# relabel ONLY the GST rows with their concessional per-head rate
			# (0.05% CGST/SGST, 0.1% IGST) so the printed rate matches the amount;
			# the per-item override otherwise leaves the nominal 9/18 on the row.
			# Read the clean rate off the rescaled item_tax_rate (uniform per head)
			# rather than amount/net, which a multi-line PO would round to 0.0502%.
			# Free-charge rows (freight/cartage) are never GST accounts → untouched.
			gst_map = _gst_account_map()
			head_rate: dict[str, float] = {}
			for item in self.get("items") or []:
				try:
					rates = json.loads(item.item_tax_rate or "{}")
				except (ValueError, TypeError):
					continue
				for head, rate in rates.items():
					if flt(rate) > flt(head_rate.get(head, 0)):
						head_rate[head] = flt(rate)
			for tax in self.get("taxes") or []:
				if gst_map.get(tax.account_head) and tax.account_head in head_rate:
					tax.rate = flt(head_rate[tax.account_head], 4)
			return
		super().calculate_taxes_and_totals()
