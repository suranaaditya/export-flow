import json

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_so_money_summary(sales_order: str) -> dict:
	"""Everything the SO detail screen needs in one round trip (spec §4.5):
	SO header, PFI list, LC list, and the money roll-up."""
	frappe.has_permission("Sales Order", "read", doc=sales_order, throw=True)
	# the PFI/LC lists below use frappe.get_all (no permission filter) — make
	# sure the caller may read those doctypes at all
	frappe.has_permission("Pro Forma Invoice", "read", throw=True)
	frappe.has_permission("Letter of Credit", "read", throw=True)

	so = frappe.db.get_value(
		"Sales Order",
		sales_order,
		[
			"name",
			"customer",
			"customer_name",
			"currency",
			"grand_total",
			"transaction_date",
			"delivery_date",
			"status",
			"docstatus",
			"incoterm",
			"named_place",
			"payment_terms_narrative",
			"company",
		],
		as_dict=True,
	)
	if not so:
		frappe.throw(_("Sales Order {0} not found").format(sales_order))

	pfis = frappe.get_all(
		"Pro Forma Invoice",
		filters={"sales_order": sales_order},
		fields=[
			"name",
			"status",
			"amount",
			"paid_amount",
			"stage_description",
			"pfi_date",
			"expected_payment_method",
			"currency",
		],
		order_by="pfi_date asc, name asc",
	)
	lcs = frappe.get_all(
		"Letter of Credit",
		filters={"sales_order": sales_order},
		fields=[
			"name",
			"lc_number",
			"status",
			"amount",
			"currency",
			"issuing_bank",
			"expiry_date",
			"latest_shipment_date",
		],
		order_by="creation asc",
	)

	active = [p for p in pfis if p.status != "Cancelled"]
	raised = flt(sum(flt(p.amount) for p in active), 2)
	received = flt(sum(flt(p.paid_amount) for p in active), 2)

	return {
		"so": so,
		"pfis": pfis,
		"lcs": lcs,
		"summary": {
			"so_value": flt(so.grand_total),
			"raised": raised,
			"received": received,
			"balance": flt(flt(so.grand_total) - received, 2),
		},
	}


@frappe.whitelist()
def get_so_items(sales_order: str) -> list[dict]:
	"""SO item rows for seeding the PFI items child table."""
	frappe.has_permission("Sales Order", "read", doc=sales_order, throw=True)
	return frappe.get_all(
		"Sales Order Item",
		filters={"parent": sales_order, "parenttype": "Sales Order"},
		fields=["name as so_detail", "item_code", "item_name", "qty", "uom", "rate", "amount"],
		order_by="idx asc",
	)


@frappe.whitelist()
def get_new_so_context() -> dict:
	"""Everything the in-app deal form needs in one round trip."""
	frappe.has_permission("Sales Order", "create", throw=True)

	company = frappe.db.get_single_value("Global Defaults", "default_company")
	company_currency = frappe.db.get_value("Company", company, "default_currency")

	return {
		"company": company,
		"company_currency": company_currency,
		"customers": frappe.get_all(
			"Customer",
			filters={"disabled": 0},
			fields=["name", "customer_name", "default_currency", "default_incoterm"],
			order_by="modified desc",
			limit_page_length=200,
		),
		"suppliers": frappe.get_all(
			"Supplier",
			filters={"disabled": 0},
			fields=["name", "supplier_name"],
			order_by="modified desc",
			limit_page_length=200,
		),
		"items": frappe.get_all(
			"Item",
			filters={"disabled": 0, "is_sales_item": 1},
			fields=["name", "item_name", "stock_uom", "pharmacopoeia_grade"],
			order_by="modified desc",
			limit_page_length=500,
		),
		"incoterms": frappe.get_all("Incoterm", pluck="name", order_by="name asc"),
		"currencies": frappe.get_all(
			"Currency", filters={"enabled": 1}, pluck="name", order_by="name asc"
		),
		"ports": frappe.get_all(
			"Port",
			filters={"disabled": 0},
			fields=["name", "unlocode", "city", "country", "mode"],
			order_by="country asc, port_name asc",
			limit_page_length=500,
		),
		"uoms": frappe.get_all(
			"UOM", filters={"enabled": 1}, pluck="name", order_by="name asc", limit_page_length=300
		),
		"countries": frappe.get_all("Country", pluck="name", order_by="name asc", limit_page_length=300),
	}


@frappe.whitelist()
def create_customer(values) -> dict:
	"""Quick-create from the deal form / Settings — fills the ERPNext-required
	group/territory with sensible defaults."""
	frappe.has_permission("Customer", "create", throw=True)
	if isinstance(values, str):
		values = json.loads(values)
	if not (values.get("customer_name") or "").strip():
		frappe.throw(_("Customer name is required"))
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": values["customer_name"].strip(),
			"customer_type": "Company",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
			"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			"default_currency": values.get("default_currency") or None,
			"default_incoterm": values.get("default_incoterm") or None,
			"destination_country": values.get("destination_country") or None,
		}
	).insert()
	return {"name": doc.name, "customer_name": doc.customer_name}


@frappe.whitelist()
def create_supplier(values) -> dict:
	frappe.has_permission("Supplier", "create", throw=True)
	if isinstance(values, str):
		values = json.loads(values)
	if not (values.get("supplier_name") or "").strip():
		frappe.throw(_("Supplier name is required"))
	doc = frappe.get_doc(
		{
			"doctype": "Supplier",
			"supplier_name": values["supplier_name"].strip(),
			"supplier_group": frappe.db.get_value("Supplier Group", {}, "name"),
			"country": values.get("country") or "India",
			"default_merchant_export_scheme": 1 if values.get("default_merchant_export_scheme") else 0,
		}
	).insert()
	return {"name": doc.name, "supplier_name": doc.supplier_name}


@frappe.whitelist()
def create_item(values) -> dict:
	"""Pharma trading item: never stocked (goods go supplier → port), always
	buyable and sellable."""
	frappe.has_permission("Item", "create", throw=True)
	if isinstance(values, str):
		values = json.loads(values)
	if not (values.get("item_name") or "").strip():
		frappe.throw(_("Item name is required"))
	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": values["item_name"].strip(),
			"item_name": values["item_name"].strip(),
			"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
			"stock_uom": values.get("stock_uom") or "Kg",
			"is_stock_item": 0,
			"is_sales_item": 1,
			"is_purchase_item": 1,
			"pharmacopoeia_grade": values.get("pharmacopoeia_grade") or None,
			"customs_tariff_number": values.get("customs_tariff_number") or None,
			"cas_number": values.get("cas_number") or None,
			"default_pack_size": values.get("default_pack_size") or None,
		}
	).insert()
	return {"name": doc.name, "item_name": doc.item_name, "stock_uom": doc.stock_uom}


@frappe.whitelist()
def get_item_info(item_code: str) -> dict:
	"""Row-fill details for the deal form's item grid."""
	frappe.has_permission("Item", "read", throw=True)
	item = frappe.db.get_value(
		"Item", item_code, ["item_name", "stock_uom", "standard_rate"], as_dict=True
	)
	if not item:
		frappe.throw(_("Item {0} not found").format(item_code))
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	item["default_supplier"] = frappe.db.get_value(
		"Item Default", {"parent": item_code, "company": company}, "default_supplier"
	) or frappe.db.get_value("Item Default", {"parent": item_code}, "default_supplier")
	return item


@frappe.whitelist()
def get_exchange_rate_to_company(currency: str) -> float:
	"""Selling exchange rate from the deal currency to the company currency
	(0 when unavailable — the form keeps the field manual)."""
	frappe.has_permission("Sales Order", "create", throw=True)
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	company_currency = frappe.db.get_value("Company", company, "default_currency")
	if not currency or currency == company_currency:
		return 1.0
	try:
		from erpnext.setup.utils import get_exchange_rate

		return flt(get_exchange_rate(currency, company_currency, args="for_selling"))
	except Exception:
		return 0.0


@frappe.whitelist()
def create_export_sales_order(deal) -> dict:
	"""Build the native Sales Order from the ExportFlow deal form.

	Suppliers are deliberately NOT captured here — the client negotiates
	procurement after the deal is booked. Lines stay plain at SO time; the
	Phase-3 PO flow sets supplier + delivered_by_supplier per line and maps
	the drop-ship POs with row-level SO links.
	"""
	frappe.has_permission("Sales Order", "create", throw=True)
	if isinstance(deal, str):
		deal = json.loads(deal)

	items = deal.get("items") or []
	if not items:
		frappe.throw(_("Add at least one item to the deal"))
	for idx, row in enumerate(items, start=1):
		if not row.get("item_code"):
			frappe.throw(_("Row {0}: item is required").format(idx))
		if flt(row.get("qty")) <= 0:
			frappe.throw(_("Row {0}: quantity must be greater than zero").format(idx))
		if flt(row.get("rate")) <= 0:
			frappe.throw(_("Row {0}: rate must be greater than zero").format(idx))

	company = frappe.db.get_single_value("Global Defaults", "default_company")
	company_currency = frappe.db.get_value("Company", company, "default_currency")
	currency = deal.get("currency") or company_currency
	conversion_rate = 1.0 if currency == company_currency else flt(deal.get("conversion_rate"))
	if conversion_rate <= 0:
		frappe.throw(_("Exchange rate must be greater than zero"))

	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": company,
			"customer": deal.get("customer"),
			"order_type": "Sales",
			"transaction_date": deal.get("transaction_date") or frappe.utils.nowdate(),
			"delivery_date": deal.get("delivery_date"),
			"currency": currency,
			"conversion_rate": conversion_rate,
			"incoterm": deal.get("incoterm") or None,
			"named_place": deal.get("named_place"),
			"payment_terms_narrative": deal.get("payment_terms_narrative"),
			"items": [
				{
					"item_code": row["item_code"],
					"qty": flt(row["qty"]),
					"rate": flt(row["rate"]),
				}
				for row in items
			],
		}
	)
	so.insert()

	if frappe.utils.cint(deal.get("submit")):
		frappe.has_permission("Sales Order", "submit", throw=True)
		so.submit()

	return {"name": so.name, "docstatus": so.docstatus}


@frappe.whitelist()
def submit_sales_order(name: str) -> dict:
	doc = frappe.get_doc("Sales Order", name)
	doc.check_permission("submit")
	if doc.docstatus != 0:
		frappe.throw(_("Sales Order {0} is not a draft").format(name))
	doc.submit()
	return {"name": doc.name, "docstatus": doc.docstatus}


def _draft_po_qty(so_detail: str) -> float:
	"""Quantity already covered by DRAFT POs for an SO line (submitted POs are
	reflected in the SO item's ordered_qty by ERPNext itself)."""
	return flt(
		frappe.db.sql(
			"""SELECT COALESCE(SUM(poi.qty), 0)
			   FROM `tabPurchase Order Item` poi
			   JOIN `tabPurchase Order` po ON po.name = poi.parent
			   WHERE poi.sales_order_item = %s AND po.docstatus = 0""",
			(so_detail,),
		)[0][0]
	)


def _shipped_qty(so_detail: str) -> float:
	return flt(
		frappe.db.sql(
			"""SELECT COALESCE(SUM(qty), 0) FROM `tabExport Shipment Item`
			   WHERE so_detail = %s""",
			(so_detail,),
		)[0][0]
	)


def _ordered_in_txn_uom(line) -> float:
	"""ordered_qty is tracked in stock UOM — convert to the line's UOM."""
	return flt(line.ordered_qty) / (flt(line.get("conversion_factor")) or 1.0)


def _delivered_shipped_split(so_detail: str) -> tuple[float, float]:
	"""(total shipped, of which still in transit) for an SO line — in-transit
	means on a shipment whose Delivered milestone is not yet completed."""
	row = frappe.db.sql(
		"""SELECT COALESCE(SUM(esi.qty), 0) AS total,
		          COALESCE(SUM(CASE WHEN sm.completed = 1 THEN 0 ELSE esi.qty END), 0) AS in_transit
		   FROM `tabExport Shipment Item` esi
		   LEFT JOIN `tabShipment Milestone` sm
		          ON sm.parent = esi.parent AND sm.milestone = 'Delivered'
		   WHERE esi.so_detail = %s""",
		(so_detail,),
		as_dict=True,
	)[0]
	return flt(row.total, 3), flt(row.in_transit, 3)


@frappe.whitelist()
def get_so_procurement(sales_order: str) -> dict:
	"""Per-line procurement state for the SO screen: ordered (submitted),
	draft-covered, remaining, shipped/in-transit, and the POs per line."""
	frappe.has_permission("Sales Order", "read", doc=sales_order, throw=True)
	frappe.has_permission("Purchase Order", "read", throw=True)

	company = frappe.db.get_single_value("Global Defaults", "default_company")
	lines = frappe.get_all(
		"Sales Order Item",
		filters={"parent": sales_order, "parenttype": "Sales Order"},
		fields=[
			"name as so_detail",
			"item_code",
			"item_name",
			"qty",
			"uom",
			"rate",
			"ordered_qty",
			"conversion_factor",
		],
		order_by="idx asc",
	)
	for line in lines:
		line["ordered_qty"] = flt(_ordered_in_txn_uom(line), 3)
		line["draft_qty"] = flt(_draft_po_qty(line.so_detail), 3)
		line["remaining"] = flt(
			max(0.0, flt(line.qty) - line["ordered_qty"] - line["draft_qty"]), 3
		)
		shipped, in_transit = _delivered_shipped_split(line.so_detail)
		line["shipped_qty"] = shipped
		line["in_transit_qty"] = in_transit
		line.pop("conversion_factor", None)
		line["pos"] = frappe.db.sql(
			"""SELECT po.name, po.supplier, po.docstatus, poi.qty, poi.rate,
			          po.merchant_export_scheme, po.gst_export_deadline
			   FROM `tabPurchase Order Item` poi
			   JOIN `tabPurchase Order` po ON po.name = poi.parent
			   WHERE poi.sales_order_item = %s AND po.docstatus < 2
			   ORDER BY po.creation asc""",
			(line.so_detail,),
			as_dict=True,
		)
	return {"lines": lines, "company_currency": frappe.db.get_value("Company", company, "default_currency")}


@frappe.whitelist()
def create_purchase_order(sales_order: str, selections) -> dict:
	"""Negotiated-procurement flow: the user picks supplier, qty and buying
	rate per SO line. SO rows get supplier + delivered_by_supplier, then
	ERPNext's drop-ship mapper creates one PO per supplier with row-level
	SO links; our negotiated rates and quantities are applied on top.

	The mapper keys its selections by item_code, so it is called once per
	supplier and the result is asserted to cover every selection — the same
	item routed to two suppliers would otherwise be silently collapsed."""
	from erpnext.selling.doctype.sales_order.sales_order import make_purchase_order

	frappe.has_permission("Purchase Order", "create", throw=True)
	if isinstance(selections, str):
		selections = json.loads(selections)
	if not selections:
		frappe.throw(_("Pick at least one line"))

	# serialise competing orders against the same SO (remaining-qty TOCTOU)
	frappe.db.sql(
		"SELECT name FROM `tabSales Order Item` WHERE parent = %s FOR UPDATE", (sales_order,)
	)

	so = frappe.get_doc("Sales Order", sales_order)
	if so.docstatus != 1:
		frappe.throw(_("Sales Order {0} must be submitted first").format(sales_order))
	so_rows = {row.name: row for row in so.items}

	company_currency = frappe.db.get_value("Company", so.company, "default_currency")

	by_detail: dict[str, dict] = {}
	for sel in selections:
		so_detail = sel.get("so_detail")
		row = so_rows.get(so_detail)
		if not row:
			frappe.throw(_("Unknown sales order line {0}").format(so_detail))
		if so_detail in by_detail:
			frappe.throw(_("Line {0} picked twice").format(row.item_code))
		ordered = flt(row.ordered_qty) / (flt(row.conversion_factor) or 1.0)
		remaining = flt(row.qty) - ordered - _draft_po_qty(so_detail)
		qty = flt(sel.get("qty")) or remaining
		if qty <= 0:
			frappe.throw(_("Line {0}: nothing left to order").format(row.item_code))
		if qty > remaining + 1e-6:
			frappe.throw(
				_("Line {0}: only {1} remains unordered").format(row.item_code, flt(remaining, 3))
			)
		if flt(sel.get("rate")) <= 0:
			frappe.throw(_("Line {0}: buying rate is required").format(row.item_code))
		if not sel.get("supplier"):
			frappe.throw(_("Line {0}: supplier is required").format(row.item_code))
		by_detail[so_detail] = {
			"supplier": sel["supplier"],
			"qty": qty,
			"rate": flt(sel["rate"]),
			"item_code": row.item_code,
		}

	# flag the chosen rows as drop-ship with their negotiated supplier
	for so_detail, sel in by_detail.items():
		current = frappe.db.get_value(
			"Sales Order Item", so_detail, ["supplier", "delivered_by_supplier"], as_dict=True
		)
		if current.supplier != sel["supplier"] or not current.delivered_by_supplier:
			frappe.db.set_value(
				"Sales Order Item",
				so_detail,
				{"supplier": sel["supplier"], "delivered_by_supplier": 1},
				update_modified=False,
			)

	# one mapper call per supplier, with only that supplier's item codes
	suppliers = sorted({sel["supplier"] for sel in by_detail.values()})
	created = []
	placed_details: set[str] = set()
	for supplier in suppliers:
		selected_items = [
			{"item_code": sel["item_code"], "supplier": supplier}
			for sel in by_detail.values()
			if sel["supplier"] == supplier
		]
		pos = make_purchase_order(sales_order, selected_items=selected_items)
		for po in pos:
			# keep only the rows the user actually selected for THIS supplier
			kept = []
			for row in po.items:
				sel = by_detail.get(row.sales_order_item)
				if sel and sel["supplier"] == po.supplier:
					row.qty = sel["qty"]
					row.rate = sel["rate"]
					kept.append(row)
					placed_details.add(row.sales_order_item)
			if not kept:
				frappe.delete_doc("Purchase Order", po.name, force=True, ignore_permissions=True)
				continue
			po.items = kept
			for idx, row in enumerate(po.items, start=1):
				row.idx = idx
			# procurement is negotiated in the company currency, regardless of
			# the supplier's default currency
			if po.currency != company_currency:
				po.currency = company_currency
				po.conversion_rate = 1
			po.save()
			created.append({"name": po.name, "supplier": po.supplier})

	missing = set(by_detail.keys()) - placed_details
	if missing:
		# rolls back everything in this request, including the db_set flags
		names = ", ".join(by_detail[d]["item_code"] for d in missing)
		frappe.throw(_("Could not place these lines on a purchase order: {0}").format(names))
	if not created:
		frappe.throw(_("No purchase order could be created from the selection"))
	return {"purchase_orders": created}


@frappe.whitelist()
def submit_purchase_order(name: str) -> dict:
	doc = frappe.get_doc("Purchase Order", name)
	doc.check_permission("submit")
	if doc.docstatus != 0:
		frappe.throw(_("Purchase Order {0} is not a draft").format(name))
	doc.submit()
	return {"name": doc.name, "docstatus": doc.docstatus}


@frappe.whitelist()
def get_purchase_orders() -> list[dict]:
	"""Purchases list rows with SO references and the GST clock."""
	frappe.has_permission("Purchase Order", "read", throw=True)
	# get_list (unlike get_all) applies the caller's role/user permissions
	pos = frappe.get_list(
		"Purchase Order",
		filters={"docstatus": ["<", 2]},
		fields=[
			"name",
			"supplier",
			"supplier_name",
			"transaction_date",
			"grand_total",
			"currency",
			"status",
			"docstatus",
			"merchant_export_scheme",
			"supplier_invoice_no",
			"supplier_invoice_date",
			"gst_export_deadline",
		],
		order_by="transaction_date desc, creation desc",
		limit_page_length=100,
	)
	for po in pos:
		po["sales_orders"] = frappe.get_all(
			"Purchase Order Item",
			filters={"parent": po.name, "sales_order": ["is", "set"]},
			pluck="sales_order",
			distinct=True,
		)
	return pos


@frappe.whitelist()
def get_po_detail(name: str) -> dict:
	frappe.has_permission("Purchase Order", "read", doc=name, throw=True)
	po = frappe.get_doc("Purchase Order", name)
	items = [
		{
			"name": row.name,
			"item_code": row.item_code,
			"item_name": row.item_name,
			"qty": row.qty,
			"uom": row.uom,
			"rate": row.rate,
			"amount": row.amount,
			"sales_order": row.sales_order,
			"sales_order_item": row.sales_order_item,
			"delivered_by_supplier": row.delivered_by_supplier,
		}
		for row in po.items
	]
	shipments = frappe.db.sql(
		"""SELECT DISTINCT esi.parent AS shipment, es.current_milestone, es.mode, es.etd
		   FROM `tabExport Shipment Item` esi
		   JOIN `tabExport Shipment` es ON es.name = esi.parent
		   WHERE esi.purchase_order = %s""",
		(name,),
		as_dict=True,
	)
	return {
		"po": {
			"name": po.name,
			"supplier": po.supplier,
			"supplier_name": po.supplier_name,
			"transaction_date": po.transaction_date,
			"schedule_date": po.schedule_date,
			"status": po.status,
			"docstatus": po.docstatus,
			"currency": po.currency,
			"grand_total": po.grand_total,
			"merchant_export_scheme": po.merchant_export_scheme,
			"supplier_invoice_no": po.supplier_invoice_no,
			"supplier_invoice_date": po.supplier_invoice_date,
			"gst_export_deadline": po.gst_export_deadline,
		},
		"items": items,
		"shipments": shipments,
	}


@frappe.whitelist()
def get_shippable_lines(customer: str) -> list[dict]:
	"""Submitted SO lines of this customer with unshipped quantity, plus the
	PO sourcing each line (for auto-linking on the shipment)."""
	frappe.has_permission("Sales Order", "read", throw=True)
	frappe.has_permission("Export Shipment", "read", throw=True)

	lines = frappe.db.sql(
		"""SELECT soi.name AS so_detail, soi.parent AS sales_order, soi.item_code,
		          soi.item_name, soi.qty, soi.uom
		   FROM `tabSales Order Item` soi
		   JOIN `tabSales Order` so ON so.name = soi.parent
		   WHERE so.docstatus = 1 AND so.customer = %s AND so.status != 'Closed'
		   ORDER BY so.transaction_date desc, soi.idx asc""",
		(customer,),
		as_dict=True,
	)
	out = []
	for line in lines:
		shipped = _shipped_qty(line.so_detail)
		remaining = flt(flt(line.qty) - shipped, 3)
		if remaining <= 1e-6:
			continue
		line["shipped_qty"] = flt(shipped, 3)
		line["remaining"] = remaining

		# one sub-row per sourcing PO line, so multi-sourced SO lines ship
		# (and carry their GST clocks) against the right PO
		po_rows = frappe.db.sql(
			"""SELECT poi.name AS po_detail, poi.parent AS purchase_order, poi.qty AS po_qty,
			          po.supplier
			   FROM `tabPurchase Order Item` poi
			   JOIN `tabPurchase Order` po ON po.name = poi.parent
			   WHERE poi.sales_order_item = %s AND po.docstatus = 1
			   ORDER BY po.creation asc""",
			(line.so_detail,),
			as_dict=True,
		)
		left = remaining
		emitted = False
		for po_row in po_rows:
			if left <= 1e-6:
				break
			shipped_from_po = flt(
				frappe.db.sql(
					"SELECT COALESCE(SUM(qty), 0) FROM `tabExport Shipment Item` WHERE po_detail = %s",
					(po_row.po_detail,),
				)[0][0]
			)
			po_capacity = flt(min(flt(po_row.po_qty) - shipped_from_po, left), 3)
			if po_capacity <= 1e-6:
				continue
			sub = dict(line)
			sub["remaining"] = po_capacity
			sub["purchase_order"] = po_row.purchase_order
			sub["po_detail"] = po_row.po_detail
			sub["supplier"] = po_row.supplier
			out.append(sub)
			left = flt(left - po_capacity, 3)
			emitted = True
		if left > 1e-6 or not emitted:
			sub = dict(line)
			sub["remaining"] = flt(left, 3)
			sub["purchase_order"] = None
			sub["po_detail"] = None
			sub["supplier"] = None
			out.append(sub)
	return out


@frappe.whitelist()
def create_shipment(payload) -> dict:
	frappe.has_permission("Export Shipment", "create", throw=True)
	if isinstance(payload, str):
		payload = json.loads(payload)

	items = payload.get("items") or []
	if not items:
		frappe.throw(_("Pick at least one line to ship"))

	doc = frappe.get_doc(
		{
			"doctype": "Export Shipment",
			"customer": payload.get("customer"),
			"mode": payload.get("mode") or "Sea",
			"incoterm": payload.get("incoterm") or None,
			"cha": payload.get("cha") or None,
			"port_of_loading": payload.get("port_of_loading") or None,
			"port_of_discharge": payload.get("port_of_discharge") or None,
			"final_destination": payload.get("final_destination"),
			"etd": payload.get("etd") or None,
			"eta": payload.get("eta") or None,
			"letter_of_credit": payload.get("letter_of_credit") or None,
			"items": [
				{
					"item_code": row.get("item_code"),
					"qty": flt(row.get("qty")),
					"uom": row.get("uom"),
					"batch_no": row.get("batch_no"),
					"sales_order": row.get("sales_order"),
					"so_detail": row.get("so_detail"),
					"purchase_order": row.get("purchase_order") or None,
					"po_detail": row.get("po_detail") or None,
					"pack_description": row.get("pack_description"),
				}
				for row in items
			],
		}
	)
	doc.insert()
	return {"name": doc.name}


@frappe.whitelist()
def get_shipments() -> list[dict]:
	frappe.has_permission("Export Shipment", "read", throw=True)
	rows = frappe.get_all(
		"Export Shipment",
		fields=["name", "customer", "customer_name", "mode", "current_milestone", "etd", "eta", "port_of_loading", "port_of_discharge"],
		order_by="creation desc",
		limit_page_length=100,
	)
	if rows:
		counts = frappe.db.sql(
			"""SELECT parent, COUNT(*) AS total, SUM(completed) AS done
			   FROM `tabShipment Milestone`
			   WHERE parent IN %s AND parenttype = 'Export Shipment'
			   GROUP BY parent""",
			(tuple(r.name for r in rows),),
			as_dict=True,
		)
		by_parent = {c.parent: c for c in counts}
		for row in rows:
			c = by_parent.get(row.name)
			row["milestones_total"] = c.total if c else 0
			row["milestones_done"] = int(c.done or 0) if c else 0
	return rows


@frappe.whitelist()
def get_shipment_detail(name: str) -> dict:
	frappe.has_permission("Export Shipment", "read", doc=name, throw=True)
	doc = frappe.get_doc("Export Shipment", name)

	items = []
	for row in doc.items:
		so_qty = flt(frappe.db.get_value("Sales Order Item", row.so_detail, "qty"))
		shipped_total = _shipped_qty(row.so_detail)
		# fall back through the SO line when the shipment was booked before
		# the PO existed (backfill normally fixes this on PO submit)
		po_name = row.purchase_order
		if not po_name:
			po_name = frappe.db.get_value(
				"Purchase Order Item",
				{"sales_order_item": row.so_detail, "docstatus": 1},
				"parent",
			)
		po = (
			frappe.db.get_value(
				"Purchase Order",
				po_name,
				["supplier_name", "merchant_export_scheme", "gst_export_deadline", "docstatus"],
				as_dict=True,
			)
			if po_name
			else None
		)
		items.append(
			{
				"name": row.name,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"batch_no": row.batch_no,
				"qty": row.qty,
				"uom": row.uom,
				"pack_description": row.pack_description,
				"sales_order": row.sales_order,
				"so_detail": row.so_detail,
				"so_qty": so_qty,
				"so_shipped_total": shipped_total,
				"purchase_order": po_name,
				"po_cancelled": 1 if po and po.docstatus == 2 else 0,
				"supplier": po.supplier_name if po else None,
				"merchant_export_scheme": po.merchant_export_scheme if po else 0,
				"gst_export_deadline": po.gst_export_deadline if po else None,
			}
		)

	lc = None
	if doc.letter_of_credit:
		lc = frappe.db.get_value(
			"Letter of Credit",
			doc.letter_of_credit,
			["name", "lc_number", "status", "expiry_date", "latest_shipment_date", "issuing_bank"],
			as_dict=True,
		)

	export_done_on = doc.export_completed_on()

	return {
		"export_completed_on": str(export_done_on) if export_done_on else None,
		"shipment": {
			f: doc.get(f)
			for f in (
				"name",
				"customer",
				"customer_name",
				"mode",
				"current_milestone",
				"incoterm",
				"cha",
				"port_of_loading",
				"port_of_discharge",
				"final_destination",
				"etd",
				"eta",
				"vessel",
				"voyage",
				"booking_number",
				"container_numbers",
				"vgm_filed",
				"shipping_bill_number",
				"shipping_bill_date",
				"leo_date",
				"bl_number",
				"bl_date",
				"egm_number",
				"egm_date",
				"airline",
				"flight_number",
				"awb_number",
				"awb_date",
				"letter_of_credit",
				"notes",
			)
		},
		"milestones": [
			{
				"name": m.name,
				"milestone": m.milestone,
				"planned_date": m.planned_date,
				"actual_date": m.actual_date,
				"completed": m.completed,
			}
			for m in doc.milestones
		],
		"items": items,
		"lc": lc,
		"sales_orders": sorted({row.sales_order for row in doc.items}),
	}


@frappe.whitelist()
def set_shipment_milestone(shipment: str, row: str, completed=1, actual_date=None) -> str:
	doc = frappe.get_doc("Export Shipment", shipment)
	doc.check_permission("write")
	doc.set_milestone(row, bool(frappe.utils.cint(completed)), actual_date)
	return doc.current_milestone


@frappe.whitelist()
def pfi_set_status(name: str, action: str):
	"""Controlled status transitions from the UI: 'sent' or 'cancel'."""
	# row lock: serialise against concurrent Payment Entry submissions
	doc = frappe.get_doc("Pro Forma Invoice", name, for_update=True)
	doc.check_permission("write")
	if action == "sent":
		doc.mark_sent()
	elif action == "cancel":
		doc.mark_cancelled()
	else:
		frappe.throw(_("Unknown action {0}").format(action))
	return doc.status
