app_name = "exportflow"
app_title = "ExportFlow"
app_publisher = "DUX Digitech"
app_description = "Export-import operations for pharma merchant exporters"
app_email = "info@duxdigitech.com"
app_license = "mit"

required_apps = ["erpnext"]

after_install = "exportflow.setup.after_install"

# Apps screen entry — opens the React SPA
add_to_apps_screen = [
	{
		"name": "exportflow",
		"logo": "/assets/exportflow/images/dux-mark.png",
		"title": "ExportFlow",
		"route": "/exportflow",
	}
]

# Serve the React SPA for all /exportflow/* client-side routes (Raven pattern)
website_route_rules = [
	{"from_route": "/exportflow/<path:app_path>", "to_route": "exportflow"},
]

doc_events = {
	"Purchase Order": {
		"before_insert": "exportflow.overrides.purchase_order.before_insert",
		"validate": "exportflow.overrides.purchase_order.validate",
		# validate does not run on update-after-submit; the supplier invoice
		# arrives after PO submission, so recompute the deadline there too
		"before_update_after_submit": "exportflow.overrides.purchase_order.validate",
	},
	"Payment Entry": {
		"validate": "exportflow.overrides.payment_entry.validate",
		"on_submit": "exportflow.overrides.payment_entry.on_submit",
		"on_cancel": "exportflow.overrides.payment_entry.on_cancel",
	},
}

scheduler_events = {
	"daily": [
		"exportflow.tasks.daily",
	],
}

fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "ExportFlow"]]},
	{
		"dt": "Role",
		"filters": [
			[
				"role_name",
				"in",
				["Export Admin", "Export Operations", "Export Accounts", "Export Viewer"],
			]
		],
	},
]
