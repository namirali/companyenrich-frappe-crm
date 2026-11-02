"""Generate the supported request schemas from CompanyEnrich's public OpenAPI file."""

import json
import sys
from pathlib import Path

OPS = {
    "person_education": (
        "GET",
        "/people/education",
        "Get person education",
        {"query": {"id": "9007199254740993"}},
    ),
    "autocomplete_companies": (
        "GET",
        "/companies/autocomplete",
        "Autocomplete company domain (free)",
        {"query": {"query": "example"}},
    ),
    "preview_companies": (
        "POST",
        "/companies/search/preview",
        "Preview company search (Scale plan)",
        {"body": {"query": "example"}},
    ),
    "preview_similar": (
        "POST",
        "/companies/similar/preview",
        "Preview similar companies (Scale plan)",
        {"body": {"domains": ["example.com"]}},
    ),
    "enrich_company": (
        "GET",
        "/companies/enrich",
        "Enrich company by domain",
        {"query": {"domain": "example.com", "waitForEnrichment": False}},
    ),
    "enrich_company_properties": (
        "POST",
        "/companies/enrich",
        "Enrich company by properties",
        {"body": {"name": "Example Company"}},
    ),
    "enrich_companies_batch": (
        "POST",
        "/companies/enrich/batch",
        "Enrich up to 50 companies",
        {"body": {"domains": ["example.com"]}},
    ),
    "get_company": (
        "GET",
        "/companies",
        "Get company by ID",
        {"query": {"id": "00000000-0000-4000-8000-000000000001"}},
    ),
    "search_companies": (
        "POST",
        "/companies/search",
        "Search companies",
        {"body": {"page": 1, "pageSize": 10, "query": "example"}},
    ),
    "similar_companies": (
        "POST",
        "/companies/similar",
        "Find similar companies",
        {"body": {"domains": ["example.com"], "page": 1, "pageSize": 10}},
    ),
    "count_companies": (
        "POST",
        "/companies/search/count",
        "Count matching companies",
        {"body": {"query": "example"}},
    ),
    "count_similar": (
        "POST",
        "/companies/similar/count",
        "Count similar companies",
        {"body": {"domains": ["example.com"]}},
    ),
    "search_people": (
        "POST",
        "/people/search",
        "Search professional profiles",
        {"body": {"domains": ["example.com"], "page": 1, "pageSize": 10}},
    ),
    "lookup_person": (
        "POST",
        "/people/lookup",
        "Look up person by email",
        {"body": {"email": "person@example.com"}},
    ),
    "get_person": ("GET", "/people", "Get person by ID", {"query": {"id": "9007199254740993"}}),
    "workforce": (
        "GET",
        "/companies/workforce",
        "Get company workforce",
        {"query": {"domain": "example.com"}},
    ),
}


def convert(value):
    if isinstance(value, list):
        return [convert(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {k: convert(v) for k, v in value.items() if k not in {"nullable", "description", "example"}}
    if result.get("type") == "object" and "properties" in result:
        result.setdefault("additionalProperties", False)
    if "$ref" in result:
        result["$ref"] = result["$ref"].replace("#/components/schemas/", "#/$defs/")
    if value.get("nullable"):
        return {"anyOf": [result, {"type": "null"}]}
    return result


def main(source):
    raw = json.loads(Path(source).read_text())
    operations = {}
    referenced = set()
    for name, (method, path, label, example) in OPS.items():
        operation = raw["paths"][path][method.lower()]
        params = [p for p in operation.get("parameters", []) if p["in"] == "query"]
        query = {
            "type": "object",
            "properties": {p["name"]: convert(p["schema"]) for p in params},
            "additionalProperties": False,
        }
        query["required"] = [p["name"] for p in params if p.get("required")]
        properties = {"query": query}
        required = ["query"] if query["required"] else []
        if "requestBody" in operation:
            properties["body"] = convert(operation["requestBody"]["content"]["application/json"]["schema"])
            required.append("body")
        schema = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
        operations[name] = {
            "method": method,
            "path": path,
            "label": label,
            "cost": " ".join(
                part.replace("**", "")
                for part in operation.get("description", "").split("\n\n")
                if part.startswith(("**Cost:", "**Requirements:", "**Notice:"))
            ),
            "schema": schema,
            "example": example,
        }

    defs = {name: convert(schema) for name, schema in raw["components"]["schemas"].items()}

    def collect(value):
        if isinstance(value, list):
            for item in value:
                collect(item)
        if isinstance(value, dict):
            if "$ref" in value:
                name = value["$ref"].split("/")[-1]
                if name not in referenced:
                    referenced.add(name)
                    collect(defs[name])
            for item in value.values():
                collect(item)

    collect(operations)
    output = {
        "source": "https://api.companyenrich.com/openapi/v1.json",
        "checked": "2026-11-02",
        "$defs": {name: defs[name] for name in sorted(referenced)},
        "operations": operations,
    }
    target = Path(__file__).resolve().parents[1] / "companyenrich_crm" / "contract.json"
    target.write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
