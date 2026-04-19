# Open Source Roadmap

This roadmap is meant to keep `mcp-router` honest and easy to contribute to.
It reflects the current state of the repository: a strong working foundation
with clear next steps toward a durable open source MCP gateway.

## Product Direction

`mcp-router` is aiming to become the open source control plane for MCP tool
traffic:

- route tool calls across multiple upstream MCP servers
- apply tenant-aware policy before execution
- protect shared tools with traffic controls
- expose audit trails and traces for operators
- provide a path from local development to staged deployment

## Guiding Principles

- be explicit about what is implemented versus what is planned
- prefer incremental, reviewable milestones over vague "rewrite" work
- keep data plane behavior well-tested before widening the surface area
- treat docs, examples, and operational clarity as product work
- make it easy for outside contributors to pick a bounded slice

## Current Baseline

Already in the repo today:

- MCP ingress with `initialize`, `tools/list`, and `tools/call`
- HTTP and stdio upstream support
- session binding, schema validation, policy checks, and traffic controls
- audit events, trace propagation, and fallback behavior
- control plane endpoints, setup flows, and dashboard
- Docker, CI checks, and staging Kubernetes assets

Known gap:

- most core stores and coordination layers are still in-memory

## Milestone 1: OSS Foundation

Goal: make the repository easier to understand, adopt, and contribute to.

Planned outcomes:

- tighten README positioning and adoption docs
- publish contribution workflow and issue taxonomy
- add architecture diagrams and request-flow examples where missing
- improve example payloads and local demo scripts
- document "good first issues" and "help wanted" areas

Definition of done:

- a new contributor can clone the repo, run it locally, and identify a first PR

Good contribution areas:

- docs polish
- onboarding scripts
- examples
- developer ergonomics

## Milestone 2: Durable Runtime State

Goal: replace critical in-memory runtime pieces with durable backing services.

Planned outcomes:

- PostgreSQL-backed registry and audit persistence
- Redis-backed session lifecycle and traffic coordination
- clear migration path from local in-memory mode to persistent mode
- tests that cover restart and recovery scenarios

Definition of done:

- key operator data survives process restart
- rate limit/session behavior works across instances

Good contribution areas:

- schema design
- repository interfaces and adapters
- migration docs
- restart/integration testing

## Milestone 3: Security And Policy Hardening

Goal: move from basic protection to stronger production safeguards.

Planned outcomes:

- stronger JWT validation and key management paths
- better tenant isolation guarantees and negative tests
- policy model improvements for real multi-role scenarios
- clearer audit semantics for auth and policy decisions

Definition of done:

- auth and tenant-boundary behavior is explicit, tested, and documented

Good contribution areas:

- negative-path tests
- claim handling
- policy evaluation rules
- audit schema improvements

## Milestone 4: Observability And Operations

Goal: make the router easier to operate in real environments.

Planned outcomes:

- external trace export instead of local-only in-memory tracing
- richer Prometheus metrics and dashboards
- stronger readiness semantics tied to backing services
- runbooks for failure, rollback, and degraded upstream behavior

Definition of done:

- operators can detect, explain, and respond to unhealthy behavior quickly

Good contribution areas:

- metrics naming
- trace export
- dashboards
- runbooks

## Milestone 5: Setup And Ecosystem Compatibility

Goal: make the project more useful in real MCP environments.

Planned outcomes:

- better import/discovery support for MCP client configs
- compatibility testing against more client/server combinations
- clearer transport behavior and error handling docs
- sample deployments for common adoption patterns

Definition of done:

- a new team can integrate `mcp-router` with less custom glue code

Good contribution areas:

- setup adapters
- integration fixtures
- transport docs
- sample configs

## Milestone 6: Operator Experience

Goal: turn the current admin surface into a stronger operator experience.

Planned outcomes:

- more actionable dashboard views for tools, policies, upstreams, and events
- safer control-plane workflows for registration and imports
- better diff/preview flows for setup actions
- improved audit and event filtering

Definition of done:

- the dashboard helps an operator understand and manage the router, not just inspect it

Good contribution areas:

- UI polish
- dashboard usability
- filtering/search
- control-plane API ergonomics

## Suggested GitHub Labeling

To keep open source work easy to navigate, use labels like:

- `good first issue`
- `help wanted`
- `docs`
- `testing`
- `security`
- `observability`
- `control-plane`
- `data-plane`
- `setup`
- `breaking-change`

## Maintainer Notes

When choosing work, prefer issues that:

- reduce the gap between README promises and actual runtime behavior
- improve contributor onboarding
- strengthen tests around boundary behavior
- preserve the project's identity as a gateway rather than an agent platform
