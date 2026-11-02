"""Bounded CompanyEnrich client; no Frappe dependency or implicit retries."""

import json
import math
from pathlib import Path

import requests
from jsonschema import Draft7Validator, FormatChecker

CONTRACT = json.loads(Path(__file__).with_name("contract.json").read_text())
OPERATIONS = CONTRACT["operations"]
BASE = "https://api.companyenrich.com"
MAX_RESPONSE = 5 * 1024 * 1024
MAX_REQUEST = 64 * 1024


class ProviderError(Exception):
    def __init__(self, message, status=None, credits=None):
        super().__init__(message)
        self.status = status
        self.credits = credits


def reject_constant(_value):
    raise ValueError("Non-finite JSON numbers are not supported")


def prepare(operation, parameters):
    if operation not in OPERATIONS:
        raise ValueError("Choose a supported CompanyEnrich operation")
    if isinstance(parameters, str):
        if len(parameters.encode()) > MAX_REQUEST:
            raise ValueError("Request is too large")
        try:
            parameters = json.loads(parameters, parse_constant=reject_constant)
        except (ValueError, TypeError) as error:
            raise ValueError("Parameters must be valid JSON") from error
    # Copy input so normalization never changes a caller's own object.
    encoded = json.dumps(parameters, allow_nan=False)
    if len(encoded.encode()) > MAX_REQUEST:
        raise ValueError("Request is too large")
    parameters = json.loads(encoded)
    if operation in {"get_person", "person_education"} and isinstance(parameters, dict):
        query = parameters.get("query", {})
        if isinstance(query, dict) and isinstance(query.get("id"), str) and query["id"].isdigit():
            query["id"] = int(query["id"])
        if isinstance(query, dict) and (type(query.get("id")) is not int or not 0 < query["id"] <= 2**63 - 1):
            raise ValueError("Person ID must be a positive 64-bit integer")
    op = OPERATIONS[operation]
    schema = {"$defs": CONTRACT["$defs"], **op["schema"]}
    errors = list(Draft7Validator(schema, format_checker=FormatChecker()).iter_errors(parameters))
    if errors:
        path = ".".join(map(str, errors[0].absolute_path)) or "parameters"
        # Do not echo request contents (people lookups can contain an email).
        raise ValueError(f"Invalid {path}; check the operation's API schema")
    query, body = parameters.get("query", {}), parameters.get("body")
    if operation == "workforce" and bool(query.get("id")) == bool(query.get("domain")):
        raise ValueError("Workforce requires exactly one of domain or company ID")
    if operation == "enrich_company_properties" and not any(body.values()):
        raise ValueError("Provide a company name or supported social identifier")
    if operation == "lookup_person" and ("@" not in body["email"] or len(body["email"]) > 320):
        raise ValueError("Provide a valid email address")
    return op, query, body


def browser_safe(value):
    """JavaScript cannot exactly represent all provider int64 IDs."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and abs(value) > 2**53 - 1:
        return str(value)
    if isinstance(value, list):
        return [browser_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: browser_safe(item) for key, item in value.items()}
    return value


def credit_value(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and 0 <= result <= 2**53 - 1 else None
    except (TypeError, ValueError, OverflowError):
        return None


class Client:
    def __init__(self, api_key):
        self.api_key = api_key

    def query(self, operation, parameters):
        op, query, body = prepare(operation, parameters)
        return self._request(op["method"], op["path"], query, body)

    def account(self):
        result = self._request("GET", "/me", {}, None)
        credits = result["data"].get("credits", {}) if isinstance(result["data"], dict) else {}
        credits = credits if isinstance(credits, dict) else {}
        total, used = credit_value(credits.get("total")), credit_value(credits.get("used"))
        return {"remaining_credits": max(0, total - used) if total is not None and used is not None else None}

    def _request(self, method, path, query, body):
        params = []
        for key, value in query.items():
            for item in value if isinstance(value, list) else [value]:
                if item is not None:
                    params.append((key, str(item).lower() if isinstance(item, bool) else str(item)))
        try:
            with requests.Session() as session:
                session.trust_env = False  # Avoid implicit netrc credentials or proxy redirects.
                with session.request(
                    method,
                    BASE + path,
                    headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
                    params=params,
                    json=body,
                    timeout=(5, 30),
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    credits = credit_value(response.headers.get("x-credit-cost"))
                    if response.status_code != 200:
                        messages = {
                            401: "CompanyEnrich rejected the API key",
                            403: "This CompanyEnrich account cannot access the operation",
                            402: "CompanyEnrich credits are exhausted",
                            404: "No matching record was returned",
                            429: "CompanyEnrich rate limit reached; try again later",
                        }
                        raise ProviderError(
                            messages.get(
                                response.status_code, "CompanyEnrich could not complete the request"
                            ),
                            response.status_code,
                            credits,
                        )
                    content = bytearray()
                    for chunk in response.iter_content(65536):
                        content.extend(chunk)
                        if len(content) > MAX_RESPONSE:
                            raise ProviderError(
                                "CompanyEnrich response exceeded the size limit; narrow the query",
                                credits=credits,
                            )
                    try:
                        data = json.loads(content, parse_constant=reject_constant)
                    except (ValueError, UnicodeDecodeError) as error:
                        raise ProviderError("CompanyEnrich returned invalid JSON", credits=credits) from error
                    if isinstance(data, dict) and credit_value(data.get("creditsConsumed")) is not None:
                        credits = credit_value(data["creditsConsumed"])
                    return {"data": browser_safe(data), "credits_consumed": credits}
        except requests.RequestException as error:
            raise ProviderError(
                "CompanyEnrich request failed. Credit usage is unknown; the request was not retried"
            ) from error
