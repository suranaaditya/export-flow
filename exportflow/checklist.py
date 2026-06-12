"""The checklist rule engine (spec §5.3).

On every Export Shipment save (and on PO submit/cancel, LC edits and customer
destination changes) the builder recomputes which Document Instances the
shipment requires and syncs them:

- a required document that has no instance gets a Pending one;
- an engine-managed instance whose condition lapsed is removed ONLY while it
  is still Pending — any progressed row is the user's work and is kept;
- manual rows are never touched;
- re-running with no changes is a no-op (never duplicates).

Identity: one instance per Document Type per shipment (`dt::<type>`), except
the per-PO GST Supplier Compliance Pack (`po::<type>::<po>`) — a shipment fed
by two 0.1%-scheme POs owes two packs, one per supplier.
"""

import frappe
from frappe.utils import add_days, cint, getdate

GST_PACK_TYPE = "GST Supplier Compliance Pack"
TRUTHY = {"1", "yes", "true", "y"}
BOOL_FIELDS = {"letter_of_credit", "merchant_export_scheme"}

# the engine writes these on managed rows while it owns them
MANAGED_FIELDS = ("source", "description", "originals", "copies", "due_date", "purchase_order")


# ---------------------------------------------------------------- hooks

def on_shipment_update(doc, method=None):
	build_checklist(doc)


def on_shipment_trash(doc, method=None):
	"""Instances are meaningless without their shipment — drop them all."""
	for name in frappe.get_all("Document Instance", filters={"shipment": doc.name}, pluck="name"):
		frappe.delete_doc("Document Instance", name, force=True, ignore_permissions=True)


def rebuild_for_lc(doc, method=None):
	"""LC requirement rows feed shipment checklists — re-sync linked shipments."""
	for name in frappe.get_all(
		"Export Shipment", filters={"letter_of_credit": doc.name}, pluck="name"
	):
		build_checklist(name)


def rebuild_for_customer(doc, method=None):
	if not doc.has_value_changed("destination_country"):
		return
	for name in frappe.get_all("Export Shipment", filters={"customer": doc.name}, pluck="name"):
		build_checklist(name)


def rebuild_for_rule_change(doc, method=None):
	"""Creating, editing, disabling or deleting a checklist rule re-syncs every
	shipment — the client runs dozens of shipments, not thousands."""
	for name in frappe.get_all("Export Shipment", pluck="name"):
		build_checklist(name)


def rebuild_for_shipments(names):
	for name in sorted(set(names)):
		if frappe.db.exists("Export Shipment", name):
			build_checklist(name)


# ---------------------------------------------------------------- context

def _merchant_scheme_pos(shipment) -> list[str]:
	"""Submitted, scheme-flagged POs feeding this shipment, with their GST
	deadline (the pack is due when the export window closes, §4.3)."""
	pos = sorted({row.purchase_order for row in shipment.items if row.purchase_order})
	if not pos:
		return []
	return frappe.get_all(
		"Purchase Order",
		filters={"name": ["in", pos], "merchant_export_scheme": 1, "docstatus": 1},
		pluck="name",
		order_by="name asc",
	)


def _context(shipment) -> dict:
	destination = (
		frappe.db.get_value("Customer", shipment.customer, "destination_country")
		if shipment.customer
		else None
	)
	return {
		"mode": shipment.mode or "",
		"incoterm": shipment.incoterm or "",
		"destination_country": destination or "",
		"customer": shipment.customer or "",
		"letter_of_credit": "Yes" if shipment.letter_of_credit else "No",
		"merchant_export_scheme": "Yes" if _merchant_scheme_pos(shipment) else "No",
	}


def _condition_matches(field: str, value: str, ctx: dict) -> bool:
	actual = (ctx.get(field) or "").strip().lower()
	wanted = [w.strip().lower() for w in (value or "").split(",") if w.strip()]
	if not wanted:
		return False
	if field in BOOL_FIELDS:
		want_true = any(w in TRUTHY for w in wanted)
		return (actual == "yes") == want_true
	return actual in wanted


def _rule_applies(rule, ctx: dict) -> bool:
	return all(
		_condition_matches(c.condition_field, c.condition_value, ctx) for c in rule.conditions
	)


# ---------------------------------------------------------------- required set

def _required_documents(shipment) -> dict[str, dict]:
	"""key -> spec for every instance this shipment should have."""
	ctx = _context(shipment)
	required: dict[str, dict] = {}

	for rule_name in frappe.get_all(
		"Document Checklist Rule", filters={"enabled": 1}, pluck="name", order_by="name asc"
	):
		rule = frappe.get_doc("Document Checklist Rule", rule_name)
		if not frappe.db.exists("Document Type", rule.document_type):
			continue
		if _rule_applies(rule, ctx):
			required.setdefault(
				f"dt::{rule.document_type}",
				{"document_type": rule.document_type, "source": "Rule"},
			)

	# §4.3: one compliance pack per 0.1%-scheme PO, due by its GST deadline
	if frappe.db.exists("Document Type", GST_PACK_TYPE):
		for po in _merchant_scheme_pos(shipment):
			required[f"po::{GST_PACK_TYPE}::{po}"] = {
				"document_type": GST_PACK_TYPE,
				"source": "Rule",
				"purchase_order": po,
				"due_date": frappe.db.get_value("Purchase Order", po, "gst_export_deadline"),
			}

	# §4.4: merge the LC's requirement rows under Banking; once the transport
	# document is dated, stamp the presentation due date on the LC paperwork
	if shipment.letter_of_credit:
		lc = frappe.get_doc("Letter of Credit", shipment.letter_of_credit)
		transport_date = shipment.bl_date if shipment.mode == "Sea" else shipment.awb_date
		presentation_due = (
			add_days(getdate(transport_date), cint(lc.presentation_period_days) or 21)
			if transport_date
			else None
		)
		for req in lc.document_requirements:
			if not frappe.db.exists("Document Type", req.document_type):
				continue
			key = f"dt::{req.document_type}"
			spec = required.setdefault(key, {"document_type": req.document_type})
			spec["source"] = "LC"
			spec["description"] = req.description
			spec["originals"] = cint(req.originals)
			spec["copies"] = cint(req.copies)
			if presentation_due:
				spec["due_date"] = presentation_due
		# the LC-conditional generated set is presented to the bank too
		if presentation_due:
			for doc_type in (
				"Bill of Exchange",
				"Bank Presentation Covering Schedule",
				"Document Courier AWB",
			):
				spec = required.get(f"dt::{doc_type}")
				if spec and not spec.get("due_date"):
					spec["due_date"] = presentation_due

	return required


# ---------------------------------------------------------------- sync

def build_checklist(shipment) -> None:
	if isinstance(shipment, str):
		shipment = frappe.get_doc("Export Shipment", shipment)
	if not shipment.name or shipment.flags.in_checklist_build:
		return
	shipment.flags.in_checklist_build = True
	try:
		_sync(shipment)
	finally:
		shipment.flags.in_checklist_build = False


def _identity_key(inst) -> str:
	"""Identity derived from Link fields, never the stored source_key — Link
	fields follow frappe.rename_doc (Document Type, Purchase Order renames),
	a frozen Data string does not."""
	if inst.purchase_order and inst.document_type == GST_PACK_TYPE:
		return f"po::{inst.document_type}::{inst.purchase_order}"
	return f"dt::{inst.document_type}"


def _untouched(inst) -> bool:
	"""True when nobody recorded anything on the row — only these may be
	auto-removed. A Pending row can still carry an uploaded file, a number or
	remarks (the UI never forces a status change to attach things)."""
	return inst.status == "Pending" and not (
		inst.file or inst.document_number or inst.document_date or (inst.remarks or "").strip()
	)


def _sync(shipment) -> None:
	# serialise concurrent builds for the same shipment (save vs PO submit)
	frappe.db.sql(
		"SELECT name FROM `tabExport Shipment` WHERE name = %s FOR UPDATE", (shipment.name,)
	)

	required = _required_documents(shipment)
	existing = frappe.get_all(
		"Document Instance",
		filters={"shipment": shipment.name, "source": ["in", ("Rule", "LC")]},
		fields=[
			"name",
			"document_type",
			"status",
			"source",
			"source_key",
			"file",
			"document_number",
			"document_date",
			"remarks",
			*MANAGED_FIELDS[1:],
		],
	)

	by_key: dict[str, list] = {}
	for inst in existing:
		by_key.setdefault(_identity_key(inst), []).append(inst)

	for key, spec in required.items():
		rows = by_key.pop(key, None)
		if not rows:
			_create_instance(shipment, key, spec)
			continue
		_update_instance(rows[0], spec, key)
		# duplicates can only come from pre-engine data; fold the untouched ones
		for extra in rows[1:]:
			if _untouched(extra):
				frappe.delete_doc(
					"Document Instance", extra.name, force=True, ignore_permissions=True
				)

	# lapsed requirements: drop rows nobody touched; rows carrying real work
	# are handed to the user (source Manual) instead of silently destroyed
	for rows in by_key.values():
		for inst in rows:
			if _untouched(inst):
				frappe.delete_doc(
					"Document Instance", inst.name, force=True, ignore_permissions=True
				)
			elif inst.source != "Manual":
				frappe.db.set_value(
					"Document Instance",
					inst.name,
					{"source": "Manual", "source_key": None},
					update_modified=False,
				)


def _create_instance(shipment, key: str, spec: dict) -> None:
	frappe.get_doc(
		{
			"doctype": "Document Instance",
			"document_type": spec["document_type"],
			"status": "Pending",
			"shipment": shipment.name,
			"customer": shipment.customer,
			"purchase_order": spec.get("purchase_order"),
			"description": spec.get("description"),
			"originals": spec.get("originals"),
			"copies": spec.get("copies"),
			"due_date": spec.get("due_date"),
			"source": spec.get("source", "Rule"),
			"source_key": key,
		}
	).insert(ignore_permissions=True)


def _update_instance(inst, spec: dict, key: str) -> None:
	"""Keep engine-owned metadata current without touching the user's work
	(status, numbers, dates, files, remarks stay theirs). Fields the spec no
	longer provides are left alone rather than blanked — e.g. LC wording stays
	readable on a row that has since fallen back to a plain rule."""
	desired = {field: spec.get(field) for field in MANAGED_FIELDS}
	desired["source"] = spec.get("source", "Rule")

	changes = {}
	for field, new in desired.items():
		if new is None:
			continue
		old = inst.get(field)
		if field in ("originals", "copies"):
			if cint(new) and cint(old) != cint(new):
				changes[field] = cint(new)
		elif str(old or "") != str(new):
			changes[field] = new
	# self-heal the stored breadcrumb after a Document Type / PO rename
	if (inst.source_key or "") != key:
		changes["source_key"] = key
	if changes:
		frappe.db.set_value("Document Instance", inst.name, changes, update_modified=False)


# ---------------------------------------------------------------- blocking

def milestone_blockers(shipment_name: str, milestone: str) -> list[dict]:
	"""Unresolved blocking instances gating this milestone (§4.2: default —
	ADC NOC and Shipping Bill block "Let Export Order")."""
	from exportflow.exportflow.doctype.document_instance.document_instance import status_index

	rows = frappe.get_all(
		"Document Instance",
		filters={
			"shipment": shipment_name,
			"blocking": 1,
			"blocked_milestone": milestone,
			"status": ["!=", "Not Applicable"],
		},
		fields=["name", "document_type", "status", "min_unblock_status"],
	)
	return [
		r
		for r in rows
		if status_index(r.status) < status_index(r.min_unblock_status or "Received")
	]
