import frappe
from unittest.mock import patch

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from exportflow.ai_email import email_context, email_send
from exportflow.api import create_purchase_order
from exportflow.tests.test_dropship import _suffix, make_customer
from exportflow.tests.test_logistics import book_deal, make_plain_item


class TestAiEmail(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")

	def _make_po(self):
		sfx = _suffix()
		item = make_plain_item(f"_Test EF Mail Item {sfx}")
		cust = make_customer(f"_Test EF Mail Cust {sfx}")
		so = book_deal(self.company, cust, [{"item_code": item, "qty": 10, "rate": 100}])
		supplier = frappe.get_doc({
			"doctype": "Supplier", "supplier_name": f"_Test EF Mail Supp {sfx}",
			"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
		}).insert(ignore_permissions=True).name
		res = create_purchase_order(
			so.name, [{"so_detail": so.items[0].name, "supplier": supplier, "qty": 10, "rate": 60}]
		)
		return res["purchase_orders"][0]["name"]

	def test_unknown_or_mismatched_purpose(self):
		with self.assertRaises(frappe.ValidationError):
			email_context("Purchase Order", "x", "bogus")
		with self.assertRaises(frappe.ValidationError):
			email_context("Pro Forma Invoice", "x", "po_to_supplier")  # purpose/doctype mismatch

	def test_email_context(self):
		po = self._make_po()
		ctx = email_context("Purchase Order", po, "po_to_supplier")
		self.assertEqual(ctx["party_type"], "Supplier")
		self.assertIn(po, ctx["attachment_label"])
		self.assertEqual(ctx["facts"]["po_number"], po)
		self.assertTrue(ctx["facts"]["items"])

	def test_send_sandbox_and_communication(self):
		po = self._make_po()
		captured = {}

		def fake_sendmail(**kw):
			captured.update(kw)

		with patch("frappe.sendmail", side_effect=fake_sendmail), \
				patch.dict(frappe.conf, {"exportflow_email_sandbox": "sandbox@test.local"}):
			res = email_send(
				"Purchase Order", po, "po_to_supplier",
				to="real@buyer.com", subject="Hi", body="Body", attach_pdf=0,
			)
		# dev redirect to the sandbox; the real recipient is preserved + shown in the subject
		self.assertEqual(res["sent_to"], ["sandbox@test.local"])
		self.assertEqual(res["intended"], "real@buyer.com")
		self.assertEqual(captured["recipients"], ["sandbox@test.local"])
		self.assertIn("real@buyer.com", captured["subject"])
		# the Communication is created and linked to the document's timeline
		comm = frappe.get_doc("Communication", res["communication"])
		self.assertEqual(comm.reference_doctype, "Purchase Order")
		self.assertEqual(comm.reference_name, po)
		self.assertEqual(comm.sent_or_received, "Sent")

	def test_send_requires_valid_recipient(self):
		po = self._make_po()
		with self.assertRaises(frappe.ValidationError):
			email_send("Purchase Order", po, "po_to_supplier", to="not-an-email",
					   subject="x", body="y", attach_pdf=0)

	def test_send_rejects_bad_cc(self):
		po = self._make_po()
		with self.assertRaises(frappe.ValidationError):
			email_send("Purchase Order", po, "po_to_supplier", to="ok@buyer.com",
					   cc="not-an-email", subject="x", body="y", attach_pdf=0)
