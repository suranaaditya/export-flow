import frappe
from frappe.utils import add_days, getdate, nowdate

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from exportflow.api import (
	add_document_instance,
	create_purchase_order,
	create_shipment,
	generate_document,
	get_shipment_documents,
	set_shipment_milestone,
	submit_purchase_order,
	update_document_instance,
)
from exportflow.checklist import build_checklist
from exportflow.setup import seed_checklist_rules, seed_document_types
from exportflow.tests.test_dropship import _suffix, make_customer, make_supplier
from exportflow.tests.test_logistics import book_deal, make_plain_item

BASE_SET = {
	"Commercial Invoice",
	"Packing List",
	"Shipping Instruction to CHA",
	"SCOMET Non-Applicability Declaration",
	"Shipping Bill",
	"ADC NOC",
	"Let Export Order",
	"EGM",
	"Certificate of Analysis",
	"Booking Confirmation",
	"Certificate of Origin",
}


def doc_types_on(shipment: str) -> set[str]:
	return set(
		frappe.get_all("Document Instance", filters={"shipment": shipment}, pluck="document_type")
	)


def instance_of(shipment: str, document_type: str, **extra) -> str:
	name = frappe.db.get_value(
		"Document Instance", {"shipment": shipment, "document_type": document_type, **extra}, "name"
	)
	assert name, f"expected a {document_type} instance on {shipment}"
	return name


class TestDocuments(IntegrationTestCase):
	"""Spec §5: the checklist rule engine (the highest-value test target),
	blocking documents and PDF generation."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")
		# idempotent — protects a test site that has not migrated yet
		seed_document_types()
		seed_checklist_rules()

	def make_deal(self, qty=10):
		sfx = _suffix()
		item = make_plain_item(f"_Test EF D Item {sfx}")
		customer = make_customer(f"_Test EF D Customer {sfx}")
		supplier = make_supplier(f"_Test EF D Supplier {sfx}")
		so = book_deal(self.company, customer, [{"item_code": item, "qty": qty, "rate": 12}])
		return so, customer, supplier

	def make_shipment(self, so, customer, qty=10, mode="Sea", incoterm=None, lc=None, po_row=None):
		row = so.items[0]
		payload = {
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
					**(po_row or {}),
				}
			],
		}
		return create_shipment(payload)["name"]

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

	# ---------------------------------------------------------------- rules

	def test_base_checklist_sea(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer, mode="Sea")
		types = doc_types_on(shp)
		self.assertTrue(BASE_SET <= types, f"base set missing: {BASE_SET - types}")
		self.assertIn("Bill of Lading", types)
		self.assertIn("VGM Declaration", types)
		self.assertNotIn("Air Waybill", types)
		# no LC linked → none of the LC paperwork
		self.assertNotIn("Bill of Exchange", types)

	def test_air_checklist(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer, mode="Air")
		types = doc_types_on(shp)
		self.assertIn("Air Waybill", types)
		self.assertNotIn("Bill of Lading", types)
		self.assertNotIn("VGM Declaration", types)

	def test_incoterm_condition_and_lapse(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer, incoterm="FOB")
		self.assertNotIn("Marine/Transit Insurance Certificate", doc_types_on(shp))

		doc = frappe.get_doc("Export Shipment", shp)
		doc.incoterm = "CIF"
		doc.save()
		self.assertIn("Marine/Transit Insurance Certificate", doc_types_on(shp))

		# lapse while still Pending → removed
		doc.incoterm = "FOB"
		doc.save()
		self.assertNotIn("Marine/Transit Insurance Certificate", doc_types_on(shp))

	def test_lapsed_but_progressed_rows_survive(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer, incoterm="CIP")
		ins = instance_of(shp, "Marine/Transit Insurance Certificate")
		update_document_instance(ins, {"status": "Received"})

		doc = frappe.get_doc("Export Shipment", shp)
		doc.incoterm = "FOB"
		doc.save()
		self.assertEqual(
			frappe.db.get_value("Document Instance", ins, "status"),
			"Received",
			"a progressed row is the user's work — the engine must not delete it",
		)

	def test_idempotent_rebuild(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		count = frappe.db.count("Document Instance", {"shipment": shp})
		doc = frappe.get_doc("Export Shipment", shp)
		build_checklist(doc)
		build_checklist(shp)
		doc.save()
		self.assertEqual(
			frappe.db.count("Document Instance", {"shipment": shp}),
			count,
			"re-running the builder must never duplicate",
		)

	def test_manual_rows_survive_rebuild(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		manual = add_document_instance(shp, "Freight Invoice", remarks="negotiated rebate")["name"]
		build_checklist(shp)
		self.assertTrue(frappe.db.exists("Document Instance", manual))
		self.assertEqual(frappe.db.get_value("Document Instance", manual, "source"), "Manual")

	def test_destination_country_rule(self):
		rule_name = "_Test Egypt: COPP"
		if not frappe.db.exists("Document Checklist Rule", rule_name):
			frappe.get_doc(
				{
					"doctype": "Document Checklist Rule",
					"rule_name": rule_name,
					"document_type": "COPP",
					"enabled": 1,
					"conditions": [
						{"condition_field": "destination_country", "condition_value": "Egypt"}
					],
				}
			).insert(ignore_permissions=True)

		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		self.assertNotIn("COPP", doc_types_on(shp))

		# stamping the customer's market re-syncs its shipments via hook
		cust = frappe.get_doc("Customer", customer)
		cust.destination_country = "Egypt"
		cust.save(ignore_permissions=True)
		self.assertIn("COPP", doc_types_on(shp))

		cust.destination_country = "United Arab Emirates"
		cust.save(ignore_permissions=True)
		self.assertNotIn("COPP", doc_types_on(shp), "pending lapsed row goes away")

	# ---------------------------------------------------------------- LC merge

	def test_lc_requirements_merge_and_due_dates(self):
		so, customer, _s = self.make_deal()
		lc = self.make_lc(
			so,
			requirements=[
				{
					"document_type": "Commercial Invoice",
					"description": "Signed commercial invoice in triplicate",
					"originals": 3,
					"copies": 2,
				}
			],
		)
		shp = self.make_shipment(so, customer, lc=lc.name)
		types = doc_types_on(shp)
		for lc_doc in ("Bill of Exchange", "Bank Presentation Covering Schedule",
				"Document Courier AWB", "eBRC"):
			self.assertIn(lc_doc, types)

		# the base-set invoice row was annotated, not duplicated
		inv = frappe.db.get_value(
			"Document Instance",
			{"shipment": shp, "document_type": "Commercial Invoice"},
			["name", "source", "description", "originals", "copies"],
			as_dict=True,
		)
		self.assertEqual(inv.source, "LC")
		self.assertEqual(inv.originals, 3)
		self.assertIn("triplicate", inv.description)
		self.assertEqual(
			frappe.db.count(
				"Document Instance", {"shipment": shp, "document_type": "Commercial Invoice"}
			),
			1,
		)

		# transport document dated → presentation clock stamped (B/L + 21 days)
		doc = frappe.get_doc("Export Shipment", shp)
		doc.bl_number = "TESTBL"
		doc.bl_date = nowdate()
		doc.save()
		due = frappe.db.get_value(
			"Document Instance", {"shipment": shp, "document_type": "Bill of Exchange"}, "due_date"
		)
		self.assertEqual(getdate(due), getdate(add_days(nowdate(), 21)))

		# unlink the LC → pending LC-only paperwork lapses, the invoice stays
		doc.reload()
		doc.letter_of_credit = None
		doc.save()
		types = doc_types_on(shp)
		self.assertNotIn("Bill of Exchange", types)
		self.assertIn("Commercial Invoice", types)

	# ---------------------------------------------------------------- GST packs

	def test_gst_pack_per_scheme_po(self):
		so, customer, supplier = self.make_deal(qty=10)
		result = create_purchase_order(
			so.name, [{"so_detail": so.items[0].name, "supplier": supplier, "qty": 10, "rate": 9}]
		)
		po_name = result["purchase_orders"][0]["name"]
		po = frappe.get_doc("Purchase Order", po_name)
		po.supplier_invoice_no = "SUP-INV-1"
		po.supplier_invoice_date = nowdate()
		po.save()

		shp = self.make_shipment(so, customer, qty=10)
		self.assertNotIn(
			"GST Supplier Compliance Pack", doc_types_on(shp), "draft POs owe nothing yet"
		)

		submit_purchase_order(po_name)
		pack = frappe.db.get_value(
			"Document Instance",
			{"shipment": shp, "document_type": "GST Supplier Compliance Pack"},
			["name", "purchase_order", "due_date"],
			as_dict=True,
		)
		self.assertTrue(pack, "PO submit must add the per-PO compliance pack")
		self.assertEqual(pack.purchase_order, po_name)
		self.assertEqual(
			getdate(pack.due_date),
			getdate(add_days(nowdate(), 90)),
			"pack is due when the §4.3 export window closes",
		)

		frappe.get_doc("Purchase Order", po_name).cancel()
		self.assertNotIn(
			"GST Supplier Compliance Pack",
			doc_types_on(shp),
			"cancelling the PO retires the pending pack",
		)

	# ---------------------------------------------------------------- blocking

	def test_blocking_documents_gate_leo(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer, mode="Sea")
		doc = frappe.get_doc("Export Shipment", shp)
		rows = doc.milestones

		# walk to the gate: Planned … Customs Filed
		for row in rows[:4]:
			set_shipment_milestone(shp, row.name, 1)

		with self.assertRaises(frappe.ValidationError, msg="ADC NOC + Shipping Bill must block LEO"):
			set_shipment_milestone(shp, rows[4].name, 1)

		# Shipping Bill unblocks at Sent/Filed (filed on ICEGATE), ADC NOC at Received
		update_document_instance(instance_of(shp, "Shipping Bill"), {"status": "Sent/Filed"})
		with self.assertRaises(frappe.ValidationError, msg="ADC NOC still pending"):
			set_shipment_milestone(shp, rows[4].name, 1)

		update_document_instance(instance_of(shp, "ADC NOC"), {"status": "Received"})
		current = set_shipment_milestone(shp, rows[4].name, 1)
		self.assertEqual(current, "Container Stuffed/Gated In")

	def test_not_applicable_unblocks(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer, mode="Sea")
		doc = frappe.get_doc("Export Shipment", shp)
		rows = doc.milestones
		for row in rows[:4]:
			set_shipment_milestone(shp, row.name, 1)

		update_document_instance(instance_of(shp, "Shipping Bill"), {"status": "Sent/Filed"})
		update_document_instance(instance_of(shp, "ADC NOC"), {"status": "Not Applicable"})
		current = set_shipment_milestone(shp, rows[4].name, 1)
		self.assertEqual(current, "Container Stuffed/Gated In")

	# ---------------------------------------------------------------- generation

	def test_generate_commercial_invoice(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer, incoterm="CIF")
		inv = instance_of(shp, "Commercial Invoice")

		result = generate_document(inv)
		self.assertTrue(result["file_url"], "PDF must be attached")
		self.assertEqual(result["status"], "Drafted")
		self.assertTrue(
			result["document_number"].startswith("EXP-INV-"),
			"invoice number auto-assigned on first generation",
		)

		row = frappe.db.get_value(
			"Document Instance", inv, ["file", "status", "document_date"], as_dict=True
		)
		self.assertEqual(row.file, result["file_url"])
		self.assertEqual(row.status, "Drafted")
		self.assertEqual(getdate(row.document_date), getdate(nowdate()))

		# regenerating refreshes the file without resetting later progress
		update_document_instance(inv, {"status": "Sent/Filed"})
		again = generate_document(inv)
		self.assertEqual(again["status"], "Sent/Filed")

	def test_generate_rejects_tracked_documents(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		with self.assertRaises(frappe.ValidationError):
			generate_document(instance_of(shp, "ADC NOC"))

	# ---------------------------------------------------------------- API guards

	def test_update_guard(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		inv = instance_of(shp, "Commercial Invoice")
		with self.assertRaises(frappe.ValidationError):
			update_document_instance(inv, {"source": "Manual"})
		with self.assertRaises(frappe.ValidationError):
			update_document_instance(inv, {"status": "Bogus"})

	# ------------------------------------------------- review-driven regressions

	def test_gst_pack_due_date_stamped_after_post_submit_invoice(self):
		"""The designed flow: PO submitted first, supplier invoice lands later
		(update-after-submit). The pack's due date must follow."""
		so, customer, supplier = self.make_deal(qty=10)
		result = create_purchase_order(
			so.name, [{"so_detail": so.items[0].name, "supplier": supplier, "qty": 10, "rate": 9}]
		)
		po_name = result["purchase_orders"][0]["name"]
		shp = self.make_shipment(so, customer, qty=10)
		submit_purchase_order(po_name)

		pack = instance_of(shp, "GST Supplier Compliance Pack")
		self.assertIsNone(
			frappe.db.get_value("Document Instance", pack, "due_date"),
			"no invoice yet, no deadline yet",
		)

		po = frappe.get_doc("Purchase Order", po_name)
		po.supplier_invoice_no = "SUP-INV-LATE"
		po.supplier_invoice_date = nowdate()
		po.save()  # update-after-submit — the SPA's invoice capture path

		self.assertEqual(
			getdate(frappe.db.get_value("Document Instance", pack, "due_date")),
			getdate(add_days(nowdate(), 90)),
			"invoice arrival must stamp the §4.3 deadline on the pack",
		)

	def test_two_scheme_pos_two_packs(self):
		"""Per-PO identity: two 0.1% suppliers feeding one shipment owe two packs."""
		sfx = _suffix()
		item_a = make_plain_item(f"_Test EF D2 A {sfx}")
		item_b = make_plain_item(f"_Test EF D2 B {sfx}")
		customer = make_customer(f"_Test EF D2 Customer {sfx}")
		s1 = make_supplier(f"_Test EF D2 Sup One {sfx}")
		s2 = make_supplier(f"_Test EF D2 Sup Two {sfx}")
		so = book_deal(
			self.company,
			customer,
			[{"item_code": item_a, "qty": 10, "rate": 12}, {"item_code": item_b, "qty": 10, "rate": 15}],
		)
		result = create_purchase_order(
			so.name,
			[
				{"so_detail": so.items[0].name, "supplier": s1, "qty": 10, "rate": 9},
				{"so_detail": so.items[1].name, "supplier": s2, "qty": 10, "rate": 11},
			],
		)
		pos = {p["supplier"]: p["name"] for p in result["purchase_orders"]}
		for i, po_name in enumerate(pos.values()):
			po = frappe.get_doc("Purchase Order", po_name)
			po.supplier_invoice_no = f"SUP-{i}"
			po.supplier_invoice_date = add_days(nowdate(), -i)
			po.save()

		shp = create_shipment(
			{
				"customer": customer,
				"mode": "Sea",
				"items": [
					{
						"item_code": row.item_code,
						"qty": 10,
						"uom": row.uom,
						"sales_order": so.name,
						"so_detail": row.name,
					}
					for row in so.items
				],
			}
		)["name"]
		for po_name in pos.values():
			submit_purchase_order(po_name)

		packs = frappe.get_all(
			"Document Instance",
			filters={"shipment": shp, "document_type": "GST Supplier Compliance Pack"},
			fields=["purchase_order", "due_date"],
		)
		self.assertEqual(len(packs), 2, "one compliance pack per scheme PO")
		self.assertEqual({p.purchase_order for p in packs}, set(pos.values()))
		due_by_po = {p.purchase_order: getdate(p.due_date) for p in packs}
		for i, po_name in enumerate(pos.values()):
			self.assertEqual(due_by_po[po_name], getdate(add_days(nowdate(), 90 - i)))

		frappe.get_doc("Purchase Order", list(pos.values())[0]).cancel()
		remaining = frappe.get_all(
			"Document Instance",
			filters={"shipment": shp, "document_type": "GST Supplier Compliance Pack"},
			pluck="purchase_order",
		)
		self.assertEqual(remaining, [list(pos.values())[1]], "only the cancelled PO's pack lapses")

	def test_document_type_rename_self_heals(self):
		"""Identity follows the Link fields — a renamed Document Type must not
		duplicate or orphan its instances."""
		sfx = _suffix()
		type_name = f"_Test Renamable {sfx}"
		frappe.get_doc(
			{
				"doctype": "Document Type",
				"document_type_name": type_name,
				"category": "Quality",
				"origin": "Tracked",
				"responsible_party": "Supplier",
				"attaches_to": "Shipment",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Document Checklist Rule",
				"rule_name": f"_Test Renamable rule {sfx}",
				"document_type": type_name,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)

		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		self.assertIn(type_name, doc_types_on(shp))

		new_name = f"{type_name} (CDSCO)"
		frappe.rename_doc("Document Type", type_name, new_name, force=True)
		build_checklist(shp)

		self.assertEqual(
			frappe.db.count("Document Instance", {"shipment": shp, "document_type": new_name}),
			1,
			"rename must neither duplicate nor delete the instance",
		)
		self.assertEqual(
			frappe.db.get_value(
				"Document Instance", {"shipment": shp, "document_type": new_name}, "source_key"
			),
			f"dt::{new_name}",
			"stored key self-heals after the rename",
		)

	def test_lapsed_pending_row_with_user_work_is_relinquished(self):
		"""A Pending row carrying an uploaded file/number/remarks is the user's
		work — on lapse it is handed over (source Manual), never deleted."""
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer, incoterm="CIP")
		ins = instance_of(shp, "Marine/Transit Insurance Certificate")
		update_document_instance(ins, {"document_number": "INS-778", "remarks": "broker copy"})
		self.assertEqual(frappe.db.get_value("Document Instance", ins, "status"), "Pending")

		doc = frappe.get_doc("Export Shipment", shp)
		doc.incoterm = "FOB"
		doc.save()

		row = frappe.db.get_value(
			"Document Instance", ins, ["source", "document_number"], as_dict=True
		)
		self.assertTrue(row, "the row must survive the lapse")
		self.assertEqual(row.source, "Manual")
		self.assertEqual(row.document_number, "INS-778")

	def test_lc_amendment_resyncs_linked_shipment(self):
		"""Bank amends the LC after booking — the on_update hook must carry the
		new requirement into the existing checklist."""
		so, customer, _s = self.make_deal()
		lc = self.make_lc(so)
		shp = self.make_shipment(so, customer, lc=lc.name)

		lc.reload()
		lc.append(
			"document_requirements",
			{"document_type": "Certificate of Origin", "description": "Chamber attested", "originals": 2},
		)
		lc.save(ignore_permissions=True)

		row = frappe.db.get_value(
			"Document Instance",
			{"shipment": shp, "document_type": "Certificate of Origin"},
			["source", "originals", "description"],
			as_dict=True,
		)
		self.assertEqual(row.source, "LC")
		self.assertEqual(row.originals, 2)
		self.assertIn("Chamber", row.description)

	def test_lc_duplicate_requirement_rows_fold_to_one_instance(self):
		so, customer, _s = self.make_deal()
		lc = self.make_lc(
			so,
			requirements=[
				{"document_type": "Commercial Invoice", "originals": 3},
				{"document_type": "Commercial Invoice", "originals": 1, "description": "extra set"},
			],
		)
		shp = self.make_shipment(so, customer, lc=lc.name)
		self.assertEqual(
			frappe.db.count(
				"Document Instance", {"shipment": shp, "document_type": "Commercial Invoice"}
			),
			1,
		)
		build_checklist(shp)
		self.assertEqual(
			frappe.db.count(
				"Document Instance", {"shipment": shp, "document_type": "Commercial Invoice"}
			),
			1,
		)

	def test_blocked_milestone_via_direct_save(self):
		"""set_milestone is not the only write path — flipping the completed
		flag on the document itself must hit the same gate."""
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer, mode="Sea")
		doc = frappe.get_doc("Export Shipment", shp)
		for row in doc.milestones[:4]:
			set_shipment_milestone(shp, row.name, 1)

		doc.reload()
		doc.milestones[4].completed = 1
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_uncomplete_leo_after_blocker_regression(self):
		"""Un-completing must work even when a blocker regressed (correcting a
		mis-click); re-completing then re-checks the gate."""
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer, mode="Sea")
		doc = frappe.get_doc("Export Shipment", shp)
		rows = doc.milestones
		for row in rows[:4]:
			set_shipment_milestone(shp, row.name, 1)
		update_document_instance(instance_of(shp, "Shipping Bill"), {"status": "Sent/Filed"})
		update_document_instance(instance_of(shp, "ADC NOC"), {"status": "Received"})
		set_shipment_milestone(shp, rows[4].name, 1)

		update_document_instance(instance_of(shp, "ADC NOC"), {"status": "Pending"})
		current = set_shipment_milestone(shp, rows[4].name, 0)
		self.assertEqual(current, "Let Export Order", "un-complete allowed despite regressed blocker")
		with self.assertRaises(frappe.ValidationError):
			set_shipment_milestone(shp, rows[4].name, 1)

	def test_rule_edit_resyncs_shipments(self):
		"""Creating/disabling a rule re-syncs existing checklists via hooks —
		no shipment save required."""
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		self.assertNotIn("Freight Invoice", doc_types_on(shp))

		rule = frappe.get_doc(
			{
				"doctype": "Document Checklist Rule",
				"rule_name": f"_Test FI {_suffix()}",
				"document_type": "Freight Invoice",
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
		self.assertIn("Freight Invoice", doc_types_on(shp), "new rule lands without a shipment save")

		rule.enabled = 0
		rule.save(ignore_permissions=True)
		self.assertNotIn("Freight Invoice", doc_types_on(shp), "disabling retires the pending row")

	def test_shipment_trash_cleans_instances(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		update_document_instance(instance_of(shp, "EGM"), {"status": "Received"})
		add_document_instance(shp, "Freight Invoice")
		frappe.delete_doc("Export Shipment", shp)
		self.assertEqual(frappe.db.count("Document Instance", {"shipment": shp}), 0)

	def test_generate_requires_shipment(self):
		orphan = frappe.get_doc(
			{
				"doctype": "Document Instance",
				"document_type": "Commercial Invoice",
				"status": "Pending",
				"source": "Manual",
			}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			generate_document(orphan.name)
		self.assertIsNone(
			frappe.db.get_value("Document Instance", orphan.name, "document_number"),
			"a failed generation must not stamp a number",
		)

	def test_generate_rejects_foreign_doctype_format(self):
		"""The PFI type's format targets the PFI doctype — generating it from a
		shipment checklist row must fail cleanly, not render garbage."""
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		manual = add_document_instance(shp, "Pro Forma Invoice")["name"]
		with self.assertRaises(frappe.ValidationError):
			generate_document(manual)

	def test_attach_document_file(self):
		from frappe.utils.file_manager import save_file

		from exportflow.api import attach_document_file

		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		ins = instance_of(shp, "ADC NOC")
		# .txt, not .pdf — frappe runs pypdf validation on pdf uploads
		file_doc = save_file("noc.txt", b"received NOC scan", "Document Instance", ins, is_private=1)

		attach_document_file(ins, file_doc.file_url)
		self.assertEqual(frappe.db.get_value("Document Instance", ins, "file"), file_doc.file_url)

		with self.assertRaises(frappe.ValidationError):
			attach_document_file(ins, "/private/files/not-attached-here.pdf")

	def test_due_date_locked_on_engine_rows(self):
		so, customer, _s = self.make_deal()
		lc = self.make_lc(so)
		shp = self.make_shipment(so, customer, lc=lc.name)
		boe = instance_of(shp, "Bill of Exchange")
		with self.assertRaises(frappe.ValidationError):
			update_document_instance(boe, {"due_date": nowdate()})

		manual = add_document_instance(shp, "Freight Invoice")["name"]
		update_document_instance(manual, {"due_date": nowdate()})
		self.assertEqual(
			getdate(frappe.db.get_value("Document Instance", manual, "due_date")), getdate(nowdate())
		)

	def test_orphaned_document_type_is_skipped(self):
		sfx = _suffix()
		type_name = f"_Test Orphan {sfx}"
		frappe.get_doc(
			{
				"doctype": "Document Type",
				"document_type_name": type_name,
				"category": "Quality",
				"origin": "Tracked",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Document Checklist Rule",
				"rule_name": f"_Test Orphan rule {sfx}",
				"document_type": type_name,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)

		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		self.assertIn(type_name, doc_types_on(shp))

		frappe.delete_doc("Document Type", type_name, force=True, ignore_permissions=True)
		doc = frappe.get_doc("Export Shipment", shp)
		doc.save()  # must not raise; the orphaned pending row simply lapses
		self.assertNotIn(type_name, doc_types_on(shp))

	def test_responsible_party_defaults_from_type(self):
		"""Frappe pre-fills Selects with their first option — the engine must
		still land each instance on its type's responsible party."""
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer, mode="Sea")
		expected = {
			"ADC NOC": "CHA",
			"Certificate of Analysis": "Supplier",
			"Bill of Lading": "Shipping Line/Airline",
			"Commercial Invoice": "Us",
		}
		for doc_type, party in expected.items():
			self.assertEqual(
				frappe.db.get_value(
					"Document Instance", {"shipment": shp, "document_type": doc_type}, "responsible_party"
				),
				party,
				f"{doc_type} should default to {party}",
			)

	def test_workspace_payload(self):
		from exportflow.api import get_documents_workspace

		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		payload = get_documents_workspace()
		mine = [d for d in payload["documents"] if d["shipment"] == shp]
		self.assertTrue(mine, "workspace must list the new shipment's documents")
		self.assertTrue(any(t["name"] == "Commercial Invoice" for t in payload["document_types"]))

	def test_checklist_card_payload(self):
		so, customer, _s = self.make_deal()
		shp = self.make_shipment(so, customer)
		payload = get_shipment_documents(shp)
		self.assertTrue(len(payload["documents"]) >= len(BASE_SET))
		self.assertTrue(any(t["name"] == "Commercial Invoice" for t in payload["document_types"]))
		inv = next(d for d in payload["documents"] if d["document_type"] == "Commercial Invoice")
		self.assertEqual(inv["origin"], "Generated")
		self.assertEqual(inv["category"], "Commercial")
		adc = next(d for d in payload["documents"] if d["document_type"] == "ADC NOC")
		self.assertEqual(adc["blocking"], 1)
		self.assertEqual(adc["blocked_milestone"], "Let Export Order")
