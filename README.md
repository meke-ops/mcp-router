# mcp-router

Production-oriented MCP gateway/proxy focused on tool discovery, policy enforcement,
routing, and observability.

## Current status

The repository now includes the backend bootstrap for milestone 1 and the first
working slice of milestone 2:

- FastAPI application skeleton
- `/v1/health` and `/v1/ready` endpoints
- `POST /mcp` JSON-RPC entrypoint
- in-memory session bootstrap for `initialize`
- upstream passthrough for `initialize`, `tools/list`, and `tools/call`
- HTTP upstream session propagation through `MCP-Session-Id`
- tenant/principal binding via `X-Tenant-Id` and `X-Principal-Id`
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

To bind a router session to a tenant and principal, send these headers on
`initialize`:

```text
X-Tenant-Id: tenant-a
X-Principal-Id: user-1
```

Subsequent calls can reuse the same `MCP-Session-Id`. If the caller sends a
different tenant or principal for that session, the router rejects the request.

## Next backend steps

- replace in-memory session management with Redis-backed lifecycle management
- introduce registry persistence, schema validation, and policy enforcement
- wire PostgreSQL, Redis, tracing, and audit storage into readiness checks
