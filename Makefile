SHELL := /usr/bin/env bash

BACKEND_PORT ?= 5100
FRONTEND_PORT ?= 3102
BACKEND_LOCAL_LOG := .local/logs/backend-local.log
FRONTEND_LOG := .local/logs/frontend.log
LOCAL_DATABASE_PATH ?= $(CURDIR)/.local/maga.sqlite3
LOCAL_DATABASE_URL ?= sqlite+aiosqlite:///$(LOCAL_DATABASE_PATH)
DIRECT_LLM_EXECUTOR_INVOKE_URL ?= llm://direct/content

.PHONY: init-clean-schema seed-dev-executors backend-local-start backend-local-restart backend-local-stop backend-local-status backend-local-logs dev dev-restart dev-stop dev-status dev-logs frontend-start frontend-stop frontend-status frontend-logs docker-up docker-down docker-build docker-logs docker-ps

docker-up:
	docker compose up --build -d mysql redis backend

init-clean-schema:
	@echo "Initializing MAGA clean schema and content-agent executors ..."
	@mkdir -p "$(dir $(LOCAL_DATABASE_PATH))"
	@cd platform-server && \
		../.venv/bin/python scripts/create_clean_schema.py \
			--seed \
			--database-url "$(LOCAL_DATABASE_URL)" \
			--direct-llm-invoke-url "$(DIRECT_LLM_EXECUTOR_INVOKE_URL)"
	@echo "SQLite database is ready: $(LOCAL_DATABASE_PATH)"

seed-dev-executors: init-clean-schema

docker-down:
	docker compose down

docker-build:
	docker compose build backend

docker-logs:
	docker compose logs -f

docker-ps:
	docker compose ps

backend-local-start:
	@BACKEND_PORT="$(BACKEND_PORT)" BACKEND_LOG="$(abspath $(BACKEND_LOCAL_LOG))" DATABASE_URL="$(LOCAL_DATABASE_URL)" ./scripts/maga_backend_local.sh start

backend-local-restart:
	@BACKEND_PORT="$(BACKEND_PORT)" BACKEND_LOG="$(abspath $(BACKEND_LOCAL_LOG))" DATABASE_URL="$(LOCAL_DATABASE_URL)" ./scripts/maga_backend_local.sh restart

backend-local-stop:
	@BACKEND_PORT="$(BACKEND_PORT)" BACKEND_LOG="$(abspath $(BACKEND_LOCAL_LOG))" ./scripts/maga_backend_local.sh stop

backend-local-status:
	@BACKEND_PORT="$(BACKEND_PORT)" BACKEND_LOG="$(abspath $(BACKEND_LOCAL_LOG))" ./scripts/maga_backend_local.sh status

backend-local-logs:
	@BACKEND_PORT="$(BACKEND_PORT)" BACKEND_LOG="$(abspath $(BACKEND_LOCAL_LOG))" ./scripts/maga_backend_local.sh logs

dev:
	@$(MAKE) init-clean-schema
	@$(MAKE) backend-local-start
	@$(MAKE) frontend-start
	@echo "MAGA local development is ready: frontend=http://localhost:$(FRONTEND_PORT) backend=http://localhost:$(BACKEND_PORT)/docs database=$(LOCAL_DATABASE_PATH)"

dev-restart:
	@$(MAKE) init-clean-schema
	@$(MAKE) backend-local-restart
	@$(MAKE) frontend-stop
	@$(MAKE) frontend-start

dev-stop:
	@$(MAKE) frontend-stop
	@$(MAKE) backend-local-stop

dev-status:
	@$(MAKE) backend-local-status
	@$(MAKE) frontend-status
	@echo "database: $(LOCAL_DATABASE_PATH)"

dev-logs:
	@mkdir -p .local/logs
	@touch "$(BACKEND_LOCAL_LOG)" "$(FRONTEND_LOG)"
	tail -f "$(BACKEND_LOCAL_LOG)" "$(FRONTEND_LOG)"

frontend-start:
	@FRONTEND_PORT="$(FRONTEND_PORT)" BACKEND_PORT="$(BACKEND_PORT)" FRONTEND_LOG="$(abspath $(FRONTEND_LOG))" ./scripts/maga_frontend_local.sh start

frontend-stop:
	@FRONTEND_PORT="$(FRONTEND_PORT)" BACKEND_PORT="$(BACKEND_PORT)" FRONTEND_LOG="$(abspath $(FRONTEND_LOG))" ./scripts/maga_frontend_local.sh stop

frontend-status:
	@FRONTEND_PORT="$(FRONTEND_PORT)" BACKEND_PORT="$(BACKEND_PORT)" FRONTEND_LOG="$(abspath $(FRONTEND_LOG))" ./scripts/maga_frontend_local.sh status

frontend-logs:
	@FRONTEND_PORT="$(FRONTEND_PORT)" BACKEND_PORT="$(BACKEND_PORT)" FRONTEND_LOG="$(abspath $(FRONTEND_LOG))" ./scripts/maga_frontend_local.sh logs
