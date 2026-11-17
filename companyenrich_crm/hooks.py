app_name = "companyenrich_crm"
app_title = "CompanyEnrich"
app_publisher = "CompanyEnrich"
app_description = "Company and people research for Frappe CRM"
app_email = ""
app_license = "MIT"
required_apps = ["crm"]

after_install = "companyenrich_crm.install.after_install"
after_migrate = "companyenrich_crm.install.after_migrate"
before_uninstall = "companyenrich_crm.install.before_uninstall"

doctype_js = {
    "CRM Lead": "public/js/record_actions.js",
    "CRM Organization": "public/js/record_actions.js",
}

add_to_apps_screen = [
    {
        "name": "companyenrich_crm",
        "title": "CompanyEnrich",
        "route": "/app/companyenrich-research",
        "logo": "/assets/companyenrich_crm/icon.svg",
        "has_permission": "companyenrich_crm.api.has_access",
    }
]
