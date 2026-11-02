import frappe
from frappe import _
from frappe.utils import get_datetime

from companyenrich_crm.client import OPERATIONS, Client, ProviderError, prepare
from companyenrich_crm.mapping import domain_from_url, profile_fields

ALLOWED_DOCTYPES = {"CRM Lead", "CRM Organization"}
ALLOWED_ROLES = {"CompanyEnrich User", "System Manager"}


def has_access():
    return frappe.session.user != "Guest" and bool(ALLOWED_ROLES.intersection(frappe.get_roles()))


def require_access():
    if not has_access():
        frappe.throw(_("The CompanyEnrich User role is required"), frappe.PermissionError)


def reference(doctype, name, write=False, for_update=False):
    if doctype not in ALLOWED_DOCTYPES or not isinstance(name, str) or not name:
        frappe.throw(_("Choose a saved CRM Lead or CRM Organization"))
    doc = frappe.get_doc(doctype, name, for_update=for_update)
    doc.check_permission("read")
    if write:
        doc.check_permission("write")
    return doc


def client():
    settings = frappe.get_single("CompanyEnrich Settings")
    if not settings.enabled:
        frappe.throw(_("CompanyEnrich is disabled. Ask a System Manager to configure it"))
    key = settings.get_password("api_key", raise_exception=False)
    if not key:
        frappe.throw(_("A CompanyEnrich API key has not been configured"))
    return Client(key)


def provider_call(action):
    try:
        return action()
    except (ProviderError, ValueError) as error:
        # ProviderError contains only our controlled messages, never upstream text.
        message = str(error)
        if isinstance(error, ProviderError) and error.credits is not None:
            message += _(" (reported credits: {0})").format(error.credits)
        frappe.throw(message)


@frappe.whitelist()
def can_access():
    return has_access()


@frappe.whitelist()
def get_context(doctype=None, name=None):
    require_access()
    result = {
        "operations": [
            {"id": key, "label": op["label"], "cost": op["cost"], "example": op["example"]}
            for key, op in OPERATIONS.items()
        ]
    }
    if doctype or name:
        doc = reference(doctype, name)
        result["reference"] = {
            "doctype": doctype,
            "name": name,
            "modified": str(doc.modified),
            "domain": domain_from_url(doc.get("website")),
            "email": doc.get("email") if doctype == "CRM Lead" else None,
            "can_write": doc.has_permission("write"),
        }
    return result


@frappe.whitelist(methods=["POST"])
def check_connection():
    frappe.only_for("System Manager")
    return provider_call(lambda: client().account())


@frappe.whitelist(methods=["POST"])
def query(operation, parameters, doctype=None, name=None):
    require_access()
    if doctype or name:
        reference(doctype, name)
    provider_call(lambda: prepare(operation, parameters))
    return provider_call(lambda: client().query(operation, parameters))


@frappe.whitelist(methods=["POST"])
def enrich_document(doctype, name, modified, kind="company"):
    require_access()
    doc = reference(doctype, name, write=True)
    if not modified or get_datetime(doc.modified) != get_datetime(modified):
        frappe.throw(_("This record has changed. Reload it before enrichment"), frappe.TimestampMismatchError)
    if kind == "company":
        domain = domain_from_url(doc.get("website"))
        if not domain:
            frappe.throw(_("Save a company website on this record before enriching it"))
        operation, parameters = "enrich_company", {"query": {"domain": domain, "waitForEnrichment": False}}
    elif kind == "person" and doctype == "CRM Lead" and doc.get("email"):
        operation, parameters = "lookup_person", {"body": {"email": doc.email}}
    else:
        frappe.throw(_("Person enrichment requires an existing CRM Lead email"))
    result = provider_call(lambda: client().query(operation, parameters))
    # Lock only after the network request. The fixed allowlist above prevents a
    # caller choosing a SQL table; values are bound parameters.
    current = reference(doctype, name, write=True, for_update=True)
    if get_datetime(current.modified) != get_datetime(modified):
        frappe.throw(
            _(
                "The record changed during enrichment. No fields were updated; the lookup may have consumed credits"
            ),
            frappe.TimestampMismatchError,
        )
    updates = {}
    for field, value in profile_fields(doctype, kind, result["data"]).items():
        meta = current.meta.get_field(field)
        if value is None or not meta or meta.permlevel or current.get(field) not in (None, ""):
            continue
        if meta.fieldtype == "Link":
            if not frappe.db.exists(meta.options, value) or not frappe.has_permission(
                meta.options, "read", doc=value
            ):
                continue
        elif meta.fieldtype == "Select":
            if value not in (meta.options or "").splitlines():
                continue
        elif meta.fieldtype not in {"Data", "Small Text", "Text", "Long Text"}:
            continue
        if meta.fieldtype == "Data" and len(value) > (meta.length or 140):
            continue
        if meta.fieldtype in {"Small Text", "Text"} and len(value.encode()) > 65000:
            continue
        updates[field] = value
    if updates:
        # Profile-only write: normal CRM save hooks can alter lifecycle fields.
        frappe.db.set_value(doctype, name, updates)
        current.add_comment(
            "Info", _("CompanyEnrich filled missing fields: {0}").format(", ".join(sorted(updates)))
        )
        current.notify_update()
    return {
        **result,
        "updated_fields": sorted(updates),
        "modified": str(frappe.db.get_value(doctype, name, "modified")),
    }
