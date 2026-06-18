import frappe
from frappe.utils import add_days, add_months, flt, getdate, nowdate

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from exportflow.api import (
	create_purchase_order_draft,
	create_shipment,
	get_shipment_finance,
	set_shipment_milestone,
)
from exportflow.exportflow.doctype.export_shipment.export_shipment import MERCHANTING_MILESTONES
from exportflow.mtt import EXPORT_FROM_INDIA, MERCHANTING, clocks, is_merchanting
from exportflow.setup import seed_checklist_rules, seed_document_types
from exportflow.tests.test_dropship import _suffix, make_customer, make_supplier
from exportflow.tests.test_logistics import book_deal, make_plain_item

# India-customs / incentive artefacts a merchanting trade must never carry
SUPPRESSED = {"Shipping Bill", "ADC NOC", "Let Export Order", "EGM"}
# generic commercial docs a merchanting trade still owns
KEPT = {"Commercial Invoice", "Packing List"}


def doc_types_on(shipment: str) -> set[str]:
	return set(
		frappe.get_all("Document Instance", filters={"shipment": shipment}, pluck="document_type")
	)


class TestMerchanting(IntegrationTestCase):
	"""Third-country / merchanting (MTT) mode — see memory note
	`third-country-merchanting`."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")
		seed_document_types()
		seed_checklist_rules()

	def make_deal(self, qty=10, rate=12):
		sfx = _suffix()
		item = make_plain_item(f"_Test EF M Item {sfx}")
		customer = make_customer(f"_Test EF M Customer {sfx}")
		so = book_deal(self.company, customer, [{"item_code": item, "qty": qty, "rate": rate}])
		return so, customer

	def make_shipment(self, so, customer, trade_type=EXPORT_FROM_INDIA, qty=10):
		row = so.items[0]
		return create_shipment(
			{
				"customer": customer,
				"mode": "Sea",
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
		)["name"]

	# ---------------------------------------------------------------- flag

	def test_default_trade_type(self):
		so, customer = self.make_deal()
		shp = self.make_shipment(so, customer)  # trade_type omitted -> default
		self.assertEqual(frappe.db.get_value("Export Shipment", shp, "trade_type"), EXPORT_FROM_INDIA)

	# ---------------------------------------------------------------- checklist

	def test_merchanting_suppresses_india_documents(self):
		so, customer = self.make_deal()
		shp = self.make_shipment(so, customer, trade_type=MERCHANTING)
		types = doc_types_on(shp)
		self.assertTrue(KEPT <= types, f"kept set missing: {KEPT - types}")
		self.assertFalse(
			SUPPRESSED & types, f"merchanting must suppress: {SUPPRESSED & types}"
		)

	def test_switching_to_merchanting_removes_suppressed(self):
		so, customer = self.make_deal()
		shp = self.make_shipment(so, customer)  # ordinary export first
		self.assertTrue(SUPPRESSED <= doc_types_on(shp), "ordinary export owns the India docs")

		doc = frappe.get_doc("Export Shipment", shp)
		doc.trade_type = MERCHANTING
		doc.save(ignore_permissions=True)

		types = doc_types_on(shp)
		self.assertFalse(SUPPRESSED & types, "suppressed docs must be removed on switch")
		self.assertTrue(KEPT <= types, "commercial docs survive the switch")

	def test_merchanting_simple_milestone_set(self):
		"""Merchanting uses the simpler 4-step set (no Indian customs) and nothing
		gates it — the India blocking docs are suppressed. "Booked" is
		auto-completed on creation; the rest walk cleanly to "Completed"."""
		so, customer = self.make_deal()
		shp = self.make_shipment(so, customer, trade_type=MERCHANTING)
		doc = frappe.get_doc("Export Shipment", shp)
		self.assertEqual([m.milestone for m in doc.milestones], MERCHANTING_MILESTONES)
		self.assertEqual(doc.current_milestone, "Shipped from Origin")
		for m in doc.milestones:
			set_shipment_milestone(shp, m.name, 1)
		doc.reload()
		self.assertTrue(all(m.completed for m in doc.milestones))
		self.assertEqual(doc.current_milestone, "Completed")

	# ---------------------------------------------------------------- incentives

	def test_incentive_rejected_for_merchanting(self):
		so, customer = self.make_deal()
		shp = self.make_shipment(so, customer, trade_type=MERCHANTING)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Export Incentive",
					"scheme": "RoDTEP",
					"shipment": shp,
					"status": "Pending",
					"fob_value": 1000,
					"rate_pct": 1,
				}
			).insert(ignore_permissions=True)

	# ---------------------------------------------------------------- realization clock

	def test_realization_due_uses_mtt_clock_for_merchanting(self):
		so, customer = self.make_deal()
		shp = self.make_shipment(so, customer, trade_type=MERCHANTING)
		commencement = add_days(nowdate(), -30)
		frappe.db.set_value("Export Shipment", shp, "mtt_commencement_date", commencement)

		rel = frappe.get_doc(
			{
				"doctype": "Export Realization",
				"shipment": shp,
				"customer": customer,
				"export_invoice": f"_TEST-MTT-{_suffix()}",
				"status": "Awaiting Realization",
				"currency": "USD",
				"invoice_value": 1000,
			}
		).insert(ignore_permissions=True)
		# 9-month MTT completion window from commencement, NOT export+15 months
		self.assertEqual(getdate(rel.due_date), add_months(getdate(commencement), 9))

	def test_realization_due_unchanged_for_ordinary_export(self):
		so, customer = self.make_deal()
		shp = self.make_shipment(so, customer)  # ordinary export
		export_date = add_days(nowdate(), -10)
		frappe.db.set_value("Export Shipment", shp, "bl_date", export_date)

		rel = frappe.get_doc(
			{
				"doctype": "Export Realization",
				"shipment": shp,
				"customer": customer,
				"export_invoice": f"_TEST-EXP-{_suffix()}",
				"status": "Awaiting Realization",
				"currency": "USD",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(getdate(rel.due_date), add_months(getdate(export_date), 15))

	# ---------------------------------------------------------------- finance block

	def test_shipment_finance_mtt_block(self):
		so, customer = self.make_deal()
		shp = self.make_shipment(so, customer, trade_type=MERCHANTING)
		frappe.db.set_value(
			"Export Shipment",
			shp,
			{"mtt_import_value_inr": 1000, "mtt_commencement_date": nowdate()},
		)
		frappe.get_doc(
			{
				"doctype": "Export Realization",
				"shipment": shp,
				"customer": customer,
				"export_invoice": f"_TEST-FX-{_suffix()}",
				"status": "Realized",
				"currency": "USD",
				"amount_received": 18,
				"amount_received_inr": 1500,
			}
		).insert(ignore_permissions=True)

		fin = get_shipment_finance(shp)
		self.assertIsNotNone(fin["mtt"])
		self.assertEqual(fin["mtt"]["net_fx_profit_inr"], 500.0)  # 1500 - 1000
		self.assertFalse(fin["mtt"]["outlay_open"], "received proceeds close the outlay clock")

	def test_finance_block_none_for_ordinary_export(self):
		so, customer = self.make_deal()
		shp = self.make_shipment(so, customer)
		self.assertIsNone(get_shipment_finance(shp)["mtt"])

	# ---------------------------------------------------------------- auto CHA

	def test_auto_cha_third_country_setting(self):
		"""When the setting is on, a merchanting shipment is stamped with the
		'Third Country' placeholder CHA; ordinary exports are untouched."""
		from exportflow.exportflow.doctype.cha.cha import THIRD_COUNTRY_CHA

		frappe.db.set_single_value("ExportFlow Settings", "auto_cha_third_country", 0)
		so, customer = self.make_deal()
		off = self.make_shipment(so, customer, trade_type=MERCHANTING)
		self.assertNotEqual(frappe.db.get_value("Export Shipment", off, "cha"), THIRD_COUNTRY_CHA)

		frappe.db.set_single_value("ExportFlow Settings", "auto_cha_third_country", 1)
		so2, customer2 = self.make_deal()
		on = self.make_shipment(so2, customer2, trade_type=MERCHANTING)
		self.assertEqual(frappe.db.get_value("Export Shipment", on, "cha"), THIRD_COUNTRY_CHA)

		# an ordinary export keeps its (empty) CHA even with the setting on
		so3, customer3 = self.make_deal()
		exp = self.make_shipment(so3, customer3)
		self.assertNotEqual(frappe.db.get_value("Export Shipment", exp, "cha"), THIRD_COUNTRY_CHA)
		frappe.db.set_single_value("ExportFlow Settings", "auto_cha_third_country", 0)

	# ---------------------------------------------------------------- review regressions

	def test_switch_with_progressed_blocking_relinquished(self):
		"""Review finding #1: switching a shipment whose Shipping Bill was already
		progressed (so it is relinquished, not deleted) must drop its milestone
		gate — else the chain is permanently frozen. With merchanting's simpler set
		there is no Let Export Order at all, and the walk runs clean to Completed."""
		from exportflow.checklist import milestone_blockers

		so, customer = self.make_deal()
		shp = self.make_shipment(so, customer)  # ordinary export first
		sb = frappe.db.get_value(
			"Document Instance", {"shipment": shp, "document_type": "Shipping Bill"}, "name"
		)
		self.assertTrue(sb, "ordinary export must own a Shipping Bill")
		frappe.db.set_value("Document Instance", sb, "status", "Drafted")  # progress it

		doc = frappe.get_doc("Export Shipment", shp)
		doc.trade_type = MERCHANTING
		doc.save(ignore_permissions=True)

		# the relinquished Shipping Bill no longer gates any milestone
		self.assertEqual(
			milestone_blockers(shp, "Let Export Order"), [], "no suppressed doc may gate a milestone"
		)
		doc.reload()
		self.assertEqual([m.milestone for m in doc.milestones], MERCHANTING_MILESTONES)
		for m in doc.milestones:
			set_shipment_milestone(shp, m.name, 1)
		doc.reload()
		self.assertTrue(
			all(m.completed for m in doc.milestones), "the chain is not frozen by the old Shipping Bill"
		)
		self.assertEqual(doc.current_milestone, "Completed")

	def test_partial_realization_net_fx(self):
		"""Review finding #2: a partial receipt must not collapse proceeds to the
		received amount and falsely flag an FX loss."""
		so, customer = self.make_deal()
		shp = self.make_shipment(so, customer, trade_type=MERCHANTING)
		frappe.db.set_value(
			"Export Shipment", shp, {"mtt_import_value_inr": 1000000, "mtt_commencement_date": nowdate()}
		)
		frappe.get_doc(
			{
				"doctype": "Export Realization",
				"shipment": shp,
				"customer": customer,
				"export_invoice": f"_TEST-PR-{_suffix()}",
				"status": "Partially Realized",
				"currency": "USD",
				"invoice_value": 20000,
				"conversion_rate": 85,
				"amount_received": 2353,
				"amount_received_inr": 200000,
			}
		).insert(ignore_permissions=True)
		fin = get_shipment_finance(shp)
		# proceeds = max(200000 received, 20000*85=1700000 expected) - 1000000 outlay
		self.assertEqual(fin["mtt"]["net_fx_profit_inr"], 700000.0)

	def test_due_recomputes_when_switched_to_merchanting(self):
		"""Review finding #3: flipping trade type must move the realization's
		FEMA due from export+15mo to the MTT completion clock."""
		so, customer = self.make_deal()
		shp = self.make_shipment(so, customer)  # ordinary
		export_date = add_days(nowdate(), -10)
		frappe.db.set_value("Export Shipment", shp, "bl_date", export_date)

		rel = frappe.get_doc(
			{
				"doctype": "Export Realization",
				"shipment": shp,
				"customer": customer,
				"export_invoice": f"_TEST-SW-{_suffix()}",
				"status": "Awaiting Realization",
				"currency": "USD",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(getdate(rel.due_date), add_months(getdate(export_date), 15))

		commencement = add_days(nowdate(), -20)
		doc = frappe.get_doc("Export Shipment", shp)
		doc.trade_type = MERCHANTING
		doc.mtt_commencement_date = commencement
		doc.save(ignore_permissions=True)

		rel.reload()
		self.assertEqual(getdate(rel.due_date), add_months(getdate(commencement), 9))

	# ---------------------------------------------------------------- auto import facts

	def _make_po_for_row(self, so, row, supplier, rate):
		"""A submitted PO line sourcing this SO row, at the given buying rate."""
		frappe.db.set_value("Sales Order Item", row.name, "delivered_by_supplier", 1)
		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"supplier": supplier,
				"company": self.company,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 15),
				"items": [
					{
						"item_code": row.item_code,
						"qty": row.qty,
						"rate": rate,
						"schedule_date": add_days(nowdate(), 15),
						"sales_order": so.name,
						"sales_order_item": row.name,
						"delivered_by_supplier": 1,
					}
				],
			}
		).insert(ignore_permissions=True)
		po.submit()
		return po

	def _ship_lines(self, customer, lines, trade_type=MERCHANTING):
		return create_shipment(
			{"customer": customer, "mode": "Sea", "trade_type": trade_type, "items": lines}
		)["name"]

	def test_auto_import_outlay_from_single_po(self):
		"""A merchanting shipment auto-fills the outlay (Σ qty × PO rate) and the
		import-leg supplier from a single linked PO."""
		so, customer = self.make_deal(qty=10, rate=12)
		supplier = make_supplier(f"_Test EF MTT Sup {_suffix()}")
		po = self._make_po_for_row(so, so.items[0], supplier, rate=7)
		row = so.items[0]
		name = self._ship_lines(
			customer,
			[
				{
					"item_code": row.item_code,
					"qty": 10,
					"uom": row.uom,
					"sales_order": so.name,
					"so_detail": row.name,
					"purchase_order": po.name,
					"po_detail": po.items[0].name,
				}
			],
		)
		shp = frappe.get_doc("Export Shipment", name)
		self.assertTrue(shp.mtt_import_value_auto, "auto on by default for merchanting")
		self.assertEqual(flt(shp.mtt_import_value_inr), 70.0)  # 10 × 7
		self.assertEqual(shp.mtt_import_supplier, supplier)

	def test_auto_outlay_sums_but_supplier_blank_when_ambiguous(self):
		"""Several POs with different suppliers: the outlay sums across them, but the
		single-supplier field is left for manual entry (never guessed)."""
		sfx = _suffix()
		item_a = make_plain_item(f"_Test EF M2 A {sfx}")
		item_b = make_plain_item(f"_Test EF M2 B {sfx}")
		customer = make_customer(f"_Test EF M2 Cust {sfx}")
		so = book_deal(
			self.company,
			customer,
			[{"item_code": item_a, "qty": 10, "rate": 12}, {"item_code": item_b, "qty": 5, "rate": 20}],
		)
		sup1 = make_supplier(f"_Test EF M2 Sup1 {sfx}")
		sup2 = make_supplier(f"_Test EF M2 Sup2 {sfx}")
		po1 = self._make_po_for_row(so, so.items[0], sup1, rate=7)
		po2 = self._make_po_for_row(so, so.items[1], sup2, rate=9)
		name = self._ship_lines(
			customer,
			[
				{
					"item_code": so.items[0].item_code,
					"qty": 10,
					"uom": so.items[0].uom,
					"sales_order": so.name,
					"so_detail": so.items[0].name,
					"purchase_order": po1.name,
					"po_detail": po1.items[0].name,
				},
				{
					"item_code": so.items[1].item_code,
					"qty": 5,
					"uom": so.items[1].uom,
					"sales_order": so.name,
					"so_detail": so.items[1].name,
					"purchase_order": po2.name,
					"po_detail": po2.items[0].name,
				},
			],
		)
		shp = frappe.get_doc("Export Shipment", name)
		self.assertEqual(flt(shp.mtt_import_value_inr), 115.0)  # 10×7 + 5×9
		self.assertFalse(shp.mtt_import_supplier, "ambiguous supplier must not be guessed")

	def test_manual_import_outlay_overrides_auto(self):
		"""Switching auto off preserves a hand-entered outlay (never recomputed)."""
		so, customer = self.make_deal(qty=10, rate=12)
		supplier = make_supplier(f"_Test EF MTT Sup3 {_suffix()}")
		po = self._make_po_for_row(so, so.items[0], supplier, rate=7)
		row = so.items[0]
		name = self._ship_lines(
			customer,
			[
				{
					"item_code": row.item_code,
					"qty": 10,
					"uom": row.uom,
					"sales_order": so.name,
					"so_detail": row.name,
					"purchase_order": po.name,
					"po_detail": po.items[0].name,
				}
			],
		)
		shp = frappe.get_doc("Export Shipment", name)
		shp.mtt_import_value_auto = 0
		shp.mtt_import_value_inr = 5000
		shp.save(ignore_permissions=True)
		shp.reload()
		self.assertEqual(flt(shp.mtt_import_value_inr), 5000.0, "manual value must survive validate")

	def test_auto_outlay_blank_without_pos(self):
		"""A merchanting shipment whose lines have no PO yet leaves the outlay blank
		(nothing bought) rather than zero."""
		so, customer = self.make_deal()
		shp = frappe.get_doc("Export Shipment", self.make_shipment(so, customer, trade_type=MERCHANTING))
		self.assertTrue(shp.mtt_import_value_auto)
		self.assertFalse(shp.mtt_import_value_inr, "no PO → no outlay (blank/zero, not a figure)")
		facts = shp.computed_import_facts()
		self.assertEqual(facts["uncosted_lines"], 1)
		self.assertEqual(facts["costed_lines"], 0)

	def test_po_submit_resyncs_auto_outlay(self):
		"""A shipment booked BEFORE its PO exists (blank PO link) picks up the
		import outlay + supplier when the sourcing PO is later submitted — via the
		SO-line fallback at create and the PO on_submit resync."""
		so, customer = self.make_deal(qty=10, rate=12)
		name = self.make_shipment(so, customer, trade_type=MERCHANTING)  # no PO yet
		shp = frappe.get_doc("Export Shipment", name)
		self.assertFalse(shp.mtt_import_value_inr, "no sourcing PO yet → blank outlay")
		supplier = make_supplier(f"_Test EF MTT POsub {_suffix()}")
		self._make_po_for_row(so, so.items[0], supplier, rate=7)  # submit → on_submit resync
		shp.reload()
		self.assertEqual(flt(shp.mtt_import_value_inr), 70.0, "PO submit resynced the outlay")
		self.assertEqual(shp.mtt_import_supplier, supplier)

	def test_auto_supplier_cleared_when_pos_become_ambiguous(self):
		"""A single-supplier shipment that later also sources a second vendor clears
		the auto-derived supplier rather than leaving a stale guess."""
		sfx = _suffix()
		item_a = make_plain_item(f"_Test EF MC A {sfx}")
		item_b = make_plain_item(f"_Test EF MC B {sfx}")
		customer = make_customer(f"_Test EF MC Cust {sfx}")
		so = book_deal(
			self.company,
			customer,
			[{"item_code": item_a, "qty": 10, "rate": 12}, {"item_code": item_b, "qty": 5, "rate": 20}],
		)
		sup1 = make_supplier(f"_Test EF MC Sup1 {sfx}")
		sup2 = make_supplier(f"_Test EF MC Sup2 {sfx}")
		po1 = self._make_po_for_row(so, so.items[0], sup1, rate=7)
		name = self._ship_lines(
			customer,
			[
				{
					"item_code": so.items[0].item_code,
					"qty": 10,
					"uom": so.items[0].uom,
					"sales_order": so.name,
					"so_detail": so.items[0].name,
					"purchase_order": po1.name,
					"po_detail": po1.items[0].name,
				}
			],
		)
		shp = frappe.get_doc("Export Shipment", name)
		self.assertEqual(shp.mtt_import_supplier, sup1, "single supplier auto-set")
		po2 = self._make_po_for_row(so, so.items[1], sup2, rate=9)
		shp.append(
			"items",
			{
				"item_code": so.items[1].item_code,
				"qty": 5,
				"uom": so.items[1].uom,
				"sales_order": so.name,
				"so_detail": so.items[1].name,
				"purchase_order": po2.name,
				"po_detail": po2.items[0].name,
			},
		)
		shp.save(ignore_permissions=True)
		shp.reload()
		self.assertFalse(shp.mtt_import_supplier, "two suppliers now → cleared, not stale sup1")
		self.assertEqual(flt(shp.mtt_import_value_inr), 115.0)  # 10×7 + 5×9

	def test_auto_outlay_via_so_detail_fallback(self):
		"""A shipment item with a blank PO link still costs out via the SO-line
		fallback when a submitted PO already sources its SO line."""
		so, customer = self.make_deal(qty=10, rate=12)
		supplier = make_supplier(f"_Test EF MTT FB {_suffix()}")
		self._make_po_for_row(so, so.items[0], supplier, rate=7)  # PO submitted first
		row = so.items[0]
		# book WITHOUT a PO link — purchase_order/po_detail blank
		name = self._ship_lines(
			customer,
			[
				{
					"item_code": row.item_code,
					"qty": 10,
					"uom": row.uom,
					"sales_order": so.name,
					"so_detail": row.name,
				}
			],
		)
		shp = frappe.get_doc("Export Shipment", name)
		self.assertEqual(flt(shp.mtt_import_value_inr), 70.0, "derived via the so_detail fallback")
		self.assertEqual(shp.mtt_import_supplier, supplier)
		self.assertEqual(shp.computed_import_facts()["costed_lines"], 1)

	# ---------------------------------------------------------------- pure helpers

	def test_clocks_helper(self):
		self.assertTrue(is_merchanting(MERCHANTING))
		self.assertFalse(is_merchanting(EXPORT_FROM_INDIA))
		self.assertFalse(is_merchanting(None))

		ship = {
			"mtt_commencement_date": "2026-01-01",
			"mtt_import_payment_date": "2026-01-01",
			"mtt_import_value_inr": 800,
			"mtt_same_ad_bank": 1,
		}
		block = clocks(
			ship,
			completion_months=9,
			outlay_months=4,
			export_proceeds_inr=1000,
			proceeds_received=False,
			today="2026-03-01",
		)
		self.assertEqual(getdate(block["completion_due"]), getdate("2026-10-01"))
		self.assertEqual(getdate(block["outlay_due"]), getdate("2026-05-01"))
		self.assertTrue(block["outlay_open"])
		self.assertEqual(block["net_fx_profit_inr"], 200.0)
		self.assertTrue(block["same_ad_bank"])


class TestMultiCurrencyAndPoMtt(IntegrationTestCase):
	"""Multi-currency POs + PO-driven merchanting (foreign supplier → MTT flag +
	SO link → shipment auto-detects merchanting, mixing blocked)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")
		seed_document_types()
		seed_checklist_rules()

	def _foreign_supplier(self):
		return frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"_Test EF Foreign {_suffix()}",
				"supplier_group": frappe.db.get_value("Supplier Group", {}, "name"),
				"country": "China",
				"gst_category": "Overseas",
				"default_currency": "USD",
			}
		).insert(ignore_permissions=True).name

	def _deal(self, items):
		sfx = _suffix()
		customer = make_customer(f"_Test EF MC Cust {sfx}")
		return book_deal(self.company, customer, items), customer

	def test_multi_currency_po_converts_to_inr(self):
		item = make_plain_item(f"_Test EF MC Item {_suffix()}")
		so, _c = self._deal([{"item_code": item, "qty": 10, "rate": 12}])
		supplier = self._foreign_supplier()
		company_currency = frappe.db.get_value("Company", self.company, "default_currency")
		alt = "EUR" if company_currency != "EUR" else "GBP"
		res = create_purchase_order_draft(
			{
				"supplier": supplier,
				"currency": alt,
				"conversion_rate": 83,
				"items": [
					{
						"item_code": item,
						"qty": 10,
						"rate": 100,
						"sales_order": so.name,
						"so_detail": so.items[0].name,
					}
				],
			}
		)
		po = frappe.get_doc("Purchase Order", res["name"])
		self.assertEqual(po.currency, alt)
		self.assertEqual(flt(po.conversion_rate), 83.0)
		self.assertEqual(flt(po.items[0].base_rate), 8300.0, "rate × conversion → company-currency base_rate")

	def test_mtt_po_requires_foreign_supplier(self):
		item = make_plain_item(f"_Test EF MC Item {_suffix()}")
		so, _c = self._deal([{"item_code": item, "qty": 10, "rate": 12}])
		domestic = make_supplier(f"_Test EF Dom {_suffix()}")
		with self.assertRaises(frappe.ValidationError):
			create_purchase_order_draft(
				{
					"supplier": domestic,
					"merchanting_trade": 1,
					"items": [
						{
							"item_code": item,
							"qty": 10,
							"rate": 100,
							"sales_order": so.name,
							"so_detail": so.items[0].name,
						}
					],
				}
			)

	def test_mtt_po_requires_so_link(self):
		free = make_plain_item(f"_Test EF Free {_suffix()}")
		foreign = self._foreign_supplier()
		with self.assertRaises(frappe.ValidationError):
			create_purchase_order_draft(
				{
					"supplier": foreign,
					"merchanting_trade": 1,
					"currency": "USD",
					"conversion_rate": 83,
					"items": [{"item_code": free, "qty": 5, "rate": 100}],
				}
			)

	def test_mtt_po_sets_flag_and_drops_domestic_scheme(self):
		item = make_plain_item(f"_Test EF MC Item {_suffix()}")
		so, _c = self._deal([{"item_code": item, "qty": 10, "rate": 12}])
		foreign = self._foreign_supplier()
		res = create_purchase_order_draft(
			{
				"supplier": foreign,
				"merchanting_trade": 1,
				"merchant_export_scheme": 1,
				"currency": "USD",
				"conversion_rate": 83,
				"items": [
					{
						"item_code": item,
						"qty": 10,
						"rate": 100,
						"sales_order": so.name,
						"so_detail": so.items[0].name,
					}
				],
			}
		)
		po = frappe.get_doc("Purchase Order", res["name"])
		self.assertEqual(po.merchanting_trade, 1)
		self.assertEqual(po.merchant_export_scheme, 0, "MTT can't use the 0.1% domestic scheme")
		# overseas supplier → no GST autofills on the PO
		self.assertEqual(flt(po.total_taxes_and_charges), 0.0)

	def test_shipment_enforces_merchanting_from_po(self):
		item = make_plain_item(f"_Test EF MC Item {_suffix()}")
		so, customer = self._deal([{"item_code": item, "qty": 10, "rate": 12}])
		foreign = self._foreign_supplier()
		create_purchase_order_draft(
			{
				"supplier": foreign,
				"merchanting_trade": 1,
				"currency": "USD",
				"conversion_rate": 83,
				"submit": 1,
				"items": [
					{
						"item_code": item,
						"qty": 10,
						"rate": 100,
						"sales_order": so.name,
						"so_detail": so.items[0].name,
					}
				],
			}
		)
		# booked as Export-from-India, but every line is bought on an MTT PO
		shp = create_shipment(
			{
				"customer": customer,
				"mode": "Sea",
				"trade_type": EXPORT_FROM_INDIA,
				"items": [
					{
						"item_code": item,
						"qty": 10,
						"uom": so.items[0].uom,
						"sales_order": so.name,
						"so_detail": so.items[0].name,
					}
				],
			}
		)["name"]
		self.assertEqual(
			frappe.db.get_value("Export Shipment", shp, "trade_type"),
			MERCHANTING,
			"trade type is enforced from the sourcing POs",
		)

	def test_shipment_blocks_mtt_india_mix(self):
		sfx = _suffix()
		item_a = make_plain_item(f"_Test EF Mix A {sfx}")
		item_b = make_plain_item(f"_Test EF Mix B {sfx}")
		so, customer = self._deal(
			[{"item_code": item_a, "qty": 10, "rate": 12}, {"item_code": item_b, "qty": 10, "rate": 12}]
		)
		foreign = self._foreign_supplier()
		domestic = make_supplier(f"_Test EF Mix Dom {sfx}")
		create_purchase_order_draft(
			{
				"supplier": foreign,
				"merchanting_trade": 1,
				"currency": "USD",
				"conversion_rate": 83,
				"submit": 1,
				"items": [
					{
						"item_code": item_a,
						"qty": 10,
						"rate": 100,
						"sales_order": so.name,
						"so_detail": so.items[0].name,
					}
				],
			}
		)
		create_purchase_order_draft(
			{
				"supplier": domestic,
				"currency": "INR",
				"conversion_rate": 1,
				"submit": 1,
				"items": [
					{
						"item_code": item_b,
						"qty": 10,
						"rate": 50,
						"sales_order": so.name,
						"so_detail": so.items[1].name,
					}
				],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			create_shipment(
				{
					"customer": customer,
					"mode": "Sea",
					"items": [
						{
							"item_code": item_a,
							"qty": 10,
							"uom": so.items[0].uom,
							"sales_order": so.name,
							"so_detail": so.items[0].name,
						},
						{
							"item_code": item_b,
							"qty": 10,
							"uom": so.items[1].uom,
							"sales_order": so.name,
							"so_detail": so.items[1].name,
						},
					],
				}
			)

	def test_shipment_blocks_mtt_mix_with_null_country_domestic(self):
		# a domestic supplier with NO country (as MIS import / desk can produce)
		# must still count as the India leg — the mix is blocked, not coerced
		sfx = _suffix()
		item_a = make_plain_item(f"_Test EF NC A {sfx}")
		item_b = make_plain_item(f"_Test EF NC B {sfx}")
		so, customer = self._deal(
			[{"item_code": item_a, "qty": 10, "rate": 12}, {"item_code": item_b, "qty": 10, "rate": 12}]
		)
		foreign = self._foreign_supplier()
		domestic = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"_Test EF NC Dom {sfx}",
				"supplier_group": frappe.db.get_value("Supplier Group", {}, "name"),
			}
		).insert(ignore_permissions=True).name
		frappe.db.set_value("Supplier", domestic, "country", None, update_modified=False)
		create_purchase_order_draft(
			{
				"supplier": foreign,
				"merchanting_trade": 1,
				"currency": "USD",
				"conversion_rate": 83,
				"submit": 1,
				"items": [
					{
						"item_code": item_a,
						"qty": 10,
						"rate": 100,
						"sales_order": so.name,
						"so_detail": so.items[0].name,
					}
				],
			}
		)
		create_purchase_order_draft(
			{
				"supplier": domestic,
				"submit": 1,
				"items": [
					{
						"item_code": item_b,
						"qty": 10,
						"rate": 50,
						"sales_order": so.name,
						"so_detail": so.items[1].name,
					}
				],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			create_shipment(
				{
					"customer": customer,
					"mode": "Sea",
					"items": [
						{
							"item_code": item_a,
							"qty": 10,
							"uom": so.items[0].uom,
							"sales_order": so.name,
							"so_detail": so.items[0].name,
						},
						{
							"item_code": item_b,
							"qty": 10,
							"uom": so.items[1].uom,
							"sales_order": so.name,
							"so_detail": so.items[1].name,
						},
					],
				}
			)

	def test_mtt_po_drops_scheme_even_when_supplier_defaults_it(self):
		# before_insert must not re-enable the 0.1% domestic scheme on an MTT PO
		# just because the (foreign) supplier carries default_merchant_export_scheme
		item = make_plain_item(f"_Test EF FS Item {_suffix()}")
		so, _c = self._deal([{"item_code": item, "qty": 10, "rate": 12}])
		foreign = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"_Test EF FS Sup {_suffix()}",
				"supplier_group": frappe.db.get_value("Supplier Group", {}, "name"),
				"country": "China",
				"default_merchant_export_scheme": 1,
			}
		).insert(ignore_permissions=True).name
		res = create_purchase_order_draft(
			{
				"supplier": foreign,
				"merchanting_trade": 1,
				"currency": "USD",
				"conversion_rate": 83,
				"items": [
					{
						"item_code": item,
						"qty": 10,
						"rate": 100,
						"sales_order": so.name,
						"so_detail": so.items[0].name,
					}
				],
			}
		)
		po = frappe.get_doc("Purchase Order", res["name"])
		self.assertEqual(po.merchanting_trade, 1)
		self.assertEqual(po.merchant_export_scheme, 0)

	def test_shipment_before_mtt_po_flips_on_submit(self):
		# book the shipment BEFORE its merchanting PO exists -> stays export; once
		# the MTT PO submits and links backfill, the shipment flips to merchanting
		item = make_plain_item(f"_Test EF SB Item {_suffix()}")
		so, customer = self._deal([{"item_code": item, "qty": 10, "rate": 12}])
		shp = create_shipment(
			{
				"customer": customer,
				"mode": "Sea",
				"items": [
					{
						"item_code": item,
						"qty": 10,
						"uom": so.items[0].uom,
						"sales_order": so.name,
						"so_detail": so.items[0].name,
					}
				],
			}
		)["name"]
		self.assertEqual(
			frappe.db.get_value("Export Shipment", shp, "trade_type"), EXPORT_FROM_INDIA
		)
		foreign = self._foreign_supplier()
		create_purchase_order_draft(
			{
				"supplier": foreign,
				"merchanting_trade": 1,
				"currency": "USD",
				"conversion_rate": 83,
				"submit": 1,
				"items": [
					{
						"item_code": item,
						"qty": 10,
						"rate": 100,
						"sales_order": so.name,
						"so_detail": so.items[0].name,
					}
				],
			}
		)
		self.assertEqual(
			frappe.db.get_value("Export Shipment", shp, "trade_type"),
			MERCHANTING,
			"PO on_submit re-derives the booked-first shipment's trade type",
		)
