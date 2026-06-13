# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# placeholder CHA for third-country / merchanting trades (no Indian customs
# agent) — matches the client's MIS convention of marking such rows "Third Country"
THIRD_COUNTRY_CHA = "Third Country"


def ensure_third_country_cha() -> str:
	"""Get-or-create the placeholder CHA. Idempotent; safe to call inside a save
	(the insert is visible to the same transaction's link validation)."""
	if not frappe.db.exists("CHA", THIRD_COUNTRY_CHA):
		frappe.get_doc({"doctype": "CHA", "cha_name": THIRD_COUNTRY_CHA}).insert(
			ignore_permissions=True
		)
	return THIRD_COUNTRY_CHA


class CHA(Document):
	pass
