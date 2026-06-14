# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ExportShipmentPack(Document):
	"""Per-batch / per-package-group packing detail for an Export Shipment line —
	the drum-range, quantity, mfg/exp dates and net/tare weights that the
	commercial invoice and packing list itemise. Grouped by item at print time."""

	pass
