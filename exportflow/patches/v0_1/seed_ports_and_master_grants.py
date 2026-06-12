from exportflow.setup import seed_ports, setup_export_role_permissions


def execute():
	setup_export_role_permissions()  # now includes UOM/Country grants
	seed_ports()
