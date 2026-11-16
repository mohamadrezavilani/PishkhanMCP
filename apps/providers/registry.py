"""Executable actions discovered in the public Pishkhan frontend.

The catalog describes products; this registry describes observed wire contracts.
Source verification is not a claim that authenticated live calls were tested.
"""

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from apps.core.errors import PishkhanError

REGISTRY_PATH = Path(__file__).with_name("data") / "pishkhan_actions.json"


@lru_cache(maxsize=1)
def registry():
    if not REGISTRY_PATH.exists():
        return {"actions": [], "live_observations": []}
    result = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return result if isinstance(result, dict) else {"actions": result}


def get_action(action_id):
    for action in registry()["actions"]:
        if action["id"] == action_id:
            return deepcopy(action)
    raise PishkhanError("UNKNOWN_ACTION", "عملیات شناخته نشد؛ ابتدا p24_search_actions را اجرا کنید.")


def find_action(endpoint, group=None):
    for action in registry()["actions"]:
        if action["path"].rstrip("/").split("/")[-1].lower() == endpoint.lower():
            if group is None or action["group"] == group:
                return deepcopy(action)
    raise PishkhanError("CONTRACT_UNAVAILABLE", f"No source-verified contract is registered for {endpoint}.")


def search_actions(query=None, service_id=None, offset=0, limit=20):
    if offset < 0 or not 1 <= limit <= 100:
        raise PishkhanError("INVALID_PAGINATION", "offset >= 0 and 1 <= limit <= 100 are required.")
    tokens = (query or "").replace("ي", "ی").replace("ك", "ک").lower().split()
    found = []
    for item in registry()["actions"]:
        if service_id and service_id not in item.get("service_ids", []):
            continue
        text = json.dumps(item, ensure_ascii=False).lower()
        if all(token in text for token in tokens):
            found.append(item)
    page = [
        {
            k: item.get(k)
            for k in ["id", "title_fa", "description", "service_ids", "requires_auth", "effect", "status"]
        }
        for item in found[offset : offset + limit]
    ]
    return {
        "items": page,
        "total": len(found),
        "offset": offset,
        "limit": limit,
        "next_offset": offset + len(page) if offset + len(page) < len(found) else None,
    }


def validate_parameters(action, parameters):
    schema = action.get("parameters_schema", {"type": "object"})
    invalid = next(Draft202012Validator(schema).iter_errors(parameters), None)
    if invalid:
        raise PishkhanError(
            "INVALID_PARAMETERS",
            "ورودی با قرارداد عملیات منطبق نیست.",
            details={
                "field": ".".join(str(x) for x in invalid.absolute_path),
                "rule": invalid.validator,
                "required": schema.get("required", []),
            },
        )


def coverage():
    items = registry()["actions"]
    services = sorted({slug for item in items for slug in item.get("service_ids", [])})
    return {
        "source_verified_actions": len(items),
        "services_with_observed_actions": services,
        "authenticated_live_validation": False,
        "observations": registry().get("live_observations", []),
    }
