import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from exportflow.reports import report_data, report_export, report_list
from exportflow.tests.test_dropship import _suffix, make_customer
from exportflow.tests.test_logistics import book_deal, make_plain_item

REPORT_KEYS = ["realization", "incentive", "sales_register", "gst_export", "merchanting"]


class TestReports(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")

	def test_catalog(self):
		keys = {r["key"] for r in report_list()}
		self.assertTrue(set(REPORT_KEYS) <= keys, f"missing: {set(REPORT_KEYS) - keys}")

	def test_data_shape(self):
		for key in REPORT_KEYS:
			d = report_data(key)
			self.assertTrue(d["title"], key)
			self.assertGreater(len(d["columns"]), 0, key)
			self.assertIsInstance(d["rows"], list)
			self.assertTrue(all("control" in f and "field" in f for f in d["filters"]), key)
			if d["rows"]:
				# the rows are dicts whose keys overlap the declared columns
				col_keys = {c["key"] for c in d["columns"]}
				self.assertTrue(col_keys & set(d["rows"][0]), key)

	def test_sales_register_rows(self):
		sfx = _suffix()
		item = make_plain_item(f"_Test EF Rep Item {sfx}")
		cust = make_customer(f"_Test EF Rep Cust {sfx}")
		book_deal(self.company, cust, [{"item_code": item, "qty": 5, "rate": 100}])
		rows = report_data("sales_register")["rows"]
		self.assertTrue(any(sfx in str(r.get("customer", "")) for r in rows), "the new SO is in the register")
		# INR value is the SO base grand total (positive)
		mine = next(r for r in rows if sfx in str(r.get("customer", "")))
		self.assertGreater(mine["inr_value"], 0)

	def test_export_xlsx(self):
		report_export("realization", "xlsx", rows="[]")
		self.assertEqual(frappe.local.response.type, "binary")
		self.assertTrue(frappe.local.response.filename.endswith(".xlsx"))
		self.assertTrue(frappe.local.response.filecontent, "xlsx bytes produced")

	def test_export_rows_are_formatted(self):
		# a single row round-trips into the xlsx without raising
		report_export(
			"sales_register",
			"xlsx",
			rows='[{"name":"SO-1","transaction_date":"2026-01-01","customer":"X","country":"India","currency":"USD","grand_total":100,"inr_value":8300,"incoterm":"FOB","status":"To Bill"}]',
		)
		self.assertTrue(frappe.local.response.filecontent)

	def test_unknown_report(self):
		with self.assertRaises(frappe.ValidationError):
			report_data("bogus")
		with self.assertRaises(frappe.ValidationError):
			report_export("bogus", "xlsx", rows="[]")
