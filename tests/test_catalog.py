"""Catalog invariants and distinctions that affect execution and user charges."""

import unittest
from urllib.parse import urlsplit

from apps.catalog.catalog import (
    UnknownServiceError,
    catalog_page,
    get_service,
    list_categories,
    list_services,
    service_requirements,
)


class CatalogTests(unittest.TestCase):
    def test_full_inventory_is_unique_and_uses_official_sources(self):
        services = list_services()
        self.assertEqual(len(services), 55)
        self.assertEqual(len({item["id"] for item in services}), 55)
        for item in services:
            self.assertEqual(urlsplit(item["source_url"]).hostname, "pishkhan24.com")
            self.assertEqual(item["id"], urlsplit(item["source_url"]).path.strip("/"))
            self.assertFalse(item["api_contract_verified"])

    def test_category_counts_match_public_inventory(self):
        self.assertEqual(
            {item["id"]: item["count"] for item in list_categories()},
            {
                "social_insurance": 18,
                "bills": 9,
                "vehicles": 15,
                "mobile": 3,
                "banking": 4,
                "postal": 4,
                "judicial": 2,
            },
        )
        self.assertEqual(list_services("postal"), list_services("پستی"))

    def test_paid_parcel_is_not_advertised_as_free_read(self):
        service = get_service("posttracking")
        self.assertEqual(service["cost_mode"], "paid")
        self.assertIn("quote", service["workflow_actions"])
        self.assertIn("tracking_code", service["input_schema"]["properties"])

    def test_toll_free_claim_applies_only_to_summary(self):
        service = get_service("freeway")
        self.assertEqual(service["cost_mode"], "free")
        self.assertEqual(service["cost_scope"], "summary_inquiry_only")
        variants = {item["id"]: item for item in service["variants"]}
        self.assertEqual(variants["summary"]["cost_mode"], "free")
        self.assertEqual(variants["details"]["cost_mode"], "unknown")
        self.assertEqual(variants["payment"]["cost_mode"], "paid")

    def test_catalog_does_not_create_capabilities_absent_from_product(self):
        self.assertNotIn("purchase", get_service("crypto")["workflow_actions"])
        self.assertNotIn("payment", get_service("bank-loans")["workflow_actions"])
        self.assertNotIn("grant_consent", get_service("exit-consent")["workflow_actions"])
        self.assertNotIn("issue_certificate", get_service("reputation-check")["workflow_actions"])

    def test_unknown_form_fields_are_not_invented(self):
        requirements = service_requirements("passport")
        self.assertEqual(requirements["requirements_status"], "unknown")
        self.assertEqual(requirements["input_schema"]["properties"], {})
        self.assertFalse(requirements["api_contract_verified"])
        self.assertEqual(requirements["capability_status"], "catalogued_requires_adapter")

    def test_form_and_prose_disagreement_is_preserved(self):
        self.assertEqual(service_requirements("subsidy")["requirements_status"], "ambiguous")
        self.assertEqual(service_requirements("transaction-check")["requirements_status"], "ambiguous")

    def test_search_normalizes_arabic_persian_characters(self):
        self.assertEqual(
            [item["id"] for item in list_services(query="كارت ملي")],
            ["national-id-card"],
        )
        self.assertEqual([item["id"] for item in list_services(query="electricity")], ["electricity"])

    def test_pagination_can_visit_all_entries_without_duplicates(self):
        seen = []
        offset = 0
        while offset is not None:
            page = catalog_page(offset=offset, limit=7)
            self.assertEqual(page["total"], 55)
            self.assertLessEqual(page["count"], 7)
            seen.extend(item["id"] for item in page["items"])
            offset = page["next_offset"]
        self.assertEqual(len(seen), 55)
        self.assertEqual(len(set(seen)), 55)
        with self.assertRaises(ValueError):
            catalog_page(limit=0)
        with self.assertRaises(ValueError):
            catalog_page(offset=-1)

    def test_caller_mutations_do_not_change_shared_catalog(self):
        service = get_service("electricity")
        service["input_schema"]["properties"].clear()
        self.assertIn("bill_id", get_service("electricity")["input_schema"]["properties"])
        with self.assertRaises(UnknownServiceError):
            get_service("not-a-service")


if __name__ == "__main__":
    unittest.main()
