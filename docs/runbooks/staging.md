# Staging Runbook

This runbook covers the milestone 12 staging workflow for `mcp-router`.

## Prerequisites

- A Kubernetes cluster with an ingress controller
- `kubectl` access to the target cluster
- A published container image for the router

## Secret preparation

Create the secrets from the example manifests before applying the overlay:

```bash
cp deploy/k8s/overlays/staging/postgres-staging-secrets.example.yaml /tmp/postgres-staging-secrets.yaml
cp deploy/k8s/overlays/staging/router-secrets.example.yaml /tmp/router-secrets.yaml
```

Replace the placeholder values in both files, then apply them:

```bash
kubectl apply -f /tmp/postgres-staging-secrets.yaml
kubectl apply -f /tmp/router-secrets.yaml
```

## Render and apply

Render the overlay locally first:

```bash
make k8s-render
kubectl kustomize deploy/k8s/overlays/staging
```

Apply the staging stack:

```bash
kubectl apply -k deploy/k8s/overlays/staging
```

## Rollout verification

Check the namespace workloads:

```bash
kubectl -n mcp-router-staging get pods
kubectl -n mcp-router-staging rollout status deploy/mcp-router
kubectl -n mcp-router-staging rollout status deploy/postgres
kubectl -n mcp-router-staging rollout status deploy/redis
```

Verify service endpoints:

```bash
kubectl -n mcp-router-staging get svc,endpoints
kubectl -n mcp-router-staging get ingress
```

## Health and readiness

Port-forward the router and validate the operational endpoints:

```bash
kubectl -n mcp-router-staging port-forward deploy/mcp-router 8000:8000
curl -sS http://127.0.0.1:8000/v1/health | jq
curl -sS http://127.0.0.1:8000/v1/ready | jq
curl -sS http://127.0.0.1:8000/metrics | head -40
```

Expected outcome:

- `/v1/health` returns `status=ok`
- `/v1/ready` returns `status=ready`
- `/metrics` exposes Prometheus text including `mcp_router_build_info`

## Log verification

Stream the application logs:

```bash
kubectl -n mcp-router-staging logs deploy/mcp-router -f
```

Expected outcome:

- JSON log lines if `MCP_ROUTER_LOG_FORMAT=json`
- `http_request_completed` entries on health, readiness, and metrics requests

## Troubleshooting

- If readiness is `not_ready`, inspect the dependency details in `/v1/ready`
- If Postgres is failing, verify `postgres-staging-secrets` and the `postgres-data` PVC
- If metrics do not scrape, confirm pod annotations and the cluster Prometheus scrape configuration
- If ingress is unreachable, check ingress controller namespace labels against the router NetworkPolicy
- If upstream calls need non-80/443 external egress, extend `networkpolicy-router.yaml`

## Rollback

To roll back the router deployment:

```bash
kubectl -n mcp-router-staging rollout undo deploy/mcp-router
```

To remove the whole staging stack:

```bash
kubectl delete -k deploy/k8s/overlays/staging
```
