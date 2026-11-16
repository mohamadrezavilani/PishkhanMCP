"""Explicit, deterministic demonstration fixtures. Never contacts a provider."""

from apps.core.errors import PishkhanError

DEMO_OTP = "123456"
DEMO_SERVICES = {"freeway", "electricity", "water", "posttracking"}


def inquiry(service_id, parameters):
    if service_id == "freeway":
        return {
            "plate": parameters["plate"],
            "total_amount": 420000,
            "currency": "IRR",
            "items": [{"route": "مسیر آزمایشی", "amount": 420000}],
            "notice": "این بدهی ساختگی است و هیچ استعلامی از پیشخوان انجام نشده است.",
        }
    if service_id in {"electricity", "water"}:
        return {
            "bill_id": parameters["bill_id"],
            "payment_id": "000000000001",
            "amount": 1250000,
            "currency": "IRR",
            "bill_status": "unpaid",
            "notice": "قبض نمایشی؛ قابل پرداخت واقعی نیست.",
        }
    if service_id == "posttracking":
        return {
            "tracking_code": parameters["tracking_code"],
            "delivery_status": "in_transit",
            "events": [{"location": "مرکز آزمایشی", "description": "مرسولهٔ نمایشی در حال ارسال است"}],
            "notice": "رویدادها ساختگی هستند؛ مرسولهٔ واقعی رهگیری نشده است.",
        }
    raise PishkhanError(
        "DEMO_SERVICE_UNSUPPORTED",
        "این خدمت در حالت نمایشی شبیه‌سازی نشده است.",
        details={"demo_services": sorted(DEMO_SERVICES)},
    )
