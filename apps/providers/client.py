"""Pishkhan JSON-envelope transport, with no automatic POST retries."""

import hashlib
import re

import httpx
from django.conf import settings

from apps.core.errors import PishkhanError

SENSITIVE_KEYS = {
    "encryptdata",
    "pin",
    "cvv2",
    "pan",
    "cardnumber",
    "password",
    "otpcode",
    "otp",
    "token",
    "session",
    "authorization",
    "access_token",
    "refresh_token",
}


def redact(value):
    if isinstance(value, dict):
        return {k: "[redacted]" if k.casefold() in SENSITIVE_KEYS else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def password_digest(password):
    """Match the public frontend's SHA-1 + legacy JS UTF-8 credential transform.

    This is an upstream wire requirement, not a password-storage algorithm.
    Non-BMP characters are encoded per UTF-16 code unit, as in the observed JS.
    """
    normalized = password.replace("\r\n", "\n")
    utf16 = normalized.encode("utf-16-be", errors="surrogatepass")
    units = "".join(chr(int.from_bytes(utf16[i : i + 2], "big")) for i in range(0, len(utf16), 2))
    return hashlib.sha1(units.encode("utf-8", errors="surrogatepass"), usedforsecurity=False).hexdigest()


class PishkhanClient:
    def __init__(self, *, transport=None):
        self.transport = transport

    def call(self, action, parameters, token=""):
        group, path = action["group"], action["path"].lstrip("/")
        if group not in {"core", "services", "public"} or not re.fullmatch(r"[A-Za-z0-9_/-]+", path):
            raise PishkhanError("INVALID_CONTRACT", "Invalid registry endpoint.")
        url = f"{settings.P24_API_BASE_URL}/{group}.svc/{path}"
        body = {"Identity": {"Token": token or ""}, "Parameters": parameters}
        try:
            with httpx.Client(
                timeout=settings.P24_API_TIMEOUT, transport=self.transport, follow_redirects=False
            ) as client:
                response = client.post(
                    url,
                    json=body,
                    headers={
                        "Accept": "application/json",
                        "Origin": "https://pishkhan24.com",
                        "Referer": "https://pishkhan24.com/",
                        "User-Agent": "PishkhanMCP/0.1 (+https://github.com/mohamadrezavilani/PishkhanMCP)",
                    },
                )
        except httpx.TimeoutException as exc:
            raise PishkhanError(
                "UPSTREAM_TIMEOUT",
                "پاسخ نهایی دریافت نشد؛ پیش از تکرار، وضعیت عملیات را بررسی کنید.",
                details={"outcome": "unknown"},
            ) from exc
        except httpx.RequestError as exc:
            raise PishkhanError(
                "UPSTREAM_CONNECTION", "ارتباط با پیشخوان کامل نشد.", details={"outcome": "unknown"}
            ) from exc
        if response.status_code >= 400 or response.is_redirect:
            raise PishkhanError(
                "UPSTREAM_HTTP",
                "پیشخوان پاسخ HTTP ناموفق داد.",
                details={"http_status": response.status_code, "outcome": "unknown"},
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise PishkhanError(
                "UPSTREAM_FORMAT", "پاسخ پیشخوان JSON معتبر نیست.", details={"outcome": "unknown"}
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("Status"), dict):
            raise PishkhanError(
                "UPSTREAM_FORMAT",
                "ساختار پاسخ پیشخوان با قرارداد مشاهده‌شده متفاوت است.",
                details={"outcome": "unknown"},
            )
        status = payload["Status"]
        code = str(status.get("Code", "")).lower()
        if code != "g00000":
            raise PishkhanError(
                "AUTH_REQUIRED" if code == "g00002" else "UPSTREAM_REJECTED",
                str(status.get("Description") or "پیشخوان درخواست را نپذیرفت."),
                details={"upstream_code": status.get("Code"), "upstream_type": status.get("Type")},
            )
        parameters = payload.get("Parameters")
        result = {"status": status, "parameters": {} if parameters is None else parameters}
        upstream_id = payload.get("RequestID") or response.headers.get("RequestID")
        if isinstance(upstream_id, str) and upstream_id:
            result["upstream_request_id"] = upstream_id
        return result
