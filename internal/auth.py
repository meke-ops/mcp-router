import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from internal.config import Settings
from internal.redaction import hash_token


class AuthenticationError(Exception):
    def __init__(self, message: str, *, status_code: int = 401) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(slots=True, frozen=True)
class AuthenticatedPrincipal:
    subject: str
    tenant_ids: tuple[str, ...]
    roles: tuple[str, ...]
    token_hash: str
    claims: dict[str, Any]


class JwtAuthenticator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def authenticate_bearer_token(
        self,
        authorization_header: str | None,
    ) -> AuthenticatedPrincipal:
        if not self._settings.auth_enabled:
            raise AuthenticationError("Authentication is not enabled.", status_code=500)
        if not self._settings.jwt_secret:
            raise AuthenticationError("JWT secret is not configured.", status_code=500)
        if authorization_header is None:
            raise AuthenticationError("Authorization header is required.")
        scheme, _, token = authorization_header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise AuthenticationError("Authorization header must use Bearer token.")

        segments = token.split(".")
        if len(segments) != 3:
            raise AuthenticationError(
                "JWT must include header, payload, and signature segments."
            )
        header_segment, payload_segment, signature_segment = segments
        header = self._decode_segment(header_segment)
        payload = self._decode_segment(payload_segment)
        signature = self._decode_bytes(signature_segment)

        if header.get("alg") != "HS256":
            raise AuthenticationError("JWT alg must be HS256.")

        signed_portion = f"{header_segment}.{payload_segment}".encode("utf-8")
        expected_signature = hmac.new(
            self._settings.jwt_secret.encode("utf-8"),
            signed_portion,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(signature, expected_signature):
            raise AuthenticationError("JWT signature validation failed.")

        self._validate_standard_claims(payload)
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationError("JWT sub claim must be a non-empty string.")

        tenant_ids = self._extract_tenant_ids(payload)
        roles = self._extract_roles(payload)
        return AuthenticatedPrincipal(
            subject=subject,
            tenant_ids=tenant_ids,
            roles=roles,
            token_hash=hash_token(token),
            claims=payload,
        )

    def _validate_standard_claims(self, payload: dict[str, Any]) -> None:
        now = time.time()
        skew = float(self._settings.jwt_clock_skew_seconds)

        exp = payload.get("exp")
        if exp is None or not isinstance(exp, (int, float)):
            raise AuthenticationError("JWT exp claim must be present.")
        if now - skew >= float(exp):
            raise AuthenticationError("JWT has expired.")

        nbf = payload.get("nbf")
        if nbf is not None:
            if not isinstance(nbf, (int, float)):
                raise AuthenticationError("JWT nbf claim must be numeric.")
            if now + skew < float(nbf):
                raise AuthenticationError("JWT is not active yet.")

        if self._settings.jwt_issuer is not None:
            if payload.get("iss") != self._settings.jwt_issuer:
                raise AuthenticationError("JWT issuer validation failed.")

        if self._settings.jwt_audience is not None:
            aud = payload.get("aud")
            valid = False
            if isinstance(aud, str):
                valid = aud == self._settings.jwt_audience
            elif isinstance(aud, list):
                valid = self._settings.jwt_audience in aud
            if not valid:
                raise AuthenticationError("JWT audience validation failed.")

    def _extract_tenant_ids(self, payload: dict[str, Any]) -> tuple[str, ...]:
        if isinstance(payload.get("tenant_ids"), list):
            tenant_ids = tuple(
                str(item) for item in payload["tenant_ids"] if isinstance(item, str)
            )
        elif isinstance(payload.get("tenant_id"), str):
            tenant_ids = (payload["tenant_id"],)
        else:
            tenant_ids = ()
        if not tenant_ids:
            raise AuthenticationError("JWT must include tenant_id or tenant_ids claim.")
        return tenant_ids

    def _extract_roles(self, payload: dict[str, Any]) -> tuple[str, ...]:
        roles = payload.get("roles", [])
        if isinstance(roles, list):
            return tuple(str(role) for role in roles if isinstance(role, str))
        return ()

    def _decode_segment(self, value: str) -> dict[str, Any]:
        decoded = self._decode_bytes(value)
        try:
            payload = json.loads(decoded.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise AuthenticationError("JWT payload is not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise AuthenticationError("JWT payload must be an object.")
        return payload

    def _decode_bytes(self, value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        try:
            return base64.urlsafe_b64decode(value + padding)
        except (ValueError, base64.binascii.Error) as exc:
            raise AuthenticationError("JWT is not valid base64url.") from exc
