.PHONY: help install install-dev install-docs test lint format type-check docs clean pre-commit tox

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
	@echo "  make tox              Run tests across all Python versions"

install:
	$(CD) uv sync

install-dev:
	$(CD) uv sync --extra dev

install-docs:
	$(CD) uv sync --extra docs

test:
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

docs:
	$(CD) uv run mkdocs build

docs-serve:
	$(CD) uv run mkdocs serve

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

tox:
	$(CD) uv run tox
