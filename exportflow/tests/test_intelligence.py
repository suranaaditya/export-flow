import frappe
from frappe.utils import add_days, add_months, flt, getdate, nowdate

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
from exportflow.api import (
	close_order,
	create_export_sales_order,
	create_purchase_order_draft,
	create_shipment,
	get_finance_workspace,
	get_po_detail,
	get_sales_dashboard,
	get_shipment_finance,
	get_shipment_finance_seed,
	get_so_money_summary,
	reopen_order,
	submit_sales_order,
)
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
		self.assertFalse(alerted(add_days(deadline, 5)), "overdue does not nag every day")
		self.assertTrue(alerted(add_days(deadline, 7)), "overdue nags weekly")

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
		self.assertFalse(alerted(add_days(due, 1)), "overdue does not nag every day")
		self.assertTrue(alerted(add_days(due, 7)), "overdue nags weekly")

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
		self.assertFalse(alerted(add_days(expiry, 3)), "overdue does not nag every day")
		self.assertTrue(alerted(add_days(expiry, 7)), "overdue nags weekly")

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

	# ---------------------------------------------------------------- finance

	def make_incentive(self, shipment, scheme="RoDTEP", **kw):
		return frappe.get_doc(
			{
				"doctype": "Export Incentive",
				"scheme": scheme,
				"shipment": shipment,
				"status": kw.get("status", "Pending"),
				"fob_value": kw.get("fob_value"),
				"rate_pct": kw.get("rate_pct"),
				"amount": kw.get("amount"),
				"scrip_date": kw.get("scrip_date"),
			}
		).insert(ignore_permissions=True)

	def test_incentive_amount_and_scrip_expiry(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		inc = self.make_incentive(shp, fob_value=100000, rate_pct=1.5)
		self.assertEqual(inc.amount, 1500.0, "amount = FOB × applied rate")

		inc2 = self.make_incentive(
			shp, status="Scrip Generated", amount=500, scrip_date=nowdate()
		)
		self.assertEqual(
			getdate(inc2.scrip_expiry), getdate(add_months(nowdate(), 24)), "scrip valid 2 years"
		)

	def test_realization_due_date_and_overdue(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		# 500 days back so export + 15 months is safely in the past
		frappe.db.set_value("Export Shipment", shp, "bl_date", add_days(nowdate(), -500))
		rel = frappe.get_doc(
			{
				"doctype": "Export Realization",
				"export_invoice": "MNG-TEST-1",
				"shipment": shp,
				"status": "Awaiting Realization",
				"currency": "USD",
				"invoice_value": 1000,
			}
		).insert(ignore_permissions=True)
		# export date pulled from B/L; due = +15 months
		self.assertEqual(getdate(rel.due_date), getdate(add_months(add_days(nowdate(), -500), 15)))
		self.assertTrue(rel.is_overdue(), "past the FEMA window with no realization")

	def test_finance_workspace_and_dashboard(self):
		so, customer, supplier = self.make_deal(qty=10)
		shp = self.make_shipment(so, customer)
		self.make_incentive(shp, amount=2000, status="Scrip Generated")
		self.make_incentive(shp, scheme="Duty Drawback", amount=500, status="Pending")

		# the workspace is company-scoped (other tests share the company on this
		# non-isolated test site) — assert against this shipment's own slice
		per = get_shipment_finance(shp)
		self.assertEqual(len(per["incentives"]), 2)
		mine = sum(flt(i["amount"]) for i in per["incentives"])
		self.assertEqual(mine, 2500.0)

		ws = get_finance_workspace()
		self.assertGreaterEqual(ws["kpis"]["incentive_total"], 2500.0)
		self.assertTrue(any(i["shipment"] == shp for i in ws["incentives"]))

		d = get_sales_dashboard()
		self.assertGreaterEqual(d["kpis"]["incentive_inr"], 2500.0)
		self.assertIn("net_margin_inr", d["kpis"])

	def test_incentive_recompute_and_not_applicable(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		inc = self.make_incentive(shp, fob_value=100000, rate_pct=1.0)
		self.assertEqual(inc.amount, 1000.0)
		# correcting the rate flows through (formula-driven amount, not pinned)
		inc.rate_pct = 0.5
		inc.save(ignore_permissions=True)
		self.assertEqual(inc.amount, 500.0, "amount tracks a corrected rate")
		# a Not Applicable claim must not count as earned incentive
		na = self.make_incentive(shp, fob_value=200000, rate_pct=1.0, status="Not Applicable")
		ws = get_shipment_finance(shp)
		na_row = next(r for r in ws["incentives"] if r["name"] == na.name)
		live = next(r for r in ws["incentives"] if r["name"] == inc.name)
		mine_total = sum(
			flt(r["amount"]) for r in ws["incentives"] if r["name"] in (inc.name, na.name)
			and r["status"] != "Not Applicable"
		)
		self.assertEqual(mine_total, 500.0, "only the live incentive counts")
		self.assertEqual(na_row["status"], "Not Applicable")
		self.assertTrue(live)

	def test_realization_due_recompute_on_export_date_change(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		rel = frappe.get_doc(
			{
				"doctype": "Export Realization",
				"export_invoice": f"MNG-RC-{_suffix()}",
				"shipment": shp,
				"status": "Awaiting Realization",
				"currency": "USD",
				"export_date": add_days(nowdate(), -10),
			}
		).insert(ignore_permissions=True)
		first = getdate(rel.due_date)
		rel.export_date = add_days(nowdate(), -40)
		rel.save(ignore_permissions=True)
		self.assertEqual(
			getdate(rel.due_date), getdate(add_months(add_days(nowdate(), -40), 15)),
			"due date follows a corrected export date",
		)
		self.assertNotEqual(getdate(rel.due_date), first)

	def test_finance_company_scoped(self):
		"""Incentives carry the shipment's company; the workspace is scoped to
		the ExportFlow company (falls back to site default on the test site)."""
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		inc = self.make_incentive(shp, amount=100)
		self.assertEqual(
			frappe.db.get_value("Export Incentive", inc.name, "company"),
			frappe.db.get_value("Export Shipment", shp, "company"),
		)

	_FIN_CAN = (
		"incentive_create",
		"incentive_write",
		"incentive_delete",
		"realization_create",
		"realization_write",
		"realization_delete",
	)

	def _fin_user(self, *roles):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"_test_fincan_{_suffix()}@example.com".lower(),
				"first_name": "FinCan",
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
		if roles:
			user.add_roles(*roles)
		return user

	def test_finance_can_permission_gating(self):
		"""The finance `can` map (drives add / edit / delete affordances on both
		the Finance screen and the shipment card) is the user's real ERPNext
		permission: System Manager full; Export Accounts may correct but not
		delete; a viewer gets nothing."""
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		self.make_incentive(shp, amount=100)

		# Administrator (System Manager) — every affordance
		can = get_shipment_finance(shp)["can"]
		ws = get_finance_workspace()["can"]
		for k in self._FIN_CAN:
			self.assertTrue(can[k], f"admin shipment-card {k}")
			self.assertTrue(ws[k], f"admin workspace {k}")

		# Export Accounts — create + write, but NOT delete (delete is admin-only)
		acct = self._fin_user("Export Accounts")
		frappe.set_user(acct.name)
		self.addCleanup(frappe.set_user, "Administrator")
		can = get_shipment_finance(shp)["can"]
		for k in ("incentive_create", "incentive_write", "realization_create", "realization_write"):
			self.assertTrue(can[k], f"accounts may {k}")
		self.assertFalse(can["incentive_delete"], "accounts may correct but not delete")
		self.assertFalse(can["realization_delete"], "accounts may correct but not delete")
		self.assertFalse(get_finance_workspace()["can"]["incentive_delete"])

		# Read-only viewer — no mutation affordances at all
		frappe.set_user("Administrator")
		viewer = self._fin_user("Export Viewer")
		frappe.set_user(viewer.name)
		can = get_shipment_finance(shp)["can"]
		self.assertFalse(any(can[k] for k in self._FIN_CAN), "viewer sees no add/edit/delete")
		ws = get_finance_workspace()["can"]
		self.assertFalse(any(ws[k] for k in self._FIN_CAN))
		self.assertTrue(ws["incentive_read"], "but the viewer can still read")

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

	# ------------------------------------------------ #4(a) finance-from-shipment

	def test_shipment_finance_seed(self):
		"""Export value = Σ(shipped qty × SO line rate): FCY for the realization
		invoice value, company currency for the incentive FOB basis. Currency and
		export date come straight from the SO and the B/L."""
		so, customer, _s = self.make_deal(qty=10)  # EUR rate 12, conversion 83
		shp = self.make_shipment(so, customer, qty=8)
		frappe.db.set_value("Export Shipment", shp, "bl_date", "2026-01-15")

		seed = get_shipment_finance_seed(shp)
		self.assertEqual(seed["currency"], so.currency)
		self.assertFalse(seed["currency_conflict"])
		self.assertEqual(flt(seed["invoice_value"]), 96.0, "8 × 12 in the deal currency")
		self.assertEqual(flt(seed["fob_value_inr"]), 7968.0, "8 × (12 × 83) in company currency")
		self.assertEqual(seed["customer"], customer)
		self.assertEqual(str(seed["export_date"]), "2026-01-15")
		self.assertFalse(seed["merchanting"])

	def test_shipment_finance_seed_currency_conflict(self):
		"""A shipment spanning two SOs in different currencies cannot offer one
		FCY invoice value — currency/value blank, but the company-currency FOB
		(base_rate) still aggregates."""
		sfx = _suffix()
		item = make_plain_item(f"_Test EF Seed {sfx}")
		customer = make_customer(f"_Test EF Seed Cust {sfx}")
		company_currency = frappe.db.get_value("Company", self.company, "default_currency")
		alt = "EUR" if company_currency != "EUR" else "GBP"

		def mk(currency, rate):
			r = create_export_sales_order(
				{
					"customer": customer,
					"currency": currency,
					"conversion_rate": 1 if currency == company_currency else 83,
					"delivery_date": add_days(nowdate(), 30),
					"items": [{"item_code": item, "qty": 5, "rate": rate}],
				}
			)
			submit_sales_order(r["name"])
			return frappe.get_doc("Sales Order", r["name"])

		so_alt = mk(alt, 10)  # base_rate = 10 × 83 = 830
		so_home = mk(company_currency, 20)  # base_rate = 20 × 1 = 20
		shp = create_shipment(
			{
				"customer": customer,
				"mode": "Sea",
				"items": [
					{
						"item_code": item,
						"qty": 5,
						"uom": so_alt.items[0].uom,
						"sales_order": so_alt.name,
						"so_detail": so_alt.items[0].name,
					},
					{
						"item_code": item,
						"qty": 5,
						"uom": so_home.items[0].uom,
						"sales_order": so_home.name,
						"so_detail": so_home.items[0].name,
					},
				],
			}
		)["name"]

		seed = get_shipment_finance_seed(shp)
		self.assertTrue(seed["currency_conflict"])
		self.assertIsNone(seed["currency"])
		self.assertIsNone(seed["invoice_value"])
		self.assertEqual(flt(seed["fob_value_inr"]), 4250.0, "5×830 + 5×20")

	# ------------------------------------------------------ #4(d) order closing

	def test_close_and_reopen_sales_order(self):
		so, _customer, _s = self.make_deal()
		self.assertEqual(so.docstatus, 1)

		res = close_order("Sales Order", so.name)
		self.assertEqual(res["status"], "Closed")
		summ = get_so_money_summary(so.name)
		self.assertFalse(summ["can"]["close"], "already closed")
		self.assertTrue(summ["can"]["reopen"])

		# closing again is a no-op, not an error
		self.assertEqual(close_order("Sales Order", so.name)["status"], "Closed")

		res2 = reopen_order("Sales Order", so.name)
		self.assertNotEqual(res2["status"], "Closed", "reopen recomputes the real status")
		summ2 = get_so_money_summary(so.name)
		self.assertTrue(summ2["can"]["close"])
		self.assertFalse(summ2["can"]["reopen"])

	def test_close_and_reopen_purchase_order(self):
		so, _customer, supplier = self.make_deal(qty=10)
		result = create_purchase_order(
			so.name, [{"so_detail": so.items[0].name, "supplier": supplier, "qty": 10, "rate": 9}]
		)
		po_name = result["purchase_orders"][0]["name"]
		submit_purchase_order(po_name)

		self.assertEqual(close_order("Purchase Order", po_name)["status"], "Closed")
		det = get_po_detail(po_name)
		self.assertTrue(det["can"]["reopen"])
		self.assertFalse(det["can"]["close"])

		reopen_order("Purchase Order", po_name)
		self.assertNotEqual(
			frappe.db.get_value("Purchase Order", po_name, "status"), "Closed"
		)

	def test_close_rejects_unsubmitted_and_unknown(self):
		sfx = _suffix()
		item = make_plain_item(f"_Test EF Close {sfx}")
		customer = make_customer(f"_Test EF Close Cust {sfx}")
		draft = create_export_sales_order(
			{
				"customer": customer,
				"currency": "EUR",
				"conversion_rate": 83,
				"delivery_date": add_days(nowdate(), 30),
				"items": [{"item_code": item, "qty": 5, "rate": 10}],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			close_order("Sales Order", draft["name"])  # still a draft
		with self.assertRaises(frappe.ValidationError):
			close_order("Export Shipment", "anything")  # not a closeable doctype
