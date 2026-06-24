"""Idempotent permission grants for the Export roles on standard doctypes.

Runs from after_install (fresh sites) and from a patch (existing sites).
Uses frappe.permissions.add_permission, which clones a doctype's standard
perms into Custom DocPerm before adding — so existing roles keep their access.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

EXPORT_ROLES = ("Export Admin", "Export Operations", "Export Accounts", "Export Viewer")

# doctype -> {role: [ptypes beyond read]}
TRANSACTION_PTYPES = ["create", "write", "submit", "cancel", "amend"]
MASTER_PTYPES = ["create", "write"]

GRANTS = {
	# deals are entered inside ExportFlow — Operations and Admin own them
	"Sales Order": {
		"Export Admin": TRANSACTION_PTYPES,
		"Export Operations": TRANSACTION_PTYPES,
		"Export Accounts": [],
		"Export Viewer": [],
	},
	"Bank Account": {role: [] for role in EXPORT_ROLES},
	"Purchase Order": {
		"Export Admin": TRANSACTION_PTYPES,
		"Export Operations": TRANSACTION_PTYPES,
		"Export Accounts": [],
		"Export Viewer": [],
	},
	"Payment Entry": {
		"Export Admin": TRANSACTION_PTYPES,
		"Export Accounts": TRANSACTION_PTYPES,
		"Export Operations": [],
		"Export Viewer": [],
	},
	# masters needed while entering a deal
	"Customer": {
		"Export Admin": MASTER_PTYPES,
		"Export Operations": MASTER_PTYPES,
		"Export Accounts": [],
		"Export Viewer": [],
	},
	"Supplier": {
		"Export Admin": MASTER_PTYPES,
		"Export Operations": MASTER_PTYPES,
		"Export Accounts": [],
		"Export Viewer": [],
	},
	"Item": {
		"Export Admin": MASTER_PTYPES,
		"Export Operations": MASTER_PTYPES,
		"Export Accounts": [],
		"Export Viewer": [],
	},
	"Purchase Taxes and Charges Template": {role: [] for role in EXPORT_ROLES},
	"Account": {
		"Export Admin": [],
		"Export Operations": [],
		"Export Accounts": [],
		"Export Viewer": [],
	},
	"Terms and Conditions": {
		"Export Admin": MASTER_PTYPES,
		"Export Operations": MASTER_PTYPES,
		"Export Accounts": [],
		"Export Viewer": [],
	},
	"Incoterm": {role: [] for role in EXPORT_ROLES},
	"Currency": {role: [] for role in EXPORT_ROLES},
	"Country": {role: [] for role in EXPORT_ROLES},
	"UOM": {
		"Export Admin": MASTER_PTYPES,
		"Export Operations": MASTER_PTYPES,
		"Export Accounts": [],
		"Export Viewer": [],
	},
	# warehouses a Goods Receipt Note receives into — read-only picklist for export roles
	"Warehouse": {role: [] for role in EXPORT_ROLES},
}


# transactions the React app prints
PRINTABLE = ("Purchase Order", "Sales Order")


def setup_export_role_permissions():
	for doctype, roles in GRANTS.items():
		for role, extra_ptypes in roles.items():
			if not frappe.db.exists("Role", role):
				continue
			# read at permlevel 0 (add_permission is a no-op if already granted)
			add_permission(doctype, role, permlevel=0)
			for ptype in extra_ptypes:
				update_permission_property(doctype, role, 0, ptype, 1, validate=False)
			if doctype in PRINTABLE:
				update_permission_property(doctype, role, 0, "print", 1, validate=False)
	frappe.clear_cache()


def seed_ports():
	"""Insert the curated port list; existing/renamed records are left alone."""
	from exportflow.ports_data import SEED_PORTS

	for port_name, unlocode, mode, city, country in SEED_PORTS:
		if frappe.db.exists("Port", port_name) or frappe.db.exists("Port", {"unlocode": unlocode}):
			continue
		frappe.get_doc(
			{
				"doctype": "Port",
				"port_name": port_name,
				"unlocode": unlocode,
				"mode": mode,
				"city": city,
				"country": country if frappe.db.exists("Country", country) else None,
			}
		).insert(ignore_permissions=True)


def seed_document_types():
	"""Spec §5.1 catalog. Existing records (possibly retuned by the client)
	are left untouched."""
	from exportflow.doc_catalog import DOCUMENT_TYPES

	for name, category, origin, responsible, attaches_to, extras in DOCUMENT_TYPES:
		if frappe.db.exists("Document Type", name):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Document Type",
				"document_type_name": name,
				"category": category,
				"origin": origin,
				"responsible_party": responsible,
				"attaches_to": attaches_to,
				**extras,
			}
		)
		# print formats land in the same migrate — don't fail on ordering
		if doc.get("default_print_format") and not frappe.db.exists(
			"Print Format", doc.default_print_format
		):
			doc.default_print_format = None
		doc.insert(ignore_permissions=True)


def seed_checklist_rules():
	"""Spec §5.3 base + conditional rules. Skips rules whose name exists and
	rules whose document type is missing (deleted by the client)."""
	from exportflow.doc_catalog import CHECKLIST_RULES

	for rule_name, document_type, conditions in CHECKLIST_RULES:
		if frappe.db.exists("Document Checklist Rule", rule_name):
			continue
		if not frappe.db.exists("Document Type", document_type):
			continue
		frappe.get_doc(
			{
				"doctype": "Document Checklist Rule",
				"rule_name": rule_name,
				"document_type": document_type,
				"enabled": 1,
				"conditions": [
					{"condition_field": field, "condition_value": value}
					for field, value in conditions
				],
			}
		).insert(ignore_permissions=True)


# Real Terms & Conditions templates — the *conditions* master (specification,
# packaging, inspection, incoterms, insurance, regulatory, material-return,
# governing law / arbitration), distinct from the payment-terms master below.
# Payment terms are stated separately on each order. [__] are fill-in placeholders.
_SELLING_TC = (
	"1. Specification & quality: The goods conform to the agreed specification and pharmacopoeial standard "
	"([IP/BP/USP/EP]) and are manufactured under valid GMP; each batch is accompanied by the manufacturer's "
	"Certificate of Analysis.\n"
	"2. Packaging & marking: Export-worthy pharmaceutical packing; each unit marked with product, batch number, "
	"manufacturing & expiry dates, quantity, net/gross weight, storage conditions and country of origin "
	"(\"Made in India\").\n"
	"3. Inspection: The goods are released by the seller's QA; any buyer or agency pre-shipment inspection is at "
	"the buyer's cost and does not waive the seller's warranty.\n"
	"4. Delivery (Incoterms 2020): Delivery per the Incoterms 2020 rule stated on the invoice "
	"([FOB/CIF/CIP] [named port/place]); under CIF/CIP the seller insures for 110% of the value.\n"
	"5. Shelf-life: The goods carry not less than [__]% of total shelf-life remaining at shipment.\n"
	"6. Regulatory & end-use: The buyer obtains all import licences and registrations in the destination country. "
	"Where the goods are SCOMET-listed, supply is conditional on DGFT authorisation and a buyer end-use "
	"certificate; the goods shall not be diverted in breach of applicable export-control or sanctions laws.\n"
	"7. Taxes: This is an export, zero-rated under Section 16 of the IGST Act, supplied under LUT without payment "
	"of IGST; all importing-country duties and taxes are to the buyer's account.\n"
	"8. Bank charges: Charges within India to the seller; charges outside India (including LC/confirmation/"
	"discrepancy) to the buyer.\n"
	"9. Force majeure: Neither party is liable for delay or failure caused by events beyond its reasonable "
	"control; the affected party shall notify within [__] days and mitigate.\n"
	"10. Governing law & disputes: Governed by the laws of India; disputes finally settled by arbitration under "
	"the Arbitration and Conciliation Act, 1996, seated at [city], India, in English; the courts at [city] have "
	"jurisdiction.\n"
	"Payment terms are as stated separately on this order."
)
_BUYING_TC = (
	"1. Specification & quality: The goods conform strictly to the agreed specification (ref [__]) and the "
	"relevant pharmacopoeial monograph, manufactured under valid cGMP; each batch is accompanied by a Certificate "
	"of Analysis in the supplier's name. No change of source, route, site or specification without the buyer's "
	"prior written approval.\n"
	"2. Packaging, marking & labelling: New, clean, tamper-evident pharma-grade containers; each marked with "
	"material, grade, batch/lot number, manufacturing & expiry/re-test dates, net/gross weight, container number "
	"(X of Y), storage conditions, manufacturer and the buyer's PO number.\n"
	"3. Material rejection & return: Acceptance is subject to the buyer's (or its customer's / the destination "
	"authority's) inspection and testing. Goods found defective, damaged, short, non-conforming, expired/"
	"short-dated, mislabelled or contaminated may be rejected by written notice notwithstanding prior payment or "
	"inspection. Rejected goods are held at the supplier's risk and, at the buyer's option, returned, destroyed "
	"or replaced; all costs (inbound and return freight, insurance, duties, testing, handling and destruction) "
	"are borne by the supplier, who shall within [7] days refund the price or supply conforming replacements "
	"within [15] days.\n"
	"4. Delivery: Time is of the essence. For merchant-export supply the goods move directly from the supplier's "
	"registered premises to the [port/ICD/airport] of export; the supplier gives at least [7] days' advance "
	"dispatch notice and makes no part shipment without the buyer's consent.\n"
	"5. Inspection: The buyer, its customer or a nominated agency may inspect and test at the supplier's premises "
	"before dispatch and on receipt; inspection or payment does not constitute acceptance.\n"
	"6. Regulatory documents: The supplier provides, as applicable, a valid GMP/WHO-GMP certificate, COPP, "
	"Certificate of Analysis, DMF/CEP, Written Confirmation and Safety Data Sheet.\n"
	"7. Shelf-life: At delivery the goods carry not less than [__]% of total shelf-life (or [__] months) "
	"remaining.\n"
	"8. Taxes: For domestic supply under the merchant-export scheme the supplier raises a tax invoice at 0.05% "
	"CGST + 0.05% SGST / 0.1% IGST per Notification 40/2017 & 41/2017; the buyer furnishes the PO to the "
	"supplier's jurisdictional officer and exports within 90 days of the tax invoice. For overseas merchanting "
	"supply, no Indian GST applies.\n"
	"9. Indemnity: The supplier indemnifies the buyer against claims from defective or non-conforming goods, IP "
	"infringement and breach of law. For domestic 0.1% supply the buyer indemnifies the supplier for the "
	"differential GST and interest caused solely by the buyer's failure to export within 90 days (save where the "
	"supplier's own delay caused it).\n"
	"10. Governing law & disputes: Domestic supply — the laws of India, arbitration under the Arbitration and "
	"Conciliation Act, 1996, seated at [city]; overseas supply — [neutral law] and [SIAC/ICC] arbitration, "
	"enforceable under the New York Convention.\n"
	"Payment terms are as stated separately on this order."
)
STANDARD_TC = [
	# (title, selling, buying, terms text)
	("Standard Export Sales Terms & Conditions", 1, 0, _SELLING_TC),
	("Standard Purchase Terms & Conditions", 0, 1, _BUYING_TC),
]


def seed_terms_templates():
	"""Insert the real spec/jurisdiction/incoterms/material-return Terms and Conditions
	templates so the SO and PO terms pickers have realistic examples. Payment terms now
	live in their own Export Payment Term master (seed_payment_terms), so payment-only
	sample rows are no longer seeded into the T&C master. Idempotent."""
	for title, selling, buying, terms in STANDARD_TC:
		if frappe.db.exists("Terms and Conditions", title):
			continue
		frappe.get_doc(
			{
				"doctype": "Terms and Conditions",
				"title": title,
				"selling": selling,
				"buying": buying,
				"terms": terms,
			}
		).insert(ignore_permissions=True)


# Payment-terms templates (Export Payment Term) — the payment-side master, the
# counterpart of Terms and Conditions, segregated by selling/buying.
SAMPLE_PAYMENT_TERMS = [
	# (template_name, selling, buying, terms text)
	("Sales — 100% advance (TT)", 1, 0,
	 "100% of the invoice value in advance by telegraphic transfer (T/T) before dispatch. Goods shipped within "
	 "[__] days of receipt of the full advance in cleared funds. Bank charges outside India to the buyer's account."),
	("Sales — 30% advance, 70% against documents", 1, 0,
	 "30% advance by T/T with order confirmation; balance 70% by T/T against scanned shipping documents before the "
	 "originals are released. Bank charges outside India to the buyer's account."),
	("Sales — Irrevocable LC at sight", 1, 0,
	 "100% irrevocable Letter of Credit at sight, confirmed by a prime international bank, advised through [bank], "
	 "operative at least [__] days before shipment and payable on presentation of the shipping documents (UCP 600). "
	 "LC, confirmation and discrepancy charges outside India to the buyer."),
	("Sales — Usance LC 90 days", 1, 0,
	 "Irrevocable usance Letter of Credit payable 90 days from Bill of Lading date for 100% of the invoice value, "
	 "advised through [bank], subject to UCP 600. LC and confirmation charges outside India to the buyer."),
	("Sales — Documents against Payment (D/P)", 1, 0,
	 "Documents against Payment (D/P) under URC 522: shipping documents released only against payment of 100% of "
	 "the invoice value at sight through banking channels. Overseas bank charges to the buyer."),
	("Sales — Documents against Acceptance (D/A)", 1, 0,
	 "Documents against Acceptance (D/A) under URC 522: documents released against the buyer's acceptance of a "
	 "usance bill of exchange payable [__] days from Bill of Lading date. Overseas bank charges to the buyer."),
	("Sales — Open account Net 30", 1, 0,
	 "Open account: payment by T/T within 30 days of the Bill of Lading date. Overdue amounts carry interest at "
	 "[__]% per month; title is retained until payment in full."),
	("Purchase — 100% advance", 0, 1,
	 "100% advance by NEFT/RTGS/wire within [__] days of acceptance of the supplier's proforma invoice, before "
	 "dispatch. Advance refundable for goods not delivered, or rejected and not replaced."),
	("Purchase — Against proforma invoice", 0, 1,
	 "Payment against the supplier's proforma invoice fixing price, specification, taxes and delivery; "
	 "[advance %/full] within [__] days of acceptance, balance per the agreed terms."),
	("Purchase — Against delivery / goods receipt", 0, 1,
	 "100% within [__] days of receipt of the goods, generation of the Goods Receipt Note and verification of "
	 "quantity, Certificate of Analysis and remaining shelf-life. No payment due on rejected goods."),
	("Purchase — Net 30 days", 0, 1,
	 "Net 30 days from the later of the supplier's tax invoice date and receipt and acceptance of the goods with a "
	 "conforming Certificate of Analysis. Disputed or rejected items may be withheld."),
	("Purchase — 30% advance, balance on delivery", 0, 1,
	 "30% advance against the supplier's proforma invoice; balance 70% within [__] days of receipt and acceptance "
	 "of the goods (goods receipt), conforming Certificate of Analysis and required documents. No balance payable "
	 "on rejected goods."),
]


def seed_payment_terms():
	"""Insert sample selling/buying Export Payment Term templates so the SO and PO
	payment-terms pickers have realistic, editable examples. Idempotent (existing
	records by name are left untouched)."""
	for name, selling, buying, terms in SAMPLE_PAYMENT_TERMS:
		if frappe.db.exists("Export Payment Term", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Export Payment Term",
				"template_name": name,
				"selling": selling,
				"buying": buying,
				"terms": terms,
			}
		).insert(ignore_permissions=True)


def seed_item_group():
	"""A stable app-owned leaf Item Group so app-created pharma items aren't filed under
	whatever happens to be the first Item Group on the bench (a hazard on a shared
	multi-app site). Idempotent."""
	if frappe.db.exists("Item Group", "Pharma Trading"):
		return
	parent = frappe.db.get_value("Item Group", "All Item Groups", "name") or frappe.db.get_value(
		"Item Group", {"is_group": 1}, "name"
	)
	frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": "Pharma Trading",
			"is_group": 0,
			"parent_item_group": parent,
		}
	).insert(ignore_permissions=True)


# the client's standard pack types — the dropdown on the shipment packing detail.
# Users add more in Settings → Master data → Pack types.
PACK_TYPES = ["HDPE Drum", "Fiber Drum", "UN Approved Drum", "Bags", "Carton Box"]


def seed_pack_types():
	"""Seed the standard package types offered on the shipment packing detail.
	Idempotent (existing records by name are left untouched)."""
	for name in PACK_TYPES:
		if frappe.db.exists("Export Pack Type", name):
			continue
		frappe.get_doc({"doctype": "Export Pack Type", "pack_type_name": name}).insert(
			ignore_permissions=True
		)


def after_install():
	setup_export_role_permissions()
	seed_ports()
	seed_document_types()
	seed_checklist_rules()
	seed_terms_templates()
	seed_payment_terms()
	seed_item_group()
	seed_pack_types()
