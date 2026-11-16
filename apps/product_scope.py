"""Product-owner scope, separate from the shared backend's source snapshots."""

EXCLUDED_SERVICES = frozenset({"taxipay"})
EXCLUDED_ENDPOINTS = frozenset({"MunicipalityTaxiFaresBills", "MunicipalityTaxiFaresBillsBarcodeInfo"})
EXCLUDED_SERVICE_NAMES = frozenset({"v1_InquiryMunicipalityTaxiFaresBills"})
SCOPE_NOTE = "Shared-backend code presence is not product availability. Taxi is excluded by the product owner; verify ConfigService.Active for live inquiry services."
