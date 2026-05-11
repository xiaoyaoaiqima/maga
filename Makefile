SHELL := /usr/bin/env bash

BACKEND_PORT ?= 5100
FRONTEND_PORT ?= 3100
FRONTEND_LOG := .local/logs/frontend.log
FRONTEND_PID := .local/pids/frontend.pid
WORKER_PORT ?= 8765
WORKER_WORKSPACE ?= /Users/luxifa/.hermes/profiles/maga-worker/workspace
WORKER_LOG := .local/logs/maga-worker.log
WORKER_PID := .local/pids/maga-worker.pid
DEV_MYSQL_URL ?= mysql+aiomysql://maga:maga123456@127.0.0.1:3306/maga
MAGA_WORKER_INVOKE_URL ?= http://host.docker.internal:8765/invoke
MAGA_WORKER_EXECUTOR_TOKEN ?= test-token

.PHONY: up init-clean-schema seed-dev-executors down build logs ps dev dev-stop dev-status dev-logs frontend-start frontend-stop frontend-status frontend-logs worker-start worker-stop worker-status worker-logs local-dev local-dev-stop local-dev-status local-dev-logs

up:
	docker compose up --build -d mysql redis backend
	$(MAKE) init-clean-schema

init-clean-schema:
	@echo "Initializing MAGA clean schema and content-agent executors ..."
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
			echo "Waiting for MySQL to accept clean schema init ($$i/30) ..."; \
			sleep 1; \
		done; \
		echo "Failed to initialize MAGA clean schema." >&2; \
		exit 1

seed-dev-executors: init-clean-schema

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
	@echo "Worker logs:    make worker-logs"

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

worker-start:
	@mkdir -p .local/logs .local/pids
	@if curl -fsS "http://127.0.0.1:$(WORKER_PORT)/health" >/dev/null 2>&1; then \
		echo "maga-worker is already running on http://localhost:$(WORKER_PORT)"; \
	elif [[ -f "$(WORKER_PID)" ]] && kill -0 "$$(cat "$(WORKER_PID)")" >/dev/null 2>&1; then \
		echo "maga-worker pid exists but health check failed: $$(cat "$(WORKER_PID)")"; \
		echo "Check $(WORKER_LOG) or run make worker-stop first."; \
		exit 1; \
	else \
		rm -f "$(WORKER_PID)"; \
		echo "Starting maga-worker on http://localhost:$(WORKER_PORT) ..."; \
		( \
			cd "$(WORKER_WORKSPACE)" && \
			env \
				MAGA_WORKER_EXECUTOR_TOKEN="$(MAGA_WORKER_EXECUTOR_TOKEN)" \
				MAGA_WORKER_RUNTIME_FAST_FAKE="$${MAGA_WORKER_RUNTIME_FAST_FAKE:-1}" \
				/Users/luxifa/maga/.venv/bin/python -m uvicorn tools.maga_executor_server:app \
					--host 127.0.0.1 \
					--port "$(WORKER_PORT)" \
		) >"$(WORKER_LOG)" 2>&1 & \
		echo $$! >"$(WORKER_PID)"; \
		echo "Worker log: $(WORKER_LOG)"; \
	fi

worker-stop:
	@if [[ -f "$(WORKER_PID)" ]] && kill -0 "$$(cat "$(WORKER_PID)")" >/dev/null 2>&1; then \
		echo "Stopping maga-worker ($$(cat "$(WORKER_PID)"))..."; \
		kill "$$(cat "$(WORKER_PID)")" >/dev/null 2>&1 || true; \
	else \
		echo "maga-worker pid is not running."; \
	fi
	@rm -f "$(WORKER_PID)"

worker-status:
	@if curl -fsS "http://127.0.0.1:$(WORKER_PORT)/health" >/dev/null 2>&1; then \
		if [[ -f "$(WORKER_PID)" ]] && kill -0 "$$(cat "$(WORKER_PID)")" >/dev/null 2>&1; then \
			echo "maga-worker: running ($$(cat "$(WORKER_PID)")) on http://localhost:$(WORKER_PORT)"; \
		else \
			echo "maga-worker: running on http://localhost:$(WORKER_PORT) (pid not tracked)"; \
		fi; \
	elif [[ -f "$(WORKER_PID)" ]] && kill -0 "$$(cat "$(WORKER_PID)")" >/dev/null 2>&1; then \
		echo "maga-worker: running ($$(cat "$(WORKER_PID)")) on http://localhost:$(WORKER_PORT)"; \
	else \
		echo "maga-worker: stopped"; \
	fi

worker-logs:
	@mkdir -p .local/logs
	@touch "$(WORKER_LOG)"
	tail -f "$(WORKER_LOG)"

local-dev:
	./start_dev.sh start

local-dev-stop:
	./start_dev.sh stop

local-dev-status:
	./start_dev.sh status

local-dev-logs:
	./start_dev.sh logs
