import frappe
from frappe.utils import flt, nowdate

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from erpnext.selling.doctype.sales_order.sales_order import make_purchase_order

from exportflow import stock
from exportflow.api import (
	add_grn_document,
	cancel_grn,
	cancel_return,
	close_order,
	create_grn,
	create_return,
	create_shipment,
	get_grn_context,
	get_po_detail,
	get_return_context,
	remove_grn_document,
	reopen_order,
	submit_grn,
	submit_return,
)
from exportflow.mtt import MERCHANTING
from exportflow.tests.test_dropship import (
	_suffix,
	make_customer,
	make_dropship_item,
	make_dropship_so,
	make_supplier,
)


def _ensure_warehouse(company: str) -> str:
	wh = frappe.get_all(
		"Warehouse", filters={"company": company, "is_group": 0, "disabled": 0}, pluck="name"
	)
	if wh:
		return wh[0]
	return (
		frappe.get_doc(
			{"doctype": "Warehouse", "warehouse_name": f"_Test GRN WH {_suffix()}", "company": company}
		)
		.insert(ignore_permissions=True)
		.name
	)


class TestGRN(IntegrationTestCase):
	"""Goods Receipt Note — quantity stock-in, PO receipt coverage, supplier-invoice
	write-back, merchanting skip, idempotency and reversal. The stock regime
	(ExportFlow Settings.maintain_stock) is the behaviour under test, so each test
	turns it on (one test turns it off to prove the drop-ship fallback)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from exportflow.setup import seed_document_types

		seed_document_types()  # supplier document types (Certificate of Analysis, …)
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")
		cls.warehouse = _ensure_warehouse(cls.company)

	def setUp(self):
		frappe.db.set_single_value("ExportFlow Settings", "maintain_stock", 1)

	def _po(self, qty=100, rate=50):
		sfx = _suffix()
		supplier = make_supplier(f"_Test GRN Sup {sfx}")
		item = make_dropship_item(f"_Test GRN Item {sfx}", supplier, self.company)
		customer = make_customer(f"_Test GRN Cust {sfx}")
		so = make_dropship_so(customer, self.company, [{"item_code": item, "qty": qty, "rate": rate}])
		po = make_purchase_order(so.name, selected_items=[{"item_code": item, "supplier": supplier}])[0]
		po.items[0].rate = rate
		po.save(ignore_permissions=True)
		po.submit()
		return po, item

	def _receive(self, po, item, qty, **kw):
		payload = {
			"purchase_order": po.name,
			"warehouse": self.warehouse,
			"items": [
				{
					"item_code": item,
					"po_detail": po.items[0].name,
					"ordered_qty": po.items[0].qty,
					"received_qty": qty,
					"uom": po.items[0].uom,
				}
			],
			**kw,
		}
		return create_grn(payload)["name"]

	def test_grn_posts_stock_and_marks_received(self):
		po, item = self._po(qty=100)
		ctx = get_grn_context(po.name)
		self.assertEqual(len(ctx["lines"]), 1)
		self.assertEqual(flt(ctx["lines"][0]["received_qty"]), 100)  # defaults to the remaining qty

		grn = self._receive(
			po, item, 100, supplier_invoice_no="SI-GRN-1", supplier_invoice_date="2026-06-10"
		)
		self.assertEqual(frappe.db.get_value("Goods Receipt Note", grn, "status"), "Draft")
		self.assertEqual(stock.balance(item, self.warehouse), 0)

		submit_grn(grn)
		self.assertEqual(frappe.db.get_value("Goods Receipt Note", grn, "status"), "Received")
		self.assertEqual(stock.balance(item, self.warehouse), 100)

		po.reload()
		self.assertEqual(po.supplier_invoice_no, "SI-GRN-1", "invoice no must write back to the PO")
		self.assertTrue(get_po_detail(po.name)["received"], "a fully-received PO must read received")

	def test_partial_receipt_leaves_po_unreceived(self):
		po, item = self._po(qty=100)
		grn = self._receive(po, item, 40)
		submit_grn(grn)
		self.assertEqual(stock.balance(item, self.warehouse), 40)
		self.assertFalse(get_po_detail(po.name)["received"], "a partly-received PO must stay unreceived")

	def test_submit_is_idempotent(self):
		po, item = self._po(qty=10)
		grn = self._receive(po, item, 10)
		submit_grn(grn)
		submit_grn(grn)
		self.assertEqual(stock.balance(item, self.warehouse), 10, "double submit must not double-post")

	def test_cancel_reverses_stock(self):
		po, item = self._po(qty=10)
		grn = self._receive(po, item, 10)
		submit_grn(grn)
		self.assertEqual(stock.balance(item, self.warehouse), 10)
		cancel_grn(grn)
		self.assertEqual(frappe.db.get_value("Goods Receipt Note", grn, "status"), "Cancelled")
		self.assertEqual(stock.balance(item, self.warehouse), 0, "cancel must reverse the stock-in")

	def test_merchanting_po_rejects_grn(self):
		po, item = self._po(qty=10)
		frappe.db.set_value("Purchase Order", po.name, "merchanting_trade", 1)
		self.assertRaises(frappe.ValidationError, get_grn_context, po.name)
		self.assertRaises(
			frappe.ValidationError,
			create_grn,
			{
				"purchase_order": po.name,
				"warehouse": self.warehouse,
				"items": [{"item_code": item, "po_detail": po.items[0].name, "received_qty": 10}],
			},
		)

	def test_no_stock_when_regime_off(self):
		frappe.db.set_single_value("ExportFlow Settings", "maintain_stock", 0)
		po, item = self._po(qty=10)
		grn = self._receive(po, item, 10, supplier_invoice_no="SI-OFF-1")
		submit_grn(grn)
		# the GRN still records the receipt + invoice, but posts no stock in light mode
		self.assertEqual(frappe.db.get_value("Goods Receipt Note", grn, "status"), "Received")
		self.assertEqual(stock.balance(item, self.warehouse), 0)
		po.reload()
		self.assertEqual(po.supplier_invoice_no, "SI-OFF-1")

	# ---- shipment stock-OUT ----------------------------------------------------

	def _ship(self, po, item, qty):
		row = po.items[0]
		return create_shipment(
			{
				"customer": frappe.db.get_value("Sales Order", row.sales_order, "customer"),
				"mode": "Sea",
				"items": [
					{
						"item_code": item,
						"qty": qty,
						"uom": row.uom,
						"sales_order": row.sales_order,
						"so_detail": row.sales_order_item,
						"purchase_order": po.name,
						"po_detail": row.name,
					}
				],
			}
		)["name"]

	def _mark_departed(self, shp_name, completed=True):
		"""Flip the departure milestone directly (bypassing the sequential engine /
		document blockers) and re-sync stock, to unit-test the stock effect."""
		doc = frappe.get_doc("Export Shipment", shp_name)
		target = doc.export_milestone_name()
		for m in doc.milestones:
			if m.milestone == target:
				m.db_set(
					{"completed": 1 if completed else 0, "actual_date": nowdate() if completed else None},
					update_modified=False,
				)
		doc.reload()
		doc.sync_shipment_stock(force_resync=True)
		return doc

	def test_shipment_posts_stock_out_on_departure(self):
		po, item = self._po(qty=100)
		submit_grn(self._receive(po, item, 100))
		self.assertEqual(stock.balance(item, self.warehouse), 100)
		shp = self._ship(po, item, 100)
		self._mark_departed(shp)
		self.assertEqual(stock.balance(item, self.warehouse), 0, "departure must ship the received stock out")
		# un-departing reverses the stock-out
		self._mark_departed(shp, completed=False)
		self.assertEqual(stock.balance(item, self.warehouse), 100, "un-departing must restore the stock")

	def test_merchanting_shipment_posts_no_stock_out(self):
		po, item = self._po(qty=10)
		submit_grn(self._receive(po, item, 10))
		shp = self._ship(po, item, 10)
		frappe.db.set_value("Export Shipment", shp, "trade_type", MERCHANTING)
		self._mark_departed(shp)
		self.assertFalse(stock.has_entries(stock.SHIPMENT_VOUCHER, shp), "merchanting never ships stock out")
		self.assertEqual(stock.balance(item, self.warehouse), 10)

	def test_grn_required_blocks_departure_without_goods(self):
		frappe.db.set_single_value("ExportFlow Settings", "grn_required_for_shipment", 1)
		po, item = self._po(qty=10)
		shp = self._ship(po, item, 10)
		doc = frappe.get_doc("Export Shipment", shp)
		target = doc.export_milestone_name()
		self.assertRaises(frappe.ValidationError, doc._assert_goods_received, target)
		# once the goods are received, the guard passes
		submit_grn(self._receive(po, item, 10))
		frappe.get_doc("Export Shipment", shp)._assert_goods_received(target)

	# ---- review fixes ----------------------------------------------------------

	def test_cannot_cancel_grn_after_goods_shipped(self):
		po, item = self._po(qty=100)
		grn = self._receive(po, item, 100)
		submit_grn(grn)
		shp = self._ship(po, item, 100)
		self._mark_departed(shp)  # ships the 100 out — balance now 0
		self.assertRaises(frappe.ValidationError, cancel_grn, grn)

	def test_trashing_grn_reverses_its_stock(self):
		po, item = self._po(qty=10)
		grn = self._receive(po, item, 10)
		submit_grn(grn)
		self.assertEqual(stock.balance(item, self.warehouse), 10)
		frappe.delete_doc("Goods Receipt Note", grn, ignore_permissions=True)
		self.assertEqual(stock.balance(item, self.warehouse), 0, "trash must reverse the stock-IN")

	def test_over_receipt_blocked_at_submit(self):
		po, item = self._po(qty=10)
		grn = self._receive(po, item, 15)  # 150% of ordered — well beyond tolerance
		self.assertRaises(frappe.ValidationError, submit_grn, grn)

	def test_over_receipt_within_tolerance_allowed(self):
		frappe.db.set_single_value("ExportFlow Settings", "grn_over_receipt_tolerance_pct", 5)
		po, item = self._po(qty=100)
		submit_grn(self._receive(po, item, 105))  # 105% — within 5% tolerance, OK
		self.assertEqual(stock.balance(item, self.warehouse), 105)
		# anything past the cap is still blocked
		self.assertRaises(frappe.ValidationError, submit_grn, self._receive(po, item, 1))

	def test_over_receipt_uses_default_tolerance_when_unset(self):
		# A docfield default is NOT back-filled into an already-saved Single, so an
		# untouched site has no Singles row → the guard must still grant the intended
		# 5% (regression: an unset value once blocked at exactly the ordered qty).
		frappe.db.delete(
			"Singles", {"doctype": "ExportFlow Settings", "field": "grn_over_receipt_tolerance_pct"}
		)
		po, item = self._po(qty=100)
		submit_grn(self._receive(po, item, 104))  # 4% over — allowed by the default 5%
		self.assertEqual(stock.balance(item, self.warehouse), 104)
		self.assertRaises(frappe.ValidationError, submit_grn, self._receive(po, item, 2))  # 106% blocked

	def test_zero_tolerance_blocks_all_over_receipt(self):
		# A deliberate 0 (per the field's help text) blocks ANY over-receipt — it must
		# NOT be swallowed by the default-5 fallback (unset vs real 0 are distinguished).
		frappe.db.set_single_value("ExportFlow Settings", "grn_over_receipt_tolerance_pct", 0)
		po, item = self._po(qty=100)
		submit_grn(self._receive(po, item, 100))  # exact qty OK
		self.assertRaises(frappe.ValidationError, submit_grn, self._receive(po, item, 1))  # any over blocked

	def test_over_receipt_message_names_the_cap(self):
		frappe.db.set_single_value("ExportFlow Settings", "grn_over_receipt_tolerance_pct", 5)
		po, item = self._po(qty=100)
		with self.assertRaises(frappe.ValidationError) as cm:
			submit_grn(self._receive(po, item, 130))
		msg = str(cm.exception)
		self.assertIn("105", msg, "message must name the real cap (100 + 5%)")
		self.assertIn("5%", msg, "message must name the tolerance %")
		self.assertNotIn("0%", msg, "the old message wrongly read 'by more than 0%'")

	# ---- PO status: Close on full receipt, re-open on return/cancel -------------

	def _po_status(self, po):
		return frappe.db.get_value("Purchase Order", po.name, "status")

	def test_full_receipt_closes_po(self):
		po, item = self._po(qty=100)
		self.assertNotEqual(self._po_status(po), "Closed")
		submit_grn(self._receive(po, item, 100))
		self.assertEqual(self._po_status(po), "Closed", "a fully-received PO is Closed")

	def test_partial_receipt_does_not_close_po(self):
		po, item = self._po(qty=100)
		submit_grn(self._receive(po, item, 40))
		self.assertNotEqual(self._po_status(po), "Closed", "a partly-received PO stays open")

	def test_cancel_grn_reopens_closed_po(self):
		po, item = self._po(qty=100)
		grn = self._receive(po, item, 100)
		submit_grn(grn)
		self.assertEqual(self._po_status(po), "Closed")
		cancel_grn(grn)
		self.assertNotEqual(self._po_status(po), "Closed", "cancelling the receipt re-opens the PO")

	def test_return_reopens_and_cancel_recloses_po(self):
		po, item = self._po(qty=100)
		grn = self._receive(po, item, 100)
		submit_grn(grn)
		self.assertEqual(self._po_status(po), "Closed")
		ret = self._return(grn, item, 30)
		submit_return(ret)
		self.assertNotEqual(self._po_status(po), "Closed", "a return below full re-opens the PO")
		cancel_return(ret)
		self.assertEqual(self._po_status(po), "Closed", "cancelling the return re-closes the now-full PO")

	def test_manual_close_survives_grn_cycle(self):
		# An operator deliberately Closes a PO by hand; completing then cancelling a
		# receipt must NOT clobber that manual Close (no goods-receipt provenance).
		po, item = self._po(qty=100)
		close_order("Purchase Order", po.name)
		self.assertEqual(self._po_status(po), "Closed")
		grn = self._receive(po, item, 100)
		submit_grn(grn)  # receipt completes, but the PO is already manually Closed
		self.assertEqual(self._po_status(po), "Closed")
		cancel_grn(grn)
		self.assertEqual(self._po_status(po), "Closed", "a manual Close is not re-opened by a GRN cancel")

	def test_reopen_survives_within_tolerance_topup(self):
		# After goods-receipt Closes a full PO, an operator re-opens it by hand; a later
		# within-tolerance top-up receipt must NOT slam it shut again (close on the
		# not-full→full transition only).
		frappe.db.set_single_value("ExportFlow Settings", "grn_over_receipt_tolerance_pct", 5)
		po, item = self._po(qty=100)
		submit_grn(self._receive(po, item, 100))
		self.assertEqual(self._po_status(po), "Closed")
		reopen_order("Purchase Order", po.name)
		self.assertNotEqual(self._po_status(po), "Closed")
		submit_grn(self._receive(po, item, 3))  # 103 ≤ 105 cap — allowed, must stay open
		self.assertNotEqual(self._po_status(po), "Closed", "a deliberate re-open is not re-closed")

	# ---- material returns ------------------------------------------------------

	def _return(self, grn, item, qty, **kw):
		ctx = get_return_context(grn)
		line = next(l for l in ctx["lines"] if l["item_code"] == item)
		return create_return(
			{
				"goods_receipt_note": grn,
				"items": [
					{
						"item_code": item,
						"grn_detail": line["grn_detail"],
						"po_detail": line["po_detail"],
						"received_qty": line["received_qty"],
						"returned_qty": qty,
					}
				],
				**kw,
			}
		)["name"]

	def test_material_return_reduces_stock_and_reopens_po(self):
		po, item = self._po(qty=100)
		grn = self._receive(po, item, 100)
		submit_grn(grn)
		self.assertEqual(stock.balance(item, self.warehouse), 100)
		self.assertTrue(get_po_detail(po.name)["received"])
		ret = self._return(grn, item, 30, reason="off-spec")
		submit_return(ret)
		self.assertEqual(stock.balance(item, self.warehouse), 70, "return ships 30 back out")
		self.assertFalse(get_po_detail(po.name)["received"], "net received 70 < 100 reopens the PO")
		self.assertEqual(
			get_grn_context(po.name)["lines"][0]["received_qty"], 30, "the returned 30 is re-receivable"
		)
		cancel_return(ret)
		self.assertEqual(stock.balance(item, self.warehouse), 100, "cancel restores the stock")
		self.assertTrue(get_po_detail(po.name)["received"])

	def test_cannot_return_more_than_received(self):
		po, item = self._po(qty=10)
		grn = self._receive(po, item, 10)
		submit_grn(grn)
		ret = self._return(grn, item, 15)
		self.assertRaises(frappe.ValidationError, submit_return, ret)

	def test_cannot_return_goods_already_shipped(self):
		po, item = self._po(qty=10)
		grn = self._receive(po, item, 10)
		submit_grn(grn)
		shp = self._ship(po, item, 10)
		self._mark_departed(shp)  # stock now 0 — the goods have left
		ret = self._return(grn, item, 10)
		self.assertRaises(frappe.ValidationError, submit_return, ret)

	def test_supplier_documents_add_and_remove(self):
		po, item = self._po(qty=10)
		grn = self._receive(po, item, 10)
		submit_grn(grn)
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"coa-{_suffix()}.txt",
				"attached_to_doctype": "Goods Receipt Note",
				"attached_to_name": grn,
				"is_private": 1,
				"content": "test",
			}
		).insert(ignore_permissions=True)
		add_grn_document(grn, "Certificate of Analysis", f.file_url)
		docs = frappe.get_doc("Goods Receipt Note", grn).documents
		self.assertEqual(len(docs), 1)
		self.assertEqual(docs[0].document_type, "Certificate of Analysis")
		# a file not attached to the GRN is refused
		self.assertRaises(frappe.ValidationError, add_grn_document, grn, "MSDS", "/private/files/nope.pdf")
		remove_grn_document(grn, docs[0].name)
		self.assertEqual(len(frappe.get_doc("Goods Receipt Note", grn).documents), 0)

	def test_grn_documents_forward_to_shipment(self):
		from exportflow.api import add_document_instance
		from exportflow.checklist import _forward_grn_documents

		po, item = self._po(qty=10)
		grn = frappe.get_doc("Goods Receipt Note", self._receive(po, item, 10))
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"coa-{_suffix()}.txt",
				"attached_to_doctype": "Goods Receipt Note",
				"attached_to_name": grn.name,
				"is_private": 1,
				"content": "coa",
			}
		).insert(ignore_permissions=True)
		grn.append("documents", {"document_type": "Certificate of Analysis", "file": f.file_url})
		grn.save()
		submit_grn(grn.name)
		shp = self._ship(po, item, 10)
		# ensure the shipment has a Certificate of Analysis slot (create if no rule did)
		di_name = frappe.db.get_value(
			"Document Instance", {"shipment": shp, "document_type": "Certificate of Analysis"}
		)
		if not di_name:
			add_document_instance(shp, "Certificate of Analysis")
			di_name = frappe.db.get_value(
				"Document Instance", {"shipment": shp, "document_type": "Certificate of Analysis"}
			)
		_forward_grn_documents(frappe.get_doc("Export Shipment", shp))  # idempotent re-sync
		di = frappe.get_doc("Document Instance", di_name)
		self.assertEqual(di.file, f.file_url, "the GRN's CoA file forwards to the shipment")
		self.assertEqual(di.status, "Received")

	def test_one_receiving_warehouse_per_po(self):
		po, item = self._po(qty=100)
		submit_grn(self._receive(po, item, 40))  # into self.warehouse
		wh2 = (
			frappe.get_doc(
				{"doctype": "Warehouse", "warehouse_name": f"_Test GRN WH2 {_suffix()}", "company": self.company}
			)
			.insert(ignore_permissions=True)
			.name
		)
		grn2 = create_grn(
			{
				"purchase_order": po.name,
				"warehouse": wh2,
				"items": [
					{"item_code": item, "po_detail": po.items[0].name, "received_qty": 30, "uom": po.items[0].uom}
				],
			}
		)["name"]
		self.assertRaises(frappe.ValidationError, submit_grn, grn2)
