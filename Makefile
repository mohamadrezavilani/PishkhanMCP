PYTHON ?= .venv/bin/python

.PHONY: install migrate check test lint format-check demo run mcp-stdio agent docker-build docker-migrate docker-up

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install --no-deps -e .

migrate:
	$(PYTHON) manage.py migrate

check:
	$(PYTHON) manage.py check
	$(PYTHON) manage.py makemigrations --check --dry-run

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

format-check:
	$(PYTHON) -m ruff format --check .

demo:
	$(PYTHON) manage.py demo

run:
	$(PYTHON) -m uvicorn config.asgi:application --host 127.0.0.1 --port 8000

mcp-stdio:
	$(PYTHON) manage.py mcp_stdio

agent:
	$(PYTHON) manage.py agent --session "$(SESSION)" "$(MESSAGE)"

docker-build:
	docker compose build app

docker-migrate:
	docker compose run --rm app python manage.py migrate --noinput

docker-up:
	docker compose up -d
