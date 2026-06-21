from exportflow.setup import seed_terms_templates


def execute():
	"""Seed the sample selling/buying Terms and Conditions templates on existing
	sites (after_install handles fresh installs). Idempotent — skips any that
	already exist."""
	seed_terms_templates()
