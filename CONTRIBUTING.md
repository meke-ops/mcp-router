# Contributing To mcp-router

Thanks for taking a look at `mcp-router`.

This project is being developed in the open as an MCP gateway focused on
policy, routing, traffic control, and observability. Contributions are welcome
across code, docs, tests, examples, and operator experience.

## Good First Areas

- improve docs, examples, and developer onboarding
- add or strengthen tests
- polish setup/discovery flows
- improve dashboard and control-plane UX
- help replace in-memory runtime pieces with durable backends

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

Run the app:

```bash
uvicorn internal.application:app --reload
```

Run quality checks:

```bash
make lint
make typecheck
make test-unit
make test-integration
make package
make k8s-render
```

Or run the local CI chain:

```bash
make ci
```

## Before You Open A PR

- keep changes scoped to one clear problem
- add or update tests when behavior changes
- update docs if user-facing behavior or setup changes
- avoid sneaking unrelated refactors into feature PRs

## Pull Request Guidelines

- explain the problem, not just the code change
- include validation notes such as `make test-unit` or `make ci`
- mention tradeoffs or follow-up work if the solution is partial
- prefer smaller PRs over large mixed changes

## Issue Guidance

When opening an issue, try to include:

- what you expected
- what happened instead
- steps to reproduce
- logs, payloads, or config snippets if relevant
- whether the issue affects local dev, setup, control plane, or MCP routing

## Design Expectations

This project is intentionally focused. Please keep contributions aligned with
the core direction:

- build a strong MCP gateway/control point
- improve policy, routing, safety, and observability
- do not turn the repo into a full agent orchestration platform

## Areas That Need The Most Help

- persistent storage for registry, audit, and runtime coordination
- Redis-backed traffic/session behavior
- auth and tenant isolation hardening
- observability exports and dashboards
- setup compatibility with real MCP clients and servers

## Communication

If a change is large or likely to affect the project's direction, open an issue
first so the approach can be aligned before implementation.
