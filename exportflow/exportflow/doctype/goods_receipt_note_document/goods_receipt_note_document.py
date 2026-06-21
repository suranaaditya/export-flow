# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class GoodsReceiptNoteDocument(Document):
	"""A supplier-provided document attached to a Goods Receipt Note (invoice copy,
	certificate of analysis, packing list, test certificate, MSDS, …) — captured
	where the paperwork arrives with the goods, for use in the export documentation."""

	pass
