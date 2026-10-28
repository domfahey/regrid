.DEFAULT_GOAL := help
UV ?= uv
PYTHON ?= .venv/bin/python
ENV_FILE = $(if $(wildcard .env),--env-file .env,)

.PHONY: help install lint format format-check type typecheck test e2e live doctor check

help:
	@echo "install       Install SDK, CLI, and development dependencies"
	@echo "lint          Check Python lint rules"
	@echo "format        Format Python source and tests"
	@echo "format-check  Check formatting without modifying files"
	@echo "typecheck     Check SDK and CLI types (alias: type)"
	@echo "test          Run mocked tests with a 90% line/branch coverage gate"
	@echo "e2e           Run local HTTPS and CLI subprocess tests"
	@echo "live          Explicit live Regrid smoke test (may incur one parcel charge)"
	@echo "doctor        Check local .env and token configuration without API calls"
	@echo "check         Run lint, formatting check, typecheck, and test"

install:
	$(UV) sync --group dev

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

format-check:
	$(PYTHON) -m ruff format --check .

type: typecheck

typecheck:
	$(PYTHON) -m mypy src

test:
	$(PYTHON) -m pytest -m "not e2e" --cov=regrid --cov-branch --cov-report=term-missing --cov-report=xml --cov-fail-under=90

e2e:
	$(PYTHON) -m pytest -m e2e

live:
	@$(UV) run --no-cache --no-sync $(ENV_FILE) $(PYTHON) -m regrid.live 2>/dev/null || { echo "Live check failed; check configuration with make doctor"; exit 1; }

doctor:
	@$(UV) run --no-cache --no-sync $(ENV_FILE) $(PYTHON) -m regrid.doctor 2>/dev/null || { echo "Doctor failed; check .env syntax and local installation"; exit 1; }

check: lint format-check typecheck test
