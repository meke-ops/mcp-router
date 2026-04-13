from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class JsonRpcErrorCode(IntEnum):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    SESSION_REQUIRED = -32001
    TOOL_NOT_FOUND = -32004
    UPSTREAM_NOT_CONFIGURED = -32005
    UPSTREAM_UNAVAILABLE = -32006
    TOOL_NAME_CONFLICT = -32007
    IDENTITY_MISMATCH = -32008


@dataclass(slots=True)
class JsonRpcFault(Exception):
    code: int
    message: str
    data: Any | None = None
