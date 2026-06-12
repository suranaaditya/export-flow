# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# context keys the engine can evaluate (exportflow/checklist.py builds them)
CONDITION_FIELDS = (
	"mode",
	"incoterm",
	"destination_country",
	"customer",
	"letter_of_credit",
	"merchant_export_scheme",
)


class DocumentChecklistRule(Document):
	def validate(self):
		for row in self.conditions:
			if row.condition_field not in CONDITION_FIELDS:
				frappe.throw(_("Row {0}: unknown condition field {1}").format(row.idx, row.condition_field))
			if not (row.condition_value or "").strip():
				frappe.throw(_("Row {0}: condition value is required").format(row.idx))
