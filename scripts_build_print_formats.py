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

EFX_CSS = """
<style>
  .efx { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #16181d; font-size: 10.5px; line-height: 1.4; }
  .efx .doc { border: 1.4px solid #16181d; }
  .efx .title { text-align: center; font-weight: 700; font-size: 14px; letter-spacing: .2em; text-transform: uppercase; padding: 7px 8px 6px; border-bottom: 1.4px solid #16181d; }
  .efx .title small { display: block; font-size: 8px; letter-spacing: .14em; font-weight: 500; color: #6b7280; margin-top: 2px; }
  .efx table { width: 100%; border-collapse: collapse; }
  .efx td, .efx th { vertical-align: top; }
  .efx .grid td { border: 0.7px solid #b9bec8; padding: 5px 9px; }
  .efx .seam td { border-bottom: 1.4px solid #16181d; }
  .efx .lbl { font-size: 7.6px; text-transform: uppercase; letter-spacing: .06em; color: #8a909c; font-weight: 600; margin-bottom: 2px; display: block; }
  .efx b { font-weight: 700; }
  .efx .mono { font-family: 'SFMono-Regular', Menlo, Consolas, monospace; }
  .efx .muted { color: #6b7280; }
  .efx .addr { white-space: pre-wrap; }
  .efx table.lines th { background: #f3f4f6; border: 0.7px solid #b9bec8; border-top: 1.4px solid #16181d; border-bottom: 1.4px solid #16181d; font-size: 8px; text-transform: uppercase; letter-spacing: .05em; color: #3b4250; padding: 5px 7px; text-align: left; }
  .efx table.lines td { border: 0.7px solid #b9bec8; padding: 6px 7px; }
  .efx .r { text-align: right; } .efx .c { text-align: center; }
  .efx .batches { margin-top: 5px; font-size: 8.8px; color: #3b4250; }
  .efx .batches .bt { padding: 1px 0; }
  .efx table.lines tr.sub td { border-top: 0; border-bottom: 0.5px dashed #d4d8df; font-size: 9px; padding-top: 2px; padding-bottom: 2px; }
  .efx table.lines tfoot td { border: 0.7px solid #b9bec8; border-top: 1.4px solid #16181d; padding: 6px 7px; font-weight: 700; }
  .efx .gd { padding: 6px 9px; font-size: 9.6px; }
  .efx .gd b { letter-spacing: .02em; }
  .efx .words { font-size: 9.6px; padding: 6px 9px; border-top: 0.7px solid #b9bec8; }
  .efx .tot td { padding: 3px 9px; font-size: 10px; }
  .efx .tot .g td { font-weight: 700; font-size: 11.5px; border-top: 1.4px solid #16181d; }
  .efx .sigbox { height: 70px; position: relative; }
  .efx .sigline { position: absolute; bottom: 6px; left: 9px; right: 9px; border-top: 0.7px solid #16181d; padding-top: 3px; font-size: 8.4px; }
  .efx .logo { max-height: 38px; max-width: 168px; margin-bottom: 5px; display: block; }
</style>
"""

# Shared top of the invoice / packing list: exporter + invoice meta, consignee /
# buyer, origin / destination, route. Composed per format with its own title.
def _efx_head(title, subtitle, show_money_meta=True):
	meta = """
        {% if ctx.buyer_order_no %}<tr><td class="lbl" style="border:0;padding:0 0 1px">Buyer's order no &amp; date</td></tr>
        <tr><td style="border:0;padding:0 0 5px"><span class="mono">{{ ctx.buyer_order_no }}</span>{% if ctx.buyer_order_date %} &middot; {{ frappe.utils.formatdate(ctx.buyer_order_date, "dd MMM yyyy") }}{% endif %}</td></tr>{% endif %}
        {% if ctx.ad_code %}<tr><td class="lbl" style="border:0;padding:0 0 1px">AD code</td></tr><tr><td style="border:0;padding:0"><span class="mono">{{ ctx.ad_code }}</span>{% if ctx.shipment.port_of_loading %} &middot; {{ ctx.shipment.port_of_loading }}{% endif %}</td></tr>{% endif %}
"""
	return ('{%- set ctx = document_print_context(doc.name) -%}\n' + EFX_CSS + """
<div class="efx"><div class="doc">
  <div class="title">""" + title + """<small>""" + subtitle + """</small></div>

  <table class="grid">
    <tr class="seam">
      <td style="width:58%">
        <span class="lbl">Exporter</span>
        {% if ctx.logo %}<img class="logo" src="{{ ctx.logo | e }}">{% endif %}
        <b>{{ ctx.company_name }}</b>
        {% if ctx.exporter_address %}<div class="addr muted">{{ ctx.exporter_address | e }}</div>{% endif %}
        <div style="margin-top:3px">{% if ctx.iec_number %}IEC <span class="mono">{{ ctx.iec_number }}</span>{% endif %}{% if ctx.gstin %} &nbsp; GSTIN <span class="mono">{{ ctx.gstin }}</span>{% endif %}</div>
      </td>
      <td>
        <table style="width:100%">
          <tr><td class="lbl" style="border:0;padding:0 0 1px">Invoice no &amp; date</td></tr>
          <tr><td style="border:0;padding:0 0 5px"><b class="mono">{{ doc.document_number or doc.name }}</b>{% if doc.document_date %} &middot; {{ frappe.utils.formatdate(doc.document_date, "dd MMM yyyy") }}{% endif %}</td></tr>
""" + meta + """
        </table>
      </td>
    </tr>
    <tr class="seam">
      <td><span class="lbl">Consignee</span><b>{{ ctx.consignee_name }}</b>{% if ctx.consignee_address %}<div class="addr muted">{{ ctx.consignee_address | e }}</div>{% endif %}</td>
      <td><span class="lbl">Buyer</span>{% if ctx.consignee_is_buyer %}<span class="muted">Same as consignee</span>{% else %}<b>{{ ctx.customer_name }}</b>{% if ctx.customer_address %}<div class="muted">{{ ctx.customer_address }}</div>{% endif %}{% endif %}</td>
    </tr>
    <tr class="seam">
      <td><span class="lbl">Country of origin of goods</span>{{ ctx.lines[0].country_of_origin if ctx.lines else "India" }}</td>
      <td><span class="lbl">Country of final destination</span>{{ ctx.destination_country or ctx.named_place or "—" }}</td>
    </tr>
    <tr>
      <td><span class="lbl">{% if ctx.shipment.mode == "Air" %}Flight / voyage{% else %}Vessel / voyage{% endif %}</span>{% if ctx.shipment.mode == "Sea" %}{{ ctx.shipment.vessel or "—" }}{% if ctx.shipment.voyage %} / {{ ctx.shipment.voyage }}{% endif %}{% else %}{{ ctx.shipment.airline or "—" }}{% if ctx.shipment.flight_number %} / {{ ctx.shipment.flight_number }}{% endif %}{% endif %}</td>
      <td><span class="lbl">Port of loading</span>{{ ctx.shipment.port_of_loading or "—" }}</td>
    </tr>
    <tr class="seam">
      <td><span class="lbl">Port of discharge</span>{{ ctx.shipment.port_of_discharge or "—" }}</td>
      <td><span class="lbl">Final destination</span>{{ ctx.shipment.final_destination or ctx.destination_country or "—" }}</td>
    </tr>
    <tr""" + ("" if show_money_meta else ' class="seam"') + """>
      <td><span class="lbl">Terms of delivery</span>{% if ctx.incoterm %}{{ ctx.incoterm }}{% if ctx.named_place %} &middot; {{ ctx.named_place }}{% endif %}{% else %}—{% endif %}</td>
      <td><span class="lbl">Terms of payment</span>{{ ctx.payment_terms or "—" }}</td>
    </tr>
  </table>
""")


COMMERCIAL_INVOICE = _efx_head("Commercial Invoice", "Customs &amp; bank negotiation copy") + """
  {% if not ctx.merchanting %}
  <div class="gd" style="border-bottom:1.4px solid #16181d">
    {% if ctx.gst_export_mode == "On payment of IGST" %}<b>Supply meant for export on payment of IGST.</b>
    {% else %}<b>Supply meant for export under LUT, without payment of IGST.</b>{% if ctx.lut_number %} LUT ARN <span class="mono">{{ ctx.lut_number }}</span>{% if ctx.lut_valid_upto %} (valid upto {{ frappe.utils.formatdate(ctx.lut_valid_upto, "dd MMM yyyy") }}){% endif %}.{% endif %}{% endif %}
  </div>
  {% else %}
  <div class="gd" style="border-bottom:1.4px solid #16181d"><b>Third-country / merchanting trade.</b> Goods shipped directly from country of origin to destination without entering India &mdash; outside the purview of GST (CGST Schedule III).</div>
  {% endif %}

  {% if ctx.mixed_currencies %}<div class="gd muted" style="border-bottom:0.7px solid #b9bec8;color:#b54708">Lines are priced in more than one currency &mdash; amounts shown per line.</div>{% endif %}
  <table class="lines">
    <thead><tr>
      <th style="width:22px">Sr</th><th>Description of goods</th><th style="width:78px">HS code</th>
      <th class="r" style="width:74px">Qty</th><th class="r" style="width:78px">Rate</th><th class="r" style="width:96px">Amount{% if ctx.currency %} ({{ ctx.currency }}){% endif %}</th>
    </tr></thead>
    <tbody>
    {% for row in ctx.lines %}
      <tr>
        <td class="c mono">{{ loop.index }}</td>
        <td>
          <b>{{ row.item_name }}</b>{% if row.grade %} &middot; {{ row.grade }}{% endif %}
          <div class="muted" style="font-size:8.8px;margin-top:1px">{% if row.cas_number %}CAS {{ row.cas_number }} &nbsp;{% endif %}Country of origin: {{ row.country_of_origin }}{% if row.pack_description %} &middot; {{ row.pack_description }}{% endif %}</div>
          {% if row.packs %}<div class="batches">
            {% for g in row.packs %}<div class="bt">&bull; Batch <b>{{ g.batch_no or "—" }}</b>{% if g.num_packages %} &middot; {{ g.num_packages }} {{ g.pack_type or "pkgs" }}{% endif %}{% if g.marks %} (nos {{ g.marks }}){% endif %}{% if g.mfg_date %} &middot; Mfg {{ frappe.utils.formatdate(g.mfg_date, "MMM yyyy") }}{% endif %}{% if g.exp_date %} &middot; Exp {{ frappe.utils.formatdate(g.exp_date, "MMM yyyy") }}{% endif %}</div>{% endfor %}
          </div>{% elif row.batch_no %}<div class="batches"><div class="bt">&bull; Batch <b>{{ row.batch_no }}</b></div></div>{% endif %}
        </td>
        <td class="mono">{{ row.hs_code or "—" }}</td>
        <td class="r mono">{{ "%g"|format(row.qty) }} {{ row.uom or "" }}</td>
        <td class="r mono">{{ frappe.utils.fmt_money(row.rate, currency=ctx.currency) if row.rate else "—" }}</td>
        <td class="r mono">{{ frappe.utils.fmt_money(row.amount, currency=ctx.currency) if row.rate else "—" }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>

  {% if ctx.currency %}
  <table>
    <tr>
      <td style="width:55%;border-right:0.7px solid #b9bec8;vertical-align:top">
        <div class="words"><span class="lbl">Amount in words</span>{{ ctx.grand_total_in_words }}</div>
        {% if ctx.taxable_value_inr %}<div class="gd" style="border-top:0.7px solid #b9bec8"><span class="lbl">Taxable value (INR)</span>{{ frappe.utils.fmt_money(ctx.taxable_value_inr, currency="INR") }} <span class="muted">@ {{ "%g"|format(ctx.shipment.inr_rate) }}/{{ ctx.currency }}</span> &nbsp;&middot;&nbsp; IGST @ {{ "%g"|format(ctx.igst_rate) }}% = {{ frappe.utils.fmt_money(ctx.igst_amount, currency="INR") }}</div>{% endif %}
      </td>
      <td>
        <table class="tot">
          <tr><td>Goods value (FOB)</td><td class="r mono">{{ frappe.utils.fmt_money(ctx.total, currency=ctx.currency) }}</td></tr>
          {% if ctx.freight %}<tr><td>Freight</td><td class="r mono">{{ frappe.utils.fmt_money(ctx.freight, currency=ctx.currency) }}</td></tr>{% endif %}
          {% if ctx.insurance %}<tr><td>Insurance</td><td class="r mono">{{ frappe.utils.fmt_money(ctx.insurance, currency=ctx.currency) }}</td></tr>{% endif %}
          <tr class="g"><td>Total ({{ ctx.incoterm_label }})</td><td class="r mono">{{ frappe.utils.fmt_money(ctx.grand_total, currency=ctx.currency) }}</td></tr>
        </table>
      </td>
    </tr>
  </table>
  {% else %}
  <div class="gd muted" style="border-top:0.7px solid #b9bec8">Lines are priced in more than one currency — the value totals are the per-line amounts above; the consolidated total is to be drawn up manually.</div>
  {% endif %}

  {% if ctx.scheme_suppliers %}
  <div class="gd" style="border-top:0.7px solid #b9bec8;background:#fafbfc">
    <span class="lbl">Merchant export &mdash; 0.1% concessional GST (Notification 41/2017&ndash;IGST(R))</span>
    {% for s in ctx.scheme_suppliers %}<div>{{ s.supplier_name }}{% if s.gstin %} &middot; GSTIN <span class="mono">{{ s.gstin }}</span>{% endif %}{% if s.invoice_no %} &middot; Inv <span class="mono">{{ s.invoice_no }}</span>{% if s.invoice_date %} {{ frappe.utils.formatdate(s.invoice_date, "dd MMM yyyy") }}{% endif %}{% endif %}</div>{% endfor %}
  </div>
  {% endif %}

  <table class="grid" style="border-top:1.4px solid #16181d">
    <tr>
      <td style="width:58%">
        <span class="lbl">Bank details for remittance</span>
        {% if ctx.has_bank %}<table style="width:100%;font-size:9.4px">
          {% if ctx.bank.name %}<tr><td style="border:0;padding:1px 8px 1px 0;width:88px" class="muted">Bank</td><td style="border:0;padding:1px 0">{{ ctx.bank.name }}{% if ctx.bank.branch %}, {{ ctx.bank.branch | e }}{% endif %}</td></tr>{% endif %}
          {% if ctx.bank.account_no %}<tr><td style="border:0;padding:1px 8px 1px 0" class="muted">Account no</td><td style="border:0;padding:1px 0"><span class="mono">{{ ctx.bank.account_no }}</span></td></tr>{% endif %}
          {% if ctx.bank.ifsc or ctx.bank.swift %}<tr><td style="border:0;padding:1px 8px 1px 0" class="muted">IFSC / SWIFT</td><td style="border:0;padding:1px 0"><span class="mono">{{ ctx.bank.ifsc or "—" }}</span> / <span class="mono">{{ ctx.bank.swift or "—" }}</span></td></tr>{% endif %}
          {% if ctx.bank.correspondent %}<tr><td style="border:0;padding:1px 8px 1px 0" class="muted">Correspondent</td><td style="border:0;padding:1px 0">{{ ctx.bank.correspondent | e }}</td></tr>{% endif %}
        </table>{% else %}<span class="muted">—</span>{% endif %}
      </td>
      <td class="sigbox">
        <div class="muted" style="font-size:9px">For <b>{{ ctx.company_name }}</b></div>
        <div class="sigline">{% if ctx.signatory_name %}{{ ctx.signatory_name }}{% if ctx.signatory_designation %} &middot; {{ ctx.signatory_designation }}{% endif %} &mdash; {% endif %}Authorised signatory</div>
      </td>
    </tr>
  </table>
</div></div>
"""

PACKING_LIST = _efx_head("Packing List", "Net, tare &amp; gross weights", show_money_meta=False) + """
  {% if ctx.invoice_number %}<div class="gd" style="border-bottom:1.4px solid #16181d">Against commercial invoice <b class="mono">{{ ctx.invoice_number }}</b>{% if ctx.invoice_date %} dated {{ frappe.utils.formatdate(ctx.invoice_date, "dd MMM yyyy") }}{% endif %}</div>{% endif %}
  <table class="lines">
    <thead><tr>
      <th style="width:22px">Sr</th><th>Description &amp; batch</th><th class="c" style="width:48px">Pkgs</th>
      <th class="r" style="width:118px">Net wt (Kg)</th><th class="r" style="width:118px">Tare wt (Kg)</th><th class="r" style="width:88px">Gross (Kg)</th>
    </tr></thead>
    <tbody>
    {% for row in ctx.lines %}
      <tr>
        <td class="c mono">{{ loop.index }}</td>
        <td><b>{{ row.item_name }}</b>{% if row.grade %} &middot; {{ row.grade }}{% endif %}<span class="muted">{% if row.hs_code %} &middot; HS {{ row.hs_code }}{% endif %}{% if row.cas_number %} &middot; CAS {{ row.cas_number }}{% endif %}</span>{% if not row.packs and row.pack_description %}<div class="muted" style="font-size:9px">{{ row.pack_description }}</div>{% endif %}</td>
        <td class="c mono">{{ row.packs|sum(attribute="num_packages") or "" }}</td>
        <td class="r mono">{{ "%g"|format(row.net_wt) if row.net_wt else "—" }}</td>
        <td class="r mono">{{ "%g"|format(row.tare_wt) if row.tare_wt else "—" }}</td>
        <td class="r mono">{{ "%g"|format(row.gross_wt) if row.gross_wt else "—" }}</td>
      </tr>
      {% for g in row.packs %}
      <tr class="sub">
        <td></td>
        <td class="muted" style="padding-left:18px">Batch <b>{{ g.batch_no or "—" }}</b>{% if g.num_packages %} &middot; {{ g.num_packages }} {{ g.pack_type or "pkgs" }}{% endif %}{% if g.marks %} (nos {{ g.marks }}){% endif %}{% if g.mfg_date %} &middot; Mfg {{ frappe.utils.formatdate(g.mfg_date, "MMM yyyy") }}{% endif %}{% if g.exp_date %} &middot; Exp {{ frappe.utils.formatdate(g.exp_date, "MMM yyyy") }}{% endif %}</td>
        <td class="c muted mono">{{ g.num_packages or "" }}</td>
        <td class="r muted mono">{% if g.num_packages %}{{ g.num_packages }} &times; {{ "%g"|format(g.net_per) }} = {% endif %}{{ "%g"|format(g.net) }}</td>
        <td class="r muted mono">{% if g.num_packages and g.tare_per %}{{ g.num_packages }} &times; {{ "%g"|format(g.tare_per) }} = {% endif %}{{ "%g"|format(g.tare) }}</td>
        <td class="r muted mono">{{ "%g"|format(g.gross) }}</td>
      </tr>
      {% endfor %}
    {% endfor %}
    </tbody>
    {% if ctx.packs_present %}<tfoot><tr>
      <td></td><td>Total</td><td class="c mono">{{ ctx.total_packages }}</td>
      <td class="r mono">{{ "%g"|format(ctx.net_total_wt) }}</td><td class="r mono">{{ "%g"|format(ctx.tare_total_wt) }}</td><td class="r mono">{{ "%g"|format(ctx.gross_total_wt) }}</td>
    </tr></tfoot>{% endif %}
  </table>

  <table class="grid" style="border-top:1.4px solid #16181d">
    <tr>
      <td style="width:58%"><span class="lbl">Declaration</span><span class="muted">We declare that this packing list shows the actual packed quantities and weights of the goods described, and that all particulars are true and correct.</span>{% if ctx.iec_number %}<div style="margin-top:3px">IEC <span class="mono">{{ ctx.iec_number }}</span></div>{% endif %}</td>
      <td class="sigbox">
        <div class="muted" style="font-size:9px">For <b>{{ ctx.company_name }}</b></div>
        <div class="sigline">{% if ctx.signatory_name %}{{ ctx.signatory_name }}{% if ctx.signatory_designation %} &middot; {{ ctx.signatory_designation }}{% endif %} &mdash; {% endif %}Authorised signatory</div>
      </td>
    </tr>
  </table>
</div></div>
"""

def _efx_sign(left=""):
	"""Bottom signatory band in the EFX bordered style."""
	return """
  <table class="grid" style="border-top:1.4px solid #16181d"><tr>
    <td style="width:58%">""" + (left or "&nbsp;") + """</td>
    <td class="sigbox"><div class="muted" style="font-size:9px">For <b>{{ ctx.company_name }}</b></div><div class="sigline">{% if ctx.signatory_name %}{{ ctx.signatory_name }}{% if ctx.signatory_designation %} &middot; {{ ctx.signatory_designation }}{% endif %} &mdash; {% endif %}Authorised signatory</div></td>
  </tr></table>
"""


def _efx_letter(title, subtitle, body, sign_left=""):
	"""Letter-style EFX document: bordered title, exporter + reference strip, a
	free-prose body and the signatory band. Shared by the declaration / banking
	documents that print from a shipment's Document Instance."""
	return ('{%- set ctx = document_print_context(doc.name) -%}\n' + EFX_CSS + """
<div class="efx"><div class="doc">
  <div class="title">""" + title + """<small>""" + subtitle + """</small></div>
  <table class="grid"><tr class="seam">
    <td style="width:60%"><span class="lbl">Exporter</span>{% if ctx.logo %}<img class="logo" src="{{ ctx.logo|e }}">{% endif %}<b>{{ ctx.company_name }}</b>{% if ctx.exporter_address %}<div class="addr muted">{{ ctx.exporter_address|e }}</div>{% endif %}<div style="margin-top:3px">{% if ctx.iec_number %}IEC <span class="mono">{{ ctx.iec_number }}</span>{% endif %}{% if ctx.gstin %} &nbsp; GSTIN <span class="mono">{{ ctx.gstin }}</span>{% endif %}</div></td>
    <td><span class="lbl">Reference</span><b class="mono">{{ doc.document_number or doc.name }}</b>{% if doc.document_date %}<div class="muted">Date {{ frappe.utils.formatdate(doc.document_date, "dd MMM yyyy") }}</div>{% endif %}{% if ctx.invoice_number %}<div class="muted" style="margin-top:3px">Against invoice <span class="mono">{{ ctx.invoice_number }}</span></div>{% endif %}</td>
  </tr></table>
""" + body + _efx_sign(sign_left) + """
</div></div>
""")


# Reusable EFX item table (description / HS / batch / qty) for the declaration
# and instruction documents.
EFX_LINES = """
  <table class="lines">
    <thead><tr><th style="width:22px">Sr</th><th>Description of goods</th><th style="width:84px">HS code</th><th style="width:104px">Batch</th><th class="r" style="width:92px">Quantity</th></tr></thead>
    <tbody>
    {% for row in ctx.lines %}
      <tr>
        <td class="c mono">{{ loop.index }}</td>
        <td><b>{{ row.item_name }}</b>{% if row.grade %} &middot; {{ row.grade }}{% endif %}{% if row.cas_number %} <span class="muted">&middot; CAS {{ row.cas_number }}</span>{% endif %}</td>
        <td class="mono">{{ row.hs_code or "—" }}</td>
        <td class="mono">{{ row.batch_no or (row.packs[0].batch_no if row.packs else "") or "—" }}</td>
        <td class="r mono">{{ "%g"|format(row.qty) }} {{ row.uom or "" }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
"""


SCOMET = _efx_letter(
	"SCOMET Declaration", "Non-applicability of export authorisation",
	"""  <div class="gd" style="font-size:10.5px;line-height:1.6">
  <p style="margin:0 0 8px">To,<br>The Deputy Commissioner of Customs{% if ctx.shipment.mode == "Air" %}, Air Cargo Complex{% endif %}{% if ctx.shipment.port_of_loading %},<br>{{ ctx.shipment.port_of_loading }}{% endif %}</p>
  <p style="margin:0 0 8px"><b>Subject:</b> Declaration of SCOMET non-applicability &mdash; shipment <span class="mono">{{ ctx.shipment.name }}</span>{% if ctx.invoice_number %} / invoice <span class="mono">{{ ctx.invoice_number }}</span>{% endif %}.</p>
  {% if ctx.scomet_text %}<p style="white-space:pre-wrap;margin:0">{{ ctx.scomet_text | e }}</p>
  {% else %}<p style="margin:0">We, <b>{{ ctx.company_name }}</b>{% if ctx.iec_number %} (IEC <span class="mono">{{ ctx.iec_number }}</span>){% endif %}, hereby declare that the goods listed below{% if ctx.destination_country %}, supplied to <b>{{ ctx.destination_country }}</b>,{% endif %} are <b>not</b> covered under the SCOMET (Special Chemicals, Organisms, Materials, Equipment and Technologies) list &mdash; Appendix 3 to Schedule 2 of the ITC(HS) Classification of Export and Import Items &mdash; and accordingly do not require an export authorisation under the Foreign Trade Policy.</p>{% endif %}
  </div>""" + EFX_LINES + """  <div class="gd" style="border-top:0.7px solid #b9bec8;font-size:10px">We undertake full responsibility for the accuracy of this declaration.</div>""",
)


SHIPPING_INSTRUCTION = _efx_head(
	"Shipping Instruction", "To the customs house agent / forwarder"
) + """
  <div class="gd" style="border-bottom:1.4px solid #16181d">To, <b>{{ ctx.shipment.cha or "The Customs House Agent" }}</b>{% if ctx.notify_party %} &nbsp;&middot;&nbsp; <b>Notify party:</b> <span style="white-space:pre-wrap">{{ ctx.notify_party | e }}</span>{% endif %}<br>Please arrange customs clearance and {{ "shipment" if ctx.shipment.mode == "Sea" else "uplift" }} of the consignment below{% if ctx.invoice_number %}, covered by our commercial invoice <span class="mono">{{ ctx.invoice_number }}</span>{% if ctx.invoice_date %} dated {{ frappe.utils.formatdate(ctx.invoice_date, "dd MMM yyyy") }}{% endif %}{% endif %}.</div>
""" + EFX_LINES + """
  <div class="gd" style="border-top:0.7px solid #b9bec8;background:#fafbfc;font-size:9.8px;line-height:1.55">
    <span class="lbl">Filing instructions</span>
    {% if ctx.merchanting %}Third-country / merchanting trade &mdash; outside GST; no shipping bill under India customs.
    {% elif ctx.gst_export_mode == "On payment of IGST" %}File the shipping bill for export <b>on payment of IGST</b>.
    {% elif ctx.lut_number %}File the shipping bill under <b>LUT without payment of IGST</b> (LUT ARN <span class="mono">{{ ctx.lut_number }}</span>).
    {% else %}Confirm the GST treatment with us before filing.{% endif %}
    {% if ctx.iec_number %} IEC <span class="mono">{{ ctx.iec_number }}</span>.{% endif %}
    {% if ctx.ad_code %} AD code at {{ ctx.shipment.port_of_loading }}: <span class="mono">{{ ctx.ad_code }}</span>.{% endif %}
    {% if ctx.scheme_suppliers %} Cargo includes goods procured under the 0.1% merchant-export scheme &mdash; supplier invoice references are on the commercial invoice.{% endif %}
    {% if ctx.lc %} Shipment is under LC <span class="mono">{{ ctx.lc.lc_number }}</span>{% if ctx.lc.latest_shipment_date %}; latest shipment date {{ frappe.utils.formatdate(ctx.lc.latest_shipment_date, "dd MMM yyyy") }}{% endif %} &mdash; please prioritise accordingly.{% endif %}
    Share the checklist of documents you need from us and keep us posted on examination and LEO.
  </div>""" + _efx_sign() + """
</div></div>
"""

BILL_OF_EXCHANGE = _efx_letter(
	"Bill of Exchange", "First of exchange (second of the same tenor and date being unpaid)",
	"""  <div class="gd" style="font-size:11px;line-height:1.7">
  {% if ctx.currency %}
  <p style="margin:0 0 10px;font-size:13px">Exchange for <b class="mono">{{ frappe.utils.fmt_money(ctx.grand_total, currency=ctx.currency) }}</b></p>
  <p style="margin:0 0 8px">At sight of this <b>FIRST</b> of Exchange (Second of the same tenor and date being unpaid), pay to the order of <b>{{ ctx.company_name }}</b> the sum of <b>{{ ctx.grand_total_in_words }}</b> for value received{% if ctx.invoice_number %} against our commercial invoice <span class="mono">{{ ctx.invoice_number }}</span>{% if ctx.invoice_date %} dated {{ frappe.utils.formatdate(ctx.invoice_date, "dd MMM yyyy") }}{% endif %}{% endif %}.</p>
  {% if ctx.lc %}<p style="margin:0">Drawn under {{ ctx.lc.issuing_bank or "the issuing bank" }} Letter of Credit No <span class="mono">{{ ctx.lc.lc_number }}</span>{% if ctx.lc.issue_date %} dated {{ frappe.utils.formatdate(ctx.lc.issue_date, "dd MMM yyyy") }}{% endif %}.</p>{% endif %}
  {% else %}<p class="muted" style="margin:0">Shipment lines are priced in more than one currency &mdash; issue this bill manually.</p>{% endif %}
  </div>
  <table class="grid" style="border-top:0.7px solid #b9bec8"><tr>
    <td style="width:50%"><span class="lbl">To (drawee)</span><b>{{ ctx.lc.issuing_bank if ctx.lc and ctx.lc.issuing_bank else ctx.customer_name }}</b>{% if ctx.lc %}<div class="muted">For account of: {{ ctx.customer_name }}</div>{% endif %}</td>
    <td><span class="lbl">Drawer</span><b>{{ ctx.company_name }}</b>{% if ctx.exporter_address %}<div class="addr muted">{{ ctx.exporter_address | e }}</div>{% endif %}</td>
  </tr></table>""",
)

COVERING_SCHEDULE = _efx_letter(
	"Document Presentation Schedule", "Covering schedule for negotiation / collection",
	"""  <div class="gd" style="font-size:10.5px;line-height:1.6">
  <p style="margin:0 0 8px">To,<br><b>{{ (ctx.lc.negotiating_bank or ctx.lc.advising_bank) if ctx.lc else "The Bank" }}</b></p>
  <p style="margin:0">We present the documents listed below {% if ctx.lc %}for negotiation under Letter of Credit <span class="mono">{{ ctx.lc.lc_number }}</span> issued by {{ ctx.lc.issuing_bank or "the issuing bank" }}{% if ctx.lc.expiry_date %}, expiring {{ frappe.utils.formatdate(ctx.lc.expiry_date, "dd MMM yyyy") }}{% endif %}{% else %}for collection{% endif %}{% if ctx.invoice_number %}, covering our commercial invoice <span class="mono">{{ ctx.invoice_number }}</span>{% if ctx.currency %} for {{ frappe.utils.fmt_money(ctx.grand_total, currency=ctx.currency) }}{% endif %}{% endif %}.{% if ctx.transport_doc.number %} {{ ctx.transport_doc.label }} <span class="mono">{{ ctx.transport_doc.number }}</span>{% if ctx.transport_doc.date %} dated {{ frappe.utils.formatdate(ctx.transport_doc.date, "dd MMM yyyy") }}{% endif %}.{% endif %}</p>
  </div>
  <table class="lines">
    <thead><tr><th style="width:22px">Sr</th><th>Document</th><th>Description</th><th class="r" style="width:74px">Originals</th><th class="r" style="width:62px">Copies</th></tr></thead>
    <tbody>
    {% if ctx.lc_requirements %}{% for req in ctx.lc_requirements %}<tr><td class="c mono">{{ loop.index }}</td><td><b>{{ req.document_type }}</b></td><td>{{ req.description or "—" }}</td><td class="r mono">{{ req.originals or "—" }}</td><td class="r mono">{{ req.copies or "—" }}</td></tr>{% endfor %}{% else %}<tr><td class="c mono">1</td><td colspan="4" class="muted">List the presented documents here (no LC requirement rows on this shipment).</td></tr>{% endif %}
    </tbody>
  </table>
  <div class="gd" style="border-top:0.7px solid #b9bec8;font-size:10px"><span class="lbl">Instructions</span>Please negotiate the documents and credit the proceeds to our account, advising us of the value date. Remit charges as per LC terms. Advise discrepancies, if any, immediately.</div>""",
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
	# the bordered professional redesign (data-fidelity build) — newer stamp
	REDESIGN = "2026-06-15 12:00:00.000000"
	write_format(
		"exportflow_commercial_invoice", "ExportFlow Commercial Invoice", COMMERCIAL_INVOICE, modified=REDESIGN
	)
	write_format("exportflow_packing_list", "ExportFlow Packing List", PACKING_LIST, modified=REDESIGN)
	write_format("exportflow_scomet_declaration", "ExportFlow SCOMET Declaration", SCOMET, modified=REDESIGN)
	write_format(
		"exportflow_shipping_instruction", "ExportFlow Shipping Instruction", SHIPPING_INSTRUCTION, modified=REDESIGN
	)
	write_format("exportflow_bill_of_exchange", "ExportFlow Bill of Exchange", BILL_OF_EXCHANGE, modified=REDESIGN)
	write_format("exportflow_covering_schedule", "ExportFlow Covering Schedule", COVERING_SCHEDULE, modified=REDESIGN)
	write_format(
		"exportflow_sales_order",
		"ExportFlow Sales Order",
		SALES_ORDER,
		doc_type="Sales Order",
		modified="2026-06-14 14:00:00.000000",
	)
