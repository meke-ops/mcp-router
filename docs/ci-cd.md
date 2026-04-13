# CI/CD and Quality Gates

This repository uses GitHub Actions for milestone 11 quality gates. The CI
pipeline is defined in `.github/workflows/ci.yml` and is intentionally split
into small required checks so branch protection can block partial regressions.

## Local commands

Use these targets before pushing:

```bash
make lint
make typecheck
make test-unit
make test-integration
make package
make image
make k8s-render
```

`make ci` runs the Python quality chain without container build. `make
compose-config` validates the compose file shape before deployment work starts.

## Required GitHub checks

Protect the `main` branch by requiring these status checks:

- `lint`
- `typecheck`
- `unit-tests`
- `integration-tests`
- `package`
- `k8s-manifests`
- `image-build`

## Notes

- `unit-tests` cover fast in-process behavior with no integrated upstream
  dependencies.
- `integration-tests` cover the in-memory integrated HTTP + stdio upstream flow,
  control-plane behavior, and security hardening scenarios.
- `package` verifies sdist and wheel creation through `python -m build`.
- `image-build` verifies both `docker compose` configuration and Docker image
  buildability from `deploy/Dockerfile`.
