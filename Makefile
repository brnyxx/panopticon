.PHONY: setup lint type test test-docker i18n rules leak persistence ci images clean

setup:
	uv sync --all-extras
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .

type:
	uv run mypy

test:
	uv run pytest -m "not docker and not network"

test-docker:
	uv run pytest -m docker

i18n:
	uv run python scripts/check_i18n.py
	uv run python scripts/check_phrases.py

rules:
	uv run python scripts/check_rules.py

leak:
	uv run pytest tests/unit/test_leak_check.py -q

schemas:
	uv run python scripts/validate_schemas.py

persistence:
	uv run python scripts/check_persistence_boundary.py

ci: lint type schemas i18n rules persistence test

images:
	docker build -t pano-sandbox-base -f src/panopticon/sandbox/images/base.Dockerfile src/panopticon/sandbox/images
	docker build -t pano-sandbox-node:20 --build-arg NODE=20 -f src/panopticon/sandbox/images/node.Dockerfile src/panopticon/sandbox/images
	docker build -t pano-sandbox-python:3.12 -f src/panopticon/sandbox/images/python.Dockerfile src/panopticon/sandbox/images

clean:
	rm -rf .venv .mypy_cache .ruff_cache .pytest_cache htmlcov coverage.xml dist build
