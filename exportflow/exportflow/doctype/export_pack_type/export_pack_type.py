# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ExportPackType(Document):
	"""A managed pack/package type (HDPE Drum, Fiber Drum, Bags, …) offered as a
	dropdown on the shipment packing detail. The selected name is stored verbatim on
	the Export Shipment Pack row's pack_type and prints on the invoice / packing list."""

	pass
