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

访问地址：

- 前端: [http://localhost:3100](http://localhost:3100)
- 后端: [http://localhost:5100/docs](http://localhost:5100/docs)

## 常用命令

```bash
make up        # 启动 mysql / redis / backend
make dev       # 启动 Docker 后端栈和本机前端
make dev-stop  # 停止 Docker 后端栈和本机前端
make down      # 停止容器
make build     # 构建 backend 镜像
make logs      # 查看容器日志
make ps        # 查看容器状态
make local-dev # 旧本机启动方式（不用 Docker）
```
