# MAGA

MAGA 是一个面向营销内容生成场景的 Agent 平台。

当前仓库采用单仓结构：

- `platform-server`: 单体后端服务
- `platform-console`: 管理台前端
- `docs`: 产品与工程文档

## 开发方式

```bash
make dev
```

这会启动：

- 本机 FastAPI 后端
- 本机 Vite 前端
- `.local/maga.sqlite3` SQLite 数据库
- MAGA clean schema 与默认后端直连大模型执行器

访问地址：

- 前端：[http://localhost:3102](http://localhost:3102)
- 后端：[http://localhost:5100/docs](http://localhost:5100/docs)
- SQLite：`/Users/luxifa/maga/.local/maga.sqlite3`

本地开发不需要 Docker、MySQL 或 Redis。A2 内容主链路由 `platform-server` 在本进程内直连 OpenAI-compatible 大模型。重启前后端并重新补齐 schema：

```bash
make dev-restart
```

## 当前内容生成链路

MAGA 当前通过 `executor_registry.invoke_url` 决定生文走向：

- `mock://...`：走 `platform-server` 内置 deterministic mock，只用于本地早期 smoke。
- `llm://direct/...`：走 `platform-server` 本进程直连 OpenAI-compatible 大模型。

推荐本地链路是：

```text
MAGA 前端/接口
  -> /api/v1/content-agent/generation/start 或 /api/v1/content-agent/batches/start
  -> MAGA 创建 task/run/stage_call
  -> 调用 executor_code=maga_direct_llm_executor，默认 invoke_url=llm://direct/content
  -> platform-server 本进程执行 content.generate / content.rewrite
  -> 返回 title/body，并在批量报告中展示审核原因、耗时和 stage trace
```

`/generation/start` 会构造最小 `generation_snapshot`，`batch_context.source=single_generation`。`/batches/start` 会先基于 `asset_registry` 生成批次计划，再为每篇文章构造带资产引用和多样性约束的 `generation_snapshot`。

详细流程、stage 职责、AE 口径和 trace 见 [AI 内容生成工作流](/Users/luxifa/maga/docs/AI_CONTENT_GENERATION_WORKFLOW.md)。

## 数据库初始化

MAGA 当前第一阶段以 clean schema 为准，不依赖历史 Alembic 链初始化新库。本地默认使用 SQLite：

```bash
make init-clean-schema
```

`make init-clean-schema` 默认会写入 `maga_direct_llm_executor`，并把 `invoke_url` 指向 `llm://direct/content`。如果本地只想跑平台内置 mock：

```bash
DIRECT_LLM_EXECUTOR_INVOKE_URL=mock://direct-llm/content make init-clean-schema
```

说明：本地 SQLite 是独立的新数据库，不会自动迁移原 MySQL 数据。后端应用启动时也会补一个不覆盖已有记录的 executor 兜底。

## 常用命令

```bash
make dev       # 本机启动 SQLite 后端和 Vite 前端
make dev-restart # 重启本机前后端，并补齐 SQLite schema
make dev-stop  # 停止本机前后端
make dev-status # 查看本机前后端和 SQLite 路径
make dev-logs  # 同时查看前后端日志
make frontend-start # 单独启动本机前端 Vite
make frontend-stop  # 单独停止本机前端
make frontend-status # 查看本机前端状态
make init-clean-schema # 创建/补齐本地 SQLite schema，并 seed 默认执行器
make docker-up    # 可选：显式启动旧 Docker 开发栈
make docker-down  # 可选：停止 Docker 开发栈
make docker-logs  # 可选：查看 Docker 日志
```
