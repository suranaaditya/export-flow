import frappe
from frappe.utils import getdate, nowdate

ALERT_ROLES = ("Export Admin", "Export Operations", "Export Accounts")


def daily():
	send_lc_alerts()


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
		already = frappe.db.exists(
			"Notification Log",
			{
				"for_user": user,
				"subject": subject,
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
