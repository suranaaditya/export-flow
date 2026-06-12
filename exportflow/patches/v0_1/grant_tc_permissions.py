from exportflow.setup import setup_export_role_permissions


def execute():
	# re-runs the idempotent grant set, now including Terms and Conditions
	setup_export_role_permissions()
