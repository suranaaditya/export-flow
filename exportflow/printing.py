"""Context builder for the Phase-4 print formats (spec §5.2).

The three shipment documents (Commercial Invoice / Packing List / SCOMET
declaration) print from a Document Instance: the instance carries the
document's own number and date, this builder assembles everything else from
the shipment graph. Registered as a jinja method in hooks.py so the templates
stay free of query logic — swapping the client's letterhead later only
touches HTML.
"""

import frappe
from frappe import _
from frappe.utils import flt

from exportflow.company import exportflow_company


def _address_display(party_type: str, party: str) -> str | None:
	try:
		from frappe.contacts.doctype.address.address import get_address_display, get_default_address

		address = get_default_address(party_type, party)
		return get_address_display(address) if address else None
	except Exception:
		return None


def _supplier_gstin(supplier: str) -> str | None:
	# gstin is an india_compliance field — absent on benches without it
	if not frappe.get_meta("Supplier").has_field("gstin"):
		return None
	return frappe.db.get_value("Supplier", supplier, "gstin")


def party_address(party_type: str, party: str) -> str | None:
	"""Default address of a party as clean multi-line PLAIN text — for the PO / SO
	print blocks. get_address_display returns <br>-joined HTML, which | striptags
	would collapse to one run-on line; we flatten the <br>s to real newlines so the
	template can render it with `| e` inside white-space:pre-wrap, exactly like the
	free-text exporter address."""
	import re
	from html import unescape

	html = _address_display(party_type, party)
	if not html:
		return None
	text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
	text = re.sub(r"<[^>]+>", "", text)
	lines = [ln.strip().rstrip(",").strip() for ln in unescape(text).splitlines()]
	return "\n".join(ln for ln in lines if ln) or None


def exporter_profile():
	"""The exporter's identity (ExportFlow Settings + company) for the PO / SO
	print blocks — the same details the shipment documents show. Registered as a
	jinja method."""
	settings = frappe.get_single("ExportFlow Settings")
	company = exportflow_company()
	return frappe._dict(
		company_name=frappe.db.get_value("Company", company, "company_name") or company,
		address=settings.exporter_address,
		gstin=settings.gstin,
		iec=settings.iec_number,
		lut=settings.lut_number,
		signatory_name=settings.signatory_name,
		signatory_designation=settings.signatory_designation,
		logo=frappe.utils.get_url(settings.company_logo) if settings.company_logo else None,
	)


def document_print_context(name: str):
	"""Everything the ExportFlow shipment print formats render."""
	inst = frappe.get_doc("Document Instance", name)
	if not inst.shipment:
		frappe.throw(_("Document {0} is not attached to a shipment").format(name))
	shipment = frappe.get_doc("Export Shipment", inst.shipment)
	settings = frappe.get_single("ExportFlow Settings")

	company = exportflow_company()
	company_name = frappe.db.get_value("Company", company, "company_name") or company

	customer_name = shipment.customer_name or shipment.customer
	customer_address = _address_display("Customer", shipment.customer)
	destination_country = frappe.db.get_value(
		"Customer", shipment.customer, "destination_country"
	)

	# items enriched with master + SO-line data (rate/currency come from the deal)
	items = []
	currencies = set()
	named_places = []
	total = 0.0
	for row in shipment.items:
		so_line = frappe.db.get_value(
			"Sales Order Item", row.so_detail, ["rate", "parent"], as_dict=True
		) or frappe._dict()
		so = (
			frappe.db.get_value(
				"Sales Order",
				so_line.parent,
				["currency", "incoterm", "named_place"],
				as_dict=True,
			)
			if so_line.parent
			else frappe._dict()
		) or frappe._dict()
		if so.currency:
			currencies.add(so.currency)
		if so.named_place and so.named_place not in named_places:
			named_places.append(so.named_place)
		item = frappe.db.get_value(
			"Item",
			row.item_code,
			["item_name", "customs_tariff_number", "pharmacopoeia_grade", "country_of_origin"],
			as_dict=True,
		) or frappe._dict()
		rate = flt(so_line.rate)
		amount = flt(rate * flt(row.qty), 2)
		total += amount
		items.append(
			frappe._dict(
				item_code=row.item_code,
				item_name=row.item_name or item.item_name or row.item_code,
				grade=item.pharmacopoeia_grade,
				hs_code=item.customs_tariff_number,
				country_of_origin=item.country_of_origin or "India",
				batch_no=row.batch_no,
				qty=flt(row.qty),
				uom=row.uom,
				rate=rate,
				amount=amount,
				pack_description=row.pack_description,
			)
		)

	currency = next(iter(currencies)) if len(currencies) == 1 else None
	ad_code = (
		frappe.db.get_value("Port", shipment.port_of_loading, "ad_code")
		if shipment.port_of_loading
		else None
	)

	# §5.2: supplier GSTIN + invoice reference for 0.1%-scheme cargo
	scheme_suppliers = []
	for po_name in sorted({r.purchase_order for r in shipment.items if r.purchase_order}):
		po = frappe.db.get_value(
			"Purchase Order",
			po_name,
			["supplier", "supplier_name", "merchant_export_scheme", "supplier_invoice_no",
			 "supplier_invoice_date", "docstatus"],
			as_dict=True,
		)
		if po and po.merchant_export_scheme and po.docstatus == 1:
			scheme_suppliers.append(
				frappe._dict(
					purchase_order=po_name,
					supplier_name=po.supplier_name or po.supplier,
					gstin=_supplier_gstin(po.supplier),
					invoice_no=po.supplier_invoice_no,
					invoice_date=po.supplier_invoice_date,
				)
			)

	lc = None
	lc_requirements = []
	if shipment.letter_of_credit:
		lc_doc = frappe.get_doc("Letter of Credit", shipment.letter_of_credit)
		lc = frappe._dict(
			name=lc_doc.name,
			lc_number=lc_doc.lc_number,
			issuing_bank=lc_doc.get("issuing_bank"),
			advising_bank=lc_doc.get("advising_bank"),
			negotiating_bank=lc_doc.get("negotiating_bank"),
			amount=lc_doc.get("amount"),
			currency=lc_doc.get("currency"),
			issue_date=lc_doc.get("issue_date"),
			expiry_date=lc_doc.get("expiry_date"),
			latest_shipment_date=lc_doc.get("latest_shipment_date"),
			presentation_period_days=lc_doc.get("presentation_period_days") or 21,
		)
		lc_requirements = [
			frappe._dict(
				document_type=req.document_type,
				description=req.description,
				originals=req.originals,
				copies=req.copies,
			)
			for req in lc_doc.document_requirements
		]

	# the SCOMET declaration and packing list reference the commercial invoice
	invoice_number, invoice_date = frappe.db.get_value(
		"Document Instance",
		{"shipment": shipment.name, "document_type": "Commercial Invoice"},
		["document_number", "document_date"],
	) or (None, None)

	transport_doc = (
		frappe._dict(label="AWB", number=shipment.awb_number, date=shipment.awb_date)
		if shipment.mode == "Air"
		else frappe._dict(label="B/L", number=shipment.bl_number, date=shipment.bl_date)
	)

	return frappe._dict(
		instance=inst,
		shipment=shipment,
		company_name=company_name,
		logo=frappe.utils.get_url(settings.company_logo) if settings.company_logo else None,
		exporter_address=settings.exporter_address,
		iec_number=settings.iec_number,
		gstin=settings.gstin,
		ad_code=ad_code,
		lut_number=settings.lut_number,
		lut_valid_upto=settings.lut_valid_upto,
		signatory_name=settings.signatory_name,
		signatory_designation=settings.signatory_designation,
		scomet_text=settings.scomet_text,
		customer_name=customer_name,
		customer_address=customer_address,
		destination_country=destination_country,
		incoterm=shipment.incoterm,
		named_place=", ".join(named_places) if named_places else shipment.final_destination,
		# "lines", not "items" — on a _dict, jinja's ctx.items resolves to the
		# dict method, not the key
		lines=items,
		currency=currency,
		mixed_currencies=len(currencies) > 1,
		total=flt(total, 2),
		scheme_suppliers=scheme_suppliers,
		lc=lc,
		lc_requirements=lc_requirements,
		invoice_number=invoice_number,
		invoice_date=invoice_date,
		transport_doc=transport_doc,
		total_in_words=frappe.utils.money_in_words(flt(total, 2), currency) if currency else None,
	)
