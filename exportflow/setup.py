"""Idempotent permission grants for the Export roles on standard doctypes.

Runs from after_install (fresh sites) and from a patch (existing sites).
Uses frappe.permissions.add_permission, which clones a doctype's standard
perms into Custom DocPerm before adding — so existing roles keep their access.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

EXPORT_ROLES = ("Export Admin", "Export Operations", "Export Accounts", "Export Viewer")

# doctype -> {role: [ptypes beyond read]}
GRANTS = {
	"Sales Order": {role: [] for role in EXPORT_ROLES},
	"Bank Account": {role: [] for role in EXPORT_ROLES},
	"Payment Entry": {
		"Export Admin": ["create", "write", "submit", "cancel", "amend"],
		"Export Accounts": ["create", "write", "submit", "cancel", "amend"],
		"Export Operations": [],
		"Export Viewer": [],
	},
}


def setup_export_role_permissions():
	for doctype, roles in GRANTS.items():
		for role, extra_ptypes in roles.items():
			if not frappe.db.exists("Role", role):
				continue
			# read at permlevel 0 (add_permission is a no-op if already granted)
			add_permission(doctype, role, permlevel=0)
			for ptype in extra_ptypes:
				update_permission_property(doctype, role, 0, ptype, 1, validate=False)
	frappe.clear_cache()


def after_install():
	setup_export_role_permissions()
