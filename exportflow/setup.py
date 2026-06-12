"""Idempotent permission grants for the Export roles on standard doctypes.

Runs from after_install (fresh sites) and from a patch (existing sites).
Uses frappe.permissions.add_permission, which clones a doctype's standard
perms into Custom DocPerm before adding — so existing roles keep their access.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

EXPORT_ROLES = ("Export Admin", "Export Operations", "Export Accounts", "Export Viewer")

# doctype -> {role: [ptypes beyond read]}
TRANSACTION_PTYPES = ["create", "write", "submit", "cancel", "amend"]
MASTER_PTYPES = ["create", "write"]

GRANTS = {
	# deals are entered inside ExportFlow — Operations and Admin own them
	"Sales Order": {
		"Export Admin": TRANSACTION_PTYPES,
		"Export Operations": TRANSACTION_PTYPES,
		"Export Accounts": [],
		"Export Viewer": [],
	},
	"Bank Account": {role: [] for role in EXPORT_ROLES},
	"Payment Entry": {
		"Export Admin": TRANSACTION_PTYPES,
		"Export Accounts": TRANSACTION_PTYPES,
		"Export Operations": [],
		"Export Viewer": [],
	},
	# masters needed while entering a deal
	"Customer": {
		"Export Admin": MASTER_PTYPES,
		"Export Operations": MASTER_PTYPES,
		"Export Accounts": [],
		"Export Viewer": [],
	},
	"Supplier": {
		"Export Admin": MASTER_PTYPES,
		"Export Operations": MASTER_PTYPES,
		"Export Accounts": [],
		"Export Viewer": [],
	},
	"Item": {
		"Export Admin": MASTER_PTYPES,
		"Export Operations": MASTER_PTYPES,
		"Export Accounts": [],
		"Export Viewer": [],
	},
	"Incoterm": {role: [] for role in EXPORT_ROLES},
	"Currency": {role: [] for role in EXPORT_ROLES},
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
