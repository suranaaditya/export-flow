"""In-app reports — filterable registers with Excel / PDF export.

Each report is (META, rows_fn): META carries the title, columns and filter config;
rows_fn returns ALL company-scoped rows (permission-gated). The frontend filters
and totals client-side, then hands the on-screen rows back to report_export, which
formats them into .xlsx / .pdf — so the file always matches the screen and there is
no duplicated filter logic. Read-only aggregates over data the app already holds."""

import json

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, nowdate

from exportflow.company import exportflow_company

CLOSED_REL = ("Realized", "eBRC Closed", "Written Off", "Cancelled")

# report -> the doctype/permission that gates it
REPORT_PERM = {
	"realization": ("Export Realization", "read"),
	"incentive": ("Export Incentive", "read"),
	"sales_register": ("Sales Order", "read"),
	"gst_export": ("Export Shipment", "read"),
	"merchanting": ("Export Shipment", "read"),
}


def _company_filter(extra=None):
	company = exportflow_company()
	f = {"company": company} if company else {}
	if extra:
		f.update(extra)
	return f


def _shipment_inr(names):
	"""Per-shipment export value in INR = Σ (shipped qty × the SO line's base_rate,
	the selling rate in company currency). One query for the whole set."""
	if not names:
		return {}
	rows = frappe.db.sql(
		"""SELECT esi.parent AS shipment, COALESCE(SUM(esi.qty * soi.base_rate), 0) AS inr
		   FROM `tabExport Shipment Item` esi
		   JOIN `tabSales Order Item` soi ON soi.name = esi.so_detail
		   WHERE esi.parent IN %s GROUP BY esi.parent""",
		(tuple(names),),
		as_dict=True,
	)
	return {r.shipment: flt(r.inr, 2) for r in rows}


def col(key, label, type="text"):
	return {"key": key, "label": label, "type": type}


def flt_(key, label, control, field=None):
	return {"key": key, "label": label, "control": control, "field": field or key}


# ---------------------------------------------------------------- realization

REALIZATION_META = {
	"title": "Export realization (FEMA / EDPMS)",
	"columns": [
		col("export_invoice", "Export invoice", "id"), col("customer", "Customer"),
		col("currency", "Ccy"), col("invoice_value", "Invoice value", "num"),
		col("inr_value", "INR value", "inr"), col("export_date", "Export date", "date"),
		col("due_date", "FEMA due", "date"), col("realized_inr", "Realized", "inr"),
		col("outstanding_inr", "Outstanding", "inr"), col("days", "Days to due", "days"),
		col("status", "Status", "tag"), col("firc_no", "FIRC"), col("ebrc_number", "eBRC"),
		col("ad_bank", "AD bank"),
	],
	"filters": [
		flt_("daterange", "Export date", "daterange", "export_date"),
		flt_("status", "Status", "select"), flt_("currency", "Currency", "select"),
		flt_("overdue", "Overdue only", "toggle"),
	],
}


def _rows_realization():
	frappe.has_permission("Export Realization", "read", throw=True)
	today = getdate(nowdate())
	rows = []
	for r in frappe.get_all(
		"Export Realization", filters=_company_filter(),
		fields=["export_invoice", "customer", "shipment", "currency", "invoice_value", "conversion_rate",
				"export_date", "due_date", "status", "amount_received_inr", "firc_no", "ebrc_number", "ad_bank"],
		order_by="export_date desc, modified desc", limit_page_length=0,
	):
		expected = flt(r.invoice_value) * (flt(r.conversion_rate) or 1.0)
		received = flt(r.amount_received_inr)
		is_open = r.status not in CLOSED_REL
		overdue = bool(is_open and r.due_date and getdate(r.due_date) < today)
		rows.append({
			"export_invoice": r.export_invoice, "customer": r.customer, "currency": r.currency,
			"invoice_value": flt(r.invoice_value, 2), "inr_value": flt(expected, 2),
			"export_date": r.export_date, "due_date": r.due_date,
			"realized_inr": flt(received, 2),
			"outstanding_inr": flt(max(0.0, expected - received) if is_open else 0.0, 2),
			"days": (getdate(r.due_date) - today).days if (is_open and r.due_date) else None,
			"status": "Overdue" if overdue and r.status != "Overdue" else r.status,
			"firc_no": r.firc_no, "ebrc_number": r.ebrc_number, "ad_bank": r.ad_bank,
			"overdue": overdue,
		})
	return rows


# ---------------------------------------------------------------- incentive

INCENTIVE_META = {
	"title": "Incentive register (RoDTEP + Drawback)",
	"columns": [
		col("scheme", "Scheme"), col("shipment", "Shipment", "id"),
		col("shipping_bill_no", "Shipping bill"), col("shipping_bill_date", "SB date", "date"),
		col("fob_value", "FOB (INR)", "inr"), col("rate_pct", "Rate %", "pct"),
		col("amount", "Amount", "inr"), col("scroll_number", "Scroll"), col("scrip_number", "Scrip"),
		col("scrip_expiry", "Scrip expiry", "date"), col("amount_received", "Credited", "inr"),
		col("status", "Status", "tag"),
	],
	"filters": [
		flt_("daterange", "SB date", "daterange", "shipping_bill_date"),
		flt_("scheme", "Scheme", "select"), flt_("status", "Status", "select"),
	],
}


def _rows_incentive():
	frappe.has_permission("Export Incentive", "read", throw=True)
	rows = []
	for r in frappe.get_all(
		"Export Incentive", filters=_company_filter(),
		fields=["scheme", "shipment", "shipping_bill_no", "shipping_bill_date", "fob_value", "rate_pct",
				"amount", "scroll_number", "scrip_number", "scrip_expiry", "status", "amount_received"],
		order_by="shipping_bill_date desc, modified desc", limit_page_length=0,
	):
		rows.append({
			"scheme": r.scheme, "shipment": r.shipment, "shipping_bill_no": r.shipping_bill_no,
			"shipping_bill_date": r.shipping_bill_date, "fob_value": flt(r.fob_value, 2),
			"rate_pct": flt(r.rate_pct), "amount": flt(r.amount, 2), "scroll_number": r.scroll_number,
			"scrip_number": r.scrip_number, "scrip_expiry": r.scrip_expiry, "status": r.status,
			"amount_received": flt(r.amount_received, 2),
		})
	return rows


# ---------------------------------------------------------------- sales register

SALES_META = {
	"title": "Export sales register",
	"columns": [
		col("name", "Sales order", "id"), col("transaction_date", "Date", "date"),
		col("customer", "Customer"), col("country", "Destination"), col("currency", "Ccy"),
		col("grand_total", "Value (FCY)", "num"), col("inr_value", "Value (INR)", "inr"),
		col("incoterm", "Incoterm"), col("status", "Status", "tag"),
	],
	"filters": [
		flt_("daterange", "Order date", "daterange", "transaction_date"),
		flt_("customer", "Customer", "searchselect"), flt_("country", "Destination", "select"),
		flt_("currency", "Currency", "select"), flt_("status", "Status", "select"),
	],
}


def _rows_sales_register():
	frappe.has_permission("Sales Order", "read", throw=True)
	country = {
		c.name: c.destination_country or "Unknown"
		for c in frappe.get_all("Customer", fields=["name", "destination_country"], limit_page_length=0)
	}
	rows = []
	for so in frappe.get_all(
		"Sales Order", filters=_company_filter({"docstatus": 1}),
		fields=["name", "transaction_date", "customer", "customer_name", "currency", "grand_total",
				"base_grand_total", "status", "incoterm"],
		order_by="transaction_date desc", limit_page_length=0,
	):
		rows.append({
			"name": so.name, "transaction_date": so.transaction_date,
			"customer": so.customer_name or so.customer, "country": country.get(so.customer, "Unknown"),
			"currency": so.currency, "grand_total": flt(so.grand_total, 2),
			"inr_value": flt(so.base_grand_total, 2), "incoterm": so.incoterm, "status": so.status,
		})
	return rows


# ---------------------------------------------------------------- GST export

GST_META = {
	"title": "GST export report",
	"columns": [
		col("shipment", "Shipment", "id"), col("customer", "Customer"), col("mode", "Mode"),
		col("gst_mode", "GST treatment", "tag"), col("igst_rate", "IGST %", "pct"),
		col("shipping_bill_no", "Shipping bill"), col("shipping_bill_date", "SB date", "date"),
		col("leo_date", "LEO date", "date"), col("export_date", "Export date", "date"),
		col("inr_value", "Export value (INR)", "inr"),
	],
	"filters": [
		flt_("daterange", "Export date", "daterange", "export_date"),
		flt_("gst_mode", "GST treatment", "select"),
	],
}


def _rows_gst_export():
	frappe.has_permission("Export Shipment", "read", throw=True)
	from exportflow.mtt import is_merchanting

	ships = frappe.get_all(
		"Export Shipment", filters=_company_filter(),
		fields=["name", "customer_name", "mode", "trade_type", "gst_export_mode", "igst_rate",
				"shipping_bill_number", "shipping_bill_date", "leo_date", "bl_date", "awb_date"],
		order_by="creation desc", limit_page_length=0,
	)
	value = _shipment_inr([s.name for s in ships])
	rows = []
	for s in ships:
		export_date = s.awb_date if s.mode == "Air" else s.bl_date
		gst_mode = "Merchanting (out of GST)" if is_merchanting(s.trade_type) else (s.gst_export_mode or "—")
		rows.append({
			"shipment": s.name, "customer": s.customer_name, "mode": s.mode, "gst_mode": gst_mode,
			"igst_rate": flt(s.igst_rate) if s.igst_rate is not None else None,
			"shipping_bill_no": s.shipping_bill_number,
			"shipping_bill_date": s.shipping_bill_date, "leo_date": s.leo_date,
			"export_date": export_date, "inr_value": value.get(s.name, 0.0),
		})
	return rows


# ---------------------------------------------------------------- merchanting

MTT_META = {
	"title": "Merchanting (third-country / MTT) register",
	"columns": [
		col("shipment", "Shipment", "id"), col("customer", "Customer"), col("ad_bank", "AD bank"),
		col("commencement_date", "Commenced", "date"), col("completion_due", "Completion due", "date"),
		col("outlay_due", "Outlay due", "date"), col("import_value_inr", "Import outlay", "inr"),
		col("export_proceeds_inr", "Proceeds", "inr"), col("net_fx_profit_inr", "Net FX", "inr"),
		col("edpms_status", "EDPMS"), col("idpms_status", "IDPMS"), col("status", "Status", "tag"),
	],
	"filters": [
		flt_("daterange", "Commenced", "daterange", "commencement_date"),
		flt_("open", "Open only", "toggle"),
	],
}


def _rows_merchanting():
	frappe.has_permission("Export Shipment", "read", throw=True)
	from exportflow.api import MTT_SHIPMENT_FIELDS, _mtt_block
	from exportflow.mtt import MERCHANTING

	merch = frappe.get_all(
		"Export Shipment", filters=_company_filter({"trade_type": MERCHANTING}),
		fields=["name", "customer_name", *MTT_SHIPMENT_FIELDS], order_by="creation desc", limit_page_length=0,
	)
	rels = {}
	if merch:
		for r in frappe.get_all(
			"Export Realization",
			filters=_company_filter({"shipment": ["in", [m.name for m in merch]]}),
			fields=["shipment", "amount_received", "amount_received_inr", "invoice_value", "conversion_rate"],
			limit_page_length=0,
		):
			rels.setdefault(r.shipment, []).append(r)
	rows = []
	for s in merch:
		b = _mtt_block(s, rels.get(s.name, []))
		if not b:
			continue
		completed = b["completed"]
		breach = bool((not completed and (b["completion_days"] or 0) < 0) or (b["outlay_open"] and (b["outlay_days"] or 0) < 0))
		rows.append({
			"shipment": s.name, "customer": s.customer_name, "ad_bank": b.get("ad_bank"),
			"commencement_date": b.get("commencement_date"), "completion_due": b.get("completion_due"),
			"outlay_due": b.get("outlay_due"), "import_value_inr": flt(b.get("import_value_inr"), 2),
			"export_proceeds_inr": flt(b.get("export_proceeds_inr"), 2),
			"net_fx_profit_inr": flt(b.get("net_fx_profit_inr"), 2) if b.get("net_fx_profit_inr") is not None else None,
			"idpms_status": b.get("idpms_status"), "edpms_status": b.get("edpms_status"),
			"status": "Completed" if completed else ("Clock breached" if breach else "In progress"),
			"open": not completed,
		})
	return rows


REPORTS = {
	"realization": (REALIZATION_META, _rows_realization),
	"incentive": (INCENTIVE_META, _rows_incentive),
	"sales_register": (SALES_META, _rows_sales_register),
	"gst_export": (GST_META, _rows_gst_export),
	"merchanting": (MTT_META, _rows_merchanting),
}

REPORT_CATALOG = [
	{"key": "realization", "title": "Export realization", "sub": "FEMA / EDPMS", "icon": "rupee"},
	{"key": "incentive", "title": "Incentive register", "sub": "RoDTEP + Drawback", "icon": "sparkle"},
	{"key": "sales_register", "title": "Sales register", "sub": "the export MIS", "icon": "file-text"},
	{"key": "gst_export", "title": "GST export", "sub": "LUT / IGST / merchanting", "icon": "shield"},
	{"key": "merchanting", "title": "Merchanting", "sub": "third-country / MTT", "icon": "globe"},
]


@frappe.whitelist()
def report_list():
	"""The report catalogue, filtered to what the user may read."""
	return [r for r in REPORT_CATALOG if frappe.has_permission(*REPORT_PERM[r["key"]])]


@frappe.whitelist()
def report_data(report: str) -> dict:
	if report not in REPORTS:
		frappe.throw(_("Unknown report {0}").format(report))
	meta, rows_fn = REPORTS[report]
	return {**meta, "rows": rows_fn(), "company": exportflow_company()}


def _ind(n):
	"""Indian digit grouping (lakh/crore) for a 2-decimal number — matches the
	on-screen en-IN formatting so the PDF reads the same as the table."""
	neg = flt(n) < 0
	intp, dec = f"{abs(flt(n)):.2f}".split(".")
	if len(intp) > 3:
		last3, rest, parts = intp[-3:], intp[:-3], []
		while len(rest) > 2:
			parts.insert(0, rest[-2:])
			rest = rest[:-2]
		if rest:
			parts.insert(0, rest)
		intp = ",".join(parts) + "," + last3
	return ("-" if neg else "") + intp + "." + dec


def _fmt(value, ctype):
	if value is None or value == "":
		return ""
	if ctype == "inr":
		return f"₹{_ind(value)}"
	if ctype == "num":
		return _ind(value)
	if ctype == "pct":
		return f"{flt(value):g}%"
	if ctype == "date":
		try:
			return formatdate(value, "dd-MM-yyyy")
		except Exception:
			return str(value)
	if ctype == "days":
		try:
			d = int(value)
		except (ValueError, TypeError):
			return str(value)
		return f"{-d}d overdue" if d < 0 else (f"{d}d" if d else "today")
	return str(value)


def _xlsx_cell(value, ctype):
	"""Spreadsheet cell: real numbers / dates so Excel can sum, sort and filter,
	and formula-injection-guarded strings for free-text cells (a leading =,+,-,@
	would otherwise become a live formula on open)."""
	if value is None or value == "":
		return None
	if ctype in ("inr", "num"):
		return flt(value)
	if ctype == "date":
		try:
			return getdate(value)
		except Exception:
			return str(value)
	s = _fmt(value, ctype)
	return ("'" + s) if s[:1] in ("=", "+", "-", "@") else s


# ------------------------------------------------------------------- PDF layout

# Relative column widths for the fitted (table-layout:fixed) PDF table. The PDF has
# NO horizontal scroll, so the chosen columns must share one page width — type gives
# a sensible default, refined by key for the few columns whose natural width the type
# alone doesn't capture (a currency code needs far less room than a customer name).
_COL_W_TYPE = {"id": 11, "tag": 9, "date": 8, "inr": 11, "num": 10, "pct": 6, "days": 8, "text": 12}
_COL_W_KEY = {"currency": 4, "mode": 6, "incoterm": 6, "igst_rate": 6, "customer": 16}


def _col_weight(c):
	return _COL_W_KEY.get(c["key"]) or _COL_W_TYPE.get(c["type"], 11)


# Self-contained style. `.print-format { margin-* }` is the ONLY lever wkhtmltopdf
# honours for page margins (get_print_format_styles reads margins from a rule whose
# selector is EXACTLY `.print-format`); `div.print-format { margin:0 }` then zeroes
# the doubled element margin. table-layout:fixed + <col> %widths keep every column on
# one page width; thead repeats the header on each page.
_REPORT_PDF_CSS = """
*{box-sizing:border-box}
body{margin:0 !important;font-family:'Helvetica Neue',Arial,sans-serif;color:#1b2230}
.print-format{margin-top:8mm;margin-bottom:14mm;margin-left:10mm;margin-right:10mm}
div.print-format{margin:0 !important;padding:0 !important}
.efxr .lh{width:100%;border-collapse:collapse;margin-bottom:7px}
.efxr .lh td{vertical-align:middle;padding:0}
.efxr .lhl{width:1%;white-space:nowrap}
.efxr .lglogo{height:42px;width:auto;display:block}
.efxr .lhc{padding-left:11px}
.efxr .lgco{font-size:14px;font-weight:700;letter-spacing:.01em}
.efxr .lgad{font-size:9px;color:#5f6b7e;margin-top:1px;line-height:1.35}
.efxr .lhr{text-align:right;white-space:nowrap;vertical-align:middle}
.efxr .lgreg{font-size:8.5px;color:#5f6b7e;line-height:1.6}
.efxr .rule{height:0;border-top:2px solid #1b2230;margin:0 0 11px}
.efxr .rt{font-size:15px;font-weight:700;margin:0 0 3px}
.efxr .rs{font-size:9.5px;color:#6a7486;margin-bottom:10px}
.efxr .rs .mc{color:#1b2230;font-weight:600}
.efxr .data{width:100%;table-layout:fixed;border-collapse:collapse}
.efxr .data th,.efxr .data td{padding:4px 6px;text-align:left;vertical-align:top;word-wrap:break-word;overflow-wrap:break-word;border-bottom:.5px solid #e3e7ee}
.efxr .data th{background:#eef1f6;text-transform:uppercase;letter-spacing:.03em;color:#52607a;font-weight:600;border-bottom:1px solid #c7cedb}
.efxr .data td.inr,.efxr .data td.num,.efxr .data td.pct,.efxr .data td.days,.efxr .data th.inr,.efxr .data th.num,.efxr .data th.pct,.efxr .data th.days{text-align:right}
.efxr .data td.inr,.efxr .data td.num{font-variant-numeric:tabular-nums}
.efxr .data td.id{font-weight:500}
.efxr .data tr.ev td{background:#f7f9fb}
.efxr .data tr.tot td{border-top:1.5px solid #1b2230;background:#eef1f6;font-weight:700}
.efxr .data tr.tot td.tlbl{text-transform:uppercase;letter-spacing:.04em;color:#52607a}
thead{display:table-header-group}
tr{page-break-inside:avoid}
"""


def _report_pdf(title, subtitle, cols, data, totals):
	"""Build a professional, single-page-width PDF and its wkhtmltopdf options: an
	MN Globex letterhead, the active-filter summary, and a table that always fits the
	page width (table-layout:fixed + proportional column widths + auto orientation),
	with a running footer carrying the generated date and page numbers."""
	from exportflow.printing import exporter_profile

	esc = frappe.utils.escape_html
	prof = exporter_profile()
	stamp = formatdate(nowdate(), "dd MMM yyyy")

	n = len(cols)
	font = 9 if n <= 6 else (8 if n <= 10 else 7)
	weights = [_col_weight(c) for c in cols]
	total_w = sum(weights) or 1
	landscape = n > 6 or total_w > 70

	colgroup = "".join(f"<col style='width:{w / total_w * 100:.3f}%'/>" for w in weights)
	head = "".join(f"<th class='{c['type']}'>{esc(c['label'])}</th>" for c in cols)

	body_rows = []
	for i, r in enumerate(data):
		cells = "".join(f"<td class='{c['type']}'>{esc(_fmt(r.get(c['key']), c['type']))}</td>" for c in cols)
		body_rows.append(f"<tr class='{'ev' if i % 2 else 'od'}'>{cells}</tr>")
	if totals:
		# label the first column that is NOT itself a totalled (money) column — keying
		# the label to index 0 would lose it when the leading column is an inr column
		lbl_idx = next((i for i, c in enumerate(cols) if c["key"] not in totals), None)
		tcells = [
			(f"<td class='{c['type']}'>{esc(_fmt(totals[c['key']], c['type']))}</td>" if c["key"] in totals
			 else (f"<td class='tlbl'>{_('Total')}</td>" if i == lbl_idx else "<td></td>"))
			for i, c in enumerate(cols)
		]
		body_rows.append(f"<tr class='tot'>{''.join(tcells)}</tr>")
	body = "".join(body_rows)

	logo = f"<img class='lglogo' src='{prof.logo}'/>" if prof.get("logo") else ""
	ident = [f"<div class='lgco'>{esc(prof.company_name or '')}</div>"]
	if prof.get("letterhead_addr"):
		ident.append(f"<div class='lgad'>{esc(prof.letterhead_addr)}</div>")
	if prof.get("letterhead_contact"):
		ident.append(f"<div class='lgad'>{esc(prof.letterhead_contact)}</div>")
	reg = []
	if prof.get("gstin"):
		reg.append(f"GSTIN&nbsp;{esc(prof.gstin)}")
	if prof.get("iec"):
		reg.append(f"IEC&nbsp;{esc(prof.iec)}")
	reg_html = f"<div class='lgreg'>{'<br/>'.join(reg)}</div>" if reg else ""

	company = prof.company_name or exportflow_company() or ""
	crumb = f"{esc(subtitle)} &nbsp;·&nbsp; " if subtitle else ""
	meta_line = (
		f"<span class='mc'>{esc(company)}</span> &nbsp;·&nbsp; "
		f"{len(data)} row{'' if len(data) == 1 else 's'} &nbsp;·&nbsp; {crumb}generated {stamp}"
	)

	dyn = f".efxr .data{{font-size:{font}px}}.efxr .data th{{font-size:{max(7, font - 1)}px}}"
	html = (
		f"<style>{_REPORT_PDF_CSS}{dyn}</style>"
		f"<div class='print-format efxr'>"
		f"<table class='lh'><tr><td class='lhl'>{logo}</td>"
		f"<td class='lhc'>{''.join(ident)}</td><td class='lhr'>{reg_html}</td></tr></table>"
		f"<div class='rule'></div>"
		f"<h1 class='rt'>{esc(title)}</h1><div class='rs'>{meta_line}</div>"
		f"<table class='data'><colgroup>{colgroup}</colgroup>"
		f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
		f"</div>"
	)
	options = {
		"page-size": "A4",
		"orientation": "Landscape" if landscape else "Portrait",
		"footer-left": company[:70],
		"footer-center": f"Generated {stamp}",
		"footer-right": "Page [page] of [topage]",
		"footer-font-name": "Helvetica",
		"footer-font-size": "7",
		"footer-spacing": "3",
	}
	return html, options


@frappe.whitelist()
def report_export(report: str, fmt: str = "xlsx", rows=None, columns=None, subtitle: str = ""):
	"""Format the on-screen (already filtered) rows into a downloadable file. The
	column set + title come from the server-side report definition; the row data —
	and which columns to include (the user's PDF/Excel column choice) — come from the
	client, which already fetched them via report_data. `subtitle` is the human filter
	summary the client shows on screen, stamped under the PDF title so it is self-documenting."""
	if report not in REPORTS:
		frappe.throw(_("Unknown report {0}").format(report))
	if fmt not in ("xlsx", "pdf"):
		frappe.throw(_("Unsupported export format {0}").format(fmt))
	frappe.has_permission(*REPORT_PERM[report], throw=True)
	meta, _rows_fn = REPORTS[report]
	cols, title = meta["columns"], meta["title"]

	# honour the client's column selection: keep the canonical column order, ignore
	# unknown keys, and fall back to all columns if nothing valid was chosen (a
	# non-list payload — scalar/object — is simply ignored, not a crash)
	if columns:
		try:
			sel = json.loads(columns) if isinstance(columns, str) else columns
		except (ValueError, TypeError):
			sel = None
		if isinstance(sel, (list, tuple)):
			keys = {str(k) for k in sel}
			chosen = [c for c in cols if c["key"] in keys]
			if chosen:
				cols = chosen

	# rows are the on-screen list the client POSTs back; tolerate a malformed or
	# wrong-shaped payload (only list-of-dict rows survive) rather than 500-ing
	try:
		parsed = json.loads(rows) if isinstance(rows, str) else rows
	except (ValueError, TypeError):
		frappe.throw(_("Invalid rows payload"))
	data = [r for r in (parsed or []) if isinstance(r, dict)]
	slug, stamp = report.replace("_", "-"), nowdate()

	# total only the money (inr) columns — the meaningful sum across mixed currencies
	totals = {}
	for c in cols:
		if c["type"] == "inr":
			totals[c["key"]] = flt(sum(flt(r.get(c["key"])) for r in data), 2)

	if fmt == "pdf":
		from frappe.utils.pdf import get_pdf

		html, options = _report_pdf(title, (subtitle or "").strip()[:300], cols, data, totals)
		frappe.local.response.filename = f"{slug}-{stamp}.pdf"
		frappe.local.response.filecontent = get_pdf(html, options=options)
		frappe.local.response.type = "binary"
		return

	from frappe.utils.xlsxutils import make_xlsx

	matrix = [[c["label"] for c in cols]]
	matrix += [[_xlsx_cell(r.get(c["key"]), c["type"]) for c in cols] for r in data]
	if totals:
		lbl_idx = next((i for i, c in enumerate(cols) if c["key"] not in totals), None)
		matrix.append([
			flt(totals[c["key"]]) if c["key"] in totals else ("Total" if i == lbl_idx else None)
			for i, c in enumerate(cols)
		])
	frappe.local.response.filename = f"{slug}-{stamp}.xlsx"
	frappe.local.response.filecontent = make_xlsx(matrix, title[:31]).getvalue()
	frappe.local.response.type = "binary"
