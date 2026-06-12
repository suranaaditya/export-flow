import frappe
from frappe.utils import flt, getdate, nowdate

ALERT_ROLES = ("Export Admin", "Export Operations", "Export Accounts")

# §4.3 — the 90-day clock gets louder as it runs down
GST_ALERT_DAYS = {30, 14, 7, 3}
# §4.4(c) — presentation/due dates on tracked documents
DOC_DUE_ALERT_DAYS = {7, 3, 1}
# Compliance register renewals (spec §3.2)
COMPLIANCE_ALERT_DAYS = {60, 30, 7}


def daily():
	alerts = []
	alerts += send_lc_alerts()
	alerts += send_gst_alerts()
	alerts += send_document_due_alerts()
	alerts += send_compliance_alerts()
	send_email_digest(alerts)


def send_email_digest(alerts: list[dict]) -> dict | None:
	"""Spec §6: optional daily email digest — one consolidated mail per day to
	every export user. Off until ExportFlow Settings enables it; SMTP setup is
	a deployment concern (failures are logged, never raised)."""
	if not alerts:
		return None
	if not frappe.db.get_single_value("ExportFlow Settings", "email_digest_enabled"):
		return None

	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", ALERT_ROLES], "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	recipients = sorted(
		set(
			frappe.get_all(
				"User",
				filters={"name": ["in", users], "enabled": 1, "user_type": "System User"},
				pluck="name",
			)
		)
		- {"Guest", "Administrator"}
	)
	if not recipients:
		return None

	subjects = [a["subject"] for a in alerts]
	digest = {
		"recipients": recipients,
		"subject": f"ExportFlow daily digest — {len(subjects)} alert{'s' if len(subjects) != 1 else ''}",
		"lines": subjects,
	}
	try:
		frappe.sendmail(
			recipients=recipients,
			subject=digest["subject"],
			message="<br>".join(frappe.utils.escape_html(s) for s in subjects),
			delayed=True,
		)
	except Exception:
		# no outgoing email account configured yet — the in-app feed stands
		frappe.log_error(title="ExportFlow digest email failed", message=frappe.get_traceback())
	return digest


def _when(days_left: int) -> str:
	if days_left > 0:
		return f"in {days_left} day{'s' if days_left != 1 else ''}"
	if days_left == 0:
		return "today"
	return f"overdue by {-days_left} day{'s' if days_left != -1 else ''}"


def send_gst_alerts(today=None) -> list[dict]:
	"""§4.3: every submitted 0.1%-scheme PO must see its cargo exported within
	90 days of the supplier invoice. Alert at 30/14/7/3 days and daily once
	overdue, until the linked shipments have actually left the country."""
	today = getdate(today or nowdate())
	alerts = []

	pos = frappe.get_all(
		"Purchase Order",
		filters={
			"docstatus": 1,
			"merchant_export_scheme": 1,
			"gst_export_deadline": ["is", "set"],
		},
		fields=["name", "supplier_name", "gst_export_deadline", "supplier_invoice_no"],
	)
	for po in pos:
		try:
			if _po_fully_exported(po.name):
				continue
			days_left = (getdate(po.gst_export_deadline) - today).days
			if days_left in GST_ALERT_DAYS or days_left <= 0:
				subject = f"GST 90-day clock: {po.name} export window closes {_when(days_left)}"
				body = (
					f"Purchase Order {po.name} ({po.supplier_name}"
					f"{', inv ' + po.supplier_invoice_no if po.supplier_invoice_no else ''}) is under the "
					f"0.1% merchant-export scheme. The goods must be exported by {po.gst_export_deadline} "
					f"or the concessional GST rate is lost (Notification 40/2017)."
				)
				alerts.append({"po": po.name, "days_left": days_left, "subject": subject})
				notify_export_users(subject, body, "Purchase Order", po.name)
		except Exception:
			frappe.log_error(title=f"GST alert failed: {po.name}", message=frappe.get_traceback())

	return alerts


def _departed_qty(column: str, value: str) -> float:
	"""Shipped qty (by po_detail or so_detail) sitting on shipments that have
	completed their export milestone."""
	assert column in ("po_detail", "so_detail")
	return flt(
		frappe.db.sql(
			f"""SELECT COALESCE(SUM(esi.qty), 0)
			   FROM `tabExport Shipment Item` esi
			   WHERE esi.{column} = %s AND EXISTS (
			       SELECT 1 FROM `tabShipment Milestone` sm
			       WHERE sm.parent = esi.parent AND sm.parenttype = 'Export Shipment'
			         AND sm.completed = 1
			         AND sm.milestone IN ('Shipped on Board', 'Departed'))""",
			(value,),
		)[0][0]
	)


def _po_fully_exported(po_name: str) -> bool:
	"""The clock stops when every exportable (SO-linked) unit of the PO is on a
	shipment past its export milestone. Free lines (packing material etc.)
	never ship through the app, so they are not part of the obligation count.

	A PO line is satisfied when its directly-linked shipment rows have
	departed; failing that, when the SO line it sources is fully departed
	across all POs (shipment rows are claimed by whichever PO submitted first,
	so split-sourced lines need the aggregate check)."""
	po_lines = frappe.get_all(
		"Purchase Order Item",
		filters={"parent": po_name, "sales_order_item": ["is", "set"]},
		fields=["name", "qty", "sales_order_item"],
	)
	if not po_lines:
		# nothing exportable is tracked — keep alerting until the deadline,
		# the obligation still exists even if the app cannot see the cargo
		return False

	for line in po_lines:
		if _departed_qty("po_detail", line.name) >= flt(line.qty) - 1e-6:
			continue
		ordered_on_so = flt(
			frappe.db.sql(
				"""SELECT COALESCE(SUM(poi.qty), 0)
				   FROM `tabPurchase Order Item` poi
				   JOIN `tabPurchase Order` po ON po.name = poi.parent
				   WHERE poi.sales_order_item = %s AND po.docstatus = 1""",
				(line.sales_order_item,),
			)[0][0]
		)
		if _departed_qty("so_detail", line.sales_order_item) >= ordered_on_so - 1e-6:
			continue
		return False
	return True


def send_document_due_alerts(today=None) -> list[dict]:
	"""Due dates on checklist documents (LC presentation sets, GST packs):
	alert at 7/3/1 days and daily once overdue while the document has not
	moved past Drafted."""
	today = getdate(today or nowdate())
	alerts = []

	rows = frappe.get_all(
		"Document Instance",
		filters={"due_date": ["is", "set"], "status": ["in", ("Pending", "Drafted")]},
		fields=[
			"name",
			"document_type",
			"shipment",
			"status",
			"due_date",
			"responsible_party",
			"purchase_order",
		],
	)
	for row in rows:
		try:
			days_left = (getdate(row.due_date) - today).days
			if days_left in DOC_DUE_ALERT_DAYS or days_left <= 0:
				where = f" on {row.shipment}" if row.shipment else ""
				# per-PO packs share type+shipment — the PO disambiguates
				if row.purchase_order:
					where += f" ({row.purchase_order})"
				subject = f"Document due: {row.document_type}{where} — {_when(days_left)}"
				body = (
					f"{row.document_type}{where} is due on {row.due_date} and is still "
					f"{row.status.lower()}."
					f"{' Responsible: ' + row.responsible_party + '.' if row.responsible_party else ''}"
				)
				alerts.append(
					{"instance": row.name, "days_left": days_left, "subject": subject}
				)
				notify_export_users(subject, body, "Document Instance", row.name)
		except Exception:
			frappe.log_error(
				title=f"Document due alert failed: {row.name}", message=frappe.get_traceback()
			)

	return alerts


def send_compliance_alerts(today=None) -> list[dict]:
	"""Compliance register renewals: 60/30/7 days before expiry and daily once
	overdue, for Active records only."""
	today = getdate(today or nowdate())
	alerts = []

	rows = frappe.get_all(
		"Compliance Record",
		filters={"status": "Active", "expiry_date": ["is", "set"]},
		fields=["name", "compliance_type", "title", "reference_number", "expiry_date"],
	)
	for row in rows:
		try:
			days_left = (getdate(row.expiry_date) - today).days
			if days_left in COMPLIANCE_ALERT_DAYS or days_left <= 0:
				subject = f"Compliance renewal: {row.title} expires {_when(days_left)}"
				body = (
					f"{row.compliance_type} — {row.title}"
					f"{' (' + row.reference_number + ')' if row.reference_number else ''} "
					f"expires on {row.expiry_date}. Renew it and archive this record."
				)
				alerts.append({"record": row.name, "days_left": days_left, "subject": subject})
				notify_export_users(subject, body, "Compliance Record", row.name)
		except Exception:
			frappe.log_error(
				title=f"Compliance alert failed: {row.name}", message=frappe.get_traceback()
			)

	return alerts


def send_lc_alerts(today=None) -> list[dict]:
	"""Spec §3.2/§4.4: alert at configurable thresholds (default 15/7/3 days)
	before an open LC's latest shipment date and expiry date, and daily once a
	date is overdue while the LC is still open.

	Phase 3 refines the condition with the linked shipment's milestone; for now
	an LC counts as at-risk while its documents have not been presented
	(status Received/Active). Returns the alerts it raised (for tests).
	"""
	from exportflow.exportflow.doctype.letter_of_credit.letter_of_credit import OPEN_STATUSES

	today = getdate(today or nowdate())
	alerts = []

	for lc_name in frappe.get_all(
		"Letter of Credit", filters={"status": ["in", OPEN_STATUSES]}, pluck="name"
	):
		try:
			alerts.extend(_alerts_for_lc(lc_name, today))
		except Exception:
			# one bad row must not blind the whole fleet
			frappe.log_error(
				title=f"LC alert failed: {lc_name}",
				message=frappe.get_traceback(),
			)

	return alerts


def _alerts_for_lc(lc_name: str, today) -> list[dict]:
	lc = frappe.get_doc("Letter of Credit", lc_name)
	thresholds = lc.get_alert_days(strict=False)
	alerts = []

	for label, date in (
		("latest shipment date", lc.latest_shipment_date),
		("expiry date", lc.expiry_date),
	):
		if not date:
			continue
		days_left = (getdate(date) - today).days
		if days_left in thresholds or days_left <= 0:
			if days_left > 0:
				when = f"in {days_left} day{'s' if days_left != 1 else ''}"
			elif days_left == 0:
				when = "today"
			else:
				when = f"overdue by {-days_left} day{'s' if days_left != -1 else ''}"
			subject = f"LC {lc.lc_number}: {label} {when}"
			body = (
				f"Letter of Credit {lc.name} ({lc.lc_number}, {lc.customer_name or lc.customer}) "
				f"reaches its {label} on {date}. Status: {lc.status}. "
				f"Sales Order: {lc.sales_order}."
			)
			alerts.append({"lc": lc.name, "label": label, "days_left": days_left, "subject": subject})
			notify_export_users(subject, body, "Letter of Credit", lc.name)

	return alerts


def notify_export_users(subject: str, body: str, ref_doctype: str, ref_name: str):
	"""In-app Notification Log for every enabled user holding an Export role.
	Deduped per user/subject/day so a re-run does not double-notify."""
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", ALERT_ROLES], "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	enabled = set(
		frappe.get_all(
			"User", filters={"name": ["in", users], "enabled": 1, "user_type": "System User"}, pluck="name"
		)
	)

	for user in sorted(enabled - {"Guest"}):
		# keyed on the referenced document too — different documents can
		# legitimately produce the same subject on the same day
		already = frappe.db.exists(
			"Notification Log",
			{
				"for_user": user,
				"subject": subject,
				"document_type": ref_doctype,
				"document_name": ref_name,
				"creation": [">=", str(getdate(nowdate()))],
			},
		)
		if already:
			continue
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"subject": subject,
				"email_content": body,
				"type": "Alert",
				"document_type": ref_doctype,
				"document_name": ref_name,
			}
		).insert(ignore_permissions=True)
