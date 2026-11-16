from apps.catalog.catalog import list_services
from apps.providers.registry import registry


def test_taxi_is_not_part_of_the_product_scope():
    assert "taxipay" not in {s["id"] for s in list_services()}
    assert not any("taxi" in a["path"].lower() for a in registry()["actions"])


def test_default_url_is_documented_without_overriding_environment():
    assert registry()["upstream_base_url"] == "https://core.pishkhan24.ayantech.ir/webservices/"
