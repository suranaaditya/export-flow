"""Third-country / merchanting trade (MTT) logic — see memory note
`third-country-merchanting`.

A merchanting trade buys from country A and sells to country B with the goods
never entering India. Such trades are outside GST (CGST Schedule III Entry 7),
carry no shipping bill / EGM / eBRC and earn no RoDTEP or Duty Drawback.
Instead RBI's FEMA MTT rules apply: both legs through the same AD bank, the
whole trade completed within ~9 months, forex outlay within ~4 months, and a
net foreign-exchange profit, closed through EDPMS/IDPMS rather than eBRC.

This module is the single source of truth for: the trade-type constants, the
set of documents merchanting suppresses, and the two FEMA clocks. It holds no
database access of its own (so it stays cheap to unit-test) — callers pass the
shipment, the window lengths and the export proceeds in.
"""

from frappe.utils import add_months, cint, flt, getdate, nowdate

MERCHANTING = "Third-country / Merchanting"
EXPORT_FROM_INDIA = "Export from India"
DEFAULT_TRADE_TYPE = EXPORT_FROM_INDIA

# FEM(O)A defaults — overridable in ExportFlow Settings (FEM Export/Import Regs
# 2026, effective 1 Oct 2026, may revise these numbers).
DEFAULT_COMPLETION_MONTHS = 9
DEFAULT_OUTLAY_MONTHS = 4

# Documents that legally cannot exist for a merchanting trade — the goods never
# touch Indian customs or the export-incentive/eBRC machinery. The checklist
# engine drops these (and their milestone-blocking) whenever a shipment is
# merchanting, regardless of which rules produced them.
SUPPRESSED_DOCS = frozenset(
	{
		"Shipping Bill",
		"ADC NOC",
		"Let Export Order",
		"EGM",
		"State Drug Controller Export NOC",
		"eBRC",
		"GST Supplier Compliance Pack",
	}
)


def is_merchanting(trade_type) -> bool:
	return (trade_type or DEFAULT_TRADE_TYPE) == MERCHANTING


def mtt_months(settings=None) -> tuple[int, int]:
	"""(completion_months, outlay_months) from ExportFlow Settings, falling back
	to the FEMA defaults. A non-positive override is treated as unset."""
	completion = outlay = None
	if settings is not None:
		completion = settings.get("mtt_completion_months")
		outlay = settings.get("mtt_outlay_months")
	return (
		cint(completion) or DEFAULT_COMPLETION_MONTHS,
		cint(outlay) or DEFAULT_OUTLAY_MONTHS,
	)


def _get(shipment, field):
	"""Read a field whether shipment is a Document or a plain dict."""
	if hasattr(shipment, "get"):
		return shipment.get(field)
	return getattr(shipment, field, None)


def clocks(
	shipment,
	*,
	completion_months: int,
	outlay_months: int,
	export_proceeds_inr=None,
	proceeds_received: bool = False,
	today=None,
) -> dict:
	"""Compute the MTT compliance picture for one shipment.

	`export_proceeds_inr` / `proceeds_received` come from the linked Export
	Realization (the caller has DB access; this module does not). Days are
	positive when the deadline is in the future, negative once overdue.
	"""
	today = getdate(today or nowdate())

	# 9-month completion clock runs from commencement (import payment, else ETD)
	commencement = (
		_get(shipment, "mtt_commencement_date")
		or _get(shipment, "mtt_import_payment_date")
		or _get(shipment, "etd")
	)
	completion_date = _get(shipment, "mtt_completion_date")
	completed = bool(completion_date)
	completion_due = add_months(getdate(commencement), completion_months) if commencement else None
	completion_days = (
		(getdate(completion_due) - today).days if (completion_due and not completed) else None
	)

	# 4-month forex-outlay clock runs from import payment until proceeds arrive
	import_payment = _get(shipment, "mtt_import_payment_date")
	outlay_open = bool(import_payment) and not proceeds_received
	outlay_due = add_months(getdate(import_payment), outlay_months) if import_payment else None
	outlay_days = (getdate(outlay_due) - today).days if (outlay_due and outlay_open) else None

	import_value = _get(shipment, "mtt_import_value_inr")
	import_value_inr = flt(import_value) if import_value else None
	proceeds = flt(export_proceeds_inr) if export_proceeds_inr else None
	net_fx_profit_inr = (
		flt(proceeds - import_value_inr, 2)
		if (import_value_inr is not None and proceeds is not None)
		else None
	)

	return {
		"is_merchanting": True,
		"commencement_date": str(commencement) if commencement else None,
		"completion_due": str(completion_due) if completion_due else None,
		"completion_days": completion_days,
		"completed": completed,
		"completion_date": str(completion_date) if completion_date else None,
		"outlay_due": str(outlay_due) if outlay_due else None,
		"outlay_days": outlay_days,
		"outlay_open": outlay_open,
		"import_payment_date": str(import_payment) if import_payment else None,
		"import_value_inr": import_value_inr,
		"export_proceeds_inr": proceeds,
		"net_fx_profit_inr": net_fx_profit_inr,
		"same_ad_bank": bool(_get(shipment, "mtt_same_ad_bank")),
		"ad_bank": _get(shipment, "mtt_ad_bank") or None,
		"idpms_status": _get(shipment, "mtt_idpms_status") or None,
		"edpms_status": _get(shipment, "mtt_edpms_status") or None,
	}
