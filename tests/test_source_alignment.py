import json
from pathlib import Path

from django.conf import settings


def test_default_api_host_matches_company_source_and_har():
    assert settings.P24_API_BASE_URL == "https://core.pishkhan24.ayantech.ir/webservices"


def test_taxi_fare_source_actions_are_registered():
    path = Path("apps/providers/data/pishkhan_actions.json")
    registry = json.loads(path.read_text(encoding="utf-8"))
    actions = {item["id"]: item for item in registry["actions"]}
    info = actions["services_municipality_taxi_fares_barcode_info_v1"]
    assert info["path"] == "v1/MunicipalityTaxiFaresBillsBarcodeInfo"
    assert info["parameters_schema"]["required"] == ["Barcode"]
    payment = actions["services_municipality_taxi_fares_bills_v1"]
    assert payment["path"] == "v1/MunicipalityTaxiFaresBills"
    assert payment["parameters_schema"]["required"] == ["Barcode", "Amount", "PurchaseKey"]
