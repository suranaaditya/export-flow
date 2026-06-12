import frappe

from exportflow.setup import seed_checklist_rules, seed_document_types


def backfill_seeded_defaults():
	"""Sites seeded by an earlier run of this catalog get the new defaults —
	but only where the client clearly never configured the field themselves."""
	from exportflow.doc_catalog import DOCUMENT_TYPES

	for name, _category, _origin, _resp, _attach, extras in DOCUMENT_TYPES:
		if not frappe.db.exists("Document Type", name):
			continue
		row = frappe.db.get_value(
			"Document Type",
			name,
			["default_print_format", "is_blocking", "blocked_milestone"],
			as_dict=True,
		)
		updates = {}
		if extras.get("default_print_format") and not row.default_print_format:
			if frappe.db.exists("Print Format", extras["default_print_format"]):
				updates["default_print_format"] = extras["default_print_format"]
		if extras.get("is_blocking") and not row.is_blocking and not row.blocked_milestone:
			updates["is_blocking"] = 1
			updates["blocked_milestone"] = extras.get("blocked_milestone") or "Let Export Order"
			updates["min_unblock_status"] = extras.get("min_unblock_status") or "Received"
		if updates:
			frappe.db.set_value("Document Type", name, updates)


def repair_autofilled_responsible_party():
	"""Frappe pre-fills a Select with its first option on insert, so every
	engine-created instance briefly defaulted to "Us" regardless of its type.
	Repair the rows where the type disagrees (the field now has a blank first
	option, so new rows take the type's default correctly)."""
	for row in frappe.get_all(
		"Document Instance",
		filters={"responsible_party": "Us"},
		fields=["name", "document_type"],
	):
		type_party = frappe.db.get_value("Document Type", row.document_type, "responsible_party")
		if type_party and type_party != "Us":
			frappe.db.set_value(
				"Document Instance", row.name, "responsible_party", type_party, update_modified=False
			)


def execute():
	seed_document_types()
	seed_checklist_rules()
	backfill_seeded_defaults()
	repair_autofilled_responsible_party()

	# shipments booked before Phase 4 get their checklists on first save —
	# build them now so the feature is live for in-flight cargo too
	from exportflow.checklist import rebuild_for_shipments

	rebuild_for_shipments(frappe.get_all("Export Shipment", pluck="name"))
