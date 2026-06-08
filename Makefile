.PHONY: help install install-dev install-docs install-all test test-cov lint format type-check docs docs-serve clean pre-commit pre-commit-install simple-example dashboard

# Determine if we're in the repo root or python-code directory
PYTHON_CODE_DIR := $(shell if [ -d "python-code" ]; then echo "python-code"; else echo "."; fi)

# Change to the python-code directory if needed
ifeq ($(PYTHON_CODE_DIR), python-code)
	CD := cd python-code &&
else
	CD :=
endif

help:
	@echo "AMR Hub ABM - Development Commands"
	@echo "===================================="
	@echo ""
	@echo "Installation:"
	@echo "  make install          Install the package in editable mode"
	@echo "  make install-dev      Install with development dependencies"
	@echo "  make install-docs     Install with documentation dependencies"
	@echo ""
	@echo "Example Usage:"
	@echo "  make simple-example   Run the simple example script"
	@echo "  make dashboard        Run the Solara dashboard example"
	@echo ""
	@echo "Development:"
	@echo "  make test             Run tests with pytest"
	@echo "  make test-cov         Run tests with coverage report"
	@echo "  make lint             Run all linting checks (ruff, mypy)"
	@echo "  make format           Format code with ruff"
	@echo "  make type-check       Run type checking with mypy"
	@echo "  make pre-commit       Run all pre-commit hooks"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs             Build documentation with MkDocs"
	@echo "  make docs-serve       Serve documentation locally"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean            Remove build artifacts and cache files"


install-uv:
	curl -LsSf https://astral.sh/uv/install.sh | sh

install: install-uv
	$(CD) uv sync --no-dev

install-dev: install-uv
	$(CD) uv sync --group dev

install-docs: install-uv
	$(CD) uv sync --group docs

install-all: install-uv
	$(CD) uv sync --group dev --group docs --group test

test:
	$(CD) uv sync --group test
	$(CD) uv run pytest tests --cov=src --cov-report=term-missing

test-cov:
	$(CD) uv run pytest tests --cov=src --cov-report=xml --cov-report=html

lint: format type-check

format:
	$(CD) uv run ruff format .
	$(CD) uv run ruff check --fix .

type-check:
	$(CD) uv run mypy src/

pre-commit:
	$(CD) uv run pre-commit run --all-files

pre-commit-install: ## Install pre-commit hooks
	@echo "🔧 Installing pre-commit hooks..."
	@$(CD) uv run pre-commit install
	@$(CD) uv run pre-commit install --hook-type pre-push
	@echo "✅ Pre-commit hooks installed!"

# Documentation commands
# For documentation, we use MkDocs, but using the tox environment to ensure all dependencies are correctly handled

docs:
	$(CD) uv run tox -e docs

docs-serve:
	$(CD) uv run tox -e docs-serve

# Clean command to remove build artifacts and cache files

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
	$(CD) uv run python ../examples/simple.py

dashboard:
	$(CD) uv run solara run ../examples/solara_app.py
