# mcp-router

Production-oriented MCP gateway/proxy focused on tool discovery, policy enforcement,
routing, and observability.

## Current status

The repository now includes the backend work through milestone 8:

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
- tenant/principal/tool-scoped rate limiting and concurrency gates
- in-memory policy, tool-call, and audit-event logging
- `traceparent` propagation from `/mcp` to upstream transports
- in-memory span recorder for request, policy, traffic, and upstream traces
- retry-aware upstream fallback chains with in-memory circuit breakers
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

## Traffic control configuration

The router applies per `tenant + principal + tool` traffic shaping for
`tools/call`.

Environment variables:

```text
MCP_ROUTER_TOOL_CALL_RATE_LIMIT_CAPACITY=60
MCP_ROUTER_TOOL_CALL_RATE_LIMIT_REFILL_RATE=30.0
MCP_ROUTER_TOOL_CALL_CONCURRENCY_LIMIT=8
```

Over-limit calls return `429` with a structured JSON-RPC error payload and an
audit event describing whether the rejection came from the token bucket or the
concurrency gate.

## Trace propagation

If the caller sends a `traceparent` header to `/mcp`, the router keeps the same
`trace_id`, emits child spans for traffic checks, policy evaluation, and
upstream routing, and forwards a child `traceparent` to HTTP and stdio
upstreams. The router also returns:

```text
X-Request-Id: <router-request-id>
X-Trace-Id: <trace-id>
traceparent: <router-root-span>
```

## Resilience configuration

Each upstream can optionally define fallback and breaker settings through
`MCP_ROUTER_UPSTREAMS_JSON`.

Example:

```json
[
  {
    "server_id": "primary-http",
    "transport": "streamable_http",
    "endpoint_url": "http://127.0.0.1:9001/mcp",
    "fallback_server_ids": ["standby-http"],
    "retry_attempts": 1,
    "circuit_breaker_failure_threshold": 2,
    "circuit_breaker_recovery_seconds": 30.0
  },
  {
    "server_id": "standby-http",
    "transport": "streamable_http",
    "endpoint_url": "http://127.0.0.1:9002/mcp",
    "discover_tools": false
  }
]
```

When the primary route hits repeated transport failures, the router opens that
server's circuit, records the event, and continues with the configured fallback
chain instead of failing hard.

## Next backend steps

- move audit, tracing, session, and traffic stores to external backends
- expose audit/query/control-plane APIs and operational dashboards
- start the control-plane API and dashboard work for milestone 9
