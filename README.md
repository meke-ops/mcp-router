# mcp-router

Open source MCP gateway/proxy focused on tool discovery, policy enforcement,
routing, and observability.

`mcp-router` is building toward a production-grade control point for MCP tool
traffic. The goal is to give teams one place to route `tools/list` and
`tools/call` requests across multiple upstream MCP servers while applying
tenant-aware policy, traffic shaping, audit logging, and operational
visibility.

## Why This Project Exists

Most MCP demos stop at "the tool call worked." Real teams usually need more:

- a central policy layer before a tool executes
- routing across multiple upstream MCP servers
- auditability for who called what and why it was allowed or denied
- traffic protection for shared tools
- a path from local demo to staged deployment

This repository is the open source build-out of that gateway.

## Project Status

This repo is already a working MVP+ and a solid open source foundation, but it
is not yet at the final "production control plane" destination.

What works today:

- FastAPI application with MCP ingress at `POST /mcp`
- `initialize`, `tools/list`, and `tools/call` request handling
- HTTP and stdio upstream routing
- tenant/principal/session binding
- JSON Schema validation before `tools/call`
- default-deny policy enforcement
- rate limiting and concurrency gates
- audit events and trace propagation
- fallback chains and circuit-breaker behavior
- control-plane REST endpoints and a bundled dashboard
- JWT-backed auth flows and basic tenant-aware identity binding
- metrics, health/readiness endpoints, Docker assets, and staging K8s manifests
- automated lint, typecheck, unit, integration, packaging, and image checks

Important current limitation:

- most core runtime stores are still in-memory today

That means the repo is great for development, demos, validation, and staging
bootstrap work, while persistent storage and harder production guarantees are
still part of the public roadmap.

## Open Source Roadmap

The roadmap is tracked in [`docs/roadmap.md`](docs/roadmap.md).

High-level priorities:

1. strengthen the repo as an OSS project
2. replace in-memory runtime pieces with durable backing services
3. harden auth, policy, and tenant isolation
4. improve observability and operator workflows
5. expand compatibility with real MCP client/server setups

## Who This Is For

- teams building MCP-based internal platforms
- developers who want a policy-aware MCP gateway
- engineers interested in multi-tenant tool routing and observability
- contributors who want to help turn a strong prototype into a durable OSS project

## Non-Goals

- a full agent orchestration platform
- workflow planning/memory/evals as the main product surface
- hiding current limitations behind vague "production-ready" language

## Project Layout

```text
api/        HTTP routers and route dependencies
cmd/        local runner entrypoints
deploy/     Docker and compose assets
docs/       architecture, CI/CD, roadmap, and runbooks
examples/   sample JSON-RPC payloads and demo upstreams
internal/   application services and domain modules
tests/      unit and integration tests
```

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
uvicorn internal.application:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

## Quality Checks

```bash
make lint
make typecheck
make test-unit
make test-integration
make package
make k8s-render
```

To run the local CI chain:

```bash
make ci
```

To validate container assets locally:

```bash
make compose-config
make image
```

## Operations Endpoints

```text
GET /v1/health
GET /v1/ready
GET /metrics
```

`/v1/ready` performs active TCP dependency probes for PostgreSQL and Redis when
`MCP_ROUTER_REQUIRE_DEPENDENCIES_FOR_READINESS=true`.

## Control Plane

```text
GET    /v1/tools
POST   /v1/tools/refresh
POST   /v1/tools/register
DELETE /v1/tools/{tool_name}
GET    /v1/upstreams
POST   /v1/upstreams
GET    /v1/policies
POST   /v1/policies
DELETE /v1/policies/{rule_id}
GET    /v1/audit/policy-decisions
GET    /v1/audit/tool-calls
GET    /v1/audit/events
GET    /v1/setup/clients
POST   /v1/setup/client-preview
POST   /v1/setup/client-apply
GET    /v1/setup/discovery
POST   /v1/setup/import
POST   /v1/setup/verify
WS     /v1/events/ws
GET    /dashboard
```

## Demo Upstream Configuration

The router can load demo upstreams from `MCP_ROUTER_UPSTREAMS_JSON`.

Example:

```bash
export MCP_ROUTER_UPSTREAMS_JSON='[
  {"server_id":"demo-http","transport":"streamable_http","endpoint_url":"http://127.0.0.1:9001/mcp"},
  {"server_id":"demo-stdio","transport":"stdio","command":["python3","examples/upstreams/stdio_server.py"]}
]'
```

Start the sample HTTP upstream with:

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

## Demo Policy Configuration

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

## Traffic Control Configuration

The router applies per `tenant + principal + tool` traffic shaping for
`tools/call`.

```text
MCP_ROUTER_TOOL_CALL_RATE_LIMIT_CAPACITY=60
MCP_ROUTER_TOOL_CALL_RATE_LIMIT_REFILL_RATE=30.0
MCP_ROUTER_TOOL_CALL_CONCURRENCY_LIMIT=8
```

Over-limit calls return `429` with a structured JSON-RPC error payload and an
audit event describing whether the rejection came from the token bucket or the
concurrency gate.

## Trace Propagation

If the caller sends a `traceparent` header to `/mcp`, the router keeps the same
`trace_id`, emits child spans for traffic checks, policy evaluation, and
upstream routing, and forwards a child `traceparent` to HTTP and stdio
upstreams. The router also returns:

```text
X-Request-Id: <router-request-id>
X-Trace-Id: <trace-id>
traceparent: <router-root-span>
```

## Resilience Configuration

Each upstream can optionally define fallback and breaker settings through
`MCP_ROUTER_UPSTREAMS_JSON`.

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

## Contributing

Open source contribution guidance lives in [`CONTRIBUTING.md`](CONTRIBUTING.md).

If you want a place to start, focus on:

- docs and examples that make the project easier to adopt
- persistence work that replaces in-memory stores
- auth, policy, audit, and observability hardening
- setup and compatibility improvements for MCP clients

## CI And Branch Protection

GitHub Actions workflow definitions live in
`.github/workflows/ci.yml`. The intended required checks for `main` are:

- `lint`
- `typecheck`
- `unit-tests`
- `integration-tests`
- `package`
- `k8s-manifests`
- `image-build`

## Kubernetes Deployment

Staging-ready Kubernetes assets live under `deploy/k8s/base` and
`deploy/k8s/overlays/staging`.

- base manifests define the router deployment, service account, service, and config
- the staging overlay adds ingress, Postgres, Redis, PVC, and network policies
- secret example manifests document required secret keys without storing real values

For the step-by-step staging workflow, use
[`docs/runbooks/staging.md`](docs/runbooks/staging.md).

## Additional Docs

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/ci-cd.md`](docs/ci-cd.md)
- [`docs/roadmap.md`](docs/roadmap.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
