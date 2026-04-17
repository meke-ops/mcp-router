from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import tomllib
from typing import Any

from internal.context import RequestIdentity, RouterRequestContext
from internal.mcp.models import JsonRpcRequest
from internal.mcp.service import MCPRouterService
from internal.registry import InMemoryToolRegistry, UpstreamServerDefinition
from internal.state_store import RouterStateStore
from internal.config import Settings


@dataclass(slots=True, frozen=True)
class ClientInstallTarget:
    client_id: str
    label: str
    scope: str
    path: str
    exists: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "clientId": self.client_id,
            "label": self.label,
            "scope": self.scope,
            "path": self.path,
            "exists": self.exists,
        }


@dataclass(slots=True, frozen=True)
class ClientPreview:
    client_id: str
    label: str
    scope: str
    server_name: str
    config_path: str
    install_command: str | None
    merged_config_text: str
    auth_mode: str
    mcp_url: str
    applied: bool = False
    backup_path: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "clientId": self.client_id,
            "label": self.label,
            "scope": self.scope,
            "serverName": self.server_name,
            "configPath": self.config_path,
            "installCommand": self.install_command,
            "mergedConfigText": self.merged_config_text,
            "authMode": self.auth_mode,
            "mcpUrl": self.mcp_url,
            "applied": self.applied,
            "backupPath": self.backup_path,
        }


@dataclass(slots=True, frozen=True)
class DetectedServerCandidate:
    candidate_id: str
    source_client: str
    source_label: str
    scope: str
    config_path: str
    server_name: str
    transport: str
    summary: str
    env_keys: tuple[str, ...]
    importable: bool
    import_reason: str | None
    normalized_upstream: UpstreamServerDefinition | None

    def to_payload(self) -> dict[str, object]:
        return {
            "candidateId": self.candidate_id,
            "sourceClient": self.source_client,
            "sourceLabel": self.source_label,
            "scope": self.scope,
            "configPath": self.config_path,
            "serverName": self.server_name,
            "transport": self.transport,
            "summary": self.summary,
            "envKeys": list(self.env_keys),
            "importable": self.importable,
            "importReason": self.import_reason,
            "normalizedUpstream": (
                self.normalized_upstream.to_record()
                if self.normalized_upstream is not None
                else None
            ),
        }


@dataclass(slots=True, frozen=True)
class ImportResult:
    imported_count: int
    updated_count: int
    refreshed: bool
    tool_count: int
    server_ids: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "importedCount": self.imported_count,
            "updatedCount": self.updated_count,
            "refreshed": self.refreshed,
            "toolCount": self.tool_count,
            "serverIds": list(self.server_ids),
        }


@dataclass(slots=True, frozen=True)
class SetupVerificationResult:
    session_id: str | None
    tool_count: int
    auth_mode: str
    identity: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return {
            "sessionId": self.session_id,
            "toolCount": self.tool_count,
            "authMode": self.auth_mode,
            "identity": self.identity,
        }


class SetupService:
    def __init__(
        self,
        *,
        settings: Settings,
        state_store: RouterStateStore,
        tool_registry: InMemoryToolRegistry,
        mcp_service: MCPRouterService,
    ) -> None:
        self._settings = settings
        self._state_store = state_store
        self._tool_registry = tool_registry
        self._mcp_service = mcp_service

    def list_clients(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for client_id, label in (
            ("claude_code", "Claude Code"),
            ("cursor", "Cursor"),
            ("codex", "Codex"),
            ("opencode", "OpenCode"),
        ):
            targets = [
                target.to_payload()
                for target in self._client_install_targets(client_id)
            ]
            items.append(
                {
                    "clientId": client_id,
                    "label": label,
                    "targets": targets,
                }
            )
        return items

    def preview_client(
        self,
        *,
        client_id: str,
        scope: str,
        mcp_url: str,
        token: str | None,
        config_path: str | None = None,
        server_name: str = "mcp-router",
    ) -> ClientPreview:
        resolved_path = Path(config_path).expanduser() if config_path else self._default_client_path(
            client_id,
            scope,
        )
        auth_mode = "bearer" if token else "none"
        if client_id == "claude_code":
            merged_config_text = self._build_claude_or_cursor_config(
                path=resolved_path,
                server_name=server_name,
                mcp_url=mcp_url,
                token=token,
            )
            install_command = (
                f'claude mcp add --transport http {server_name} --scope {scope} "{mcp_url}"'
            )
        elif client_id == "cursor":
            merged_config_text = self._build_claude_or_cursor_config(
                path=resolved_path,
                server_name=server_name,
                mcp_url=mcp_url,
                token=token,
            )
            install_command = None
        elif client_id == "opencode":
            merged_config_text = self._build_opencode_config(
                path=resolved_path,
                server_name=server_name,
                mcp_url=mcp_url,
                token=token,
            )
            install_command = None
        elif client_id == "codex":
            merged_config_text = self._build_codex_config(
                path=resolved_path,
                server_name=server_name,
                mcp_url=mcp_url,
                token=token,
            )
            install_command = f'codex mcp add {server_name} --url "{mcp_url}"'
        else:
            raise ValueError(f"Unsupported client: {client_id}")
        return ClientPreview(
            client_id=client_id,
            label=_client_label(client_id),
            scope=scope,
            server_name=server_name,
            config_path=str(resolved_path),
            install_command=install_command,
            merged_config_text=merged_config_text,
            auth_mode=auth_mode,
            mcp_url=mcp_url,
        )

    def apply_client_preview(self, preview: ClientPreview) -> ClientPreview:
        path = Path(preview.config_path).expanduser()
        backup_path: str | None = None
        if path.exists():
            timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            backup = path.with_name(f"{path.name}.bak-{timestamp}")
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            backup_path = str(backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(preview.merged_config_text, encoding="utf-8")
        return ClientPreview(
            client_id=preview.client_id,
            label=preview.label,
            scope=preview.scope,
            server_name=preview.server_name,
            config_path=preview.config_path,
            install_command=preview.install_command,
            merged_config_text=preview.merged_config_text,
            auth_mode=preview.auth_mode,
            mcp_url=preview.mcp_url,
            applied=True,
            backup_path=backup_path,
        )

    def discover_candidates(self) -> list[DetectedServerCandidate]:
        candidates: list[DetectedServerCandidate] = []
        seen_ids: set[str] = set()
        for path_info in self._discovery_paths():
            path = path_info["path"]
            if not path.exists():
                continue
            if path_info["client_id"] == "codex":
                parsed = self._discover_codex(path, path_info["scope"])
            elif path_info["client_id"] == "opencode":
                parsed = self._discover_opencode(path, path_info["scope"])
            else:
                parsed = self._discover_json_mcp(
                    path,
                    path_info["client_id"],
                    path_info["scope"],
                )
            for candidate in parsed:
                if candidate.candidate_id in seen_ids:
                    continue
                seen_ids.add(candidate.candidate_id)
                candidates.append(candidate)
        return candidates

    async def import_candidates(
        self,
        *,
        candidate_ids: list[str],
        refresh: bool,
        request_context: RouterRequestContext,
    ) -> ImportResult:
        candidates_by_id = {
            candidate.candidate_id: candidate for candidate in self.discover_candidates()
        }
        imported_count = 0
        updated_count = 0
        server_ids: list[str] = []
        for candidate_id in candidate_ids:
            candidate = candidates_by_id.get(candidate_id)
            if candidate is None or candidate.normalized_upstream is None:
                continue
            existing = await self._tool_registry.find_upstream_by_signature(
                candidate.normalized_upstream.normalized_signature()
            )
            if existing is not None:
                upstream = UpstreamServerDefinition(
                    server_id=existing.server_id,
                    transport=candidate.normalized_upstream.transport,
                    url=candidate.normalized_upstream.url,
                    command=candidate.normalized_upstream.command,
                    args=candidate.normalized_upstream.args,
                    env=candidate.normalized_upstream.env,
                    headers=candidate.normalized_upstream.headers,
                    timeout_seconds=candidate.normalized_upstream.timeout_seconds,
                    discover_tools=candidate.normalized_upstream.discover_tools,
                    fallback_server_ids=candidate.normalized_upstream.fallback_server_ids,
                    retry_attempts=candidate.normalized_upstream.retry_attempts,
                    circuit_breaker_failure_threshold=(
                        candidate.normalized_upstream.circuit_breaker_failure_threshold
                    ),
                    circuit_breaker_recovery_seconds=(
                        candidate.normalized_upstream.circuit_breaker_recovery_seconds
                    ),
                    origin_client=candidate.normalized_upstream.origin_client,
                    origin_path=candidate.normalized_upstream.origin_path,
                    managed_by="import",
                    last_imported_at=_now_iso(),
                )
                updated_count += 1
            else:
                upstream = UpstreamServerDefinition(
                    server_id=self._allocate_server_id(candidate),
                    transport=candidate.normalized_upstream.transport,
                    url=candidate.normalized_upstream.url,
                    command=candidate.normalized_upstream.command,
                    args=candidate.normalized_upstream.args,
                    env=candidate.normalized_upstream.env,
                    headers=candidate.normalized_upstream.headers,
                    timeout_seconds=candidate.normalized_upstream.timeout_seconds,
                    discover_tools=candidate.normalized_upstream.discover_tools,
                    fallback_server_ids=candidate.normalized_upstream.fallback_server_ids,
                    retry_attempts=candidate.normalized_upstream.retry_attempts,
                    circuit_breaker_failure_threshold=(
                        candidate.normalized_upstream.circuit_breaker_failure_threshold
                    ),
                    circuit_breaker_recovery_seconds=(
                        candidate.normalized_upstream.circuit_breaker_recovery_seconds
                    ),
                    origin_client=candidate.normalized_upstream.origin_client,
                    origin_path=candidate.normalized_upstream.origin_path,
                    managed_by="import",
                    last_imported_at=_now_iso(),
                )
                imported_count += 1
            await self._tool_registry.upsert_upstream_server(upstream)
            self._state_store.upsert_upstream(upstream)
            server_ids.append(upstream.server_id)
        tool_count = 0
        if refresh:
            tools = await self._mcp_service.refresh_registry(request_context)
            tool_count = len(tools)
        else:
            tool_count = len(await self._tool_registry.list_registered_tools())
        return ImportResult(
            imported_count=imported_count,
            updated_count=updated_count,
            refreshed=refresh,
            tool_count=tool_count,
            server_ids=tuple(server_ids),
        )

    async def verify_router(
        self,
        *,
        auth_mode: str,
        request_context: RouterRequestContext,
        identity: RequestIdentity,
    ) -> SetupVerificationResult:
        initialize_result = await self._mcp_service.handle_request(
            request=JsonRpcRequest(
                jsonrpc="2.0",
                id="setup-verify-init",
                method="initialize",
                params={},
            ),
            session_id=None,
            identity=identity,
            request_context=request_context,
        )
        tool_result = await self._mcp_service.handle_request(
            request=JsonRpcRequest(
                jsonrpc="2.0",
                id="setup-verify-tools",
                method="tools/list",
                params={},
            ),
            session_id=initialize_result.session_id,
            identity=identity,
            request_context=request_context,
        )
        tools = (tool_result.response.result or {}).get("tools", []) if tool_result.response else []
        return SetupVerificationResult(
            session_id=initialize_result.session_id,
            tool_count=len(tools) if isinstance(tools, list) else 0,
            auth_mode=auth_mode,
            identity={
                "tenantId": identity.tenant_id,
                "principalId": identity.principal_id,
                "roles": list(identity.roles),
            },
        )

    def _client_install_targets(self, client_id: str) -> list[ClientInstallTarget]:
        targets: list[ClientInstallTarget] = []
        if client_id in {"claude_code", "cursor"}:
            targets.append(
                ClientInstallTarget(
                    client_id=client_id,
                    label=_client_label(client_id),
                    scope="user",
                    path=str(self._default_client_path(client_id, "user")),
                    exists=self._default_client_path(client_id, "user").exists(),
                )
            )
            targets.append(
                ClientInstallTarget(
                    client_id=client_id,
                    label=_client_label(client_id),
                    scope="project",
                    path=str(self._default_client_path(client_id, "project")),
                    exists=self._default_client_path(client_id, "project").exists(),
                )
            )
        else:
            targets.append(
                ClientInstallTarget(
                    client_id=client_id,
                    label=_client_label(client_id),
                    scope="user",
                    path=str(self._default_client_path(client_id, "user")),
                    exists=self._default_client_path(client_id, "user").exists(),
                )
            )
        return targets

    def _default_client_path(self, client_id: str, scope: str) -> Path:
        workspace_root = self._settings.resolved_workspace_root()
        home = self._settings.resolved_home()
        if client_id == "claude_code":
            return home / ".claude.json" if scope == "user" else workspace_root / ".mcp.json"
        if client_id == "cursor":
            return home / ".cursor" / "mcp.json" if scope == "user" else workspace_root / ".cursor" / "mcp.json"
        if client_id == "codex":
            return home / ".codex" / "config.toml"
        if client_id == "opencode":
            return home / ".config" / "opencode" / "opencode.json"
        raise ValueError(f"Unsupported client: {client_id}")

    def _build_claude_or_cursor_config(
        self,
        *,
        path: Path,
        server_name: str,
        mcp_url: str,
        token: str | None,
    ) -> str:
        payload = _load_json_file(path)
        mcp_servers = payload.setdefault("mcpServers", {})
        server_payload: dict[str, object] = {"url": mcp_url}
        if token:
            server_payload["headers"] = {"Authorization": f"Bearer {token}"}
        mcp_servers[server_name] = server_payload
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"

    def _build_opencode_config(
        self,
        *,
        path: Path,
        server_name: str,
        mcp_url: str,
        token: str | None,
    ) -> str:
        payload = _load_jsonc_file(path)
        if "$schema" not in payload:
            payload["$schema"] = "https://opencode.ai/config.json"
        mcp = payload.setdefault("mcp", {})
        server_payload: dict[str, object] = {
            "type": "remote",
            "url": mcp_url,
            "enabled": True,
        }
        if token:
            server_payload["headers"] = {"Authorization": f"Bearer {token}"}
        mcp[server_name] = server_payload
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"

    def _build_codex_config(
        self,
        *,
        path: Path,
        server_name: str,
        mcp_url: str,
        token: str | None,
    ) -> str:
        existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
        base_text = _remove_codex_server_block(existing_text, server_name)
        snippet_lines = [
            f"[mcp_servers.{server_name}]",
            f'url = "{_toml_escape(mcp_url)}"',
        ]
        if token:
            snippet_lines.append(
                f'http_headers = {{ Authorization = "Bearer {_toml_escape(token)}" }}'
            )
        snippet = "\n".join(snippet_lines) + "\n"
        if base_text and not base_text.endswith("\n"):
            base_text += "\n"
        if base_text and not base_text.endswith("\n\n"):
            base_text += "\n"
        return f"{base_text}{snippet}"

    def _discovery_paths(self) -> list[dict[str, Path | str]]:
        workspace_root = self._settings.resolved_workspace_root()
        home = self._settings.resolved_home()
        return [
            {"client_id": "claude_code", "scope": "user", "path": home / ".claude.json"},
            {"client_id": "claude_code", "scope": "project", "path": workspace_root / ".mcp.json"},
            {"client_id": "cursor", "scope": "user", "path": home / ".cursor" / "mcp.json"},
            {"client_id": "cursor", "scope": "project", "path": workspace_root / ".cursor" / "mcp.json"},
            {"client_id": "codex", "scope": "user", "path": home / ".codex" / "config.toml"},
            {"client_id": "opencode", "scope": "user", "path": home / ".config" / "opencode" / "opencode.json"},
            {"client_id": "opencode", "scope": "project", "path": workspace_root / "opencode.json"},
            {"client_id": "opencode", "scope": "project", "path": workspace_root / "opencode.jsonc"},
        ]

    def _discover_json_mcp(
        self,
        path: Path,
        client_id: str,
        scope: str,
    ) -> list[DetectedServerCandidate]:
        payload = _load_json_file(path)
        servers = payload.get("mcpServers", {})
        if not isinstance(servers, dict):
            return []
        candidates: list[DetectedServerCandidate] = []
        for server_name, raw_server in servers.items():
            if not isinstance(raw_server, dict):
                continue
            candidates.append(
                self._candidate_from_json_server(
                    client_id=client_id,
                    scope=scope,
                    path=path,
                    server_name=server_name,
                    raw_server=raw_server,
                )
            )
        return candidates

    def _discover_opencode(self, path: Path, scope: str) -> list[DetectedServerCandidate]:
        payload = _load_jsonc_file(path)
        servers = payload.get("mcp", {})
        if not isinstance(servers, dict):
            return []
        candidates: list[DetectedServerCandidate] = []
        for server_name, raw_server in servers.items():
            if not isinstance(raw_server, dict):
                continue
            server_type = raw_server.get("type")
            if server_type == "remote":
                raw = {
                    "url": raw_server.get("url"),
                    "headers": raw_server.get("headers", {}),
                }
            else:
                command = raw_server.get("command", [])
                if isinstance(command, list) and command:
                    raw = {
                        "command": command[0],
                        "args": command[1:],
                        "env": raw_server.get("environment", {}),
                    }
                else:
                    raw = {
                        "command": None,
                        "args": [],
                        "env": raw_server.get("environment", {}),
                    }
            candidates.append(
                self._candidate_from_json_server(
                    client_id="opencode",
                    scope=scope,
                    path=path,
                    server_name=server_name,
                    raw_server=raw,
                )
            )
        return candidates

    def _discover_codex(self, path: Path, scope: str) -> list[DetectedServerCandidate]:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        servers = payload.get("mcp_servers", {})
        if not isinstance(servers, dict):
            return []
        candidates: list[DetectedServerCandidate] = []
        for server_name, raw_server in servers.items():
            if not isinstance(raw_server, dict):
                continue
            headers = raw_server.get("http_headers", {})
            if raw_server.get("bearer_token_env_var"):
                headers = {
                    **headers,
                    "Authorization": (
                        f'Bearer ${{{raw_server["bearer_token_env_var"]}}}'
                    ),
                }
            raw = {
                "url": raw_server.get("url"),
                "command": raw_server.get("command"),
                "args": raw_server.get("args", []),
                "env": raw_server.get("env", {}),
                "headers": headers,
            }
            candidates.append(
                self._candidate_from_json_server(
                    client_id="codex",
                    scope=scope,
                    path=path,
                    server_name=server_name,
                    raw_server=raw,
                )
            )
        return candidates

    def _candidate_from_json_server(
        self,
        *,
        client_id: str,
        scope: str,
        path: Path,
        server_name: str,
        raw_server: dict[str, Any],
    ) -> DetectedServerCandidate:
        transport: str
        upstream: UpstreamServerDefinition | None
        import_reason: str | None = None
        url = raw_server.get("url")
        command = raw_server.get("command")
        args = raw_server.get("args", [])
        env = raw_server.get("env", {})
        headers = raw_server.get("headers", {})

        if isinstance(url, str) and url:
            transport = "streamable_http"
            upstream = UpstreamServerDefinition(
                server_id=_slugify(server_name),
                transport="streamable_http",
                url=url,
                command=None,
                args=(),
                env={},
                headers={
                    key: str(value) for key, value in headers.items() if isinstance(key, str)
                },
                origin_client=client_id,
                origin_path=str(path),
                managed_by="import",
                last_imported_at=_now_iso(),
            )
        elif isinstance(command, str) and command:
            transport = "stdio"
            upstream = UpstreamServerDefinition(
                server_id=_slugify(server_name),
                transport="stdio",
                url=None,
                command=command,
                args=tuple(str(item) for item in args if isinstance(item, str)),
                env={
                    key: str(value) for key, value in env.items() if isinstance(key, str)
                },
                headers={},
                origin_client=client_id,
                origin_path=str(path),
                managed_by="import",
                last_imported_at=_now_iso(),
            )
        else:
            transport = "unsupported"
            upstream = None
            import_reason = "Only stdio and streamable_http candidates are supported."

        return DetectedServerCandidate(
            candidate_id=_candidate_id(client_id, scope, path, server_name),
            source_client=client_id,
            source_label=_client_label(client_id),
            scope=scope,
            config_path=str(path),
            server_name=server_name,
            transport=transport,
            summary=upstream.to_discovery_summary() if upstream else "-",
            env_keys=tuple(sorted(upstream.env.keys())) if upstream else (),
            importable=upstream is not None,
            import_reason=import_reason,
            normalized_upstream=upstream,
        )

    def _allocate_server_id(self, candidate: DetectedServerCandidate) -> str:
        base = _slugify(candidate.server_name) or "imported-server"
        existing_ids = {
            upstream.server_id for upstream in self._state_store.load().upstreams
        }
        existing_ids.update(
            upstream.server_id
            for upstream in []
        )
        if base not in existing_ids:
            return base
        suffix = 2
        while f"{base}-{suffix}" in existing_ids:
            suffix += 1
        return f"{base}-{suffix}"


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_jsonc_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw_text = path.read_text(encoding="utf-8")
    payload = json.loads(_strip_json_comments(raw_text))
    return payload if isinstance(payload, dict) else {}


def _strip_json_comments(raw_text: str) -> str:
    in_string = False
    escaped = False
    in_line_comment = False
    in_block_comment = False
    result: list[str] = []
    index = 0
    while index < len(raw_text):
        char = raw_text[index]
        next_char = raw_text[index + 1] if index + 1 < len(raw_text) else ""
        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                result.append(char)
            index += 1
            continue
        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == "/" and next_char == "/":
            in_line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue
        result.append(char)
        if char == '"':
            in_string = True
        index += 1
    return "".join(result)


def _remove_codex_server_block(raw_text: str, server_name: str) -> str:
    if not raw_text.strip():
        return ""
    server_prefix = f"[mcp_servers.{server_name}"
    lines = raw_text.splitlines()
    kept: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped.startswith(server_prefix):
                skipping = True
                continue
            if skipping:
                skipping = False
        if not skipping:
            kept.append(line)
    cleaned = "\n".join(kept).strip("\n")
    return f"{cleaned}\n" if cleaned else ""


def _candidate_id(client_id: str, scope: str, path: Path, server_name: str) -> str:
    digest = hashlib.sha256(
        f"{client_id}|{scope}|{path}|{server_name}".encode("utf-8")
    ).hexdigest()[:12]
    return f"{client_id}:{digest}"


def _client_label(client_id: str) -> str:
    return {
        "claude_code": "Claude Code",
        "cursor": "Cursor",
        "codex": "Codex",
        "opencode": "OpenCode",
    }[client_id]


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
