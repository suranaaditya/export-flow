import frappe
from frappe.utils import add_days, add_months, getdate, nowdate

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
