"""Service discovery independent of Django, providers, or database state.

The catalog describes public product capabilities. It deliberately does not
claim that a service has a verified executable API. Provider adapters own that
decision and must report their availability separately.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from apps.product_scope import EXCLUDED_SERVICES, SCOPE_NOTE


class UnknownServiceError(KeyError):
    """The supplied identifier is not a catalog service."""


_DATA_FILE = Path(__file__).with_name("data") / "services.json"
_CHARACTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "\u200c": " "})


def _search_text(value: str) -> str:
    return " ".join(value.translate(_CHARACTERS).casefold().split())


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    payload = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    payload["services"] = [s for s in payload["services"] if s["id"] not in EXCLUDED_SERVICES]
    payload["scope"] = SCOPE_NOTE
    for category in payload["categories"]:
        category["count"] = sum(s["category"] == category["id"] for s in payload["services"])
    services = payload["services"]
    identifiers = [service["id"] for service in services]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Catalog contains duplicate service identifiers")
    return payload


def list_categories() -> list[dict[str, Any]]:
    """Return category identifiers, Persian names, and catalog entry counts."""
    return deepcopy(_catalog()["categories"])


def list_services(
    category: str | None = None,
    query: str | None = None,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Search by category ID/Persian label and normalized Persian/English text.

    With no pagination parameters all entries are returned. Use ``catalog_page``
    when a tool or HTTP endpoint needs a total and next-page cursor.
    """
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100):
        raise ValueError("limit must be an integer from 1 to 100")
    selected_category = _search_text(category) if category else None
    tokens = _search_text(query).split() if query else []
    matches = []
    for service in _catalog()["services"]:
        if selected_category and selected_category not in {
            _search_text(service["category"]),
            _search_text(service["category_fa"]),
        }:
            continue
        haystack = _search_text(
            " ".join(
                [service["id"], service["name_fa"], service["description"]] + service.get("keywords", [])
            )
        )
        words = re.findall(r"[\w-]+", haystack)
        if not all(any(word.startswith(token) for word in words) for token in tokens):
            continue
        matches.append(service)
    end = None if limit is None else offset + limit
    return deepcopy(matches[offset:end])


def catalog_page(
    category: str | None = None,
    query: str | None = None,
    *,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    """Return a bounded page, retaining total count for tool/client navigation."""
    items = list_services(category, query, offset=offset, limit=limit)
    total = len(list_services(category, query))
    next_offset = offset + len(items)
    return {
        "items": items,
        "total": total,
        "count": len(items),
        "offset": offset,
        "limit": limit,
        "next_offset": next_offset if next_offset < total else None,
    }


def get_service(service_id: str) -> dict[str, Any]:
    """Return an isolated copy of an exact, stable URL-derived service ID."""
    for service in _catalog()["services"]:
        if service["id"] == service_id:
            return deepcopy(service)
    raise UnknownServiceError(service_id)


def service_requirements(service_id: str) -> dict[str, Any]:
    """Explain observed inputs and what still requires a provider contract.

    ``input_schema`` is an agent-facing normalized form, not a request body to
    send to an upstream API. Unknown/ambiguous requirements remain explicit.
    """
    service = get_service(service_id)
    return {
        "service_id": service["id"],
        "name_fa": service["name_fa"],
        "source_url": service["source_url"],
        "input_schema": service["input_schema"],
        "observed_inputs": service["observed_inputs"],
        "requirements_status": service["requirements_status"],
        "requires_account": service["requires_account"],
        "account_requirement_basis": service["account_requirement_basis"],
        "cost_mode": service["cost_mode"],
        "cost_scope": service["cost_scope"],
        "workflow_actions": service["workflow_actions"],
        "variants": service["variants"],
        "limitations": service["limitations"],
        "capability_status": service["capability_status"],
        "api_contract_verified": False,
        "evidence": service["evidence"],
        "next_step": "Use the selected provider's capability report and verified contract before execution.",
    }
