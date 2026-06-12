# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# forward order of the working statuses; "Not Applicable" sits outside it
STATUS_ORDER = ["Pending", "Drafted", "Sent/Filed", "Received", "Verified"]


def status_index(status: str) -> int:
	try:
		return STATUS_ORDER.index(status)
	except ValueError:
		return -1


class DocumentInstance(Document):
	def validate(self):
		self.sync_type_facts()

	def sync_type_facts(self):
		"""Category/origin always mirror the Document Type (they are facts of
		the type); responsible/blocking are defaults the user may override, so
		they are filled only when blank on a new row (fetch_from would clobber
		manual overrides on every save)."""
		dt = frappe.db.get_value(
			"Document Type",
			self.document_type,
			[
				"category",
				"origin",
				"responsible_party",
				"is_blocking",
				"blocked_milestone",
				"min_unblock_status",
			],
			as_dict=True,
		)
		if not dt:
			frappe.throw(_("Document Type {0} not found").format(self.document_type))
		self.category = dt.category
		self.origin = dt.origin
		if not self.responsible_party:
			self.responsible_party = dt.responsible_party
		if self.is_new() and not self.blocking and dt.is_blocking:
			self.blocking = 1
			self.blocked_milestone = dt.blocked_milestone or "Let Export Order"
			self.min_unblock_status = dt.min_unblock_status or "Received"
		if self.blocking and not self.min_unblock_status:
			self.min_unblock_status = "Received"

	def resolved_for_blocking(self) -> bool:
		"""True when this instance no longer holds up its blocked milestone."""
		if self.status == "Not Applicable":
			return True
		return status_index(self.status) >= status_index(self.min_unblock_status or "Received")
