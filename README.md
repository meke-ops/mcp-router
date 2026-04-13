# mcp-router

Production-oriented MCP gateway/proxy focused on tool discovery, policy enforcement,
routing, and observability.

## Current status

The repository now includes the backend work through milestone 5:

- FastAPI application skeleton
- `/v1/health` and `/v1/ready` endpoints
- `POST /mcp` JSON-RPC entrypoint
- in-memory session bootstrap for `initialize`
- upstream passthrough for `initialize`, `tools/list`, and `tools/call`
- HTTP upstream session propagation through `MCP-Session-Id`
- tenant/principal binding via `X-Tenant-Id` and `X-Principal-Id`
- session role binding via `X-Principal-Roles`
- versioned in-memory tool registry with server bindings
- JSON Schema validation before `tools/call` routing
- default-deny policy enforcement before `tools/call`
- in-memory policy decision audit logging with rule and obligation capture
- integration tests covering one HTTP and one stdio upstream

## Project layout

```text
api/        HTTP routers and route dependencies
cmd/        local runner entrypoints
deploy/     Docker and compose assets
docs/       architecture notes
examples/   sample JSON-RPC payloads
internal/   application services and domain modules
tests/      API tests
```

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
uvicorn internal.application:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

## Running tests

```bash
pytest
```

## Demo upstream configuration

The router can load demo upstreams from `MCP_ROUTER_UPSTREAMS_JSON`.

Example:

```bash
export MCP_ROUTER_UPSTREAMS_JSON='[
  {"server_id":"demo-http","transport":"streamable_http","endpoint_url":"http://127.0.0.1:9001/mcp"},
  {"server_id":"demo-stdio","transport":"stdio","command":["python3","examples/upstreams/stdio_server.py"]}
]'
```

You can start the sample HTTP upstream with:

```bash
python3 examples/upstreams/http_server.py
```

To bind a router session to a tenant, principal, and optional roles, send these
headers on `initialize`:

```text
X-Tenant-Id: tenant-a
X-Principal-Id: user-1
X-Principal-Roles: ops,admin
```

Subsequent calls can reuse the same `MCP-Session-Id`. If the caller sends a
different tenant, principal, or role set for that session, the router rejects
the request.

## Demo policy configuration

The router can load policy rules from `MCP_ROUTER_POLICIES_JSON`.

Example:

```bash
export MCP_ROUTER_POLICIES_JSON='[
  {
    "rule_id":"deny-blocked-principal",
    "effect":"deny",
    "reason":"Principal is blocked from invoking tools in this tenant.",
    "priority":100,
    "tenant_ids":["tenant-a"],
    "principal_ids":["blocked-user"],
    "tool_names":["demo.*"],
    "obligations":[
      {"type":"notify","parameters":{"channel":"security"}}
    ]
  },
  {
    "rule_id":"allow-http-for-user-1",
    "effect":"allow",
    "reason":"Principal is allowed to use the HTTP demo tool.",
    "priority":50,
    "tenant_ids":["tenant-a"],
    "principal_ids":["user-1"],
    "tool_names":["demo.http.reverse"],
    "obligations":[
      {"type":"audit","parameters":{"level":"full"}}
    ]
  }
]'
```

If no policy matches a `tools/call`, the router returns a deterministic default
deny response and records the decision in the audit log.

## Next backend steps

- replace in-memory session management with Redis-backed lifecycle management
- add Redis-backed rate limiting and concurrency gates
- wire PostgreSQL, Redis, tracing, and audit storage into readiness checks
