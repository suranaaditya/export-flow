import frappe
from frappe.utils import add_days, getdate

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


def on_cancel(doc, method=None):
	clear_shipment_links(doc)


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
