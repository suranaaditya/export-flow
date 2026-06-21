"""Quantity-only stock ledger for ExportFlow.

A deliberately lightweight ledger: one `ExportFlow Stock Ledger` row per movement,
with NO GL / accounting. MN Globex runs perpetual inventory, so a real ERPNext
stock voucher (Purchase Receipt / Delivery Note / Stock Entry) would post to the
books; we avoid that entirely and track quantity only. A Goods Receipt Note posts
stock IN at the receiving (port) warehouse; the shipment posts stock OUT at
departure. Every helper is idempotent per (voucher_type, voucher_no) so a re-save
never double-posts, and reversible on cancel.
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

GRN_VOUCHER = "Goods Receipt Note"
SHIPMENT_VOUCHER = "Export Shipment"


def maintain_stock_enabled() -> bool:
	"""Master switch for the stock regime (GRN stock-in + shipment stock-out).
	OFF unless ExportFlow Settings.maintain_stock is explicitly enabled — the
	regime is a behavioural change, so existing sites stay in pure drop-ship mode
	until the operator opts in. (The Settings field default is on, so saving
	Settings through the form turns it on.)"""
	return bool(frappe.db.get_single_value("ExportFlow Settings", "maintain_stock"))


def balance(item_code: str, warehouse: str) -> float:
	"""Net quantity on hand for an item at a warehouse (sum of signed rows)."""
	if not (item_code and warehouse):
		return 0.0
	total = frappe.db.sql(
		"select sum(qty) from `tabExportFlow Stock Ledger` where item_code=%s and warehouse=%s",
		(item_code, warehouse),
	)
	return flt(total[0][0]) if total and total[0][0] is not None else 0.0


def has_entries(voucher_type: str, voucher_no: str) -> bool:
	return bool(
		frappe.db.exists(
			"ExportFlow Stock Ledger", {"voucher_type": voucher_type, "voucher_no": voucher_no}
		)
	)


def _aggregate(rows):
	"""Collapse [(item, warehouse, qty), ...] by (item, warehouse)."""
	agg: dict = {}
	for item_code, warehouse, qty in rows:
		if not (item_code and warehouse) or not flt(qty):
			continue
		agg[(item_code, warehouse)] = agg.get((item_code, warehouse), 0.0) + flt(qty)
	return agg


def _write(agg, voucher_type, voucher_no, company):
	stamp = now_datetime()
	for (item_code, warehouse), qty in agg.items():
		if not flt(qty):
			continue
		frappe.get_doc(
			{
				"doctype": "ExportFlow Stock Ledger",
				"item_code": item_code,
				"warehouse": warehouse,
				"qty": flt(qty),
				"voucher_type": voucher_type,
				"voucher_no": voucher_no,
				"company": company,
				"posting_datetime": stamp,
			}
		).insert(ignore_permissions=True)


def post_in(rows, voucher_type, voucher_no, company=None):
	"""Stock IN — rows = [(item, warehouse, qty)] (qty magnitude). Idempotent."""
	if has_entries(voucher_type, voucher_no):
		return
	agg = {k: abs(v) for k, v in _aggregate(rows).items()}
	_write(agg, voucher_type, voucher_no, company)


def post_out(rows, voucher_type, voucher_no, company=None, allow_negative=False):
	"""Stock OUT — rows = [(item, warehouse, qty)] (qty magnitude to remove).
	Honours the site's no-negative-stock rule unless allow_negative. Idempotent."""
	if has_entries(voucher_type, voucher_no):
		return
	agg = {k: abs(v) for k, v in _aggregate(rows).items()}
	if not allow_negative:
		for (item_code, warehouse), qty in agg.items():
			avail = balance(item_code, warehouse)
			if flt(qty) - avail > 1e-6:
				frappe.throw(
					_(
						"Not enough stock of {0} at {1}: {2} on hand, {3} required by {4} {5}."
					).format(item_code, warehouse, avail, flt(qty), voucher_type, voucher_no)
				)
	_write({k: -v for k, v in agg.items()}, voucher_type, voucher_no, company)


def reverse(voucher_type, voucher_no):
	"""Remove every ledger row for a voucher (on cancel / un-post)."""
	for name in frappe.get_all(
		"ExportFlow Stock Ledger",
		filters={"voucher_type": voucher_type, "voucher_no": voucher_no},
		pluck="name",
	):
		frappe.delete_doc("ExportFlow Stock Ledger", name, ignore_permissions=True, force=True)
