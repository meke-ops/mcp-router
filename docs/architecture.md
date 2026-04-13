# Initial backend architecture

This bootstrap keeps the repository aligned with `development.md` while focusing
on the MCP data plane and its supporting backend services.

## Implemented now

- FastAPI application bootstrap with explicit service container
- versioned REST surface under `/v1`
- MCP JSON-RPC ingress at `POST /mcp`
- in-memory session manager to support `initialize`
- tenant/principal-aware session binding with mismatch protection
- versioned in-memory registry for tool discovery, bindings, and schema metadata
- JSON Schema validation before upstream tool execution
- default-deny policy evaluation with deterministic rule ordering
- per tool-call rate limiting and concurrency gates
- in-memory audit records for policy decisions, tool calls, and audit events
- traceparent-compatible span recording and upstream propagation
- retry-aware fallback chains and in-memory circuit breaker state
- passthrough transport gateway for `streamable_http` and `stdio` upstreams
- readiness surface that already exposes PostgreSQL and Redis configuration state
- control-plane REST and WebSocket endpoints for registry, policy, and audit operations
- bundled browser dashboard served from the FastAPI application

## Deferred to next milestones

- PostgreSQL-backed registry and audit storage
- Redis-backed session lifecycle and traffic control
- external trace export, metrics, and dashboards
- production auth hardening and tenant security barriers
