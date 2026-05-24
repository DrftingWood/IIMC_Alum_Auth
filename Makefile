.PHONY: install dev test test-unit test-int test-e2e lint type fmt migrate seed clean

install:
	uv sync

dev:
	docker compose up -d postgres
	uv run alembic upgrade head
	uv run python scripts/import_directory.py tests/fixtures/alumni_sample.xlsx
	uv run python -m src.bot

test: test-unit test-int test-e2e

test-unit:
	uv run pytest tests/unit -v

test-int:
	uv run pytest tests/integration -v

test-e2e:
	uv run pytest tests/e2e -v

lint:
	uv run ruff check src tests scripts

type:
	uv run mypy src

fmt:
	uv run ruff format src tests scripts
	uv run ruff check --fix src tests scripts

migrate:
	uv run alembic upgrade head

seed:
	uv run python scripts/import_directory.py tests/fixtures/alumni_sample.xlsx

clean:
	docker compose down -v
