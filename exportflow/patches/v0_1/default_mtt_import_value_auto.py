"""Initialise the 'auto-derive from POs' flag (and derived figures) on existing
merchanting shipments.

New shipments default the flag on, but existing rows are set explicitly here.
The decision is keyed on PO-DERIVABILITY (stable across re-runs), NOT on the
mutable stored outlay, so the patch is idempotent and a forced re-run can never
flip a backfilled auto row to manual:

  - linked POs cost the shipment out  -> auto on, and the derived outlay +
    single-supplier are filled in now;
  - no derivable PO outlay but a manual/MIS figure already stored -> kept manual
    (flag off) so that figure is preserved;
  - nothing stored and nothing derivable -> auto on, awaiting its POs.

A re-run re-reads the POs as they stand then, so a manual (auto=0) row whose POs
have since become derivable would be re-flagged auto and its stored figure
replaced. Re-runs are deliberate, so this is acceptable; a hand-entered outlay you
want kept indefinitely should live on a shipment without a sourcing PO.
"""

import frappe

from exportflow.mtt import MERCHANTING


def execute():
	if not frappe.db.has_column("Export Shipment", "mtt_import_value_auto"):
		return
	for name in frappe.get_all("Export Shipment", filters={"trade_type": MERCHANTING}, pluck="name"):
		doc = frappe.get_doc("Export Shipment", name)
		facts = doc.computed_import_facts()
		derivable = facts["outlay_inr"] > 0
		auto = 1 if (derivable or not doc.mtt_import_value_inr) else 0
		updates = {"mtt_import_value_auto": auto}
		if auto and derivable:
			updates["mtt_import_value_inr"] = facts["outlay_inr"]
			updates["mtt_import_supplier"] = (
				facts["suppliers"][0] if len(facts["suppliers"]) == 1 else None
			)
		frappe.db.set_value("Export Shipment", name, updates, update_modified=False)
