.PHONY: install dev lint typecheck test test-unit test-integration package image compose-config k8s-render ci

PYTHON ?= python3
PIP := $(PYTHON) -m pip

install:
	$(PIP) install -e ".[dev]"

dev:
	uvicorn internal.application:app --host 0.0.0.0 --port 8000 --reload

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest

test-unit:
	$(PYTHON) -m pytest -m unit

test-integration:
	$(PYTHON) -m pytest -m integration

package:
	$(PYTHON) -m build --no-isolation

image:
	docker build -f deploy/Dockerfile -t mcp-router:local .

compose-config:
	docker compose -f deploy/docker-compose.yml config >/dev/null

k8s-render:
	kubectl kustomize deploy/k8s/overlays/staging >/dev/null

ci: lint typecheck test-unit test-integration package k8s-render
