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


# Sample payment / T&C templates so the client can see the mechanism. Segregated
# by the native Terms and Conditions selling/buying flags: selling rows show in
# the Sales-Order picker, buying rows in the Purchase-Order picker.
SAMPLE_TERMS = [
	# (title, selling, buying, terms text)
	(
		"Sales — 30% advance, 70% against B/L",
		1,
		0,
		"30% advance by telegraphic transfer with order confirmation; balance 70% "
		"against a scanned copy of the Bill of Lading / Airway Bill before the "
		"originals are couriered.",
	),
	(
		"Sales — 100% irrevocable LC at sight",
		1,
		0,
		"100% irrevocable Letter of Credit at sight, confirmed by a prime "
		"international bank, payable on presentation of the shipping documents.",
	),
	(
		"Sales — 100% advance (TT)",
		1,
		0,
		"100% advance payment by telegraphic transfer before dispatch of the goods.",
	),
	(
		"Sales — Cash against documents (CAD)",
		1,
		0,
		"Payment 100% against documents (D/P) through the bank on first presentation.",
	),
	(
		"Purchase — 50% advance, 50% before dispatch",
		0,
		1,
		"50% advance with the purchase order; balance 50% before dispatch from the "
		"supplier's works.",
	),
	(
		"Purchase — Net 30 days",
		0,
		1,
		"Net 30 days from the date of the supplier invoice / receipt of the goods.",
	),
	(
		"Purchase — 100% against delivery",
		0,
		1,
		"100% payment against delivery of the goods together with the documents.",
	),
	(
		"Purchase — 100% advance",
		0,
		1,
		"100% advance payment with the purchase order.",
	),
]


def seed_terms_templates():
	"""Insert sample selling/buying Terms and Conditions templates so the SO and
	PO payment-terms pickers have realistic examples. Existing records (by name)
	are left untouched — idempotent."""
	for title, selling, buying, terms in SAMPLE_TERMS:
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


def after_install():
	setup_export_role_permissions()
	seed_ports()
	seed_document_types()
	seed_checklist_rules()
	seed_terms_templates()
