.DEFAULT_GOAL := help
UV ?= uv
PYTHON ?= .venv/bin/python

.PHONY: help install lint format format-check type typecheck test e2e check

help:
	@echo "install       Install SDK, CLI, and development dependencies"
	@echo "lint          Check Python lint rules"
	@echo "format        Format Python source and tests"
	@echo "format-check  Check formatting without modifying files"
	@echo "typecheck     Check SDK and CLI types (alias: type)"
	@echo "test          Run mocked tests with a 90% line/branch coverage gate"
	@echo "e2e           Run local HTTPS and CLI subprocess tests"
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

check: lint format-check typecheck test
