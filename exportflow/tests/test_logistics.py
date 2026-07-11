import frappe
from frappe.utils import add_days, flt, nowdate

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from exportflow.api import (
	amend_document,
	create_export_sales_order,
	create_purchase_order,
	create_purchase_order_draft,
	create_shipment,
	get_sales_order_for_edit,
	get_shipment_detail,
	preview_purchase_order,
	get_shippable_lines,
	get_so_procurement,
	set_shipment_milestone,
	submit_purchase_order,
	submit_sales_order,
	update_purchase_order_doc,
	update_sales_order,
	update_shipment,
)
from exportflow.exportflow.doctype.export_shipment.export_shipment import (
	AIR_MILESTONES,
	MERCHANTING_MILESTONES,
	SEA_MILESTONES,
)
from exportflow.mtt import MERCHANTING
from exportflow.tests.test_dropship import _suffix, make_customer, make_supplier


def _completed(doc, milestone: str) -> bool:
	return any(m.completed for m in doc.milestones if m.milestone == milestone)


def _resolve_blockers(shipment: str) -> None:
	"""Clear the base Shipping Bill / ADC NOC blocks by moving each blocking
	Document Instance to its minimum unblock status."""
	for di in frappe.get_all(
		"Document Instance",
		filters={"shipment": shipment, "blocking": 1},
		fields=["name", "min_unblock_status"],
	):
		frappe.db.set_value(
			"Document Instance", di.name, "status", di.min_unblock_status or "Received"
		)


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

	def make_test_shipment(self, so, customer, qty=60, mode="Sea", so_row=None, trade_type=None):
		row = so_row or so.items[0]
		return create_shipment(
			{
				"customer": customer,
				"mode": mode,
				"trade_type": trade_type,
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

	def test_buyer_po_carries_from_so_to_shipment(self):
		"""The customer's PO no/date entered on the SO round-trips through edit AND carries
		onto a shipment booked from it (which then prints on the commercial invoice)."""
		sfx = _suffix()
		item = make_plain_item(f"_Test EF PO Item {sfx}")
		customer = make_customer(f"_Test EF PO Cust {sfx}")
		company_currency = frappe.db.get_value("Company", self.company, "default_currency")
		res = create_export_sales_order(
			{
				"customer": customer,
				"delivery_date": add_days(nowdate(), 30),
				"currency": "EUR" if company_currency != "EUR" else "USD",
				"conversion_rate": 83,
				"po_no": "PO-BUYER-77",
				"po_date": "2026-06-10",
				"items": [{"item_code": item, "qty": 50, "rate": 20}],
			}
		)
		edit = get_sales_order_for_edit(res["name"])
		self.assertEqual(edit["po_no"], "PO-BUYER-77")
		self.assertEqual(str(edit["po_date"]), "2026-06-10")
		submit_sales_order(res["name"])
		so = frappe.get_doc("Sales Order", res["name"])
		ship = self.make_test_shipment(so, customer, qty=50)
		shp = frappe.get_doc("Export Shipment", ship["name"])
		self.assertEqual(shp.buyer_order_no, "PO-BUYER-77", "buyer's PO carried from the SO")
		self.assertEqual(str(shp.buyer_order_date), "2026-06-10")

	def test_shipment_milestones_and_qty_validation(self):
		so, customer, _s1, _s2 = self.setup_deal(qty_a=100)

		shp1 = self.make_test_shipment(so, customer, qty=60)
		doc = frappe.get_doc("Export Shipment", shp1["name"])
		self.assertEqual([m.milestone for m in doc.milestones], SEA_MILESTONES)
		# a freshly-booked shipment is auto-advanced through "At Port/CFS"
		self.assertEqual(doc.current_milestone, "Customs Filed")

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
		# on-creation auto-advance: the first three steps are done, current is the
		# next pending one (Customs Filed)
		self.assertTrue(all(m.completed for m in rows[:3]))
		self.assertEqual(doc.current_milestone, "Customs Filed")

		# cannot skip ahead past the current pending step
		with self.assertRaises(frappe.ValidationError):
			set_shipment_milestone(doc.name, rows[5].name, 1)

		current = set_shipment_milestone(doc.name, rows[3].name, 1, actual_date=nowdate())
		self.assertEqual(current, "Let Export Order")

		doc.reload()
		self.assertTrue(doc.milestones[3].completed)
		self.assertEqual(str(doc.milestones[3].actual_date), nowdate())

		# cannot un-complete an earlier step while a later one is done
		with self.assertRaises(frappe.ValidationError):
			set_shipment_milestone(doc.name, rows[2].name, 0)

		# un-complete the latest completed step
		current = set_shipment_milestone(doc.name, rows[3].name, 0)
		self.assertEqual(current, "Customs Filed")

	def test_creation_seeds_initial_progress(self):
		"""A shipment is never booked in advance — on creation the pre-departure
		steps are auto-completed (client rule 2026-06-18)."""
		so, customer, _s1, _s2 = self.setup_deal(qty_a=30)

		sea = frappe.get_doc(
			"Export Shipment", self.make_test_shipment(so, customer, qty=10)["name"]
		)
		self.assertTrue(_completed(sea, "At Port/CFS"))
		self.assertFalse(_completed(sea, "Customs Filed"))
		self.assertEqual(sea.current_milestone, "Customs Filed")

		air = frappe.get_doc(
			"Export Shipment", self.make_test_shipment(so, customer, qty=10, mode="Air")["name"]
		)
		self.assertTrue(_completed(air, "At Airport/CFS"))
		self.assertEqual(air.current_milestone, "Customs Filed")

		merch = frappe.get_doc(
			"Export Shipment",
			self.make_test_shipment(so, customer, qty=10, trade_type=MERCHANTING)["name"],
		)
		self.assertEqual([m.milestone for m in merch.milestones], MERCHANTING_MILESTONES)
		self.assertTrue(_completed(merch, "Booked"))
		self.assertEqual(merch.current_milestone, "Shipped from Origin")

	def test_fast_forward_respects_blocking(self):
		"""A document fact carries the earlier pending steps, but a milestone
		gated by an unresolved blocking document is never forced."""
		so, customer, _s1, _s2 = self.setup_deal(qty_a=10)
		doc = frappe.get_doc(
			"Export Shipment", self.make_test_shipment(so, customer, qty=10)["name"]
		)
		self.assertEqual(doc.current_milestone, "Customs Filed")

		# the B/L date proves departure — it carries the pending "Customs Filed",
		# but "Let Export Order" is blocked by the base Shipping Bill / ADC NOC
		doc.bl_number = "BL-FF-1"
		doc.bl_date = nowdate()
		doc.save()
		doc.reload()
		self.assertTrue(_completed(doc, "Customs Filed"), "carried the earlier pending step")
		self.assertFalse(_completed(doc, "Let Export Order"), "blocked milestone not forced")
		self.assertFalse(_completed(doc, "Shipped on Board"))
		self.assertEqual(doc.current_milestone, "Let Export Order")

	def test_fast_forward_clean_after_unblock(self):
		"""With the blockers resolved, the customs / LEO / departure facts
		fast-forward the whole chain, carrying every earlier pending step."""
		so, customer, _s1, _s2 = self.setup_deal(qty_a=10)
		doc = frappe.get_doc(
			"Export Shipment", self.make_test_shipment(so, customer, qty=10)["name"]
		)
		_resolve_blockers(doc.name)

		doc.reload()
		doc.shipping_bill_number = "SB-FF-2"
		doc.shipping_bill_date = nowdate()
		doc.leo_date = nowdate()
		doc.bl_number = "BL-FF-2"
		doc.bl_date = nowdate()
		doc.save()
		doc.reload()
		for milestone in (
			"Customs Filed",
			"Let Export Order",
			"Container Stuffed/Gated In",
			"Shipped on Board",
		):
			self.assertTrue(_completed(doc, milestone), milestone)
		self.assertEqual(doc.current_milestone, "Arrived Destination")

	def test_fast_forward_merchanting(self):
		"""Merchanting departure completes "Shipped from Origin" (no Indian
		customs steps to carry)."""
		so, customer, _s1, _s2 = self.setup_deal(qty_a=10)
		doc = frappe.get_doc(
			"Export Shipment",
			self.make_test_shipment(so, customer, qty=10, trade_type=MERCHANTING)["name"],
		)
		self.assertEqual(doc.current_milestone, "Shipped from Origin")

		doc.bl_number = "BL-MTT-1"
		doc.bl_date = nowdate()
		doc.save()
		doc.reload()
		self.assertTrue(_completed(doc, "Booked"))
		self.assertTrue(_completed(doc, "Shipped from Origin"))
		self.assertEqual(doc.current_milestone, "Arrived at Destination")

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

	def test_edit_draft_and_amend_sales_order(self):
		"""Drafts edit in place; a submitted SO (no downstream links) amends into
		a fresh draft and edits are then blocked on the cancelled original."""
		sfx = _suffix()
		item = make_plain_item(f"_Test EF Edit Item {sfx}")
		customer = make_customer(f"_Test EF Edit Cust {sfx}")
		cc = frappe.db.get_value("Company", self.company, "default_currency")
		created = create_export_sales_order(
			{
				"customer": customer,
				"delivery_date": add_days(nowdate(), 30),
				"currency": cc,
				"conversion_rate": 1,
				"items": [{"item_code": item, "qty": 10, "rate": 5}],
			}
		)
		name = created["name"]

		# edit the draft — qty/rate change sticks
		update_sales_order(
			name,
			{
				"customer": customer,
				"delivery_date": add_days(nowdate(), 40),
				"currency": cc,
				"conversion_rate": 1,
				"items": [{"item_code": item, "qty": 20, "rate": 7}],
			},
		)
		so = frappe.get_doc("Sales Order", name)
		self.assertEqual(flt(so.items[0].qty), 20.0)
		self.assertEqual(flt(so.items[0].rate), 7.0)

		# submit, then editing the submitted doc is refused
		submit_sales_order(name)
		with self.assertRaises(frappe.ValidationError):
			update_sales_order(name, {"items": [{"item_code": item, "qty": 1, "rate": 1}]})

		# amend reopens an editable draft; the original is cancelled
		amended = amend_document("Sales Order", name)
		self.assertNotEqual(amended["name"], name)
		new = frappe.get_doc("Sales Order", amended["name"])
		self.assertEqual(new.docstatus, 0)
		self.assertEqual(new.amended_from, name)
		self.assertEqual(frappe.db.get_value("Sales Order", name, "docstatus"), 2)

	def test_edit_draft_purchase_order(self):
		so, _customer, supplier_one, _s2 = self.setup_deal(qty_a=100)
		result = create_purchase_order(
			so.name, [{"so_detail": so.items[0].name, "supplier": supplier_one, "qty": 40, "rate": 9}]
		)
		po_name = result["purchase_orders"][0]["name"]
		update_purchase_order_doc(
			po_name,
			{
				"supplier": supplier_one,
				"items": [
					{
						"item_code": so.items[0].item_code,
						"qty": 30,
						"rate": 8,
						"sales_order": so.name,
						"so_detail": so.items[0].name,
					}
				],
			},
		)
		po = frappe.get_doc("Purchase Order", po_name)
		self.assertEqual(flt(po.items[0].qty), 30.0)
		self.assertEqual(flt(po.items[0].rate), 8.0)
		self.assertEqual(po.items[0].sales_order, so.name)

	def test_po_edit_respects_remaining_cap(self):
		"""Review finding: the edit path must keep the over-ordering cap, only
		excluding the edited PO's own draft contribution (not dropping it)."""
		so, _customer, supplier_one, _s2 = self.setup_deal(qty_a=100)
		result = create_purchase_order(
			so.name, [{"so_detail": so.items[0].name, "supplier": supplier_one, "qty": 40, "rate": 9}]
		)
		po_name = result["purchase_orders"][0]["name"]
		linked = {
			"item_code": so.items[0].item_code,
			"sales_order": so.name,
			"so_detail": so.items[0].name,
			"rate": 9,
		}
		# editing UP to the full SO qty is fine — its own 40 is excluded from the cap
		update_purchase_order_doc(po_name, {"supplier": supplier_one, "items": [{**linked, "qty": 100}]})
		self.assertEqual(
			flt(frappe.db.get_value("Purchase Order Item", {"parent": po_name}, "qty")), 100.0
		)
		# but editing BEYOND the SO line qty is still rejected
		with self.assertRaises(frappe.ValidationError):
			update_purchase_order_doc(po_name, {"supplier": supplier_one, "items": [{**linked, "qty": 101}]})

	def test_update_shipment_header_and_lines(self):
		so, customer, _s1, _s2 = self.setup_deal(qty_a=100)
		shp = self.make_test_shipment(so, customer, qty=60)
		row = frappe.db.get_value("Export Shipment Item", {"parent": shp["name"]}, "name")
		update_shipment(
			shp["name"],
			{
				"notes": "edited",
				"final_destination": "Durban yard",
				"items": [{"name": row, "qty": 50, "batch_no": "B-1", "pack_description": "25kg drums"}],
			},
		)
		doc = frappe.get_doc("Export Shipment", shp["name"])
		self.assertEqual(doc.notes, "edited")
		self.assertEqual(doc.final_destination, "Durban yard")
		self.assertEqual(flt(doc.items[0].qty), 50.0)
		self.assertEqual(doc.items[0].batch_no, "B-1")

	def test_update_shipment_commercial_fields_and_packs(self):
		so, customer, _s1, _s2 = self.setup_deal(qty_a=100)
		shp = self.make_test_shipment(so, customer, qty=60)
		item = frappe.db.get_value("Export Shipment Item", {"parent": shp["name"]}, "item_code")
		update_shipment(
			shp["name"],
			{
				"gst_export_mode": "On payment of IGST",
				"igst_rate": 18,
				"inr_rate": 89.6,
				"freight_amount": 100,
				"insurance_amount": 50,
				"buyer_order_no": "PO-9",
				"consignee_to_order": 1,
				"notify_party": "Notify Co.",
				"packs": [
					{
						"item_code": item,
						"batch_no": "CH-1",
						"marks": "1-10",
						"num_packages": 30,
						"pack_type": "HDPE Drums",
						"net_per": 25,
						"tare_per": 2.4,
						"mfg_date": "2025-12-01",
						"exp_date": "2030-11-01",
					}
				],
			},
		)
		doc = frappe.get_doc("Export Shipment", shp["name"])
		self.assertEqual(doc.gst_export_mode, "On payment of IGST")
		self.assertEqual(flt(doc.freight_amount), 100.0)
		self.assertEqual(doc.consignee_to_order, 1)
		self.assertEqual(doc.notify_party, "Notify Co.")
		self.assertEqual(len(doc.packs), 1)
		self.assertEqual(doc.packs[0].batch_no, "CH-1")
		self.assertEqual(doc.packs[0].num_packages, 30)
		self.assertEqual(flt(doc.packs[0].net_per), 25.0)
		# get_shipment_detail surfaces packs + the new fields back to the edit form
		detail = get_shipment_detail(shp["name"])
		self.assertEqual(len(detail["packs"]), 1)
		self.assertEqual(detail["packs"][0]["pack_type"], "HDPE Drums")
		self.assertEqual(detail["shipment"]["gst_export_mode"], "On payment of IGST")
		# replacing with an empty packs list clears them
		update_shipment(shp["name"], {"packs": []})
		self.assertEqual(len(frappe.get_doc("Export Shipment", shp["name"]).packs), 0)

	def test_pack_rejects_item_not_on_shipment(self):
		so, customer, _s1, _s2 = self.setup_deal(qty_a=100)
		shp = self.make_test_shipment(so, customer, qty=60)
		stray = make_plain_item(f"_Test EF L Stray {_suffix()}")
		with self.assertRaises(frappe.ValidationError):
			update_shipment(
				shp["name"],
				{"packs": [{"item_code": stray, "num_packages": 1, "net_per": 10}]},
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
