# Initial backend architecture

This bootstrap keeps the repository aligned with `development.md` while staying
strictly away from the dashboard/UI scope.

## Implemented now

- FastAPI application bootstrap with explicit service container
- versioned REST surface under `/v1`
- MCP JSON-RPC ingress at `POST /mcp`
- in-memory session manager to support `initialize`
- tenant/principal-aware session binding with mismatch protection
- upstream-aware in-memory registry for tool discovery and routing
- passthrough transport gateway for `streamable_http` and `stdio` upstreams
- readiness surface that already exposes PostgreSQL and Redis configuration state

## Deferred to next milestones

- PostgreSQL-backed registry and audit storage
- Redis-backed session lifecycle and rate limiting
- upstream stdio and Streamable HTTP routing
- policy engine, tracing, metrics, and circuit breaker
