# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ExportPaymentTerm(Document):
	"""A reusable payment-terms template, the payment-side counterpart of the native
	Terms and Conditions master. Plain text (no payment_schedule rows) — the selected
	template's text is copied onto the order's payment-terms narrative, which is the
	authoritative value that prints. Segregated by selling / buying like Terms and
	Conditions."""

	pass
