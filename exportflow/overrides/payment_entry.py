import frappe
from frappe import _


def validate(doc, method=None):
	if not doc.get("pro_forma_invoice"):
		return

	if doc.payment_type != "Receive":
		frappe.throw(_("Only incoming (Receive) payments can settle a Pro Forma Invoice"))

	pfi = frappe.db.get_value(
		"Pro Forma Invoice", doc.pro_forma_invoice, ["customer", "status"], as_dict=True
	)
	if not pfi:
		frappe.throw(_("Pro Forma Invoice {0} not found").format(doc.pro_forma_invoice))
	if pfi.status == "Cancelled":
		frappe.throw(_("Pro Forma Invoice {0} is cancelled").format(doc.pro_forma_invoice))
	if doc.party_type != "Customer" or doc.party != pfi.customer:
		frappe.throw(
			_("Payment party must be customer {0} of Pro Forma Invoice {1}").format(
				pfi.customer, doc.pro_forma_invoice
			)
		)


def on_submit(doc, method=None):
	_update_linked_pfi(doc)


def on_cancel(doc, method=None):
	_update_linked_pfi(doc)


def _update_linked_pfi(doc):
	if doc.get("pro_forma_invoice"):
		# row lock: serialise against concurrent cancel/mark-sent transitions
		frappe.get_doc("Pro Forma Invoice", doc.pro_forma_invoice, for_update=True).update_payment_status()
