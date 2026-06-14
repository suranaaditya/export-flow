import frappe
from frappe.utils import add_days, add_months, flt, getdate, nowdate

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from exportflow.api import create_shipment, get_shipment_finance, set_shipment_milestone
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

	def test_merchanting_leo_milestone_not_blocked(self):
		"""With Shipping Bill / ADC NOC suppressed, nothing gates Let Export
		Order on a merchanting shipment."""
		so, customer = self.make_deal()
		shp = self.make_shipment(so, customer, trade_type=MERCHANTING)
		doc = frappe.get_doc("Export Shipment", shp)
		# walk up to and through Let Export Order
		for m in doc.milestones:
			set_shipment_milestone(shp, m.name, 1)
			if m.milestone == "Let Export Order":
				break
		doc.reload()
		leo = next(m for m in doc.milestones if m.milestone == "Let Export Order")
		self.assertTrue(leo.completed, "LEO must complete — no blocking docs on merchanting")

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

	def test_switch_with_progressed_blocking_unblocks_leo(self):
		"""Review finding #1: switching a shipment whose Shipping Bill was already
		progressed (so it is relinquished, not deleted) must still drop its
		milestone gate — else Let Export Order is permanently blocked."""
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

		self.assertEqual(
			milestone_blockers(shp, "Let Export Order"), [], "no suppressed doc may gate LEO"
		)
		doc.reload()
		for m in doc.milestones:
			set_shipment_milestone(shp, m.name, 1)
			if m.milestone == "Let Export Order":
				break
		doc.reload()
		leo = next(m for m in doc.milestones if m.milestone == "Let Export Order")
		self.assertTrue(leo.completed)

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
