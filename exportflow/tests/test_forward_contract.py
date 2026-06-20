import frappe
from frappe.utils import flt

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from exportflow.api import get_forward_contracts, get_open_forwards
from exportflow.tests.test_dropship import _suffix


class TestForwardContract(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")

	def _forward(self, currency="USD", amount=10000, rate=85.0, maturity="2027-01-01"):
		return frappe.get_doc({
			"doctype": "Forward Contract", "company": self.company,
			"contract_no": f"FC-{_suffix()}", "currency": currency,
			"contract_amount": amount, "forward_rate": rate, "maturity_date": maturity,
		}).insert(ignore_permissions=True)

	def _realization(self, fc=None, currency="USD", amount_received=0.0, invoice_value=10000):
		doc = frappe.get_doc({
			"doctype": "Export Realization", "company": self.company,
			"export_invoice": f"INV-{_suffix()}", "currency": currency,
			"invoice_value": invoice_value, "amount_received": amount_received,
		})
		if fc:
			doc.conversion_mode = "Forward Contract"
			doc.forward_contract = fc
		return doc.insert(ignore_permissions=True)

	def test_realization_locks_to_forward_rate(self):
		fc = self._forward(rate=86.5)
		r = self._realization(fc=fc.name, amount_received=4000)
		self.assertEqual(flt(r.conversion_rate), 86.5)
		self.assertEqual(flt(r.fwd_rate), 86.5)
		self.assertEqual(r.fwd_contract_no, fc.contract_no)
		fc.reload()
		self.assertEqual(flt(fc.utilized_amount), 4000)
		self.assertEqual(flt(fc.outstanding_amount), 6000)
		self.assertEqual(fc.status, "Partially Utilized")

	def test_full_utilization(self):
		fc = self._forward(amount=5000)
		self._realization(fc=fc.name, amount_received=3000)
		self._realization(fc=fc.name, amount_received=2000)
		fc.reload()
		self.assertEqual(flt(fc.utilized_amount), 5000)
		self.assertEqual(fc.status, "Fully Utilized")

	def test_currency_mismatch_blocked(self):
		fc = self._forward(currency="EUR")
		with self.assertRaises(frappe.ValidationError):
			self._realization(fc=fc.name, currency="USD", amount_received=100)

	def test_delete_releases_cover(self):
		fc = self._forward(amount=5000)
		r = self._realization(fc=fc.name, amount_received=2000)
		fc.reload()
		self.assertEqual(flt(fc.utilized_amount), 2000)
		frappe.delete_doc("Export Realization", r.name)
		fc.reload()
		self.assertEqual(flt(fc.utilized_amount), 0)
		self.assertEqual(fc.status, "Open")

	def test_open_forwards_currency_filtered(self):
		fc_usd = self._forward(currency="USD")
		fc_eur = self._forward(currency="EUR")
		usd = [f["name"] for f in get_open_forwards("USD")]
		self.assertIn(fc_usd.name, usd)
		self.assertNotIn(fc_eur.name, usd)

	def test_matured_cover_still_drawable(self):
		from frappe.utils import add_days, nowdate

		fc = self._forward(currency="USD", amount=5000, maturity=add_days(nowdate(), -1))
		fc.reload()
		self.assertEqual(fc.status, "Matured")
		self.assertGreater(flt(fc.outstanding_amount), 0)
		# matured cover is still deliverable → stays in the picker + the hedge total
		self.assertIn(fc.name, [f["name"] for f in get_open_forwards("USD")])

	def test_unlink_clears_forward_fields_and_releases_cover(self):
		fc = self._forward(rate=86.0)
		r = self._realization(fc=fc.name, amount_received=1000)
		self.assertEqual(r.fwd_contract_no, fc.contract_no)
		r.conversion_mode = "Direct"
		r.save(ignore_permissions=True)
		r.reload()
		self.assertFalse(r.forward_contract)
		self.assertFalse(r.fwd_contract_no)
		fc.reload()
		self.assertEqual(flt(fc.utilized_amount), 0)

	def test_maturity_alert(self):
		from frappe.utils import add_days, nowdate

		from exportflow.tasks import send_forward_maturity_alerts

		fc = self._forward(amount=10000, maturity=add_days(nowdate(), 7))  # matures in 7d, undrawn
		alerts = send_forward_maturity_alerts()
		self.assertTrue(any(a["forward_contract"] == fc.name for a in alerts))

	def test_portfolio_and_exposure(self):
		fc = self._forward(currency="USD", amount=8000)
		self._realization(fc=fc.name, amount_received=3000, invoice_value=10000)
		data = get_forward_contracts()
		self.assertTrue(any(c["name"] == fc.name for c in data["contracts"]))
		self.assertIsInstance(data["exposure"], list)
