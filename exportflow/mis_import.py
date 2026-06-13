"""Import MN Globex's historical MIS export sheet into ExportFlow.

Reads the cleaned JSON produced by scripts_mis_clean.py and creates, under the
ExportFlow company: masters (customers / items / suppliers / ports / CHAs),
submitted Sales Orders, Export Shipments, Export Incentives (RoDTEP + Drawback)
and Export Realizations. Idempotent at group granularity — a group whose export
invoice already has a realization is skipped, so re-running never duplicates.

Run on the server:
    bench --site <site> execute exportflow.mis_import.run \\
        --kwargs "{'path': '/tmp/mis_clean.json', 'company': 'MN Globex', 'dry_run': True}"
"""

import json

import frappe
from frappe.utils import add_days, flt

from exportflow.mtt import EXPORT_FROM_INDIA, MERCHANTING

USD_FALLBACK_RATE = 85.0  # FY25-26 ballpark when the sheet leaves the $ rate blank
GENERIC = {"third country", "na", "nil", "cancelled", "-"}


def _is_generic(v) -> bool:
	return not v or str(v).strip().lower() in GENERIC


def _is_merchanting(group) -> bool:
	"""The MIS marks third-country / merchanting rows by putting "Third Country"
	in the CHA and forwarder columns (note the recurring typo "Third Counrty").
	Goods ship A→B without entering India."""
	for key in ("cha", "forwarder"):
		v = (group.get(key) or "").strip().lower()
		if v.startswith("third coun"):
			return True
	return False


def _import_value_inr(group, rate: float) -> float | None:
	"""Buy-leg outlay in INR from the per-item supplier rates (for the MTT
	net-FX-profit check). None when the sheet carries no supplier pricing."""
	fcy = sum(
		flt(it["qty"]) * flt(it.get("supplier_rate"))
		for it in group["items"]
		if it.get("qty") and it.get("supplier_rate")
	)
	return flt(fcy * rate, 2) if fcy else None


def _mtt_shipment_fields(group, merchanting: bool, rate: float) -> dict:
	"""MTT fields to stamp on a merchanting shipment from the MIS row. The sheet
	carries no import-payment date, so the 9-month clock is anchored on the
	export (B/L) date as a proxy and the outlay clock stays manual."""
	if not merchanting:
		return {}
	sup_name = group.get("supplier_name")
	fields = {
		"mtt_ad_bank": group.get("bank") or None,
		"mtt_import_supplier": (
			ensure_supplier(sup_name) if sup_name and not _is_generic(sup_name) else None
		),
		"mtt_commencement_date": group.get("bl_date") or group.get("shipping_bill_date") or None,
		"mtt_import_value_inr": _import_value_inr(group, rate),
	}
	if flt(group.get("amount_received")) > 0 and group.get("pay_received_date"):
		fields["mtt_completion_date"] = group.get("pay_received_date")
	return fields


def _linked_po_items(items, so, txn) -> list[dict]:
	"""PO lines for a supplier's items, each linked to the SO line of the same
	item so the shipment shows its source PO and the SO↔PO relationship holds.
	A given SO line is linked only once across the group's suppliers — the used
	set rides on the SO doc instance so successive supplier buckets share it."""
	so_by_code: dict = {}
	for r in so.items:
		so_by_code.setdefault(r.item_code, r)
	used: set = getattr(so, "_ef_linked_so_rows", None) or set()
	so._ef_linked_so_rows = used
	po_items = []
	for it in items:
		item_code = ensure_item(it["product"], it.get("hs_code"), it.get("uom") or "Kg")
		line = {
			"item_code": item_code,
			"qty": flt(it["qty"]),
			"rate": flt(it["supplier_rate"]),
			"uom": ensure_uom(it.get("uom") or "Kg"),
			"schedule_date": add_days(txn, 7),
		}
		so_row = so_by_code.get(item_code)
		if so_row and so_row.name not in used:
			line.update(
				{"sales_order": so.name, "sales_order_item": so_row.name, "delivered_by_supplier": 1}
			)
			used.add(so_row.name)
		po_items.append(line)
	return po_items


def _flag_dropship_so_rows(po, supplier):
	"""Stamp the drop-ship supplier on the SO lines a PO sources (mirrors the
	in-app negotiated-PO flow) so the link is symmetric on both documents."""
	for row in po.items:
		if row.sales_order_item:
			frappe.db.set_value(
				"Sales Order Item",
				row.sales_order_item,
				{"supplier": supplier, "delivered_by_supplier": 1},
				update_modified=False,
			)


# ---------------------------------------------------------------- masters

def _suppress_gst_company_fixtures():
	"""india_compliance builds GST tax templates on Company on_update that
	reference this site's pre-configured GST accounts — that fails for a fresh
	company and would touch the shared site's GST config. ExportFlow uses no
	GST on imported orders, so no-op those hooks just for the creation."""
	patched = []
	for mod in (
		"india_compliance.gst_india.overrides.company",
		"india_compliance.income_tax_india.overrides.company",
	):
		try:
			m = frappe.get_module(mod)
			if hasattr(m, "make_company_fixtures"):
				patched.append((m, m.make_company_fixtures))
				m.make_company_fixtures = lambda *a, **k: None
		except Exception:
			pass
	return patched


def ensure_company(name: str) -> str:
	if frappe.db.exists("Company", name):
		return name
	patched = _suppress_gst_company_fixtures()
	try:
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": name,
				"abbr": "MNG",
				"default_currency": "INR",
				"country": "India",
			}
		).insert(ignore_permissions=True)
	finally:
		for m, fn in patched:
			m.make_company_fixtures = fn
	return name


def ensure_uom(uom: str) -> str:
	uom = uom or "Kg"
	if not frappe.db.exists("UOM", uom):
		frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)
	return uom


def ensure_customer(name: str, country: str | None) -> str:
	existing = frappe.db.exists("Customer", {"customer_name": name})
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Company",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
			"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			"default_currency": "USD",
			"destination_country": country if country and frappe.db.exists("Country", country) else None,
		}
	).insert(ignore_permissions=True)
	return doc.name


def ensure_supplier(name: str) -> str:
	existing = frappe.db.exists("Supplier", {"supplier_name": name})
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Supplier",
			"supplier_name": name,
			"supplier_group": frappe.db.get_value("Supplier Group", {}, "name"),
		}
	).insert(ignore_permissions=True)
	return doc.name


def ensure_tariff(hs_code: str | None) -> str | None:
	"""customs_tariff_number is an india_compliance link — create the HS record
	if it doesn't exist, but never let it break the import (best-effort)."""
	if not hs_code or not frappe.db.exists("DocType", "Customs Tariff Number"):
		return None
	if frappe.db.exists("Customs Tariff Number", hs_code):
		return hs_code
	frappe.db.savepoint("tariff")
	try:
		frappe.get_doc(
			{"doctype": "Customs Tariff Number", "tariff_number": hs_code}
		).insert(ignore_permissions=True)
		return hs_code
	except Exception:
		frappe.db.rollback(save_point="tariff")
		return None


def ensure_item(product: str, hs_code: str | None, uom: str) -> str:
	existing = frappe.db.exists("Item", {"item_name": product})
	if existing:
		return existing
	code = product[:140]
	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": product,
			"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
			"stock_uom": ensure_uom(uom),
			"is_stock_item": 0,
			"is_sales_item": 1,
			"is_purchase_item": 1,
			"customs_tariff_number": ensure_tariff(hs_code),
		}
	).insert(ignore_permissions=True)
	return doc.name


def ensure_port(name: str, mode: str) -> str | None:
	if _is_generic(name):
		return None
	if frappe.db.exists("Port", name):
		return name
	frappe.get_doc(
		{
			"doctype": "Port",
			"port_name": name,
			"mode": "Air" if mode == "Air" else "Sea",
		}
	).insert(ignore_permissions=True)
	return name


def ensure_cha(name: str) -> str | None:
	if _is_generic(name):
		return None
	existing = frappe.db.exists("CHA", {"cha_name": name})
	if existing:
		return existing
	return frappe.get_doc({"doctype": "CHA", "cha_name": name}).insert(ignore_permissions=True).name


# ---------------------------------------------------------------- per group

def _mode(group) -> str:
	raw = (group.get("mode_raw") or "").lower()
	return "Air" if "air" in raw else "Sea"


def _currency_rate(group) -> tuple[str, float]:
	rate = group.get("dollar_rate")
	if rate and rate < 2:
		return "INR", 1.0
	return "USD", flt(rate) or USD_FALLBACK_RATE


def import_group(group: dict, company: str) -> dict:
	inv = group.get("export_invoice") or group.get("buyer_po_no")
	if not inv:
		return {"invoice": None, "status": "skipped", "reason": "no invoice/PO key"}
	if frappe.db.exists("Export Realization", {"export_invoice": inv, "company": company}):
		return {"invoice": inv, "status": "exists"}

	currency, rate = _currency_rate(group)
	customer = ensure_customer(group["buyer"], group.get("country"))
	mode = _mode(group)

	# --- sales order ---
	txn_date = group.get("shipping_bill_date") or group.get("bl_date") or "2025-04-01"
	so_items = []
	for it in group["items"]:
		if not (it.get("qty") and it.get("rate")):
			continue
		item_code = ensure_item(it["product"], it.get("hs_code"), it.get("uom") or "Kg")
		so_items.append(
			{
				"item_code": item_code,
				"qty": flt(it["qty"]),
				"rate": flt(it["rate"]),
				"uom": ensure_uom(it.get("uom") or "Kg"),
				"conversion_factor": 1,
				"delivery_date": add_days(txn_date, 15),
			}
		)
	if not so_items:
		return {"invoice": inv, "status": "skipped", "reason": "no priced item lines"}

	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": company,
			"customer": customer,
			"order_type": "Sales",
			"transaction_date": txn_date,
			"delivery_date": add_days(txn_date, 15),
			"currency": currency,
			"conversion_rate": rate,
			"po_no": group.get("buyer_po_no"),
			"items": so_items,
		}
	)
	so.insert(ignore_permissions=True)
	so.submit()

	# --- shipment (lines mapped to the SO rows we just created) ---
	pol = ensure_port(group.get("port_of_loading"), mode)
	pod = ensure_port(group.get("pod"), mode)
	cha = ensure_cha(group.get("cha"))
	merchanting = _is_merchanting(group)

	ship_items = []
	for row, it in zip(so.items, [i for i in group["items"] if i.get("qty") and i.get("rate")]):
		ship_items.append(
			{
				"item_code": row.item_code,
				"qty": row.qty,
				"uom": row.uom,
				"sales_order": so.name,
				"so_detail": row.name,
			}
		)
	shipment = frappe.get_doc(
		{
			"doctype": "Export Shipment",
			"company": company,
			"customer": customer,
			"mode": mode,
			"trade_type": MERCHANTING if merchanting else EXPORT_FROM_INDIA,
			"port_of_loading": pol,
			"port_of_discharge": pod,
			"final_destination": group.get("country") or group.get("pod"),
			"cha": cha,
			"shipping_bill_number": group.get("shipping_bill_no"),
			"shipping_bill_date": group.get("shipping_bill_date"),
			"egm_number": group.get("egm_no"),
			"egm_date": group.get("egm_date"),
			"bl_number": group.get("bl_no"),
			"bl_date": group.get("bl_date"),
			**_mtt_shipment_fields(group, merchanting, rate),
			"items": ship_items,
		}
	)
	shipment.insert(ignore_permissions=True)

	# --- procurement — one PO per ACTUAL supplier, linked to the SO lines so
	# the shipment shows its source PO (on_submit backfills the shipment links) ---
	buckets: dict[str, list] = {}
	for it in group["items"]:
		if not (it.get("qty") and it.get("supplier_rate")):
			continue
		sup_name = it.get("supplier_name") or group.get("supplier_name")
		if sup_name and not _is_generic(sup_name):
			buckets.setdefault(sup_name, []).append(it)
	for sup_name, items in buckets.items():
		supplier = ensure_supplier(sup_name)
		po_items = _linked_po_items(items, so, txn_date)
		# savepoint so one supplier's PO failure undoes only that PO
		frappe.db.savepoint("po")
		try:
			po = frappe.get_doc(
				{
					"doctype": "Purchase Order",
					"company": company,
					"supplier": supplier,
					"transaction_date": txn_date,
					"schedule_date": add_days(txn_date, 7),
					"currency": currency,
					"conversion_rate": rate,
					"items": po_items,
				}
			)
			po.insert(ignore_permissions=True)
			_flag_dropship_so_rows(po, supplier)
			po.submit()
		except Exception:
			# procurement is supplementary — never fail the export import on it
			frappe.db.rollback(save_point="po")

	# --- incentives ---
	if group.get("rodtep_amt") or group.get("rodtep_pct"):
		frappe.get_doc(
			{
				"doctype": "Export Incentive",
				"company": company,
				"scheme": "RoDTEP",
				"shipment": shipment.name,
				"status": "Scroll Generated" if group.get("rodtep_scroll") else "Pending",
				"fob_value": group.get("fob_value_inr"),
				"rate_pct": group.get("rodtep_pct"),
				"amount": group.get("rodtep_amt"),
				"scroll_number": group.get("rodtep_scroll"),
			}
		).insert(ignore_permissions=True)
	if group.get("dbk_amt") or group.get("dbk_pct"):
		frappe.get_doc(
			{
				"doctype": "Export Incentive",
				"company": company,
				"scheme": "Duty Drawback",
				"shipment": shipment.name,
				"status": "Credited" if group.get("dbk_received") else "Pending",
				"rate_pct": group.get("dbk_pct"),
				"amount": group.get("dbk_amt"),
				"drawback_serial": group.get("dbk_book"),
				"amount_received": group.get("dbk_received"),
			}
		).insert(ignore_permissions=True)

	# --- realization (also the idempotency marker for this group) ---
	received = flt(group.get("amount_received"))
	invoice_value = sum(flt(i.get("amount")) for i in group["items"] if i.get("amount"))
	if received <= 0:
		status = "Awaiting Realization"
	elif invoice_value and received < invoice_value * 0.98:
		# tolerance absorbs bank-charge/FX shortfalls on otherwise-full receipts
		status = "Partially Realized"
	else:
		status = "Realized"
	frappe.get_doc(
		{
			"doctype": "Export Realization",
			"company": company,
			"export_invoice": inv,
			"shipment": shipment.name,
			"customer": customer,
			"status": status,
			"currency": currency,
			"conversion_rate": rate,
			"invoice_value": invoice_value,
			"ad_bank": group.get("bank"),
			"fbc_number": group.get("fbc_no"),
			"firc_no": group.get("irm_no"),
			"document_submitted_date": group.get("doc_submit_date"),
			"remittance_date": group.get("pay_received_date"),
			"amount_received": received,
			"amount_received_inr": flt(received * rate, 2),
			"bank_charges": group.get("bank_charges"),
			"oc_received": 1 if (group.get("oc_received") or "").upper().startswith("RECEIV") else 0,
		}
	).insert(ignore_permissions=True)

	return {"invoice": inv, "status": "imported", "so": so.name, "shipment": shipment.name}


# ---------------------------------------------------------------- maintenance

def backfill_trade_types(path: str, company: str = "MN Globex", dry_run: int = 1) -> dict:
	"""Set trade_type (and the MTT fields) on shipments already imported, keyed
	by export invoice → realization → shipment. Idempotent: re-running just
	rewrites the same values. Saving each shipment re-runs the checklist engine,
	which removes the now-suppressed India-only documents on merchanting rows.

	Run on the server (the client JSON is not in the repo):
	    bench --site <site> execute exportflow.mis_import.backfill_trade_types \\
	        --kwargs "{'path': '/tmp/mis_clean.json', 'company': 'MN Globex', 'dry_run': False}"
	"""
	dry_run = int(dry_run)
	with open(path) as f:
		groups = json.load(f)
	if not frappe.db.exists("Company", company):
		frappe.throw(f"Unknown company {company}")

	result = {"merchanting": 0, "export": 0, "missing": 0, "company": company}
	for group in groups:
		inv = group.get("export_invoice") or group.get("buyer_po_no")
		if not inv:
			continue
		rel = frappe.db.get_value(
			"Export Realization",
			{"export_invoice": inv, "company": company},
			["name", "shipment"],
			as_dict=True,
		)
		if not rel or not rel.shipment or not frappe.db.exists("Export Shipment", rel.shipment):
			result["missing"] += 1
			continue

		merchanting = _is_merchanting(group)
		_currency, rate = _currency_rate(group)
		shp = frappe.get_doc("Export Shipment", rel.shipment)
		shp.trade_type = MERCHANTING if merchanting else EXPORT_FROM_INDIA
		for field, value in _mtt_shipment_fields(group, merchanting, rate).items():
			shp.set(field, value)
		shp.save(ignore_permissions=True)

		# the realization's FEMA clock changes basis for merchanting (MTT
		# completion, not export+15mo) — clear the due so validate recomputes it
		if merchanting:
			realization = frappe.get_doc("Export Realization", rel.name)
			realization.due_date = None
			realization.save(ignore_permissions=True)

		result["merchanting" if merchanting else "export"] += 1

	if dry_run:
		frappe.db.rollback()
		result["mode"] = "dry-run (rolled back)"
	else:
		frappe.db.commit()
		result["mode"] = "committed"
	frappe.logger().info(f"MIS trade-type backfill: {result}")
	return result


def relink_purchase_orders(path: str, company: str = "MN Globex", dry_run: int = 1) -> dict:
	"""Rebuild the imported POs with proper Sales Order links. The first import
	created per-supplier POs with no sales_order_item, so shipments showed no
	source PO and the SO↔PO relationship was missing. This deletes the
	company's POs and recreates them per group, linked to the group's SO
	(recovered via realization → shipment → SO line) and submitted — the PO
	on_submit hook then backfills the shipment-item PO links. SOs, shipments,
	realizations and incentives are untouched (their names are preserved).

	Run on the server:
	    bench --site <site> execute exportflow.mis_import.relink_purchase_orders \\
	        --kwargs "{'path': '/tmp/mis_clean.json', 'company': 'MN Globex', 'dry_run': False}"
	"""
	dry_run = int(dry_run)
	with open(path) as f:
		groups = json.load(f)
	if not frappe.db.exists("Company", company):
		frappe.throw(f"Unknown company {company}")

	deleted = 0
	for n in frappe.get_all("Purchase Order", filters={"company": company}, pluck="name"):
		doc = frappe.get_doc("Purchase Order", n)
		if doc.docstatus == 1:
			doc.flags.ignore_links = True
			doc.cancel()
		frappe.delete_doc("Purchase Order", n, force=True, ignore_permissions=True)
		deleted += 1

	result = {
		"deleted": deleted,
		"pos_created": 0,
		"linked_groups": 0,
		"skipped": 0,
		"errors": [],
		"company": company,
	}
	for group in groups:
		inv = group.get("export_invoice") or group.get("buyer_po_no")
		if not inv:
			continue
		frappe.db.savepoint("relink")
		try:
			shipment = frappe.db.get_value(
				"Export Realization", {"export_invoice": inv, "company": company}, "shipment"
			)
			so_name = (
				frappe.db.get_value(
					"Export Shipment Item",
					{"parent": shipment, "sales_order": ["is", "set"]},
					"sales_order",
				)
				if shipment
				else None
			)
			if not so_name:
				result["skipped"] += 1
				continue
			so = frappe.get_doc("Sales Order", so_name)
			currency, rate = _currency_rate(group)
			txn = group.get("shipping_bill_date") or group.get("bl_date") or "2025-04-01"

			buckets: dict[str, list] = {}
			for it in group["items"]:
				if not (it.get("qty") and it.get("supplier_rate")):
					continue
				sup_name = it.get("supplier_name") or group.get("supplier_name")
				if sup_name and not _is_generic(sup_name):
					buckets.setdefault(sup_name, []).append(it)

			created_here = 0
			for sup_name, items in buckets.items():
				supplier = ensure_supplier(sup_name)
				po_items = _linked_po_items(items, so, txn)
				po = frappe.get_doc(
					{
						"doctype": "Purchase Order",
						"company": company,
						"supplier": supplier,
						"transaction_date": txn,
						"schedule_date": add_days(txn, 7),
						"currency": currency,
						"conversion_rate": rate,
						"items": po_items,
					}
				)
				po.insert(ignore_permissions=True)
				_flag_dropship_so_rows(po, supplier)
				po.submit()  # on_submit backfills shipment-item PO links
				created_here += 1

			result["pos_created"] += created_here
			result["linked_groups" if created_here else "skipped"] += 1
			if not dry_run:
				frappe.db.commit()
		except Exception as e:
			frappe.db.rollback(save_point="relink")
			result["errors"].append({"invoice": inv, "error": str(e)[:200]})

	if dry_run:
		frappe.db.rollback()
		result["mode"] = "dry-run (rolled back)"
	else:
		frappe.db.commit()
		result["mode"] = "committed"
	frappe.logger().info(f"MIS PO relink: {result}")
	return result


def clear_company_data(company: str) -> dict:
	"""Delete the ExportFlow transactional docs for a company so the import can
	be re-run cleanly. Masters (customers/items/suppliers) are left in place —
	ensure_* is idempotent. Destructive; call deliberately."""
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(f"Unknown company {company}")
	counts = {}
	# plain (non-submittable) records first
	for dt in ("Export Realization", "Export Incentive"):
		names = frappe.get_all(dt, filters={"company": company}, pluck="name")
		for n in names:
			frappe.delete_doc(dt, n, force=True, ignore_permissions=True)
		counts[dt] = len(names)
	# shipments: on_trash cascades their Document Instances
	ships = frappe.get_all("Export Shipment", filters={"company": company}, pluck="name")
	for n in ships:
		frappe.delete_doc("Export Shipment", n, force=True, ignore_permissions=True)
	counts["Export Shipment"] = len(ships)
	# submittable ERPNext docs: cancel then delete
	for dt in ("Purchase Order", "Sales Order"):
		names = frappe.get_all(dt, filters={"company": company}, pluck="name")
		for n in names:
			doc = frappe.get_doc(dt, n)
			if doc.docstatus == 1:
				doc.flags.ignore_links = True
				doc.cancel()
			frappe.delete_doc(dt, n, force=True, ignore_permissions=True)
		counts[dt] = len(names)
	frappe.db.commit()
	return counts


# ---------------------------------------------------------------- entry point

def run(path: str, company: str = "MN Globex", dry_run: int = 1, set_default: int = 0) -> dict:
	"""Import the cleaned MIS JSON. dry_run rolls everything back after
	validating against the real controllers. set_default points ExportFlow
	Settings at the company (real runs only)."""
	dry_run = int(dry_run)
	with open(path) as f:
		groups = json.load(f)

	company = ensure_company(company)
	# several export invoices legitimately share one buyer PO number — allow it
	frappe.db.set_single_value("Selling Settings", "allow_against_multiple_purchase_orders", 1)
	results = {"imported": 0, "exists": 0, "skipped": 0, "errors": [], "company": company}

	for group in groups:
		inv = group.get("export_invoice") or group.get("buyer_po_no")
		# per-group savepoint: a bad group rolls back only itself, never the
		# company or the groups already imported
		frappe.db.savepoint("grp")
		try:
			r = import_group(group, company)
			if r["status"] == "imported":
				results["imported"] += 1
			elif r["status"] == "exists":
				results["exists"] += 1
			else:
				results["skipped"] += 1
			# commit per group on a real run so one bad row doesn't lose the rest
			if not dry_run:
				frappe.db.commit()
		except Exception as e:
			frappe.db.rollback(save_point="grp")
			results["errors"].append({"invoice": inv, "error": str(e)[:300]})

	if dry_run:
		frappe.db.rollback()
	elif int(set_default):
		frappe.db.set_single_value("ExportFlow Settings", "company", company)
		frappe.db.commit()

	results["mode"] = "dry-run (rolled back)" if dry_run else "committed"
	frappe.logger().info(f"MIS import: {results}")
	return results
