from fastapi import FastAPI, Header, Response
import uvicorn


HTTP_UPSTREAM_SESSION_ID = "demo-http-upstream-session"
app = FastAPI(title="mcp-router demo HTTP upstream")


@app.post("/mcp")
async def handle_mcp(
    payload: dict,
    response: Response,
    mcp_session_id: str | None = Header(default=None, alias="MCP-Session-Id"),
) -> dict:
    method = payload.get("method")
    request_id = payload.get("id")
    params = payload.get("params", {})

    if method == "initialize":
        response.headers["MCP-Session-Id"] = HTTP_UPSTREAM_SESSION_ID
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "serverInfo": {
                    "name": "demo-http-upstream",
                    "version": "0.1.0",
                },
                "capabilities": {
                    "tools": {
                        "listChanged": False,
                    }
                },
            },
        }

    if method == "tools/list":
        if mcp_session_id != HTTP_UPSTREAM_SESSION_ID:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32001,
                    "message": "HTTP upstream session is missing.",
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "demo.http.reverse",
                        "description": "Reverses text using the HTTP upstream.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                            },
                            "required": ["text"],
                        },
                    }
                ]
            },
        }

    if method == "tools/call":
        if mcp_session_id != HTTP_UPSTREAM_SESSION_ID:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32001,
                    "message": "HTTP upstream session is missing.",
                },
            }
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        if tool_name != "demo.http.reverse":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32004,
                    "message": f"Unknown tool: {tool_name}",
                },
            }
        text = arguments.get("text", "")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": text[::-1],
                    }
                ],
                "structuredContent": {
                    "tool": tool_name,
                    "transport": "streamable_http",
                    "reversed": text[::-1],
                },
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": -32601,
            "message": f"Unsupported method: {method}",
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9001)
