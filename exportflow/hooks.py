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

# Apply the merchant-export 0.1% concessional GST when the scheme flag is set;
# stock ERPNext behaviour otherwise (see overrides/purchase_order.py).
override_doctype_class = {
	"Purchase Order": "exportflow.overrides.purchase_order.ExportFlowPurchaseOrder",
}

doc_events = {
	"Purchase Order": {
		"before_insert": "exportflow.overrides.purchase_order.before_insert",
		"validate": "exportflow.overrides.purchase_order.validate",
		# validate does not run on update-after-submit; the supplier invoice
		# arrives after PO submission, so recompute the deadline there too
		"before_update_after_submit": "exportflow.overrides.purchase_order.validate",
		# shipments booked before procurement get their PO links backfilled
		"on_submit": "exportflow.overrides.purchase_order.on_submit",
		"on_cancel": "exportflow.overrides.purchase_order.on_cancel",
		# invoice details land post-submit — the GST pack's due date follows
		"on_update_after_submit": "exportflow.overrides.purchase_order.on_update_after_submit",
	},
	"Payment Entry": {
		"validate": "exportflow.overrides.payment_entry.validate",
		"on_submit": "exportflow.overrides.payment_entry.on_submit",
		"on_cancel": "exportflow.overrides.payment_entry.on_cancel",
	},
	# the §5.3 checklist engine keeps Document Instances in sync; a trade-type /
	# MTT-commencement change also moves the realizations' FEMA clock
	"Export Shipment": {
		"on_update": [
			"exportflow.checklist.on_shipment_update",
			# document facts (shipping bill / LEO / bl-awb date) fast-forward the
			# milestone chain — runs after the checklist rebuild so the blocking
			# state it respects is current
			"exportflow.exportflow.doctype.export_shipment.export_shipment.advance_milestones_from_facts",
			"exportflow.exportflow.doctype.export_realization.export_realization.resync_due_dates_for_shipment",
			# the departure date fills the FEMA export_date on the auto-created
			# realization shell (resync only moves an already-formula'd due)
			"exportflow.exportflow.doctype.export_realization.export_realization.fill_export_dates_for_shipment",
			# a fully-shipped drop-ship PO is delivered — flip its status so the SO advances
			"exportflow.overrides.purchase_order.mark_covered_pos_delivered",
		],
		"on_trash": "exportflow.checklist.on_shipment_trash",
	},
	"Letter of Credit": {
		"on_update": "exportflow.checklist.rebuild_for_lc",
	},
	"Customer": {
		"on_update": "exportflow.checklist.rebuild_for_customer",
	},
	"Document Checklist Rule": {
		"on_update": "exportflow.checklist.rebuild_for_rule_change",
		# after_delete, not on_trash — the rebuild must see the rule gone
		"after_delete": "exportflow.checklist.rebuild_for_rule_change",
	},
	# a realization drawing on a forward contract keeps that contract's utilization current
	"Export Realization": {
		"on_update": "exportflow.exportflow.doctype.forward_contract.forward_contract.recompute_for_realization",
		"on_trash": "exportflow.exportflow.doctype.forward_contract.forward_contract.recompute_for_realization",
	},
}

# print-format context builders (Commercial Invoice / Packing List / SCOMET)
jinja = {
	"methods": [
		"exportflow.printing.document_print_context",
		"exportflow.printing.party_address",
		"exportflow.printing.exporter_profile",
	],
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
