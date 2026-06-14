import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from exportflow.api import (
	create_item,
	create_purchase_order_draft,
	get_po_detail,
	preview_purchase_order,
	update_item,
)
from exportflow.tests.test_dropship import _suffix, make_supplier


class TestItemTax(IntegrationTestCase):
	"""#6: Item Tax Template + GST HSN on the item master, and the per-item PO
	tax breakup. The GST/HSN autofill itself needs india_compliance (live only);
	here we test the template plumbing + the engine override + the breakup."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")
		cls.tax_account = frappe.get_all(
			"Account",
			filters={"company": cls.company, "is_group": 0, "account_type": "Tax"},
			pluck="name",
			limit_page_length=1,
		)[0]

	def _item_tax_template(self, rate):
		return frappe.get_doc(
			{
				"doctype": "Item Tax Template",
				"title": f"_Test EF ITT {_suffix()}",
				"company": self.company,
				"taxes": [{"tax_type": self.tax_account, "tax_rate": rate}],
			}
		).insert(ignore_permissions=True)

	def _ptc_template(self, rate):
		return frappe.get_doc(
			{
				"doctype": "Purchase Taxes and Charges Template",
				"title": f"_Test EF PTC {_suffix()}",
				"company": self.company,
				"taxes": [
					{
						"category": "Total",
						"add_deduct_tax": "Add",
						"charge_type": "On Net Total",
						"account_head": self.tax_account,
						"description": "Test tax",
						"rate": rate,
					}
				],
			}
		).insert(ignore_permissions=True)

	def test_create_and_update_item_tax_template(self):
		itt = self._item_tax_template(5)
		item = create_item(
			{"item_name": f"_Test EF TaxPlumb {_suffix()}", "item_tax_template": itt.name}
		)["name"]
		self.assertEqual(
			frappe.get_all("Item Tax", filters={"parent": item}, pluck="item_tax_template"),
			[itt.name],
			"create stores the single tax-template row",
		)

		itt2 = self._item_tax_template(12)
		update_item(item, {"item_tax_template": itt2.name})
		self.assertEqual(
			frappe.get_all("Item Tax", filters={"parent": item}, pluck="item_tax_template"),
			[itt2.name],
			"update swaps the template",
		)

		update_item(item, {"item_tax_template": ""})
		self.assertEqual(
			frappe.get_all("Item Tax", filters={"parent": item}), [], "blank clears the row"
		)

	def test_update_item_partial_payload_preserves_tax_template(self):
		# a partial update that doesn't mention item_tax_template must not wipe it
		itt = self._item_tax_template(5)
		item = create_item(
			{"item_name": f"_Test EF Partial {_suffix()}", "item_tax_template": itt.name}
		)["name"]
		update_item(item, {"pharmacopoeia_grade": "USP"})
		self.assertEqual(
			frappe.get_all("Item Tax", filters={"parent": item}, pluck="item_tax_template"),
			[itt.name],
			"omitting the tax key preserves the existing template",
		)
		self.assertEqual(frappe.db.get_value("Item", item, "pharmacopoeia_grade"), "USP")

	def test_update_item_refuses_to_flatten_desk_multi_row_taxes(self):
		# an item configured in the desk with several validity-dated tax rows must
		# not be silently collapsed when edited in-app
		itt1 = self._item_tax_template(5)
		itt2 = self._item_tax_template(8)
		sfx = _suffix()
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"_Test EF MultiTax {sfx}",
				"item_name": f"_Test EF MultiTax {sfx}",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": "Kg",
				"is_stock_item": 0,
				"taxes": [
					{"item_tax_template": itt1.name, "valid_from": "2020-01-01"},
					{"item_tax_template": itt2.name, "valid_from": "2024-01-01"},
				],
			}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			update_item(item.name, {"item_tax_template": ""})
		self.assertEqual(
			len(frappe.get_all("Item Tax", filters={"parent": item.name})), 2, "desk rows survive"
		)

	def test_saved_po_per_item_tax_breakup(self):
		# get_po_detail's per-item breakup must work for a SAVED (reloaded) PO, not
		# only the live preview — and reflect each item's rate override
		ptc = self._ptc_template(6)
		itt = self._item_tax_template(2)  # overrides the same tax head to 2%
		sfx = _suffix()
		supplier = make_supplier(f"_Test EF SB Sup {sfx}")
		a = create_item({"item_name": f"_Test EF SB A {sfx}", "item_tax_template": itt.name})["name"]
		b = create_item({"item_name": f"_Test EF SB B {sfx}"})["name"]
		res = create_purchase_order_draft(
			{
				"supplier": supplier,
				"taxes_template": ptc.name,
				"items": [
					{"item_code": a, "qty": 10, "rate": 100},
					{"item_code": b, "qty": 10, "rate": 100},
				],
			}
		)
		det = get_po_detail(res["name"])
		by = {r["item_code"]: r for r in det["totals"]["by_item"]}
		self.assertAlmostEqual(by[a]["tax"], 20.0, places=1, msg="2% override on the saved PO")
		self.assertAlmostEqual(by[b]["tax"], 60.0, places=1, msg="6% template rate")

	def test_gst_hsn_code_skipped_without_india_compliance(self):
		# erptest has no gst_hsn_code field — passing it must not raise
		item = create_item({"item_name": f"_Test EF HSN {_suffix()}", "gst_hsn_code": "29420090"})
		self.assertTrue(frappe.db.exists("Item", item["name"]))

	def test_preview_per_item_tax_breakup_with_override(self):
		ptc = self._ptc_template(6)
		itt = self._item_tax_template(2)  # overrides the same tax head to 2%
		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Tax Sup {sfx}")
		a = create_item({"item_name": f"_Test EF TaxA {sfx}", "item_tax_template": itt.name})["name"]
		b = create_item({"item_name": f"_Test EF TaxB {sfx}"})["name"]

		prev = preview_purchase_order(
			{
				"supplier": supplier,
				"taxes_template": ptc.name,
				"items": [
					{"item_code": a, "qty": 10, "rate": 100},  # net 1000
					{"item_code": b, "qty": 10, "rate": 100},  # net 1000
				],
			}
		)
		by = {r["item_code"]: r for r in prev["by_item"]}
		self.assertEqual(len(prev["by_item"]), 2, "one breakup row per item")
		self.assertAlmostEqual(by[a]["net"], 1000.0, places=1)
		# A's rate is overridden to 2% by its item tax template; B uses the 6% template
		self.assertAlmostEqual(by[a]["tax"], 20.0, places=1)
		self.assertAlmostEqual(by[b]["tax"], 60.0, places=1)
