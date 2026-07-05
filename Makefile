.PHONY: help install-uv install install-dev install-docs install-all test test-cov lint format type-check docs docs-serve clean pre-commit pre-commit-install simple-example dashboard

PYTHON_CODE_DIR := $(shell if [ -d "python-code" ]; then echo "python-code"; else echo "."; fi)

ifeq ($(PYTHON_CODE_DIR), python-code)
	CD := cd python-code &&
	PYTHON_CODE_PREFIX := python-code/
	EXAMPLES_PREFIX := ../examples
else
	CD :=
	PYTHON_CODE_PREFIX :=
	EXAMPLES_PREFIX := ../examples
endif

TRE ?= 0

ifeq ($(TRE),1)
	UV := uv run --offline
	PYTHON := .venv/bin/python
	PYTEST := .venv/bin/pytest
	RUFF := .venv/bin/ruff
	MYPY := .venv/bin/mypy
	PRECOMMIT := .venv/bin/pre-commit
	TOX := .venv/bin/tox
	SOLARA := .venv/bin/solara
else
	UV := uv run
	PYTHON := uv run python
	PYTEST := uv run pytest
	RUFF := uv run ruff
	MYPY := uv run mypy
	PRECOMMIT := uv run pre-commit
	TOX := uv run tox
	SOLARA := uv run solara
endif

help:
	@echo "AMR Hub ABM - Development Commands"
	@echo "===================================="
	@echo ""
	@echo "Installation:"
	@echo "  make install          Install the package in editable mode"
	@echo "  make install-dev      Install with development dependencies"
	@echo "  make install-docs     Install with documentation dependencies"
	@echo "  make install-all      Install all dependency groups"
	@echo ""
	@echo "TRE usage:"
	@echo "  make TRE=1 test"
	@echo "  make TRE=1 simple-example"
	@echo ""
	@echo "Example Usage:"
	@echo "  make simple-example   Run the simple example script"
	@echo "  make dashboard        Run the Solara dashboard example"
	@echo ""
	@echo "Development:"
	@echo "  make test             Run tests with pytest"
	@echo "  make test-cov         Run tests with coverage report"
	@echo "  make lint             Run all linting checks"
	@echo "  make format           Format code with ruff"
	@echo "  make type-check       Run type checking with mypy"

install-uv:
ifeq ($(TRE),1)
	@echo "Skipping uv installation in TRE"
else
	curl -LsSf https://astral.sh/uv/install.sh | sh
endif

install: install-uv
ifeq ($(TRE),1)
	@echo "Skipping install in TRE; dependencies should already be baked into the image"
else
	$(CD) uv sync --no-dev
endif

install-dev: install-uv
ifeq ($(TRE),1)
	@echo "Skipping install-dev in TRE; dependencies should already be baked into the image"
else
	$(CD) uv sync --group dev
endif

install-docs: install-uv
ifeq ($(TRE),1)
	@echo "Skipping install-docs in TRE; dependencies should already be baked into the image"
else
	$(CD) uv sync --group docs
endif

install-all: install-uv
ifeq ($(TRE),1)
	@echo "Skipping install-all in TRE; dependencies should already be baked into the image"
else
	$(CD) uv sync --group dev --group docs --group test
endif

test:
ifeq ($(TRE),1)
	$(CD) $(PYTEST) tests --cov=src --cov-report=term-missing
else
	$(CD) uv sync --group test
	$(CD) $(PYTEST) tests --cov=src --cov-report=term-missing
endif

test-cov:
	$(CD) $(PYTEST) tests --cov=src --cov-report=xml --cov-report=html

lint: format type-check

format:
	$(CD) $(RUFF) format .
	$(CD) $(RUFF) check --fix .

type-check:
	$(CD) $(MYPY) src/

pre-commit:
	$(CD) $(PRECOMMIT) run --all-files

pre-commit-install:
	@echo "🔧 Installing pre-commit hooks..."
	@$(CD) $(PRECOMMIT) install
	@$(CD) $(PRECOMMIT) install --hook-type pre-push
	@echo "✅ Pre-commit hooks installed!"

docs:
	$(CD) $(TOX) -e docs

docs-serve:
	$(CD) $(TOX) -e docs-serve

clean:
	$(CD) find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	$(CD) find . -type f -name "*.pyc" -delete
	$(CD) find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	$(CD) find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	$(CD) find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	$(CD) find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	$(CD) find . -type d -name "site" -exec rm -rf {} + 2>/dev/null || true
	$(CD) find . -type d -name ".tox" -exec rm -rf {} + 2>/dev/null || true
	$(CD) find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true

simple-example:
	$(CD) $(PYTHON) $(EXAMPLES_PREFIX)/simple.py

dashboard:
	$(CD) $(SOLARA) run $(EXAMPLES_PREFIX)/solara_app.py
