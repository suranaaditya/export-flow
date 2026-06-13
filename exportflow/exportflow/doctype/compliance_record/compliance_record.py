# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class ComplianceRecord(Document):
	def validate(self):
		if not self.company:
			from exportflow.company import exportflow_company

			self.company = exportflow_company()
		if self.compliance_type == "AD Code" and not self.port:
			frappe.throw(_("AD codes are registered per port — pick the port"))
		if self.compliance_type != "AD Code":
			self.port = None
		if (
			self.issue_date
			and self.expiry_date
			and getdate(self.expiry_date) < getdate(self.issue_date)
		):
			frappe.throw(_("Expiry date cannot be before the issue date"))
