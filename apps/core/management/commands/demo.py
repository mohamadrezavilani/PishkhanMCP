import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.tools import call_tool


class Command(BaseCommand):
    help = "Run the three deterministic demo journeys without contacting Pishkhan."

    def handle(self, *args, **options):
        if settings.P24_MODE != "demo":
            raise CommandError("This command only runs with P24_MODE=demo.")
        results = []

        def call(name, arguments):
            result = call_tool(name, arguments)
            if not result.get("ok"):
                raise CommandError(json.dumps(result, ensure_ascii=False))
            results.append({"tool": name, "result": result})
            return result

        session = call("p24_create_session", {})["session_id"]
        common = {"session_id": session}
        call("p24_request_otp", {**common, "phone": "09120000000", "idempotency_key": "demo-otp"})
        call(
            "p24_verify_otp",
            {**common, "phone": "09120000000", "otp": "123456", "idempotency_key": "demo-verify"},
        )
        call("p24_toll_summary", {**common, "plate": "12ب34567", "idempotency_key": "demo-toll"})
        call(
            "p24_electricity_bill",
            {**common, "bill_id": "0001234567890", "idempotency_key": "demo-electricity"},
        )
        payment = call(
            "p24_prepare_bill_payment",
            {**common, "bill_ids": ["DEMO-BILL"], "gateway": "demo", "idempotency_key": "demo-payment"},
        )
        call("p24_demo_complete_payment", {**common, "operation_id": payment["operation_id"]})
        call("p24_get_receipt", {**common, "operation_id": payment["operation_id"]})
        quote = call(
            "p24_quote_parcel_inquiry",
            {**common, "tracking_code": "000000000000000000000001", "idempotency_key": "demo-parcel-quote"},
        )
        call(
            "p24_run_parcel_inquiry",
            {**common, "quote_id": quote["result"]["quote_id"], "idempotency_key": "demo-parcel-run"},
        )
        self.stdout.write(
            json.dumps(
                {"ok": True, "mode": "demo", "session_id": session, "real_requests": 0, "journeys": results},
                ensure_ascii=False,
                indent=2,
            )
        )
