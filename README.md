# MAGA

MAGA 是一个面向营销内容生成场景的 Agent 平台。

当前仓库采用单仓结构：

- `platform-server`: 单体后端服务
- `platform-console`: 管理台前端
- `docs`: 产品与工程文档

## 开发方式

```bash
make up
```

这会启动：

- MySQL
- Redis
- MAGA Platform Server

然后在本地启动前端：

```bash
cd platform-console
pnpm install
pnpm dev
```

访问地址：

- 前端: [http://localhost:3100](http://localhost:3100)
- 后端: [http://localhost:5100/docs](http://localhost:5100/docs)

## 常用命令

```bash
make up        # 启动 mysql / redis / backend
make down      # 停止容器
make build     # 构建 backend 镜像
make logs      # 查看容器日志
make ps        # 查看容器状态
make dev       # 提示本地前端启动方式
```
