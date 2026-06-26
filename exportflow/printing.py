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
from frappe.utils import cint, flt

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


def _plain(html: str | None) -> str | None:
	"""A Text-Editor field (e.g. Item.description, which carries the full chemical /
	IUPAC name the invoice prints) flattened to a single clean plain-text run."""
	if not html:
		return None
	import re
	from html import unescape

	text = re.sub(r"<[^>]+>", " ", html)
	text = re.sub(r"\s+", " ", unescape(text)).strip()
	return text or None


def _manufacturer_name(mfg: str | None) -> str | None:
	"""Resolve an Item's default manufacturer link to its display name for the
	invoice / packing-list 'MFG' line."""
	if not mfg:
		return None
	return frappe.db.get_value("Manufacturer", mfg, "full_name") or mfg


def _parse_drums(detail: str | None, net_per: float, tare_per: float) -> list:
	"""Individually-weighed drums for a batch, so the packing list itemises each
	drum (net uniform, tare/gross per drum) exactly as the client's document does.
	Each non-blank line is one drum: a single number is that drum's TARE (net stays
	the uniform net_per); 'net,tare' (comma or space) varies both. Blank → fall back
	to the uniform num_packages × per-pkg form."""
	import re

	drums = []
	for ln in (detail or "").splitlines():
		ln = ln.strip()
		if not ln:
			continue
		parts = [x for x in re.split(r"[,\s]+", ln) if x]
		try:
			if len(parts) >= 2:
				net, tare = flt(parts[0]), flt(parts[1])
			else:
				net, tare = flt(net_per), flt(parts[0])
		except (ValueError, TypeError):
			continue
		drums.append(frappe._dict(net=flt(net, 2), tare=flt(tare, 2), gross=flt(net + tare, 2)))
	return drums


def _logo_data_uri() -> str | None:
	"""The company logo as a base64 data URI, read straight from the File content.
	Embedding it avoids depending on the web server serving /files (which is
	misconfigured on this multi-tenant bench) and is what lets wkhtmltopdf render
	the logo inline in the PDF."""
	url = frappe.db.get_single_value("ExportFlow Settings", "company_logo")
	if not url:
		return None
	try:
		import base64
		import mimetypes

		names = frappe.get_all("File", filters={"file_url": url}, pluck="name", limit=1)
		if not names:
			return None
		content = frappe.get_doc("File", names[0]).get_content()
		if isinstance(content, str):
			content = content.encode()
		mime = mimetypes.guess_type(url)[0] or "image/png"
		return f"data:{mime};base64,{base64.b64encode(content).decode()}"
	except Exception:
		return None


def _app_img_uri(filename: str) -> str | None:
	"""A static image shipped in the app (exportflow/public/img) as a base64 data URI —
	read straight from disk so it embeds inline in wkhtmltopdf (the certification badge
	strip + the brand rule on the letterhead, which must render identically every time)."""
	try:
		import base64
		import mimetypes

		path = frappe.get_app_path("exportflow", "public", "img", filename)
		with open(path, "rb") as f:
			data = f.read()
		mime = mimetypes.guess_type(filename)[0] or "image/png"
		return f"data:{mime};base64,{base64.b64encode(data).decode()}"
	except Exception:
		return None


def _letterhead_address(exporter_address: str | None):
	"""Split the free-text exporter address into a one-line address + a contact line
	for the centred letterhead block (street + city on one line, the 'Tel ... · email'
	line separate)."""
	import re

	lines = [ln.strip().rstrip(",").strip() for ln in (exporter_address or "").split("\n") if ln.strip()]
	# match a real contact line ("Tel ...", "Phone:", "Fax", "Email") on a word
	# boundary so a state like "Telangana" is NOT mistaken for the phone line
	def _is_contact(ln):
		return bool(re.match(r"^(tel|phone|ph|mob|mobile|fax|e-?mail)\b", ln, re.I))

	contact = next((ln for ln in lines if _is_contact(ln)), "")
	addr = ", ".join(ln for ln in lines if not _is_contact(ln))
	return addr, contact


def _flatten_address_html(html: str | None) -> str | None:
	"""get_address_display returns <br>-joined HTML; flatten it to clean multi-line PLAIN
	text so the template can render it with `| e` inside white-space:pre-wrap, exactly like
	the free-text exporter address (| striptags would collapse it to one run-on line).
	Empty Address fields render as the literal 'None' (e.g. a missing pincode → 'None
	BERLIN') — strip those stray tokens so they never reach a printed document."""
	if not html:
		return None
	import re
	from html import unescape

	text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
	text = re.sub(r"<[^>]+>", "", text)
	lines = []
	for ln in unescape(text).splitlines():
		ln = re.sub(r"\bNone\b", "", ln)  # drop stray 'None' rendered from an empty field
		ln = re.sub(r"\s+", " ", ln).strip().rstrip(",").strip()
		if ln:
			lines.append(ln)
	return "\n".join(lines) or None


def party_address(party_type: str, party: str) -> str | None:
	"""Default address of a party as clean multi-line PLAIN text — for the PO / SO
	print blocks."""
	return _flatten_address_html(_address_display(party_type, party))


def _gst_state_map() -> dict:
	"""GST state-code → state-name (india_compliance); empty where it isn't installed."""
	try:
		from india_compliance.gst_india.constants import STATE_NUMBERS

		return {code: name for name, code in STATE_NUMBERS.items()}
	except Exception:
		return {}


def _state_from_gstin(gstin: str | None):
	"""State name + 2-digit code from a GSTIN (the leading two digits)."""
	if not gstin or len(gstin) < 2:
		return None, None
	code = gstin[:2]
	return _gst_state_map().get(code), code


def _pan_from_gstin(gstin: str | None) -> str | None:
	"""PAN embedded in a GSTIN — characters 3-12 (2-digit state + 10-char PAN + 3)."""
	return gstin[2:12] if gstin and len(gstin) >= 12 else None


def exporter_profile():
	"""The exporter's identity (ExportFlow Settings + company) for the PO / SO
	print blocks — the same details the shipment documents show. Registered as a
	jinja method."""
	settings = frappe.get_single("ExportFlow Settings")
	company = exportflow_company()
	lh_addr, lh_contact = _letterhead_address(settings.exporter_address)
	state_name, state_code = _state_from_gstin(settings.gstin)
	return frappe._dict(
		company_name=frappe.db.get_value("Company", company, "company_name") or company,
		address=settings.exporter_address,
		letterhead_addr=lh_addr,
		letterhead_contact=lh_contact,
		gstin=settings.gstin,
		iec=settings.iec_number,
		lut=settings.lut_number,
		pan=_pan_from_gstin(settings.gstin),
		cin=settings.get("cin"),
		jurisdiction=settings.get("jurisdiction"),
		statutory_lines=settings.get("statutory_lines"),
		state_name=state_name,
		state_code=state_code,
		signatory_name=settings.signatory_name,
		signatory_designation=settings.signatory_designation,
		logo=_logo_data_uri(),
		cert_badges=_app_img_uri("mn_certs.png"),
		gradient_rule=_app_img_uri("mn_rule.png"),
	)


def address_text(address_name: str | None) -> str | None:
	"""A specific Address (by name) as clean multi-line plain text — for documents that
	carry a CHOSEN address (PO supplier_address, SO customer_address) rather than the
	party's default. Registered as a jinja method."""
	if not address_name:
		return None
	return _flatten_address_html(_address_display_by_name(address_name))


def _address_display_by_name(address_name: str) -> str | None:
	try:
		from frappe.contacts.doctype.address.address import get_address_display

		return get_address_display(address_name)
	except Exception:
		return None


def supplier_profile(supplier: str, supplier_gstin: str | None = None, address_name: str | None = None):
	"""Supplier identity for the PO 'Supplier (Bill from)' block — name, address,
	GSTIN + derived state/PAN, and the primary contact's name / phone / email. When the
	PO carries a chosen supplier_address, that address prints (not the default).
	Registered as a jinja method."""
	meta = frappe.get_meta("Supplier")
	want = [f for f in ["supplier_name", "gstin", "pan", "mobile_no", "email_id", "supplier_primary_contact"] if meta.has_field(f)]
	sup = (frappe.db.get_value("Supplier", supplier, want, as_dict=True) if want else None) or frappe._dict()
	gstin = supplier_gstin or sup.get("gstin")
	state_name, state_code = _state_from_gstin(gstin)
	contact_person = None
	if sup.get("supplier_primary_contact"):
		cp = frappe.db.get_value("Contact", sup.supplier_primary_contact, ["first_name", "last_name"], as_dict=True)
		if cp:
			contact_person = (" ".join(x for x in [cp.first_name, cp.last_name] if x)).strip() or None
	return frappe._dict(
		name=sup.get("supplier_name") or supplier,
		address=address_text(address_name) or party_address("Supplier", supplier),
		gstin=gstin,
		pan=sup.get("pan") or _pan_from_gstin(gstin),
		state_name=state_name,
		state_code=state_code,
		mobile=sup.get("mobile_no"),
		email=sup.get("email_id"),
		contact_person=contact_person,
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

	# per-batch packing detail, grouped by item — each group's net/tare/gross is
	# (count × per-package weight), exactly as the packing list itemises it
	packs_by_item: dict[str, list] = {}
	for p in shipment.get("packs") or []:
		# individually-weighed drums (optional) take precedence over the uniform
		# num_packages × per-pkg weights, and drive the per-drum packing-list lines
		drums = _parse_drums(p.get("drum_detail"), p.net_per, p.tare_per)
		if drums:
			num = len(drums)
			net = sum(d.net for d in drums)
			tare = sum(d.tare for d in drums)
			net_uniform = len({d.net for d in drums}) <= 1
		else:
			num = cint(p.num_packages)
			net = flt(p.num_packages) * flt(p.net_per)
			tare = flt(p.num_packages) * flt(p.tare_per)
			net_uniform = True
		packs_by_item.setdefault(p.item_code, []).append(
			frappe._dict(
				batch_no=p.batch_no,
				marks=p.marks,
				num_packages=num,
				pack_type=p.pack_type,
				net_per=flt(p.net_per),
				tare_per=flt(p.tare_per),
				gross_per=flt(p.net_per) + flt(p.tare_per),
				mfg_date=p.mfg_date,
				exp_date=p.exp_date,
				drums=drums,
				net_uniform=net_uniform,
				net=flt(net, 2),
				tare=flt(tare, 2),
				gross=flt(net + tare, 2),
			)
		)

	# items enriched with master + SO-line data (rate/currency come from the deal)
	items = []
	currencies = set()
	named_places = []
	payment_terms = None
	total = 0.0
	fob_inr = 0.0
	net_total_wt = tare_total_wt = gross_total_wt = 0.0
	pkg_total = 0
	for row in shipment.items:
		so_line = frappe.db.get_value(
			"Sales Order Item", row.so_detail, ["rate", "base_rate", "parent"], as_dict=True
		) or frappe._dict()
		so = (
			frappe.db.get_value(
				"Sales Order",
				so_line.parent,
				["currency", "incoterm", "named_place", "payment_terms_narrative"],
				as_dict=True,
			)
			if so_line.parent
			else frappe._dict()
		) or frappe._dict()
		if so.currency:
			currencies.add(so.currency)
		if so.named_place and so.named_place not in named_places:
			named_places.append(so.named_place)
		if so.get("payment_terms_narrative") and not payment_terms:
			payment_terms = so.payment_terms_narrative
		item = frappe.db.get_value(
			"Item",
			row.item_code,
			[
				"item_name",
				"description",
				"customs_tariff_number",
				"pharmacopoeia_grade",
				"country_of_origin",
				"cas_number",
				"default_pack_size",
				"default_item_manufacturer",
			],
			as_dict=True,
		) or frappe._dict()
		rate = flt(so_line.rate)
		amount = flt(rate * flt(row.qty), 2)
		total += amount
		# FOB in INR (the SO line's company-currency rate) — the FEMA / drawback
		# declarations state the export value in rupees
		fob_inr += flt(so_line.get("base_rate")) * flt(row.qty)
		# attach this line's packing groups + roll up its weights
		line_packs = packs_by_item.get(row.item_code, [])
		line_net = flt(sum(g.net for g in line_packs), 2)
		line_tare = flt(sum(g.tare for g in line_packs), 2)
		line_gross = flt(sum(g.gross for g in line_packs), 2)
		net_total_wt += line_net
		tare_total_wt += line_tare
		gross_total_wt += line_gross
		pkg_total += sum(g.num_packages for g in line_packs)
		item_name = row.item_name or item.item_name or row.item_code
		description = _plain(item.get("description"))
		items.append(
			frappe._dict(
				item_code=row.item_code,
				item_name=item_name,
				# the full chemical / IUPAC name the invoice prints under the item name
				description=description if description and description != item_name else None,
				grade=item.pharmacopoeia_grade,
				hs_code=item.customs_tariff_number,
				cas_number=item.cas_number,
				country_of_origin=item.country_of_origin or "India",
				pack_size=item.get("default_pack_size"),
				manufacturer=_manufacturer_name(item.get("default_item_manufacturer")),
				batch_no=row.batch_no,
				qty=flt(row.qty),
				uom=row.uom,
				rate=rate,
				amount=amount,
				pack_description=row.pack_description,
				packs=line_packs,
				net_wt=line_net,
				tare_wt=line_tare,
				gross_wt=line_gross,
			)
		)

	currency = next(iter(currencies)) if len(currencies) == 1 else None
	ad_code = (
		frappe.db.get_value("Port", shipment.port_of_loading, "ad_code")
		if shipment.port_of_loading
		else None
	)

	# §5.2: supplier GSTIN + invoice reference for 0.1%-scheme cargo, and the set of
	# domestic suppliers feeding this shipment (the invoice's "MFG" / manufacturer line)
	scheme_suppliers = []
	po_supplier_names = []
	for po_name in sorted({r.purchase_order for r in shipment.items if r.purchase_order}):
		po = frappe.db.get_value(
			"Purchase Order",
			po_name,
			["supplier", "supplier_name", "merchant_export_scheme", "supplier_invoice_no",
			 "supplier_invoice_date", "docstatus"],
			as_dict=True,
		)
		if not po:
			continue
		sup_name = po.supplier_name or po.supplier
		if sup_name and sup_name not in po_supplier_names:
			po_supplier_names.append(sup_name)
		if po.merchant_export_scheme and po.docstatus == 1:
			scheme_suppliers.append(
				frappe._dict(
					purchase_order=po_name,
					supplier_name=sup_name,
					gstin=_supplier_gstin(po.supplier),
					invoice_no=po.supplier_invoice_no,
					invoice_date=po.supplier_invoice_date,
				)
			)

	# MFG line: the goods' manufacturer(s) — prefer an item-level manufacturer, else
	# fall back to the domestic PO supplier(s) the merchant exporter bought from
	item_manufacturers = []
	for ln in items:
		if ln.manufacturer and ln.manufacturer not in item_manufacturers:
			item_manufacturers.append(ln.manufacturer)
	manufacturers = item_manufacturers or po_supplier_names

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

	from exportflow.mtt import is_merchanting

	merchanting = is_merchanting(shipment.trade_type)

	# consignee: "TO THE ORDER", an explicit party, or (default) the buyer itself.
	# the address is always plain text with real newlines (party_address flattens
	# get_address_display's <br> HTML) so the template's `| e` + pre-wrap renders it
	# cleanly — using customer_address (raw <br> HTML) here would print literal tags.
	if shipment.get("consignee_to_order"):
		consignee_name, consignee_address = "TO THE ORDER", None
	elif shipment.get("consignee_name") or shipment.get("consignee_address"):
		consignee_name = shipment.consignee_name or customer_name
		consignee_address = shipment.consignee_address or party_address("Customer", shipment.customer)
	else:
		consignee_name = customer_name
		consignee_address = party_address("Customer", shipment.customer)
	# when the consignee resolves to the buyer, the Buyer block just repeats it
	consignee_is_buyer = not shipment.get("consignee_to_order") and consignee_name == customer_name

	# money: goods + freight + insurance = the incoterm (CFR/CIF/CIP) total
	freight = flt(shipment.get("freight_amount"))
	insurance = flt(shipment.get("insurance_amount"))
	goods_total = flt(total, 2)
	grand_total = flt(goods_total + freight + insurance, 2)

	# GST declaration mode — suppressed entirely for merchanting (outside GST)
	gst_export_mode = None if merchanting else (shipment.get("gst_export_mode") or "Under LUT (without IGST)")
	igst_rate = flt(shipment.get("igst_rate"))
	inr_rate = flt(shipment.get("inr_rate"))
	taxable_value_inr = igst_amount = None
	if gst_export_mode == "On payment of IGST" and inr_rate:
		taxable_value_inr = flt(grand_total * inr_rate, 2)
		igst_amount = flt(taxable_value_inr * igst_rate / 100.0, 2)

	# exporter collection bank (for the buyer's remittance) — the correspondent /
	# Nostro bank, its own SWIFT and the routing no print as discrete lines, as the
	# client's banker block carries them
	bank = frappe._dict(
		account_no=settings.get("bank_account_no"),
		name=settings.get("bank_name"),
		branch=settings.get("bank_branch_address"),
		ifsc=settings.get("bank_ifsc"),
		swift=settings.get("bank_swift"),
		correspondent=settings.get("bank_correspondent"),
		correspondent_swift=settings.get("bank_correspondent_swift"),
		routing_no=settings.get("bank_routing_no"),
	)
	has_bank = any(bank.values())

	incoterm_label = shipment.incoterm or ("FOB" if not (freight or insurance) else "CIF")

	# AD bank for the FEMA / SDF declaration — the merchanting AD bank, else the
	# bank named on a realization booked against this shipment
	ad_bank = shipment.get("mtt_ad_bank") or frappe.db.get_value(
		"Export Realization", {"shipment": shipment.name}, "ad_bank"
	)

	lh_addr, lh_contact = _letterhead_address(settings.exporter_address)
	return frappe._dict(
		instance=inst,
		shipment=shipment,
		company_name=company_name,
		logo=_logo_data_uri(),
		cert_badges=_app_img_uri("mn_certs.png"),
		gradient_rule=_app_img_uri("mn_rule.png"),
		exporter_address=settings.exporter_address,
		letterhead_addr=lh_addr,
		letterhead_contact=lh_contact,
		iec_number=settings.iec_number,
		gstin=settings.gstin,
		cin=settings.get("cin"),
		jurisdiction=settings.get("jurisdiction"),
		ad_code=ad_code,
		lut_number=settings.lut_number,
		lut_valid_upto=settings.lut_valid_upto,
		signatory_name=settings.signatory_name,
		signatory_designation=settings.signatory_designation,
		scomet_text=settings.scomet_text,
		merchanting=merchanting,
		customer_name=customer_name,
		customer_address=customer_address,
		consignee_name=consignee_name,
		consignee_address=consignee_address,
		consignee_is_buyer=consignee_is_buyer,
		notify_party=shipment.get("notify_party"),
		destination_country=destination_country,
		incoterm=shipment.incoterm,
		incoterm_label=incoterm_label,
		named_place=", ".join(named_places) if named_places else shipment.final_destination,
		buyer_order_no=shipment.get("buyer_order_no"),
		buyer_order_date=shipment.get("buyer_order_date"),
		payment_terms=payment_terms,
		manufacturers=manufacturers,
		claim_rodtep=cint(shipment.get("claim_rodtep")),
		rodtep_rate_pct=flt(shipment.get("rodtep_rate_pct")),
		claim_drawback=cint(shipment.get("claim_drawback")),
		drawback_rate_pct=flt(shipment.get("drawback_rate_pct")),
		# "lines", not "items" — on a _dict, jinja's ctx.items resolves to the
		# dict method, not the key
		lines=items,
		currency=currency,
		mixed_currencies=len(currencies) > 1,
		total=goods_total,
		freight=freight,
		insurance=insurance,
		grand_total=grand_total,
		fob_value_inr=flt(fob_inr, 2),
		ad_bank=ad_bank,
		net_total_wt=flt(net_total_wt, 2),
		tare_total_wt=flt(tare_total_wt, 2),
		gross_total_wt=flt(gross_total_wt, 2),
		total_packages=pkg_total,
		packs_present=any(line.packs for line in items),
		gst_export_mode=gst_export_mode,
		igst_rate=igst_rate,
		taxable_value_inr=taxable_value_inr,
		igst_amount=igst_amount,
		bank=bank,
		has_bank=has_bank,
		scheme_suppliers=scheme_suppliers,
		lc=lc,
		lc_requirements=lc_requirements,
		invoice_number=invoice_number,
		invoice_date=invoice_date,
		transport_doc=transport_doc,
		total_in_words=frappe.utils.money_in_words(goods_total, currency) if currency else None,
		grand_total_in_words=frappe.utils.money_in_words(grand_total, currency) if currency else None,
	)
