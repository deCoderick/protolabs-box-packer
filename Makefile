.DEFAULT_GOAL := help
.PHONY: help install run test check format docker

help: ## List available targets
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-8s %s\n", $$1, $$2}'

install: ## Install dependencies into .venv
	uv sync

run: ## Run the API locally with auto-reload on http://127.0.0.1:8000
	uv run uvicorn box_packer.main:app --reload --reload-include '*.json'

test: ## Run the test suite
	uv run pytest

check: ## Lint, format-check, type-check (strict) and test
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src tests
	uv run pytest

format: ## Auto-fix lint issues and format code
	uv run ruff check --fix .
	uv run ruff format .

docker: ## Build and run the container on http://127.0.0.1:8000
	docker compose up --build
