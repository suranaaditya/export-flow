import frappe
from frappe.utils import add_days, flt, nowdate

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from exportflow.api import (
	create_export_sales_order,
	create_purchase_order,
	create_purchase_order_draft,
	create_shipment,
	preview_purchase_order,
	get_shippable_lines,
	get_so_procurement,
	set_shipment_milestone,
	submit_purchase_order,
	submit_sales_order,
)
from exportflow.exportflow.doctype.export_shipment.export_shipment import (
	AIR_MILESTONES,
	SEA_MILESTONES,
)
from exportflow.tests.test_dropship import _suffix, make_customer, make_supplier


def make_plain_item(name: str) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": name,
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": "Kg",
				"is_stock_item": 0,
				"is_sales_item": 1,
				"is_purchase_item": 1,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def book_deal(company, customer, items):
	"""SO via the deal-form endpoint (no suppliers), submitted."""
	company_currency = frappe.db.get_value("Company", company, "default_currency")
	result = create_export_sales_order(
		{
			"customer": customer,
			"delivery_date": add_days(nowdate(), 30),
			"currency": "EUR" if company_currency != "EUR" else "USD",
			"conversion_rate": 83,
			"items": items,
		}
	)
	submit_sales_order(result["name"])
	return frappe.get_doc("Sales Order", result["name"])


class TestLogistics(IntegrationTestCase):
	"""Spec §7 Phase 3: negotiated PO flow, milestone engine, M:N shipment
	quantity validation."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")

	def setup_deal(self, qty_a=100, qty_b=50):
		sfx = _suffix()
		item_a = make_plain_item(f"_Test EF L Item A {sfx}")
		item_b = make_plain_item(f"_Test EF L Item B {sfx}")
		customer = make_customer(f"_Test EF L Customer {sfx}")
		supplier_one = make_supplier(f"_Test EF L Supplier One {sfx}")
		supplier_two = make_supplier(f"_Test EF L Supplier Two {sfx}")
		so = book_deal(
			self.company,
			customer,
			[
				{"item_code": item_a, "qty": qty_a, "rate": 12},
				{"item_code": item_b, "qty": qty_b, "rate": 20},
			],
		)
		return so, customer, supplier_one, supplier_two

	def test_negotiated_po_flow(self):
		so, _customer, supplier_one, supplier_two = self.setup_deal()
		rows = {r.item_code: r for r in so.items}
		items = list(rows.values())

		result = create_purchase_order(
			so.name,
			[
				{"so_detail": items[0].name, "supplier": supplier_one, "qty": 100, "rate": 9},
				{"so_detail": items[1].name, "supplier": supplier_two, "qty": 50, "rate": 15},
			],
		)
		self.assertEqual(len(result["purchase_orders"]), 2, "One PO per supplier")

		for created in result["purchase_orders"]:
			po = frappe.get_doc("Purchase Order", created["name"])
			self.assertEqual(po.docstatus, 0)
			self.assertEqual(len(po.items), 1)
			row = po.items[0]
			self.assertEqual(row.sales_order, so.name)
			self.assertTrue(row.sales_order_item)
			self.assertIn(flt(row.rate), (9.0, 15.0), "Negotiated buying rate applied")
			self.assertTrue(row.delivered_by_supplier)

		# SO rows now carry the negotiated supplier
		so.reload()
		self.assertEqual(so.items[0].supplier, supplier_one)
		self.assertTrue(so.items[0].delivered_by_supplier)

		# draft coverage blocks double-ordering
		with self.assertRaises(frappe.ValidationError):
			create_purchase_order(
				so.name,
				[{"so_detail": so.items[0].name, "supplier": supplier_one, "qty": 10, "rate": 9}],
			)

		procurement = get_so_procurement(so.name)
		line = next(l for l in procurement["lines"] if l["so_detail"] == so.items[0].name)
		self.assertEqual(flt(line["draft_qty"]), 100.0)
		self.assertEqual(flt(line["remaining"]), 0.0)

		submit_purchase_order(result["purchase_orders"][0]["name"])
		po = frappe.get_doc("Purchase Order", result["purchase_orders"][0]["name"])
		self.assertEqual(po.docstatus, 1)

	def test_same_item_two_lines_two_suppliers(self):
		"""The ERPNext mapper keys by item_code — our per-supplier calls must
		still place BOTH lines when the same item goes to two suppliers."""
		sfx = _suffix()
		item = make_plain_item(f"_Test EF L Twin Item {sfx}")
		customer = make_customer(f"_Test EF L Twin Customer {sfx}")
		supplier_one = make_supplier(f"_Test EF L Twin Sup One {sfx}")
		supplier_two = make_supplier(f"_Test EF L Twin Sup Two {sfx}")
		so = book_deal(
			self.company,
			customer,
			[{"item_code": item, "qty": 60, "rate": 12}, {"item_code": item, "qty": 40, "rate": 12}],
		)

		result = create_purchase_order(
			so.name,
			[
				{"so_detail": so.items[0].name, "supplier": supplier_one, "qty": 60, "rate": 9},
				{"so_detail": so.items[1].name, "supplier": supplier_two, "qty": 40, "rate": 8},
			],
		)
		self.assertEqual(len(result["purchase_orders"]), 2, "Both suppliers must get their PO")
		placed = {}
		for created in result["purchase_orders"]:
			po = frappe.get_doc("Purchase Order", created["name"])
			self.assertEqual(len(po.items), 1, "Each PO carries only its own line")
			placed[po.items[0].sales_order_item] = (po.supplier, flt(po.items[0].qty), flt(po.items[0].rate))
		self.assertEqual(placed[so.items[0].name], (supplier_one, 60.0, 9.0))
		self.assertEqual(placed[so.items[1].name], (supplier_two, 40.0, 8.0))

	def test_po_backfills_shipment_links(self):
		"""Shipment booked before procurement: PO submit claims the rows."""
		so, customer, supplier_one, _s2 = self.setup_deal(qty_a=50)
		shp = self.make_test_shipment(so, customer, qty=50)
		row_name = frappe.db.get_value(
			"Export Shipment Item", {"parent": shp["name"]}, "name"
		)
		self.assertFalse(
			frappe.db.get_value("Export Shipment Item", row_name, "purchase_order"),
			"No PO link at booking time",
		)

		result = create_purchase_order(
			so.name, [{"so_detail": so.items[0].name, "supplier": supplier_one, "qty": 50, "rate": 9}]
		)
		po_name = result["purchase_orders"][0]["name"]
		submit_purchase_order(po_name)

		self.assertEqual(
			frappe.db.get_value("Export Shipment Item", row_name, "purchase_order"),
			po_name,
			"PO submit must backfill the shipment item link",
		)

		frappe.get_doc("Purchase Order", po_name).cancel()
		self.assertFalse(
			frappe.db.get_value("Export Shipment Item", row_name, "purchase_order"),
			"PO cancel must release the shipment item link",
		)

	def test_partial_po_qty(self):
		so, _customer, supplier_one, _s2 = self.setup_deal(qty_a=100)
		first_line = so.items[0]
		create_purchase_order(
			so.name, [{"so_detail": first_line.name, "supplier": supplier_one, "qty": 40, "rate": 9}]
		)
		procurement = get_so_procurement(so.name)
		line = next(l for l in procurement["lines"] if l["so_detail"] == first_line.name)
		self.assertEqual(flt(line["draft_qty"]), 40.0)
		self.assertEqual(flt(line["remaining"]), 60.0)

	def make_test_shipment(self, so, customer, qty=60, mode="Sea", so_row=None):
		row = so_row or so.items[0]
		return create_shipment(
			{
				"customer": customer,
				"mode": mode,
				"items": [
					{
						"item_code": row.item_code,
						"qty": qty,
						"uom": row.uom,
						"sales_order": so.name,
						"so_detail": row.name,
					}
				],
			}
		)

	def test_shipment_milestones_and_qty_validation(self):
		so, customer, _s1, _s2 = self.setup_deal(qty_a=100)

		shp1 = self.make_test_shipment(so, customer, qty=60)
		doc = frappe.get_doc("Export Shipment", shp1["name"])
		self.assertEqual([m.milestone for m in doc.milestones], SEA_MILESTONES)
		self.assertEqual(doc.current_milestone, "Planned")

		# second shipment within the remaining 40 is fine
		shp2 = self.make_test_shipment(so, customer, qty=40)
		self.assertTrue(shp2["name"])

		# a third exceeding the SO line must fail (M:N cumulative check)
		with self.assertRaises(frappe.ValidationError):
			self.make_test_shipment(so, customer, qty=1)

		# shippable lines for the customer no longer include the exhausted line
		lines = get_shippable_lines(customer)
		self.assertFalse(
			[l for l in lines if l["so_detail"] == so.items[0].name],
			"Fully shipped lines disappear from the picker",
		)

	def test_air_milestones_seeded(self):
		so, customer, _s1, _s2 = self.setup_deal(qty_a=10)
		shp = self.make_test_shipment(so, customer, qty=10, mode="Air")
		doc = frappe.get_doc("Export Shipment", shp["name"])
		self.assertEqual([m.milestone for m in doc.milestones], AIR_MILESTONES)

	def test_sequential_milestone_engine(self):
		so, customer, _s1, _s2 = self.setup_deal(qty_a=10)
		shp = self.make_test_shipment(so, customer, qty=10)
		doc = frappe.get_doc("Export Shipment", shp["name"])
		rows = doc.milestones

		# cannot skip ahead
		with self.assertRaises(frappe.ValidationError):
			set_shipment_milestone(doc.name, rows[2].name, 1)

		current = set_shipment_milestone(doc.name, rows[0].name, 1)
		self.assertEqual(current, "Goods Dispatched")
		current = set_shipment_milestone(doc.name, rows[1].name, 1, actual_date=nowdate())
		self.assertEqual(current, "At Port/CFS")

		doc.reload()
		self.assertTrue(doc.milestones[0].completed)
		self.assertEqual(str(doc.milestones[1].actual_date), nowdate())

		# cannot un-complete the first while the second is done
		with self.assertRaises(frappe.ValidationError):
			set_shipment_milestone(doc.name, rows[0].name, 0)

		current = set_shipment_milestone(doc.name, rows[1].name, 0)
		self.assertEqual(current, "Goods Dispatched")

	def test_standalone_po_form(self):
		"""The full PO form: header details + terms, SO-linked and free lines
		mixed, drop-ship flags stamped, remaining enforced."""
		so, _customer, supplier_one, _s2 = self.setup_deal(qty_a=100)
		sfx = _suffix()
		free_item = make_plain_item(f"_Test EF L Free Item {sfx}")
		tc = frappe.get_doc(
			{
				"doctype": "Terms and Conditions",
				"title": f"_Test EF Buying Terms {sfx}",
				"buying": 1,
				"terms": "Material must ship with COA per batch.",
			}
		).insert(ignore_permissions=True)

		# distinct accounts: the engine maps actual amounts by account head, so
		# a charge sharing the levy's account would zero the percentage row
		expense_accounts = frappe.get_all(
			"Account",
			filters={"company": self.company, "is_group": 0, "root_type": "Expense"},
			pluck="name",
			limit=2,
		)
		expense_account, cartage_account = expense_accounts[0], expense_accounts[1]
		template = frappe.get_doc(
			{
				"doctype": "Purchase Taxes and Charges Template",
				"title": f"_Test EF Taxes {sfx}",
				"company": self.company,
				"taxes": [
					{
						"category": "Total",
						"add_deduct_tax": "Add",
						"charge_type": "On Net Total",
						"account_head": expense_account,
						"description": "Test levy 10%",
						"rate": 10,
					}
				],
			}
		).insert(ignore_permissions=True)

		podata = {
			"supplier": supplier_one,
			"schedule_date": add_days(nowdate(), 20),
			"merchant_export_scheme": 1,
			"tc_name": tc.name,
			"terms": tc.terms,
			"taxes_template": template.name,
			"extra_charges": [
				{"description": "Cartage to CFS", "account_head": cartage_account, "amount": 250}
			],
			"items": [
				{
					"item_code": so.items[0].item_code,
					"qty": 70,
					"rate": 9,
					"sales_order": so.name,
					"so_detail": so.items[0].name,
				},
				{"item_code": free_item, "qty": 5, "rate": 100},
			],
		}

		# the live preview computes through the real engine without saving
		preview = preview_purchase_order(podata)
		self.assertEqual(flt(preview["net_total"]), 1130.0)  # 70×9 + 5×100
		self.assertEqual(flt(preview["total_taxes_and_charges"]), 363.0)  # 113 levy + 250 cartage
		self.assertEqual(flt(preview["grand_total"]), 1493.0)
		self.assertFalse(
			frappe.db.exists("Purchase Order", {"supplier": supplier_one, "docstatus": 0}),
			"Preview must not persist anything",
		)

		result = create_purchase_order_draft(podata)
		po = frappe.get_doc("Purchase Order", result["name"])
		self.assertEqual(po.docstatus, 0)
		self.assertEqual(po.tc_name, tc.name)
		self.assertIn("COA per batch", po.terms)
		self.assertTrue(po.merchant_export_scheme)
		self.assertEqual(len(po.items), 2)
		self.assertEqual(len(po.taxes), 2, "Template levy + cartage row")
		self.assertEqual(flt(po.grand_total), 1493.0)

		linked = next(r for r in po.items if r.sales_order_item)
		free = next(r for r in po.items if not r.sales_order_item)
		self.assertEqual(linked.sales_order, so.name)
		self.assertTrue(linked.delivered_by_supplier)
		self.assertFalse(free.delivered_by_supplier)

		so.reload()
		self.assertEqual(so.items[0].supplier, supplier_one, "Drop-ship supplier stamped on the SO line")

		# remaining enforcement counts the draft just created (70 of 100)
		with self.assertRaises(frappe.ValidationError):
			create_purchase_order_draft(
				{
					"supplier": supplier_one,
					"items": [
						{
							"item_code": so.items[0].item_code,
							"qty": 40,
							"rate": 9,
							"sales_order": so.name,
							"so_detail": so.items[0].name,
						}
					],
				}
			)

	def test_shipment_rejects_foreign_so_line(self):
		so, customer, _s1, _s2 = self.setup_deal(qty_a=10)
		other_customer = make_customer(f"_Test EF L Other {_suffix()}")
		with self.assertRaises(frappe.ValidationError):
			create_shipment(
				{
					"customer": other_customer,
					"mode": "Sea",
					"items": [
						{
							"item_code": so.items[0].item_code,
							"qty": 5,
							"sales_order": so.name,
							"so_detail": so.items[0].name,
						}
					],
				}
			)
