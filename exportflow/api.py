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
	}


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
