# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ExportFlowSettings(Document):
	def on_update(self):
		# enabling the auto-CHA rule pre-creates the placeholder CHA so it is
		# immediately selectable and the shipment Link never dangles
		if self.auto_cha_third_country:
			from exportflow.exportflow.doctype.cha.cha import ensure_third_country_cha

			ensure_third_country_cha()
