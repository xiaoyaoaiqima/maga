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
- 本机进程：MAGA Console 前端开发服务
- MAGA clean schema 与默认执行器 seed

访问地址：

- 前端: [http://localhost:3100](http://localhost:3100)
- 后端: [http://localhost:5100/docs](http://localhost:5100/docs)

## 数据库初始化

MAGA 当前第一阶段以 clean schema 为准，不依赖历史 Alembic 链初始化新库。本地和服务器准备数据库时使用同一条入口：

```bash
make init-clean-schema
```

默认会写入 `hermes_maga_worker`，并把 `invoke_url` 指向 `http://host.docker.internal:8765/invoke`。如果本地只想跑平台内置 mock：

```bash
MAGA_WORKER_INVOKE_URL=mock://maga-worker/invoke make init-clean-schema
```

## maga-worker

真实产文链路需要宿主机上有 Hermes `maga-worker` 的 `/invoke` 服务：

```bash
make worker-start
```

默认监听 `http://127.0.0.1:8765`，Docker 后端通过 `http://host.docker.internal:8765/invoke` 调用它。当前本地默认设置 `MAGA_WORKER_RUNTIME_FAST_FAKE=1`，用于跑通真实 HTTP 协议链路但不触发完整模型生成；要验证完整 runtime 时可改成：

```bash
MAGA_WORKER_RUNTIME_FAST_FAKE=0 make worker-start
```

## 常用命令

```bash
make up        # 启动 mysql / redis / backend
make dev       # 启动 Docker 后端栈和本机前端
make init-clean-schema # 创建/补齐 MAGA clean schema，并 seed 默认执行器
make worker-start # 启动宿主机 maga-worker /invoke 服务
make worker-stop  # 停止宿主机 maga-worker
make dev-stop  # 停止 Docker 后端栈和本机前端
make down      # 停止容器
make build     # 构建 backend 镜像
make logs      # 查看容器日志
make ps        # 查看容器状态
make local-dev # 旧本机启动方式（不用 Docker）
```
