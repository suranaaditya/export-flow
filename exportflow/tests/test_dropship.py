import frappe
from frappe.utils import add_days, nowdate

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from erpnext.selling.doctype.sales_order.sales_order import make_purchase_order


def _suffix() -> str:
	return frappe.generate_hash(length=6).upper()


def make_supplier(name: str) -> str:
	supplier = frappe.get_doc(
		{
			"doctype": "Supplier",
			"supplier_name": name,
			"supplier_group": frappe.db.get_value("Supplier Group", {}, "name"),
			"country": "India",
			"default_merchant_export_scheme": 1,
		}
	).insert(ignore_permissions=True)
	return supplier.name


def make_customer(name: str) -> str:
	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Company",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
			"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			"gst_category": "Overseas",
		}
	).insert(ignore_permissions=True)
	return customer.name


def make_dropship_item(name: str, default_supplier: str, company: str) -> str:
	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": name,
			"item_name": name,
			"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
			"stock_uom": "Kg",
			"is_stock_item": 0,
			"is_sales_item": 1,
			"is_purchase_item": 1,
			"delivered_by_supplier": 1,
			"pharmacopoeia_grade": "IP",
			"item_defaults": [{"company": company, "default_supplier": default_supplier}],
		}
	).insert(ignore_permissions=True)
	return item.name


def make_dropship_so(customer: str, company: str, item_rows: list[dict]):
	# Foreign-currency deal: pick a currency different from the company currency.
	company_currency = frappe.db.get_value("Company", company, "default_currency")
	deal_currency = "USD" if company_currency != "USD" else "EUR"
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer,
			"company": company,
			"transaction_date": nowdate(),
			"delivery_date": add_days(nowdate(), 30),
			"order_type": "Sales",
			"currency": deal_currency,
			"conversion_rate": 83.0,
			"payment_terms_narrative": "30% advance, 70% against B/L copy",
			"items": [
				{
					"item_code": row["item_code"],
					"qty": row["qty"],
					"rate": row.get("rate", 10),
					"delivered_by_supplier": 1,
				}
				for row in item_rows
			],
		}
	)
	so.insert(ignore_permissions=True)
	so.submit()
	return so


class TestDropShipFlow(IntegrationTestCase):
	"""Spec §4.1: SO items default to delivered_by_supplier, POs are created via
	ERPNext's drop-ship mapping so item-level SO↔PO linkage is native; no stock
	ledger entries anywhere."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")

	def test_one_po_covers_multiple_so_lines(self):
		"""Two SO lines with the same default supplier map into ONE PO."""
		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Supplier {sfx}")
		item_a = make_dropship_item(f"_Test EF Item A {sfx}", supplier, self.company)
		item_b = make_dropship_item(f"_Test EF Item B {sfx}", supplier, self.company)
		customer = make_customer(f"_Test EF Customer {sfx}")

		so = make_dropship_so(
			customer,
			self.company,
			[{"item_code": item_a, "qty": 100}, {"item_code": item_b, "qty": 50}],
		)

		pos = make_purchase_order(
			so.name,
			selected_items=[
				{"item_code": item_a, "supplier": supplier},
				{"item_code": item_b, "supplier": supplier},
			],
		)
		self.assertEqual(len(pos), 1, "Expected a single PO for a single supplier")

		po = pos[0]
		self.assertEqual(po.supplier, supplier)
		self.assertEqual(len(po.items), 2)

		so_rows_by_item = {row.item_code: row for row in so.items}
		for po_row in po.items:
			self.assertEqual(po_row.sales_order, so.name, "PO row must link back to the SO")
			expected_so_row = so_rows_by_item[po_row.item_code]
			self.assertEqual(
				po_row.sales_order_item,
				expected_so_row.name,
				"PO row must link to the exact SO item row",
			)
			self.assertEqual(po_row.qty, expected_so_row.qty)

		# make_purchase_order already inserts the PO when a supplier is given
		self.assertFalse(po.is_new(), "PO should be inserted by the drop-ship mapper")
		self.assertTrue(
			all(row.delivered_by_supplier for row in po.items),
			"PO rows must carry delivered_by_supplier",
		)

	def test_one_so_maps_to_multiple_pos(self):
		"""SO lines with different default suppliers map into one PO per supplier."""
		sfx = _suffix()
		supplier_one = make_supplier(f"_Test EF Supplier One {sfx}")
		supplier_two = make_supplier(f"_Test EF Supplier Two {sfx}")
		item_a = make_dropship_item(f"_Test EF Item C {sfx}", supplier_one, self.company)
		item_b = make_dropship_item(f"_Test EF Item D {sfx}", supplier_two, self.company)
		customer = make_customer(f"_Test EF Customer Two {sfx}")

		so = make_dropship_so(
			customer,
			self.company,
			[{"item_code": item_a, "qty": 100}, {"item_code": item_b, "qty": 200}],
		)

		pos = make_purchase_order(
			so.name,
			selected_items=[
				{"item_code": item_a, "supplier": supplier_one},
				{"item_code": item_b, "supplier": supplier_two},
			],
		)
		self.assertEqual(len(pos), 2, "Expected one PO per supplier")
		self.assertEqual({po.supplier for po in pos}, {supplier_one, supplier_two})

		so_rows_by_item = {row.item_code: row for row in so.items}
		expected_item_for_supplier = {supplier_one: item_a, supplier_two: item_b}
		for po in pos:
			self.assertEqual(len(po.items), 1, "Each supplier's PO must carry only its own line")
			po_row = po.items[0]
			self.assertEqual(po_row.item_code, expected_item_for_supplier[po.supplier])
			expected_so_row = so_rows_by_item[po_row.item_code]
			self.assertEqual(po_row.sales_order, so.name)
			self.assertEqual(
				po_row.sales_order_item,
				expected_so_row.name,
				"PO row must link to the exact SO item row",
			)
			self.assertEqual(po_row.qty, expected_so_row.qty)

	def test_create_customer_builds_consignee_address(self):
		"""An app-created customer with address fields gets a primary Address so the
		commercial invoice / packing list can print a consignee block."""
		from exportflow.api import create_customer

		name = create_customer(
			{
				"customer_name": f"_Test EF Consignee {_suffix()}",
				"destination_country": "Germany",
				"address_line1": "12 Hafenstrasse",
				"city": "Hamburg",
				"pincode": "20457",
			}
		)["name"]
		addr = frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Address", "link_doctype": "Customer", "link_name": name},
			"parent",
		)
		self.assertTrue(addr, "a primary address must be created")
		row = frappe.db.get_value("Address", addr, ["city", "country", "is_primary_address"], as_dict=True)
		self.assertEqual(row.city, "Hamburg")
		self.assertEqual(row.country, "Germany")
		self.assertEqual(int(row.is_primary_address), 1)
		# no address fields → no address created
		bare = create_customer({"customer_name": f"_Test EF Bare {_suffix()}"})["name"]
		self.assertFalse(
			frappe.db.get_value(
				"Dynamic Link",
				{"parenttype": "Address", "link_doctype": "Customer", "link_name": bare},
				"parent",
			),
			"no address fields entered → no address",
		)

	def test_create_supplier_builds_address(self):
		"""An app-created supplier with address fields gets a primary Address so the PO
		'Supplier (Bill from)' block prints the full address — including a foreign
		supplier entered without a GSTIN."""
		from exportflow.api import create_supplier

		name = create_supplier(
			{
				"supplier_name": f"_Test EF Sup Addr {_suffix()}",
				"country": "Germany",
				"address_line1": "12 Hafenstrasse",
				"city": "Hamburg",
				"pincode": "20457",
			}
		)["name"]
		addr = frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Address", "link_doctype": "Supplier", "link_name": name},
			"parent",
		)
		self.assertTrue(addr, "a foreign supplier with an address must get one (no GSTIN needed)")
		row = frappe.db.get_value(
			"Address", addr, ["address_line1", "country", "is_primary_address"], as_dict=True
		)
		self.assertEqual(row.address_line1, "12 Hafenstrasse")
		self.assertEqual(row.country, "Germany")
		self.assertEqual(int(row.is_primary_address), 1)
		# no address fields + no GSTIN → no address
		bare = create_supplier({"supplier_name": f"_Test EF Sup Bare {_suffix()}", "country": "Germany"})["name"]
		self.assertFalse(
			frappe.db.get_value(
				"Dynamic Link",
				{"parenttype": "Address", "link_doctype": "Supplier", "link_name": bare},
				"parent",
			),
			"no address fields + no GSTIN → no address",
		)

	def test_create_party_creates_contact_and_primary_links(self):
		"""Phase 1: an app-created customer / supplier with contact fields gets a primary
		Contact (phone + email) linked via Dynamic Link, and the party's primary-address +
		primary-contact link fields are wired — fully linked in ERPNext, not just via
		Dynamic Links."""
		from exportflow.api import create_customer, create_supplier

		cust = create_customer(
			{
				"customer_name": f"_Test EF Cust Contact {_suffix()}",
				"destination_country": "Germany",
				"address_line1": "12 Hafenstrasse",
				"city": "Hamburg",
				"contact_person": "Hans Mueller",
				"mobile": "+49 40 123456",
				"email": "hans@buyer.de",
			}
		)["name"]
		contact = frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Contact", "link_doctype": "Customer", "link_name": cust},
			"parent",
		)
		self.assertTrue(contact, "a primary contact must be created")
		self.assertEqual(frappe.db.get_value("Customer", cust, "customer_primary_contact"), contact)
		self.assertTrue(
			frappe.db.get_value("Customer", cust, "customer_primary_address"), "primary address link wired"
		)
		row = frappe.db.get_value("Contact", contact, ["first_name", "email_id", "mobile_no"], as_dict=True)
		self.assertEqual(row.first_name, "Hans")
		self.assertEqual(row.email_id, "hans@buyer.de")
		self.assertEqual(row.mobile_no, "+49 40 123456")

		sup = create_supplier(
			{
				"supplier_name": f"_Test EF Sup Contact {_suffix()}",
				"country": "India",
				"contact_person": "Sunil G",
				"mobile": "99799-09072",
				"email": "sunil@sup.com",
			}
		)["name"]
		sc = frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Contact", "link_doctype": "Supplier", "link_name": sup},
			"parent",
		)
		self.assertTrue(sc, "supplier primary contact created")
		self.assertEqual(frappe.db.get_value("Supplier", sup, "supplier_primary_contact"), sc)

	def test_party_multi_address_contact_management(self):
		"""Phase 2: a party can hold multiple addresses + contacts; set-primary flips the
		party's primary link; the current primary cannot be removed."""
		from exportflow.api import (
			add_party_address,
			add_party_contact,
			create_customer,
			get_party_contacts,
			remove_party_address,
			set_party_primary_address,
		)

		cust = create_customer(
			{
				"customer_name": f"_Test EF Multi {_suffix()}",
				"destination_country": "Germany",
				"address_line1": "1 First St",
				"city": "Hamburg",
			}
		)["name"]
		a2 = add_party_address("Customer", cust, {"address_line1": "2 Second St", "city": "Berlin"})["name"]
		data = get_party_contacts("Customer", cust)
		self.assertEqual(len(data["addresses"]), 2, "two addresses now")
		self.assertEqual(len([a for a in data["addresses"] if a["is_primary"]]), 1, "exactly one primary")
		# promote the added address to primary
		set_party_primary_address("Customer", cust, a2)
		self.assertEqual(frappe.db.get_value("Customer", cust, "customer_primary_address"), a2)
		# the current primary cannot be removed
		with self.assertRaises(frappe.ValidationError):
			remove_party_address("Customer", cust, a2)
		# a second contact can be added
		add_party_contact("Customer", cust, {"contact_person": "Jane Doe", "email": "jane@buyer.de"})
		self.assertEqual(len(get_party_contacts("Customer", cust)["contacts"]), 1)

	def test_phase3_picked_address_resolves_in_print(self):
		"""Phase 3: a chosen Address (not just the party default) resolves through the print
		helpers, so the SO/PO/shipment print the address selected on the order — not only
		the party's primary."""
		from exportflow.api import add_party_address, create_supplier
		from exportflow.printing import address_text, supplier_profile

		sup = create_supplier(
			{"supplier_name": f"_Test EF Pick {_suffix()}", "country": "India"}
		)["name"]
		# a distinct second address on the same supplier
		a2 = add_party_address(
			"Supplier",
			sup,
			{
				"address_line1": "Unit 7B, Worli Naka",
				"city": "Mumbai",
				"state": "Maharashtra",
				"pincode": "400018",
			},
		)["name"]
		# address_text renders the *chosen* address verbatim...
		txt = address_text(a2)
		self.assertIn("Worli Naka", txt)
		self.assertIn("Mumbai", txt)
		# ...and supplier_profile honours address_name over the party default
		prof = supplier_profile(sup, None, a2)
		self.assertIn("Worli Naka", prof["address"])

	def test_indian_address_requires_state(self):
		"""Phase 3: an Indian address with no GSTIN and no state is rejected with a clean
		message — the city is never silently used as the GST state (which india_compliance
		would otherwise reject deep in a traceback)."""
		from exportflow.api import add_party_address, create_supplier

		sup = create_supplier({"supplier_name": f"_Test EF NoState {_suffix()}", "country": "India"})["name"]
		with self.assertRaises(frappe.ValidationError):
			add_party_address("Supplier", sup, {"address_line1": "Y", "city": "Mumbai", "country": "India"})

	def test_create_customer_multi_address(self):
		"""The create form's address repeater builds several ERPNext Addresses — row 0 is the
		primary billing address; a row typed 'Shipping' becomes the customer's shipping
		address (the SO Ship-to picker's default). Blank row country falls back to the
		customer's destination country."""
		from exportflow.api import create_customer, get_party_contacts
		from exportflow.printing import address_text

		cust = create_customer(
			{
				"customer_name": f"_Test EF MultiAddr {_suffix()}",
				"destination_country": "Germany",
				"addresses": [
					{"address_type": "Billing", "address_line1": "1 Billing Strasse", "city": "Hamburg"},
					{"address_type": "Shipping", "address_line1": "9 Ship Dock", "city": "Bremen"},
				],
			}
		)["name"]
		addrs = get_party_contacts("Customer", cust)["addresses"]
		self.assertEqual(len(addrs), 2, "both addresses created")
		primary = [a for a in addrs if a["is_primary"]]
		self.assertEqual(len(primary), 1, "exactly one primary")
		self.assertIn("Billing", primary[0]["address_line1"])
		self.assertEqual(primary[0]["country"], "Germany", "blank row country fell back to destination")
		ship = [a for a in addrs if a["is_shipping_address"]]
		self.assertTrue(any("Ship Dock" in a["address_line1"] for a in ship), "the shipping row is flagged")
		self.assertEqual(frappe.db.get_value("Customer", cust, "customer_primary_address"), primary[0]["name"])
		# a missing pincode must NOT print as the literal 'None' (get_address_display quirk)
		self.assertNotIn("None", address_text(primary[0]["name"]) or "")

	def test_create_party_lone_address_doubles_as_shipping(self):
		"""When the repeater has no row tagged 'Shipping', the primary billing address also
		serves as the shipping default — so the Ship-to picker always has something."""
		from exportflow.api import create_supplier, get_party_contacts

		sup = create_supplier(
			{
				"supplier_name": f"_Test EF SupShip {_suffix()}",
				"country": "India",
				"addresses": [
					{"address_type": "Billing", "address_line1": "Plot 9 MIDC", "city": "Pune", "state": "Maharashtra"},
				],
			}
		)["name"]
		addrs = get_party_contacts("Supplier", sup)["addresses"]
		self.assertEqual(len(addrs), 1)
		self.assertEqual(int(addrs[0]["is_shipping_address"]), 1, "lone address doubles as the shipping default")
		self.assertEqual(addrs[0]["state"], "Maharashtra")
		self.assertTrue(frappe.db.get_value("Supplier", sup, "supplier_primary_address"))

	def test_default_charge_account_fills_in(self):
		"""Feedback #11: a charge with only a name + amount (no account picked) posts
		to the configured/standard default expense account, resolved server-side."""
		from exportflow.api import _build_po_doc, _default_charge_account

		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Sup Charge {sfx}")
		item = make_dropship_item(f"_Test EF Item Charge {sfx}", supplier, self.company)
		doc = _build_po_doc(
			{
				"supplier": supplier,
				"items": [{"item_code": item, "qty": 10, "rate": 100}],
				"extra_charges": [{"description": "Cartage to CFS", "amount": 500}],
			},
			validate_remaining=False,
		)
		actuals = [t for t in doc.taxes if t.charge_type == "Actual"]
		self.assertEqual(len(actuals), 1, "the account-less charge still becomes a tax row")
		self.assertEqual(actuals[0].tax_amount, 500)
		expected = _default_charge_account(self.company)
		self.assertEqual(actuals[0].account_head, expected, "filled from the default account")
		acc = frappe.db.get_value("Account", expected, ["is_group", "root_type"], as_dict=True)
		self.assertFalse(acc.is_group, "default must be a postable (non-group) account")
		self.assertEqual(acc.root_type, "Expense")

	def test_preview_does_not_create_charge_account(self):
		"""Batch-2 review fix: the live preview has NO side effects — an account-less
		charge never triggers auto-creation of a GL account during preview."""
		from exportflow.api import preview_purchase_order

		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Sup Prev {sfx}")
		item = make_dropship_item(f"_Test EF Item Prev {sfx}", supplier, self.company)
		before = frappe.db.count("Account", {"company": self.company})
		preview_purchase_order(
			{
				"supplier": supplier,
				"items": [{"item_code": item, "qty": 2, "rate": 100}],
				"extra_charges": [{"description": "Cartage", "amount": 300}],
			}
		)
		after = frappe.db.count("Account", {"company": self.company})
		self.assertEqual(before, after, "preview must not create any Account")

	def test_po_line_specification_and_packaging(self):
		"""Feedback #13: per-line specification + packaging are captured and persist."""
		from exportflow.api import _build_po_doc

		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Sup Spec {sfx}")
		item = make_dropship_item(f"_Test EF Item Spec {sfx}", supplier, self.company)
		po = _build_po_doc(
			{
				"supplier": supplier,
				"items": [
					{
						"item_code": item,
						"qty": 5,
						"rate": 50,
						"specification": "USP grade, min 99% purity",
						"packaging": "25 kg HDPE drums",
					}
				],
			},
			validate_remaining=False,
		).insert(ignore_permissions=True)
		po.reload()
		self.assertEqual(po.items[0].specification, "USP grade, min 99% purity")
		self.assertEqual(po.items[0].packaging, "25 kg HDPE drums")

	def test_so_procurement_excludes_edited_po(self):
		"""Feedback #10: get_so_procurement(exclude_po=...) drops that draft PO's own
		contribution so the PO edit form's live "remaining on SO" doesn't double-count."""
		from exportflow.api import _build_po_doc, get_so_procurement

		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Sup Rem {sfx}")
		item = make_dropship_item(f"_Test EF Item Rem {sfx}", supplier, self.company)
		customer = make_customer(f"_Test EF Cust Rem {sfx}")
		so = make_dropship_so(customer, self.company, [{"item_code": item, "qty": 100}])
		so_detail = so.items[0].name
		po = _build_po_doc(
			{
				"supplier": supplier,
				"items": [
					{"item_code": item, "qty": 40, "rate": 10, "sales_order": so.name, "so_detail": so_detail}
				],
			}
		).insert(ignore_permissions=True)

		base = {l["so_detail"]: l for l in get_so_procurement(so.name)["lines"]}[so_detail]
		self.assertEqual(base["draft_qty"], 40, "the draft PO covers 40")
		self.assertEqual(base["remaining"], 60)

		excl = {
			l["so_detail"]: l for l in get_so_procurement(so.name, exclude_po=po.name)["lines"]
		}[so_detail]
		self.assertEqual(excl["draft_qty"], 0, "this PO's own draft is excluded")
		self.assertEqual(excl["remaining"], 100)

	def test_doc_attachments_list_and_remove(self):
		"""Feedback #17: generic multi-file attachments on a Sales/Purchase Order —
		list returns attached files, remove deletes only an attached file, and the
		doctype allow-list is enforced."""
		from frappe.utils.file_manager import save_file

		from exportflow.api import list_doc_attachments, remove_doc_attachment

		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Sup Att {sfx}")
		item = make_dropship_item(f"_Test EF Item Att {sfx}", supplier, self.company)
		customer = make_customer(f"_Test EF Cust Att {sfx}")
		so = make_dropship_so(customer, self.company, [{"item_code": item, "qty": 5}])

		filedoc = save_file("spec.txt", "specification text", "Sales Order", so.name, is_private=1)
		rows = list_doc_attachments("Sales Order", so.name)
		self.assertEqual(len(rows), 1)
		# frappe appends a hash to the stored name; match the file we just attached
		self.assertEqual(rows[0]["file_url"], filedoc.file_url)
		self.assertTrue(rows[0]["file_name"].startswith("spec"))

		remove_doc_attachment("Sales Order", so.name, filedoc.file_url)
		self.assertEqual(len(list_doc_attachments("Sales Order", so.name)), 0)
		self.assertFalse(frappe.db.exists("File", filedoc.name), "the File row is deleted")

		with self.assertRaises(frappe.ValidationError):
			list_doc_attachments("Item", item)

	def test_amend_is_idempotent_and_recoverable(self):
		"""Feedback #4: amend is idempotent + recoverable — a retry after the original
		is cancelled returns the SAME draft (no re-cancel / duplicate), and
		get_amended_draft / _doc_can.resume_amend surface it for "Continue amendment"."""
		from exportflow.api import _doc_can, amend_document, get_amended_draft

		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Sup Amend {sfx}")
		item = make_dropship_item(f"_Test EF Item Amend {sfx}", supplier, self.company)
		customer = make_customer(f"_Test EF Cust Amend {sfx}")
		so = make_dropship_so(customer, self.company, [{"item_code": item, "qty": 10}])

		first = amend_document("Sales Order", so.name)
		self.assertFalse(first["resumed"], "first amend cancels + creates a draft")
		draft = first["name"]
		self.assertEqual(frappe.db.get_value("Sales Order", so.name, "docstatus"), 2, "original cancelled")
		self.assertEqual(frappe.db.get_value("Sales Order", draft, "amended_from"), so.name)

		# the original is now Cancelled (docstatus=2) — a retry must NOT throw the
		# "only a submitted document can be amended" guard, but return the same draft
		again = amend_document("Sales Order", so.name)
		self.assertTrue(again["resumed"], "retry resumes the existing draft")
		self.assertEqual(again["name"], draft, "no duplicate draft is created")

		self.assertEqual(get_amended_draft("Sales Order", so.name)["name"], draft)
		self.assertTrue(_doc_can("Sales Order", so.name).get("resume_amend"))

	def test_no_stock_movement_through_delivery(self):
		"""Spec §4.1: the full drop-ship leg — SO → PO → supplier delivers
		directly — produces no Delivery Note and no stock ledger entries."""
		from erpnext.buying.doctype.purchase_order.purchase_order import update_status

		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Supplier SLE {sfx}")
		item = make_dropship_item(f"_Test EF Item E {sfx}", supplier, self.company)
		customer = make_customer(f"_Test EF Customer SLE {sfx}")

		so = make_dropship_so(customer, self.company, [{"item_code": item, "qty": 10}])

		po = make_purchase_order(so.name, selected_items=[{"item_code": item, "supplier": supplier}])[0]
		po.items[0].rate = 100
		po.save(ignore_permissions=True)
		po.submit()

		# Supplier ships straight to the port — mark the drop-ship PO delivered
		update_status("Delivered", po.name)

		so.reload()
		self.assertEqual(so.per_delivered, 100, "SO must be fully delivered via the drop-ship PO")
		self.assertFalse(
			frappe.db.exists("Delivery Note Item", {"against_sales_order": so.name}),
			"Drop-ship flow must not create Delivery Notes",
		)
		for voucher in (so.name, po.name):
			self.assertFalse(
				frappe.db.exists("Stock Ledger Entry", {"voucher_no": voucher}),
				f"Drop-ship flow must not create stock ledger entries ({voucher})",
			)

	def test_gst_export_deadline_computation(self):
		"""Spec §4.3: deadline = supplier invoice date + 90 days when the
		merchant export scheme applies."""
		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Supplier GST {sfx}")
		item = make_dropship_item(f"_Test EF Item F {sfx}", supplier, self.company)

		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"supplier": supplier,
				"company": self.company,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 15),
				"supplier_invoice_no": f"SI-{sfx}",
				"supplier_invoice_date": "2026-06-01",
				"items": [{"item_code": item, "qty": 5, "rate": 100, "schedule_date": add_days(nowdate(), 15)}],
			}
		).insert(ignore_permissions=True)

		self.assertEqual(po.merchant_export_scheme, 1, "Scheme must default from the supplier on new POs")
		self.assertEqual(str(po.gst_export_deadline), "2026-08-30")

		po.merchant_export_scheme = 0
		po.save(ignore_permissions=True)
		self.assertFalse(po.gst_export_deadline, "Deadline must clear when the scheme is unchecked")

	def test_deadline_recomputes_on_submitted_po(self):
		"""The supplier invoice arrives only after PO submission — the fields
		are editable on submitted POs and the deadline recomputes there."""
		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Supplier Sub {sfx}")
		item = make_dropship_item(f"_Test EF Item G {sfx}", supplier, self.company)

		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"supplier": supplier,
				"company": self.company,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 15),
				"items": [{"item_code": item, "qty": 5, "rate": 100, "schedule_date": add_days(nowdate(), 15)}],
			}
		).insert(ignore_permissions=True)
		self.assertFalse(po.gst_export_deadline, "No deadline before the supplier invoice exists")
		po.submit()

		po.supplier_invoice_no = f"SI-{sfx}"
		po.supplier_invoice_date = "2026-06-15"
		po.save(ignore_permissions=True)

		po.reload()
		self.assertEqual(
			str(po.gst_export_deadline), "2026-09-13", "Deadline must recompute on a submitted PO"
		)

	def test_amended_po_keeps_unchecked_scheme(self):
		"""Amending a PO whose scheme was deliberately unchecked must not
		silently re-enable it from the supplier default."""
		sfx = _suffix()
		supplier = make_supplier(f"_Test EF Supplier Amend {sfx}")  # default scheme = 1
		item = make_dropship_item(f"_Test EF Item H {sfx}", supplier, self.company)

		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"supplier": supplier,
				"company": self.company,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 15),
				"items": [{"item_code": item, "qty": 5, "rate": 100, "schedule_date": add_days(nowdate(), 15)}],
			}
		).insert(ignore_permissions=True)
		self.assertEqual(po.merchant_export_scheme, 1, "Defaults from supplier on first insert")

		po.merchant_export_scheme = 0
		po.save(ignore_permissions=True)
		po.submit()
		po.cancel()

		amended = frappe.copy_doc(po)
		amended.amended_from = po.name
		amended.docstatus = 0
		amended.insert(ignore_permissions=True)
		self.assertEqual(
			amended.merchant_export_scheme, 0, "Amendment must keep the user's unchecked scheme"
		)

	def test_shipment_marks_fully_shipped_po_delivered(self):
		"""Booking shipments that cumulatively cover a drop-ship PO flips it to
		Delivered (and advances the SO) — a partial shipment leaves it open."""
		from exportflow.api import create_shipment

		sfx = _suffix()
		supplier = make_supplier(f"_Test EF AD Sup {sfx}")
		item = make_dropship_item(f"_Test EF AD Item {sfx}", supplier, self.company)
		customer = make_customer(f"_Test EF AD Cust {sfx}")
		so = make_dropship_so(customer, self.company, [{"item_code": item, "qty": 100}])
		po = make_purchase_order(so.name, selected_items=[{"item_code": item, "supplier": supplier}])[0]
		po.items[0].rate = 50
		po.save(ignore_permissions=True)
		po.submit()

		row, po_row = so.items[0], po.items[0]

		def ship(qty):
			create_shipment(
				{
					"customer": customer,
					"mode": "Sea",
					"items": [
						{
							"item_code": item,
							"qty": qty,
							"uom": row.uom,
							"sales_order": so.name,
							"so_detail": row.name,
							"purchase_order": po.name,
							"po_detail": po_row.name,
						}
					],
				}
			)

		ship(40)  # partial — PO stays open
		po.reload()
		self.assertNotEqual(po.status, "Delivered", "a partly-shipped PO must stay open")

		ship(60)  # now fully covered (40 + 60 = 100)
		po.reload()
		self.assertEqual(po.status, "Delivered", "a fully-shipped PO must flip to Delivered")
		so.reload()
		self.assertEqual(so.per_delivered, 100, "the SO must show fully delivered")
