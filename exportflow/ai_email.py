"""AI-assisted outbound email — a purpose-driven composer.

For a given document it resolves the recipient, attaches the right PDF, drafts the
subject + body with the self-hosted Gemma model (Ollama; facts are INJECTED, never
invented), and sends + logs it as a linked Communication. Phase 1 purposes:
PO -> supplier, PFI -> customer.

Safety:
- The model only PHRASES from a facts dict; it is told to use no other information.
- Attachments are re-derived server-side from the purpose config (the client cannot
  ask us to print an arbitrary doctype/print format).
- Dev sends are redirected to a sandbox address (site_config `exportflow_email_sandbox`)
  so development never reaches a real supplier/customer; the real recipient is shown in
  the subject prefix.
"""

import json

import requests

import frappe
from frappe import _
from frappe.contacts.doctype.contact.contact import get_default_contact
from frappe.utils import escape_html, flt, fmt_money, format_date


def _ollama_url() -> str:
	return frappe.conf.get("ollama_url") or "http://127.0.0.1:11434/api/generate"


def _ollama_json(prompt: str, num_predict: int = 500) -> dict:
	"""Call the self-hosted Gemma via Ollama and return its parsed JSON object."""
	payload = {
		"model": frappe.conf.get("exportflow_email_model") or "gemma4:e4b",
		"prompt": prompt,
		"stream": False,
		"think": False,
		"format": "json",
		"keep_alive": "5m",
		"options": {"num_predict": num_predict, "temperature": 0.3},
	}
	resp = requests.post(_ollama_url(), json=payload, timeout=60)
	resp.raise_for_status()
	try:
		return json.loads(resp.json().get("response") or "{}")
	except (json.JSONDecodeError, ValueError):
		return {}


# --------------------------------------------------------------- recipient

def _party_email(party_type: str, party: str | None) -> str | None:
	"""Best email for a Customer / Supplier — the default contact, else any linked
	contact that has an email."""
	if not party:
		return None
	contact = get_default_contact(party_type, party)
	if contact:
		email = frappe.db.get_value("Contact", contact, "email_id")
		if email:
			return email
	links = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": party_type, "link_name": party, "parenttype": "Contact"},
		pluck="parent",
	)
	if links:
		return frappe.db.get_value("Contact", {"name": ["in", links], "email_id": ["is", "set"]}, "email_id")
	return None


# --------------------------------------------------------------- fact builders

def _line_items(doc) -> list[dict]:
	return [
		{
			"item": it.item_name or it.item_code,
			"qty": flt(it.qty),
			"uom": it.uom,
			"rate": flt(it.rate),
			"amount": flt(it.amount),
		}
		for it in doc.items
	][:12]


def _po_facts(doc) -> dict:
	return {
		"document": "Purchase Order",
		"po_number": doc.name,
		"date": format_date(doc.transaction_date),
		"supplier": doc.supplier_name or doc.supplier,
		"currency": doc.currency,
		"order_total": fmt_money(doc.grand_total, currency=doc.currency),
		"line_count": len(doc.items),
		"items": _line_items(doc),
		"incoterm": doc.get("incoterm") or None,
		"delivery": "drop-shipped directly to the port of shipment",
	}


def _pfi_facts(doc) -> dict:
	return {
		"document": "Proforma Invoice",
		"pfi_number": doc.name,
		"date": format_date(doc.pfi_date),
		"customer": doc.customer_name or doc.customer,
		"currency": doc.currency,
		"invoice_total": fmt_money(doc.amount, currency=doc.currency),
		"line_count": len(doc.items),
		"items": _line_items(doc),
		"payment_method": doc.get("expected_payment_method") or None,
	}


PURPOSES = {
	"po_to_supplier": {
		"doctype": "Purchase Order",
		"party_type": "Supplier",
		"party_field": "supplier",
		"name_field": "supplier_name",
		"print_format": "ExportFlow Purchase Order",
		"attach_label": "Purchase Order",
		"facts": _po_facts,
		"intent": "enclose a purchase order and ask the supplier to acknowledge it and confirm dispatch as per the order terms",
	},
	"pfi_to_customer": {
		"doctype": "Pro Forma Invoice",
		"party_type": "Customer",
		"party_field": "customer",
		"name_field": "customer_name",
		"print_format": "Pro Forma Invoice",
		"attach_label": "Proforma Invoice",
		"facts": _pfi_facts,
		"intent": "enclose a proforma invoice and ask the customer to confirm the order and arrange the advance payment or letter of credit as applicable",
	},
}


def _cfg(purpose: str, doctype: str) -> dict:
	cfg = PURPOSES.get(purpose)
	if not cfg or cfg["doctype"] != doctype:
		frappe.throw(_("Unknown email purpose {0}").format(purpose))
	return cfg


def _build_prompt(cfg: dict, facts: dict, tone: str) -> str:
	from exportflow.printing import exporter_profile

	ex = exporter_profile()
	sender = ex.company_name or "the exporter"
	signatory = ex.signatory_name or ""
	recipient = facts.get("supplier") or facts.get("customer") or "the recipient"
	return (
		"You are drafting a short, professional B2B email on behalf of an Indian merchant exporter.\n"
		f"You represent the sender: {sender}.\n"
		f"The recipient is: {recipient}.\n"
		f"Goal: {cfg['intent']}.\n"
		f"Tone: {tone}.\n\n"
		"RULES:\n"
		"- Use ONLY the facts in the JSON below. Do NOT invent any number, date, name, price or term.\n"
		"- State that the document is attached as a PDF.\n"
		"- Keep the body under 130 words, with a greeting and a sign-off"
		+ (f" from {signatory}, {sender}" if signatory else f" from {sender}")
		+ ".\n"
		"- Do NOT put the subject line inside the body.\n\n"
		f"FACTS:\n{json.dumps(facts, ensure_ascii=False, indent=1)}\n\n"
		'Return ONLY valid JSON of the form {"subject": "...", "body": "..."} '
		"with real newline characters in the body."
	)


# --------------------------------------------------------------- endpoints

@frappe.whitelist()
def email_context(doctype: str, name: str, purpose: str) -> dict:
	"""Recipient + default attachment + the facts the draft will use. Fast/deterministic."""
	cfg = _cfg(purpose, doctype)
	frappe.has_permission(doctype, "read", doc=name, throw=True)
	doc = frappe.get_doc(doctype, name)
	party = doc.get(cfg["party_field"])
	return {
		"purpose": purpose,
		"to": _party_email(cfg["party_type"], party),
		"to_name": doc.get(cfg["name_field"]) or party,
		"party_type": cfg["party_type"],
		"attachment_label": f"{cfg['attach_label']} — {name}.pdf",
		"facts": cfg["facts"](doc),
		"sandbox": frappe.conf.get("exportflow_email_sandbox"),
	}


@frappe.whitelist()
def email_draft(doctype: str, name: str, purpose: str, tone: str = "professional and courteous") -> dict:
	"""Ask Gemma to draft {subject, body} from the document's facts."""
	cfg = _cfg(purpose, doctype)
	frappe.has_permission(doctype, "read", doc=name, throw=True)
	doc = frappe.get_doc(doctype, name)
	prompt = _build_prompt(cfg, cfg["facts"](doc), tone)
	try:
		out = _ollama_json(prompt)
	except requests.RequestException as e:
		frappe.log_error(f"email draft LLM unreachable: {e}", "exportflow.ai_email")
		frappe.throw(_("The AI drafting service is unreachable right now — you can still write the email manually."))
	subject = (out.get("subject") or "").strip()
	body = (out.get("body") or "").strip()
	if not subject or not body:
		frappe.throw(_("The AI returned an empty draft. Please try again or write it manually."))
	return {"subject": subject, "body": body}


@frappe.whitelist()
def email_send(doctype: str, name: str, purpose: str, to: str, subject: str, body: str,
			   cc: str | None = None, attach_pdf: int = 1) -> dict:
	"""Send the email (attachment re-derived server-side) and log it as a linked
	Communication. In dev, redirect to the sandbox address."""
	cfg = _cfg(purpose, doctype)
	frappe.has_permission(doctype, "read", doc=name, throw=True)
	if not to or "@" not in to:
		frappe.throw(_("A valid recipient email is required."))
	if not (subject or "").strip() or not (body or "").strip():
		frappe.throw(_("Subject and body are required."))

	attachments = []
	if int(attach_pdf):
		pdf = frappe.get_print(doctype, name, print_format=cfg["print_format"], as_pdf=True, no_letterhead=1)
		attachments.append({"fname": f"{cfg['attach_label']}-{name}.pdf".replace(" ", "-"), "fcontent": pdf})

	sandbox = frappe.conf.get("exportflow_email_sandbox")
	recipients = [sandbox] if sandbox else [to]
	cc_list = [] if sandbox else ([cc] if cc else [])
	subj = f"[SANDBOX → {to}] {subject}" if sandbox else subject
	content = (
		'<div style="white-space:pre-wrap;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1b2230">'
		+ escape_html(body)
		+ "</div>"
	)

	# explicit Communication so the email shows in the document's timeline (sendmail's
	# reference_* links the queue but does not create a Communication on its own)
	comm = frappe.get_doc({
		"doctype": "Communication",
		"communication_type": "Communication",
		"communication_medium": "Email",
		"sent_or_received": "Sent",
		"subject": subj,
		"content": content,
		"recipients": ", ".join(recipients),
		"cc": ", ".join(cc_list) or None,
		"reference_doctype": doctype,
		"reference_name": name,
		"status": "Linked",
	}).insert(ignore_permissions=True)

	frappe.sendmail(
		recipients=recipients,
		cc=cc_list or None,
		subject=subj,
		content=content,
		attachments=attachments,
		communication=comm.name,
		reference_doctype=doctype,
		reference_name=name,
	)
	return {"sent_to": recipients, "sandbox": bool(sandbox), "intended": to, "communication": comm.name}
