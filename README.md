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

- Docker 容器：MySQL / Redis / MAGA Platform Server
- MAGA clean schema 与默认后端直连大模型执行器 seed

访问地址：

- 后端: [http://localhost:5100/docs](http://localhost:5100/docs)

前端不放 Docker，也不由 `make dev` 自动管理；需要前端时单独在本机启动：

```bash
make frontend-start
```

`make dev` 默认不启动 Hermes/worker，生文由 `platform-server` 直连 OpenAI-compatible 大模型。只想重启 MAGA 后端栈并重新 seed schema 时也可以显式运行：

```bash
make dev-restart
```

## 当前内容生成链路

MAGA 当前通过 `executor_registry.invoke_url` 决定生文走向：

- `mock://...`：走 `platform-server` 内置 deterministic mock，只用于本地早期 smoke。
- `llm://direct/...`：走 `platform-server` 本进程直连 OpenAI-compatible 大模型，不依赖 Hermes/worker。
- `http(s)://...`：由 MAGA 后端按 Executor Protocol v0.1 同步 POST 到 worker 的 `/invoke`。

推荐本地链路是：

```text
MAGA 前端/接口
  -> /api/v1/content-agent/generation/start 或 /api/v1/content-agent/batches/start
  -> MAGA 创建 task/run/stage_call
  -> 调用 executor_code=hermes_maga_worker，默认 invoke_url=llm://direct/content
  -> platform-server 本进程执行 content.generate / content.rewrite
  -> 返回 title/body，并在批量报告中展示审核原因、耗时和 stage trace
```

`/generation/start` 会构造最小 `generation_snapshot`，`batch_context.source=single_generation`。`/batches/start` 会先基于 `asset_registry` 生成批次计划，再为每篇文章构造带资产引用和多样性约束的 `generation_snapshot`。

详细流程、stage 职责、AE 口径和 trace 见 [AI 内容生成工作流](/Users/luxifa/maga/docs/AI_CONTENT_GENERATION_WORKFLOW.md)。

## 数据库初始化

MAGA 当前第一阶段以 clean schema 为准，不依赖历史 Alembic 链初始化新库。本地和服务器准备数据库时使用同一条入口：

```bash
make init-clean-schema
```

`make init-clean-schema` 默认会写入 `hermes_maga_worker`，并把 `invoke_url` 指向 `llm://direct/content`。如果本地只想跑平台内置 mock：

```bash
MAGA_WORKER_INVOKE_URL=mock://maga-worker/invoke make init-clean-schema
```

说明：后端应用启动时也会补一个不覆盖已有记录的 executor 兜底，代码常量默认是 `llm://direct/content`；推荐开发入口仍以 `make init-clean-schema` / `make dev` 的 seed 结果为准。

## maga-worker

Hermes `maga-worker` 现在只作为兼容或对照链路，需要时可手动启动：

```bash
make worker-start
```

默认监听 `http://127.0.0.1:8765`。如果要把生文路由切回 worker，可在 seed 时显式传入：

```bash
MAGA_WORKER_INVOKE_URL=http://host.docker.internal:8765/invoke make init-clean-schema
```

如果只想跑通 HTTP 协议链路、不触发模型生成，可临时改成：

```bash
MAGA_WORKER_RUNTIME_FAST_FAKE=1 make worker-start
```

## 常用命令

```bash
make up        # 启动 mysql / redis / backend
make dev       # 统一启动/刷新 Docker 后端栈，并 seed 直连执行器
make dev-restart # 重启 Docker 后端栈，并重新 seed schema
make frontend-start # 单独启动本机前端 Vite
make frontend-stop  # 单独停止本机前端
make frontend-status # 查看本机前端状态
make init-clean-schema # 创建/补齐 MAGA clean schema，并 seed 默认执行器
make worker-start # 可选：启动宿主机 maga-worker /invoke 服务
make worker-stop  # 停止宿主机 maga-worker
make worker-status # 查看宿主机 maga-worker 状态
make worker-logs   # 查看宿主机 maga-worker 日志
make dev-stop  # 停止 Docker 后端栈
make down      # 停止容器
make build     # 构建 backend 镜像
make logs      # 查看容器日志
make ps        # 查看容器状态
make local-dev # 旧本机启动方式（不用 Docker）
```
