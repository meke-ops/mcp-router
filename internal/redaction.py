from collections.abc import Mapping, Sequence
import hashlib
import re
from typing import Any


EMAIL_PATTERN = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
JWT_LIKE_PATTERN = re.compile(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE)


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, Mapping):
        return {key: redact_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [redact_value(item) for item in value]
    return value


def redact_identifier(value: str) -> str:
    return _redact_string(value)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _redact_string(value: str) -> str:
    redacted = EMAIL_PATTERN.sub(_replace_email, value)
    redacted = JWT_LIKE_PATTERN.sub(_replace_token, redacted)
    redacted = BEARER_PATTERN.sub(_replace_bearer, redacted)
    return redacted


def _replace_email(match: re.Match[str]) -> str:
    local_part = match.group(1)
    domain = match.group(2)
    if len(local_part) <= 1:
        return f"***@{domain}"
    return f"{local_part[0]}***@{domain}"


def _replace_token(match: re.Match[str]) -> str:
    token = match.group(0)
    return f"[redacted-token:{hash_token(token)[:12]}]"


def _replace_bearer(match: re.Match[str]) -> str:
    token = match.group(0).split(maxsplit=1)[1]
    return f"Bearer [redacted-token:{hash_token(token)[:12]}]"
