# CompanyEnrich for Frappe CRM

[CompanyEnrich](https://companyenrich.com) provides company enrichment, company search and lookalikes, professional people profiles, and workforce data through an API. This independent, installable Frappe app brings those capabilities into Frappe CRM. It is not an upstream Frappe product or an approved Marketplace listing.

## Install

Requires Frappe 15 or 16 and Frappe CRM **1.91.1 or newer in the 1.x series**, with the class-based CRM Form Script API. Install CRM first. Back up an existing site before adding an app.

```sh
bench get-app https://github.com/namirali/companyenrich-frappe-crm --branch main
bench --site your-site install-app companyenrich_crm
bench --site your-site migrate
bench build --app companyenrich_crm
```

While the implementation PR is open, use `--branch codex/companyenrich-integration` instead of `--branch main`.

1. As a System Manager, open **CompanyEnrich Settings**, enter an API key in the encrypted Password field, enable the integration, and save.
2. Use **Check saved API key (free)** to verify it via `GET /me` and view remaining credits. No account details are exposed.
3. Grant **CompanyEnrich User** only to users allowed to spend the site's shared CompanyEnrich credits. System Managers also have access. Existing CRM permissions still apply.
4. Open a saved Lead or Organization and choose **CompanyEnrich**, or visit `/app/companyenrich-research` for standalone research. CRM opens the research page in a new tab; save any CRM edits first and reload the record after applying enrichment.

The installed CRM Form Scripts add an action using the supported scripting API. Desk forms get the same action through `doctype_js`. No upstream source patches or frontend build dependency are required. Administrators can disable the two `CompanyEnrich — CRM …` scripts; upgrades preserve that choice.

## Operations

The research page exposes editable JSON parameters, documented examples, request cost guidance, returned data and reported credit usage. All filters from the bundled public request schema are available, including industry, location, headcount, revenue, technologies and supported people filters. Results remain in the current browser view and are not automatically imported into CRM.

| Operation | Endpoint |
| --- | --- |
| Enrich company by domain | `GET /companies/enrich` |
| Enrich by name or social identifier | `POST /companies/enrich` |
| Batch enrich companies (1–50 domains) | `POST /companies/enrich/batch` |
| Get company by UUID | `GET /companies` |
| Search companies | `POST /companies/search` |
| Find similar companies | `POST /companies/similar` |
| Count company search matches | `POST /companies/search/count` |
| Count similar companies | `POST /companies/similar/count` |
| Search people | `POST /people/search` |
| Look up person from a known email | `POST /people/lookup` |
| Get person by ID | `GET /people` |
| Company workforce | `GET /companies/workforce` |
| Person education | `GET /people/education` |
| Company autocomplete | `GET /companies/autocomplete` |
| Preview company search (Scale plan) | `POST /companies/search/preview` |
| Preview similar companies (Scale plan) | `POST /companies/similar/preview` |

People search returns professional profiles, **not email addresses**. Person lookup accepts an email you already have. Large person IDs are preserved as strings in browser results; enter them as quoted strings in parameters. Optional workforce expansions are explicit and can consume additional credits.

Preview endpoints require a Scale plan and return at most 25 results. Autocomplete and previews run only when selected and explicitly requested.

The contract was generated from the [public OpenAPI schema](https://api.companyenrich.com/openapi/v1.json) on 2026-11-02. API documentation and current pricing remain authoritative: [docs.companyenrich.com](https://docs.companyenrich.com). The app does not implement asynchronous bulk/scroll/export/list administration or beta email/jobs/advertising APIs.

## Fill missing profile fields

On a record-linked page, a separate confirmation action can fill missing company fields from its saved website, or missing person fields from a Lead's saved email. It checks CRM read and write permissions before requesting data, then locks and rechecks the record after the API returns. If someone changed the record meanwhile, it refuses to apply the result; the lookup may already have consumed credits.

Company fields: organization name, website, company description, employee range and public company social links. Industry is filled only when it already exists as a readable CRM Industry. Person fields: first name, last name and job title. Existing values are never replaced. Custom nonzero field permission levels are skipped for both source identifiers and target profile fields. Lifecycle/status, ownership, consent, contact details and annual revenue are never changed. CRM Lead's LinkedIn field describes the company, so a person's LinkedIn profile is intentionally not written there.

Profile changes use a constrained database update after permission and concurrency checks, avoiding unrelated CRM save hooks that can alter lifecycle fields. An Info comment records changed field names, without API payloads or credentials. Custom business validations in save hooks do not run for these profile-only updates.

## Credits, privacy and errors

Nothing runs in the background or on record load. Each click is one request; the app does not retry a failed, timed-out or rate-limited paid request. Domain profile filling explicitly uses cached enrichment (`waitForEnrichment=false`); a missing cached company can return 404 while the provider schedules enrichment. The app does not automatically repeat it.

Reported credits come from the response's `creditsConsumed` value (including zero), otherwise `x-credit-cost`; absent usage is shown as unknown. No local estimate is presented as an actual charge. Free connection checking returns only remaining credits.

Requests go only to `https://api.companyenrich.com`, with TLS verification, no redirects, bounded response/request sizes and connection/read timeouts. Raw upstream errors and request payloads are not logged by this app. The API key is stored in Frappe's encrypted Password storage and is only configurable by System Managers. There is no per-user budget: administrators control access to the shared key through roles. Review the provider's terms and your organization's data policies before using real records.

## Development and tests

```sh
python -m pip install -e '.[test]'
ruff check .
ruff format --check .
pytest
python -m build
node --test tests/ui.test.cjs
# In a test bench with CRM and this app installed:
bench --site test_site set-config allow_tests true
bench --site test_site run-tests --app companyenrich_crm
```

Tests mock every CompanyEnrich request; they never require a key or spend credits. CI runs unit, UI and package checks plus installation and integration tests against Frappe 15 and 16 with CRM 1.91.1. To regenerate request validation from a reviewed public schema:

```sh
python tools/generate_contract.py path/to/companyenrich-openapi.json
```

## Upgrade and uninstall

```sh
bench update
bench --site your-site migrate
# Back up first. Frappe asks for confirmation before removing app data:
bench --site your-site uninstall-app companyenrich_crm
```

Uninstall removes app settings/page and its two named CRM Form Scripts. Existing CRM data is retained. The role is retained to avoid deleting administrator-managed user assignments; it grants no API access after the app is removed. Previously applied profile values and audit comments remain.

[Marketplace listing draft and submission steps](docs/marketplace-listing.md). Report integration bugs through this repository's issues. MIT licensed.
