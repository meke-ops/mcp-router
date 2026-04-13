import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    tenant_id: str
    principal_id: str
    created_at: datetime
    expires_at: datetime
    upstream_sessions: dict[str, str] = field(default_factory=dict)


class InMemorySessionManager:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> SessionRecord | None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.expires_at <= datetime.now(UTC):
                self._sessions.pop(session_id, None)
                return None
            return session

    async def get_or_create(
        self,
        session_id: str | None,
        tenant_id: str,
        principal_id: str,
    ) -> SessionRecord:
        if session_id:
            existing = await self.get(session_id)
            if existing is not None:
                self._assert_context(existing, tenant_id=tenant_id, principal_id=principal_id)
                return await self.touch(session_id)

        async with self._lock:
            now = datetime.now(UTC)
            new_session = SessionRecord(
                session_id=str(uuid4()),
                tenant_id=tenant_id,
                principal_id=principal_id,
                created_at=now,
                expires_at=now + self._ttl,
            )
            self._sessions[new_session.session_id] = new_session
            return new_session

    async def touch(self, session_id: str) -> SessionRecord:
        async with self._lock:
            session = self._sessions[session_id]
            session.expires_at = datetime.now(UTC) + self._ttl
            return session

    async def set_upstream_session(
        self,
        session_id: str,
        server_id: str,
        upstream_session_id: str,
    ) -> None:
        async with self._lock:
            session = self._sessions[session_id]
            session.upstream_sessions[server_id] = upstream_session_id

    async def get_upstream_session(
        self,
        session_id: str,
        server_id: str,
    ) -> str | None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.expires_at <= datetime.now(UTC):
                self._sessions.pop(session_id, None)
                return None
            return session.upstream_sessions.get(server_id)

    def _assert_context(
        self,
        session: SessionRecord,
        tenant_id: str,
        principal_id: str,
    ) -> None:
        if session.tenant_id != tenant_id or session.principal_id != principal_id:
            raise ValueError(
                "Session context mismatch."
            )
