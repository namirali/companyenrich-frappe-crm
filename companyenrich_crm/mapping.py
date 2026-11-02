"""Only profile fields; no contact details, consent, ownership or lifecycle fields."""

from urllib.parse import urlsplit

EMPLOYEES = {
    "1-10": "1-10",
    "11-50": "11-50",
    "51-200": "51-200",
    "201-500": "201-500",
    "501-1K": "501-1000",
    "1K-5K": "1000+",
    "5K-10K": "1000+",
    "over-10K": "1000+",
}


def text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def public_url(value):
    value = text(value)
    if not value:
        return None
    try:
        parts = urlsplit(value)
        return (
            value
            if parts.scheme in {"https", "http"}
            and parts.hostname
            and not parts.username
            and not parts.password
            else None
        )
    except ValueError:
        return None


def domain_from_url(value):
    value = text(value)
    if not value:
        return None
    try:
        parts = urlsplit(value if "://" in value else "https://" + value)
        _ = parts.port  # Reject invalid ports and scheme-like non-URLs.
        return (
            parts.hostname
            if parts.scheme in {"http", "https"} and not parts.username and not parts.password
            else None
        )
    except ValueError:
        return None


def profile_fields(doctype, kind, data):
    if not isinstance(data, dict):
        return {}
    if kind == "person":
        if doctype != "CRM Lead":
            return {}
        # CRM Lead's linkedin field belongs to the organization, so a person's
        # profile URL must not replace it.
        return {
            key: text(data.get(source))
            for key, source in {
                "first_name": "first_name",
                "last_name": "last_name",
                "job_title": "position",
            }.items()
        }
    socials = data.get("socials") if isinstance(data.get("socials"), dict) else {}
    fields = {
        "organization" if doctype == "CRM Lead" else "organization_name": text(data.get("name")),
        "website": public_url(data.get("website")),
        "company_description": text(data.get("description")),
        "no_of_employees": EMPLOYEES.get(text(data.get("employees"))),
        "industry": text(data.get("industry")),
        "linkedin": public_url(socials.get("linkedin_url")),
        "twitter": public_url(socials.get("twitter_url")),
        "facebook": public_url(socials.get("facebook_url")),
    }
    return fields
