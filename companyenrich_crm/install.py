"""Install only the app's named CRM scripts; preserve administrator disablement."""

from pathlib import Path

import frappe

SCRIPT_PREFIX = "CompanyEnrich — "


def sync_scripts():
    if not frappe.db.exists("Role", "CompanyEnrich User"):
        frappe.get_doc({"doctype": "Role", "role_name": "CompanyEnrich User", "desk_access": 1}).insert(
            ignore_permissions=True
        )
    template = Path(__file__).with_name("public").joinpath("js", "crm_form_script.js").read_text()
    for doctype in ("CRM Lead", "CRM Organization"):
        name = SCRIPT_PREFIX + doctype
        script = template.replace("CE_CONTROLLER", doctype.replace(" ", "")).replace("CE_DOCTYPE", doctype)
        if frappe.db.exists("CRM Form Script", name):
            # Only app-owned names; disabled scripts remain disabled on upgrades.
            frappe.db.set_value("CRM Form Script", name, {"script": script, "dt": doctype, "view": "Form"})
        else:
            frappe.get_doc(
                {
                    "doctype": "CRM Form Script",
                    "name": name,
                    "dt": doctype,
                    "view": "Form",
                    "enabled": 1,
                    "is_standard": 1,
                    "script": script,
                }
            ).insert(ignore_permissions=True)

    # Desk caches page scripts by the Page modified timestamp. Refresh it when
    # upgrading JavaScript even if the page's JSON metadata did not change.
    if frappe.db.exists("Page", "companyenrich-research"):
        frappe.db.set_value("Page", "companyenrich-research", "modified", frappe.utils.now_datetime())


def after_install():
    sync_scripts()


def after_migrate():
    sync_scripts()


def before_uninstall():
    for doctype in ("CRM Lead", "CRM Organization"):
        name = SCRIPT_PREFIX + doctype
        if frappe.db.exists("CRM Form Script", name):
            frappe.delete_doc("CRM Form Script", name, ignore_permissions=True, force=True)
