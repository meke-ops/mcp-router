# mcp-router

Production-oriented MCP gateway/proxy focused on tool discovery, policy enforcement,
routing, and observability.

## Current status

The repository now includes the backend bootstrap for milestone 1 and the first
slice of milestone 2:

- FastAPI application skeleton
- `/v1/health` and `/v1/ready` endpoints
- `POST /mcp` JSON-RPC entrypoint
- in-memory session bootstrap for `initialize`
- `tools/list` and `tools/call` scaffolding
- test suite for the initial API contract

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

## Next backend steps

- replace in-memory session management with Redis-backed lifecycle management
- add upstream MCP server bindings and passthrough routing
- introduce registry persistence, schema validation, and policy enforcement
- wire PostgreSQL, Redis, tracing, and audit storage into readiness checks
