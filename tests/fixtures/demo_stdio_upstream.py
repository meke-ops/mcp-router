import json
import os
import sys


def make_response(request_id, result=None, error=None):
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
    }
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return payload


for raw_line in sys.stdin:
    request = json.loads(raw_line)
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        response = make_response(
            request_id,
            result={
                "protocolVersion": "2025-03-26",
                "serverInfo": {
                    "name": "demo-stdio-upstream",
                    "version": "0.1.0",
                },
                "capabilities": {
                    "tools": {
                        "listChanged": False,
                    }
                },
            },
        )
    elif method == "tools/list":
        response = make_response(
            request_id,
            result={
                "tools": [
                    {
                        "name": "demo.stdio.echo",
                        "description": "Echoes a text payload from the stdio upstream.",
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
        )
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        if tool_name != "demo.stdio.echo":
            response = make_response(
                request_id,
                error={
                    "code": -32004,
                    "message": f"Unknown tool: {tool_name}",
                },
            )
        else:
            response = make_response(
                request_id,
                result={
                    "content": [
                        {
                            "type": "text",
                            "text": arguments.get("text", ""),
                        }
                    ],
                    "structuredContent": {
                        "tool": tool_name,
                        "transport": "stdio",
                        "echo": arguments.get("text", ""),
                        "tenantId": os.getenv("MCP_ROUTER_TENANT_ID"),
                        "principalId": os.getenv("MCP_ROUTER_PRINCIPAL_ID"),
                    },
                },
            )
    else:
        response = make_response(
            request_id,
            error={
                "code": -32601,
                "message": f"Unsupported method: {method}",
            },
        )

    if request_id is not None:
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
