from dataclasses import dataclass
from typing import Any

from internal.config import Settings
from internal.mcp.errors import JsonRpcErrorCode, JsonRpcFault
from internal.mcp.models import JsonRpcRequest, JsonRpcResponse
from internal.registry import InMemoryToolRegistry
from internal.session_manager import InMemorySessionManager


@dataclass(slots=True)
class DispatchResult:
    response: JsonRpcResponse | None
    session_id: str | None = None
    status_code: int = 200


class MCPRouterService:
    def __init__(
        self,
        settings: Settings,
        session_manager: InMemorySessionManager,
        tool_registry: InMemoryToolRegistry,
    ) -> None:
        self._settings = settings
        self._session_manager = session_manager
        self._tool_registry = tool_registry

    async def handle_request(
        self,
        request: JsonRpcRequest,
        session_id: str | None,
    ) -> DispatchResult:
        try:
            if request.method == "initialize":
                return await self._handle_initialize(request, session_id)
            if request.method == "notifications/initialized":
                return await self._handle_initialized_notification(session_id)
            if request.method == "tools/list":
                return await self._handle_tools_list(request, session_id)
            if request.method == "tools/call":
                return await self._handle_tools_call(request, session_id)
            raise JsonRpcFault(
                code=JsonRpcErrorCode.METHOD_NOT_FOUND,
                message=f"Unsupported MCP method: {request.method}",
            )
        except JsonRpcFault as exc:
            return DispatchResult(
                response=JsonRpcResponse(
                    id=request.id,
                    error={
                        "code": int(exc.code),
                        "message": exc.message,
                        "data": exc.data,
                    },
                ),
                session_id=session_id,
            )

    async def _handle_initialize(
        self,
        request: JsonRpcRequest,
        session_id: str | None,
    ) -> DispatchResult:
        self._require_request_id(request)
        session = await self._session_manager.get_or_create(session_id=session_id)

        return DispatchResult(
            response=JsonRpcResponse(
                id=request.id,
                result={
                    "protocolVersion": "2025-03-26",
                    "serverInfo": {
                        "name": self._settings.app_name,
                        "version": self._settings.app_version,
                    },
                    "capabilities": {
                        "tools": {
                            "listChanged": False,
                        }
                    },
                },
            ),
            session_id=session.session_id,
        )

    async def _handle_initialized_notification(
        self,
        session_id: str | None,
    ) -> DispatchResult:
        session = await self._require_session(session_id)
        await self._session_manager.touch(session.session_id)
        return DispatchResult(response=None, session_id=session.session_id, status_code=202)

    async def _handle_tools_list(
        self,
        request: JsonRpcRequest,
        session_id: str | None,
    ) -> DispatchResult:
        self._require_request_id(request)
        session = await self._require_session(session_id)
        tools = [tool.to_mcp_payload() for tool in await self._tool_registry.list_tools()]

        return DispatchResult(
            response=JsonRpcResponse(
                id=request.id,
                result={"tools": tools},
            ),
            session_id=session.session_id,
        )

    async def _handle_tools_call(
        self,
        request: JsonRpcRequest,
        session_id: str | None,
    ) -> DispatchResult:
        self._require_request_id(request)
        session = await self._require_session(session_id)
        tool_name = request.params.get("name")
        arguments = request.params.get("arguments", {})

        if not isinstance(tool_name, str) or not tool_name.strip():
            raise JsonRpcFault(
                code=JsonRpcErrorCode.INVALID_PARAMS,
                message="tools/call requires a non-empty tool name.",
            )
        if not isinstance(arguments, dict):
            raise JsonRpcFault(
                code=JsonRpcErrorCode.INVALID_PARAMS,
                message="tools/call arguments must be an object.",
            )

        tool = await self._tool_registry.get_tool(tool_name)
        if tool is None:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.TOOL_NOT_FOUND,
                message=f"Tool is not registered: {tool_name}",
            )

        raise JsonRpcFault(
            code=JsonRpcErrorCode.UPSTREAM_NOT_CONFIGURED,
            message="Tool routing is scaffolded but no upstream binding exists yet.",
            data={"tool": tool.name, "argumentsPreview": arguments},
        )

    def _require_request_id(self, request: JsonRpcRequest) -> None:
        if request.id is None:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.INVALID_REQUEST,
                message="A JSON-RPC id is required for request/response flows.",
            )

    async def _require_session(self, session_id: str | None):
        if session_id is None:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.SESSION_REQUIRED,
                message="MCP-Session-Id header is required. Call initialize first.",
            )

        session = await self._session_manager.get(session_id)
        if session is None:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.SESSION_REQUIRED,
                message="Session is missing or expired. Call initialize again.",
            )
        return session
