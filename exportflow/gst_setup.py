"""One-off, idempotent GST onboarding for MN Globex on erp.jewonline.in.

Scoped STRICTLY to MN Globex's own data (its transacted items + its suppliers)
— Item/Supplier are global masters on this shared bench, so we never wipe other
companies' tax rows or touch their vendors.

What it does:
  1. Registers MN Globex's GST (real GSTIN 23AABCM1736F1ZY, Madhya Pradesh) via
     the company gstin field + a company GST address.
  2. Creates MN Globex's GST accounts + GST Item Tax Templates (GST 5/12/18% etc)
     via india_compliance's create_company_fixtures.
  3. For each MN Globex transacted item: sets gst_hsn_code (HS code cleaned to a
     valid GST HSN) and assigns the right "GST x% - MNG" template (rate by HSN
     chapter), preserving any other company's tax rows on shared items.
  4. Registers NANDU + creates 10 demo Indian pharma suppliers with VALID demo
     GSTINs (mix of MP intra-state and other states) so PO GST autofills.

Demo GSTINs are format/checksum valid but NOT real registrations — replace with
the real numbers before any statutory use.

Run:  bench --site erp.jewonline.in execute \
        "frappe.get_attr('exportflow.gst_setup.run')(dry_run=True)"
"""

import frappe
from frappe.utils import nowdate

COMPANY = "MN Globex"
COMPANY_GSTIN = "23AABCM1736F1ZY"  # web-researched, real (MP, state code 23)
COMPANY_STATE = "Madhya Pradesh"

# HSN 2-digit chapter -> GST %, else DEFAULT (organic/inorganic chemicals,
# extracts, vitamins, dyes, enzymes, resins, machinery = 18%)
RATE_BY_CHAPTER = {"04": 5, "30": 12}
DEFAULT_RATE = 18

GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _gstin_checksum(first14: str) -> str:
	factor, total = 2, 0
	for ch in reversed(first14):
		d = factor * GSTIN_CHARS.index(ch)
		total += d // 36 + d % 36
		factor = 1 if factor == 2 else 2
	return GSTIN_CHARS[(36 - total % 36) % 36]


def make_gstin(state_code: str, pan: str) -> str:
	f14 = f"{state_code}{pan}1Z"
	return f14 + _gstin_checksum(f14)


# self-test: the algorithm must reproduce MN Globex's real check digit ("Y")
assert make_gstin("23", "AABCM1736F") == COMPANY_GSTIN, make_gstin("23", "AABCM1736F")


# 10 demo Indian pharma/chemical suppliers (generic names, not impersonating real
# firms); state code drives intra (23=MP -> CGST+SGST) vs inter (-> IGST)
DEMO_SUPPLIERS = [
	("Indore Pharma Chem Pvt Ltd", "Indore", "Madhya Pradesh", "23", "AABCI1001A"),
	("Malwa Nutraceuticals", "Indore", "Madhya Pradesh", "23", "AABCM2002B"),
	("Narmada Active Ingredients", "Bhopal", "Madhya Pradesh", "23", "AABCN3003C"),
	("Western Bulk Drugs Pvt Ltd", "Mumbai", "Maharashtra", "27", "AABCW4004D"),
	("Sahyadri Fine Chem", "Pune", "Maharashtra", "27", "AABCS5005E"),
	("Gujarat Organics & Extracts", "Vadodara", "Gujarat", "24", "AABCG6006F"),
	("Ankleshwar Chemicals Pvt Ltd", "Ankleshwar", "Gujarat", "24", "AABCA7007G"),
	("Deccan Lifesciences", "Hyderabad", "Telangana", "36", "AABCD8008H"),
	("Southern API Traders", "Chennai", "Tamil Nadu", "33", "AABCS9009J"),
	("Capital Vitamins & Herbs", "New Delhi", "Delhi", "07", "AABCC1010K"),
]


def _log(plan, msg):
	plan.append(msg)


def _gst_hsn_for(raw):
	"""Cleaned HS code matched to an existing GST HSN Code (try full, 8, 6, 4)."""
	code = (raw or "").replace(".", "").strip()
	if not code:
		return None
	for n in (len(code), 8, 6, 4):
		c = code[:n]
		if len(c) >= 4 and frappe.db.exists("GST HSN Code", c):
			return c
	return None


def _rate_for(raw):
	ch = (raw or "").replace(".", "").strip()[:2]
	return RATE_BY_CHAPTER.get(ch, DEFAULT_RATE)


def _mng_item_codes():
	soi = frappe.db.sql(
		"""SELECT DISTINCT soi.item_code FROM `tabSales Order Item` soi
		   JOIN `tabSales Order` so ON so.name=soi.parent WHERE so.company=%s""",
		COMPANY,
	)
	poi = frappe.db.sql(
		"""SELECT DISTINCT poi.item_code FROM `tabPurchase Order Item` poi
		   JOIN `tabPurchase Order` po ON po.name=poi.parent WHERE po.company=%s""",
		COMPANY,
	)
	return sorted({r[0] for r in soi} | {r[0] for r in poi})


def _ensure_address(plan, title, gstin, state, city, link_dt, link_name, is_company, dry):
	name = frappe.db.get_value("Address", {"gstin": gstin}, "name")
	if name:
		_log(plan, f"  address exists for {gstin} ({title})")
		return name
	_log(plan, f"  + address {title} · {gstin} · {state}")
	if dry:
		return None
	doc = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": title,
			"address_type": "Billing",
			"address_line1": city,
			"city": city,
			"state": state,
			"country": "India",
			"gstin": gstin,
			"gst_category": "Registered Regular",
			"is_your_company_address": 1 if is_company else 0,
			"links": [{"link_doctype": link_dt, "link_name": link_name}],
		}
	).insert(ignore_permissions=True)
	return doc.name


def _ensure_company_gst(plan, dry):
	_log(plan, "STEP 1/4 — company GST registration")
	company = frappe.get_doc("Company", COMPANY)
	if company.meta.has_field("gstin") and company.gstin != COMPANY_GSTIN:
		_log(plan, f"  set Company.gstin = {COMPANY_GSTIN}")
		if not dry:
			company.db_set("gstin", COMPANY_GSTIN, update_modified=False)
	if company.meta.has_field("gst_category") and company.gst_category != "Registered Regular":
		_log(plan, "  set Company.gst_category = Registered Regular")
		if not dry:
			company.db_set("gst_category", "Registered Regular", update_modified=False)
	_ensure_address(
		plan, "MN Globex - Indore", COMPANY_GSTIN, COMPANY_STATE,
		"412-A City Center, 570 M.G. Road, Indore 452001", "Company", COMPANY, True, dry,
	)


def _clean_orphan_gst_settings(plan, dry):
	"""GST Settings (a shared single doctype) has orphaned rows pointing to
	accounts of a company whose GST accounts were deleted (GHR CACS Pune /
	CACSPU). Frappe re-validates ALL rows on save, so those dangling FKs block
	adding MN Globex's accounts. Remove only rows whose accounts no longer exist
	(already non-functional) — never a row with valid accounts."""
	gs = frappe.get_doc("GST Settings")
	valid, removed = [], []
	for r in gs.gst_accounts:
		miss = [a for a in (r.cgst_account, r.sgst_account, r.igst_account) if a and not frappe.db.exists("Account", a)]
		(removed if miss else valid).append(r)
	if not removed:
		_log(plan, "  GST Settings: no orphaned rows")
		return
	_log(plan, f"  GST Settings: removing {len(removed)} orphaned rows {[(r.company, r.account_type) for r in removed]}")
	if not dry:
		gs.set("gst_accounts", valid)
		gs.save(ignore_permissions=True)


def _ensure_fixtures(plan, dry):
	_log(plan, "STEP 2/4 — GST accounts + Item Tax Templates")
	abbr = frappe.db.get_value("Company", COMPANY, "abbr")
	wanted = [f"GST {r}% - {abbr}" for r in (5, 12, 18)]
	have = [t for t in wanted if frappe.db.exists("Item Tax Template", t)]
	if len(have) == len(wanted):
		_log(plan, f"  templates already present: {wanted}")
		return abbr
	_clean_orphan_gst_settings(plan, dry)
	_log(plan, f"  create_company_fixtures({COMPANY}) -> GST accounts + templates")
	if not dry:
		from india_compliance.gst_india.overrides.company import create_company_fixtures

		create_company_fixtures(COMPANY)
	return abbr


def _assign_item(plan, code, abbr, dry):
	raw = (frappe.db.get_value("Item", code, "customs_tariff_number") or "").strip()
	hsn = _gst_hsn_for(raw)
	rate = _rate_for(raw)
	template = f"GST {rate}% - {abbr}"
	doc = frappe.get_doc("Item", code)
	# preserve other companies' tax rows on a shared item; replace only MNG's
	kept = [t for t in doc.taxes if frappe.db.get_value("Item Tax Template", t.item_tax_template, "company") != COMPANY]
	already = any(t.item_tax_template == template for t in doc.taxes)
	need_hsn = hsn and doc.meta.has_field("gst_hsn_code") and doc.gst_hsn_code != hsn
	if already and not need_hsn:
		return f"  = {code}: {template}, hsn={doc.gst_hsn_code}"
	if not dry:
		doc.set("taxes", kept)
		doc.append("taxes", {"item_tax_template": template})
		if need_hsn:
			doc.gst_hsn_code = hsn
		doc.save(ignore_permissions=True)
	return f"  + {code}: {template}, hsn={hsn or '(none)'} [raw {raw or '-'}]"


def _ensure_supplier_gst(plan, name, gstin, state, city, dry):
	if not frappe.db.exists("Supplier", name):
		_log(plan, f"  + supplier {name} ({state})")
		if not dry:
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": name,
					"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
					"supplier_type": "Company",
					"country": "India",
					"gst_category": "Registered Regular",
					"gstin": gstin,
				}
			).insert(ignore_permissions=True)
	else:
		sup = frappe.get_doc("Supplier", name)
		changed = []
		if sup.meta.has_field("gstin") and sup.gstin != gstin:
			changed.append("gstin")
			if not dry:
				sup.db_set("gstin", gstin, update_modified=False)
		if sup.meta.has_field("gst_category") and sup.gst_category != "Registered Regular":
			changed.append("gst_category")
			if not dry:
				sup.db_set("gst_category", "Registered Regular", update_modified=False)
		_log(plan, f"  ~ supplier {name}: {', '.join(changed) or 'already registered'}")
	_ensure_address(plan, f"{name} - {city}", gstin, state, city, "Supplier", name, False, dry)


def run(dry_run=True):
	dry = bool(dry_run)
	plan = [f"=== GST onboarding for {COMPANY} (dry_run={dry}) ==="]

	_ensure_company_gst(plan, dry)
	abbr = _ensure_fixtures(plan, dry)

	_log(plan, "STEP 3/4 — items (HSN + tax template)")
	codes = _mng_item_codes()
	_log(plan, f"  {len(codes)} MN Globex transacted items")
	# in dry run the templates don't exist yet; just preview rate/hsn decisions
	for code in codes:
		raw = (frappe.db.get_value("Item", code, "customs_tariff_number") or "").strip()
		if dry:
			_log(plan, f"  ? {code}: GST {_rate_for(raw)}% , hsn={_gst_hsn_for(raw) or '(none)'} [raw {raw or '-'}]")
		else:
			_log(plan, _assign_item(plan, code, abbr, dry))

	_log(plan, "STEP 4/4 — suppliers")
	# the Indian supplier on the user's PO
	if frappe.db.exists("Supplier", "NANDU"):
		_ensure_supplier_gst(plan, "NANDU", make_gstin("23", "AABCN0001A"), "Madhya Pradesh", "Indore", dry)
	for nm, city, state, sc, pan in DEMO_SUPPLIERS:
		_ensure_supplier_gst(plan, nm, make_gstin(sc, pan), state, city, dry)

	if not dry:
		frappe.db.commit()
	plan.append("=== done ===")
	return "\n".join(p for p in plan if p)
