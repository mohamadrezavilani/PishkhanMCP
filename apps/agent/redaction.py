"""Remove credential values from persisted transcripts without disabling login.

Current-turn credentials may be passed to the selected model and authentication
tool. Persisted conversation messages and the public trace omit recognized
credential fields. This is not a general personal-data classifier.
"""

from __future__ import annotations

import json
import re
from typing import Any

REDACTED = "[REDACTED]"
_SECRET_KEYS = {
    "password",
    "passwd",
    "pwd",
    "otp",
    "otpcode",
    "demootp",
    "verificationcode",
    "smscode",
    "smstoken",
    "accesstoken",
    "refreshtoken",
    "token",
    "authorization",
    "apikey",
    "accesskey",
    "cookie",
    "sessiontoken",
    "رمز",
    "رمزعبور",
    "کدتایید",
    "کدتأیید",
}
_LABELLED_SECRET = re.compile(
    r"(?i)((?:password|passwd|otp|رمز\s*عبور|رمز\s*یکبارمصرف|کد\s*ت[اأ]یید)\s*[:=]\s*)([^\s,،]+)"
)


def _is_secret_key(key: str) -> bool:
    return re.sub(r"[\s_-]+", "", key).casefold() in _SECRET_KEYS


def _json_value(value: str) -> Any | None:
    if value.lstrip().startswith(("{", "[")):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            pass
    return None


def collect_secrets(value: Any) -> set[str]:
    secrets: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if _is_secret_key(str(key)) and isinstance(item, (str, int)) and str(item):
                secrets.add(str(item))
            secrets.update(collect_secrets(item))
    elif isinstance(value, list):
        for item in value:
            secrets.update(collect_secrets(item))
    elif isinstance(value, str):
        parsed = _json_value(value)
        if parsed is not None:
            secrets.update(collect_secrets(parsed))
        secrets.update(match.group(2) for match in _LABELLED_SECRET.finditer(value))
    secrets.discard(REDACTED)
    return secrets


def redact(value: Any, known_secrets: set[str] | None = None) -> Any:
    """Preserve tool-call structure while replacing known credential values."""
    secrets = known_secrets if known_secrets is not None else collect_secrets(value)
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_secret_key(str(key)) else redact(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        parsed = _json_value(value)
        if parsed is not None:
            return json.dumps(redact(parsed, secrets), ensure_ascii=False)
        text = _LABELLED_SECRET.sub(lambda match: match.group(1) + REDACTED, value)
        for secret in sorted(secrets, key=len, reverse=True):
            if len(secret) >= 3:
                text = text.replace(secret, REDACTED)
        return text
    return value
