up:
	docker compose up --build -d mysql redis backend

down:
	docker compose down

build:
	docker compose build backend

logs:
	docker compose logs -f

ps:
	docker compose ps

dev:
	@echo "前端请本地运行：cd platform-console && pnpm install && pnpm dev"
