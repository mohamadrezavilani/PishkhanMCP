import hashlib
import json

import httpx
import pytest
from jsonschema import Draft202012Validator

from apps.core.errors import PishkhanError
from apps.providers.client import PishkhanClient, password_digest, redact
from apps.providers.registry import find_action, registry, validate_parameters


def test_actual_wire_envelope_and_exact_endpoint(settings):
    settings.P24_API_BASE_URL = "https://provider.example/webservices"
    seen = []

    def upstream(request):
        seen.append(request)
        return httpx.Response(200, json={"Status": {"Code": "G00000"}, "Parameters": {"Amount": 123}})

    client = PishkhanClient(transport=httpx.MockTransport(upstream))
    result = client.call(
        find_action("ElectricBills", "services"), {"Identifier": "00012", "PurchaseKey": "key"}, "token"
    )
    assert str(seen[0].url) == "https://provider.example/webservices/services.svc/v1/ElectricBills"
    assert json.loads(seen[0].content) == {
        "Identity": {"Token": "token"},
        "Parameters": {"Identifier": "00012", "PurchaseKey": "key"},
    }
    assert result["parameters"]["Amount"] == 123


@pytest.mark.parametrize("parameters", [[], False, 0, "", {"List": []}])
def test_preserves_non_object_parameters(parameters):
    client = PishkhanClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"Status": {"Code": "g00000"}, "Parameters": parameters})
        )
    )
    assert client.call(find_action("ConfigBasic", "core"), {})["parameters"] == parameters


def test_timeout_is_unknown_and_post_not_retried():
    calls = []

    def upstream(request):
        calls.append(request)
        raise httpx.ReadTimeout("late", request=request)

    with pytest.raises(PishkhanError) as error:
        PishkhanClient(transport=httpx.MockTransport(upstream)).call(
            find_action("InvoicePayment", "core"), {}
        )
    assert error.value.code == "UPSTREAM_TIMEOUT"
    assert error.value.details["outcome"] == "unknown"
    assert len(calls) == 1


def test_upstream_auth_error_is_not_success():
    client = PishkhanClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"Status": {"Code": "G00002", "Description": "Session expired"}, "Parameters": None}
            )
        )
    )
    with pytest.raises(PishkhanError) as error:
        client.call(find_action("ConfigBasic", "core"), {})
    assert error.value.code == "AUTH_REQUIRED"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(502, text="bad gateway"),
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json=[1, 2]),
    ],
)
def test_invalid_upstream_response_keeps_outcome_unknown(response):
    client = PishkhanClient(transport=httpx.MockTransport(lambda request: response))
    with pytest.raises(PishkhanError) as error:
        client.call(find_action("ConfigBasic", "core"), {})
    assert error.value.details["outcome"] == "unknown"


def test_password_wire_transform_and_redaction():
    assert password_digest("password") == "5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8"
    assert (
        password_digest("line1\r\nline2") == hashlib.sha1(b"line1\nline2", usedforsecurity=False).hexdigest()
    )
    assert password_digest("رمز") == hashlib.sha1("رمز".encode(), usedforsecurity=False).hexdigest()
    result = redact({"Password": "secret", "OTPCode": "12345", "child": [{"Token": "t", "Amount": 10}]})
    assert "secret" not in json.dumps(result)
    assert result["child"][0]["Amount"] == 10


def test_registry_has_unique_valid_contracts_and_invoice_nested_json_string():
    items = registry()["actions"]
    assert len(items) >= 150
    assert len({item["id"] for item in items}) == len(items)
    for item in items:
        Draft202012Validator.check_schema(item["parameters_schema"])
        assert item["status"] == "source_verified"
        evidence = item["evidence"]
        assert evidence["kind"] in {"public_javascript", "company_source"}
        assert len(evidence["sha256"]) == 64
        assert evidence["source"].startswith(("https://pishkhan24.com/", "core-main/Core/"))
    action = find_action("InvoiceRegister", "services")
    validate_parameters(
        action, {"Service": "v1_InquiryElectricBills", "Parameters": '{"Identifier":"00012"}'}
    )
    with pytest.raises(PishkhanError):
        validate_parameters(
            action, {"Service": "v1_InquiryElectricBills", "Parameters": {"Identifier": "00012"}}
        )
