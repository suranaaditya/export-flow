# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ExportFlowStockLedger(Document):
	# A passive, system-written ledger row. Movements are created/reversed only
	# through exportflow.stock (post_in / post_out / reverse) — never hand-edited.
	pass
