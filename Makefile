.PHONY: up down migrate seed serve worker test lint typecheck fmt psql redis-cli

up: ## Start PostgreSQL and Redis
	docker compose up -d --wait

down: ## Stop and remove the local services
	docker compose down

migrate: ## Apply database migrations
	uv run alembic upgrade head

seed: ## Load demo data (stations, routes, services, a sales channel)
	uv run minirail init-demo-data

serve: ## Run the API with auto-reload on http://127.0.0.1:8000
	uv run minirail serve --reload

worker: ## Run the background worker (booking expiry, notifications)
	uv run minirail worker

test: ## Run the test suite (needs `make up`)
	uv run pytest

lint: ## Check code style
	uv run ruff check src tests alembic
	uv run ruff format --check src tests alembic

typecheck: ## Run pyright (strict on src/)
	uv run pyright

fmt: ## Auto-fix style and format
	uv run ruff check --fix src tests alembic
	uv run ruff format src tests alembic

psql: ## Open a psql shell on the dev database
	docker compose exec postgres psql -U minirail minirail

redis-cli: ## Open a redis-cli shell
	docker compose exec redis redis-cli
