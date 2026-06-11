from urllib.parse import quote

import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		# Preserve the deep link (path + query) across the login round trip
		requested = (frappe.local.request.full_path or "/exportflow").rstrip("?")
		frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(requested)
		raise frappe.Redirect

	context.csrf_token = frappe.sessions.get_csrf_token()
	context.no_cache = 1
	return context
