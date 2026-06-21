import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from exportflow.company import exportflow_company


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
			"tc_name",
			"terms",
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
		"items": frappe.get_all(
			"Sales Order Item",
			filters={"parent": sales_order, "parenttype": "Sales Order"},
			fields=["item_code", "item_name", "qty", "uom", "rate", "amount"],
			order_by="idx asc",
		),
		"can": _doc_can("Sales Order", sales_order, status=so.status),
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

	company = exportflow_company()
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
		"item_tax_templates": _item_tax_templates(company),
		# selling-side terms templates only — the same master the PO uses,
		# segregated by the native selling/buying flags (see get_new_po_context)
		"terms_templates": frappe.get_all(
			"Terms and Conditions",
			filters={"disabled": 0, "selling": 1},
			pluck="name",
			order_by="name asc",
			limit_page_length=100,
		),
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


# scalar item-master fields the create/edit forms own
ITEM_SCALAR_FIELDS = (
	"pharmacopoeia_grade",
	"customs_tariff_number",
	"cas_number",
	"default_pack_size",
	"stock_uom",
)


def _item_has_gst_hsn() -> bool:
	"""india_compliance adds gst_hsn_code to Item — present on the GST site, not
	on the test site. Cache-safe meta check so the tax plumbing degrades cleanly
	where GST isn't installed."""
	return frappe.get_meta("Item").has_field("gst_hsn_code")


def _apply_item_tax_fields(doc, values) -> None:
	"""Set the GST HSN code (india_compliance, when the field exists and the code
	is in the master) and a SINGLE Item Tax Template row (Item.taxes) from the
	item-form values. The PO tax engine then auto-applies them: GST autofills
	from HSN on india_compliance, the tax template overrides per-item rates.

	Each field is touched only when its key is present in the payload, so a
	partial update never wipes an untouched field (mirrors update_item's scalar
	loop)."""
	if "gst_hsn_code" in values and _item_has_gst_hsn():
		hsn = (values.get("gst_hsn_code") or "").strip()
		if hsn and not frappe.db.exists("GST HSN Code", hsn):
			frappe.throw(_("GST HSN code {0} is not in the master").format(hsn))
		doc.gst_hsn_code = hsn or None
	if "item_tax_template" in values:
		# the app manages one tax template per item; refuse to silently flatten a
		# multi-row table set up in the desk (validity-dated rows etc.)
		if len(doc.get("taxes") or []) > 1:
			frappe.throw(
				_("{0} has multiple tax rows configured in the desk — edit them there.").format(
					doc.name or doc.item_name
				)
			)
		template = (values.get("item_tax_template") or "").strip()
		doc.set("taxes", [])
		if template:
			doc.append("taxes", {"item_tax_template": template})


@frappe.whitelist()
def create_item(values) -> dict:
	"""Pharma trading item: always buyable and sellable, carrying the GST HSN code
	+ Item Tax Template that drive PO tax autofill. Stocked only when the stock
	regime is on (goods are received at a port warehouse via a GRN); otherwise it
	stays a non-stock drop-ship item."""
	from exportflow.stock import maintain_stock_enabled

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
			"is_stock_item": 1 if maintain_stock_enabled() else 0,
			"is_sales_item": 1,
			"is_purchase_item": 1,
			"pharmacopoeia_grade": values.get("pharmacopoeia_grade") or None,
			"customs_tariff_number": values.get("customs_tariff_number") or None,
			"cas_number": values.get("cas_number") or None,
			"default_pack_size": values.get("default_pack_size") or None,
		}
	)
	_apply_item_tax_fields(doc, values)
	doc.insert()
	return {"name": doc.name, "item_name": doc.item_name, "stock_uom": doc.stock_uom}


@frappe.whitelist()
def update_item(name: str, values) -> dict:
	"""Edit an item master from the in-app form — scalar fields plus the GST HSN
	code and the single Item Tax Template (Item.taxes). item_name/item_code are
	immutable here (rename is a separate concern)."""
	doc = frappe.get_doc("Item", name)
	doc.check_permission("write")
	if isinstance(values, str):
		values = json.loads(values)
	for field in ITEM_SCALAR_FIELDS:
		if field in values:
			doc.set(field, values.get(field) or None)
	_apply_item_tax_fields(doc, values)
	doc.save()
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
	company = exportflow_company()
	item["default_supplier"] = frappe.db.get_value(
		"Item Default", {"parent": item_code, "company": company}, "default_supplier"
	) or frappe.db.get_value("Item Default", {"parent": item_code}, "default_supplier")
	return item


def _item_tax_templates(company: str | None) -> list[str]:
	"""Item Tax Templates for the company (the picker on the item form). Always
	company-scoped — like the sibling taxes_templates/accounts sources — so an
	unconfigured site yields an empty list, never another company's templates."""
	return frappe.get_all(
		"Item Tax Template", filters={"company": company}, pluck="name", order_by="name asc",
		limit_page_length=0,
	)


@frappe.whitelist()
def get_exchange_rate_to_company(currency: str) -> float:
	"""Selling exchange rate from the deal currency to the company currency
	(0 when unavailable — the form keeps the field manual)."""
	frappe.has_permission("Sales Order", "create", throw=True)
	company = exportflow_company()
	company_currency = frappe.db.get_value("Company", company, "default_currency")
	if not currency or currency == company_currency:
		return 1.0
	try:
		from erpnext.setup.utils import get_exchange_rate

		return flt(get_exchange_rate(currency, company_currency, args="for_selling"))
	except Exception:
		return 0.0


@frappe.whitelist()
def get_po_exchange_rate(currency: str) -> float:
	"""Buying exchange rate from the PO currency to the company currency (0 when
	unavailable — the form keeps the field manual). Foreign suppliers buy in
	their own currency; base amounts stay in INR via this rate."""
	frappe.has_permission("Purchase Order", "create", throw=True)
	company = exportflow_company()
	company_currency = frappe.db.get_value("Company", company, "default_currency")
	if not currency or currency == company_currency:
		return 1.0
	try:
		from erpnext.setup.utils import get_exchange_rate

		return flt(get_exchange_rate(currency, company_currency, args="for_buying"))
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

	company = exportflow_company()
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
			"tc_name": deal.get("tc_name") or None,
			"terms": deal.get("terms"),
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


# ---------------------------------------------------------------- edit / amend

# orders whose lifecycle can be Closed / Re-opened (ERPNext update_status)
CLOSEABLE_DOCTYPES = ("Sales Order", "Purchase Order")
AMENDABLE_DOCTYPES = ("Sales Order", "Purchase Order")


def _existing_amended_draft(doctype: str, name: str) -> str | None:
	"""An unsubmitted (docstatus=0) document already amended from `name` — the
	in-progress amend draft, if a previous amend cancelled the original but the
	editable-copy step was lost (e.g. a slow cancel + page refresh). Deterministic
	(newest first) so the same draft is always resumed even if more than one exists."""
	return frappe.db.get_value(
		doctype, {"amended_from": name, "docstatus": 0}, "name", order_by="creation desc"
	)


def _doc_can(doctype: str, name: str, *, amendable: bool = True, status: str | None = None) -> dict:
	"""Edit affordances the detail screens gate on — straight from the user's
	ERPNext role permissions. `amend` is offered only for a submitted doc the
	user may amend; `edit` means a draft the user may write. For closeable orders
	(SO/PO) `close`/`reopen` reflect the status (pass it in to skip a re-query)."""
	docstatus = cint(frappe.db.get_value(doctype, name, "docstatus"))
	can_write = bool(frappe.has_permission(doctype, "write", doc=name))
	out = {
		"docstatus": docstatus,
		"write": can_write,
		"edit": can_write and docstatus == 0,
		"submit": bool(frappe.has_permission(doctype, "submit", doc=name)),
		"cancel": bool(frappe.has_permission(doctype, "cancel", doc=name)),
		"amend": bool(
			amendable and docstatus == 1 and frappe.has_permission(doctype, "amend", doc=name)
		),
	}
	if doctype in CLOSEABLE_DOCTYPES:
		st = status if status is not None else frappe.db.get_value(doctype, name, "status")
		out["close"] = bool(can_write and docstatus == 1 and st not in ("Closed", "Cancelled"))
		out["reopen"] = bool(can_write and st == "Closed")
	# a Cancelled order with an in-progress amended draft the user may continue
	if doctype in AMENDABLE_DOCTYPES and docstatus == 2 and amendable:
		out["resume_amend"] = bool(
			frappe.has_permission(doctype, "amend", doc=name) and _existing_amended_draft(doctype, name)
		)
	return out


@frappe.whitelist()
def close_order(doctype: str, name: str) -> dict:
	"""Close a submitted Sales/Purchase Order — stops further billing/delivery
	without cancelling it (ERPNext update_status). Re-openable later."""
	if doctype not in CLOSEABLE_DOCTYPES:
		frappe.throw(_("{0} cannot be closed here").format(doctype))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")
	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted order can be closed"))
	if doc.status != "Closed":
		doc.update_status("Closed")
	return {"name": name, "status": frappe.db.get_value(doctype, name, "status")}


@frappe.whitelist()
def reopen_order(doctype: str, name: str) -> dict:
	"""Re-open a Closed Sales/Purchase Order. ERPNext's update_status('Draft') is
	the documented re-open sentinel — it recomputes the real lifecycle status."""
	if doctype not in CLOSEABLE_DOCTYPES:
		frappe.throw(_("{0} cannot be reopened here").format(doctype))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")
	if doc.status == "Closed":
		doc.update_status("Draft")
		# operator now owns the open state — drop goods-receipt Close-provenance so a
		# later receipt/return doesn't auto-re-close or re-open it from under them.
		if doctype == "Purchase Order" and doc.get("grn_auto_closed"):
			doc.db_set("grn_auto_closed", 0)
	return {"name": name, "status": frappe.db.get_value(doctype, name, "status")}


@frappe.whitelist()
def amend_document(doctype: str, name: str) -> dict:
	"""ERPNext-faithful, IDEMPOTENT amend: cancel the submitted document and reopen
	it as an editable draft (amended_from set). Safe to retry — if an amended draft
	already exists (a previous slow cancel committed but the draft step was lost on
	a refresh), return that draft instead of cancelling again. Raises a clear error
	when downstream links (PFIs, submitted POs, …) block the cancel."""
	if doctype not in AMENDABLE_DOCTYPES:
		frappe.throw(_("{0} cannot be amended here").format(doctype))
	frappe.has_permission(doctype, "amend", doc=name, throw=True)
	# serialize concurrent amends on the same original: a second caller then either
	# sees the first's draft (resume) or the original already Cancelled (guard),
	# instead of both racing to create a duplicate draft
	frappe.db.get_value(doctype, name, "name", for_update=True)
	# recovery / idempotency FIRST — a retry sees the original already Cancelled
	# (docstatus=2), so this must run before the docstatus==1 guard below
	existing = _existing_amended_draft(doctype, name)
	if existing:
		return {"name": existing, "doctype": doctype, "resumed": True}
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted document can be amended"))
	doc.cancel()
	amended = frappe.copy_doc(doc)
	amended.amended_from = name
	amended.docstatus = 0
	amended.insert()
	return {"name": amended.name, "doctype": doctype, "resumed": False}


@frappe.whitelist()
def get_amended_draft(doctype: str, name: str) -> dict:
	"""Any in-progress amended draft of `name` — lets the detail screen of a
	Cancelled order offer "Continue amendment"."""
	if doctype not in AMENDABLE_DOCTYPES:
		frappe.throw(_("{0} cannot be amended here").format(doctype))
	frappe.has_permission(doctype, "read", doc=name, throw=True)
	return {"name": _existing_amended_draft(doctype, name)}


@frappe.whitelist()
def get_sales_order_for_edit(name: str) -> dict:
	"""SO header + item lines in the deal-form shape, for the edit screen."""
	frappe.has_permission("Sales Order", "read", doc=name, throw=True)
	so = frappe.db.get_value(
		"Sales Order",
		name,
		[
			"name",
			"customer",
			"currency",
			"conversion_rate",
			"transaction_date",
			"delivery_date",
			"incoterm",
			"named_place",
			"payment_terms_narrative",
			"tc_name",
			"terms",
			"docstatus",
		],
		as_dict=True,
	)
	if not so:
		frappe.throw(_("Sales Order {0} not found").format(name))
	so["items"] = frappe.get_all(
		"Sales Order Item",
		filters={"parent": name, "parenttype": "Sales Order"},
		fields=["item_code", "item_name", "qty", "uom", "rate"],
		order_by="idx asc",
	)
	return so


@frappe.whitelist()
def update_sales_order(name: str, deal) -> dict:
	"""Edit a DRAFT sales order's header + item lines (submitted orders must be
	amended first). Mirrors create_export_sales_order's validation."""
	doc = frappe.get_doc("Sales Order", name)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft sales order can be edited — amend it first"))
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

	company_currency = frappe.db.get_value("Company", doc.company, "default_currency")
	currency = deal.get("currency") or company_currency
	conversion_rate = 1.0 if currency == company_currency else flt(deal.get("conversion_rate"))
	if conversion_rate <= 0:
		frappe.throw(_("Exchange rate must be greater than zero"))

	doc.customer = deal.get("customer") or doc.customer
	doc.transaction_date = deal.get("transaction_date") or doc.transaction_date
	doc.delivery_date = deal.get("delivery_date")
	doc.currency = currency
	doc.conversion_rate = conversion_rate
	doc.incoterm = deal.get("incoterm") or None
	doc.named_place = deal.get("named_place")
	doc.payment_terms_narrative = deal.get("payment_terms_narrative")
	doc.tc_name = deal.get("tc_name") or None
	doc.terms = deal.get("terms")
	doc.set(
		"items",
		[
			{"item_code": row["item_code"], "qty": flt(row["qty"]), "rate": flt(row["rate"])}
			for row in items
		],
	)
	doc.save()

	if frappe.utils.cint(deal.get("submit")):
		doc.check_permission("submit")
		doc.submit()
	return {"name": doc.name, "docstatus": doc.docstatus}


def _draft_po_qty(so_detail: str, exclude_po: str | None = None) -> float:
	"""Quantity already covered by DRAFT POs for an SO line (submitted POs are
	reflected in the SO item's ordered_qty by ERPNext itself). When editing a
	draft PO, exclude_po drops its own current contribution so the remaining
	check doesn't double-count the very PO being edited."""
	return flt(
		frappe.db.sql(
			"""SELECT COALESCE(SUM(poi.qty), 0)
			   FROM `tabPurchase Order Item` poi
			   JOIN `tabPurchase Order` po ON po.name = poi.parent
			   WHERE poi.sales_order_item = %s AND po.docstatus = 0
			     AND (%s IS NULL OR po.name != %s)""",
			(so_detail, exclude_po, exclude_po),
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
def get_so_procurement(sales_order: str, exclude_po: str | None = None) -> dict:
	"""Per-line procurement state for the SO screen: ordered (submitted),
	draft-covered, remaining, shipped/in-transit, and the POs per line.

	exclude_po drops that draft PO's own contribution from the draft/remaining
	figures — the PO edit form passes its own name so the live "remaining on SO"
	caption doesn't double-count the quantities already on the PO being edited."""
	frappe.has_permission("Sales Order", "read", doc=sales_order, throw=True)
	frappe.has_permission("Purchase Order", "read", throw=True)

	company = exportflow_company()
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
		line["draft_qty"] = flt(_draft_po_qty(line.so_detail, exclude_po), 3)
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
def get_new_po_context() -> dict:
	"""Everything the standalone PO form needs in one round trip."""
	frappe.has_permission("Purchase Order", "create", throw=True)
	company = exportflow_company()
	return {
		"company": company,
		"company_currency": frappe.db.get_value("Company", company, "default_currency"),
		"suppliers": frappe.get_all(
			"Supplier",
			filters={"disabled": 0},
			fields=["name", "supplier_name", "default_merchant_export_scheme", "default_currency", "country"],
			order_by="modified desc",
			limit_page_length=200,
		),
		"items": frappe.get_all(
			"Item",
			filters={"disabled": 0, "is_purchase_item": 1},
			fields=["name", "item_name", "stock_uom"],
			order_by="modified desc",
			limit_page_length=500,
		),
		"terms_templates": frappe.get_all(
			"Terms and Conditions",
			filters={"disabled": 0, "buying": 1},
			pluck="name",
			order_by="name asc",
			limit_page_length=100,
		),
		"taxes_templates": frappe.get_all(
			"Purchase Taxes and Charges Template",
			filters={"company": company, "disabled": 0},
			fields=["name", "is_default"],
			order_by="is_default desc, name asc",
			limit_page_length=100,
		),
		"accounts": frappe.get_all(
			"Account",
			filters={"company": company, "is_group": 0, "root_type": "Expense"},
			fields=["name", "account_name"],
			order_by="account_name asc",
			limit_page_length=500,
		),
		"sales_orders": frappe.get_all(
			"Sales Order",
			filters={"docstatus": 1, "status": ["!=", "Closed"]},
			fields=["name", "customer_name"],
			order_by="transaction_date desc",
			limit_page_length=100,
		),
		# option sources for the quick-create modals
		"uoms": frappe.get_all(
			"UOM", filters={"enabled": 1}, pluck="name", order_by="name asc", limit_page_length=300
		),
		"countries": frappe.get_all("Country", pluck="name", order_by="name asc", limit_page_length=300),
		"item_tax_templates": _item_tax_templates(company),
		"currencies": frappe.get_all(
			"Currency", filters={"enabled": 1}, pluck="name", order_by="name asc"
		),
	}


@frappe.whitelist()
def get_terms_text(template: str) -> str:
	frappe.has_permission("Terms and Conditions", "read", throw=True)
	return frappe.db.get_value("Terms and Conditions", template, "terms") or ""


def _supplier_is_foreign(supplier: str) -> bool:
	"""A supplier outside India (the import leg of a merchanting trade buys
	overseas). Country is authoritative; gst_category Overseas is the fallback
	(only checked where india_compliance has added that field)."""
	country = frappe.db.get_value("Supplier", supplier, "country")
	if country and country != "India":
		return True
	if frappe.get_meta("Supplier").has_field("gst_category"):
		return frappe.db.get_value("Supplier", supplier, "gst_category") == "Overseas"
	return False


def _default_charge_account(company: str, create_if_missing: bool = True) -> str | None:
	"""The expense account a cartage/freight charge posts to when the user does not
	pick one — feedback #11, where users enter only a charge name + amount. It is
	configurable via ExportFlow Settings.default_charge_account and falls back to the
	company's standard "Freight and Forwarding Charges" expense head, creating one
	under the company's expense group if somehow absent. Always a real, non-group
	Expense account (ERPNext rejects an Actual tax row otherwise); the caller guards
	against it colliding with the taxes template's GST heads.

	create_if_missing=False (the live preview, which must have NO side effects)
	returns None instead of inserting an account — the caller skips the charge row."""
	if not company:
		frappe.throw(_("No company is configured for ExportFlow — set it in ExportFlow Settings."))
	configured = frappe.db.get_single_value("ExportFlow Settings", "default_charge_account")
	if configured:
		acc = frappe.db.get_value(
			"Account", configured, ["company", "is_group", "root_type"], as_dict=True
		)
		if acc and acc.company == company and not acc.is_group and acc.root_type == "Expense":
			return configured
	existing = frappe.db.get_value(
		"Account",
		{
			"company": company,
			"is_group": 0,
			"root_type": "Expense",
			"account_name": "Freight and Forwarding Charges",
		},
		"name",
	)
	if existing:
		return existing
	if not create_if_missing:
		return None
	parent = frappe.db.get_value(
		"Account", {"company": company, "is_group": 1, "account_name": "Indirect Expenses"}, "name"
	) or frappe.db.get_value(
		"Account", {"company": company, "is_group": 1, "root_type": "Expense"}, "name"
	)
	if not parent:
		frappe.throw(
			_("No expense account is configured for charges — set a default in ExportFlow Settings.")
		)
	return (
		frappe.get_doc(
			{
				"doctype": "Account",
				"company": company,
				"parent_account": parent,
				"account_name": "Freight and Forwarding Charges",
				"root_type": "Expense",
				"account_type": "Expense Account",
				"is_group": 0,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _build_po_doc(
	podata,
	validate_remaining: bool = True,
	target=None,
	exclude_po: str | None = None,
	allow_account_create: bool = True,
):
	"""Construct the PO the standalone form describes: header, mixed
	SO-linked/free rows, taxes template rows, and extra charge heads. Shared by
	the live tax preview, the create, and (with target=an existing draft) the
	edit path. allow_account_create=False (preview) forbids the side effect of
	auto-creating a default charge account. exclude_po drops the edited PO's own draft contribution from the
	remaining-qty check so an in-place edit isn't rejected for double-counting."""
	items = podata.get("items") or []
	if not items:
		frappe.throw(_("Add at least one item"))
	if not podata.get("supplier"):
		frappe.throw(_("Supplier is required"))

	supplier = podata["supplier"]
	schedule_date = podata.get("schedule_date") or frappe.utils.add_days(frappe.utils.nowdate(), 15)

	linked_sos = sorted({row.get("sales_order") for row in items if row.get("sales_order")})
	for so_name in linked_sos:
		if validate_remaining:
			frappe.db.sql(
				"SELECT name FROM `tabSales Order Item` WHERE parent = %s FOR UPDATE", (so_name,)
			)
		if frappe.db.get_value("Sales Order", so_name, "docstatus") != 1:
			frappe.throw(_("Sales Order {0} must be submitted first").format(so_name))

	po_rows = []
	for idx, row in enumerate(items, start=1):
		if not row.get("item_code"):
			frappe.throw(_("Row {0}: item is required").format(idx))
		if flt(row.get("qty")) <= 0:
			frappe.throw(_("Row {0}: quantity must be greater than zero").format(idx))
		if flt(row.get("rate")) <= 0:
			frappe.throw(_("Row {0}: rate is required").format(idx))

		po_row = {
			"item_code": row["item_code"],
			"qty": flt(row["qty"]),
			"rate": flt(row["rate"]),
			"schedule_date": schedule_date,
			# per-line specification + packaging (feedback #13) — printed on the PO
			"specification": row.get("specification"),
			"packaging": row.get("packaging"),
		}
		if row.get("so_detail"):
			so_row = frappe.db.get_value(
				"Sales Order Item",
				row["so_detail"],
				["parent", "item_code", "qty", "ordered_qty", "conversion_factor"],
				as_dict=True,
			)
			if not so_row or so_row.parent != row.get("sales_order"):
				frappe.throw(_("Row {0}: line reference does not belong to {1}").format(idx, row.get("sales_order")))
			if so_row.item_code != row["item_code"]:
				frappe.throw(_("Row {0}: item does not match the sales order line").format(idx))
			if validate_remaining:
				ordered = flt(so_row.ordered_qty) / (flt(so_row.conversion_factor) or 1.0)
				remaining = flt(so_row.qty) - ordered - _draft_po_qty(row["so_detail"], exclude_po)
				if flt(row["qty"]) > remaining + 1e-6:
					frappe.throw(
						_("Row {0}: only {1} remains unordered on {2}").format(
							idx, flt(remaining, 3), row["sales_order"]
						)
					)
			po_row.update(
				{
					"sales_order": row["sales_order"],
					"sales_order_item": row["so_detail"],
					"delivered_by_supplier": 1,
				}
			)
		po_rows.append(po_row)

	company = exportflow_company()

	# taxes: template rows first, then freeform charge heads (cartage etc.)
	taxes = []
	taxes_template = podata.get("taxes_template")
	if taxes_template:
		from erpnext.controllers.accounts_controller import get_taxes_and_charges

		for tax in get_taxes_and_charges("Purchase Taxes and Charges Template", taxes_template) or []:
			taxes.append(tax)
	template_accounts = {t.get("account_head") for t in taxes}
	default_charge_account = None  # resolved lazily, once, only if a charge needs it
	for charge in podata.get("extra_charges") or []:
		amount = flt(charge.get("amount"))
		if amount <= 0:
			continue
		user_account = charge.get("account_head")
		account_head = user_account
		if not account_head:
			# users enter only a charge name + amount — the expense account is filled
			# in behind the scenes from the configured default (feedback #11)
			if default_charge_account is None:
				default_charge_account = _default_charge_account(
					company, create_if_missing=allow_account_create
				)
			account_head = default_charge_account
		if not account_head:
			# preview with no resolvable default (account creation suppressed) — skip
			# the row rather than persist an account during a side-effect-free preview
			continue
		if account_head in template_accounts:
			# the engine maps actual amounts item-wise by account head — a
			# percentage row sharing the account would silently compute zero
			if user_account:
				frappe.throw(
					_("Charge '{0}': pick an account that is not already used by the taxes template").format(
						charge.get("description") or account_head
					)
				)
			# the user can no longer pick an account — point the admin at the setting
			frappe.throw(
				_(
					"The default charge account is already used by the taxes template — choose a"
					" different 'Default expense account for PO charges' in ExportFlow Settings."
				)
			)
		taxes.append(
			{
				# purchase taxes need the category/add-deduct pair as well
				"category": "Total",
				"add_deduct_tax": "Add",
				"charge_type": "Actual",
				"account_head": account_head,
				"description": charge.get("description") or "Charges",
				"tax_amount": amount,
			}
		)

	# currency — buying can be in the supplier's currency (foreign suppliers),
	# base_rate (INR) is still derived via the rate so outlay/margin are unaffected
	company_currency = frappe.db.get_value("Company", company, "default_currency")
	currency = podata.get("currency") or company_currency
	conversion_rate = 1.0 if currency == company_currency else flt(podata.get("conversion_rate"))
	if conversion_rate <= 0:
		frappe.throw(_("Exchange rate must be greater than zero"))

	# third-country / merchanting purchase: the import leg must be overseas and
	# linked to the export sales order; the domestic 0.1% scheme can't apply, and
	# GST is naturally nil for an overseas supplier
	merchanting = bool(podata.get("merchanting_trade"))
	if merchanting:
		if not _supplier_is_foreign(supplier):
			frappe.throw(_("A merchanting (third-country) purchase needs an overseas supplier."))
		if not any(row.get("so_detail") for row in items):
			frappe.throw(
				_("A merchanting purchase must be linked to a sales order — pull its lines.")
			)

	header = {
		"supplier": supplier,
		"transaction_date": podata.get("transaction_date") or frappe.utils.nowdate(),
		"schedule_date": schedule_date,
		"currency": currency,
		"conversion_rate": conversion_rate,
		"merchant_export_scheme": 0 if merchanting else (1 if podata.get("merchant_export_scheme") else 0),
		"merchanting_trade": 1 if merchanting else 0,
		"taxes_and_charges": taxes_template or None,
		"tc_name": podata.get("tc_name") or None,
		"terms": podata.get("terms"),
	}
	if target is not None:
		# editing an existing draft — keep its name, replace header/lines/taxes
		target.update(header)
		target.set("items", po_rows)
		target.set("taxes", taxes)
		return target

	return frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"company": company,
			"items": po_rows,
			"taxes": taxes,
			**header,
		}
	)


def _book_po_taxes(po) -> None:
	"""india_compliance's GST templates carry NO static tax rows — set_missing_values
	is what adds the GST account-head row(s) (and each item's tax rate) based on the
	items' HSN and the place of supply. The create/edit paths must run it before
	saving so the booked PO carries the SAME tax the preview shows; without it the PO
	keeps the template name but an empty taxes table, so GST appears on entry and then
	vanishes after submit. The negotiated buying rate is preserved — set_missing_values
	must not re-fetch the day's exchange rate for a foreign-currency PO."""
	rate = flt(po.conversion_rate)
	po.run_method("set_missing_values")
	if rate > 0:
		po.conversion_rate = rate


def _po_item_tax_breakup(po) -> list[dict]:
	"""Per-item net + tax, from ERPNext's own itemised tax breakup — so the form
	shows how GST lands on each line as items are added (the dynamic per-item
	breakup), computed by the same engine that books the tax. get_itemised_tax is
	keyed by item code, so lines sharing an item collapse into one row."""
	from erpnext.controllers.taxes_and_totals import get_itemised_tax

	try:
		# a saved/reloaded PO has no runtime item_wise_tax_detail on its tax rows,
		# so get_itemised_tax would raise — recompute in memory (no save) first so
		# the per-item breakup is available on the detail view, not just the preview
		po.run_method("calculate_taxes_and_totals")
		itemised = get_itemised_tax(po)  # {item_code: {tax_desc: {tax_amount, ...}}}
	except Exception:
		itemised = {}
	rows: dict[str, dict] = {}
	order: list[str] = []
	for it in po.items:
		row = rows.get(it.item_code)
		if not row:
			row = {"item_code": it.item_code, "item_name": it.item_name, "net": 0.0, "tax": 0.0}
			rows[it.item_code] = row
			order.append(it.item_code)
		row["net"] += flt(it.net_amount or it.amount)
	for code, taxes in (itemised or {}).items():
		row = rows.get(code)
		if row:
			row["tax"] = flt(sum(flt(t.get("tax_amount")) for t in taxes.values()))
	return [{**rows[c], "net": flt(rows[c]["net"], 2), "tax": flt(rows[c]["tax"], 2)} for c in order]


def _po_totals(po) -> dict:
	return {
		"net_total": flt(po.net_total),
		"total_taxes_and_charges": flt(po.total_taxes_and_charges),
		"grand_total": flt(po.grand_total),
		"taxes": [
			{
				"description": tax.description,
				"rate": flt(tax.rate),
				"tax_amount": flt(tax.base_tax_amount_after_discount_amount or tax.tax_amount),
				"total": flt(tax.base_total or tax.total),
			}
			for tax in po.taxes
		],
		"by_item": _po_item_tax_breakup(po),
	}


@frappe.whitelist()
def preview_purchase_order(podata) -> dict:
	"""Compute taxes/totals for the form WITHOUT saving — runs the same
	ERPNext + india_compliance validation pipeline a real save would, so
	item/HSN GST autofills exactly like the desk."""
	frappe.has_permission("Purchase Order", "create", throw=True)
	if isinstance(podata, str):
		podata = json.loads(podata)

	# the preview must have NO side effects — never auto-create a charge account
	po = _build_po_doc(podata, validate_remaining=False, allow_account_create=False)
	# set_missing_values fetches each item's item_tax_rate (the per-item GST
	# override from its Item Tax Template) and supplier defaults; validate then
	# runs the full ERPNext + india_compliance pipeline (HSN GST autofill) — the
	# same order a real save uses, so the preview matches what gets booked
	try:
		po.run_method("set_missing_values")
		po.run_method("validate")
	except Exception:
		# a preview must not die on incomplete data — fall back to the math
		po.run_method("calculate_taxes_and_totals")
	return _po_totals(po)


@frappe.whitelist()
def create_purchase_order_draft(podata) -> dict:
	"""Standalone PO form: full header (dates, taxes, terms, scheme) plus a
	mix of SO-linked lines (drop-ship, validated against remaining qty) and
	free lines. Buying happens in the company currency."""
	frappe.has_permission("Purchase Order", "create", throw=True)
	if isinstance(podata, str):
		podata = json.loads(podata)

	po = _build_po_doc(podata, validate_remaining=True)
	supplier = po.supplier
	_book_po_taxes(po)  # populate india_compliance's GST rows so they persist on save
	po.insert()

	# stamp the negotiated supplier on the linked SO rows (drop-ship)
	for row in po.items:
		if row.sales_order_item:
			current = frappe.db.get_value(
				"Sales Order Item", row.sales_order_item, ["supplier", "delivered_by_supplier"], as_dict=True
			)
			if current.supplier != supplier or not current.delivered_by_supplier:
				frappe.db.set_value(
					"Sales Order Item",
					row.sales_order_item,
					{"supplier": supplier, "delivered_by_supplier": 1},
					update_modified=False,
				)

	if frappe.utils.cint(podata.get("submit")):
		frappe.has_permission("Purchase Order", "submit", throw=True)
		po.submit()

	return {"name": po.name, "docstatus": po.docstatus}


@frappe.whitelist()
def submit_purchase_order(name: str) -> dict:
	doc = frappe.get_doc("Purchase Order", name)
	doc.check_permission("submit")
	if doc.docstatus != 0:
		frappe.throw(_("Purchase Order {0} is not a draft").format(name))
	doc.submit()
	return {"name": doc.name, "docstatus": doc.docstatus}


@frappe.whitelist()
def update_purchase_order_doc(name: str, podata) -> dict:
	"""Edit a DRAFT purchase order (header + lines + taxes); submitted POs must
	be amended first. Re-runs the same builder as create, so item/HSN GST
	autofills exactly the same way."""
	doc = frappe.get_doc("Purchase Order", name)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft purchase order can be edited — amend it first"))
	if isinstance(podata, str):
		podata = json.loads(podata)

	# enforce the remaining-qty cap, but exclude this PO's own current draft
	# contribution so an in-place edit isn't rejected for double-counting itself
	_build_po_doc(podata, validate_remaining=True, target=doc, exclude_po=doc.name)
	_book_po_taxes(doc)  # re-populate india_compliance's GST rows so they persist
	doc.save()

	for row in doc.items:
		if row.sales_order_item:
			current = frappe.db.get_value(
				"Sales Order Item", row.sales_order_item, ["supplier", "delivered_by_supplier"], as_dict=True
			)
			if current.supplier != doc.supplier or not current.delivered_by_supplier:
				frappe.db.set_value(
					"Sales Order Item",
					row.sales_order_item,
					{"supplier": doc.supplier, "delivered_by_supplier": 1},
					update_modified=False,
				)

	if frappe.utils.cint(podata.get("submit")):
		doc.check_permission("submit")
		doc.submit()
	return {"name": doc.name, "docstatus": doc.docstatus}


@frappe.whitelist()
def get_purchase_orders() -> list[dict]:
	"""Purchases list rows with SO references and the GST clock."""
	frappe.has_permission("Purchase Order", "read", throw=True)
	company = exportflow_company()
	po_filters = {"docstatus": ["<", 2]}
	if company:
		po_filters["company"] = company
	# get_list (unlike get_all) applies the caller's role/user permissions
	pos = frappe.get_list(
		"Purchase Order",
		filters=po_filters,
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
	received_pos = set(
		frappe.get_all(
			"Goods Receipt Note", filters={"status": "Received"}, pluck="purchase_order", distinct=True
		)
	)
	for po in pos:
		po["sales_orders"] = frappe.get_all(
			"Purchase Order Item",
			filters={"parent": po.name, "sales_order": ["is", "set"]},
			pluck="sales_order",
			distinct=True,
		)
		po["has_grn"] = po.name in received_pos
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
			"specification": row.get("specification"),
			"packaging": row.get("packaging"),
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
	# reconstruct the freeform charge heads (Actual rows that are not part of
	# the taxes template) so the edit form can round-trip them
	template_accounts = set()
	if po.taxes_and_charges:
		from erpnext.controllers.accounts_controller import get_taxes_and_charges

		template_accounts = {
			t.get("account_head")
			for t in (get_taxes_and_charges("Purchase Taxes and Charges Template", po.taxes_and_charges) or [])
		}
	extra_charges = [
		{"description": t.description, "account_head": t.account_head, "amount": flt(t.tax_amount)}
		for t in po.taxes
		if t.charge_type == "Actual" and t.account_head not in template_accounts
	]
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
			"conversion_rate": po.conversion_rate,
			"grand_total": po.grand_total,
			"merchant_export_scheme": po.merchant_export_scheme,
			"merchanting_trade": po.get("merchanting_trade"),
			"supplier_invoice_no": po.supplier_invoice_no,
			"supplier_invoice_date": po.supplier_invoice_date,
			"gst_export_deadline": po.gst_export_deadline,
			"taxes_and_charges": po.taxes_and_charges,
			"tc_name": po.tc_name,
			"terms": po.terms,
		},
		"totals": _po_totals(po),
		"items": items,
		"extra_charges": extra_charges,
		"shipments": shipments,
		"grns": frappe.get_all(
			"Goods Receipt Note",
			filters={"purchase_order": name},
			fields=["name", "warehouse", "status", "posting_date", "supplier_invoice_no"],
			order_by="creation asc",
		),
		"received": _po_grn_summary(name)["fully_received"],
		"can": _doc_can("Purchase Order", name, status=po.status),
	}


# --- generic multi-file attachments (SO / PO supporting docs, feedback #17) ------

_ATTACHABLE_DOCTYPES = ("Sales Order", "Purchase Order")


@frappe.whitelist()
def list_doc_attachments(doctype: str, name: str) -> list[dict]:
	"""Files attached to a Sales/Purchase Order — backs the multi-file 'Attachments'
	card. Read-gated on the parent document."""
	if doctype not in _ATTACHABLE_DOCTYPES:
		frappe.throw(_("{0} does not support attachments here").format(doctype))
	frappe.has_permission(doctype, "read", doc=name, throw=True)
	return frappe.get_all(
		"File",
		filters={"attached_to_doctype": doctype, "attached_to_name": name},
		fields=["name", "file_name", "file_url", "is_private", "file_size", "creation"],
		order_by="creation desc",
	)


@frappe.whitelist()
def remove_doc_attachment(doctype: str, name: str, file_url: str) -> dict:
	"""Delete a file attached to a Sales/Purchase Order. Write-gated on the parent;
	only removes a File that is actually attached to that document."""
	if doctype not in _ATTACHABLE_DOCTYPES:
		frappe.throw(_("{0} does not support attachments here").format(doctype))
	# orders are usually submitted (docstatus=1, not writable), but their files must
	# stay manageable — so gate removal on being an editor of the doctype (the same
	# capability that lets a user attach), plus read on this specific document
	frappe.has_permission(doctype, "read", doc=name, throw=True)
	if not frappe.has_permission(doctype, "write"):
		frappe.throw(
			_("You do not have permission to manage attachments on {0}").format(doctype),
			frappe.PermissionError,
		)
	file_name = frappe.db.get_value(
		"File",
		{"attached_to_doctype": doctype, "attached_to_name": name, "file_url": file_url},
		"name",
	)
	if not file_name:
		frappe.throw(_("That file is not attached to {0}").format(name))
	frappe.delete_doc("File", file_name, ignore_permissions=True)
	return {"ok": True}


# --- Goods Receipt Note (receive PO goods into a warehouse; quantity stock-in) --


def _po_grn_summary(po_name: str) -> dict:
	"""NET received quantity per PO line — RECEIVED Goods Receipt Notes minus
	RETURNED Material Returns — and whether the PO is fully received. A return
	reopens the returned quantity as remaining, so it can be re-received."""
	rows = frappe.db.sql(
		"""SELECT gi.po_detail AS po_detail, SUM(gi.received_qty) AS qty
		   FROM `tabGoods Receipt Note Item` gi
		   JOIN `tabGoods Receipt Note` g ON g.name = gi.parent
		   WHERE g.purchase_order = %s AND g.status = 'Received'
		   GROUP BY gi.po_detail""",
		(po_name,),
		as_dict=True,
	)
	received = {r.po_detail: flt(r.qty) for r in rows if r.po_detail}
	returns = frappe.db.sql(
		"""SELECT ri.po_detail AS po_detail, SUM(ri.returned_qty) AS qty
		   FROM `tabMaterial Return Item` ri
		   JOIN `tabMaterial Return` r ON r.name = ri.parent
		   WHERE r.purchase_order = %s AND r.status = 'Returned'
		   GROUP BY ri.po_detail""",
		(po_name,),
		as_dict=True,
	)
	for r in returns:
		if r.po_detail and r.po_detail in received:
			received[r.po_detail] = flt(received[r.po_detail]) - flt(r.qty)
	po_lines = frappe.get_all("Purchase Order Item", filters={"parent": po_name}, fields=["name", "qty"])
	fully = bool(po_lines) and all(received.get(l.name, 0) + 1e-6 >= flt(l.qty) for l in po_lines)
	return {"received_by_line": received, "fully_received": fully, "has_grn": bool(rows)}


def _grn_warehouses(company: str | None) -> list[dict]:
	"""MN Globex warehouses for the GRN picklist — port-type warehouses first."""
	filters = {"is_group": 0, "disabled": 0}
	if company:
		filters["company"] = company
	whs = frappe.get_all(
		"Warehouse", filters=filters, fields=["name", "warehouse_name", "warehouse_type"]
	)
	whs.sort(key=lambda w: (w.get("warehouse_type") != "Port", w["name"]))
	return whs


@frappe.whitelist()
def get_receivable_pos() -> list[dict]:
	"""Submitted, non-merchanting purchase orders that still have goods to receive
	(not fully covered by Received GRNs) — lets a GRN be started straight from the
	Goods receipts screen by picking a supplier and one of their open POs."""
	frappe.has_permission("Purchase Order", "read", throw=True)
	frappe.has_permission("Goods Receipt Note", "create", throw=True)
	company = exportflow_company()
	filters = {"docstatus": 1}
	if company:
		filters["company"] = company
	out = []
	for po in frappe.get_all(
		"Purchase Order",
		filters=filters,
		fields=[
			"name",
			"supplier",
			"supplier_name",
			"transaction_date",
			"grand_total",
			"currency",
			"merchanting_trade",
		],
		order_by="transaction_date desc, creation desc",
		limit_page_length=200,
	):
		if po.get("merchanting_trade"):
			continue  # merchanting goods never enter India → no GRN
		summary = _po_grn_summary(po.name)
		if summary["fully_received"]:
			continue
		rec = summary["received_by_line"]
		lines = frappe.get_all("Purchase Order Item", filters={"parent": po.name}, fields=["name", "qty"])
		po["remaining_lines"] = sum(1 for l in lines if flt(rec.get(l.name, 0)) + 1e-6 < flt(l.qty))
		po.pop("merchanting_trade", None)
		out.append(po)
	return out


@frappe.whitelist()
def get_grn_context(purchase_order: str) -> dict:
	"""Everything the GRN create form needs: PO lines with ordered vs already-
	received quantity, and the warehouse picklist."""
	frappe.has_permission("Purchase Order", "read", doc=purchase_order, throw=True)
	frappe.has_permission("Goods Receipt Note", "create", throw=True)
	po = frappe.db.get_value(
		"Purchase Order",
		purchase_order,
		["name", "supplier", "supplier_name", "docstatus", "merchanting_trade", "company"],
		as_dict=True,
	)
	if not po:
		frappe.throw(_("Purchase Order {0} not found").format(purchase_order))
	if po.docstatus != 1:
		frappe.throw(_("Purchase Order {0} is not submitted").format(purchase_order))
	if po.merchanting_trade:
		frappe.throw(
			_("{0} is a merchanting purchase — its goods never enter India, so no Goods Receipt Note applies.").format(
				purchase_order
			)
		)
	summary = _po_grn_summary(purchase_order)
	lines = []
	for r in frappe.get_all(
		"Purchase Order Item",
		filters={"parent": purchase_order},
		fields=["name", "item_code", "item_name", "qty", "uom", "stock_uom", "conversion_factor"],
		order_by="idx asc",
	):
		already = flt(summary["received_by_line"].get(r.name, 0))
		lines.append(
			{
				"po_detail": r.name,
				"item_code": r.item_code,
				"item_name": r.item_name,
				"ordered_qty": flt(r.qty),
				"already_received": already,
				"received_qty": flt(flt(r.qty) - already, 3),  # default to the remaining qty
				"uom": r.uom,
				"stock_uom": r.stock_uom,
				"conversion_factor": flt(r.conversion_factor) or 1,
			}
		)
	return {
		"purchase_order": po.name,
		"supplier": po.supplier,
		"supplier_name": po.supplier_name,
		"company": po.company,
		"warehouses": _grn_warehouses(po.company),
		"lines": lines,
		"fully_received": summary["fully_received"],
	}


def _grn_item_rows(items) -> list[dict]:
	out = []
	for r in items or []:
		if not r.get("item_code") or flt(r.get("received_qty")) <= 0:
			continue
		out.append(
			{
				"item_code": r.get("item_code"),
				"item_name": r.get("item_name"),
				"po_detail": r.get("po_detail") or None,
				"ordered_qty": flt(r.get("ordered_qty")),
				"received_qty": flt(r.get("received_qty")),
				"uom": r.get("uom"),
				"stock_uom": r.get("stock_uom"),
				"conversion_factor": flt(r.get("conversion_factor")) or 1,
			}
		)
	return out


def _grn_doc_rows(documents) -> list[dict]:
	"""Normalise supplier-document rows (document_type + uploaded file)."""
	out = []
	for d in documents or []:
		if not (d.get("document_type") and d.get("file")):
			continue
		out.append(
			{
				"document_type": d.get("document_type"),
				"file": d.get("file"),
				"description": d.get("description"),
			}
		)
	return out


@frappe.whitelist()
def get_supplier_document_types() -> list[dict]:
	"""Tracked document types a supplier provides with the goods (CoA, MSDS, …) —
	for the GRN document picker. These map 1:1 to the shipment's checklist slots."""
	frappe.has_permission("Document Type", "read", throw=True)
	return frappe.get_all(
		"Document Type",
		filters={"origin": "Tracked", "responsible_party": "Supplier"},
		fields=["name", "category"],
		order_by="category, name",
	)


@frappe.whitelist()
def create_grn(payload) -> dict:
	frappe.has_permission("Goods Receipt Note", "create", throw=True)
	if isinstance(payload, str):
		payload = json.loads(payload)
	if not payload.get("purchase_order"):
		frappe.throw(_("Pick a Purchase Order"))
	if not payload.get("warehouse"):
		frappe.throw(_("Pick a receiving warehouse"))
	items = _grn_item_rows(payload.get("items"))
	if not items:
		frappe.throw(_("Enter a received quantity for at least one line"))
	doc = frappe.get_doc(
		{
			"doctype": "Goods Receipt Note",
			"purchase_order": payload.get("purchase_order"),
			"warehouse": payload.get("warehouse"),
			"posting_date": payload.get("posting_date") or nowdate(),
			"supplier_invoice_no": payload.get("supplier_invoice_no"),
			"supplier_invoice_date": payload.get("supplier_invoice_date") or None,
			"supplier_invoice_file": payload.get("supplier_invoice_file") or None,
			"remarks": payload.get("remarks"),
			"status": "Draft",
			"items": items,
			"packs": _pack_rows(payload.get("packs")),
			"documents": _grn_doc_rows(payload.get("documents")),
		}
	)
	doc.insert()
	return {"name": doc.name}


@frappe.whitelist()
def update_grn(name: str, payload) -> dict:
	doc = frappe.get_doc("Goods Receipt Note", name)
	doc.check_permission("write")
	if doc.status != "Draft":
		frappe.throw(_("Only a draft Goods Receipt Note can be edited"))
	if isinstance(payload, str):
		payload = json.loads(payload)
	if payload.get("warehouse"):
		doc.warehouse = payload.get("warehouse")
	if payload.get("posting_date"):
		doc.posting_date = payload.get("posting_date")
	doc.supplier_invoice_no = payload.get("supplier_invoice_no")
	doc.supplier_invoice_date = payload.get("supplier_invoice_date") or None
	if "supplier_invoice_file" in payload:
		doc.supplier_invoice_file = payload.get("supplier_invoice_file") or None
	doc.remarks = payload.get("remarks")
	if payload.get("items") is not None:
		doc.set("items", _grn_item_rows(payload.get("items")))
	if payload.get("packs") is not None:
		doc.set("packs", _pack_rows(payload.get("packs")))
	doc.save()
	return {"name": doc.name}


def _grn_writeback_invoice(grn) -> None:
	"""Copy the supplier invoice no/date onto the PO — the PO stays the system of
	record for the 90-day GST export clock (its on_update_after_submit recomputes
	gst_export_deadline and rebuilds the shipment checklist). Best-effort; never
	blocks the receipt."""
	if not (grn.supplier_invoice_no or grn.supplier_invoice_date):
		return
	try:
		po = frappe.get_doc("Purchase Order", grn.purchase_order)
		changed = False
		if grn.supplier_invoice_no and po.supplier_invoice_no != grn.supplier_invoice_no:
			po.supplier_invoice_no = grn.supplier_invoice_no
			changed = True
		if grn.supplier_invoice_date and str(po.supplier_invoice_date or "") != str(
			grn.supplier_invoice_date
		):
			po.supplier_invoice_date = grn.supplier_invoice_date
			changed = True
		if changed:
			po.save()  # fires on_update_after_submit → GST deadline + checklist rebuild
	except Exception:
		frappe.log_error(
			title=f"GRN invoice write-back failed: {grn.name}", message=frappe.get_traceback()
		)


def _grn_sync_po_status(po_name: str, was_full: bool = False) -> None:
	"""Reflect goods-receipt completeness in the linked Purchase Order's lifecycle
	status: Close the PO once every line is fully received (net of returns), and
	re-open a PO that goods-receipt itself Closed when a later cancellation, return or
	deletion drops the net below the ordered quantity. Best-effort — a status-sync
	failure must never block the receipt/return action.

	Two guards keep this from fighting an operator's deliberate decisions:
	- CLOSE only on the not-full→full transition (`was_full` is the PO's fully-received
	  state from BEFORE this action) — so a PO an operator re-opened by hand is not
	  slammed shut again by an unrelated within-tolerance receipt.
	- RE-OPEN only a PO WE Closed, tracked by the `grn_auto_closed` provenance flag
	  (cleared by reopen_order) — never undoing a Close an operator made by hand.

	A Delivered PO (drop-ship, flipped to Delivered at ship time) and an On-Hold PO are
	left as-is; merchanting POs never receive. This runs as a system side-effect of an
	already write-permission-checked receipt/return — like the ship-time Delivered flip
	— so it does not separately check Purchase Order write permission."""
	try:
		po = frappe.get_doc("Purchase Order", po_name)
		if po.docstatus != 1 or po.get("merchanting_trade"):
			return
		full = _po_grn_summary(po_name)["fully_received"]
		if full and not was_full and po.status not in ("Closed", "Cancelled", "Delivered", "On Hold"):
			po.update_status("Closed")
			po.db_set("grn_auto_closed", 1)  # provenance: this Close is goods-receipt-driven
		elif not full and po.status == "Closed" and po.get("grn_auto_closed"):
			po.db_set("grn_auto_closed", 0)
			po.update_status("Draft")  # documented re-open sentinel; recomputes the real status
	except Exception:
		frappe.log_error(
			title=f"GRN PO-status sync failed: {po_name}", message=frappe.get_traceback()
		)


def _grn_assert_single_warehouse(doc) -> None:
	"""One purchase order is received into ONE warehouse — keeps the shipment's
	per-line warehouse resolution unambiguous (it picks the PO's Received GRN). A
	second receipt for the same PO into a different warehouse is refused; use the
	same warehouse, or a separate PO."""
	other = frappe.db.get_value(
		"Goods Receipt Note",
		{
			"purchase_order": doc.purchase_order,
			"status": "Received",
			"warehouse": ["!=", doc.warehouse],
			"name": ["!=", doc.name],
		},
		["name", "warehouse"],
		as_dict=True,
	)
	if other:
		frappe.throw(
			_(
				"{0} already received goods for {1} into {2}. Receive into the same warehouse, or raise a separate purchase order."
			).format(other.name, doc.purchase_order, other.warehouse)
		)


def _grn_over_receipt_tolerance() -> float:
	"""Over-receipt tolerance % from ExportFlow Settings. The docfield default (5) is
	NOT back-filled into an already-saved Single, so read the raw Singles row to tell
	'never configured' (→ default 5) from a deliberate value — including a deliberate 0,
	which means 'block any over-receipt' per the field's own help text."""
	rows = frappe.db.sql(
		"SELECT `value` FROM `tabSingles` WHERE doctype=%s AND field=%s",
		("ExportFlow Settings", "grn_over_receipt_tolerance_pct"),
	)
	raw = rows[0][0] if rows else None
	return flt(raw) if raw not in (None, "") else 5.0


def _grn_assert_within_ordered(doc) -> None:
	"""Cumulative NET received quantity (this GRN + other Received GRNs − returns) may
	not exceed each PO line's ordered quantity beyond the over-receipt tolerance
	(ExportFlow Settings.grn_over_receipt_tolerance_pct — default 5% for weighing
	variance; 0 blocks any over-receipt). Reports every over-receiving line at once,
	and the cap shown is the cap enforced (both rounded to 3 dp)."""
	tol = _grn_over_receipt_tolerance()
	ordered = {
		r.name: flt(r.qty)
		for r in frappe.get_all(
			"Purchase Order Item", filters={"parent": doc.purchase_order}, fields=["name", "qty"]
		)
	}
	already = _po_grn_summary(doc.purchase_order)["received_by_line"]  # net of other GRNs/returns
	by_line: dict = {}
	for r in doc.items:
		if r.po_detail:
			by_line[r.po_detail] = by_line.get(r.po_detail, 0.0) + flt(r.received_qty)
	violations = []
	for po_detail, qty in by_line.items():
		ord_qty = flt(ordered.get(po_detail, 0))
		cap = flt(ord_qty * (1 + tol / 100.0), 3)  # round once so display == enforced
		cumulative = flt(already.get(po_detail, 0)) + qty
		if cumulative > cap + 1e-6:
			item = next((r.item_code for r in doc.items if r.po_detail == po_detail), po_detail)
			violations.append(
				_("{0}: received total {1} exceeds the maximum {2} ({3} ordered + {4}% tolerance).").format(
					item, flt(cumulative, 3), cap, flt(ord_qty, 3), "%g" % tol
				)
			)
	if violations:
		frappe.throw("<br>".join(violations), title=_("Over-receipt"))


@frappe.whitelist()
def submit_grn(name: str) -> dict:
	"""Receive the goods: post quantity stock-IN at the warehouse (only when the
	stock regime is on), copy the supplier invoice to the PO, and mark the GRN
	Received. Idempotent."""
	from exportflow import stock

	doc = frappe.get_doc("Goods Receipt Note", name)
	doc.check_permission("write")
	if doc.status == "Received":
		return {"name": name, "status": "Received"}
	if doc.status != "Draft":
		frappe.throw(_("Only a draft Goods Receipt Note can be received"))
	if not doc.items:
		frappe.throw(_("Nothing to receive"))
	frappe.db.get_value("Purchase Order", doc.purchase_order, "name", for_update=True)  # serialize PO-status sync
	_grn_assert_single_warehouse(doc)
	_grn_assert_within_ordered(doc)
	was_full = _po_grn_summary(doc.purchase_order)["fully_received"]  # state before this receipt counts
	if stock.maintain_stock_enabled():
		# stock-IN in the line's transaction UOM — the shipment posts OUT in the
		# same unit (Export Shipment Item.qty), so the ledger nets to zero once the
		# received goods ship. conversion_factor is captured for reference only.
		rows = [(r.item_code, doc.warehouse, flt(r.received_qty)) for r in doc.items]
		stock.post_in(rows, stock.GRN_VOUCHER, doc.name, company=doc.company)
	doc.db_set("status", "Received")
	_grn_writeback_invoice(doc)
	_grn_sync_po_status(doc.purchase_order, was_full=was_full)  # this receipt completed it → Close
	return {"name": name, "status": "Received"}


@frappe.whitelist()
def cancel_grn(name: str) -> dict:
	"""Reverse the receipt: undo the stock-IN and mark the GRN Cancelled. Refuses
	when a shipment has already shipped these goods out (reversing the stock-IN
	would leave a dangling negative balance)."""
	from exportflow import stock

	doc = frappe.get_doc("Goods Receipt Note", name)
	doc.check_permission("write")
	if doc.status == "Cancelled":
		return {"name": name, "status": "Cancelled"}
	frappe.db.get_value("Purchase Order", doc.purchase_order, "name", for_update=True)  # serialize PO-status sync
	doc.assert_not_consumed()
	stock.reverse(stock.GRN_VOUCHER, doc.name)
	doc.db_set("status", "Cancelled")
	_grn_sync_po_status(doc.purchase_order)  # dropped below full → re-open if we Closed it
	return {"name": name, "status": "Cancelled"}


@frappe.whitelist()
def attach_grn_invoice(name: str, file_url: str) -> dict:
	"""Stamp an uploaded supplier-invoice file onto the GRN (mirrors
	attach_document_file for Document Instance)."""
	doc = frappe.get_doc("Goods Receipt Note", name)
	doc.check_permission("write")
	if not frappe.db.exists(
		"File",
		{"file_url": file_url, "attached_to_doctype": "Goods Receipt Note", "attached_to_name": name},
	):
		frappe.throw(_("That file is not attached to {0}").format(name))
	doc.db_set({"supplier_invoice_file": file_url})
	return {"supplier_invoice_file": file_url}


@frappe.whitelist()
def get_grns() -> list[dict]:
	frappe.has_permission("Goods Receipt Note", "read", throw=True)
	company = exportflow_company()
	filters = {"company": company} if company else {}
	return frappe.get_list(
		"Goods Receipt Note",
		filters=filters,
		fields=[
			"name",
			"purchase_order",
			"supplier_name",
			"warehouse",
			"status",
			"posting_date",
			"supplier_invoice_no",
		],
		order_by="posting_date desc, creation desc",
		limit_page_length=100,
	)


@frappe.whitelist()
def get_grn_detail(name: str) -> dict:
	frappe.has_permission("Goods Receipt Note", "read", doc=name, throw=True)
	doc = frappe.get_doc("Goods Receipt Note", name)
	can_write = bool(frappe.has_permission("Goods Receipt Note", "write", doc=name))
	return {
		"grn": {
			"name": doc.name,
			"purchase_order": doc.purchase_order,
			"supplier": doc.supplier,
			"supplier_name": doc.supplier_name,
			"company": doc.company,
			"posting_date": doc.posting_date,
			"warehouse": doc.warehouse,
			"status": doc.status,
			"supplier_invoice_no": doc.supplier_invoice_no,
			"supplier_invoice_date": doc.supplier_invoice_date,
			"supplier_invoice_file": doc.supplier_invoice_file,
			"remarks": doc.remarks,
		},
		"items": [
			{
				"name": r.name,
				"item_code": r.item_code,
				"item_name": r.item_name,
				"po_detail": r.po_detail,
				"ordered_qty": r.ordered_qty,
				"received_qty": r.received_qty,
				"uom": r.uom,
			}
			for r in doc.items
		],
		"packs": [
			{
				"name": p.name,
				"item_code": p.item_code,
				"batch_no": p.batch_no,
				"marks": p.marks,
				"num_packages": p.num_packages,
				"pack_type": p.pack_type,
				"net_per": p.net_per,
				"tare_per": p.tare_per,
				"mfg_date": p.mfg_date,
				"exp_date": p.exp_date,
			}
			for p in doc.packs
		],
		"documents": [
			{
				"name": d.name,
				"document_type": d.document_type,
				"file": d.file,
				"description": d.description,
			}
			for d in doc.documents
		],
		"returns": frappe.get_all(
			"Material Return",
			filters={"goods_receipt_note": name},
			fields=["name", "status", "posting_date"],
			order_by="creation asc",
		),
		"can": {
			"edit": can_write and doc.status == "Draft",
			"receive": can_write and doc.status == "Draft",
			"cancel": can_write and doc.status == "Received",
			"return_material": can_write and doc.status == "Received",
		},
	}


@frappe.whitelist()
def add_grn_document(
	name: str, document_type: str, file_url: str, description: str | None = None
) -> dict:
	"""Attach a supplier-provided document (already uploaded to this GRN) as a typed
	row — CoA, MSDS, test certs, etc. The Document Type maps it to the shipment's
	checklist, so the file forwards to the shipment without a second upload."""
	doc = frappe.get_doc("Goods Receipt Note", name)
	doc.check_permission("write")
	if not (document_type or "").strip():
		frappe.throw(_("Pick a document type (e.g. Certificate of Analysis)"))
	if not frappe.db.exists(
		"File",
		{"file_url": file_url, "attached_to_doctype": "Goods Receipt Note", "attached_to_name": name},
	):
		frappe.throw(_("That file is not attached to {0}").format(name))
	doc.append("documents", {"document_type": document_type, "file": file_url, "description": description})
	doc.save()
	return {"name": name}


@frappe.whitelist()
def remove_grn_document(name: str, row: str) -> dict:
	"""Remove a supplier-document row from a GRN."""
	doc = frappe.get_doc("Goods Receipt Note", name)
	doc.check_permission("write")
	doc.set("documents", [d for d in doc.documents if d.name != row])
	doc.save()
	return {"name": name}


@frappe.whitelist()
def sync_grn_documents(shipment: str) -> dict:
	"""Pull supplier documents from the goods receipts into this shipment's checklist
	— fills each matching, still-empty Tracked document with the GRN's file (no
	re-upload). Runs automatically on save too; this is the manual re-sync."""
	frappe.has_permission("Export Shipment", "write", doc=shipment, throw=True)
	from exportflow.checklist import _forward_grn_documents

	count = _forward_grn_documents(frappe.get_doc("Export Shipment", shipment))
	return {"attached": count}


# --- Material Return (send received goods back to the supplier) -----------------


def _returned_for_grn_item(grn_detail: str, exclude: str | None = None) -> float:
	"""Quantity already returned against a GRN line (across Returned Material
	Returns), optionally excluding one return."""
	if not grn_detail:
		return 0.0
	cond = "AND r.name != %(ex)s" if exclude else ""
	res = frappe.db.sql(
		f"""SELECT SUM(ri.returned_qty)
		    FROM `tabMaterial Return Item` ri
		    JOIN `tabMaterial Return` r ON r.name = ri.parent
		    WHERE ri.grn_detail = %(g)s AND r.status = 'Returned' {cond}""",
		{"g": grn_detail, "ex": exclude},
	)
	return flt(res[0][0]) if res and res[0][0] else 0.0


@frappe.whitelist()
def get_return_context(goods_receipt_note: str) -> dict:
	"""Lines of a Received GRN that can still be returned (received − already
	returned), for raising a Material Return."""
	frappe.has_permission("Goods Receipt Note", "read", doc=goods_receipt_note, throw=True)
	frappe.has_permission("Material Return", "create", throw=True)
	grn = frappe.db.get_value(
		"Goods Receipt Note",
		goods_receipt_note,
		["name", "purchase_order", "supplier_name", "warehouse", "status"],
		as_dict=True,
	)
	if not grn:
		frappe.throw(_("Goods Receipt Note {0} not found").format(goods_receipt_note))
	if grn.status != "Received":
		frappe.throw(_("Only a received Goods Receipt Note can be returned"))
	lines = []
	for it in frappe.get_all(
		"Goods Receipt Note Item",
		filters={"parent": goods_receipt_note},
		fields=["name", "item_code", "item_name", "po_detail", "received_qty", "uom"],
		order_by="idx asc",
	):
		already = _returned_for_grn_item(it.name)
		returnable = flt(flt(it.received_qty) - already, 3)
		if returnable <= 1e-6:
			continue
		lines.append(
			{
				"item_code": it.item_code,
				"item_name": it.item_name,
				"po_detail": it.po_detail,
				"grn_detail": it.name,
				"received_qty": flt(it.received_qty),
				"already_returned": already,
				"returnable": returnable,
				"returned_qty": returnable,  # default to all that's returnable
				"uom": it.uom,
			}
		)
	return {
		"goods_receipt_note": grn.name,
		"purchase_order": grn.purchase_order,
		"supplier_name": grn.supplier_name,
		"warehouse": grn.warehouse,
		"lines": lines,
	}


def _return_item_rows(items) -> list[dict]:
	out = []
	for r in items or []:
		if not r.get("item_code") or flt(r.get("returned_qty")) <= 0:
			continue
		out.append(
			{
				"item_code": r.get("item_code"),
				"item_name": r.get("item_name"),
				"po_detail": r.get("po_detail") or None,
				"grn_detail": r.get("grn_detail") or None,
				"received_qty": flt(r.get("received_qty")),
				"returned_qty": flt(r.get("returned_qty")),
				"uom": r.get("uom"),
			}
		)
	return out


@frappe.whitelist()
def create_return(payload) -> dict:
	frappe.has_permission("Material Return", "create", throw=True)
	if isinstance(payload, str):
		payload = json.loads(payload)
	if not payload.get("goods_receipt_note"):
		frappe.throw(_("Pick the goods receipt to return against"))
	items = _return_item_rows(payload.get("items"))
	if not items:
		frappe.throw(_("Enter a quantity to return for at least one line"))
	doc = frappe.get_doc(
		{
			"doctype": "Material Return",
			"goods_receipt_note": payload.get("goods_receipt_note"),
			"posting_date": payload.get("posting_date") or nowdate(),
			"reason": payload.get("reason"),
			"status": "Draft",
			"items": items,
		}
	)
	doc.insert()
	return {"name": doc.name}


@frappe.whitelist()
def update_return(name: str, payload) -> dict:
	doc = frappe.get_doc("Material Return", name)
	doc.check_permission("write")
	if doc.status != "Draft":
		frappe.throw(_("Only a draft Material Return can be edited"))
	if isinstance(payload, str):
		payload = json.loads(payload)
	if payload.get("posting_date"):
		doc.posting_date = payload.get("posting_date")
	doc.reason = payload.get("reason")
	if payload.get("items") is not None:
		doc.set("items", _return_item_rows(payload.get("items")))
	doc.save()
	return {"name": doc.name}


def _return_assert_returnable(doc) -> None:
	"""A line may not return more than was received on its GRN line (net of other
	returns)."""
	for r in doc.items:
		if not r.grn_detail:
			continue
		recv = flt(frappe.db.get_value("Goods Receipt Note Item", r.grn_detail, "received_qty"))
		already = _returned_for_grn_item(r.grn_detail, exclude=doc.name)
		if flt(r.returned_qty) - (recv - already) > 1e-6:
			frappe.throw(
				_("Cannot return {0} of {1} — only {2} was received and not yet returned.").format(
					flt(r.returned_qty), r.item_code, flt(recv - already)
				)
			)


@frappe.whitelist()
def submit_return(name: str) -> dict:
	"""Confirm the return: post the goods OUT of the warehouse (only when the stock
	regime is on) and mark it Returned — the PO's net received drops, reopening the
	returned quantity as remaining. The stock-out refuses to go negative, so goods
	already shipped cannot be returned. Idempotent."""
	from exportflow import stock

	doc = frappe.get_doc("Material Return", name)
	doc.check_permission("write")
	if doc.status == "Returned":
		return {"name": name, "status": "Returned"}
	if doc.status != "Draft":
		frappe.throw(_("Only a draft Material Return can be confirmed"))
	if not doc.items:
		frappe.throw(_("Nothing to return"))
	_return_assert_returnable(doc)
	frappe.db.get_value("Purchase Order", doc.purchase_order, "name", for_update=True)  # serialize PO-status sync
	if stock.maintain_stock_enabled():
		rows = [(r.item_code, doc.warehouse, flt(r.returned_qty)) for r in doc.items]
		stock.post_out(rows, stock.RETURN_VOUCHER, doc.name, company=doc.company)
	doc.db_set("status", "Returned")
	_grn_sync_po_status(doc.purchase_order)  # net received dropped → re-open if we Closed it
	return {"name": name, "status": "Returned"}


@frappe.whitelist()
def cancel_return(name: str) -> dict:
	"""Reverse the return: restore the stock and mark it Cancelled (the PO's net
	received goes back up)."""
	from exportflow import stock

	doc = frappe.get_doc("Material Return", name)
	doc.check_permission("write")
	if doc.status == "Cancelled":
		return {"name": name, "status": "Cancelled"}
	frappe.db.get_value("Purchase Order", doc.purchase_order, "name", for_update=True)  # serialize PO-status sync
	was_full = _po_grn_summary(doc.purchase_order)["fully_received"]  # state before the return is undone
	stock.reverse(stock.RETURN_VOUCHER, doc.name)
	doc.db_set("status", "Cancelled")
	_grn_sync_po_status(doc.purchase_order, was_full=was_full)  # net restored → may re-close
	return {"name": name, "status": "Cancelled"}


@frappe.whitelist()
def get_returns() -> list[dict]:
	frappe.has_permission("Material Return", "read", throw=True)
	company = exportflow_company()
	filters = {"company": company} if company else {}
	return frappe.get_list(
		"Material Return",
		filters=filters,
		fields=["name", "goods_receipt_note", "purchase_order", "supplier_name", "status", "posting_date"],
		order_by="posting_date desc, creation desc",
		limit_page_length=100,
	)


@frappe.whitelist()
def get_return_detail(name: str) -> dict:
	frappe.has_permission("Material Return", "read", doc=name, throw=True)
	doc = frappe.get_doc("Material Return", name)
	can_write = bool(frappe.has_permission("Material Return", "write", doc=name))
	return {
		"mr": {
			"name": doc.name,
			"goods_receipt_note": doc.goods_receipt_note,
			"purchase_order": doc.purchase_order,
			"supplier": doc.supplier,
			"supplier_name": doc.supplier_name,
			"company": doc.company,
			"posting_date": doc.posting_date,
			"warehouse": doc.warehouse,
			"status": doc.status,
			"reason": doc.reason,
		},
		"items": [
			{
				"name": r.name,
				"item_code": r.item_code,
				"item_name": r.item_name,
				"received_qty": r.received_qty,
				"returned_qty": r.returned_qty,
				"uom": r.uom,
			}
			for r in doc.items
		],
		"can": {
			"edit": can_write and doc.status == "Draft",
			"confirm": can_write and doc.status == "Draft",
			"cancel": can_write and doc.status == "Returned",
		},
	}


@frappe.whitelist()
def get_grn_packs(purchase_orders) -> list[dict]:
	"""Pack / batch rows captured on the Received GRNs of these purchase orders, so
	the New Shipment form can pull them forward into its packing list."""
	frappe.has_permission("Goods Receipt Note", "read", throw=True)
	if isinstance(purchase_orders, str):
		try:
			purchase_orders = json.loads(purchase_orders)
		except ValueError:
			purchase_orders = [purchase_orders]
	pos = [p for p in (purchase_orders or []) if p]
	if not pos:
		return []
	grns = frappe.get_all(
		"Goods Receipt Note",
		filters={"purchase_order": ["in", pos], "status": "Received"},
		pluck="name",
	)
	if not grns:
		return []
	return frappe.get_all(
		"Goods Receipt Note Pack",
		filters={"parent": ["in", grns]},
		fields=[
			"item_code",
			"batch_no",
			"marks",
			"num_packages",
			"pack_type",
			"net_per",
			"tare_per",
			"mfg_date",
			"exp_date",
		],
		order_by="parent asc, idx asc",
	)


@frappe.whitelist()
def get_shipment_defaults(sales_order: str) -> dict:
	"""Booking a shipment from the deal: the SO already carries the customer,
	incoterm, named place and its letter of credit — prefill them instead of
	asking the user to retype what the system knows."""
	frappe.has_permission("Sales Order", "read", doc=sales_order, throw=True)
	frappe.has_permission("Letter of Credit", "read", throw=True)
	so = frappe.db.get_value(
		"Sales Order",
		sales_order,
		["customer", "customer_name", "incoterm", "named_place", "docstatus"],
		as_dict=True,
	)
	if not so:
		frappe.throw(_("Sales Order {0} not found").format(sales_order))
	if so.docstatus != 1:
		frappe.throw(_("Sales Order {0} is not submitted").format(sales_order))

	from exportflow.exportflow.doctype.letter_of_credit.letter_of_credit import OPEN_STATUSES

	lc = frappe.get_all(
		"Letter of Credit",
		filters={"sales_order": sales_order, "status": ["in", OPEN_STATUSES]},
		fields=["name", "lc_number"],
		order_by="creation desc",
		limit_page_length=1,
	)
	return {
		"customer": so.customer,
		"customer_name": so.customer_name,
		"incoterm": so.incoterm,
		"named_place": so.named_place,
		"letter_of_credit": lc[0].name if lc else None,
		"lc_number": lc[0].lc_number if lc else None,
		# for preselecting this SO's lines in the picker
		"so_details": frappe.get_all(
			"Sales Order Item", filters={"parent": sales_order}, pluck="name"
		),
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
			          po.supplier, po.merchanting_trade
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
			sub["merchanting"] = bool(po_row.merchanting_trade)
			# the India-export leg = a sourcing PO whose supplier isn't overseas;
			# lets the shipment form mirror the backend's mix block exactly
			sub["india"] = not _supplier_is_foreign(po_row.supplier)
			out.append(sub)
			left = flt(left - po_capacity, 3)
			emitted = True
		if left > 1e-6 or not emitted:
			sub = dict(line)
			sub["remaining"] = flt(left, 3)
			sub["purchase_order"] = None
			sub["po_detail"] = None
			sub["supplier"] = None
			sub["merchanting"] = False
			sub["india"] = False
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
			"company": exportflow_company(),
			"customer": payload.get("customer"),
			"mode": payload.get("mode") or "Sea",
			"trade_type": payload.get("trade_type") or None,
			"incoterm": payload.get("incoterm") or None,
			"cha": payload.get("cha") or None,
			"port_of_loading": payload.get("port_of_loading") or None,
			"port_of_discharge": payload.get("port_of_discharge") or None,
			"final_destination": payload.get("final_destination"),
			"etd": payload.get("etd") or None,
			"eta": payload.get("eta") or None,
			"letter_of_credit": payload.get("letter_of_credit") or None,
			"gst_export_mode": payload.get("gst_export_mode") or None,
			"igst_rate": flt(payload.get("igst_rate")) or None,
			"inr_rate": flt(payload.get("inr_rate")) or None,
			"freight_amount": flt(payload.get("freight_amount")) or None,
			"insurance_amount": flt(payload.get("insurance_amount")) or None,
			"buyer_order_no": payload.get("buyer_order_no"),
			"buyer_order_date": payload.get("buyer_order_date") or None,
			"consignee_to_order": 1 if payload.get("consignee_to_order") else 0,
			"consignee_name": payload.get("consignee_name"),
			"consignee_address": payload.get("consignee_address"),
			"notify_party": payload.get("notify_party"),
			"claim_rodtep": 1 if payload.get("claim_rodtep") else 0,
			"rodtep_rate_pct": flt(payload.get("rodtep_rate_pct")) or None,
			"claim_drawback": 1 if payload.get("claim_drawback") else 0,
			"drawback_rate_pct": flt(payload.get("drawback_rate_pct")) or None,
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
			"packs": _pack_rows(payload.get("packs")),
		}
	)
	doc.insert()
	return {"name": doc.name}


def _pack_rows(packs) -> list[dict]:
	"""Normalise an incoming packs payload into Export Shipment Pack child rows."""
	out = []
	for p in packs or []:
		if not p.get("item_code"):
			continue
		out.append(
			{
				"item_code": p.get("item_code"),
				"batch_no": p.get("batch_no"),
				"marks": p.get("marks"),
				"num_packages": cint(p.get("num_packages")),
				"pack_type": p.get("pack_type"),
				"net_per": flt(p.get("net_per")),
				"tare_per": flt(p.get("tare_per")),
				"mfg_date": p.get("mfg_date") or None,
				"exp_date": p.get("exp_date") or None,
			}
		)
	return out


@frappe.whitelist()
def get_shipments() -> list[dict]:
	frappe.has_permission("Export Shipment", "read", throw=True)
	company = exportflow_company()
	rows = frappe.get_all(
		"Export Shipment",
		filters={"company": company} if company else None,
		fields=["name", "customer", "customer_name", "mode", "trade_type", "current_milestone", "etd", "eta", "port_of_loading", "port_of_discharge"],
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

	from exportflow.mtt import is_merchanting

	mtt_outlay = None
	if is_merchanting(doc.trade_type):
		facts = doc.computed_import_facts()
		# the single supplier auto-fill applies (None when ambiguous / none)
		single = facts["suppliers"][0] if len(facts["suppliers"]) == 1 else None
		mtt_outlay = {
			"computed": facts["outlay_inr"],
			"costed_lines": facts["costed_lines"],
			"uncosted_lines": facts["uncosted_lines"],
			"suppliers": facts["suppliers"],
			"supplier": single,
			"supplier_name": frappe.db.get_value("Supplier", single, "supplier_name") if single else None,
		}

	return {
		"export_completed_on": str(export_done_on) if export_done_on else None,
		"mtt_outlay": mtt_outlay,
		"shipment": {
			f: doc.get(f)
			for f in (
				"name",
				"customer",
				"customer_name",
				"mode",
				"trade_type",
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
				"gst_export_mode",
				"igst_rate",
				"inr_rate",
				"freight_amount",
				"insurance_amount",
				"buyer_order_no",
				"buyer_order_date",
				"consignee_to_order",
				"consignee_name",
				"consignee_address",
				"notify_party",
				"claim_rodtep",
				"rodtep_rate_pct",
				"claim_drawback",
				"drawback_rate_pct",
				"mtt_ad_bank",
				"mtt_same_ad_bank",
				"mtt_import_supplier",
				"mtt_import_value_auto",
				"mtt_import_value_inr",
				"mtt_commencement_date",
				"mtt_import_payment_date",
				"mtt_completion_date",
				"mtt_idpms_status",
				"mtt_edpms_status",
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
		"packs": [
			{
				f: p.get(f)
				for f in (
					"name",
					"item_code",
					"batch_no",
					"marks",
					"num_packages",
					"pack_type",
					"net_per",
					"tare_per",
					"mfg_date",
					"exp_date",
				)
			}
			for p in doc.packs
		],
		"lc": lc,
		"sales_orders": sorted({row.sales_order for row in doc.items}),
		# Export Shipment is not submittable — editing is plain write permission
		"can": _doc_can("Export Shipment", name, amendable=False),
	}


# header fields the shipment edit form may set (customer/SO links stay fixed —
# those are structural; change them by re-booking the shipment)
SHIPMENT_EDITABLE = {
	"mode",
	"trade_type",
	"incoterm",
	"cha",
	"port_of_loading",
	"port_of_discharge",
	"final_destination",
	"etd",
	"eta",
	"letter_of_credit",
	"notes",
	# commercial / invoice terms (drive the redesigned prints)
	"gst_export_mode",
	"igst_rate",
	"inr_rate",
	"freight_amount",
	"insurance_amount",
	"buyer_order_no",
	"buyer_order_date",
	"consignee_to_order",
	"consignee_name",
	"consignee_address",
	"notify_party",
	# incentive claims booked at shipment time (drive the auto-created shells)
	"claim_rodtep",
	"rodtep_rate_pct",
	"claim_drawback",
	"drawback_rate_pct",
}
SHIPMENT_DATE_FIELDS = {"etd", "eta", "buyer_order_date"}


@frappe.whitelist()
def update_shipment(name: str, payload) -> dict:
	"""Edit a shipment's header fields and the qty/batch/pack of its existing
	lines. Adding or removing lines goes through the booking flow. Runs the full
	controller validation (cross-shipment qty, milestone seeding, checklist)."""
	doc = frappe.get_doc("Export Shipment", name)
	doc.check_permission("write")
	if isinstance(payload, str):
		payload = json.loads(payload)

	for field in SHIPMENT_EDITABLE:
		if field in payload:
			value = payload[field]
			if field in SHIPMENT_DATE_FIELDS and not value:
				value = None
			doc.set(field, value if value != "" else None)

	if "items" in payload:
		patch = {row.get("name"): row for row in payload["items"] if row.get("name")}
		for row in doc.items:
			p = patch.get(row.name)
			if not p:
				continue
			if "qty" in p:
				row.qty = flt(p["qty"])
			if "batch_no" in p:
				row.batch_no = p.get("batch_no")
			if "pack_description" in p:
				row.pack_description = p.get("pack_description")

	# packs are a flat editor — replace wholesale when the key is present
	if "packs" in payload:
		doc.set("packs", _pack_rows(payload["packs"]))

	doc.save()
	return {"name": doc.name}


@frappe.whitelist()
def set_shipment_milestone(shipment: str, row: str, completed=1, actual_date=None) -> str:
	doc = frappe.get_doc("Export Shipment", shipment)
	doc.check_permission("write")
	doc.set_milestone(row, bool(frappe.utils.cint(completed)), actual_date)
	return doc.current_milestone


# ---------------------------------------------------------------- documents (Phase 4)

INSTANCE_EDITABLE_FIELDS = {
	"status",
	"document_number",
	"document_date",
	"due_date",
	"responsible_party",
	"remarks",
	"description",
	"originals",
	"copies",
}
INSTANCE_DATE_FIELDS = {"document_date", "due_date"}
INSTANCE_STATUSES = ("Pending", "Drafted", "Sent/Filed", "Received", "Verified", "Not Applicable")

INSTANCE_LIST_FIELDS = [
	"name",
	"document_type",
	"category",
	"origin",
	"status",
	"responsible_party",
	"shipment",
	"customer",
	"sales_order",
	"purchase_order",
	"document_number",
	"document_date",
	"due_date",
	"originals",
	"copies",
	"description",
	"remarks",
	"file",
	"blocking",
	"blocked_milestone",
	"min_unblock_status",
	"source",
	"modified",
]


def _doc_type_options():
	"""Document Type catalog for the pickers + generate gating. format_doc_type
	is the target doctype of the type's print format — only Document-Instance
	formats can be generated from the checklist (the Pro Forma Invoice format
	targets its own doctype and is produced from the PFI screen instead)."""
	types = frappe.get_all(
		"Document Type",
		fields=["name", "category", "origin", "responsible_party", "default_print_format"],
		order_by="category asc, name asc",
		limit_page_length=300,
	)
	formats = list({t.default_print_format for t in types if t.default_print_format})
	fmt_dt = (
		{
			r.name: r.doc_type
			for r in frappe.get_all(
				"Print Format", filters={"name": ["in", formats]}, fields=["name", "doc_type"]
			)
		}
		if formats
		else {}
	)
	for t in types:
		t["format_doc_type"] = fmt_dt.get(t.default_print_format)
	return types


@frappe.whitelist()
def get_shipment_documents(shipment: str) -> dict:
	"""The shipment checklist card: every instance plus the type catalog for
	the manual-add picker."""
	frappe.has_permission("Export Shipment", "read", doc=shipment, throw=True)
	frappe.has_permission("Document Instance", "read", throw=True)
	return {
		"documents": frappe.get_all(
			"Document Instance",
			filters={"shipment": shipment},
			fields=INSTANCE_LIST_FIELDS,
			order_by="creation asc",
			limit_page_length=300,
		),
		"document_types": _doc_type_options(),
	}


@frappe.whitelist()
def get_documents_workspace() -> dict:
	"""Documents workspace: recent instances across all shipments (the client
	runs dozens of shipments, not thousands — 500 rows cover the horizon)."""
	frappe.has_permission("Document Instance", "read", throw=True)
	return {
		"documents": frappe.get_list(
			"Document Instance",
			fields=INSTANCE_LIST_FIELDS,
			order_by="modified desc",
			limit_page_length=500,
		),
		"document_types": _doc_type_options(),
	}


@frappe.whitelist()
def add_document_instance(shipment: str, document_type: str, remarks: str | None = None) -> dict:
	"""Manual checklist row — never touched by the rule engine."""
	frappe.has_permission("Document Instance", "create", throw=True)
	frappe.has_permission("Export Shipment", "read", doc=shipment, throw=True)
	customer = frappe.db.get_value("Export Shipment", shipment, "customer")
	if not customer:
		frappe.throw(_("Shipment {0} not found").format(shipment))
	doc = frappe.get_doc(
		{
			"doctype": "Document Instance",
			"document_type": document_type,
			"shipment": shipment,
			"customer": customer,
			"status": "Pending",
			"source": "Manual",
			"remarks": remarks,
		}
	).insert()
	return {"name": doc.name}


@frappe.whitelist()
def update_document_instance(name: str, values) -> dict:
	"""Controlled field updates from the UI (status, numbers, dates, remarks).
	Engine-owned fields (source, links, blocking config) stay server-side."""
	if isinstance(values, str):
		values = json.loads(values)
	unknown = set(values) - INSTANCE_EDITABLE_FIELDS
	if unknown:
		frappe.throw(_("Cannot update field(s): {0}").format(", ".join(sorted(unknown))))
	if "status" in values and values["status"] not in INSTANCE_STATUSES:
		frappe.throw(_("Unknown status {0}").format(values["status"]))

	doc = frappe.get_doc("Document Instance", name)
	doc.check_permission("write")
	if (
		"due_date" in values
		and doc.source != "Manual"
		and str(values.get("due_date") or "") != str(doc.due_date or "")
	):
		frappe.throw(
			_("The due date of {0} is tracked automatically (LC presentation / GST deadlines)").format(
				doc.document_type
			)
		)
	prev_number = doc.document_number
	for field, value in values.items():
		if field in INSTANCE_DATE_FIELDS and not value:
			value = None
		doc.set(field, value)
	doc.save()
	# the auto-created realization is keyed on the Commercial Invoice number — if
	# the user renumbers the CI, re-point its shell so regeneration stays
	# idempotent (a stale number would orphan the shell and let a duplicate open)
	if (
		doc.document_type == "Commercial Invoice"
		and doc.shipment
		and prev_number
		and prev_number != doc.document_number
	):
		for rel in frappe.get_all(
			"Export Realization",
			filters={"shipment": doc.shipment, "export_invoice": prev_number},
			pluck="name",
		):
			frappe.db.set_value(
				"Export Realization", rel, "export_invoice", doc.document_number, update_modified=False
			)
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def attach_document_file(name: str, file_url: str) -> dict:
	"""Stamp an uploaded file onto the instance. frappe's upload_file records
	attached_to_field but never writes the Attach field itself — this endpoint
	closes the loop after the client uploads."""
	doc = frappe.get_doc("Document Instance", name)
	doc.check_permission("write")
	if not frappe.db.exists(
		"File",
		{"file_url": file_url, "attached_to_doctype": "Document Instance", "attached_to_name": name},
	):
		frappe.throw(_("That file is not attached to {0}").format(name))
	doc.db_set({"file": file_url})
	return {"file": file_url}


def _auto_create_realization(doc) -> None:
	"""A Commercial Invoice has been generated → ensure an Export Realization
	shell exists for the shipment so the FEMA proceeds clock is tracked from the
	moment the export value is known. Idempotent at the SHIPMENT level (one
	auto-shell per shipment — never duplicates an imported/historical realization
	nor a re-generation), gated by ExportFlow Settings.auto_create_realization, and
	created for merchanting too (its realization tracks the MTT/EDPMS clock — unlike
	incentives, which a merchanting trade cannot earn). The realization
	controller fills customer and, once departed, export_date + the FEMA due
	date. Never raises — the caller wraps it, and it must never block the PDF."""
	# default ON: an unset Single field reads as None (the JSON default is not
	# materialised in tabSingles until the doc is saved), so treat None as enabled
	# and only skip on an explicit 0
	enabled = frappe.db.get_single_value("ExportFlow Settings", "auto_create_realization")
	if enabled is not None and not enabled:
		return
	if not doc.shipment or not doc.document_number:
		return
	# one auto-opened realization per shipment. Keying on the shipment (not the
	# invoice number) is what makes this safe against the historical/imported
	# realizations — those carry the MIS invoice number, so a per-(shipment,
	# number) check would mint a DUPLICATE when an old shipment's CI is generated.
	# A genuine second invoice on one shipment is added manually from the finance
	# card; this automation only ensures the first shell exists.
	if frappe.db.exists("Export Realization", {"shipment": doc.shipment}):
		return
	seed = _finance_seed(doc.shipment)
	invoice_value = seed.get("invoice_value")
	# seed the FX rate so a foreign-currency shell reports the right INR figure on
	# the finance dashboards (expected_inr = invoice_value × conversion_rate);
	# _finance_seed already carries both the FCY total and its INR equivalent, so
	# rate = INR / FCY. Left blank when the value/currency is unknown (the
	# dashboard then contributes 0 rather than a 1:1 mis-scaling).
	conversion_rate = None
	if seed.get("currency") and invoice_value:
		conversion_rate = flt(flt(seed.get("fob_value_inr")) / flt(invoice_value), 6) or None
	frappe.get_doc(
		{
			"doctype": "Export Realization",
			"shipment": doc.shipment,
			"export_invoice": doc.document_number,
			"status": "Awaiting Realization",
			# currency only when the shipment's sales orders agree; the FCY value
			# is meaningful only within one currency (else both left blank)
			"currency": seed.get("currency") or None,
			"invoice_value": invoice_value or None,
			"conversion_rate": conversion_rate,
		}
	).insert(ignore_permissions=True)


def _auto_create_incentives(doc) -> None:
	"""A Commercial Invoice has been generated → for each incentive scheme the
	shipment is booked to claim (RoDTEP / Duty Drawback, chosen on the booking
	form), open a Pending Export Incentive pre-filled with the FOB basis and the
	booked rate, so it is a confirm-and-file worklist item rather than a blank one
	(amount = FOB × rate, left blank when no rate was captured). Idempotent per
	(shipment, scheme). HARD-SKIPS merchanting — those trades cannot earn RoDTEP
	or Drawback and the Export Incentive controller would throw. Gated by
	ExportFlow Settings.auto_create_incentive (default ON; an unset Single field
	reads None, so only an explicit 0 disables it). Never raises — the caller
	wraps it and it must never block the PDF."""
	enabled = frappe.db.get_single_value("ExportFlow Settings", "auto_create_incentive")
	if enabled is not None and not enabled:
		return
	if not doc.shipment:
		return
	seed = _finance_seed(doc.shipment)
	if seed.get("merchanting"):
		# third-country / merchanting trades are ineligible for RoDTEP / Drawback
		return
	booked = frappe.db.get_value(
		"Export Shipment",
		doc.shipment,
		["claim_rodtep", "rodtep_rate_pct", "claim_drawback", "drawback_rate_pct"],
		as_dict=True,
	)
	if not booked:
		return
	fob = seed.get("fob_value_inr")
	wanted = []
	if booked.claim_rodtep:
		wanted.append(("RoDTEP", flt(booked.rodtep_rate_pct)))
	if booked.claim_drawback:
		wanted.append(("Duty Drawback", flt(booked.drawback_rate_pct)))
	for scheme, rate in wanted:
		# one auto-shell per (shipment, scheme) — never duplicates a manually
		# added or historical claim
		if frappe.db.exists("Export Incentive", {"shipment": doc.shipment, "scheme": scheme}):
			continue
		frappe.get_doc(
			{
				"doctype": "Export Incentive",
				"shipment": doc.shipment,
				"scheme": scheme,
				"status": "Pending",
				"fob_value": fob or None,
				"rate_pct": rate or None,
			}
		).insert(ignore_permissions=True)


@frappe.whitelist()
def generate_shipment_documents(shipment: str) -> dict:
	"""Generate every generatable document on a shipment in one pass. Generatable
	= origin 'Generated' AND a print format that targets Document Instance (the
	same gate the per-row Generate button uses). Rows already past Pending are
	left untouched — re-generation stays a deliberate per-row choice. Returns a
	per-document result so the UI can report partial success."""
	frappe.has_permission("Export Shipment", "read", doc=shipment, throw=True)
	frappe.has_permission("Document Instance", "write", throw=True)

	type_map = {t["name"]: t for t in _doc_type_options()}
	rows = frappe.get_all(
		"Document Instance",
		filters={"shipment": shipment},
		fields=["name", "document_type", "status"],
		order_by="creation asc",
		limit_page_length=300,
	)
	results = []
	for row in rows:
		t = type_map.get(row.document_type)
		generatable = bool(
			t and t.get("origin") == "Generated" and t.get("format_doc_type") == "Document Instance"
		)
		if not generatable or row.status != "Pending":
			continue
		try:
			res = generate_document(row.name)
			results.append(
				{
					"name": row.name,
					"document_type": row.document_type,
					"ok": True,
					"status": res.get("status"),
				}
			)
		except frappe.PermissionError:
			# an expected authz denial on a specific instance — report it as a
			# failed row, but don't log it as an application error
			results.append(
				{
					"name": row.name,
					"document_type": row.document_type,
					"ok": False,
					"error": "Not permitted",
				}
			)
		except Exception as e:
			frappe.log_error(
				title=f"Generate-all failed: {row.name}", message=frappe.get_traceback()
			)
			results.append(
				{
					"name": row.name,
					"document_type": row.document_type,
					"ok": False,
					"error": str(e),
				}
			)
	return {
		"results": results,
		"generated": sum(1 for r in results if r["ok"]),
		"failed": sum(1 for r in results if not r["ok"]),
	}


@frappe.whitelist()
def generate_document(name: str) -> dict:
	"""§5.2: render the instance's print format to PDF, attach it, move
	Pending → Drafted. Re-generating refreshes the file without resetting
	progress that happened after drafting."""
	doc = frappe.get_doc("Document Instance", name)
	doc.check_permission("write")
	# serialise concurrent generation of the same instance (a double-clicked
	# Generate, or a bulk pass overlapping a per-row generate) so the CI's
	# realization shell is opened exactly once
	frappe.db.get_value("Document Instance", name, "name", for_update=True)
	dt = frappe.db.get_value(
		"Document Type", doc.document_type, ["origin", "default_print_format"], as_dict=True
	)
	if not dt or dt.origin != "Generated":
		frappe.throw(_("{0} is a tracked document — attach the received file instead").format(doc.document_type))
	if not dt.default_print_format:
		frappe.throw(_("No print format is configured for {0}").format(doc.document_type))
	fmt_doctype = frappe.db.get_value("Print Format", dt.default_print_format, "doc_type")
	if fmt_doctype != "Document Instance":
		# e.g. the Pro Forma Invoice type's format targets the PFI doctype —
		# that document is generated from its own screen, not the checklist
		frappe.throw(
			_("{0} is generated from its own screen, not from the checklist").format(doc.document_type)
		)
	if not doc.shipment:
		frappe.throw(_("Only shipment documents can be generated here"))

	stamps = {}
	if not doc.document_number and doc.document_type == "Commercial Invoice":
		from frappe.model.naming import make_autoname

		stamps["document_number"] = make_autoname("EXP-INV-.YY.-.####")
	if not doc.document_date:
		stamps["document_date"] = frappe.utils.nowdate()
	if stamps:
		doc.db_set(stamps)

	pdf = frappe.get_print(
		"Document Instance", doc.name, print_format=dt.default_print_format, as_pdf=True, no_letterhead=1
	)
	from frappe.utils.file_manager import save_file

	# path-safe slug — frappe.scrub leaves "/" (e.g. "Drawback / DEEC Declaration"),
	# which save_file would read as a subdirectory that doesn't exist
	slug = re.sub(r"[^a-z0-9]+", "_", doc.document_type.lower()).strip("_") or "document"
	filename = f"{slug}_{doc.name}.pdf"
	file_doc = save_file(filename, pdf, "Document Instance", doc.name, is_private=1)

	updates = {"file": file_doc.file_url}
	if doc.status == "Pending":
		updates["status"] = "Drafted"
	doc.db_set(updates)

	# the export value is known the moment the Commercial Invoice exists — open
	# its realization shell now (FEMA due date filled later, at departure). Must
	# never block the PDF, so it is isolated.
	if doc.document_type == "Commercial Invoice":
		try:
			_auto_create_realization(doc)
		except Exception:
			frappe.log_error(
				title=f"Auto-create realization failed: {doc.name}", message=frappe.get_traceback()
			)
		try:
			_auto_create_incentives(doc)
		except Exception:
			frappe.log_error(
				title=f"Auto-create incentives failed: {doc.name}", message=frappe.get_traceback()
			)

	return {
		"file_url": file_doc.file_url,
		"status": doc.status,
		"document_number": doc.document_number,
	}


@frappe.whitelist()
def get_checklist_rules() -> list[dict]:
	"""Rules with their conditions in one round trip (Settings screen)."""
	frappe.has_permission("Document Checklist Rule", "read", throw=True)
	rules = frappe.get_all(
		"Document Checklist Rule",
		fields=["name", "rule_name", "document_type", "enabled", "notes"],
		order_by="name asc",
		limit_page_length=500,
	)
	for rule in rules:
		rule["conditions"] = frappe.get_all(
			"Document Checklist Condition",
			filters={"parent": rule.name, "parenttype": "Document Checklist Rule"},
			fields=["condition_field", "condition_value"],
			order_by="idx asc",
		)
	return rules


# ---------------------------------------------------------------- dashboard (Phase 5)


def _export_milestones() -> tuple[str, ...]:
	from exportflow.exportflow.doctype.export_shipment.export_shipment import EXPORT_MILESTONE

	return tuple(EXPORT_MILESTONE.values())


def _doc_unresolved_blocker(row) -> bool:
	from exportflow.exportflow.doctype.document_instance.document_instance import status_index

	if not row.blocking or row.status == "Not Applicable":
		return False
	return status_index(row.status) < status_index(row.min_unblock_status or "Received")


def _doc_done(row) -> bool:
	from exportflow.exportflow.doctype.document_instance.document_instance import status_index

	return row.status == "Not Applicable" or status_index(row.status) >= 2


def _shipment_chip(shipment, milestones_done: int, milestones_total: int, has_blocker: bool):
	"""Mockup status chips: Delivered / In transit / LEO awaited / Blocked /
	current milestone."""
	if milestones_total and milestones_done >= milestones_total:
		return "Delivered", "ok"
	if has_blocker and shipment.current_milestone == "Let Export Order":
		return "Blocked", "err"
	if shipment.current_milestone == "Let Export Order":
		return "LEO awaited", "pend"
	# past the export milestone = goods left the country
	done_names = shipment.get("_done_names") or set()
	if any(m in done_names for m in _export_milestones()):
		return "In transit", "ok"
	return shipment.current_milestone or "Planned", "pend"


def _month_key(d) -> str:
	return getdate(d).strftime("%Y-%m") if d else ""


@frappe.whitelist()
def get_sales_dashboard() -> dict:
	"""The financial picture (spec §6 sales view): export value booked, money
	received vs outstanding, procurement cost and indicative gross margin, with
	breakdowns by customer, destination and month. Computed from the deal data
	we already hold; incentive/realization sections are layered in once those
	doctypes exist."""
	out: dict = {"kpis": {}, "by_customer": [], "by_country": [], "by_month": [], "top_products": []}
	company = exportflow_company()

	def cf(extra=None):
		f = {"company": company} if company else {}
		if extra:
			f.update(extra)
		return f

	can = {
		"so": frappe.has_permission("Sales Order", "read"),
		"pfi": frappe.has_permission("Pro Forma Invoice", "read"),
		"po": frappe.has_permission("Purchase Order", "read"),
	}
	out["can"] = can
	if not can["so"]:
		return out

	# submitted, non-cancelled sales orders are the export topline
	sos = frappe.get_all(
		"Sales Order",
		filters=cf({"docstatus": 1}),
		fields=[
			"name",
			"customer",
			"customer_name",
			"currency",
			"grand_total",
			"base_grand_total",
			"transaction_date",
			"status",
		],
		limit_page_length=0,
	)
	customer_country = {}
	for cust in frappe.get_all(
		"Customer", fields=["name", "destination_country"], limit_page_length=0
	):
		customer_country[cust.name] = cust.destination_country or "Unknown"

	by_currency: dict[str, float] = {}
	value_inr = 0.0
	by_customer: dict[str, dict] = {}
	by_country: dict[str, float] = {}
	by_month: dict[str, float] = {}
	open_value_inr = 0.0
	for so in sos:
		inr = flt(so.base_grand_total)
		value_inr += inr
		by_currency[so.currency] = flt(by_currency.get(so.currency, 0) + flt(so.grand_total), 2)
		c = by_customer.setdefault(
			so.customer, {"customer": so.customer_name or so.customer, "value_inr": 0.0, "orders": 0}
		)
		c["value_inr"] += inr
		c["orders"] += 1
		country = customer_country.get(so.customer, "Unknown")
		by_country[country] = flt(by_country.get(country, 0) + inr, 2)
		by_month[_month_key(so.transaction_date)] = flt(
			by_month.get(_month_key(so.transaction_date), 0) + inr, 2
		)
		if so.status not in ("Completed", "Closed"):
			open_value_inr += inr

	out["kpis"]["export_value_inr"] = flt(value_inr, 2)
	out["kpis"]["export_value_by_currency"] = [
		{"currency": cur, "amount": amt} for cur, amt in sorted(by_currency.items())
	]
	out["kpis"]["order_count"] = len(sos)
	out["kpis"]["open_value_inr"] = flt(open_value_inr, 2)

	# realization: PFI raised vs received (advances + stage payments)
	if can["pfi"]:
		pfis = frappe.get_all(
			"Pro Forma Invoice",
			filters=cf({"docstatus": ["<", 2], "status": ["!=", "Cancelled"]}),
			fields=["amount", "paid_amount", "conversion_rate", "currency", "status"],
			limit_page_length=0,
		)
		raised = received = 0.0
		for p in pfis:
			rate = flt(p.conversion_rate) or 1.0
			raised += flt(p.amount) * rate
			received += flt(p.paid_amount) * rate
		out["kpis"]["pfi_raised_inr"] = flt(raised, 2)
		out["kpis"]["pfi_received_inr"] = flt(received, 2)
		out["kpis"]["pfi_outstanding_inr"] = flt(raised - received, 2)

	# procurement cost (POs are booked in company currency = INR)
	procurement_inr = 0.0
	if can["po"]:
		pos = frappe.get_all(
			"Purchase Order",
			filters=cf({"docstatus": 1}),
			fields=["base_grand_total", "grand_total"],
			limit_page_length=0,
		)
		procurement_inr = sum(flt(p.base_grand_total) or flt(p.grand_total) for p in pos)
		out["kpis"]["procurement_inr"] = flt(procurement_inr, 2)
		out["kpis"]["gross_margin_inr"] = flt(value_inr - procurement_inr, 2)
		out["kpis"]["margin_pct"] = flt(100 * (value_inr - procurement_inr) / value_inr, 1) if value_inr else 0.0

	# export incentives — RoDTEP scrips + Drawback cash earned vs still pending
	incentive_inr = 0.0
	if frappe.has_permission("Export Incentive", "read"):
		can["incentive"] = True
		incentives = frappe.get_all(
			"Export Incentive",
			filters=cf({"status": ["not in", INCENTIVE_DEAD]}),
			fields=["amount", "status"],
			limit_page_length=0,
		)
		incentive_inr = sum(flt(i.amount) for i in incentives)
		# pending = everything not yet realized (matches get_finance_workspace)
		pending = sum(flt(i.amount) for i in incentives if i.status not in INCENTIVE_REALIZED)
		out["kpis"]["incentive_inr"] = flt(incentive_inr, 2)
		out["kpis"]["incentive_pending_inr"] = flt(pending, 2)

	# bank realization — proceeds actually realized + overdue (FEMA 15-month)
	if frappe.has_permission("Export Realization", "read"):
		can["realization"] = True
		rels = frappe.get_all(
			"Export Realization",
			filters=cf(),
			fields=["amount_received_inr", "invoice_value", "conversion_rate", "status", "due_date"],
			limit_page_length=0,
		)
		realized = sum(flt(r.amount_received_inr) for r in rels)
		closed = ("Realized", "eBRC Closed", "Written Off", "Cancelled")
		today = getdate(nowdate())
		overdue = 0
		outstanding = 0.0
		for r in rels:
			open_row = r.status not in closed
			if open_row and r.due_date and getdate(r.due_date) < today:
				overdue += 1
			if open_row:
				# expected INR for this invoice, less what's come in — same
				# population as the overdue count (not the SO topline)
				expected = flt(r.invoice_value) * (flt(r.conversion_rate) or 1.0)
				outstanding += max(0.0, expected - flt(r.amount_received_inr))
		out["kpis"]["realized_inr"] = flt(realized, 2)
		out["kpis"]["realization_outstanding_inr"] = flt(outstanding, 2)
		out["kpis"]["realization_overdue"] = overdue

	# net margin folds incentives into the gross figure
	if "gross_margin_inr" in out["kpis"]:
		out["kpis"]["net_margin_inr"] = flt(out["kpis"]["gross_margin_inr"] + incentive_inr, 2)

	out["by_customer"] = sorted(
		[{**v, "value_inr": flt(v["value_inr"], 2)} for v in by_customer.values()],
		key=lambda r: -r["value_inr"],
	)[:8]
	out["by_country"] = sorted(
		[{"country": k, "value_inr": v} for k, v in by_country.items()], key=lambda r: -r["value_inr"]
	)[:8]
	out["by_month"] = [
		{"month": k, "value_inr": by_month[k]} for k in sorted(by_month) if k
	][-12:]

	return out


@frappe.whitelist()
def get_compliance_permissions() -> dict:
	"""The register hides mutation affordances from read-only roles."""
	return {
		"can_create": bool(frappe.has_permission("Compliance Record", "create")),
		"can_write": bool(frappe.has_permission("Compliance Record", "write")),
		"can_delete": bool(frappe.has_permission("Compliance Record", "delete")),
	}


# ---------------------------------------------------------------- finance (Phase 6)

INCENTIVE_FIELDS = [
	"name",
	"scheme",
	"shipment",
	"status",
	"shipping_bill_no",
	"shipping_bill_date",
	"fob_value",
	"rate_pct",
	"amount",
	"scroll_number",
	"scroll_date",
	"scrip_number",
	"scrip_expiry",
	"drawback_serial",
	"amount_received",
	"received_date",
	"remarks",
	"modified",
]
REALIZATION_FIELDS = [
	"name",
	"export_invoice",
	"shipment",
	"customer",
	"status",
	"currency",
	"invoice_value",
	"export_date",
	"due_date",
	"ad_bank",
	"fbc_number",
	"firc_no",
	"remittance_date",
	"amount_received",
	"amount_received_inr",
	"bank_charges",
	"conversion_mode",
	"conversion_rate",
	"forward_contract",
	"fwd_contract_no",
	"fwd_rate",
	"ebrc_number",
	"ebrc_date",
	"brc_ref",
	"oc_received",
	"remarks",
	"modified",
]


FORWARD_FIELDS = [
	"name", "contract_no", "ad_bank", "currency", "contract_amount", "forward_rate",
	"inr_value", "booking_date", "maturity_date", "status", "utilized_amount",
	"outstanding_amount", "hedge_note", "notes", "modified",
]
# realization statuses still owing FX (open receivables = the unhedged exposure base)
_OPEN_REL = ("Awaiting Realization", "Partially Realized", "Overdue", "Lodged with Bank")
# forward statuses that still carry live cover — Matured cover can still be delivered or
# rolled, so it counts toward the hedge / the picker until fully drawn (matches the alert)
_FORWARD_COVER = ("Open", "Partially Utilized", "Matured")


@frappe.whitelist()
def get_forward_contracts() -> dict:
	"""Forward contracts portfolio + a per-currency FX exposure summary for the
	Forward FX screen, one trip."""
	frappe.has_permission("Forward Contract", "read", throw=True)
	company = exportflow_company()
	cf = {"company": company} if company else {}
	contracts = frappe.get_all(
		"Forward Contract", filters=cf, fields=FORWARD_FIELDS, order_by="maturity_date asc, modified desc",
		limit_page_length=0,
	)
	today = getdate(nowdate())
	for c in contracts:
		c["days_to_maturity"] = (getdate(c.maturity_date) - today).days if c.maturity_date else None
	return {
		"contracts": contracts,
		"exposure": _fx_exposure(company),
		"can": {
			"write": frappe.has_permission("Forward Contract", "write"),
			"delete": frappe.has_permission("Forward Contract", "delete"),
		},
	}


@frappe.whitelist()
def get_open_forwards(currency: str | None = None) -> list:
	"""Forwards with cover still available — for the realization picker. Filtered to the
	realization's currency so a USD deal can't draw on a EUR forward."""
	frappe.has_permission("Forward Contract", "read", throw=True)
	company = exportflow_company()
	filters = {"status": ["in", list(_FORWARD_COVER)], "outstanding_amount": [">", 0]}
	if company:
		filters["company"] = company
	if currency:
		filters["currency"] = currency
	rows = frappe.get_all(
		"Forward Contract", filters=filters,
		fields=["name", "contract_no", "currency", "forward_rate", "outstanding_amount", "maturity_date"],
		order_by="maturity_date asc", limit_page_length=0,
	)
	for r in rows:
		r["label"] = f"{r.contract_no} · {r.currency} @ {flt(r.forward_rate):g} · {flt(r.outstanding_amount):,.0f} left"
	return rows


def _fx_exposure(company: str | None) -> list:
	"""Per-currency open receivables (FCY still owed) vs open forward cover → the
	unhedged exposure and a hedge ratio."""
	if not frappe.has_permission("Export Realization", "read"):
		return []
	cf = {"company": company} if company else {}
	recv: dict[str, float] = {}
	for r in frappe.get_all(
		"Export Realization", filters={**cf, "status": ["in", _OPEN_REL]},
		fields=["currency", "invoice_value", "amount_received"], limit_page_length=0,
	):
		if not r.currency:
			continue
		recv[r.currency] = recv.get(r.currency, 0.0) + max(0.0, flt(r.invoice_value) - flt(r.amount_received))

	cover: dict[str, float] = {}
	for c in frappe.get_all(
		"Forward Contract", filters={**cf, "status": ["in", list(_FORWARD_COVER)]},
		fields=["currency", "outstanding_amount"], limit_page_length=0,
	):
		if c.currency:
			cover[c.currency] = cover.get(c.currency, 0.0) + flt(c.outstanding_amount)

	out = []
	for ccy in sorted(set(recv) | set(cover)):
		receivable = flt(recv.get(ccy, 0.0), 2)
		hedged = flt(cover.get(ccy, 0.0), 2)
		out.append({
			"currency": ccy,
			"receivable": receivable,
			"hedged": hedged,
			"open_exposure": flt(max(0.0, receivable - hedged), 2),
			"hedge_pct": round(min(100.0, hedged / receivable * 100), 1) if receivable > 0 else None,
			# cover exceeding receivables (over-hedged, or cover on a currency with no open
			# receivables) is a real signal, not something to hide behind the 100% cap
			"over_hedged": flt(max(0.0, hedged - receivable), 2),
		})
	return out


# shared incentive status semantics (keep the two finance surfaces in sync)
INCENTIVE_REALIZED = ("Scrip Generated", "Credited", "Utilized")
INCENTIVE_DEAD = ("Cancelled", "Not Applicable")


def _incentive_realized(row) -> bool:
	return row.status in INCENTIVE_REALIZED


# shipment fields the MTT compliance panel reads
MTT_SHIPMENT_FIELDS = (
	"trade_type",
	"mtt_ad_bank",
	"mtt_same_ad_bank",
	"mtt_import_supplier",
	"mtt_import_value_inr",
	"mtt_commencement_date",
	"mtt_import_payment_date",
	"mtt_completion_date",
	"mtt_idpms_status",
	"mtt_edpms_status",
	"etd",
)


def _mtt_block(shipment_facts: dict, realizations: list) -> dict | None:
	"""The FEMA merchanting picture for one shipment — clocks, net-FX profit and
	closure status — or None when the shipment is an ordinary export. Export
	proceeds come from the linked realizations (realized INR if money has
	arrived, else the expected invoice value in INR)."""
	from exportflow import mtt

	if not mtt.is_merchanting(shipment_facts.get("trade_type")):
		return None
	completion_months, outlay_months = mtt.mtt_months(frappe.get_cached_doc("ExportFlow Settings"))

	# proceeds per realization = the greater of what has actually arrived and
	# what is still expected (invoice × rate) — so a partial receipt does not
	# wipe out the still-outstanding balance and falsely flag an FX loss
	# (mirrors the receivable convention used by the sales dashboard)
	proceeds_inr = flt(
		sum(
			max(
				flt(r.get("amount_received_inr")),
				flt(r.get("invoice_value")) * (flt(r.get("conversion_rate")) or 1.0),
			)
			for r in realizations
		)
	)
	received_any = any(
		flt(r.get("amount_received")) > 0 or flt(r.get("amount_received_inr")) > 0 for r in realizations
	)

	return mtt.clocks(
		shipment_facts,
		completion_months=completion_months,
		outlay_months=outlay_months,
		# pass the figure when a realization exists (even if it sums to 0), else None
		export_proceeds_inr=proceeds_inr if realizations else None,
		proceeds_received=received_any,
	)


@frappe.whitelist()
def get_finance_workspace() -> dict:
	"""Incentives + realizations portfolio for the Finance screen, one trip."""
	company = exportflow_company()
	cf = {"company": company} if company else {}
	today = getdate(nowdate())

	can_inc = frappe.has_permission("Export Incentive", "read")
	can_rel = frappe.has_permission("Export Realization", "read")
	incentives = (
		frappe.get_all(
			"Export Incentive", filters=cf, fields=INCENTIVE_FIELDS, order_by="modified desc",
			limit_page_length=0,
		)
		if can_inc
		else []
	)
	realizations = (
		frappe.get_all(
			"Export Realization", filters=cf, fields=REALIZATION_FIELDS, order_by="modified desc",
			limit_page_length=0,
		)
		if can_rel
		else []
	)
	closed = ("Realized", "eBRC Closed", "Written Off", "Cancelled")
	for r in realizations:
		r["overdue"] = bool(
			r.status not in closed and r.due_date and getdate(r.due_date) < today
		)

	kpis = {}
	if can_inc:
		active = [i for i in incentives if i.status not in INCENTIVE_DEAD]
		kpis["incentive_total"] = flt(sum(flt(i.amount) for i in active), 2)
		kpis["incentive_pending"] = flt(
			sum(flt(i.amount) for i in active if not _incentive_realized(i)), 2
		)
	if can_rel:
		kpis["realized"] = flt(sum(flt(r.amount_received_inr) for r in realizations), 2)
		kpis["overdue_count"] = sum(1 for r in realizations if r["overdue"])
		kpis["open_count"] = sum(1 for r in realizations if r.status not in closed)

	# third-country / merchanting trades — FEMA MTT compliance, not incentives
	from exportflow.mtt import MERCHANTING

	mtt_trades = []
	can_ship = frappe.has_permission("Export Shipment", "read")
	if can_ship:
		rels_by_ship: dict[str, list] = {}
		for r in realizations:
			if r.get("shipment"):
				rels_by_ship.setdefault(r["shipment"], []).append(r)
		merch = frappe.get_all(
			"Export Shipment",
			filters={**cf, "trade_type": MERCHANTING},
			fields=["name", "customer_name", *MTT_SHIPMENT_FIELDS],
			order_by="modified desc",
			limit_page_length=0,
		)
		for shp in merch:
			block = _mtt_block(shp, rels_by_ship.get(shp["name"], []))
			if not block:
				continue
			block["shipment"] = shp["name"]
			block["customer_name"] = shp.get("customer_name")
			mtt_trades.append(block)
		kpis["mtt_count"] = len(mtt_trades)
		kpis["mtt_completion_overdue"] = sum(
			1 for t in mtt_trades if not t["completed"] and (t["completion_days"] or 0) < 0
		)
		kpis["mtt_outlay_overdue"] = sum(
			1 for t in mtt_trades if t["outlay_open"] and (t["outlay_days"] or 0) < 0
		)
		kpis["mtt_fx_negative"] = sum(
			1 for t in mtt_trades if t["net_fx_profit_inr"] is not None and t["net_fx_profit_inr"] < 0
		)

	return {
		"incentives": incentives,
		"realizations": realizations,
		"mtt_trades": mtt_trades,
		"kpis": kpis,
		"can": {
			"incentive_read": can_inc,
			"realization_read": can_rel,
			"mtt_read": can_ship,
			**_finance_can(),
		},
	}


@frappe.whitelist()
def get_shipment_finance(shipment: str) -> dict:
	"""Incentives + realizations attached to one shipment (detail card), plus
	the FEMA merchanting compliance block when the shipment is third-country."""
	frappe.has_permission("Export Shipment", "read", doc=shipment, throw=True)
	realizations = (
		frappe.get_all(
			"Export Realization",
			filters={"shipment": shipment},
			fields=REALIZATION_FIELDS,
			order_by="creation asc",
		)
		if frappe.has_permission("Export Realization", "read")
		else []
	)
	facts = frappe.db.get_value(
		"Export Shipment", shipment, MTT_SHIPMENT_FIELDS, as_dict=True
	)
	return {
		"incentives": frappe.get_all(
			"Export Incentive",
			filters={"shipment": shipment},
			fields=INCENTIVE_FIELDS,
			order_by="creation asc",
		)
		if frappe.has_permission("Export Incentive", "read")
		else [],
		"realizations": realizations,
		"mtt": _mtt_block(facts, realizations) if facts else None,
		# create → the "Add" actions; write → editing an existing row; delete →
		# removing one made by mistake. Each is the user's real ERPNext permission
		# (the save/delete call re-checks per-doc server-side regardless).
		"can": _finance_can(),
	}


def _finance_can() -> dict:
	"""Per-doctype create/write/delete flags for the incentive & realization
	cards — drives which row affordances (add / edit / delete) the UI shows."""
	return {
		"incentive_create": bool(frappe.has_permission("Export Incentive", "create")),
		"incentive_write": bool(frappe.has_permission("Export Incentive", "write")),
		"incentive_delete": bool(frappe.has_permission("Export Incentive", "delete")),
		"realization_create": bool(frappe.has_permission("Export Realization", "create")),
		"realization_write": bool(frappe.has_permission("Export Realization", "write")),
		"realization_delete": bool(frappe.has_permission("Export Realization", "delete")),
	}


@frappe.whitelist()
def get_shipment_finance_seed(shipment: str) -> dict:
	"""Pre-fill values for creating an incentive or a realization straight from
	the shipment finance card. The export value is Σ(shipped qty × SO line rate)
	over THIS shipment's lines — surfaced both in the deal currency (the
	realization invoice value) and in INR (the incentive FOB basis). Customer,
	export date and the FEMA due date are derived by the document controllers on
	save; export_date is previewed here only so the form shows it. Currency is
	returned only when every line's sales order shares one (else the user picks)."""
	frappe.has_permission("Export Shipment", "read", doc=shipment, throw=True)
	return _finance_seed(shipment)


def _finance_seed(shipment: str) -> dict:
	"""The finance-seed math without the permission gate — shared by the
	whitelisted endpoint above and the CI-driven realization auto-create (a
	system action)."""
	shp = frappe.db.get_value(
		"Export Shipment",
		shipment,
		["customer", "customer_name", "mode", "bl_date", "awb_date", "trade_type"],
		as_dict=True,
	)
	if not shp:
		frappe.throw(_("Shipment {0} not found").format(shipment))

	from exportflow.mtt import is_merchanting

	rows = frappe.get_all(
		"Export Shipment Item",
		filters={"parent": shipment},
		fields=["qty", "so_detail", "sales_order"],
	)
	currencies: set[str] = set()
	so_currency: dict[str, str | None] = {}
	fcy = inr = 0.0
	for r in rows:
		# so_detail/sales_order are reqd and validate_items guarantees they
		# resolve, so the defensive skips below never fire for a saved shipment
		if not r.so_detail:
			continue
		line = frappe.db.get_value(
			"Sales Order Item", r.so_detail, ["rate", "base_rate"], as_dict=True
		)
		if not line:
			continue
		fcy += flt(r.qty) * flt(line.rate)
		inr += flt(r.qty) * flt(line.base_rate)
		if r.sales_order:
			if r.sales_order not in so_currency:
				so_currency[r.sales_order] = frappe.db.get_value(
					"Sales Order", r.sales_order, "currency"
				)
			if so_currency[r.sales_order]:
				currencies.add(so_currency[r.sales_order])

	homogeneous = len(currencies) == 1
	export_date = shp.awb_date if shp.mode == "Air" else shp.bl_date
	return {
		"shipment": shipment,
		"customer": shp.customer,
		"customer_name": shp.customer_name,
		"merchanting": is_merchanting(shp.trade_type),
		"currency": next(iter(currencies)) if homogeneous else None,
		"currency_conflict": len(currencies) > 1,
		# FCY total is only meaningful within a single currency
		"invoice_value": flt(fcy, 2) if homogeneous else None,
		"fob_value_inr": flt(inr, 2),
		"export_date": str(export_date) if export_date else None,
	}


@frappe.whitelist()
def get_dashboard() -> dict:
	"""Everything the dashboard renders, one round trip (spec §6). Each card
	group is permission-gated independently so a narrower role still gets the
	blocks it may see."""
	today = getdate(nowdate())
	out: dict = {"kpis": {}, "shipments": [], "deadlines": [], "documents": [], "pfis": []}
	company = exportflow_company()

	can = {
		"shipment": frappe.has_permission("Export Shipment", "read"),
		"doc": frappe.has_permission("Document Instance", "read"),
		"lc": frappe.has_permission("Letter of Credit", "read"),
		"po": frappe.has_permission("Purchase Order", "read"),
		"pfi": frappe.has_permission("Pro Forma Invoice", "read"),
		"compliance": frappe.has_permission("Compliance Record", "read"),
	}

	# every block is scoped to the ExportFlow company
	def cf(extra=None):
		f = {"company": company} if company else {}
		if extra:
			f.update(extra)
		return f

	# all of this company's shipment names — scopes the document feeds too
	company_shipments = (
		frappe.get_all("Export Shipment", filters=cf(), pluck="name", limit_page_length=0)
		if can["shipment"]
		else []
	)

	# ---- live shipments table -------------------------------------------
	live_names: list[str] = []
	if can["shipment"]:
		shipments = frappe.get_all(
			"Export Shipment",
			filters=cf({"current_milestone": ["!=", "Completed"]}),
			fields=[
				"name",
				"customer_name",
				"mode",
				"current_milestone",
				"port_of_loading",
				"port_of_discharge",
				"etd",
			],
			order_by="etd asc, creation desc",
			limit_page_length=8,
		)
		live_names = [s.name for s in shipments]
		live_count = frappe.db.count("Export Shipment", cf({"current_milestone": ["!=", "Completed"]}))

		milestone_rows = (
			frappe.db.sql(
				"""SELECT parent, COUNT(*) AS total, SUM(completed) AS done,
				          GROUP_CONCAT(CASE WHEN completed = 1 THEN milestone END) AS done_names
				   FROM `tabShipment Milestone`
				   WHERE parent IN %s AND parenttype = 'Export Shipment'
				   GROUP BY parent""",
				(tuple(live_names),),
				as_dict=True,
			)
			if live_names
			else []
		)
		miles = {m.parent: m for m in milestone_rows}

		docs_by_shipment: dict[str, list] = {}
		blockers_by_shipment: dict[str, int] = {}
		if can["doc"] and live_names:
			doc_rows = frappe.get_all(
				"Document Instance",
				filters={"shipment": ["in", live_names]},
				fields=["shipment", "status", "blocking", "min_unblock_status"],
				limit_page_length=0,
			)
			for row in doc_rows:
				docs_by_shipment.setdefault(row.shipment, []).append(row)
				if _doc_unresolved_blocker(row):
					blockers_by_shipment[row.shipment] = blockers_by_shipment.get(row.shipment, 0) + 1

		for s in shipments:
			m = miles.get(s.name)
			docs = docs_by_shipment.get(s.name, [])
			s["_done_names"] = set((m.done_names or "").split(",")) if m else set()
			chip, tone = _shipment_chip(
				s, int(m.done or 0) if m else 0, m.total if m else 0, bool(blockers_by_shipment.get(s.name))
			)
			out["shipments"].append(
				{
					"name": s.name,
					"customer_name": s.customer_name,
					"route": " → ".join(p for p in (s.port_of_loading, s.port_of_discharge) if p) or None,
					"mode": s.mode,
					"current_milestone": s.current_milestone,
					"milestones_done": int(m.done or 0) if m else 0,
					"milestones_total": m.total if m else 0,
					"docs_done": sum(1 for d in docs if _doc_done(d)),
					"docs_total": len(docs),
					"etd": s.etd,
					"chip": chip,
					"tone": tone,
				}
			)
		out["kpis"]["live_shipments"] = live_count
		out["kpis"]["awaiting_leo"] = frappe.db.count(
			"Export Shipment", cf({"current_milestone": "Let Export Order"})
		)
		# goods past the export milestone on shipments that are not yet done
		out["kpis"]["in_transit"] = cint(
			frappe.db.sql(
				"""SELECT COUNT(DISTINCT sm.parent)
				   FROM `tabShipment Milestone` sm
				   JOIN `tabExport Shipment` es ON es.name = sm.parent
				   WHERE sm.parenttype = 'Export Shipment' AND sm.completed = 1
				     AND sm.milestone IN %(ms)s AND es.current_milestone != 'Completed'
				     AND (%(co)s IS NULL OR es.company = %(co)s)""",
				{"ms": _export_milestones(), "co": company},
			)[0][0]
		)

	# ---- documents KPIs + pending feed (scoped to this company's shipments) --
	if can["doc"] and company_shipments:
		open_docs = frappe.get_all(
			"Document Instance",
			filters={"status": ["in", ("Pending", "Drafted")], "shipment": ["in", company_shipments]},
			fields=[
				"name",
				"document_type",
				"shipment",
				"status",
				"due_date",
				"blocking",
				"min_unblock_status",
				"responsible_party",
			],
			limit_page_length=0,
		)
		blocking_docs = [d for d in open_docs if _doc_unresolved_blocker(d)]
		out["kpis"]["docs_pending"] = len(open_docs)
		out["kpis"]["docs_blocking"] = len(blocking_docs)
		out["kpis"]["docs_with_cha"] = sum(
			1 for d in open_docs if d.responsible_party == "CHA"
		)
		out["kpis"]["docs_due_soon"] = sum(
			1 for d in open_docs if d.due_date and (getdate(d.due_date) - today).days <= 7
		)

		def doc_sort_key(d):
			days = (getdate(d.due_date) - today).days if d.due_date else 9999
			return (0 if _doc_unresolved_blocker(d) else 1, days)

		for d in sorted(open_docs, key=doc_sort_key)[:6]:
			out["documents"].append(
				{
					"document_type": d.document_type,
					"shipment": d.shipment,
					"status": d.status,
					"responsible_party": d.responsible_party,
					"days": (getdate(d.due_date) - today).days if d.due_date else None,
					"blocking": 1 if _doc_unresolved_blocker(d) else 0,
				}
			)

	# ---- deadline feed: LC dates, GST clocks, compliance renewals -------
	# rows are structured (label / ref / sub) so the UI can set IDs in mono+cyan
	deadlines = []
	at_risk_lcs: set[str] = set()
	if can["lc"]:
		from exportflow.exportflow.doctype.letter_of_credit.letter_of_credit import OPEN_STATUSES

		for lc in frappe.get_all(
			"Letter of Credit",
			filters=cf({"status": ["in", OPEN_STATUSES]}),
			fields=["name", "lc_number", "customer_name", "latest_shipment_date", "expiry_date"],
			limit_page_length=0,
		):
			for label, date in (
				("LC latest shipment", lc.latest_shipment_date),
				("LC expiry", lc.expiry_date),
			):
				if not date:
					continue
				days = (getdate(date) - today).days
				if days <= 30:
					if days <= 14:
						at_risk_lcs.add(lc.name)
					deadlines.append(
						{
							"kind": "lc",
							"label": label,
							"ref": lc.lc_number,
							"sub": lc.customer_name or "",
							"days": days,
							"route": f"/lc/{lc.name}",
						}
					)
	if can["po"]:
		from exportflow.tasks import _po_fully_exported

		# bounded: only POs whose window closes within the feed horizon
		for po in frappe.get_all(
			"Purchase Order",
			filters=cf(
				{
					"docstatus": 1,
					"merchant_export_scheme": 1,
					"gst_export_deadline": ["<=", frappe.utils.add_days(today, 30)],
				}
			),
			fields=["name", "supplier_name", "gst_export_deadline"],
			limit_page_length=0,
		):
			if _po_fully_exported(po.name):
				continue
			days = (getdate(po.gst_export_deadline) - today).days
			deadlines.append(
				{
					"kind": "gst",
					"label": "90-day GST clock",
					"ref": po.name,
					"sub": f"{po.supplier_name} · export by {frappe.utils.formatdate(po.gst_export_deadline, 'dd MMM')}",
					"days": days,
					"route": f"/purchases/{po.name}",
				}
			)
	if can["compliance"]:
		for rec in frappe.get_all(
			"Compliance Record",
			filters=cf({"status": "Active", "expiry_date": ["is", "set"]}),
			fields=["name", "compliance_type", "title", "expiry_date"],
			limit_page_length=0,
		):
			days = (getdate(rec.expiry_date) - today).days
			if days <= 60:
				deadlines.append(
					{
						"kind": "compliance",
						"label": f"{rec.compliance_type} renewal — {rec.title}",
						"ref": None,
						"sub": f"Compliance register · due {frappe.utils.formatdate(rec.expiry_date, 'dd MMM')}",
						"days": days,
						"route": "/compliance",
					}
				)
	# merchanting (MTT) clocks: 4-month forex outlay and 9-month completion
	if can["shipment"]:
		from exportflow.mtt import MERCHANTING

		merch = frappe.get_all(
			"Export Shipment",
			filters=cf({"trade_type": MERCHANTING, "mtt_completion_date": ["is", "not set"]}),
			fields=["name", "customer_name", *MTT_SHIPMENT_FIELDS],
			limit_page_length=0,
		)
		if merch:
			rel_rows = frappe.get_all(
				"Export Realization",
				filters={"shipment": ["in", [m.name for m in merch]]},
				fields=["shipment", "amount_received", "amount_received_inr", "invoice_value", "conversion_rate"],
				limit_page_length=0,
			)
			rels_by_ship: dict[str, list] = {}
			for r in rel_rows:
				rels_by_ship.setdefault(r.shipment, []).append(r)
			for shp in merch:
				block = _mtt_block(shp, rels_by_ship.get(shp.name, []))
				if not block:
					continue
				if block["outlay_open"] and block["outlay_days"] is not None and block["outlay_days"] <= 30:
					deadlines.append(
						{
							"kind": "mtt",
							"label": "MTT forex outlay (4-month)",
							"ref": shp.name,
							"sub": f"{shp.customer_name or ''} · receive export proceeds",
							"days": block["outlay_days"],
							"route": f"/shipments/{shp.name}",
						}
					)
				if not block["completed"] and block["completion_days"] is not None and block["completion_days"] <= 30:
					deadlines.append(
						{
							"kind": "mtt",
							"label": "MTT completion (9-month)",
							"ref": shp.name,
							"sub": f"{shp.customer_name or ''} · complete the trade",
							"days": block["completion_days"],
							"route": f"/shipments/{shp.name}",
						}
					)
	deadlines.sort(key=lambda d: d["days"])
	out["deadlines"] = deadlines[:8]
	if can["lc"] or can["po"] or can["compliance"] or can["shipment"]:
		out["kpis"]["deadlines_14d"] = sum(1 for d in deadlines if d["days"] <= 14)
		out["kpis"]["lc_at_risk"] = len(at_risk_lcs)
		out["kpis"]["gst_at_risk"] = sum(
			1 for d in deadlines if d["kind"] == "gst" and d["days"] <= 14
		)

	# ---- receivable / PFIs awaiting payment ------------------------------
	if can["pfi"]:
		open_pfis = frappe.get_all(
			"Pro Forma Invoice",
			filters=cf({"status": ["in", ("Sent", "Partially Paid")]}),
			fields=[
				"name",
				"customer",
				"customer_name",
				"stage_description",
				"amount",
				"paid_amount",
				"currency",
				"pfi_date",
			],
			order_by="pfi_date asc",
			limit_page_length=0,
		)
		by_currency: dict[str, float] = {}
		for p in open_pfis:
			balance = flt(p.amount) - flt(p.paid_amount)
			if balance <= 0:
				continue
			by_currency[p.currency] = flt(by_currency.get(p.currency, 0) + balance, 2)
		out["kpis"]["receivable"] = [
			{"currency": cur, "amount": amt} for cur, amt in sorted(by_currency.items())
		]
		out["kpis"]["open_pfis"] = len(open_pfis)
		out["pfis"] = [
			{
				"name": p.name,
				"customer": p.customer_name or p.customer,
				"stage_description": p.stage_description,
				"balance": flt(flt(p.amount) - flt(p.paid_amount), 2),
				"currency": p.currency,
				"pfi_date": p.pfi_date,
			}
			for p in open_pfis[:5]
		]

	# ---- finance snapshot + realization aging (FEMA proceeds clock) ------
	if frappe.has_permission("Export Realization", "read"):
		closed_rel = ("Realized", "eBRC Closed", "Written Off", "Cancelled")
		export_inr = realized_inr = outstanding_inr = 0.0
		aging = {"overdue": 0, "d0_30": 0, "d30_60": 0, "d60p": 0}
		overdue_n = 0
		for r in frappe.get_all(
			"Export Realization",
			filters=cf(),
			fields=["status", "invoice_value", "conversion_rate", "amount_received_inr", "due_date"],
			limit_page_length=0,
		):
			# conversion_rate falls back to 1 only when truly unset (an INR deal);
			# the auto-created shells now seed it, so FCY values scale correctly
			expected = flt(r.invoice_value) * (flt(r.conversion_rate) or 1.0)
			export_inr += expected
			realized_inr += flt(r.amount_received_inr)
			if r.status not in closed_rel:
				outstanding_inr += max(0.0, expected - flt(r.amount_received_inr))
				if r.due_date:
					d = (getdate(r.due_date) - today).days
					if d < 0:
						aging["overdue"] += 1
						overdue_n += 1
					elif d <= 30:
						aging["d0_30"] += 1
					elif d <= 60:
						aging["d30_60"] += 1
					else:
						aging["d60p"] += 1
		out["kpis"]["export_value_inr"] = flt(export_inr, 2)
		out["kpis"]["realized_inr"] = flt(realized_inr, 2)
		out["kpis"]["outstanding_inr"] = flt(outstanding_inr, 2)
		out["kpis"]["realizations_overdue"] = overdue_n
		out["aging"] = aging

	# ---- merchanting (MTT) split + clock breaches + pipeline by stage ----
	if can["shipment"]:
		from exportflow.mtt import MERCHANTING

		out["kpis"]["shipments_total"] = len(company_shipments)
		out["kpis"]["mtt_total"] = frappe.db.count(
			"Export Shipment", cf({"trade_type": MERCHANTING})
		)

		merch_all = frappe.get_all(
			"Export Shipment",
			filters=cf({"trade_type": MERCHANTING}),
			fields=["name", *MTT_SHIPMENT_FIELDS],
			limit_page_length=0,
		)
		if merch_all:
			rbs: dict[str, list] = {}
			for r in frappe.get_all(
				"Export Realization",
				filters={"shipment": ["in", [m.name for m in merch_all]]},
				fields=["shipment", "amount_received", "amount_received_inr", "invoice_value", "conversion_rate"],
				limit_page_length=0,
			):
				rbs.setdefault(r.shipment, []).append(r)
			c_over = o_over = fx_neg = 0
			for shp in merch_all:
				b = _mtt_block(shp, rbs.get(shp.name, []))
				if not b:
					continue
				if not b["completed"] and (b["completion_days"] or 0) < 0:
					c_over += 1
				if b["outlay_open"] and (b["outlay_days"] or 0) < 0:
					o_over += 1
				if b["net_fx_profit_inr"] is not None and b["net_fx_profit_inr"] < 0:
					fx_neg += 1
			out["kpis"]["mtt_completion_overdue"] = c_over
			out["kpis"]["mtt_outlay_overdue"] = o_over
			out["kpis"]["mtt_fx_negative"] = fx_neg

		# coarse, mode-agnostic stages so the pipeline reads at a glance
		stage_of = {
			"Planned": "Booked", "Booked": "Booked", "Goods Dispatched": "Booked",
			"At Port/CFS": "At port", "At Airport/CFS": "At port",
			"Customs Filed": "Customs", "Let Export Order": "Customs",
			"Container Stuffed/Gated In": "Shipped", "Cargo Accepted": "Shipped",
			"Shipped on Board": "Shipped", "Departed": "Shipped", "Shipped from Origin": "Shipped",
			"Arrived Destination": "Arrived", "Arrived at Destination": "Arrived",
		}
		stages = ["Booked", "At port", "Customs", "Shipped", "Arrived"]
		counts = {s: 0 for s in stages}
		for row in frappe.get_all(
			"Export Shipment",
			filters=cf({"current_milestone": ["!=", "Completed"]}),
			fields=["current_milestone"],
			limit_page_length=0,
		):
			bucket = stage_of.get(row.current_milestone)
			if bucket:
				counts[bucket] += 1
		out["pipeline"] = [{"stage": s, "count": counts[s]} for s in stages]

	# the UI hides card groups the role cannot read — "no access" must not
	# masquerade as "nothing pending"
	out["can"] = can
	return out


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


@frappe.whitelist()
def get_company_logo() -> dict:
	"""The company logo as a base64 data URI — for the nav bar and the Settings
	preview. Embedded (not a /files URL) because the web server's /files route is
	misconfigured on this multi-tenant bench."""
	from exportflow.printing import _logo_data_uri

	return {
		"logo": _logo_data_uri(),
		"nav_height": cint(frappe.db.get_single_value("ExportFlow Settings", "logo_nav_height")) or 28,
	}
