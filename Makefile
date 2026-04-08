.PHONY: install dev test

install:
	python3 -m pip install -e ".[dev]"

dev:
	uvicorn internal.application:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest
