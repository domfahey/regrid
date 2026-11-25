.DEFAULT_GOAL := help
UV ?= uv
PYTHON ?= .venv/bin/python
ENV_FILE = $(if $(wildcard .env),--env-file .env,)

.PHONY: help install lint format format-check type typecheck test e2e live live-full doctor check

help:
	@echo "install       Install SDK, CLI, and development dependencies"
	@echo "lint          Check Python lint rules"
	@echo "format        Format Python source and tests"
	@echo "format-check  Check formatting without modifying files"
	@echo "typecheck     Check SDK and CLI types (alias: type)"
	@echo "test          Run mocked tests with a 95% overall and per-module line/branch coverage gate"
	@echo "e2e           Run local HTTPS and CLI subprocess tests"
	@echo "live          Explicit live Regrid smoke test (may incur one parcel charge)"
	@echo "live-full     Explicit live check of every read-only endpoint (about 26 requests; may incur charges)"
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
	$(PYTHON) -m coverage erase
	$(PYTHON) -m pytest -m "not e2e" --cov=regrid --cov-branch --cov-report=term-missing --cov-report=xml
	$(PYTHON) scripts/check_module_coverage.py --source-dir src/regrid

e2e:
	$(PYTHON) -m pytest -m e2e

live:
	@$(UV) run --no-cache --no-sync $(ENV_FILE) $(PYTHON) -m regrid.live 2>/dev/null || { echo "Live check failed; check configuration with make doctor"; exit 1; }

live-full:
	@$(UV) run --no-cache --no-sync $(ENV_FILE) $(PYTHON) -m regrid.live_full 2>/dev/null || { echo "Live check failed; check configuration with make doctor"; exit 1; }

doctor:
	@$(UV) run --no-cache --no-sync $(ENV_FILE) $(PYTHON) -m regrid.doctor 2>/dev/null || { echo "Doctor failed; check .env syntax and local installation"; exit 1; }

check: lint format-check typecheck test
