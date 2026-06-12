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
