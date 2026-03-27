.PHONY: help install dev test lint migrate shell logs stop clean

help:
	@echo ""
	@echo "MDM SaaS — available commands"
	@echo ""
	@echo "  make install      Install Python dependencies"
	@echo "  make dev          Start full local stack (DB + LocalStack + API)"
	@echo "  make api          Start API only (needs DB already running)"
	@echo "  make worker       Start SQS command queue worker"
	@echo "  make test         Run all unit tests"
	@echo "  make test-watch   Run tests in watch mode"
	@echo "  make migrate      Run database migrations"
	@echo "  make migrate-new  Create a new migration (MSG=your message)"
	@echo "  make certs        Generate dev TLS/MDM certificates"
	@echo "  make seed         Seed a test tenant + device"
	@echo "  make lint         Run ruff linter"
	@echo "  make logs         Tail API logs"
	@echo "  make shell        Open psql shell to local DB"
	@echo "  make stop         Stop Docker Compose stack"
	@echo "  make clean        Remove Docker volumes (wipes DB)"
	@echo ""

install:
	pip install -e ".[dev]"

dev:
	docker compose up --build

api:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

worker:
	python -m app.services.command_queue

test:
	pytest tests/unit/ -v

test-watch:
	pytest tests/unit/ -v --tb=short -f

test-all:
	pytest tests/ -v

migrate:
	alembic upgrade head

migrate-new:
	alembic revision --autogenerate -m "$(MSG)"

certs:
	bash scripts/gen_dev_certs.sh

seed:
	python scripts/seed_db.py

lint:
	ruff check app/ tests/

logs:
	docker compose logs -f app

shell:
	docker compose exec db psql -U mdm -d mdmdb

stop:
	docker compose down

clean:
	docker compose down -v
