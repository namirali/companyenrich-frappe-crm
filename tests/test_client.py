import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from companyenrich_crm.client import (
    BASE,
    MAX_RESPONSE,
    OPERATIONS,
    Client,
    ProviderError,
    browser_safe,
    prepare,
)
from companyenrich_crm.mapping import domain_from_url, profile_fields


@pytest.mark.parametrize("operation", OPERATIONS)
def test_all_documented_examples_match_contract(operation):
    prepare(operation, OPERATIONS[operation]["example"])


@pytest.mark.parametrize(
    "operation,parameters",
    [
        ("unknown", {}),
        ("search_people", {"body": {"companyDomain": "example.com"}}),
        ("get_person", {"query": {"id": 9.3e19}}),
        ("search_people", {"body": {"pageSize": 101}}),
        ("enrich_companies_batch", {"body": {"domains": []}}),
        ("workforce", {"query": {}}),
        ("workforce", {"query": {"domain": "example.com", "id": "00000000-0000-4000-8000-000000000001"}}),
        ("get_company", {"query": {"id": "not-a-uuid"}}),
        ("get_person", {"query": {"id": "9223372036854775808"}}),
        ("get_person", {"query": {"id": 0}}),
        ("enrich_company_properties", {"body": {}}),
        ("lookup_person", {"body": {"email": "not-email"}}),
        ("enrich_company", {"query": {"domain": "example.com"}, "url": "https://evil.example"}),
        ("search_people", '{"body":{"pageSize":NaN}}'),
        ("search_people", "x" * 66000),
    ],
)
def test_rejects_invalid_requests(operation, parameters):
    with pytest.raises(ValueError):
        prepare(operation, parameters)


def test_person_id_does_not_round_or_mutate():
    parameters = {"query": {"id": "9007199254740993"}}
    _, query, _ = prepare("get_person", parameters)
    assert query["id"] == 9007199254740993
    assert parameters["query"]["id"] == "9007199254740993"
    assert browser_safe({"id": 9007199254740993, "count": 10, "flag": True}) == {
        "id": "9007199254740993",
        "count": 10,
        "flag": True,
    }


def response(data=None, status=200, headers=None, chunks=None):
    mock = MagicMock()
    mock.__enter__.return_value = mock
    mock.status_code = status
    mock.headers = headers or {}
    mock.iter_content.return_value = chunks if chunks is not None else [json.dumps(data).encode()]
    return mock


def session(mock_response):
    mock = MagicMock()
    mock.__enter__.return_value = mock
    mock.request.return_value = mock_response
    return mock


def test_exact_transport_and_zero_credits():
    mock = session(response({"id": 9007199254740993, "creditsConsumed": 0}, headers={"x-credit-cost": "5"}))
    with patch("companyenrich_crm.client.requests.Session", return_value=mock):
        result = Client("secret").query(
            "enrich_company",
            {
                "query": {
                    "domain": "example.com",
                    "waitForEnrichment": False,
                    "expand": ["workforce"],
                }
            },
        )
    assert result == {"data": {"id": "9007199254740993", "creditsConsumed": 0}, "credits_consumed": 0}
    args, kwargs = mock.request.call_args
    assert args == ("GET", BASE + "/companies/enrich")
    assert kwargs["params"] == [
        ("domain", "example.com"),
        ("waitForEnrichment", "false"),
        ("expand", "workforce"),
    ]
    assert kwargs["headers"]["Authorization"] == "Bearer secret"
    assert kwargs["allow_redirects"] is False
    assert kwargs["stream"] is True
    assert kwargs["timeout"] == (5, 30)
    assert mock.trust_env is False
    assert mock.request.call_count == 1


@pytest.mark.parametrize("status", [301, 401, 402, 403, 404, 429, 500])
def test_upstream_errors_never_leak_body_and_do_not_retry(status):
    mock = session(
        response({"message": "secret person@example.com"}, status=status, headers={"x-credit-cost": "1"})
    )
    with (
        patch("companyenrich_crm.client.requests.Session", return_value=mock),
        pytest.raises(ProviderError) as caught,
    ):
        Client("secret").query("lookup_person", {"body": {"email": "person@example.com"}})
    assert "secret" not in str(caught.value)
    assert "@" not in str(caught.value)
    assert caught.value.credits == 1
    assert mock.request.call_count == 1


@pytest.mark.parametrize("chunks", [[b"not json"], [b"NaN"], [b"x" * (MAX_RESPONSE + 1)]])
def test_invalid_and_oversized_responses(chunks):
    with (
        patch("companyenrich_crm.client.requests.Session", return_value=session(response(chunks=chunks))),
        pytest.raises(ProviderError),
    ):
        Client("secret").account()


def test_transport_failure_not_retried():
    mock = session(None)
    mock.request.side_effect = requests.Timeout("secret")
    with (
        patch("companyenrich_crm.client.requests.Session", return_value=mock),
        pytest.raises(ProviderError, match="not retried"),
    ):
        Client("secret").account()
    assert mock.request.call_count == 1


def test_free_account_returns_only_remaining_credits():
    with patch(
        "companyenrich_crm.client.requests.Session",
        return_value=session(
            response({"email": "private@example.com", "credits": {"total": 100, "used": 15}})
        ),
    ):
        assert Client("secret").account() == {"remaining_credits": 85}


def test_profile_mapping_excludes_lifecycle_contact_consent_and_person_socials():
    source = {
        "name": "Acme",
        "employees": "501-1K",
        "annual_revenue": 123,
        "email": "x@example.com",
        "status": "Qualified",
        "socials": {"linkedin_url": "https://linkedin.com/company/acme"},
    }
    company = profile_fields("CRM Lead", "company", source)
    assert company["no_of_employees"] == "501-1000"
    assert company["organization"] == "Acme"
    assert not {"status", "email", "phone", "annual_revenue", "lead_owner", "consent"} & company.keys()
    person = profile_fields(
        "CRM Lead", "person", {"first_name": "A", "last_name": "B", "position": "CEO", **source}
    )
    assert person == {"first_name": "A", "last_name": "B", "job_title": "CEO"}
    assert profile_fields("CRM Organization", "person", source) == {}


def test_malformed_profile_values_are_ignored():
    result = profile_fields(
        "CRM Lead",
        "company",
        {"employees": [], "socials": "bad", "name": {}, "website": "javascript:alert(1)"},
    )
    assert all(value is None for value in result.values())
    assert domain_from_url("https://example.com/path") == "example.com"
    assert domain_from_url("user:password@example.com") is None
    assert domain_from_url("javascript:alert(1)") is None
