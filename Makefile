.PHONY: setup lint type foundation test test-docker i18n rules leak persistence schemas ci images images-podman clean

setup:
	uv sync --all-extras
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .

type:
	uv run mypy

foundation:
	uv run mypy --strict tests/unit/engine
	uv run mypy --strict scripts/check_rules.py
	uv run mypy --strict scripts/check_engine_loc.py scripts/check_no_excuse_rules.py
	uv run mypy --strict scripts/release_gate.py scripts/release_evidence.py scripts/performance_gate.py scripts/release_preflight.py scripts/package_binary.py scripts/assemble_release.py scripts/render_homebrew_formula.py
	uv run python scripts/check_no_excuse_rules.py tests/unit/engine scripts/check_rules.py
	uv run python scripts/check_engine_loc.py  # 250 pure LOC maximum

test:
	uv run pytest -m "not docker and not network" --cov=panopticon --cov-report=term

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

ci: lint type foundation schemas i18n rules persistence test

images:
	docker build -t pano-sandbox-base:ultragoal -f src/panopticon/sandbox/images/base.Dockerfile src/panopticon/sandbox/images
	docker build -t pano-sandbox-node:20-ultragoal --build-arg BASE_IMAGE=pano-sandbox-base:ultragoal -f src/panopticon/sandbox/images/node.Dockerfile src/panopticon/sandbox/images
	docker build -t pano-sandbox-node:22-ultragoal --build-arg BASE_IMAGE=pano-sandbox-base:ultragoal --build-arg NODE_IMAGE=node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 -f src/panopticon/sandbox/images/node.Dockerfile src/panopticon/sandbox/images
	docker build -t pano-sandbox-python:3.12-ultragoal -f src/panopticon/sandbox/images/python.Dockerfile src/panopticon/sandbox/images

images-podman:
	podman build -t localhost/pano-sandbox-base:ultragoal -f src/panopticon/sandbox/images/base.Dockerfile src/panopticon/sandbox/images
	podman build -t localhost/pano-sandbox-node:20-ultragoal --build-arg BASE_IMAGE=localhost/pano-sandbox-base:ultragoal -f src/panopticon/sandbox/images/node.Dockerfile src/panopticon/sandbox/images
	podman build -t localhost/pano-sandbox-node:22-ultragoal --build-arg BASE_IMAGE=localhost/pano-sandbox-base:ultragoal --build-arg NODE_IMAGE=node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 -f src/panopticon/sandbox/images/node.Dockerfile src/panopticon/sandbox/images
	podman build -t localhost/pano-sandbox-python:3.12-ultragoal -f src/panopticon/sandbox/images/python.Dockerfile src/panopticon/sandbox/images

clean:
	rm -rf .venv .mypy_cache .ruff_cache .pytest_cache htmlcov coverage.xml dist build
