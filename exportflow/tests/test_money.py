import frappe
from frappe.utils import add_days, flt, nowdate

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from exportflow.api import (
	create_export_sales_order,
	get_so_money_summary,
	pfi_set_status,
	submit_sales_order,
)
from exportflow.tasks import send_lc_alerts
from exportflow.tests.test_dropship import (
	_suffix,
	make_customer,
	make_dropship_item,
	make_dropship_so,
	make_supplier,
)


def make_money_so(company: str):
	"""SO worth 1500 in deal currency (100×10 + 50×10), conversion rate 83."""
	sfx = _suffix()
	supplier = make_supplier(f"_Test EF Supplier M {sfx}")
	item_a = make_dropship_item(f"_Test EF Item M1 {sfx}", supplier, company)
	item_b = make_dropship_item(f"_Test EF Item M2 {sfx}", supplier, company)
	customer = make_customer(f"_Test EF Customer M {sfx}")
	so = make_dropship_so(
		customer,
		company,
		[{"item_code": item_a, "qty": 100, "rate": 10}, {"item_code": item_b, "qty": 50, "rate": 10}],
	)
	return so, customer


def make_pfi(so, percentage=None, amount=None, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Pro Forma Invoice",
			"sales_order": so.name,
			"pfi_date": nowdate(),
			"basis": "Percentage of SO" if percentage is not None else "Manual amount",
			"percentage": percentage,
			"amount": amount,
			"stage_description": kwargs.get("stage_description", "30% advance"),
			"expected_payment_method": kwargs.get("expected_payment_method", "Wire Transfer"),
		}
	).insert(ignore_permissions=True)
	return doc


def make_receive_payment(company: str, customer: str, base_amount: float, pfi_name: str):
	"""Incoming payment in company currency against the PFI."""
	paid_from = frappe.db.get_value("Company", company, "default_receivable_account")
	paid_to = frappe.db.get_value("Company", company, "default_cash_account")
	pe = frappe.get_doc(
		{
			"doctype": "Payment Entry",
			"payment_type": "Receive",
			# v16 PE defaults mode_of_payment to "Bank", which has no standard record
			"mode_of_payment": "Wire Transfer",
			"company": company,
			"posting_date": nowdate(),
			"party_type": "Customer",
			"party": customer,
			"paid_from": paid_from,
			"paid_to": paid_to,
			"paid_amount": base_amount,
			"received_amount": base_amount,
			"source_exchange_rate": 1,
			"target_exchange_rate": 1,
			"reference_no": f"TT-{_suffix()}",
			"reference_date": nowdate(),
			"pro_forma_invoice": pfi_name,
		}
	).insert(ignore_permissions=True)
	pe.submit()
	return pe


class TestMoneyFlow(IntegrationTestCase):
	"""Spec §3.2/§4.5: PFI amounts, payment roll-up, SO summary, LC alerts."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")

	def test_pfi_percentage_amount(self):
		so, _customer = make_money_so(self.company)
		pfi = make_pfi(so, percentage=30)
		self.assertEqual(flt(pfi.amount), 450.0, "30% of a 1500 SO must be 450")
		self.assertEqual(pfi.currency, so.currency, "PFI settles in the deal currency")
		self.assertEqual(flt(pfi.conversion_rate), 83.0, "Rate defaults from the SO")
		self.assertEqual(pfi.status, "Draft")

	def test_pfi_manual_amount_and_send(self):
		so, _customer = make_money_so(self.company)
		pfi = make_pfi(so, amount=500, stage_description="Fixed advance")
		self.assertEqual(flt(pfi.amount), 500.0)
		pfi_set_status(pfi.name, "sent")
		pfi.reload()
		self.assertEqual(pfi.status, "Sent")

	def test_payment_rollup_partial_full_and_cancel(self):
		so, customer = make_money_so(self.company)
		pfi = make_pfi(so, percentage=30)  # 450 in deal currency, rate 83
		pfi_set_status(pfi.name, "sent")
		pfi.reload()

		# 8300 company currency -> 100 deal currency
		pe1 = make_receive_payment(self.company, customer, 8300, pfi.name)
		pfi.reload()
		self.assertEqual(pfi.status, "Partially Paid")
		self.assertEqual(flt(pfi.paid_amount), 100.0)

		# remaining 350 deal currency -> 29050 company currency
		pe2 = make_receive_payment(self.company, customer, 29050, pfi.name)
		pfi.reload()
		self.assertEqual(pfi.status, "Paid")
		self.assertEqual(flt(pfi.paid_amount), 450.0)

		pe2.cancel()
		pfi.reload()
		self.assertEqual(pfi.status, "Partially Paid")
		self.assertEqual(flt(pfi.paid_amount), 100.0)

		pe1.cancel()
		pfi.reload()
		self.assertEqual(pfi.status, "Sent", "Fully unwound payments leave a Sent PFI")
		self.assertEqual(flt(pfi.paid_amount), 0.0)

	def test_unwound_draft_pfi_returns_to_draft(self):
		"""A PFI that was never marked Sent must not be fabricated into Sent
		by a payment landing and then being cancelled."""
		so, customer = make_money_so(self.company)
		pfi = make_pfi(so, percentage=30)
		self.assertEqual(pfi.status, "Draft")

		pe = make_receive_payment(self.company, customer, 8300, pfi.name)
		pfi.reload()
		self.assertEqual(pfi.status, "Partially Paid")

		pe.cancel()
		pfi.reload()
		self.assertEqual(pfi.status, "Draft", "Never-sent PFIs must unwind to Draft, not Sent")

	def test_settlement_tolerance_absorbs_fx_drift(self):
		"""A wire credited at a slightly different bank rate still settles the
		PFI (0.5% relative tolerance)."""
		so, customer = make_money_so(self.company)
		pfi = make_pfi(so, percentage=30)  # 450 deal currency @ rate 83 = 37350
		# bank credited ~0.3% short: 37240 base -> 448.67 deal currency
		make_receive_payment(self.company, customer, 37240, pfi.name)
		pfi.reload()
		self.assertEqual(pfi.status, "Paid", "Sub-tolerance FX drift must still settle")

	def test_pfi_requires_submitted_so(self):
		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Supplier DS {sfx}")
		item = make_dropship_item(f"_Test EF Item DS {sfx}", supplier, self.company)
		customer = make_customer(f"_Test EF Customer DS {sfx}")
		draft_so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": customer,
				"company": self.company,
				"transaction_date": nowdate(),
				"delivery_date": add_days(nowdate(), 30),
				"order_type": "Sales",
				"currency": "EUR" if frappe.db.get_value("Company", self.company, "default_currency") != "EUR" else "USD",
				"conversion_rate": 83.0,
				"items": [{"item_code": item, "qty": 10, "rate": 10, "delivered_by_supplier": 1}],
			}
		).insert(ignore_permissions=True)  # NOT submitted
		with self.assertRaises(frappe.ValidationError):
			make_pfi(draft_so, percentage=10)

	def test_payment_party_must_match_pfi_customer(self):
		so, _customer = make_money_so(self.company)
		other = make_customer(f"_Test EF Other Customer {_suffix()}")
		pfi = make_pfi(so, percentage=10)
		with self.assertRaises(frappe.ValidationError):
			make_receive_payment(self.company, other, 1000, pfi.name)

	def test_pfi_cancel_blocked_with_payments(self):
		so, customer = make_money_so(self.company)
		pfi = make_pfi(so, percentage=30)
		make_receive_payment(self.company, customer, 8300, pfi.name)
		pfi.reload()
		with self.assertRaises(frappe.ValidationError):
			pfi_set_status(pfi.name, "cancel")

	def test_so_money_summary(self):
		so, customer = make_money_so(self.company)
		pfi_a = make_pfi(so, percentage=30)  # 450
		make_pfi(so, amount=200, stage_description="Second stage")  # 200
		cancelled = make_pfi(so, amount=999, stage_description="Cancelled stage")
		pfi_set_status(cancelled.name, "cancel")

		make_receive_payment(self.company, customer, 8300, pfi_a.name)  # 100 received

		data = get_so_money_summary(so.name)
		self.assertEqual(flt(data["summary"]["so_value"]), 1500.0)
		self.assertEqual(flt(data["summary"]["raised"]), 650.0, "Cancelled PFIs do not count")
		self.assertEqual(flt(data["summary"]["received"]), 100.0)
		self.assertEqual(flt(data["summary"]["balance"]), 1400.0)
		self.assertEqual(len(data["pfis"]), 3)

	def make_lc(self, so, **kwargs):
		return frappe.get_doc(
			{
				"doctype": "Letter of Credit",
				"sales_order": so.name,
				"lc_number": f"LC-TEST-{_suffix()}",
				"issuing_bank": "Emirates NBD",
				"amount": 1500,
				"issue_date": nowdate(),
				"expiry_date": kwargs.get("expiry_date", add_days(nowdate(), 40)),
				"latest_shipment_date": kwargs.get("latest_shipment_date", add_days(nowdate(), 30)),
				"status": kwargs.get("status", "Active"),
			}
		).insert(ignore_permissions=True)

	def test_lc_validation(self):
		so, _customer = make_money_so(self.company)
		lc = self.make_lc(so)
		self.assertEqual(lc.currency, so.currency)
		self.assertEqual(lc.get_alert_days(), [15, 7, 3])
		with self.assertRaises(frappe.ValidationError):
			self.make_lc(so, expiry_date=add_days(nowdate(), 10), latest_shipment_date=add_days(nowdate(), 30))

	def test_lc_alert_thresholds(self):
		so, _customer = make_money_so(self.company)
		# LSD in 7 days (threshold hit), expiry in 40 (no threshold)
		lc = self.make_lc(so, latest_shipment_date=add_days(nowdate(), 7))

		alerts = send_lc_alerts()
		mine = [a for a in alerts if a["lc"] == lc.name]
		self.assertEqual(len(mine), 1)
		self.assertEqual(mine[0]["label"], "latest shipment date")
		self.assertEqual(mine[0]["days_left"], 7)

		self.assertTrue(
			frappe.db.exists(
				"Notification Log", {"document_name": lc.name, "subject": mine[0]["subject"]}
			),
			"An in-app notification must be raised",
		)

		# re-running the same day must not duplicate notifications
		count_before = frappe.db.count("Notification Log", {"document_name": lc.name})
		send_lc_alerts()
		self.assertEqual(frappe.db.count("Notification Log", {"document_name": lc.name}), count_before)

	def test_lc_overdue_alerts_and_malformed_thresholds(self):
		so, _customer = make_money_so(self.company)
		# overdue LSD (expiry must be >= LSD at insert, so backdate both via db_set)
		lc = self.make_lc(so, latest_shipment_date=add_days(nowdate(), 1))
		lc.db_set("latest_shipment_date", add_days(nowdate(), -4), update_modified=False)
		# malformed thresholds bypassing validate must not blind the run
		lc.db_set("alert_thresholds", "soon, later", update_modified=False)

		alerts = send_lc_alerts()
		mine = [a for a in alerts if a["lc"] == lc.name and a["label"] == "latest shipment date"]
		self.assertEqual(len(mine), 1, "Overdue open LCs must keep alerting")
		self.assertEqual(mine[0]["days_left"], -4)
		self.assertIn("overdue by 4 days", mine[0]["subject"])

	def test_create_export_sales_order_endpoint(self):
		"""The in-app deal form books the SO with NO supplier — procurement is
		negotiated later, so lines stay plain until the Phase-3 PO flow."""
		sfx = _suffix()
		# plain sales item: no item-level drop-ship flag, like the client's real items
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"_Test EF Plain Item {sfx}",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": "Kg",
				"is_stock_item": 0,
				"is_sales_item": 1,
				"is_purchase_item": 1,
			}
		).insert(ignore_permissions=True)
		customer = make_customer(f"_Test EF Customer Form {sfx}")
		company_currency = frappe.db.get_value("Company", self.company, "default_currency")
		deal_currency = "EUR" if company_currency != "EUR" else "USD"

		result = create_export_sales_order(
			{
				"customer": customer,
				"delivery_date": add_days(nowdate(), 30),
				"currency": deal_currency,
				"conversion_rate": 83,
				"named_place": "Jebel Ali",
				"payment_terms_narrative": "30% advance",
				"items": [{"item_code": item.name, "qty": 100, "rate": 12}],
			}
		)
		so = frappe.get_doc("Sales Order", result["name"])
		self.assertEqual(so.docstatus, 0, "Saved as draft by default")
		self.assertEqual(so.currency, deal_currency)
		self.assertEqual(so.payment_terms_narrative, "30% advance")
		self.assertFalse(so.items[0].supplier, "No supplier at deal-entry time")
		self.assertEqual(flt(so.grand_total), 1200.0)

		submitted = submit_sales_order(so.name)
		self.assertEqual(submitted["docstatus"], 1, "Submits without a supplier")

		# zero-rate rows must be rejected up front
		with self.assertRaises(frappe.ValidationError):
			create_export_sales_order(
				{
					"customer": customer,
					"delivery_date": add_days(nowdate(), 30),
					"currency": deal_currency,
					"conversion_rate": 83,
					"items": [{"item_code": item.name, "qty": 5, "rate": 0}],
				}
			)

	def test_lc_alerts_skip_closed(self):
		so, _customer = make_money_so(self.company)
		lc = self.make_lc(so, latest_shipment_date=add_days(nowdate(), 3), status="Negotiated/Paid")
		alerts = send_lc_alerts()
		self.assertFalse([a for a in alerts if a["lc"] == lc.name], "Settled LCs never alert")
