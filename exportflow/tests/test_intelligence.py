import frappe
from frappe.utils import add_days, nowdate

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from exportflow.api import (
	add_document_instance,
	create_purchase_order,
	get_dashboard,
	get_shipment_defaults,
	set_shipment_milestone,
	submit_purchase_order,
	update_document_instance,
)
from exportflow.api import create_purchase_order_draft, create_shipment, get_sales_dashboard
from exportflow.setup import seed_checklist_rules, seed_document_types
from exportflow.tasks import (
	send_compliance_alerts,
	send_document_due_alerts,
	send_email_digest,
	send_gst_alerts,
)
from exportflow.tests.test_documents import instance_of
from exportflow.tests.test_dropship import _suffix, make_customer, make_supplier
from exportflow.tests.test_logistics import book_deal, make_plain_item
from exportflow.tests.test_money import make_pfi


class TestIntelligence(IntegrationTestCase):
	"""Phase 5: scheduler alerts, shipment defaults, the dashboard payload."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")
		seed_document_types()
		seed_checklist_rules()

	def make_deal(self, qty=10):
		sfx = _suffix()
		item = make_plain_item(f"_Test EF I Item {sfx}")
		customer = make_customer(f"_Test EF I Customer {sfx}")
		supplier = make_supplier(f"_Test EF I Supplier {sfx}")
		so = book_deal(self.company, customer, [{"item_code": item, "qty": qty, "rate": 12}])
		return so, customer, supplier

	def make_shipment(self, so, customer, qty=10, mode="Sea", incoterm=None, lc=None):
		row = so.items[0]
		return create_shipment(
			{
				"customer": customer,
				"mode": mode,
				"incoterm": incoterm,
				"letter_of_credit": lc,
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

	def make_lc(self, so, requirements=None):
		return frappe.get_doc(
			{
				"doctype": "Letter of Credit",
				"sales_order": so.name,
				"customer": so.customer,
				"lc_number": f"LC-TEST-{_suffix()}",
				"amount": 1000,
				"currency": so.currency,
				"expiry_date": add_days(nowdate(), 90),
				"latest_shipment_date": add_days(nowdate(), 60),
				"document_requirements": requirements or [],
			}
		).insert(ignore_permissions=True)

	def ship_everything(self, shp: str):
		"""Walk a sea shipment to Shipped on Board (export milestone), clearing
		the LEO blockers on the way."""
		update_document_instance(instance_of(shp, "Shipping Bill"), {"status": "Sent/Filed"})
		update_document_instance(instance_of(shp, "ADC NOC"), {"status": "Received"})
		doc = frappe.get_doc("Export Shipment", shp)
		for row in doc.milestones[:7]:  # … up to and including Shipped on Board
			set_shipment_milestone(shp, row.name, 1)

	def make_scheme_po(self, qty=10, invoice_date=None):
		so, customer, supplier = self.make_deal(qty=qty)
		result = create_purchase_order(
			so.name, [{"so_detail": so.items[0].name, "supplier": supplier, "qty": qty, "rate": 9}]
		)
		po_name = result["purchase_orders"][0]["name"]
		po = frappe.get_doc("Purchase Order", po_name)
		po.supplier_invoice_no = "SUP-INV-ALERT"
		po.supplier_invoice_date = invoice_date or nowdate()
		po.save()
		return so, customer, po_name

	# ---------------------------------------------------------------- GST alerts

	def test_gst_alert_thresholds(self):
		so, customer, po_name = self.make_scheme_po()
		self.make_shipment(so, customer, qty=10)
		submit_purchase_order(po_name)
		deadline = frappe.db.get_value("Purchase Order", po_name, "gst_export_deadline")

		def alerted(today) -> bool:
			return any(a["po"] == po_name for a in send_gst_alerts(today=today))

		self.assertFalse(alerted(add_days(deadline, -45)), "quiet outside the tiers")
		self.assertTrue(alerted(add_days(deadline, -30)))
		self.assertFalse(alerted(add_days(deadline, -20)))
		self.assertTrue(alerted(add_days(deadline, -7)))
		self.assertTrue(alerted(deadline), "deadline day alerts")
		self.assertTrue(alerted(add_days(deadline, 5)), "overdue nags daily")

	def test_gst_alert_stops_after_export(self):
		so, customer, po_name = self.make_scheme_po()
		shp = self.make_shipment(so, customer, qty=10)
		submit_purchase_order(po_name)
		deadline = frappe.db.get_value("Purchase Order", po_name, "gst_export_deadline")

		self.ship_everything(shp)
		self.assertFalse(
			any(a["po"] == po_name for a in send_gst_alerts(today=add_days(deadline, -7))),
			"the clock stops once the goods are on board",
		)

	def test_gst_alert_keeps_running_on_partial_export(self):
		so, customer, po_name = self.make_scheme_po(qty=10)
		shp1 = self.make_shipment(so, customer, qty=6)
		submit_purchase_order(po_name)
		deadline = frappe.db.get_value("Purchase Order", po_name, "gst_export_deadline")

		self.ship_everything(shp1)
		self.assertTrue(
			any(a["po"] == po_name for a in send_gst_alerts(today=add_days(deadline, -7))),
			"4 of 10 units still unshipped — keep alerting",
		)

	# ---------------------------------------------------------------- doc due alerts

	def test_document_due_alerts(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		manual = add_document_instance(shp, "Freight Invoice")["name"]
		due = add_days(nowdate(), 30)
		update_document_instance(manual, {"due_date": due})

		def alerted(today) -> bool:
			return any(a["instance"] == manual for a in send_document_due_alerts(today=today))

		self.assertFalse(alerted(add_days(due, -10)))
		self.assertTrue(alerted(add_days(due, -3)))
		self.assertTrue(alerted(add_days(due, 1)), "overdue nags daily")

		update_document_instance(manual, {"status": "Sent/Filed"})
		self.assertFalse(alerted(add_days(due, -3)), "a filed document stops alerting")

	# ---------------------------------------------------------------- compliance

	def make_compliance(self, **kwargs):
		return frappe.get_doc(
			{
				"doctype": "Compliance Record",
				"compliance_type": kwargs.get("compliance_type", "LUT"),
				"title": kwargs.get("title", f"_Test LUT {_suffix()}"),
				"status": kwargs.get("status", "Active"),
				"expiry_date": kwargs.get("expiry_date"),
				"port": kwargs.get("port"),
			}
		).insert(ignore_permissions=True)

	def test_compliance_alert_thresholds(self):
		expiry = add_days(nowdate(), 90)
		rec = self.make_compliance(expiry_date=expiry)

		def alerted(today) -> bool:
			return any(a["record"] == rec.name for a in send_compliance_alerts(today=today))

		self.assertFalse(alerted(add_days(expiry, -90)))
		self.assertTrue(alerted(add_days(expiry, -60)))
		self.assertTrue(alerted(add_days(expiry, -7)))
		self.assertTrue(alerted(add_days(expiry, 3)), "overdue nags daily")

		rec.status = "Archived"
		rec.save(ignore_permissions=True)
		self.assertFalse(alerted(add_days(expiry, -7)), "archived records are silent")

	def test_ad_code_requires_port(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_compliance(compliance_type="AD Code", title=f"_Test ADC {_suffix()}")

	# ---------------------------------------------------------------- shipment defaults

	def test_shipment_defaults_from_so(self):
		so, customer, _s = self.make_deal()
		frappe.db.set_value(
			"Sales Order", so.name, {"incoterm": "CIF", "named_place": "Jebel Ali"},
			update_modified=False,
		)
		lc = self.make_lc(so)

		defaults = get_shipment_defaults(so.name)
		self.assertEqual(defaults["customer"], customer)
		self.assertEqual(defaults["incoterm"], "CIF")
		self.assertEqual(defaults["named_place"], "Jebel Ali")
		self.assertEqual(defaults["letter_of_credit"], lc.name)
		self.assertEqual(set(defaults["so_details"]), {row.name for row in so.items})

		lc.db_set("status", "Closed")
		self.assertIsNone(
			get_shipment_defaults(so.name)["letter_of_credit"],
			"closed LCs are not offered as defaults",
		)

	# ------------------------------------------------- review-driven regressions

	def test_gst_alert_silences_despite_free_lines(self):
		"""A scheme PO mixing SO-linked cargo with free lines (packing material)
		must stop alerting once the exportable cargo has departed."""
		so, customer, supplier = self.make_deal(qty=10)
		sfx = _suffix()
		free_item = make_plain_item(f"_Test EF I Free {sfx}")
		result = create_purchase_order_draft(
			{
				"supplier": supplier,
				"merchant_export_scheme": 1,
				"items": [
					{
						"item_code": so.items[0].item_code,
						"qty": 10,
						"rate": 9,
						"sales_order": so.name,
						"so_detail": so.items[0].name,
					},
					{"item_code": free_item, "qty": 5, "rate": 100},
				],
			}
		)
		po = frappe.get_doc("Purchase Order", result["name"])
		po.supplier_invoice_no = "SUP-FREE"
		po.supplier_invoice_date = nowdate()
		po.save()
		shp = self.make_shipment(so, customer, qty=10)
		submit_purchase_order(po.name)
		deadline = frappe.db.get_value("Purchase Order", po.name, "gst_export_deadline")

		self.ship_everything(shp)
		self.assertFalse(
			any(a["po"] == po.name for a in send_gst_alerts(today=add_days(deadline, -7))),
			"free lines never ship through the app — they are not export obligations",
		)

	def test_gst_alert_silences_for_split_pos(self):
		"""One SO line sourced 6/4 from two scheme POs, shipped on one shipment:
		both clocks must stop after departure even though the shipment rows are
		claimed by whichever PO submitted first."""
		so, customer, s1 = self.make_deal(qty=10)
		s2 = make_supplier(f"_Test EF I Sup Two {_suffix()}")
		po_names = []
		for supplier, qty in ((s1, 6), (s2, 4)):
			result = create_purchase_order(
				so.name, [{"so_detail": so.items[0].name, "supplier": supplier, "qty": qty, "rate": 9}]
			)
			po = frappe.get_doc("Purchase Order", result["purchase_orders"][0]["name"])
			po.supplier_invoice_no = f"SUP-{qty}"
			po.supplier_invoice_date = nowdate()
			po.save()
			po_names.append(po.name)

		shp = self.make_shipment(so, customer, qty=10)
		for name in po_names:
			submit_purchase_order(name)
		self.ship_everything(shp)

		deadline = frappe.db.get_value("Purchase Order", po_names[0], "gst_export_deadline")
		alerts = send_gst_alerts(today=add_days(deadline, -7))
		for name in po_names:
			self.assertFalse(
				any(a["po"] == name for a in alerts),
				f"{name} must stop alerting once the SO line is fully departed",
			)

	def test_alerts_create_notification_logs_with_dedup(self):
		so, customer, po_name = self.make_scheme_po()
		self.make_shipment(so, customer, qty=10)
		submit_purchase_order(po_name)
		deadline = frappe.db.get_value("Purchase Order", po_name, "gst_export_deadline")

		mine = [a for a in send_gst_alerts(today=add_days(deadline, -30)) if a["po"] == po_name]
		self.assertTrue(mine)
		self.assertTrue(
			frappe.db.exists(
				"Notification Log", {"document_name": po_name, "subject": mine[0]["subject"]}
			),
			"the alert must land in the in-app feed",
		)
		count = frappe.db.count("Notification Log", {"document_name": po_name})
		send_gst_alerts(today=add_days(deadline, -30))
		self.assertEqual(
			frappe.db.count("Notification Log", {"document_name": po_name}),
			count,
			"same-day re-run must not duplicate",
		)

	def test_email_digest_gated_by_settings(self):
		sfx = _suffix()
		frappe.get_doc(
			{
				"doctype": "User",
				"email": f"_test_digest_{sfx}@example.com".lower(),
				"first_name": "Digest",
				"user_type": "System User",
				"roles": [{"role": "Export Admin"}],
			}
		).insert(ignore_permissions=True)

		frappe.db.set_single_value("ExportFlow Settings", "email_digest_enabled", 0)
		self.assertIsNone(send_email_digest([{"subject": "test alert"}]), "off by default")

		frappe.db.set_single_value("ExportFlow Settings", "email_digest_enabled", 1)
		digest = send_email_digest([{"subject": "test alert"}])
		self.assertTrue(digest, "enabled digest composes")
		self.assertIn("test alert", digest["lines"])
		self.assertTrue(any("_test_digest_" in r for r in digest["recipients"]))
		self.assertIsNone(send_email_digest([]), "no alerts, no mail")

	def test_dashboard_lc_at_risk_counts_lcs_not_entries(self):
		so, _customer, _s = self.make_deal()
		lc = self.make_lc(so)
		# both LC dates inside 14 days → still ONE at-risk LC
		lc.db_set("latest_shipment_date", add_days(nowdate(), 5))
		lc.db_set("expiry_date", add_days(nowdate(), 10))

		d = get_dashboard()
		lc_rows = [r for r in d["deadlines"] if r["kind"] == "lc" and r["ref"] == lc.lc_number]
		self.assertEqual(len(lc_rows), 2, "both dates feed the deadline list")
		self.assertGreaterEqual(d["kpis"]["lc_at_risk"], 1)
		mine_at_risk = len({r["route"] for r in lc_rows})
		self.assertEqual(mine_at_risk, 1, "one LC, however many of its dates are near")

	def test_dashboard_in_transit_chip(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		self.ship_everything(shp)

		d = get_dashboard()
		mine = next((s for s in d["shipments"] if s["name"] == shp), None)
		if mine:  # the live table is capped at 8 — the KPI is the hard assert
			self.assertEqual(mine["chip"], "In transit")
			self.assertEqual(mine["tone"], "ok")
		self.assertGreaterEqual(d["kpis"]["in_transit"], 1)

	def test_dashboard_permission_gating(self):
		sfx = _suffix()
		bare = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"_test_bare_{sfx}@example.com".lower(),
				"first_name": "Bare",
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
		frappe.set_user(bare.name)
		self.addCleanup(frappe.set_user, "Administrator")

		d = get_dashboard()
		self.assertEqual(d["kpis"], {}, "no roles, no numbers")
		self.assertEqual(d["shipments"], [])
		self.assertEqual(d["deadlines"], [])
		self.assertEqual(d["documents"], [])
		self.assertEqual(d["pfis"], [])
		self.assertFalse(any(d["can"].values()))

	def test_sales_dashboard(self):
		so, customer, supplier = self.make_deal(qty=10)
		result = create_purchase_order(
			so.name, [{"so_detail": so.items[0].name, "supplier": supplier, "qty": 10, "rate": 9}]
		)
		submit_purchase_order(result["purchase_orders"][0]["name"])

		d = get_sales_dashboard()
		self.assertGreaterEqual(d["kpis"]["export_value_inr"], 1)
		self.assertGreaterEqual(d["kpis"]["order_count"], 1)
		self.assertIn("gross_margin_inr", d["kpis"], "procurement present → margin computed")
		self.assertTrue(any(c["customer"] for c in d["by_customer"]))
		self.assertTrue(d["can"]["so"])
		# export value carries the deal currency breakdown
		self.assertTrue(d["kpis"]["export_value_by_currency"])

	def test_sales_dashboard_permission_gated(self):
		sfx = _suffix()
		bare = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"_test_sbare_{sfx}@example.com".lower(),
				"first_name": "SBare",
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
		frappe.set_user(bare.name)
		self.addCleanup(frappe.set_user, "Administrator")
		d = get_sales_dashboard()
		self.assertFalse(d["can"]["so"])
		self.assertEqual(d["kpis"], {})

	# ---------------------------------------------------------------- dashboard

	def test_dashboard_payload(self):
		so, customer, po_name = self.make_scheme_po()
		shp = self.make_shipment(so, customer, qty=10)
		submit_purchase_order(po_name)
		# pull the GST deadline inside the dashboard's 30-day window
		po = frappe.get_doc("Purchase Order", po_name)
		po.supplier_invoice_date = add_days(nowdate(), -70)
		po.save()
		pfi = make_pfi(so, amount=5000)
		pfi.mark_sent()

		d = get_dashboard()

		self.assertGreaterEqual(d["kpis"]["live_shipments"], 1)
		self.assertGreaterEqual(d["kpis"]["docs_pending"], 1)
		self.assertGreaterEqual(d["kpis"]["docs_blocking"], 1, "ADC NOC + Shipping Bill pending")

		mine = next((s for s in d["shipments"] if s["name"] == shp), None)
		self.assertTrue(mine, "the new shipment shows in the live table")
		self.assertGreater(mine["docs_total"], 0)
		self.assertEqual(mine["milestones_total"], 9)
		self.assertEqual(mine["tone"], "pend")

		self.assertTrue(
			any(row["kind"] == "gst" and row["ref"] == po_name for row in d["deadlines"]),
			"the 20-day GST clock makes the deadline feed",
		)
		self.assertTrue(any(p["name"] == pfi.name for p in d["pfis"]))
		self.assertTrue(
			any(r["currency"] == pfi.currency and r["amount"] >= 5000 for r in d["kpis"]["receivable"])
		)
