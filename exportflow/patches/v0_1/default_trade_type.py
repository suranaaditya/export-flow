"""Default trade_type on shipments created before the field existed.

Merchanting rows are marked from the client MIS via
`exportflow.mis_import.backfill_trade_types` (that needs the client data file);
this patch only ensures no shipment is left with a NULL trade type.
"""

import frappe

from exportflow.mtt import DEFAULT_TRADE_TYPE


def execute():
	if not frappe.db.has_column("Export Shipment", "trade_type"):
		return
	frappe.db.sql(
		"UPDATE `tabExport Shipment` SET trade_type = %s WHERE trade_type IS NULL OR trade_type = ''",
		(DEFAULT_TRADE_TYPE,),
	)
