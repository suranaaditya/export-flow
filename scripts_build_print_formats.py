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
  .print-format { margin-top: 6mm; margin-bottom: 8mm; margin-left: 12mm; margin-right: 12mm; }
  body { margin: 0 !important; }
  div.print-format { margin: 0 !important; padding: 0 !important; }
  .efx { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #16181d; font-size: 10.5px; line-height: 1.4; }
  .efx .doc { border: 1.4px solid #16181d; }
  .efx .title { text-align: center; font-weight: 700; font-size: 14px; letter-spacing: .2em; text-transform: uppercase; padding: 7px 8px 6px; border-bottom: 1.4px solid #16181d; }
  .efx .title small { display: block; font-size: 8px; letter-spacing: .14em; font-weight: 500; color: #6b7280; margin-top: 2px; }
  .efx table { width: 100%; border-collapse: collapse; }
  .efx td, .efx th { vertical-align: top; }
  .efx .grid td { border: 0.7px solid #b9bec8; padding: 3px 9px; }
  .efx .grid td table td { padding-top: 0 !important; padding-bottom: 2px !important; line-height: 1.3 !important; }
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
  .efx .words { font-size: 9.6px; padding: 6px 9px; }
  .efx .tot td { padding: 3px 9px; font-size: 10px; }
  .efx .tot .g td { font-weight: 700; font-size: 11.5px; border-top: 1.4px solid #16181d; }
  .efx .sigbox { height: 70px; position: relative; }
  .efx .sigline { position: absolute; bottom: 6px; left: 9px; right: 9px; border-top: 0.7px solid #16181d; padding-top: 3px; font-size: 8.4px; }
  .efx .logo { max-height: 38px; max-width: 168px; margin-bottom: 5px; display: block; }
  .efx table.lh { width: 100%; border-collapse: collapse; }
  .efx table.lh td { vertical-align: middle; padding: 0; }
  .efx table.lh td.lh-logo { width: 104px; }
  .efx table.lh td.lh-logo img { height: 46px; max-width: 100px; display: block; }
  .efx td.lh-id { text-align: center; }
  .efx td.lh-id .nm { font-size: 15px; font-weight: 700; color: #16181d; letter-spacing: .015em; }
  .efx td.lh-id .addr { font-size: 8.6px; color: #41485a; line-height: 1.62; margin-top: 2px; }
  .efx td.lh-certs { width: 166px; text-align: right; white-space: nowrap; }
  .efx td.lh-certs img { height: 38px; vertical-align: middle; }
  .efx .lh-rule img { width: 100%; height: 3px; display: block; margin: 8px 0 11px; }
</style>
"""

# Letterhead banner — logo on the left, the exporter's branded identity on the
# right, a rule below: the client's own letterhead style. Sits above the bordered
# document box on every format. Two variants because the shipment formats carry
# ctx.* (document_print_context) while the SO / PO / PFI carry ex.* (exporter_profile).
def _letterhead(logo, name, addr, contact, certs, rule):
	t = """
  <table class="lh"><tr>
    <td class="lh-logo">{% if @LOGO@ %}<img src="{{ @LOGO@ | e }}">{% endif %}</td>
    <td class="lh-id">
      <div class="nm">{{ @NAME@ }}</div>
      {% if @ADDR@ %}<div class="addr">{{ @ADDR@ | e }}{% if @CONTACT@ %}<br>{{ @CONTACT@ | e }}{% endif %}</div>{% endif %}
    </td>
    <td class="lh-certs">{% if @CERTS@ %}<img src="{{ @CERTS@ | e }}">{% endif %}</td>
  </tr></table>
  {% if @RULE@ %}<div class="lh-rule"><img src="{{ @RULE@ | e }}"></div>{% else %}<div style="height:2px;background:#16181d;margin:8px 0 11px"></div>{% endif %}
"""
	return (t.replace("@LOGO@", logo).replace("@NAME@", name).replace("@ADDR@", addr)
	        .replace("@CONTACT@", contact).replace("@CERTS@", certs).replace("@RULE@", rule))


LH_CTX = _letterhead("ctx.logo", "ctx.company_name", "ctx.letterhead_addr", "ctx.letterhead_contact", "ctx.cert_badges", "ctx.gradient_rule")
LH_EX = _letterhead("ex.logo", "ex.company_name", "ex.letterhead_addr", "ex.letterhead_contact", "ex.cert_badges", "ex.gradient_rule")


# Shared top of the invoice / packing list: exporter + invoice meta, consignee /
# buyer, origin / destination, route. Composed per format with its own title.
def _efx_head(title, subtitle, show_money_meta=True):
	meta = """
        {% if ctx.buyer_order_no %}<tr><td class="lbl" style="border:0;padding:0 0 1px">Buyer's order no &amp; date</td></tr>
        <tr><td style="border:0;padding:0 0 3px"><span class="mono">{{ ctx.buyer_order_no }}</span>{% if ctx.buyer_order_date %} &middot; {{ frappe.utils.formatdate(ctx.buyer_order_date, "dd MMM yyyy") }}{% endif %}</td></tr>{% endif %}
        {% if ctx.ad_code %}<tr><td class="lbl" style="border:0;padding:0 0 1px">AD code</td></tr><tr><td style="border:0;padding:0"><span class="mono">{{ ctx.ad_code }}</span>{% if ctx.shipment.port_of_loading %} &middot; {{ ctx.shipment.port_of_loading }}{% endif %}</td></tr>{% endif %}
"""
	return ('{%- set ctx = document_print_context(doc.name) -%}\n' + EFX_CSS + """
<div class="efx">""" + LH_CTX + """<div class="doc">
  <div class="title">""" + title + """<small>""" + subtitle + """</small></div>

  <table class="grid">
    <tr class="seam">
      <td style="width:58%">
        <span class="lbl">Exporter</span>
        <b>{{ ctx.company_name }}</b>
        <div style="margin-top:3px">{% if ctx.iec_number %}IEC <span class="mono">{{ ctx.iec_number }}</span>{% endif %}{% if ctx.gstin %} &nbsp; GSTIN <span class="mono">{{ ctx.gstin }}</span>{% endif %}</div>
      </td>
      <td>
        <table style="width:100%">
          <tr><td class="lbl" style="border:0;padding:0 0 1px">Invoice no &amp; date</td></tr>
          <tr><td style="border:0;padding:0 0 3px"><b class="mono">{{ doc.document_number or doc.name }}</b>{% if doc.document_date %} &middot; {{ frappe.utils.formatdate(doc.document_date, "dd MMM yyyy") }}{% endif %}</td></tr>
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
      <td style="width:58%;border-right:0.7px solid #b9bec8;vertical-align:top">
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
        {% if ctx.has_bank %}<table style="width:100%;font-size:9.4px;line-height:1.2">
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
<div class="efx">""" + LH_CTX + """<div class="doc">
  <div class="title">""" + title + """<small>""" + subtitle + """</small></div>
  <table class="grid"><tr class="seam">
    <td style="width:58%"><span class="lbl">Exporter</span><b>{{ ctx.company_name }}</b><div style="margin-top:3px">{% if ctx.iec_number %}IEC <span class="mono">{{ ctx.iec_number }}</span>{% endif %}{% if ctx.gstin %} &nbsp; GSTIN <span class="mono">{{ ctx.gstin }}</span>{% endif %}</div></td>
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
    <td style="width:58%"><span class="lbl">To (drawee)</span><b>{{ ctx.lc.issuing_bank if ctx.lc and ctx.lc.issuing_bank else ctx.customer_name }}</b>{% if ctx.lc %}<div class="muted">For account of: {{ ctx.customer_name }}</div>{% endif %}</td>
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


# ---- statutory declarations generated on every shipment ----

NON_HAZARDOUS = _efx_letter(
	"Shipper's Certification of Non-Hazardous Cargo",
	'{% if ctx.shipment.mode == "Air" %}Carriage by air{% else %}Carriage by sea{% endif %}',
	"""  <div class="gd" style="font-size:10.5px;line-height:1.6">
  <table style="width:100%;margin-bottom:8px"><tr>
    <td style="padding:0 12px 0 0;width:33%"><span class="lbl">Port of departure</span>{{ ctx.shipment.port_of_loading or "—" }}</td>
    <td style="padding:0 12px 0 0;width:33%"><span class="lbl">Port of discharge</span>{{ ctx.shipment.port_of_discharge or "—" }}</td>
    <td style="padding:0"><span class="lbl">Destination</span>{{ ctx.shipment.final_destination or ctx.destination_country or "—" }}</td>
  </tr></table>
  <p style="margin:0">We hereby certify that the contents of this consignment are fully and accurately described above by their proper names, and are properly classified, packed, marked and labelled, and in all respects in proper condition for transport. We further certify that the goods are <b>not dangerous goods</b> and are <b>not hazardous</b> for carriage by {% if ctx.shipment.mode == "Air" %}air{% else %}sea{% endif %}. We acknowledge that we may be liable for any loss or damage resulting from a mis-statement or omission, and agree that the carrier may rely upon this certificate.</p>
  </div>""" + EFX_LINES + """  <div class="gd" style="border-top:0.7px solid #b9bec8;font-size:10px">Total net weight: <b>{% if ctx.net_total_wt %}{{ "%g"|format(ctx.net_total_wt) }} Kg{% else %}as per packing list{% endif %}</b>{% if ctx.iec_number %} &nbsp;&middot;&nbsp; IEC <span class="mono">{{ ctx.iec_number }}</span>{% endif %}</div>""",
)


FORM_SDF = _efx_letter(
	"Form SDF", "Declaration under the Foreign Exchange Management Act, 1999",
	"""  <div class="gd" style="font-size:10px;line-height:1.6">
  <table style="width:100%;margin-bottom:8px"><tr>
    <td style="padding:0 12px 0 0;width:50%"><span class="lbl">Shipping bill no &amp; date</span>{% if ctx.shipment.shipping_bill_number %}<span class="mono">{{ ctx.shipment.shipping_bill_number }}</span>{% if ctx.shipment.shipping_bill_date %} &middot; {{ frappe.utils.formatdate(ctx.shipment.shipping_bill_date, "dd MMM yyyy") }}{% endif %}{% else %}—{% endif %}</td>
    <td style="padding:0"><span class="lbl">Invoice no &amp; date</span>{% if ctx.invoice_number %}<span class="mono">{{ ctx.invoice_number }}</span>{% if ctx.invoice_date %} &middot; {{ frappe.utils.formatdate(ctx.invoice_date, "dd MMM yyyy") }}{% endif %}{% else %}—{% endif %}</td>
  </tr></table>
  <p style="margin:0 0 6px"><b>1.</b> I/We hereby declare that I/We am/are the <b>seller / consignor</b> of the goods in respect of which this declaration is made, that the particulars given in the shipping bill stated above are true, and that &mdash; (a) the value as contracted with the buyer is the same as the full export value declared in the above shipping bill; (b) where the full export value is not ascertainable at the time of export, the value declared is that which I/We, having regard to the prevailing market conditions, expect to receive on the sale of the goods in the overseas market.</p>
  <p style="margin:0 0 6px"><b>2.</b> I/We undertake that I/We will deliver to the bank named herein{% if ctx.ad_bank %} &mdash; <b>{{ ctx.ad_bank }}</b>{% endif %} the foreign exchange representing the full export value of the goods on or before the due date, in the manner prescribed in the Foreign Exchange Management (Export of Goods and Services) Regulations.</p>
  <p style="margin:0"><b>3.</b> I/We am/are resident in India and have a place of business in India. &nbsp; <b>4.</b> I/We am/are not in the Caution List of the Reserve Bank of India.</p>
  </div>
  <table class="grid" style="border-top:1.4px solid #16181d"><tr>
    <td style="width:58%"><span class="lbl">Name &amp; address of exporter</span><b>{{ ctx.company_name }}</b>{% if ctx.exporter_address %}<div class="addr muted">{{ ctx.exporter_address | e }}</div>{% endif %}{% if ctx.iec_number %}<div>IEC <span class="mono">{{ ctx.iec_number }}</span></div>{% endif %}</td>
    <td><span class="lbl">FOB value (INR)</span><b>{% if ctx.fob_value_inr %}{{ frappe.utils.fmt_money(ctx.fob_value_inr, currency="INR") }}{% else %}—{% endif %}</b>{% if ctx.ad_bank %}<div style="margin-top:5px"><span class="lbl">Authorised dealer bank</span>{{ ctx.ad_bank }}</div>{% endif %}</td>
  </tr></table>
  <div class="gd" style="border-top:0.7px solid #b9bec8"><span class="lbl">For Authorised Dealer's use</span><div style="height:50px"></div><div class="muted" style="font-size:8.4px">To be completed by the AD bank: uniform code number; date of negotiation / receipt for collection; currency &amp; amount realised; credit to Nostro / debit to NR-Rupee account; period of return reported to the Reserve Bank of India.</div></div>""",
)


DRAWBACK_DECL = _efx_letter(
	"Drawback / DEEC Declaration", "Appendix-III &mdash; to be filed for export goods under claim for drawback",
	"""  <div class="gd" style="font-size:9.6px;line-height:1.55">
  <div style="margin-bottom:6px"><span class="lbl">Shipping bill no &amp; date</span>{% if ctx.shipment.shipping_bill_number %}<span class="mono">{{ ctx.shipment.shipping_bill_number }}</span>{% if ctx.shipment.shipping_bill_date %} &middot; {{ frappe.utils.formatdate(ctx.shipment.shipping_bill_date, "dd MMM yyyy") }}{% endif %}{% else %}—{% endif %}</div>
  <p style="margin:0 0 5px">We, <b>{{ ctx.company_name }}</b>{% if ctx.iec_number %} (IEC <span class="mono">{{ ctx.iec_number }}</span>){% endif %}, hereby declare in respect of the export goods covered by the above shipping bill that &mdash;</p>
  <p style="margin:0 0 4px"><b>(i)</b> the quality and specification of the goods are in accordance with the terms of the export contract entered into with the buyer / consignee; <b>(ii)</b> there is no change in the manufacturing formula or in the quantum per unit of the imported / indigenous materials utilised in the manufacture of the export goods; <b>(iii)</b> the export goods have not been manufactured / exported availing the procedure under rule 18 or sub-rule (2) of rule 19 of the Central Excise Rules, nor in discharge of an export obligation under a duty-exemption / advance authorisation except as separately declared; <b>(iv)</b> the drawback amount claimed is more than 1% of the FOB value of the export, or, where it is less than 1%, it exceeds &#8377; 500.</p>
  <p style="margin:0">We undertake to repatriate the export proceeds within the period prescribed and to submit the Bank Realisation Certificate (eBRC) to the Assistant Commissioner (Drawback); failing realisation within the said period, to refund the drawback received against this shipping bill.</p>
  </div>
  <table class="lines">
    <thead><tr><th style="width:22px">Sr</th><th>Item (as described in the invoice)</th><th style="width:90px">HS code</th><th class="r" style="width:130px">Present market value</th></tr></thead>
    <tbody>{% for row in ctx.lines %}<tr><td class="c mono">{{ loop.index }}</td><td><b>{{ row.item_name }}</b></td><td class="mono">{{ row.hs_code or "—" }}</td><td class="r mono">{% if ctx.currency %}{{ frappe.utils.fmt_money(row.amount, currency=ctx.currency) }}{% else %}—{% endif %}</td></tr>{% endfor %}</tbody>
  </table>""",
)


EXPORT_VALUE_DECL = _efx_letter(
	"Export Value Declaration", "Annexure-A &mdash; Customs Valuation (Determination of Value of Export Goods) Rules, 2007",
	"""  <div class="gd" style="font-size:10px;line-height:1.55">
  <table style="width:100%;margin-bottom:8px"><tr>
    <td style="padding:0 12px 0 0;width:50%"><span class="lbl">Shipping bill no &amp; date</span>{% if ctx.shipment.shipping_bill_number %}<span class="mono">{{ ctx.shipment.shipping_bill_number }}</span>{% if ctx.shipment.shipping_bill_date %} &middot; {{ frappe.utils.formatdate(ctx.shipment.shipping_bill_date, "dd MMM yyyy") }}{% endif %}{% else %}—{% endif %}</td>
    <td style="padding:0"><span class="lbl">Invoice no &amp; date</span>{% if ctx.invoice_number %}<span class="mono">{{ ctx.invoice_number }}</span>{% if ctx.invoice_date %} &middot; {{ frappe.utils.formatdate(ctx.invoice_date, "dd MMM yyyy") }}{% endif %}{% else %}—{% endif %}</td>
  </tr></table>
  <table style="width:100%">
    <tr><td style="padding:3px 8px 3px 0;width:46%;border-bottom:0.5px solid #e3e6ea">1. Nature of transaction</td><td style="padding:3px 0;border-bottom:0.5px solid #e3e6ea"><b>Sale</b></td></tr>
    <tr><td style="padding:3px 8px 3px 0;border-bottom:0.5px solid #e3e6ea">2. Method of valuation</td><td style="padding:3px 0;border-bottom:0.5px solid #e3e6ea"><b>Rule 3</b> &mdash; transaction value</td></tr>
    <tr><td style="padding:3px 8px 3px 0;border-bottom:0.5px solid #e3e6ea">3. Whether seller and buyer are related</td><td style="padding:3px 0;border-bottom:0.5px solid #e3e6ea"><b>No</b></td></tr>
    <tr><td style="padding:3px 8px 3px 0;border-bottom:0.5px solid #e3e6ea">4. Terms of delivery</td><td style="padding:3px 0;border-bottom:0.5px solid #e3e6ea">{% if ctx.incoterm %}{{ ctx.incoterm }}{% if ctx.named_place %} &middot; {{ ctx.named_place }}{% endif %}{% else %}—{% endif %}</td></tr>
    <tr><td style="padding:3px 8px 3px 0;border-bottom:0.5px solid #e3e6ea">5. Terms of payment</td><td style="padding:3px 0;border-bottom:0.5px solid #e3e6ea">{{ ctx.payment_terms or "—" }}</td></tr>
    <tr><td style="padding:3px 8px 3px 0">6. Declared export value</td><td style="padding:3px 0"><b>{% if ctx.currency %}{{ frappe.utils.fmt_money(ctx.grand_total, currency=ctx.currency) }}{% else %}—{% endif %}</b>{% if ctx.fob_value_inr %} <span class="muted">&middot; FOB {{ frappe.utils.fmt_money(ctx.fob_value_inr, currency="INR") }}</span>{% endif %}</td></tr>
  </table>
  <p style="margin:8px 0 0">I/We hereby declare that the information furnished above is true, complete and correct in every respect, and undertake to bring to the notice of the proper officer any particulars subsequently coming to my/our knowledge which would have a bearing on the valuation of the export goods.</p>
  </div>""",
)


def _efx_txn_sign(left=""):
	"""EFX signatory band for the transactional documents (uses `ex` =
	exporter_profile(), which the SO / PO / PFI templates set at the top)."""
	return """
  <table class="grid" style="border-top:1.4px solid #16181d"><tr>
    <td style="width:58%">""" + (left or "&nbsp;") + """</td>
    <td class="sigbox"><div class="muted" style="font-size:9px">For <b>{{ ex.company_name }}</b></div><div class="sigline">{% if ex.signatory_name %}{{ ex.signatory_name }}{% if ex.signatory_designation %} &middot; {{ ex.signatory_designation }}{% endif %} &mdash; {% endif %}Authorised signatory</div></td>
  </tr></table>
"""


# EFX line + totals tables for SO / PO (doc.items with HSN, doc.taxes)
EFX_TXN_LINES = """
  <table class="lines">
    <thead><tr><th style="width:22px">Sr</th><th>Description</th><th style="width:84px">HSN</th><th class="r" style="width:80px">Qty</th><th class="r" style="width:90px">Rate</th><th class="r" style="width:106px">Amount ({{ doc.currency }})</th></tr></thead>
    <tbody>
    {% for row in doc.items %}
      <tr>
        <td class="c mono">{{ loop.index }}</td>
        <td><b>{{ row.item_name }}</b>{% if row.item_code != row.item_name %} <span class="muted mono" style="font-size:8.6px">{{ row.item_code }}</span>{% endif %}</td>
        <td class="mono">{{ row.get("gst_hsn_code") or "—" }}</td>
        <td class="r mono">{{ frappe.utils.flt(row.qty) }} {{ row.uom or "" }}</td>
        <td class="r mono">{{ frappe.utils.fmt_money(row.rate, currency=doc.currency) }}</td>
        <td class="r mono">{{ frappe.utils.fmt_money(row.amount, currency=doc.currency) }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
"""

# Purchase-order variant of the line table — adds per-line specification and
# packaging sub-lines (feedback #13). Forked so the shared EFX_TXN_LINES (used by
# the Sales Order and other transaction prints) is unaffected.
EFX_TXN_LINES_PO = """
  <table class="lines">
    <thead><tr><th style="width:22px">Sr</th><th>Description</th><th style="width:84px">HSN</th><th class="r" style="width:80px">Qty</th><th class="r" style="width:90px">Rate</th><th class="r" style="width:106px">Amount ({{ doc.currency }})</th></tr></thead>
    <tbody>
    {% for row in doc.items %}
      <tr>
        <td class="c mono">{{ loop.index }}</td>
        <td><b>{{ row.item_name }}</b>{% if row.item_code != row.item_name %} <span class="muted mono" style="font-size:8.6px">{{ row.item_code }}</span>{% endif %}{% if row.get("specification") %}<div class="muted" style="font-size:8.6px;white-space:pre-wrap"><b>Spec:</b> {{ row.specification }}</div>{% endif %}{% if row.get("packaging") %}<div class="muted" style="font-size:8.6px;white-space:pre-wrap"><b>Packing:</b> {{ row.packaging }}</div>{% endif %}</td>
        <td class="mono">{{ row.get("gst_hsn_code") or "—" }}</td>
        <td class="r mono">{{ frappe.utils.flt(row.qty) }} {{ row.uom or "" }}</td>
        <td class="r mono">{{ frappe.utils.fmt_money(row.rate, currency=doc.currency) }}</td>
        <td class="r mono">{{ frappe.utils.fmt_money(row.amount, currency=doc.currency) }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
"""

EFX_TXN_TOTALS = """
  <table>
    <tr>
      <td style="width:58%;border-right:0.7px solid #b9bec8;vertical-align:bottom">
        <div class="words"><span class="lbl">Amount in words</span>{{ frappe.utils.money_in_words(doc.grand_total, doc.currency) }}</div>
      </td>
      <td>
        <table class="tot">
          <tr><td>Net total</td><td class="r mono">{{ frappe.utils.fmt_money(doc.net_total, currency=doc.currency) }}</td></tr>
          {% for tax in doc.taxes %}<tr><td>{{ tax.description }}{% if tax.rate %} @ {{ frappe.utils.flt(tax.rate) }}%{% endif %}</td><td class="r mono">{{ frappe.utils.fmt_money(tax.base_tax_amount_after_discount_amount or tax.tax_amount, currency=doc.currency) }}</td></tr>{% endfor %}
          <tr class="g"><td>Grand total</td><td class="r mono">{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}</td></tr>
        </table>
      </td>
    </tr>
  </table>
"""

_TERMS = """
  {% if doc.get("payment_terms_narrative") %}<div class="gd" style="border-top:0.7px solid #b9bec8;white-space:pre-wrap;font-size:9.6px"><span class="lbl">Payment terms</span>{{ doc.payment_terms_narrative | e }}</div>{% endif %}
  {% if doc.terms %}<div class="gd" style="border-top:0.7px solid #b9bec8;white-space:pre-wrap;font-size:9.6px"><span class="lbl">Terms &amp; conditions{% if doc.tc_name %} &middot; {{ doc.tc_name }}{% endif %}</span>{{ doc.terms | striptags }}</div>{% endif %}
"""

_SYS_GEN = '<span class="muted" style="font-size:8.6px">System generated by ExportFlow.</span>'


SALES_ORDER = (
	'{%- set ex = exporter_profile() -%}\n'
	'{%- set cust_addr = party_address("Customer", doc.customer) -%}\n'
	'{%- set dest = frappe.db.get_value("Customer", doc.customer, "destination_country") -%}\n'
	+ EFX_CSS + """
<div class="efx">""" + LH_EX + """<div class="doc">
  <div class="title">Sales Order<small>Export order confirmation{% if doc.docstatus == 0 %} &middot; DRAFT{% endif %}</small></div>
  <table class="grid">
    <tr class="seam">
      <td style="width:58%"><span class="lbl">Exporter / Seller</span><b>{{ ex.company_name }}</b><div style="margin-top:3px">{% if ex.iec %}IEC <span class="mono">{{ ex.iec }}</span>{% endif %}{% if ex.gstin %} &nbsp; GSTIN <span class="mono">{{ ex.gstin }}</span>{% endif %}</div></td>
      <td>
        <table style="width:100%">
          <tr><td class="lbl" style="border:0;padding:0 0 1px">Order no &amp; date</td></tr>
          <tr><td style="border:0;padding:0 0 3px"><b class="mono">{{ doc.name }}</b> &middot; {{ frappe.utils.formatdate(doc.transaction_date, "dd MMM yyyy") }}</td></tr>
          {% if doc.delivery_date %}<tr><td class="lbl" style="border:0;padding:0 0 1px">Delivery by</td></tr><tr><td style="border:0;padding:0">{{ frappe.utils.formatdate(doc.delivery_date, "dd MMM yyyy") }}</td></tr>{% endif %}
        </table>
      </td>
    </tr>
    <tr class="seam">
      <td><span class="lbl">Customer / Buyer</span><b>{{ doc.customer_name or doc.customer }}</b>{% if cust_addr %}<div class="addr muted">{{ cust_addr|e }}</div>{% endif %}{% if dest %}<div class="muted">Country of final destination: {{ dest }}</div>{% endif %}</td>
      <td>
        <table style="width:100%">
          <tr><td class="lbl" style="border:0;padding:0 0 1px">Currency / incoterm</td></tr>
          <tr><td style="border:0;padding:0 0 3px"><span class="mono">{{ doc.currency }}</span>{% if doc.incoterm %} &middot; {{ doc.incoterm }}{% if doc.named_place %} ({{ doc.named_place }}){% endif %}{% endif %}</td></tr>
          {% if doc.po_no %}<tr><td class="lbl" style="border:0;padding:0 0 1px">Buyer's ref</td></tr><tr><td style="border:0;padding:0 0 3px"><span class="mono">{{ doc.po_no }}</span></td></tr>{% endif %}
        </table>
      </td>
    </tr>
  </table>
""" + EFX_TXN_LINES + EFX_TXN_TOTALS + _TERMS + _efx_txn_sign(_SYS_GEN) + """
</div></div>
"""
)


PURCHASE_ORDER = (
	'{%- set ex = exporter_profile() -%}\n'
	'{%- set sup_addr = party_address("Supplier", doc.supplier) -%}\n'
	'{%- set sos = doc.items | map(attribute="sales_order") | select | unique | list -%}\n'
	+ EFX_CSS + """
<div class="efx">""" + LH_EX + """<div class="doc">
  <div class="title">Purchase Order<small>{% if doc.merchant_export_scheme %}Merchant export &mdash; concessional 0.1% GST (Notification 41/2017-IGST(R)){% else %}Procurement order{% endif %}{% if doc.docstatus == 0 %} &middot; DRAFT{% endif %}</small></div>
  <table class="grid">
    <tr class="seam">
      <td style="width:58%"><span class="lbl">Buyer</span><b>{{ ex.company_name }}</b><div style="margin-top:3px">{% if ex.gstin %}GSTIN <span class="mono">{{ ex.gstin }}</span>{% endif %}{% if ex.iec %} &nbsp; IEC <span class="mono">{{ ex.iec }}</span>{% endif %}</div></td>
      <td>
        <table style="width:100%">
          <tr><td class="lbl" style="border:0;padding:0 0 1px">PO no &amp; date</td></tr>
          <tr><td style="border:0;padding:0 0 3px"><b class="mono">{{ doc.name }}</b> &middot; {{ frappe.utils.formatdate(doc.transaction_date, "dd MMM yyyy") }}</td></tr>
          {% if doc.schedule_date %}<tr><td class="lbl" style="border:0;padding:0 0 1px">Required by</td></tr><tr><td style="border:0;padding:0">{{ frappe.utils.formatdate(doc.schedule_date, "dd MMM yyyy") }}</td></tr>{% endif %}
        </table>
      </td>
    </tr>
    <tr class="seam">
      <td><span class="lbl">Supplier</span><b>{{ doc.supplier_name }}</b>{% if sup_addr %}<div class="addr muted">{{ sup_addr|e }}</div>{% endif %}{% if doc.get("supplier_gstin") %}<div>GSTIN <span class="mono">{{ doc.supplier_gstin }}</span></div>{% endif %}</td>
      <td><span class="lbl">Delivery</span>{% if sos %}Drop-ship &mdash; deliver direct to the port of shipment.{% else %}As advised.{% endif %}</td>
    </tr>
  </table>
""" + EFX_TXN_LINES_PO + EFX_TXN_TOTALS + _TERMS + _efx_txn_sign(_SYS_GEN) + """
</div></div>
"""
)


PRO_FORMA = (
	'{%- set ex = exporter_profile() -%}\n'
	'{%- set so = frappe.get_doc("Sales Order", doc.sales_order) -%}\n'
	'{%- set bank = frappe.get_doc("Bank Account", doc.bank_account) if doc.bank_account else None -%}\n'
	'{%- set rows = doc.items if doc.items else so.get("items") -%}\n'
	'{%- set cust_addr = party_address("Customer", doc.customer) -%}\n'
	+ EFX_CSS + """
<div class="efx">""" + LH_EX + """<div class="doc">
  <div class="title">Pro Forma Invoice<small>Not a tax invoice &mdash; issued for advance payment / LC establishment</small></div>
  <table class="grid">
    <tr class="seam">
      <td style="width:58%"><span class="lbl">Exporter</span><b>{{ ex.company_name }}</b><div style="margin-top:3px">{% if ex.iec %}IEC <span class="mono">{{ ex.iec }}</span>{% endif %}{% if ex.gstin %} &nbsp; GSTIN <span class="mono">{{ ex.gstin }}</span>{% endif %}</div></td>
      <td>
        <table style="width:100%">
          <tr><td class="lbl" style="border:0;padding:0 0 1px">PFI no &amp; date</td></tr>
          <tr><td style="border:0;padding:0 0 3px"><b class="mono">{{ doc.name }}</b> &middot; {{ frappe.utils.formatdate(doc.pfi_date, "dd MMM yyyy") }}</td></tr>
          {% if doc.stage_description %}<tr><td style="border:0;padding:0" class="muted">{{ doc.stage_description }}</td></tr>{% endif %}
        </table>
      </td>
    </tr>
    <tr class="seam">
      <td><span class="lbl">Buyer</span><b>{{ doc.customer_name or doc.customer }}</b>{% if cust_addr %}<div class="addr muted">{{ cust_addr|e }}</div>{% endif %}</td>
      <td>
        <table style="width:100%">
          <tr><td class="lbl" style="border:0;padding:0 0 1px">Sales order</td></tr>
          <tr><td style="border:0;padding:0 0 3px"><span class="mono">{{ doc.sales_order }}</span></td></tr>
          {% if so.incoterm %}<tr><td class="lbl" style="border:0;padding:0 0 1px">Incoterm</td></tr><tr><td style="border:0;padding:0 0 3px">{{ so.incoterm }}{% if so.named_place %} &middot; {{ so.named_place }}{% endif %}</td></tr>{% endif %}
          {% if doc.expected_payment_method %}<tr><td class="lbl" style="border:0;padding:0 0 1px">Payment by</td></tr><tr><td style="border:0;padding:0">{{ doc.expected_payment_method }}</td></tr>{% endif %}
        </table>
      </td>
    </tr>
  </table>
  {% if doc.basis == "Percentage of SO" %}<div class="gd muted" style="border-bottom:0.7px solid #b9bec8">Stage value: {{ doc.get_formatted("percentage") }}% of sales order value {{ frappe.utils.fmt_money(so.grand_total, currency=doc.currency) }}</div>{% endif %}
  <table class="lines">
    <thead><tr><th style="width:22px">Sr</th><th>Description</th><th class="r" style="width:80px">Qty</th><th class="r" style="width:90px">Rate</th><th class="r" style="width:106px">Amount ({{ doc.currency }})</th></tr></thead>
    <tbody>
    {% if rows %}{% for row in rows %}<tr><td class="c mono">{{ loop.index }}</td><td><b>{{ row.item_name or row.item_code }}</b></td><td class="r mono">{{ frappe.utils.flt(row.qty) }} {{ row.uom or "" }}</td><td class="r mono">{{ frappe.utils.fmt_money(row.rate, currency=doc.currency) }}</td><td class="r mono">{{ frappe.utils.fmt_money(row.amount, currency=doc.currency) }}</td></tr>{% endfor %}{% else %}<tr><td class="c mono">1</td><td>As per sales order <span class="mono">{{ doc.sales_order }}</span></td><td class="r">&mdash;</td><td class="r">&mdash;</td><td class="r mono">{{ frappe.utils.fmt_money(doc.amount, currency=doc.currency) }}</td></tr>{% endif %}
    </tbody>
  </table>
  <table>
    <tr>
      <td style="width:58%;border-right:0.7px solid #b9bec8;vertical-align:bottom"><div class="words"><span class="lbl">Amount in words</span>{{ frappe.utils.money_in_words(doc.amount, doc.currency) }}</div></td>
      <td><table class="tot"><tr class="g"><td>Amount payable</td><td class="r mono">{{ frappe.utils.fmt_money(doc.amount, currency=doc.currency) }}</td></tr></table></td>
    </tr>
  </table>
""" + _efx_txn_sign('{% if bank %}<span class="lbl">Remit to</span><b>{{ bank.account_name }}</b>{% if bank.bank %} &middot; {{ bank.bank }}{% endif %}{% if bank.bank_account_no %}<div>A/c <span class="mono">{{ bank.bank_account_no }}</span></div>{% endif %}{% if bank.iban %}<div>IBAN <span class="mono">{{ bank.iban }}</span></div>{% endif %}{% if bank.get("branch_code") %}<div>SWIFT/IFSC <span class="mono">{{ bank.branch_code }}</span></div>{% endif %}{% endif %}{% if doc.terms %}<div class="muted" style="white-space:pre-wrap;margin-top:6px">{{ doc.terms | e }}</div>{% endif %}') + """
</div></div>
"""
)


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
		"margin_bottom": 9.0,
		"margin_left": 15.0,
		"margin_right": 15.0,
		"margin_top": 7.0,
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
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w") as f:
		json.dump(payload, f, indent=1, sort_keys=True, ensure_ascii=False)
		f.write("\n")
	print("wrote", path)


if __name__ == "__main__":
	# every format shares the bordered EFX style + the letterhead banner — one stamp;
	# bump it on any edit so migrate re-syncs the standard print formats
	REDESIGN = "2026-06-17 22:00:00.000000"
	# the PO format alone changed (per-line spec/packaging, feedback #13) — give it
	# its own newer stamp so only it re-syncs, not all 13 formats
	PO_REDESIGN = "2026-06-21 12:00:00.000000"
	# SO + PO grew a dedicated "Payment terms" line (separate from T&C) — bump both
	# so only those two re-sync
	PAYMENT_TERMS_REDESIGN = "2026-06-22 09:00:00.000000"
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
	write_format("exportflow_non_hazardous_cargo", "ExportFlow Non-Hazardous Cargo", NON_HAZARDOUS, modified=REDESIGN)
	write_format("exportflow_form_sdf", "ExportFlow Form SDF", FORM_SDF, modified=REDESIGN)
	write_format("exportflow_drawback_declaration", "ExportFlow Drawback Declaration", DRAWBACK_DECL, modified=REDESIGN)
	write_format("exportflow_export_value_declaration", "ExportFlow Export Value Declaration", EXPORT_VALUE_DECL, modified=REDESIGN)
	write_format(
		"exportflow_sales_order", "ExportFlow Sales Order", SALES_ORDER,
		doc_type="Sales Order", modified=PAYMENT_TERMS_REDESIGN,
	)
	write_format(
		"exportflow_purchase_order", "ExportFlow Purchase Order", PURCHASE_ORDER,
		doc_type="Purchase Order", modified=PAYMENT_TERMS_REDESIGN,
	)
	write_format(
		"pro_forma_invoice", "Pro Forma Invoice", PRO_FORMA,
		doc_type="Pro Forma Invoice", modified=REDESIGN,
	)
