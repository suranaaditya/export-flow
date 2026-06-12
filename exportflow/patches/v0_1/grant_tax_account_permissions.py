from exportflow.setup import setup_export_role_permissions


def execute():
	# re-runs the idempotent grant set, now including taxes templates,
	# account read, and print on PO/SO
	setup_export_role_permissions()
