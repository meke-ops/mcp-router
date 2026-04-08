from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse

from api.http.dependencies import get_services
from internal.container import ServiceContainer
from internal.mcp.models import JsonRpcRequest

router = APIRouter(tags=["mcp"])


@router.post("")
async def handle_mcp(
    request: JsonRpcRequest,
    services: ServiceContainer = Depends(get_services),
    mcp_session_id: str | None = Header(default=None, alias="MCP-Session-Id"),
) -> Response:
    dispatch_result = await services.mcp_service.handle_request(
        request=request,
        session_id=mcp_session_id,
    )

    if dispatch_result.response is None:
        response: Response = Response(status_code=dispatch_result.status_code)
    else:
        response = JSONResponse(
            status_code=dispatch_result.status_code,
            content=dispatch_result.response.model_dump(mode="json", exclude_none=True),
        )

    if dispatch_result.session_id:
        response.headers["MCP-Session-Id"] = dispatch_result.session_id

    return response
