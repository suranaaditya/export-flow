"""One-shot generator for the Phase-4 print format JSONs (run locally, not shipped).
Keeps the HTML readable here; json.dump handles the escaping."""

import json
import os

BASE = os.path.join(os.path.dirname(__file__), "exportflow", "exportflow", "print_format")

SHARED_CSS = """
<style>
  .ef-doc { font-family: Helvetica, Arial, sans-serif; font-size: 12px; color: #1a2030; line-height: 1.5; }
  .ef-doc h1 { font-size: 19px; letter-spacing: .14em; margin: 0 0 2px; }
  .ef-doc .muted { color: #586273; }
  .ef-doc .mono { font-family: Menlo, Consolas, monospace; }
  .ef-doc .head { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #1a2030; padding-bottom: 10px; margin-bottom: 14px; }
  .ef-doc table.meta { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
  .ef-doc table.meta td { vertical-align: top; padding: 0 8px 8px 0; width: 50%; }
  .ef-doc .blk { border: 1px solid #dcdfe6; padding: 9px 11px; min-height: 72px; }
  .ef-doc .blk .lbl { font-size: 9.5px; text-transform: uppercase; letter-spacing: .08em; color: #586273; margin-bottom: 4px; }
  .ef-doc table.kv { width: 100%; border-collapse: collapse; font-size: 11px; }
  .ef-doc table.kv td { padding: 2px 8px 2px 0; }
  .ef-doc table.kv td.k { color: #586273; white-space: nowrap; width: 130px; }
  .ef-doc table.items { width: 100%; border-collapse: collapse; margin: 6px 0 0; }
  .ef-doc table.items th { text-align: left; font-size: 10px; text-transform: uppercase; letter-spacing: .06em; border-top: 1px solid #1a2030; border-bottom: 1px solid #1a2030; padding: 6px 8px; }
  .ef-doc table.items td { border-bottom: 1px solid #e7e9ee; padding: 6px 8px; vertical-align: top; }
  .ef-doc table.items .r { text-align: right; }
  .ef-doc .totals { margin-top: 8px; width: 100%; }
  .ef-doc .totals td { padding: 3px 8px; }
  .ef-doc .totals .grand { font-weight: bold; font-size: 13.5px; border-top: 2px solid #1a2030; }
  .ef-doc .decl { border: 1px solid #dcdfe6; background: #f7f8fa; padding: 8px 11px; margin-top: 12px; font-size: 11px; }
  .ef-doc .decl .lbl { font-size: 9.5px; text-transform: uppercase; letter-spacing: .08em; color: #586273; margin-bottom: 3px; }
  .ef-doc .foot { margin-top: 26px; display: flex; justify-content: space-between; gap: 20px; }
  .ef-doc .sig { margin-top: 52px; border-top: 1px solid #1a2030; width: 230px; padding-top: 4px; font-size: 10.5px; }
  .ef-doc .warn { color: #b54708; font-size: 11px; margin-top: 8px; }
</style>
"""

EXPORTER_CONSIGNEE = """
  <table class="meta"><tr>
    <td><div class="blk">
      <div class="lbl">Exporter</div>
      {% if ctx.logo %}<img src="{{ ctx.logo | e }}" style="max-height:42px;max-width:170px;margin-bottom:5px;display:block">{% endif %}
      <b>{{ ctx.company_name }}</b><br>
      {% if ctx.exporter_address %}<span style="white-space:pre-wrap">{{ ctx.exporter_address | e }}</span><br>{% endif %}
      {% if ctx.iec_number %}IEC: <span class="mono">{{ ctx.iec_number }}</span><br>{% endif %}
      {% if ctx.gstin %}GSTIN: <span class="mono">{{ ctx.gstin }}</span><br>{% endif %}
      {% if ctx.ad_code %}AD Code: <span class="mono">{{ ctx.ad_code }}</span>{% if ctx.shipment.port_of_loading %} ({{ ctx.shipment.port_of_loading }}){% endif %}{% endif %}
    </div></td>
    <td><div class="blk">
      <div class="lbl">Consignee / Buyer</div>
      <b>{{ ctx.customer_name }}</b><br>
      {% if ctx.customer_address %}{{ ctx.customer_address }}<br>{% endif %}
      {% if ctx.destination_country %}<span class="muted">Country of final destination:</span> {{ ctx.destination_country }}{% endif %}
    </div></td>
  </tr></table>
"""

SHIPMENT_BLOCK = """
  <div class="blk" style="margin-bottom:12px">
    <div class="lbl">Shipment</div>
    <table class="kv">
      <tr>
        <td class="k">Shipment ref</td><td class="mono">{{ ctx.shipment.name }}</td>
        <td class="k">Mode</td><td>{{ ctx.shipment.mode }}{% if ctx.shipment.mode == "Sea" and ctx.shipment.vessel %} · {{ ctx.shipment.vessel }}{% if ctx.shipment.voyage %} / {{ ctx.shipment.voyage }}{% endif %}{% elif ctx.shipment.mode == "Air" and ctx.shipment.airline %} · {{ ctx.shipment.airline }}{% if ctx.shipment.flight_number %} / {{ ctx.shipment.flight_number }}{% endif %}{% endif %}</td>
      </tr>
      <tr>
        <td class="k">Port of loading</td><td>{{ ctx.shipment.port_of_loading or "—" }}</td>
        <td class="k">Port of discharge</td><td>{{ ctx.shipment.port_of_discharge or "—" }}</td>
      </tr>
      <tr>
        <td class="k">Final destination</td><td>{{ ctx.shipment.final_destination or ctx.destination_country or "—" }}</td>
        <td class="k">Incoterm</td><td>{% if ctx.incoterm %}{{ ctx.incoterm }}{% if ctx.named_place %} · {{ ctx.named_place }}{% endif %}{% else %}—{% endif %}</td>
      </tr>
      <tr>
        <td class="k">{{ ctx.transport_doc.label }} no / date</td>
        <td>{% if ctx.transport_doc.number %}<span class="mono">{{ ctx.transport_doc.number }}</span>{% if ctx.transport_doc.date %} · {{ frappe.utils.formatdate(ctx.transport_doc.date, "dd MMM yyyy") }}{% endif %}{% else %}—{% endif %}</td>
        <td class="k">Shipping bill</td>
        <td>{% if ctx.shipment.shipping_bill_number %}<span class="mono">{{ ctx.shipment.shipping_bill_number }}</span>{% if ctx.shipment.shipping_bill_date %} · {{ frappe.utils.formatdate(ctx.shipment.shipping_bill_date, "dd MMM yyyy") }}{% endif %}{% else %}—{% endif %}</td>
      </tr>
      {% if ctx.shipment.container_numbers or ctx.lc %}
      <tr>
        <td class="k">Containers</td><td>{{ (ctx.shipment.container_numbers or "—").split("\\n") | join(", ") }}</td>
        <td class="k">Letter of credit</td><td>{% if ctx.lc %}<span class="mono">{{ ctx.lc.lc_number }}</span>{% if ctx.lc.issuing_bank %} · {{ ctx.lc.issuing_bank }}{% endif %}{% else %}—{% endif %}</td>
      </tr>
      {% endif %}
    </table>
  </div>
"""

SIGNATURE = """
  <div class="foot">
    <div style="flex:1"></div>
    <div>
      <div class="muted" style="font-size:10.5px">For {{ ctx.company_name }}</div>
      <div class="sig">{% if ctx.signatory_name %}{{ ctx.signatory_name }}{% if ctx.signatory_designation %} · {{ ctx.signatory_designation }}{% endif %}<br>{% endif %}Authorised signatory</div>
    </div>
  </div>
"""

COMMERCIAL_INVOICE = (
	'{%- set ctx = document_print_context(doc.name) -%}\n' + SHARED_CSS + """
<div class="ef-doc">
  <div class="head">
    <div>
      <h1>COMMERCIAL INVOICE</h1>
      <div class="muted">For export — customs and negotiation copy</div>
    </div>
    <div style="text-align:right">
      <div class="mono" style="font-size:14px"><b>{{ doc.document_number or doc.name }}</b></div>
      <div class="muted">Date: <span class="mono">{{ frappe.utils.formatdate(doc.document_date, "dd MMM yyyy") if doc.document_date else "—" }}</span></div>
    </div>
  </div>
""" + EXPORTER_CONSIGNEE + SHIPMENT_BLOCK + """
  {% if ctx.mixed_currencies %}<div class="warn">Shipment lines are priced in more than one currency — amounts below are per line.</div>{% endif %}
  <table class="items">
    <thead><tr>
      <th style="width:24px">#</th><th>Description of goods</th><th>HS code</th><th>Batch</th>
      <th class="r">Qty</th><th class="r">Rate</th><th class="r">Amount{% if ctx.currency %} ({{ ctx.currency }}){% endif %}</th>
    </tr></thead>
    <tbody>
    {% for row in ctx.lines %}
      <tr>
        <td class="mono">{{ loop.index }}</td>
        <td><b>{{ row.item_name }}</b>{% if row.grade %} · {{ row.grade }}{% endif %}{% if row.pack_description %}<br><span class="muted">{{ row.pack_description }}</span>{% endif %}<br><span class="muted">Country of origin: {{ row.country_of_origin }}</span></td>
        <td class="mono">{{ row.hs_code or "—" }}</td>
        <td class="mono">{{ row.batch_no or "—" }}</td>
        <td class="r mono">{{ row.qty }} {{ row.uom or "" }}</td>
        <td class="r mono">{{ frappe.utils.fmt_money(row.rate, currency=ctx.currency) if row.rate else "—" }}</td>
        <td class="r mono">{{ frappe.utils.fmt_money(row.amount, currency=ctx.currency) if row.rate else "—" }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>

  {% if ctx.currency %}
  <table class="totals"><tr>
    <td></td>
    <td style="width:45%">
      <table style="width:100%">
        <tr><td class="grand">Total{% if ctx.incoterm %} ({{ ctx.incoterm }}{% if ctx.named_place %}, {{ ctx.named_place }}{% endif %}){% endif %}</td>
            <td class="grand r mono" style="text-align:right">{{ frappe.utils.fmt_money(ctx.total, currency=ctx.currency) }}</td></tr>
        <tr><td class="muted" colspan="2" style="font-size:10.5px">{{ frappe.utils.money_in_words(ctx.total, ctx.currency) }}</td></tr>
      </table>
    </td>
  </tr></table>
  {% endif %}

  {% if ctx.lut_number %}
  <div class="decl">
    <div class="lbl">GST declaration</div>
    Supply meant for export under LUT without payment of IGST.
    LUT ARN: <span class="mono">{{ ctx.lut_number }}</span>{% if ctx.lut_valid_upto %} · valid upto {{ frappe.utils.formatdate(ctx.lut_valid_upto, "dd MMM yyyy") }}{% endif %}.
  </div>
  {% endif %}

  {% if ctx.scheme_suppliers %}
  <div class="decl">
    <div class="lbl">Merchant export — 0.1% concessional GST (Notification 40/2017 – Central Tax (Rate))</div>
    Goods procured from registered suppliers under the concessional rate:
    <table class="kv" style="margin-top:4px">
      {% for s in ctx.scheme_suppliers %}
      <tr>
        <td>{{ s.supplier_name }}</td>
        <td class="mono">{% if s.gstin %}GSTIN {{ s.gstin }}{% else %}GSTIN —{% endif %}</td>
        <td class="mono">{% if s.invoice_no %}Inv {{ s.invoice_no }}{% if s.invoice_date %} · {{ frappe.utils.formatdate(s.invoice_date, "dd MMM yyyy") }}{% endif %}{% else %}Inv —{% endif %}</td>
      </tr>
      {% endfor %}
    </table>
  </div>
  {% endif %}
""" + SIGNATURE + "\n</div>\n"
)

PACKING_LIST = (
	'{%- set ctx = document_print_context(doc.name) -%}\n' + SHARED_CSS + """
<div class="ef-doc">
  <div class="head">
    <div>
      <h1>PACKING LIST</h1>
      {% if ctx.invoice_number %}<div class="muted">Against commercial invoice <span class="mono">{{ ctx.invoice_number }}</span>{% if ctx.invoice_date %} dated {{ frappe.utils.formatdate(ctx.invoice_date, "dd MMM yyyy") }}{% endif %}</div>{% endif %}
    </div>
    <div style="text-align:right">
      <div class="mono" style="font-size:14px"><b>{{ doc.document_number or doc.name }}</b></div>
      <div class="muted">Date: <span class="mono">{{ frappe.utils.formatdate(doc.document_date, "dd MMM yyyy") if doc.document_date else "—" }}</span></div>
    </div>
  </div>
""" + EXPORTER_CONSIGNEE + SHIPMENT_BLOCK + """
  <table class="items">
    <thead><tr>
      <th style="width:24px">#</th><th>Description of goods</th><th>Batch</th><th>Packing</th><th class="r">Quantity</th>
    </tr></thead>
    <tbody>
    {% for row in ctx.lines %}
      <tr>
        <td class="mono">{{ loop.index }}</td>
        <td><b>{{ row.item_name }}</b>{% if row.grade %} · {{ row.grade }}{% endif %}</td>
        <td class="mono">{{ row.batch_no or "—" }}</td>
        <td>{{ row.pack_description or "—" }}</td>
        <td class="r mono">{{ row.qty }} {{ row.uom or "" }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
""" + SIGNATURE + "\n</div>\n"
)

SCOMET = (
	'{%- set ctx = document_print_context(doc.name) -%}\n' + SHARED_CSS + """
<div class="ef-doc">
  <div class="head">
    <div>
      <h1>SCOMET DECLARATION</h1>
      <div class="muted">Non-applicability of export authorisation</div>
    </div>
    <div style="text-align:right">
      <div class="mono" style="font-size:14px"><b>{{ doc.document_number or doc.name }}</b></div>
      <div class="muted">Date: <span class="mono">{{ frappe.utils.formatdate(doc.document_date, "dd MMM yyyy") if doc.document_date else "—" }}</span></div>
    </div>
  </div>

  <p>To,<br>The Deputy Commissioner of Customs{% if ctx.shipment.port_of_loading %},<br>{{ ctx.shipment.port_of_loading }}{% endif %}</p>

  <p><b>Subject: Declaration of SCOMET non-applicability — shipment <span class="mono">{{ ctx.shipment.name }}</span>{% if ctx.invoice_number %} / invoice <span class="mono">{{ ctx.invoice_number }}</span>{% endif %}</b></p>

  {% if ctx.scomet_text %}
  <p style="white-space:pre-wrap">{{ ctx.scomet_text | e }}</p>
  {% else %}
  <p>We, <b>{{ ctx.company_name }}</b>{% if ctx.iec_number %} (IEC <span class="mono">{{ ctx.iec_number }}</span>){% endif %},
  hereby declare that the goods listed below, exported to <b>{{ ctx.customer_name }}</b>{% if ctx.destination_country %}, {{ ctx.destination_country }}{% endif %},
  are <b>not</b> covered under the SCOMET (Special Chemicals, Organisms, Materials, Equipment and Technologies) list —
  Appendix 3 to Schedule 2 of the ITC(HS) Classification of Export and Import Items — and accordingly do not require
  an export authorisation under the Foreign Trade Policy.</p>
  {% endif %}

  <table class="items">
    <thead><tr><th style="width:24px">#</th><th>Description of goods</th><th>HS code</th><th>Batch</th><th class="r">Quantity</th></tr></thead>
    <tbody>
    {% for row in ctx.lines %}
      <tr>
        <td class="mono">{{ loop.index }}</td>
        <td><b>{{ row.item_name }}</b>{% if row.grade %} · {{ row.grade }}{% endif %}</td>
        <td class="mono">{{ row.hs_code or "—" }}</td>
        <td class="mono">{{ row.batch_no or "—" }}</td>
        <td class="r mono">{{ row.qty }} {{ row.uom or "" }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>

  <p style="margin-top:12px">We undertake full responsibility for the accuracy of this declaration.</p>
""" + SIGNATURE + "\n</div>\n"
)


SHIPPING_INSTRUCTION = (
	'{%- set ctx = document_print_context(doc.name) -%}\n' + SHARED_CSS + """
<div class="ef-doc">
  <div class="head">
    <div>
      <h1>SHIPPING INSTRUCTION</h1>
      <div class="muted">To the customs house agent</div>
    </div>
    <div style="text-align:right">
      <div class="mono" style="font-size:14px"><b>{{ doc.document_number or doc.name }}</b></div>
      <div class="muted">Date: <span class="mono">{{ frappe.utils.formatdate(doc.document_date, "dd MMM yyyy") if doc.document_date else "—" }}</span></div>
    </div>
  </div>

  <p>To,<br><b>{{ ctx.shipment.cha or "The Customs House Agent" }}</b></p>
  <p>Please arrange customs clearance and {{ "shipment" if ctx.shipment.mode == "Sea" else "uplift" }} of the following export consignment{% if ctx.invoice_number %} covered by our commercial invoice <span class="mono">{{ ctx.invoice_number }}</span>{% if ctx.invoice_date %} dated {{ frappe.utils.formatdate(ctx.invoice_date, "dd MMM yyyy") }}{% endif %}{% endif %}.</p>
""" + EXPORTER_CONSIGNEE + SHIPMENT_BLOCK + """
  <table class="items">
    <thead><tr><th style="width:24px">#</th><th>Description of goods</th><th>HS code</th><th>Batch</th><th>Packing</th><th class="r">Quantity</th></tr></thead>
    <tbody>
    {% for row in ctx.lines %}
      <tr>
        <td class="mono">{{ loop.index }}</td>
        <td><b>{{ row.item_name }}</b>{% if row.grade %} · {{ row.grade }}{% endif %}</td>
        <td class="mono">{{ row.hs_code or "—" }}</td>
        <td class="mono">{{ row.batch_no or "—" }}</td>
        <td>{{ row.pack_description or "—" }}</td>
        <td class="r mono">{{ row.qty }} {{ row.uom or "" }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>

  <div class="decl">
    <div class="lbl">Filing instructions</div>
    {% if ctx.lut_number %}File the shipping bill under LUT without payment of IGST (LUT ARN <span class="mono">{{ ctx.lut_number }}</span>).{% else %}Confirm the GST treatment with us before filing.{% endif %}
    {% if ctx.iec_number %} IEC: <span class="mono">{{ ctx.iec_number }}</span>.{% endif %}
    {% if ctx.ad_code %} AD code at {{ ctx.shipment.port_of_loading }}: <span class="mono">{{ ctx.ad_code }}</span>.{% endif %}
    {% if ctx.scheme_suppliers %} Cargo includes goods procured under the 0.1% merchant-export scheme — supplier invoice references are on the commercial invoice.{% endif %}
    {% if ctx.lc %} Shipment is under LC <span class="mono">{{ ctx.lc.lc_number }}</span>{% if ctx.lc.latest_shipment_date %}; latest shipment date {{ frappe.utils.formatdate(ctx.lc.latest_shipment_date, "dd MMM yyyy") }}{% endif %} — please prioritise accordingly.{% endif %}
    Share the checklist of documents you need from us and keep us posted on examination and LEO.
  </div>
""" + SIGNATURE + "\n</div>\n"
)

BILL_OF_EXCHANGE = (
	'{%- set ctx = document_print_context(doc.name) -%}\n' + SHARED_CSS + """
<div class="ef-doc">
  <div class="head">
    <div>
      <h1>BILL OF EXCHANGE</h1>
      <div class="muted">First of exchange (second of the same tenor and date being unpaid)</div>
    </div>
    <div style="text-align:right">
      <div class="mono" style="font-size:14px"><b>{{ doc.document_number or doc.name }}</b></div>
      <div class="muted">Date: <span class="mono">{{ frappe.utils.formatdate(doc.document_date, "dd MMM yyyy") if doc.document_date else "—" }}</span></div>
    </div>
  </div>

  {% if ctx.currency %}
  <p style="font-size:14px">Exchange for <b class="mono">{{ frappe.utils.fmt_money(ctx.total, currency=ctx.currency) }}</b></p>

  <p>At sight of this <b>FIRST</b> of Exchange (second of the same tenor and date being unpaid), pay to the order of
  <b>{{ ctx.company_name }}</b> the sum of <b>{{ ctx.total_in_words }}</b>
  for value received{% if ctx.invoice_number %} against our commercial invoice <span class="mono">{{ ctx.invoice_number }}</span>{% if ctx.invoice_date %} dated {{ frappe.utils.formatdate(ctx.invoice_date, "dd MMM yyyy") }}{% endif %}{% endif %}.</p>
  {% else %}
  <p class="warn">Shipment lines are priced in more than one currency — issue this bill manually.</p>
  {% endif %}

  {% if ctx.lc %}
  <p>Drawn under {{ ctx.lc.issuing_bank or "the issuing bank" }} Letter of Credit No <span class="mono">{{ ctx.lc.lc_number }}</span>{% if ctx.lc.issue_date %} dated {{ frappe.utils.formatdate(ctx.lc.issue_date, "dd MMM yyyy") }}{% endif %}.</p>
  {% endif %}

  <table class="meta" style="margin-top:14px"><tr>
    <td><div class="blk">
      <div class="lbl">To (drawee)</div>
      <b>{{ ctx.lc.issuing_bank if ctx.lc and ctx.lc.issuing_bank else ctx.customer_name }}</b>
      {% if ctx.lc %}<br><span class="muted">For account of:</span> {{ ctx.customer_name }}{% endif %}
    </div></td>
    <td><div class="blk">
      <div class="lbl">Drawer</div>
      <b>{{ ctx.company_name }}</b>
      {% if ctx.exporter_address %}<br><span style="white-space:pre-wrap">{{ ctx.exporter_address | e }}</span>{% endif %}
    </div></td>
  </tr></table>
""" + SIGNATURE + "\n</div>\n"
)

COVERING_SCHEDULE = (
	'{%- set ctx = document_print_context(doc.name) -%}\n' + SHARED_CSS + """
<div class="ef-doc">
  <div class="head">
    <div>
      <h1>DOCUMENT PRESENTATION SCHEDULE</h1>
      <div class="muted">Covering schedule for negotiation / collection</div>
    </div>
    <div style="text-align:right">
      <div class="mono" style="font-size:14px"><b>{{ doc.document_number or doc.name }}</b></div>
      <div class="muted">Date: <span class="mono">{{ frappe.utils.formatdate(doc.document_date, "dd MMM yyyy") if doc.document_date else "—" }}</span></div>
    </div>
  </div>

  <p>To,<br><b>{{ (ctx.lc.negotiating_bank or ctx.lc.advising_bank) if ctx.lc else "The Bank" }}</b></p>

  <p>We present the documents listed below
  {% if ctx.lc %}for negotiation under Letter of Credit <span class="mono">{{ ctx.lc.lc_number }}</span> issued by {{ ctx.lc.issuing_bank or "the issuing bank" }}{% if ctx.lc.expiry_date %}, expiring {{ frappe.utils.formatdate(ctx.lc.expiry_date, "dd MMM yyyy") }}{% endif %}{% else %}for collection{% endif %}{% if ctx.invoice_number %}, covering our commercial invoice <span class="mono">{{ ctx.invoice_number }}</span>{% if ctx.currency %} for {{ frappe.utils.fmt_money(ctx.total, currency=ctx.currency) }}{% endif %}{% endif %}.
  {% if ctx.transport_doc.number %}{{ ctx.transport_doc.label }} <span class="mono">{{ ctx.transport_doc.number }}</span>{% if ctx.transport_doc.date %} dated {{ frappe.utils.formatdate(ctx.transport_doc.date, "dd MMM yyyy") }}{% endif %}.{% endif %}</p>

  <table class="items">
    <thead><tr><th style="width:24px">#</th><th>Document</th><th>Description</th><th class="r">Originals</th><th class="r">Copies</th></tr></thead>
    <tbody>
    {% if ctx.lc_requirements %}
      {% for req in ctx.lc_requirements %}
      <tr>
        <td class="mono">{{ loop.index }}</td>
        <td><b>{{ req.document_type }}</b></td>
        <td>{{ req.description or "—" }}</td>
        <td class="r mono">{{ req.originals or "—" }}</td>
        <td class="r mono">{{ req.copies or "—" }}</td>
      </tr>
      {% endfor %}
    {% else %}
      <tr><td class="mono">1</td><td colspan="4" class="muted">List the presented documents here (no LC requirement rows on this shipment).</td></tr>
    {% endif %}
    </tbody>
  </table>

  <div class="decl">
    <div class="lbl">Instructions</div>
    Please negotiate the documents and credit the proceeds to our account, advising us of the value date.
    Remit charges as per LC terms. Advise discrepancies, if any, immediately.
  </div>
""" + SIGNATURE + "\n</div>\n"
)


SALES_ORDER = """{%- set ex = exporter_profile() -%}
{%- set cust_addr = party_address("Customer", doc.customer) -%}
{%- set dest = frappe.db.get_value("Customer", doc.customer, "destination_country") -%}
<style>
  .ef-so { font-family: Helvetica, Arial, sans-serif; font-size: 12px; color: #1a2030; line-height: 1.5; }
  .ef-so h1 { font-size: 20px; letter-spacing: .14em; margin: 0 0 2px; }
  .ef-so .muted { color: #586273; }
  .ef-so .mono { font-family: Menlo, Consolas, monospace; }
  .ef-so .head { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #1a2030; padding-bottom: 10px; margin-bottom: 14px; }
  .ef-so table.meta { width: 100%; border-collapse: collapse; margin-bottom: 14px; }
  .ef-so table.meta td { vertical-align: top; padding: 0 8px 0 0; width: 50%; }
  .ef-so .blk { border: 1px solid #dcdfe6; padding: 9px 11px; min-height: 86px; }
  .ef-so .blk .lbl { font-size: 9.5px; text-transform: uppercase; letter-spacing: .08em; color: #586273; margin-bottom: 4px; }
  .ef-so table.kv { width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 12px; }
  .ef-so table.kv td { padding: 2px 8px 2px 0; }
  .ef-so table.kv td.k { color: #586273; white-space: nowrap; width: 120px; }
  .ef-so table.items { width: 100%; border-collapse: collapse; margin: 6px 0 0; }
  .ef-so table.items th { text-align: left; font-size: 10px; text-transform: uppercase; letter-spacing: .06em; border-top: 1px solid #1a2030; border-bottom: 1px solid #1a2030; padding: 6px 8px; }
  .ef-so table.items td { border-bottom: 1px solid #e7e9ee; padding: 6px 8px; vertical-align: top; }
  .ef-so table.items .r { text-align: right; }
  .ef-so table.totals { width: 45%; margin-left: auto; margin-top: 8px; border-collapse: collapse; }
  .ef-so table.totals td { padding: 3px 8px; }
  .ef-so table.totals .r { text-align: right; }
  .ef-so table.totals .grand td { font-weight: bold; font-size: 14px; border-top: 2px solid #1a2030; }
  .ef-so .terms { margin-top: 16px; white-space: pre-wrap; }
  .ef-so .terms .lbl { font-size: 9.5px; text-transform: uppercase; letter-spacing: .08em; color: #586273; margin-bottom: 4px; }
  .ef-so .foot { margin-top: 26px; display: flex; justify-content: space-between; align-items: flex-end; }
  .ef-so .sig { margin-top: 50px; border-top: 1px solid #1a2030; width: 220px; padding-top: 4px; font-size: 10.5px; }
</style>
<div class="ef-so">
  <div class="head">
    <div>
      <h1>SALES ORDER</h1>
      <div class="muted">Export order confirmation</div>
    </div>
    <div style="text-align:right">
      <div class="mono" style="font-size:14px"><b>{{ doc.name }}</b></div>
      <div class="muted">Date: <span class="mono">{{ frappe.utils.formatdate(doc.transaction_date, "dd MMM yyyy") }}</span></div>
      {% if doc.delivery_date %}<div class="muted">Delivery by: <span class="mono">{{ frappe.utils.formatdate(doc.delivery_date, "dd MMM yyyy") }}</span></div>{% endif %}
      {% if doc.docstatus == 0 %}<div class="muted"><b>DRAFT</b></div>{% endif %}
    </div>
  </div>

  <table class="meta"><tr>
    <td><div class="blk">
      <div class="lbl">Exporter / Seller</div>
      {% if ex.logo %}<img src="{{ ex.logo | e }}" style="max-height:42px;max-width:170px;margin-bottom:5px;display:block">{% endif %}
      <b>{{ ex.company_name }}</b><br>
      {% if ex.address %}<span class="muted" style="white-space:pre-wrap">{{ ex.address | e }}</span><br>{% endif %}
      {% if ex.gstin %}GSTIN: <span class="mono">{{ ex.gstin }}</span><br>{% endif %}
      {% if ex.iec %}IEC: <span class="mono">{{ ex.iec }}</span>{% endif %}
    </div></td>
    <td><div class="blk">
      <div class="lbl">Customer / Buyer</div>
      <b>{{ doc.customer_name or doc.customer }}</b><br>
      {% if cust_addr %}<span class="muted" style="white-space:pre-wrap">{{ cust_addr | e }}</span><br>{% endif %}
      {% if dest %}<span class="muted">Country of final destination:</span> {{ dest }}{% endif %}
    </div></td>
  </tr></table>

  <table class="kv">
    <tr>
      <td class="k">Currency</td><td class="mono">{{ doc.currency }}</td>
      <td class="k">Incoterm</td><td>{% if doc.incoterm %}{{ doc.incoterm }}{% if doc.named_place %} · {{ doc.named_place }}{% endif %}{% else %}—{% endif %}</td>
    </tr>
    {% if doc.po_no or doc.payment_terms_template %}
    <tr>
      <td class="k">Buyer's ref</td><td class="mono">{{ doc.po_no or "—" }}</td>
      <td class="k">Payment terms</td><td>{{ doc.payment_terms_template or "—" }}</td>
    </tr>
    {% endif %}
  </table>

  <table class="items">
    <thead><tr><th style="width:26px">#</th><th>Description</th><th>HSN</th><th class="r">Qty</th><th class="r">Rate</th><th class="r">Amount ({{ doc.currency }})</th></tr></thead>
    <tbody>
    {% for row in doc.items %}
      <tr>
        <td class="mono">{{ loop.index }}</td>
        <td><b>{{ row.item_name }}</b>{% if row.item_code != row.item_name %}<br><span class="muted mono" style="font-size:10px">{{ row.item_code }}</span>{% endif %}</td>
        <td class="mono">{{ row.get("gst_hsn_code") or "" }}</td>
        <td class="r mono">{{ frappe.utils.flt(row.qty) }} {{ row.uom or "" }}</td>
        <td class="r mono">{{ frappe.utils.fmt_money(row.rate, currency=doc.currency) }}</td>
        <td class="r mono">{{ frappe.utils.fmt_money(row.amount, currency=doc.currency) }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>

  <table class="totals">
    <tr><td class="muted">Net total</td><td class="r mono">{{ frappe.utils.fmt_money(doc.net_total, currency=doc.currency) }}</td></tr>
    {% for tax in doc.taxes %}
    <tr><td class="muted">{{ tax.description }}{% if tax.rate %} @ {{ frappe.utils.flt(tax.rate) }}%{% endif %}</td><td class="r mono">{{ frappe.utils.fmt_money(tax.base_tax_amount_after_discount_amount or tax.tax_amount, currency=doc.currency) }}</td></tr>
    {% endfor %}
    <tr class="grand"><td>Grand total</td><td class="r mono">{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}</td></tr>
    <tr><td colspan="2" class="muted" style="font-size:10.5px">{{ frappe.utils.money_in_words(doc.grand_total, doc.currency) }}</td></tr>
  </table>

  {% if doc.terms %}
  <div class="terms">
    <div class="lbl">Terms &amp; conditions{% if doc.tc_name %} · {{ doc.tc_name }}{% endif %}</div>{{ doc.terms | striptags }}
  </div>
  {% endif %}

  <div class="foot">
    <div class="muted" style="font-size:10.5px">This sales order is system generated by ExportFlow.</div>
    <div>
      <div class="muted" style="font-size:10.5px">For {{ ex.company_name }}</div>
      <div class="sig">{% if ex.signatory_name %}{{ ex.signatory_name }}{% if ex.signatory_designation %} · {{ ex.signatory_designation }}{% endif %}<br>{% endif %}Authorised signatory</div>
    </div>
  </div>
</div>
"""


def write_format(
	folder: str,
	name: str,
	html: str,
	doc_type: str = "Document Instance",
	modified: str = "2026-06-12 12:30:00.000000",
):
	payload = {
		"absolute_value": 0,
		"align_labels_right": 0,
		"creation": "2026-06-12 10:00:00.000000",
		"css": "",
		"custom_format": 1,
		"default_print_language": "en",
		"disabled": 0,
		"doc_type": doc_type,
		"docstatus": 0,
		"doctype": "Print Format",
		"font_size": 12,
		"html": html,
		"idx": 0,
		"line_breaks": 0,
		"margin_bottom": 15.0,
		"margin_left": 15.0,
		"margin_right": 15.0,
		"margin_top": 15.0,
		# bump on every edit — frappe only re-syncs a standard print format
		# when the file's modified stamp is newer than the DB record
		"modified": modified,
		"modified_by": "Administrator",
		"module": "ExportFlow",
		"name": name,
		"owner": "Administrator",
		"page_number": "Hide",
		"print_format_builder": 0,
		"print_format_type": "Jinja",
		"raw_printing": 0,
		"show_section_headings": 0,
		"standard": "Yes",
	}
	path = os.path.join(BASE, folder, folder + ".json")
	with open(path, "w") as f:
		json.dump(payload, f, indent=1, sort_keys=True, ensure_ascii=False)
		f.write("\n")
	print("wrote", path)


if __name__ == "__main__":
	# the logo was added to the Exporter block (these three) — bump their stamp;
	# the formats below keep their old stamp so migrate doesn't needlessly re-sync
	NEW = "2026-06-14 14:00:00.000000"
	write_format(
		"exportflow_commercial_invoice", "ExportFlow Commercial Invoice", COMMERCIAL_INVOICE, modified=NEW
	)
	write_format("exportflow_packing_list", "ExportFlow Packing List", PACKING_LIST, modified=NEW)
	write_format("exportflow_scomet_declaration", "ExportFlow SCOMET Declaration", SCOMET)
	write_format(
		"exportflow_shipping_instruction", "ExportFlow Shipping Instruction", SHIPPING_INSTRUCTION, modified=NEW
	)
	write_format("exportflow_bill_of_exchange", "ExportFlow Bill of Exchange", BILL_OF_EXCHANGE)
	write_format("exportflow_covering_schedule", "ExportFlow Covering Schedule", COVERING_SCHEDULE)
	write_format(
		"exportflow_sales_order",
		"ExportFlow Sales Order",
		SALES_ORDER,
		doc_type="Sales Order",
		modified="2026-06-14 14:00:00.000000",
	)
