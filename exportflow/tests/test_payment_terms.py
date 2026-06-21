import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from exportflow.api import get_new_po_context, get_new_so_context, get_payment_terms_text
from exportflow.setup import seed_payment_terms


class TestPaymentTerms(IntegrationTestCase):
	"""Export Payment Term master + the SO/PO payment-terms pickers — the payment-side
	counterpart of Terms and Conditions, segregated by selling / buying."""

	def _term(self, name, selling=0, buying=0, text="Net 30 days from invoice."):
		if not frappe.db.exists("Export Payment Term", name):
			frappe.get_doc(
				{
					"doctype": "Export Payment Term",
					"template_name": name,
					"selling": selling,
					"buying": buying,
					"terms": text,
				}
			).insert(ignore_permissions=True)
		return name

	def test_get_payment_terms_text(self):
		self._term("_Test PT Text", selling=1, text="50% advance, 50% on delivery.")
		self.assertEqual(get_payment_terms_text("_Test PT Text"), "50% advance, 50% on delivery.")

	def test_so_context_offers_selling_terms_only(self):
		sell = self._term("_Test PT Sell", selling=1)
		buy = self._term("_Test PT Buy", buying=1)
		opts = get_new_so_context()["payment_terms_templates"]
		self.assertIn(sell, opts)
		self.assertNotIn(buy, opts, "a buying-only payment term must not show on the sales order")

	def test_po_context_offers_buying_terms_only(self):
		sell = self._term("_Test PT Sell2", selling=1)
		buy = self._term("_Test PT Buy2", buying=1)
		opts = get_new_po_context()["payment_terms_templates"]
		self.assertIn(buy, opts)
		self.assertNotIn(sell, opts, "a selling-only payment term must not show on the purchase order")

	def test_disabled_term_is_hidden(self):
		t = self._term("_Test PT Disabled", selling=1)
		frappe.db.set_value("Export Payment Term", t, "disabled", 1)
		self.assertNotIn(t, get_new_so_context()["payment_terms_templates"])
		frappe.db.set_value("Export Payment Term", t, "disabled", 0)

	def test_seed_is_idempotent_and_two_sided(self):
		seed_payment_terms()
		before = frappe.db.count("Export Payment Term")
		seed_payment_terms()
		self.assertEqual(frappe.db.count("Export Payment Term"), before, "re-seeding makes no duplicates")
		self.assertTrue(frappe.db.exists("Export Payment Term", "Sales — 100% advance (TT)"))
		self.assertTrue(frappe.db.exists("Export Payment Term", "Purchase — Net 30 days"))
