"""Read-only HTTP check of the LAN page; never calls Claude/Core or sends OTP."""

import json
from urllib.parse import urlsplit

import httpx
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Check the consumer portal over HTTP without a model, OTP or payment."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default="http://127.0.0.1:8000")

    def handle(self, *args, **options):
        base = options["base_url"].rstrip("/")
        if urlsplit(base).scheme not in {"http", "https"} or not urlsplit(base).netloc:
            raise CommandError("A valid http(s) --base-url is required")
        checks = []
        try:
            with httpx.Client(base_url=base, trust_env=False, timeout=15) as client:
                health = client.get("/health/")
                health.raise_for_status()
                checks.append("http_health")
                home = client.get("/")
                home.raise_for_status()
                if 'id="chat-form"' not in home.text or 'id="session-id"' in home.text:
                    raise CommandError("The consumer portal is not installed at /")
                checks.append("consumer_page_not_console")
                for name in ("pilot.css", "pilot.js"):
                    client.get("/portal-assets/" + name).raise_for_status()
                    checks.append(name)
                state = client.get("/api/portal/state/")
                state.raise_for_status()
                if state.json()["authenticated"]:
                    raise CommandError("A fresh browser unexpectedly inherited a logged-in account")
                checks.append("fresh_browser_has_no_account")
                if not client.cookies.get("csrftoken"):
                    raise CommandError("CSRF bootstrap cookie missing")
                checks.append("csrf_bootstrap")
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise CommandError(f"Portal HTTP check failed: {type(exc).__name__}") from exc
        self.stdout.write(
            json.dumps(
                {
                    "ok": True,
                    "mode": health.json()["mode"],
                    "checks": checks,
                    "model_calls": 0,
                    "real_otp_sent": False,
                    "real_payment_attempted": False,
                },
                indent=2,
            )
        )
