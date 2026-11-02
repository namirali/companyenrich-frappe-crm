"""Run with bench --site test_site run-tests --app companyenrich_crm."""

from unittest.mock import patch

import frappe

from companyenrich_crm import api
from companyenrich_crm.install import SCRIPT_PREFIX, sync_scripts

try:
    from frappe.tests import IntegrationTestCase as FrappeTestCase
except ImportError:  # Frappe 15
    from frappe.tests.utils import FrappeTestCase


class TestIntegration(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.organization = frappe.get_doc(
            {
                "doctype": "CRM Organization",
                "organization_name": "CE fixture " + frappe.generate_hash(length=10),
                "website": "https://example.com",
                "no_of_employees": "",
            }
        ).insert()
        self.original_modified = str(self.organization.modified)

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def test_installed_settings_page_and_scripts(self):
        self.assertTrue(frappe.db.exists("Page", "companyenrich-research"))
        self.assertTrue(frappe.db.exists("Role", "CompanyEnrich User"))
        settings = frappe.get_single("CompanyEnrich Settings")
        self.assertEqual(settings.meta.get_field("api_key").fieldtype, "Password")
        self.assertEqual([permission.role for permission in settings.meta.permissions], ["System Manager"])
        for doctype in ("CRM Lead", "CRM Organization"):
            script = frappe.get_doc("CRM Form Script", SCRIPT_PREFIX + doctype)
            self.assertIn("class " + doctype.replace(" ", ""), script.script)
            self.assertIn("/app/companyenrich-research?", script.script)
        frappe.db.set_value("CRM Form Script", SCRIPT_PREFIX + "CRM Lead", "enabled", 0)
        page_modified = frappe.db.get_value("Page", "companyenrich-research", "modified")
        sync_scripts()
        self.assertNotEqual(frappe.db.get_value("Page", "companyenrich-research", "modified"), page_modified)
        self.assertEqual(frappe.db.get_value("CRM Form Script", SCRIPT_PREFIX + "CRM Lead", "enabled"), 0)

    def test_guest_cannot_spend(self):
        frappe.set_user("Guest")
        with patch.object(api, "client") as client, self.assertRaises(frappe.PermissionError):
            api.query("lookup_person", '{"body":{"email":"person@example.com"}}')
        client.assert_not_called()

    def test_read_and_write_permissions_checked_before_spending(self):
        with (
            patch("frappe.model.document.Document.check_permission", side_effect=frappe.PermissionError),
            patch.object(api, "client") as client,
            self.assertRaises(frappe.PermissionError),
        ):
            api.enrich_document("CRM Organization", self.organization.name, self.original_modified)
        client.assert_not_called()

    def test_stale_record_rejected_before_spending(self):
        with patch.object(api, "client") as client, self.assertRaises(frappe.TimestampMismatchError):
            api.enrich_document("CRM Organization", self.organization.name, "2000-01-01 00:00:00")
        client.assert_not_called()

    def test_fill_only_profile_fields(self):
        before = self.organization.as_dict()
        data = {
            "name": "Must not overwrite",
            "description": "Public company description",
            "employees": "501-1K",
            "annual_revenue": 123,
            "website": "https://other.example",
            "socials": {"linkedin_url": "https://linkedin.com/company/example"},
        }
        with patch.object(api, "client") as client:
            client.return_value.query.return_value = {"data": data, "credits_consumed": 1}
            result = api.enrich_document("CRM Organization", self.organization.name, self.original_modified)
            client.return_value.query.assert_called_once_with(
                "enrich_company", {"query": {"domain": "example.com", "waitForEnrichment": False}}
            )
        self.organization.reload()
        self.assertEqual(self.organization.organization_name, before["organization_name"])
        self.assertEqual(self.organization.website, before["website"])
        self.assertEqual(self.organization.annual_revenue, before["annual_revenue"])
        self.assertEqual(self.organization.company_description, "Public company description")
        self.assertEqual(self.organization.no_of_employees, "501-1000")
        self.assertIn("company_description", result["updated_fields"])
        self.assertEqual(result["credits_consumed"], 1)

    def test_change_during_provider_call_is_not_overwritten(self):
        def changed(*args):
            frappe.db.set_value(
                "CRM Organization", self.organization.name, "company_description", "Concurrent human edit"
            )
            return {"data": {"description": "API value"}, "credits_consumed": 1}

        with patch.object(api, "client") as client, self.assertRaises(frappe.TimestampMismatchError):
            client.return_value.query.side_effect = changed
            api.enrich_document("CRM Organization", self.organization.name, self.original_modified)
        self.assertEqual(
            frappe.db.get_value("CRM Organization", self.organization.name, "company_description"),
            "Concurrent human edit",
        )

    def test_signed_in_user_without_spending_role_cannot_request(self):
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": "ce-" + frappe.generate_hash(length=10) + "@example.com",
                "first_name": "Fixture",
                "send_welcome_email": 0,
                "roles": [{"role": "Sales User"}],
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(user.name)
        self.assertFalse(api.has_access())
        with patch.object(api, "client") as client, self.assertRaises(frappe.PermissionError):
            api.query("search_people", '{"body":{"domains":["example.com"]}}')
        client.assert_not_called()

    def test_spending_role_does_not_grant_crm_record_permissions(self):
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": "ce-" + frappe.generate_hash(length=10) + "@example.com",
                "first_name": "Fixture",
                "send_welcome_email": 0,
                "roles": [{"role": "CompanyEnrich User"}],
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(user.name)
        self.assertTrue(api.has_access())
        with patch.object(api, "client") as client, self.assertRaises(frappe.PermissionError):
            api.enrich_document("CRM Organization", self.organization.name, self.original_modified)
        client.assert_not_called()

    def test_password_is_encrypted_and_not_in_context(self):
        settings = frappe.get_single("CompanyEnrich Settings")
        settings.api_key = "test-placeholder-never-a-live-key"
        settings.save()
        self.assertEqual(settings.get_password("api_key"), "test-placeholder-never-a-live-key")
        self.assertNotEqual(
            frappe.db.get_single_value("CompanyEnrich Settings", "api_key"),
            "test-placeholder-never-a-live-key",
        )
        self.assertNotIn("test-placeholder-never-a-live-key", str(api.get_context()))
