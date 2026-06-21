from exportflow.setup import setup_export_role_permissions


def execute():
	# re-runs the idempotent grant set, now including Warehouse (read) for the
	# Goods Receipt Note picklist
	setup_export_role_permissions()
