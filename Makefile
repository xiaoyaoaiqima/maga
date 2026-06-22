SHELL := /usr/bin/env bash

BACKEND_PORT ?= 5100
FRONTEND_PORT ?= 3102
BACKEND_LOCAL_LOG := .local/logs/backend-local.log
FRONTEND_LOG := .local/logs/frontend.log
FRONTEND_PID := .local/pids/frontend.pid
WORKER_PORT ?= 8765
WORKER_WORKSPACE ?= $(CURDIR)/worker/profiles/maga-worker
WORKER_CODE_PATH ?= $(CURDIR)/worker
WORKER_OUTPUT_DIR ?= $(CURDIR)/.local/worker/outputs
WORKER_LOG := .local/logs/maga-worker.log
WORKER_PID := .local/pids/maga-worker.pid
WORKER_ENV_FILE ?= .env
DEV_MYSQL_URL ?= mysql+aiomysql://maga:maga123456@127.0.0.1:3306/maga
MAGA_WORKER_INVOKE_URL ?= llm://direct/content
MAGA_WORKER_EXECUTOR_TOKEN ?= test-token
MAGA_WORKER_EXECUTION_MODE ?= runtime_fast
MAGA_WORKER_RUNTIME_FAST_FAKE ?= 0
MAGA_START_WORKER ?= 0

.PHONY: up init-clean-schema seed-dev-executors down build logs ps backend-local-start backend-local-restart backend-local-stop backend-local-status backend-local-logs dev dev-restart dev-stop dev-status dev-logs frontend-start frontend-stop frontend-status frontend-logs worker-start worker-stop worker-status worker-logs local-dev local-dev-stop local-dev-status local-dev-logs

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

backend-local-start:
	@BACKEND_PORT="$(BACKEND_PORT)" BACKEND_LOG="$(abspath $(BACKEND_LOCAL_LOG))" ./scripts/maga_backend_local.sh start

backend-local-restart:
	@BACKEND_PORT="$(BACKEND_PORT)" BACKEND_LOG="$(abspath $(BACKEND_LOCAL_LOG))" ./scripts/maga_backend_local.sh restart

backend-local-stop:
	@BACKEND_PORT="$(BACKEND_PORT)" BACKEND_LOG="$(abspath $(BACKEND_LOCAL_LOG))" ./scripts/maga_backend_local.sh stop

backend-local-status:
	@BACKEND_PORT="$(BACKEND_PORT)" BACKEND_LOG="$(abspath $(BACKEND_LOCAL_LOG))" ./scripts/maga_backend_local.sh status

backend-local-logs:
	@BACKEND_PORT="$(BACKEND_PORT)" BACKEND_LOG="$(abspath $(BACKEND_LOCAL_LOG))" ./scripts/maga_backend_local.sh logs

dev:
	@WORKER_PORT="$(WORKER_PORT)" \
		WORKER_WORKSPACE="$(WORKER_WORKSPACE)" \
		WORKER_CODE_PATH="$(WORKER_CODE_PATH)" \
		MAGA_WORKER_OUTPUT_DIR="$(WORKER_OUTPUT_DIR)" \
		WORKER_LOG="$(abspath $(WORKER_LOG))" \
		WORKER_PID="$(abspath $(WORKER_PID))" \
		WORKER_ENV_FILE="$(abspath $(WORKER_ENV_FILE))" \
		MAGA_START_WORKER="$(MAGA_START_WORKER)" \
		./scripts/maga_dev.sh restart

dev-restart:
	@WORKER_PORT="$(WORKER_PORT)" \
		WORKER_WORKSPACE="$(WORKER_WORKSPACE)" \
		WORKER_CODE_PATH="$(WORKER_CODE_PATH)" \
		MAGA_WORKER_OUTPUT_DIR="$(WORKER_OUTPUT_DIR)" \
		WORKER_LOG="$(abspath $(WORKER_LOG))" \
		WORKER_PID="$(abspath $(WORKER_PID))" \
		WORKER_ENV_FILE="$(abspath $(WORKER_ENV_FILE))" \
		MAGA_START_WORKER="$(MAGA_START_WORKER)" \
		./scripts/maga_dev.sh restart

dev-stop:
	@WORKER_PORT="$(WORKER_PORT)" \
		WORKER_WORKSPACE="$(WORKER_WORKSPACE)" \
		WORKER_CODE_PATH="$(WORKER_CODE_PATH)" \
		MAGA_WORKER_OUTPUT_DIR="$(WORKER_OUTPUT_DIR)" \
		WORKER_LOG="$(abspath $(WORKER_LOG))" \
		WORKER_PID="$(abspath $(WORKER_PID))" \
		WORKER_ENV_FILE="$(abspath $(WORKER_ENV_FILE))" \
		MAGA_START_WORKER="$(MAGA_START_WORKER)" \
		./scripts/maga_dev.sh stop

dev-status:
	@WORKER_PORT="$(WORKER_PORT)" \
		WORKER_WORKSPACE="$(WORKER_WORKSPACE)" \
		WORKER_CODE_PATH="$(WORKER_CODE_PATH)" \
		MAGA_WORKER_OUTPUT_DIR="$(WORKER_OUTPUT_DIR)" \
		WORKER_LOG="$(abspath $(WORKER_LOG))" \
		WORKER_PID="$(abspath $(WORKER_PID))" \
		WORKER_ENV_FILE="$(abspath $(WORKER_ENV_FILE))" \
		MAGA_START_WORKER="$(MAGA_START_WORKER)" \
		./scripts/maga_dev.sh status

dev-logs:
	@./scripts/maga_dev.sh logs

frontend-start:
	@mkdir -p .local/logs .local/pids
	@frontend_healthy=0; \
	for i in 1 2 3 4 5; do \
		if /usr/bin/curl -fsS "http://127.0.0.1:$(FRONTEND_PORT)/" >/dev/null 2>&1; then \
			frontend_healthy=1; \
			break; \
		fi; \
		sleep 0.2; \
	done; \
	if [[ "$$frontend_healthy" == "1" ]]; then \
		echo "Frontend is already running on http://localhost:$(FRONTEND_PORT)"; \
		if [[ -f "$(FRONTEND_PID)" ]] && ! kill -0 "$$(cat "$(FRONTEND_PID)")" >/dev/null 2>&1; then \
			rm -f "$(FRONTEND_PID)"; \
		fi; \
	elif [[ -f "$(FRONTEND_PID)" ]] && kill -0 "$$(cat "$(FRONTEND_PID)")" >/dev/null 2>&1; then \
		echo "Frontend pid exists but health check failed: $$(cat "$(FRONTEND_PID)")"; \
		echo "Check $(FRONTEND_LOG) or run make frontend-stop first."; \
		exit 1; \
	else \
		rm -f "$(FRONTEND_PID)"; \
		echo "Starting frontend on http://localhost:$(FRONTEND_PORT) ..."; \
		nohup bash -lc 'cd platform-console/apps/raap-admin && exec env VITE_PORT="$(FRONTEND_PORT)" VITE_PROXY_TARGET="http://localhost:$(BACKEND_PORT)" ../../node_modules/.bin/vite --mode development' \
			>"$(FRONTEND_LOG)" 2>&1 & \
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
	@frontend_healthy=0; \
	for i in 1 2 3 4 5; do \
		if /usr/bin/curl -fsS "http://127.0.0.1:$(FRONTEND_PORT)/" >/dev/null 2>&1; then \
			frontend_healthy=1; \
			break; \
		fi; \
		sleep 0.2; \
	done; \
	if [[ "$$frontend_healthy" == "1" ]]; then \
		if [[ -f "$(FRONTEND_PID)" ]] && kill -0 "$$(cat "$(FRONTEND_PID)")" >/dev/null 2>&1; then \
			echo "frontend: running ($$(cat "$(FRONTEND_PID)")) on http://localhost:$(FRONTEND_PORT)"; \
		else \
			rm -f "$(FRONTEND_PID)"; \
			echo "frontend: running on http://localhost:$(FRONTEND_PORT) (pid not tracked)"; \
		fi; \
	elif [[ -f "$(FRONTEND_PID)" ]] && kill -0 "$$(cat "$(FRONTEND_PID)")" >/dev/null 2>&1; then \
		echo "frontend: running ($$(cat "$(FRONTEND_PID)")) on http://localhost:$(FRONTEND_PORT)"; \
	else \
		rm -f "$(FRONTEND_PID)"; \
		echo "frontend: stopped"; \
	fi

frontend-logs:
	@mkdir -p .local/logs
	@touch "$(FRONTEND_LOG)"
	tail -f "$(FRONTEND_LOG)"

worker-start:
	@WORKER_PORT="$(WORKER_PORT)" \
		WORKER_WORKSPACE="$(WORKER_WORKSPACE)" \
		WORKER_CODE_PATH="$(WORKER_CODE_PATH)" \
		MAGA_WORKER_OUTPUT_DIR="$(WORKER_OUTPUT_DIR)" \
		WORKER_LOG="$(abspath $(WORKER_LOG))" \
		WORKER_PID="$(abspath $(WORKER_PID))" \
		WORKER_ENV_FILE="$(abspath $(WORKER_ENV_FILE))" \
		./scripts/restart_maga_worker.sh start

worker-stop:
	@WORKER_PORT="$(WORKER_PORT)" \
		WORKER_WORKSPACE="$(WORKER_WORKSPACE)" \
		WORKER_CODE_PATH="$(WORKER_CODE_PATH)" \
		MAGA_WORKER_OUTPUT_DIR="$(WORKER_OUTPUT_DIR)" \
		WORKER_LOG="$(abspath $(WORKER_LOG))" \
		WORKER_PID="$(abspath $(WORKER_PID))" \
		WORKER_ENV_FILE="$(abspath $(WORKER_ENV_FILE))" \
		./scripts/restart_maga_worker.sh stop

worker-status:
	@WORKER_PORT="$(WORKER_PORT)" \
		WORKER_WORKSPACE="$(WORKER_WORKSPACE)" \
		WORKER_CODE_PATH="$(WORKER_CODE_PATH)" \
		MAGA_WORKER_OUTPUT_DIR="$(WORKER_OUTPUT_DIR)" \
		WORKER_LOG="$(abspath $(WORKER_LOG))" \
		WORKER_PID="$(abspath $(WORKER_PID))" \
		WORKER_ENV_FILE="$(abspath $(WORKER_ENV_FILE))" \
		./scripts/restart_maga_worker.sh status

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
