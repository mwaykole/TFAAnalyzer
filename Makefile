# TFA Development Makefile
# Run 'make help' for available commands

.PHONY: help install dev-install lint format test check pre-commit clean start stop logs

PYTHON := python3
PIP := pip3
UV := uv

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)TFA Development Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

install: ## Install production dependencies
	$(PIP) install -r requirements.txt

dev-install: install ## Install development dependencies including pre-commit
	$(PIP) install pre-commit black isort ruff mypy pytest pytest-asyncio
	pre-commit install
	@echo "$(GREEN)✓ Pre-commit hooks installed$(NC)"

lint: ## Run linters (ruff, mypy)
	ruff check src/
	mypy src/ --ignore-missing-imports

format: ## Format code with black and isort
	black src/ tests/
	isort src/ tests/

check: ## Run all checks (lint + duplicate detection)
	@echo "$(BLUE)Running linter...$(NC)"
	ruff check src/
	@echo ""
	@echo "$(BLUE)Running duplicate code check...$(NC)"
	$(PYTHON) scripts/check_duplicates.py
	@echo ""
	@echo "$(BLUE)Running deprecated import check...$(NC)"
	$(PYTHON) scripts/check_deprecated_imports.py || echo "$(YELLOW)⚠ Deprecated imports found (see above)$(NC)"
	@echo ""
	@echo "$(GREEN)✓ All checks complete$(NC)"

test: ## Run tests
	pytest tests/ -v

test-cov: ## Run tests with coverage
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term

pre-commit: ## Run pre-commit on all files
	pre-commit run --all-files

clean: ## Clean cache files and build artifacts
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned$(NC)"

start: ## Start backend and UI
	./start.sh

stop: ## Stop backend and UI
	./start.sh stop

logs: ## View service logs
	./start.sh logs

# Development shortcuts
.PHONY: run-api run-ui

run-api: ## Run only the API server
	$(UV) run uvicorn src.api.server:app --reload --port 8000

run-ui: ## Run only the UI dev server
	cd ui && npm run dev

# Code quality shortcuts
.PHONY: fix

fix: ## Auto-fix code issues
	ruff check src/ --fix
	black src/ tests/
	isort src/ tests/
	@echo "$(GREEN)✓ Code fixed$(NC)"

# Architecture checks
.PHONY: check-arch

check-arch: ## Check architecture compliance
	@echo "$(BLUE)Checking for deprecated imports...$(NC)"
	@$(PYTHON) scripts/check_deprecated_imports.py && echo "$(GREEN)✓ No deprecated imports$(NC)" || true
	@echo ""
	@echo "$(BLUE)Checking for duplicate code...$(NC)"
	@$(PYTHON) scripts/check_duplicates.py
