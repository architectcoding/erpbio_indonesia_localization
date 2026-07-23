"""Serves the /erpbio-tax SPA — Indonesian tax compliance (Coretax e-Faktur
export/import). Same session/boot model as the ERPbio suite's other SPAs."""

import frappe
from frappe.boot import load_translations

no_cache = 1


def get_context(context):
	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # nosemgrep
	context = frappe._dict()
	context.csrf_token = csrf_token
	context.boot = get_boot()
	context.site_name = frappe.local.site
	return context


@frappe.whitelist(methods=["POST"], allow_guest=True)
def get_context_for_dev():
	if not frappe.conf.developer_mode:
		frappe.throw(frappe._("This method is only meant for developer mode"))
	return get_boot()


def get_boot():
	bootinfo = frappe._dict(
		{
			"site_name": frappe.local.site,
			"default_route": "/erpbio-tax",
			"socketio_port": frappe.conf.socketio_port,
			"app_title": "ERPbio Tax",
		}
	)
	bootinfo.lang = str(frappe.local.lang)
	load_translations(bootinfo)
	# load_translations re-sets lang to a LocalProxy that json.dumps rejects;
	# the template JSON-encodes this dict, so coerce back to str.
	bootinfo.lang = str(bootinfo.lang)
	return bootinfo
