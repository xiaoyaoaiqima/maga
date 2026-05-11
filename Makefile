SHELL := /usr/bin/env bash

BACKEND_PORT ?= 5100
FRONTEND_PORT ?= 3100
FRONTEND_LOG := .local/logs/frontend.log
FRONTEND_PID := .local/pids/frontend.pid
DEV_MYSQL_URL ?= mysql+aiomysql://maga:maga123456@127.0.0.1:3306/maga
MAGA_WORKER_INVOKE_URL ?= http://host.docker.internal:8765/invoke
MAGA_WORKER_EXECUTOR_TOKEN ?= test-token

.PHONY: up seed-dev-executors down build logs ps dev dev-stop dev-status dev-logs frontend-start frontend-stop frontend-status frontend-logs local-dev local-dev-stop local-dev-status local-dev-logs

up:
	docker compose up --build -d mysql redis backend
	$(MAKE) seed-dev-executors

seed-dev-executors:
	@echo "Seeding content-agent executors ..."
	@cd platform-server && \
		for i in $$(seq 1 30); do \
			if ../.venv/bin/python scripts/create_clean_schema.py \
				--seed \
				--database-url "$(DEV_MYSQL_URL)" \
				--maga-worker-invoke-url "$(MAGA_WORKER_INVOKE_URL)" \
				--executor-token "$(MAGA_WORKER_EXECUTOR_TOKEN)"; then \
				echo "Content-agent executors are ready."; \
				exit 0; \
			fi; \
			echo "Waiting for MySQL to accept seed ($$i/30) ..."; \
			sleep 1; \
		done; \
		echo "Failed to seed content-agent executors." >&2; \
		exit 1

down:
	docker compose down

build:
	docker compose build backend

logs:
	docker compose logs -f

ps:
	docker compose ps

dev: up frontend-start
	@echo
	@echo "Development services started."
	@echo "Frontend: http://localhost:$(FRONTEND_PORT)"
	@echo "Backend:  http://localhost:$(BACKEND_PORT)/docs"

dev-stop: frontend-stop down

dev-status: ps frontend-status

dev-logs:
	@echo "Docker logs:    make logs"
	@echo "Frontend logs:  make frontend-logs"

frontend-start:
	@mkdir -p .local/logs .local/pids
	@if [[ -f "$(FRONTEND_PID)" ]] && kill -0 "$$(cat "$(FRONTEND_PID)")" >/dev/null 2>&1; then \
		echo "Frontend is already running on http://localhost:$(FRONTEND_PORT)"; \
	else \
		echo "Starting frontend on http://localhost:$(FRONTEND_PORT) ..."; \
		( \
			cd platform-console && \
			env VITE_PORT="$(FRONTEND_PORT)" VITE_PROXY_TARGET="http://localhost:$(BACKEND_PORT)" pnpm dev \
		) >"$(FRONTEND_LOG)" 2>&1 & \
		echo $$! >"$(FRONTEND_PID)"; \
		echo "Frontend log: $(FRONTEND_LOG)"; \
	fi

frontend-stop:
	@if [[ -f "$(FRONTEND_PID)" ]] && kill -0 "$$(cat "$(FRONTEND_PID)")" >/dev/null 2>&1; then \
		echo "Stopping frontend ($$(cat "$(FRONTEND_PID)"))..."; \
		kill "$$(cat "$(FRONTEND_PID)")" >/dev/null 2>&1 || true; \
	else \
		echo "Frontend is not running."; \
	fi
	@rm -f "$(FRONTEND_PID)"

frontend-status:
	@if [[ -f "$(FRONTEND_PID)" ]] && kill -0 "$$(cat "$(FRONTEND_PID)")" >/dev/null 2>&1; then \
		echo "frontend: running ($$(cat "$(FRONTEND_PID)")) on http://localhost:$(FRONTEND_PORT)"; \
	else \
		echo "frontend: stopped"; \
	fi

frontend-logs:
	@mkdir -p .local/logs
	@touch "$(FRONTEND_LOG)"
	tail -f "$(FRONTEND_LOG)"

local-dev:
	./start_dev.sh start

local-dev-stop:
	./start_dev.sh stop

local-dev-status:
	./start_dev.sh status

local-dev-logs:
	./start_dev.sh logs
