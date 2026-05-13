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
- 本机进程：Hermes `maga-worker` `/invoke` 服务
- MAGA clean schema 与默认执行器 seed

访问地址：

- 后端: [http://localhost:5100/docs](http://localhost:5100/docs)
- worker: [http://localhost:8765/health](http://localhost:8765/health)

前端不放 Docker，也不由 `make dev` 自动管理；需要前端时单独在本机启动：

```bash
make frontend-start
```

`make dev` 会强制重启 `maga-worker`，确保本地修改后的 worker 最新代码被加载。只想重启 MAGA 后端栈和 worker 时也可以显式运行：

```bash
make dev-restart
```

## 当前内容生成链路

MAGA 当前通过 `executor_registry.invoke_url` 决定生文走向：

- `mock://...`：走 `platform-server` 内置 deterministic mock，只用于本地早期 smoke。
- `http(s)://...`：由 MAGA 后端按 Executor Protocol v0.1 同步 POST 到 worker 的 `/invoke`。

推荐本地链路是：

```text
MAGA 前端/接口
  -> /api/v1/content-agent/generation/start 或 /api/v1/content-agent/batches/start
  -> MAGA 创建 task/run/stage_call
  -> 依次调用 hermes_maga_worker:
     xhs.interpret_brief
     xhs.run_ae_analysis
     xhs.generate_draft
     xhs.run_ae_review
     xhs.rewrite_draft（仅审核未通过时）
  -> 返回 title/body，并在批量报告中展示审核原因、耗时和 stage trace
```

`/generation/start` 会构造最小 `generation_snapshot`，`batch_context.source=single_generation`。`/batches/start` 会先基于 `asset_registry` 生成批次计划，再为每篇文章构造带资产引用和多样性约束的 `generation_snapshot`。

## 数据库初始化

MAGA 当前第一阶段以 clean schema 为准，不依赖历史 Alembic 链初始化新库。本地和服务器准备数据库时使用同一条入口：

```bash
make init-clean-schema
```

`make init-clean-schema` 默认会写入 `hermes_maga_worker` 和历史兼容别名 `hermes_xhs_writer`，并把 `invoke_url` 指向 `http://host.docker.internal:8765/invoke`。如果本地只想跑平台内置 mock：

```bash
MAGA_WORKER_INVOKE_URL=mock://maga-worker/invoke make init-clean-schema
```

说明：后端应用启动时也会补一个不覆盖已有记录的 executor 兜底，代码常量默认是 `mock://maga-worker/invoke`；推荐开发入口仍以 `make init-clean-schema` / `make dev` 的 seed 结果为准。

## maga-worker

真实产文链路需要宿主机上有 Hermes `maga-worker` 的 `/invoke` 服务：

```bash
make worker-start
```

默认监听 `http://127.0.0.1:8765`，Docker 后端通过 `http://host.docker.internal:8765/invoke` 调用它。当前本地默认设置 `MAGA_WORKER_EXECUTION_MODE=runtime_fast`、`MAGA_WORKER_RUNTIME_FAST_FAKE=0`，会进入真实 fast runtime 生成；如果只想跑通 HTTP 协议链路、不触发模型生成，可临时改成：

```bash
MAGA_WORKER_RUNTIME_FAST_FAKE=1 make worker-start
```

## 常用命令

```bash
make up        # 启动 mysql / redis / backend
make dev       # 统一启动/刷新 Docker 后端栈、maga-worker
make dev-restart # 强制重启 maga-worker，并重新 seed schema
make frontend-start # 单独启动本机前端 Vite
make frontend-stop  # 单独停止本机前端
make frontend-status # 查看本机前端状态
make init-clean-schema # 创建/补齐 MAGA clean schema，并 seed 默认执行器
make worker-start # 启动宿主机 maga-worker /invoke 服务
make worker-stop  # 停止宿主机 maga-worker
make worker-status # 查看宿主机 maga-worker 状态
make worker-logs   # 查看宿主机 maga-worker 日志
make dev-stop  # 停止 Docker 后端栈、maga-worker
make down      # 停止容器
make build     # 构建 backend 镜像
make logs      # 查看容器日志
make ps        # 查看容器状态
make local-dev # 旧本机启动方式（不用 Docker）
```
