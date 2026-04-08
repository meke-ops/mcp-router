from typing import Any

from pydantic import BaseModel, ConfigDict, Field


JsonRpcId = str | int | None


class JsonRpcRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    jsonrpc: str = Field(pattern=r"^2\.0$")
    id: JsonRpcId = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcErrorObject(BaseModel):
    code: int
    message: str
    data: Any | None = None


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: JsonRpcId = None
    result: dict[str, Any] | None = None
    error: JsonRpcErrorObject | None = None
