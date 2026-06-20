# Copyright (c) 2026, DUX Digitech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_months, flt, getdate

from exportflow.mtt import is_merchanting, mtt_months

# FEMA realization window (RBI raised it from 9 to 15 months in late 2025;
# 18 months when the export is invoiced/settled in INR)
REALIZATION_MONTHS = 15
REALIZATION_MONTHS_INR = 18


def expected_due(shipment_facts, export_date, currency, completion_months):
	"""The FEMA due date for export proceeds. Merchanting proceeds follow the
	MTT completion clock (commencement + N months); ordinary exports follow the
	15/18-month realization window. Pure — callers supply the shipment facts and
	the configured window so it can be reused outside the controller."""
	if shipment_facts and is_merchanting(shipment_facts.get("trade_type")):
		commencement = (
			shipment_facts.get("mtt_commencement_date") or shipment_facts.get("etd") or export_date
		)
		return add_months(getdate(commencement), completion_months) if commencement else None
	if not export_date:
		return None
	months = REALIZATION_MONTHS_INR if currency == "INR" else REALIZATION_MONTHS
	return add_months(getdate(export_date), months)


def resync_due_dates_for_shipment(doc, method=None):
	"""Export Shipment on_update hook: when trade type or MTT commencement
	changes, the FEMA clock basis for the shipment's realizations changes too.
	Move any due date that was still tracking the old formula to the new one;
	deliberate manual overrides are left untouched."""
	before = doc.get_doc_before_save()
	if not before:
		return
	watched = ("trade_type", "mtt_commencement_date", "etd")
	if not any(before.get(f) != doc.get(f) for f in watched):
		return

	completion_months, _ = mtt_months(frappe.get_cached_doc("ExportFlow Settings"))
	old_facts = {f: before.get(f) for f in watched}
	new_facts = {f: doc.get(f) for f in watched}
	for r in frappe.get_all(
		"Export Realization",
		filters={"shipment": doc.name},
		fields=["name", "export_date", "currency", "due_date"],
	):
		new_exp = expected_due(new_facts, r.export_date, r.currency, completion_months)
		if not new_exp or not r.due_date:
			continue
		old_exp = expected_due(old_facts, r.export_date, r.currency, completion_months)
		if old_exp and getdate(r.due_date) == getdate(old_exp) and getdate(r.due_date) != getdate(new_exp):
			frappe.db.set_value("Export Realization", r.name, "due_date", new_exp, update_modified=False)


def fill_export_dates_for_shipment(doc, method=None):
	"""Export Shipment on_update hook (companion to the auto-created realization
	shell): when the BL/AWB date is first entered, fill the FEMA export_date —
	and the due date — on the shipment's realizations that are still waiting for
	it. resync_due_dates_for_shipment only *moves* a due that already tracked a
	formula, so it can never backfill a shell created at CI time with a blank
	export_date; this closes that gap.

	Only blank export_dates are filled (never overwrite a manual one); closed
	realizations are left alone; the due date is set only when itself still blank
	(a deliberate manual due survives)."""
	before = doc.get_doc_before_save()
	if not before:
		return
	dep_field = "awb_date" if doc.mode == "Air" else "bl_date"
	dep_date = doc.get(dep_field)
	if not dep_date or before.get(dep_field):
		return  # only when the departure date is newly set

	completion_months, _ = mtt_months(frappe.get_cached_doc("ExportFlow Settings"))
	facts = {f: doc.get(f) for f in ("trade_type", "mtt_commencement_date", "etd")}
	closed = ("Realized", "eBRC Closed", "Written Off", "Cancelled")
	for r in frappe.get_all(
		"Export Realization",
		filters={
			"shipment": doc.name,
			"export_date": ["is", "not set"],
			"status": ["not in", closed],
		},
		fields=["name", "currency", "due_date"],
	):
		updates = {"export_date": dep_date}
		new_due = expected_due(facts, dep_date, r.currency, completion_months)
		if new_due and not r.due_date:
			updates["due_date"] = new_due
		frappe.db.set_value("Export Realization", r.name, updates, update_modified=False)


class ExportRealization(Document):
	def validate(self):
		if not self.company and self.shipment:
			self.company = frappe.db.get_value("Export Shipment", self.shipment, "company")
		if not self.company:
			from exportflow.company import exportflow_company

			self.company = exportflow_company()
		self.pull_shipment_facts()
		self.set_due_date()
		self.apply_forward_contract()

	def pull_shipment_facts(self):
		self._shipment_facts = None
		if not self.shipment:
			return
		shp = frappe.db.get_value(
			"Export Shipment",
			self.shipment,
			["customer", "mode", "bl_date", "awb_date", "trade_type", "mtt_commencement_date", "etd"],
			as_dict=True,
		)
		if not shp:
			return
		self._shipment_facts = shp
		if not self.customer:
			self.customer = shp.customer
		if not self.export_date:
			self.export_date = shp.awb_date if shp.mode == "Air" else shp.bl_date

	def _expected_due(self, export_date, currency):
		completion_months, _ = mtt_months(frappe.get_cached_doc("ExportFlow Settings"))
		return expected_due(self._shipment_facts, export_date, currency, completion_months)

	def set_due_date(self):
		"""FEMA window from the export date (MTT completion clock for
		merchanting); recompute when the inputs are corrected, but preserve a
		deliberate manual due date."""
		expected = self._expected_due(self.export_date, self.currency)
		if not expected:
			return
		if self.is_new() or not self.due_date:
			self.due_date = expected
			return
		before = self.get_doc_before_save()
		if before and (before.export_date != self.export_date or before.currency != self.currency):
			old_expected = self._expected_due(before.export_date, before.currency)
			# only auto-move if the due date was still tracking the formula
			if old_expected and getdate(self.due_date) == old_expected:
				self.due_date = expected

	def apply_forward_contract(self):
		"""When settled under a forward contract, lock the conversion rate to the forward
		rate and copy its reference (for display + the MIS register). Clears the link when
		the conversion mode is anything else."""
		if self.conversion_mode != "Forward Contract":
			self.forward_contract = None
			self.fwd_contract_no = None
			self.fwd_rate = None
			return
		if not self.forward_contract:
			return
		fc = frappe.db.get_value(
			"Forward Contract", self.forward_contract,
			["contract_no", "forward_rate", "currency"], as_dict=True,
		)
		if not fc:
			return
		if fc.currency and self.currency and fc.currency != self.currency:
			frappe.throw(
				frappe._("Forward contract {0} is in {1}, not {2}.").format(
					self.forward_contract, fc.currency, self.currency
				)
			)
		self.fwd_contract_no = fc.contract_no
		if flt(fc.forward_rate) > 0:
			self.fwd_rate = fc.forward_rate
			self.conversion_rate = fc.forward_rate

	def is_overdue(self, today=None) -> bool:
		from frappe.utils import nowdate

		if self.status in ("Realized", "eBRC Closed", "Written Off", "Cancelled"):
			return False
		return bool(self.due_date and getdate(self.due_date) < getdate(today or nowdate()))
