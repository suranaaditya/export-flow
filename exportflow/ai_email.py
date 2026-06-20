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
from frappe.utils import escape_html, flt, fmt_money, format_date, split_emails, validate_email_address


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
		out = json.loads(resp.json().get("response") or "{}")
	except (json.JSONDecodeError, ValueError):
		return {}
	return out if isinstance(out, dict) else {}  # a JSON list/scalar is not a usable draft


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


def _exporter_bank() -> dict | None:
	"""The exporter's receiving-bank details from ExportFlow Settings — so a proforma
	email can tell the customer where to wire the advance."""
	s = frappe.get_single("ExportFlow Settings")
	bank = {
		"bank_name": s.get("bank_name"),
		"account_no": s.get("bank_account_no"),
		"branch": s.get("bank_branch_address"),
		"ifsc": s.get("bank_ifsc"),
		"swift": s.get("bank_swift"),
		"correspondent": s.get("bank_correspondent"),
	}
	bank = {k: v for k, v in bank.items() if v}
	return bank or None


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
		"payment_method": doc.get("expected_payment_method") or "Advance payment / Letter of Credit",
		"remit_payment_to": _exporter_bank(),
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


def _build_prompt(cfg: dict, facts: dict, tone: str, instruction: str | None = None) -> str:
	from exportflow.printing import exporter_profile

	ex = exporter_profile()
	sender = ex.company_name or "the exporter"
	signatory = ex.signatory_name or ""
	recipient = facts.get("supplier") or facts.get("customer") or "the recipient"
	extra = (instruction or "").strip()
	return (
		"You are drafting a professional B2B email on behalf of an Indian merchant exporter.\n"
		f"You represent the sender: {sender}.\n"
		f"The recipient is: {recipient}.\n"
		f"Goal: {cfg['intent']}.\n"
		f"Tone: {tone}.\n\n"
		"RULES:\n"
		"- Use ONLY the facts in the JSON below. Do NOT invent any number, date, name, price or term.\n"
		"- State that the document is attached as a PDF.\n"
		"- If the facts include payment / bank details (payment_method, remit_payment_to), include them so "
		"the recipient knows how and where to pay.\n"
		"- Keep the body focused (under 180 words), with a greeting and a sign-off"
		+ (f" from {signatory}, {sender}" if signatory else f" from {sender}")
		+ ".\n"
		"- Do NOT put the subject line inside the body.\n\n"
		f"FACTS:\n{json.dumps(facts, ensure_ascii=False, indent=1)}\n\n"
		"--- What the user specifically wants this email to mention (weave it in naturally, but stay grounded "
		"in the facts above) ---\n"
		f"{extra or '(no extra instruction — write a fitting email for the goal above)'}\n\n"
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
def email_draft(doctype: str, name: str, purpose: str, instruction: str = None,
				tone: str = "professional and courteous") -> dict:
	"""Ask Gemma to draft {subject, body} from the document's facts plus the user's
	free-text instruction (what they want the email to say)."""
	cfg = _cfg(purpose, doctype)
	frappe.has_permission(doctype, "read", doc=name, throw=True)
	doc = frappe.get_doc(doctype, name)
	prompt = _build_prompt(cfg, cfg["facts"](doc), tone, instruction)
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
	# emailing a confidential document OUT requires more than view access — a pure
	# viewer must not be able to mail the PDF to an arbitrary address
	if not any(frappe.has_permission(doctype, p, doc=name) for p in ("email", "submit", "write")):
		frappe.throw(_("You do not have permission to email this document."), frappe.PermissionError)
	# validate every recipient address (to + each cc); split_emails handles a comma list
	to = (to or "").strip()
	validate_email_address(to, throw=True)
	cc_list = [e.strip() for e in split_emails(cc or "") if e.strip()]
	for addr in cc_list:
		validate_email_address(addr, throw=True)
	if not (subject or "").strip() or not (body or "").strip():
		frappe.throw(_("Subject and body are required."))

	attachments = []
	if int(attach_pdf):
		pdf = frappe.get_print(doctype, name, print_format=cfg["print_format"], as_pdf=True, no_letterhead=1)
		attachments.append({"fname": f"{cfg['attach_label']}-{name}.pdf".replace(" ", "-"), "fcontent": pdf})

	sandbox = frappe.conf.get("exportflow_email_sandbox")
	recipients = [sandbox] if sandbox else [to]
	cc_final = [] if sandbox else cc_list
	subj = f"[SANDBOX → {to}] {subject}" if sandbox else subject
	content = (
		'<div style="white-space:pre-wrap;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1b2230">'
		+ escape_html(body)
		+ "</div>"
	)

	acc = _smtp_account()
	if acc:
		# self-contained smtplib send from the connected account — never touches the
		# shared site's default Email Account; log the Communication only on success
		_smtp_send(acc, recipients, cc_final, subj, content, attachments)
		comm = _log_communication(doctype, name, subj, content, recipients, cc_final)
	else:
		comm = _log_communication(doctype, name, subj, content, recipients, cc_final)
		frappe.sendmail(
			recipients=recipients, cc=cc_final or None, subject=subj, content=content,
			attachments=attachments, communication=comm.name,
			reference_doctype=doctype, reference_name=name,
		)
	return {"sent_to": recipients, "sandbox": bool(sandbox), "intended": to,
			"communication": comm.name, "via": "smtp" if acc else "site"}


def _log_communication(doctype, name, subject, content, recipients, cc):
	"""A Sent Communication linked to the document so the email shows in its timeline."""
	return frappe.get_doc({
		"doctype": "Communication",
		"communication_type": "Communication",
		"communication_medium": "Email",
		"sent_or_received": "Sent",
		"subject": subject,
		"content": content,
		"recipients": ", ".join(recipients),
		"cc": ", ".join(cc) or None,
		"reference_doctype": doctype,
		"reference_name": name,
		"status": "Linked",
	}).insert(ignore_permissions=True)


# ---------------------------------------------------- connected sending account

def _smtp_account():
	"""The connected ExportFlow sending account (Settings) if both an address and an
	app password are set — else None (fall back to the site's default email)."""
	s = frappe.get_single("ExportFlow Settings")
	if s.get("smtp_email") and s.get_password("smtp_password", raise_exception=False):
		return s
	return None


def _smtp_send(acc, recipients, cc, subject, html, attachments):
	"""Send via the connected account's own SMTP (self-contained; does not use Frappe's
	site-wide Email Account)."""
	import re
	import smtplib
	import ssl as _ssl
	from email.message import EmailMessage
	from email.utils import formataddr

	pw = acc.get_password("smtp_password")
	host = acc.smtp_host or "smtp.gmail.com"
	use_ssl = int(acc.get("smtp_use_ssl") or 0)
	port = int(acc.smtp_port or (465 if use_ssl else 587))

	msg = EmailMessage()
	msg["Subject"] = subject
	msg["From"] = formataddr((acc.get("smtp_sender_name") or acc.smtp_email, acc.smtp_email))
	msg["To"] = ", ".join(recipients)
	if cc:
		msg["Cc"] = ", ".join(cc)
	msg.set_content(re.sub(r"<[^>]+>", "", html))  # plain-text fallback
	msg.add_alternative(html, subtype="html")
	for a in attachments or []:
		msg.add_attachment(a["fcontent"], maintype="application", subtype="pdf", filename=a["fname"])

	ctx = _ssl.create_default_context()
	server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) if use_ssl else smtplib.SMTP(host, port, timeout=30)
	try:
		if not use_ssl:
			server.starttls(context=ctx)
		server.login(acc.smtp_email, pw)
		server.send_message(msg, to_addrs=recipients + list(cc or []))
	finally:
		try:
			server.quit()
		except Exception:
			pass


@frappe.whitelist()
def get_email_account() -> dict:
	"""The connected sending account (never returns the password)."""
	frappe.has_permission("ExportFlow Settings", "read", throw=True)
	s = frappe.get_single("ExportFlow Settings")
	return {
		"email": s.get("smtp_email"),
		"sender_name": s.get("smtp_sender_name"),
		"host": s.get("smtp_host") or "smtp.gmail.com",
		"port": s.get("smtp_port") or 465,
		"use_ssl": bool(int(s.get("smtp_use_ssl") or 0)),
		"has_password": bool(s.get_password("smtp_password", raise_exception=False)),
		"configured": bool(_smtp_account()),
	}


@frappe.whitelist()
def save_email_account(email, sender_name=None, host=None, port=None, use_ssl=1, password=None) -> dict:
	"""Save the connected sending account. The app password is stored encrypted; it is
	only overwritten when a new one is supplied."""
	frappe.has_permission("ExportFlow Settings", "write", throw=True)
	email = (email or "").strip()
	if email:
		validate_email_address(email, throw=True)
	s = frappe.get_single("ExportFlow Settings")
	s.smtp_email = email
	s.smtp_sender_name = (sender_name or "").strip() or None
	s.smtp_host = (host or "").strip() or "smtp.gmail.com"
	s.smtp_port = int(port or 465)
	s.smtp_use_ssl = 1 if str(use_ssl) in ("1", "true", "True") else 0
	if password:
		s.smtp_password = password
	s.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "configured": bool(_smtp_account())}


@frappe.whitelist()
def test_email_account() -> dict:
	"""Verify the connected account's SMTP login (connect + auth, no message sent)."""
	frappe.has_permission("ExportFlow Settings", "write", throw=True)
	acc = _smtp_account()
	if not acc:
		frappe.throw(_("Enter the email address and app password, Save, then test."))
	import smtplib
	import ssl as _ssl

	host = acc.smtp_host or "smtp.gmail.com"
	use_ssl = int(acc.get("smtp_use_ssl") or 0)
	port = int(acc.smtp_port or (465 if use_ssl else 587))
	try:
		ctx = _ssl.create_default_context()
		server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) if use_ssl else smtplib.SMTP(host, port, timeout=20)
		if not use_ssl:
			server.starttls(context=ctx)
		server.login(acc.smtp_email, acc.get_password("smtp_password"))
		server.quit()
	except Exception as e:
		frappe.throw(_("Could not connect: {0}").format(str(e)[:160]))
	return {"ok": True, "email": acc.smtp_email}
