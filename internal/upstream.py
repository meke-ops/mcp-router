import asyncio
import json
import os
from dataclasses import dataclass

import httpx

from internal.mcp.models import JsonRpcRequest, JsonRpcResponse
from internal.registry import UpstreamServerDefinition


@dataclass(slots=True)
class UpstreamCallResult:
    response: JsonRpcResponse | None
    upstream_session_id: str | None = None
    server_id: str | None = None


class UpstreamTransportError(Exception):
    pass


class UpstreamTransportGateway:
    def __init__(
        self,
        http_transport_overrides: dict[str, httpx.AsyncBaseTransport] | None = None,
    ) -> None:
        self._http_transport_overrides = http_transport_overrides or {}

    async def send(
        self,
        server: UpstreamServerDefinition,
        request: JsonRpcRequest,
        session_id: str | None = None,
        tenant_id: str | None = None,
        principal_id: str | None = None,
        request_id: str | None = None,
        traceparent: str | None = None,
    ) -> UpstreamCallResult:
        if server.transport == "streamable_http":
            return await self._send_http(
                server=server,
                request=request,
                session_id=session_id,
                tenant_id=tenant_id,
                principal_id=principal_id,
                request_id=request_id,
                traceparent=traceparent,
            )
        if server.transport == "stdio":
            return await self._send_stdio(
                server=server,
                request=request,
                tenant_id=tenant_id,
                principal_id=principal_id,
                request_id=request_id,
                traceparent=traceparent,
            )
        raise UpstreamTransportError(f"Unsupported transport: {server.transport}")

    async def _send_http(
        self,
        server: UpstreamServerDefinition,
        request: JsonRpcRequest,
        session_id: str | None,
        tenant_id: str | None,
        principal_id: str | None,
        request_id: str | None,
        traceparent: str | None,
    ) -> UpstreamCallResult:
        if not server.endpoint_url:
            raise UpstreamTransportError(
                f"HTTP upstream is missing endpoint URL for {server.server_id}."
            )

        client_kwargs: dict[str, object] = {
            "timeout": server.timeout_seconds,
        }
        transport = self._http_transport_overrides.get(server.endpoint_url)
        if transport is not None:
            client_kwargs["transport"] = transport

        headers = {"Content-Type": "application/json"}
        if session_id:
            headers["MCP-Session-Id"] = session_id
        if tenant_id:
            headers["X-MCP-Router-Tenant-Id"] = tenant_id
        if principal_id:
            headers["X-MCP-Router-Principal-Id"] = principal_id
        if request_id:
            headers["X-MCP-Router-Request-Id"] = request_id
        if traceparent:
            headers["traceparent"] = traceparent

        async with httpx.AsyncClient(**client_kwargs) as client:
            try:
                response = await client.post(
                    server.endpoint_url,
                    json=request.model_dump(mode="json", exclude_none=True),
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                raise UpstreamTransportError(
                    f"HTTP upstream request failed for {server.server_id}: {exc}"
                ) from exc

        if request.id is None:
            return UpstreamCallResult(
                response=None,
                upstream_session_id=response.headers.get("MCP-Session-Id"),
                server_id=server.server_id,
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise UpstreamTransportError(
                f"HTTP upstream returned invalid JSON for {server.server_id}."
            ) from exc

        return UpstreamCallResult(
            response=JsonRpcResponse.model_validate(payload),
            upstream_session_id=response.headers.get("MCP-Session-Id"),
            server_id=server.server_id,
        )

    async def _send_stdio(
        self,
        server: UpstreamServerDefinition,
        request: JsonRpcRequest,
        tenant_id: str | None,
        principal_id: str | None,
        request_id: str | None,
        traceparent: str | None,
    ) -> UpstreamCallResult:
        if not server.command:
            raise UpstreamTransportError(
                f"stdio upstream is missing command for {server.server_id}."
            )

        env = os.environ.copy()
        env.update(server.env)
        if tenant_id:
            env["MCP_ROUTER_TENANT_ID"] = tenant_id
        if principal_id:
            env["MCP_ROUTER_PRINCIPAL_ID"] = principal_id
        if request_id:
            env["MCP_ROUTER_REQUEST_ID"] = request_id
        if traceparent:
            env["TRACEPARENT"] = traceparent
        process = await asyncio.create_subprocess_exec(
            *server.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None

        payload = request.model_dump(mode="json", exclude_none=True)
        process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

        if request.id is None:
            await asyncio.wait_for(process.wait(), timeout=server.timeout_seconds)
            return UpstreamCallResult(response=None, server_id=server.server_id)

        stdout_line = await asyncio.wait_for(
            process.stdout.readline(),
            timeout=server.timeout_seconds,
        )
        stderr_output = await asyncio.wait_for(
            process.stderr.read(),
            timeout=server.timeout_seconds,
        )
        return_code = await asyncio.wait_for(
            process.wait(),
            timeout=server.timeout_seconds,
        )

        if return_code != 0:
            stderr_text = stderr_output.decode("utf-8", errors="replace").strip()
            raise UpstreamTransportError(
                f"stdio upstream exited with code {return_code} for {server.server_id}: {stderr_text}"
            )
        if not stdout_line:
            raise UpstreamTransportError(
                f"stdio upstream returned an empty response for {server.server_id}."
            )

        try:
            payload = json.loads(stdout_line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise UpstreamTransportError(
                f"stdio upstream returned invalid JSON for {server.server_id}."
            ) from exc

        return UpstreamCallResult(
            response=JsonRpcResponse.model_validate(payload),
            server_id=server.server_id,
        )
