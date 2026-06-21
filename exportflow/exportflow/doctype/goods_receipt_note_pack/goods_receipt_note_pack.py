# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class GoodsReceiptNotePack(Document):
	"""Per-batch / per-package-group detail captured on a Goods Receipt Note;
	mirrors Export Shipment Pack so it forwards 1:1 to the shipment."""

	pass
