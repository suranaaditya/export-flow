from exportflow.setup import setup_export_role_permissions


def execute():
	# re-runs the idempotent grant set, now including Sales Order write/submit
	# for Operations/Admin plus Customer/Supplier/Item/Incoterm/Currency
	setup_export_role_permissions()
