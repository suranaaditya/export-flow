import frappe
from frappe.utils import add_days, nowdate

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from erpnext.selling.doctype.sales_order.sales_order import make_purchase_order


def _suffix() -> str:
	return frappe.generate_hash(length=6).upper()


def make_supplier(name: str) -> str:
	supplier = frappe.get_doc(
		{
			"doctype": "Supplier",
			"supplier_name": name,
			"supplier_group": frappe.db.get_value("Supplier Group", {}, "name"),
			"country": "India",
			"default_merchant_export_scheme": 1,
		}
	).insert(ignore_permissions=True)
	return supplier.name


def make_customer(name: str) -> str:
	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Company",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
			"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			"gst_category": "Overseas",
		}
	).insert(ignore_permissions=True)
	return customer.name


def make_dropship_item(name: str, default_supplier: str, company: str) -> str:
	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": name,
			"item_name": name,
			"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
			"stock_uom": "Kg",
			"is_stock_item": 0,
			"is_sales_item": 1,
			"is_purchase_item": 1,
			"delivered_by_supplier": 1,
			"pharmacopoeia_grade": "IP",
			"item_defaults": [{"company": company, "default_supplier": default_supplier}],
		}
	).insert(ignore_permissions=True)
	return item.name


def make_dropship_so(customer: str, company: str, item_rows: list[dict]):
	# Foreign-currency deal: pick a currency different from the company currency.
	company_currency = frappe.db.get_value("Company", company, "default_currency")
	deal_currency = "USD" if company_currency != "USD" else "EUR"
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer,
			"company": company,
			"transaction_date": nowdate(),
			"delivery_date": add_days(nowdate(), 30),
			"order_type": "Sales",
			"currency": deal_currency,
			"conversion_rate": 83.0,
			"payment_terms_narrative": "30% advance, 70% against B/L copy",
			"items": [
				{
					"item_code": row["item_code"],
					"qty": row["qty"],
					"rate": row.get("rate", 10),
					"delivered_by_supplier": 1,
				}
				for row in item_rows
			],
		}
	)
	so.insert(ignore_permissions=True)
	so.submit()
	return so


class TestDropShipFlow(IntegrationTestCase):
	"""Spec §4.1: SO items default to delivered_by_supplier, POs are created via
	ERPNext's drop-ship mapping so item-level SO↔PO linkage is native; no stock
	ledger entries anywhere."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")

	def test_one_po_covers_multiple_so_lines(self):
		"""Two SO lines with the same default supplier map into ONE PO."""
		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Supplier {sfx}")
		item_a = make_dropship_item(f"_Test EF Item A {sfx}", supplier, self.company)
		item_b = make_dropship_item(f"_Test EF Item B {sfx}", supplier, self.company)
		customer = make_customer(f"_Test EF Customer {sfx}")

		so = make_dropship_so(
			customer,
			self.company,
			[{"item_code": item_a, "qty": 100}, {"item_code": item_b, "qty": 50}],
		)

		pos = make_purchase_order(
			so.name,
			selected_items=[
				{"item_code": item_a, "supplier": supplier},
				{"item_code": item_b, "supplier": supplier},
			],
		)
		self.assertEqual(len(pos), 1, "Expected a single PO for a single supplier")

		po = pos[0]
		self.assertEqual(po.supplier, supplier)
		self.assertEqual(len(po.items), 2)

		so_rows_by_item = {row.item_code: row for row in so.items}
		for po_row in po.items:
			self.assertEqual(po_row.sales_order, so.name, "PO row must link back to the SO")
			expected_so_row = so_rows_by_item[po_row.item_code]
			self.assertEqual(
				po_row.sales_order_item,
				expected_so_row.name,
				"PO row must link to the exact SO item row",
			)
			self.assertEqual(po_row.qty, expected_so_row.qty)

		# make_purchase_order already inserts the PO when a supplier is given
		self.assertFalse(po.is_new(), "PO should be inserted by the drop-ship mapper")
		self.assertTrue(
			all(row.delivered_by_supplier for row in po.items),
			"PO rows must carry delivered_by_supplier",
		)

	def test_one_so_maps_to_multiple_pos(self):
		"""SO lines with different default suppliers map into one PO per supplier."""
		sfx = _suffix()
		supplier_one = make_supplier(f"_Test EF Supplier One {sfx}")
		supplier_two = make_supplier(f"_Test EF Supplier Two {sfx}")
		item_a = make_dropship_item(f"_Test EF Item C {sfx}", supplier_one, self.company)
		item_b = make_dropship_item(f"_Test EF Item D {sfx}", supplier_two, self.company)
		customer = make_customer(f"_Test EF Customer Two {sfx}")

		so = make_dropship_so(
			customer,
			self.company,
			[{"item_code": item_a, "qty": 100}, {"item_code": item_b, "qty": 200}],
		)

		pos = make_purchase_order(
			so.name,
			selected_items=[
				{"item_code": item_a, "supplier": supplier_one},
				{"item_code": item_b, "supplier": supplier_two},
			],
		)
		self.assertEqual(len(pos), 2, "Expected one PO per supplier")
		self.assertEqual({po.supplier for po in pos}, {supplier_one, supplier_two})

		so_rows_by_item = {row.item_code: row for row in so.items}
		expected_item_for_supplier = {supplier_one: item_a, supplier_two: item_b}
		for po in pos:
			self.assertEqual(len(po.items), 1, "Each supplier's PO must carry only its own line")
			po_row = po.items[0]
			self.assertEqual(po_row.item_code, expected_item_for_supplier[po.supplier])
			expected_so_row = so_rows_by_item[po_row.item_code]
			self.assertEqual(po_row.sales_order, so.name)
			self.assertEqual(
				po_row.sales_order_item,
				expected_so_row.name,
				"PO row must link to the exact SO item row",
			)
			self.assertEqual(po_row.qty, expected_so_row.qty)

	def test_no_stock_movement_through_delivery(self):
		"""Spec §4.1: the full drop-ship leg — SO → PO → supplier delivers
		directly — produces no Delivery Note and no stock ledger entries."""
		from erpnext.buying.doctype.purchase_order.purchase_order import update_status

		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Supplier SLE {sfx}")
		item = make_dropship_item(f"_Test EF Item E {sfx}", supplier, self.company)
		customer = make_customer(f"_Test EF Customer SLE {sfx}")

		so = make_dropship_so(customer, self.company, [{"item_code": item, "qty": 10}])

		po = make_purchase_order(so.name, selected_items=[{"item_code": item, "supplier": supplier}])[0]
		po.items[0].rate = 100
		po.save(ignore_permissions=True)
		po.submit()

		# Supplier ships straight to the port — mark the drop-ship PO delivered
		update_status("Delivered", po.name)

		so.reload()
		self.assertEqual(so.per_delivered, 100, "SO must be fully delivered via the drop-ship PO")
		self.assertFalse(
			frappe.db.exists("Delivery Note Item", {"against_sales_order": so.name}),
			"Drop-ship flow must not create Delivery Notes",
		)
		for voucher in (so.name, po.name):
			self.assertFalse(
				frappe.db.exists("Stock Ledger Entry", {"voucher_no": voucher}),
				f"Drop-ship flow must not create stock ledger entries ({voucher})",
			)

	def test_gst_export_deadline_computation(self):
		"""Spec §4.3: deadline = supplier invoice date + 90 days when the
		merchant export scheme applies."""
		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Supplier GST {sfx}")
		item = make_dropship_item(f"_Test EF Item F {sfx}", supplier, self.company)

		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"supplier": supplier,
				"company": self.company,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 15),
				"supplier_invoice_no": f"SI-{sfx}",
				"supplier_invoice_date": "2026-06-01",
				"items": [{"item_code": item, "qty": 5, "rate": 100, "schedule_date": add_days(nowdate(), 15)}],
			}
		).insert(ignore_permissions=True)

		self.assertEqual(po.merchant_export_scheme, 1, "Scheme must default from the supplier on new POs")
		self.assertEqual(str(po.gst_export_deadline), "2026-08-30")

		po.merchant_export_scheme = 0
		po.save(ignore_permissions=True)
		self.assertFalse(po.gst_export_deadline, "Deadline must clear when the scheme is unchecked")

	def test_deadline_recomputes_on_submitted_po(self):
		"""The supplier invoice arrives only after PO submission — the fields
		are editable on submitted POs and the deadline recomputes there."""
		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Supplier Sub {sfx}")
		item = make_dropship_item(f"_Test EF Item G {sfx}", supplier, self.company)

		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"supplier": supplier,
				"company": self.company,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 15),
				"items": [{"item_code": item, "qty": 5, "rate": 100, "schedule_date": add_days(nowdate(), 15)}],
			}
		).insert(ignore_permissions=True)
		self.assertFalse(po.gst_export_deadline, "No deadline before the supplier invoice exists")
		po.submit()

		po.supplier_invoice_no = f"SI-{sfx}"
		po.supplier_invoice_date = "2026-06-15"
		po.save(ignore_permissions=True)

		po.reload()
		self.assertEqual(
			str(po.gst_export_deadline), "2026-09-13", "Deadline must recompute on a submitted PO"
		)

	def test_amended_po_keeps_unchecked_scheme(self):
		"""Amending a PO whose scheme was deliberately unchecked must not
		silently re-enable it from the supplier default."""
		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Supplier Amend {sfx}")  # default scheme = 1
		item = make_dropship_item(f"_Test EF Item H {sfx}", supplier, self.company)

		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"supplier": supplier,
				"company": self.company,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 15),
				"items": [{"item_code": item, "qty": 5, "rate": 100, "schedule_date": add_days(nowdate(), 15)}],
			}
		).insert(ignore_permissions=True)
		self.assertEqual(po.merchant_export_scheme, 1, "Defaults from supplier on first insert")

		po.merchant_export_scheme = 0
		po.save(ignore_permissions=True)
		po.submit()
		po.cancel()

		amended = frappe.copy_doc(po)
		amended.amended_from = po.name
		amended.docstatus = 0
		amended.insert(ignore_permissions=True)
		self.assertEqual(
			amended.merchant_export_scheme, 0, "Amendment must keep the user's unchecked scheme"
		)
