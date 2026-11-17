"""Resolve product identity from the contract, never from list ordering."""

from apps.core.errors import PishkhanError

MOBILE_OPERATORS = {"mci": "Mci", "irancell": "Irancell", "rightel": "Rightel"}
MOBILE_ENDPOINTS = {"CellPhoneBills", "CellPhoneBillsDetails"}


def normalize_inputs(action, parameters):
    result = dict(parameters)
    if action["path"].split("/")[-1] in MOBILE_ENDPOINTS and "Operator" in result:
        operator = str(result["Operator"]).strip().casefold()
        if operator not in MOBILE_OPERATORS:
            raise PishkhanError("INVALID_MOBILE_OPERATOR", "Choose mci, irancell or rightel.")
        result["Operator"] = MOBILE_OPERATORS[operator]
    return result


def resolve_service(action, parameters, request=None):
    """Reject ambiguity and cross-service requests before contacting Core."""
    candidates = action.get("service_ids", [])
    selected = ""
    if action["path"].split("/")[-1] in MOBILE_ENDPOINTS and parameters.get("Operator"):
        selected = str(parameters["Operator"]).casefold()
        if selected not in MOBILE_OPERATORS or selected not in candidates:
            raise PishkhanError("INVALID_MOBILE_OPERATOR", "Operator does not match this action.")
    elif request and request.service_id in candidates:
        selected = request.service_id
    elif len(candidates) == 1:
        selected = candidates[0]
    elif candidates:
        raise PishkhanError(
            "SERVICE_CONTEXT_REQUIRED",
            "Select the service for this shared endpoint.",
            details={"service_ids": candidates},
        )
    if selected and request and request.service_id and selected != request.service_id:
        raise PishkhanError("REQUEST_SERVICE_MISMATCH", "Use a new request for a different service.")
    return selected
