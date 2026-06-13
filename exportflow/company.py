"""Single source of truth for the company ExportFlow operates under.

The app runs on a shared dev bench, so we do NOT touch the site-wide
Global Defaults default_company (other apps depend on it). Instead the
ExportFlow Company is configured in ExportFlow Settings; everything else
falls back to the site default so a fresh/test site still works.
"""

import frappe


def exportflow_company() -> str | None:
	company = frappe.db.get_single_value("ExportFlow Settings", "company")
	if company and frappe.db.exists("Company", company):
		return company
	return frappe.db.get_single_value("Global Defaults", "default_company")


def company_currency(company: str | None = None) -> str | None:
	company = company or exportflow_company()
	return frappe.db.get_value("Company", company, "default_currency") if company else None
