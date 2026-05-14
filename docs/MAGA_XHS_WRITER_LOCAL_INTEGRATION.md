# MAGA x maga-worker 本地组合

## 当前目标

收敛 `maga-worker` Hermes profile，用来开发和验证：

MAGA = 营销内容生成工作台 / 控制平面 / 数据资产中心
maga-worker = 当前默认统一 Agent 执行层 / worker

## 本地目录映射

| 角色 | 路径 | 说明 |
| --- | --- | --- |
| MAGA 项目 | `/Users/luxifa/maga` | source of truth 的代码库 |
| maga-worker runtime | `/Users/luxifa/maga/worker/maga_worker` | 正式 worker 代码，随 MAGA repo 部署 |
| maga-worker profile 静态文件 | `/Users/luxifa/maga/worker/profiles/maga-worker` | 专家 prompt、GE 风格库、brief/campaign 兜底文件 |
| Hermes maga-worker profile | `/Users/luxifa/.hermes/profiles/maga-worker` | 本地 Agent 上下文，不是生产代码或部署边界 |
| xhs-writer profile | `/Users/luxifa/.hermes/profiles/xhs-writer` | 历史小红书生文原型，短期迁入 `maga-worker` 的 `xhs.*` 能力 |
| maga-asset-steward profile | `/Users/luxifa/.hermes/profiles/maga-asset-steward` | 历史资产治理原型，短期迁入 `maga-worker` 的 `asset.*` 能力 |
| maga-dev profile | `/Users/luxifa/.hermes/profiles/maga-dev` | MAGA 集成开发 Agent，不作为生产 worker |

## 推荐生产边界

MAGA 不直接调用 Hermes profile 文件系统作为业务数据库。

前期只部署/管理一个 worker：`maga-worker`。它内部可以承载多组 capability：

- `xhs.*`：实际产文、审核、改写
- `asset.*`：资料清洗、资产变更提案
- `feedback.*`：人工反馈总结、训练建议
- `prompt.*`：Prompt patch / 策略优化建议

生产方向应是：

1. MAGA 创建 ContentTask / ContentRun。
2. repo 内 `maga-worker` 通过 `/invoke` 协议接收任务。
3. MAGA 返回 task snapshot，包括 brief、brand、product、selling points、expert rules、generation strategy、score rubric。
4. `maga-worker` 根据 capability 运行 GE/AE pipeline、资产提案或反馈训练分析。
5. `maga-worker` 通过 MAGA API 回写 run_event、artifact、score、final content 或 change proposal。
6. MAGA 进入人工审核/发布/评估流程。

## 当前本地执行链路

当前正式生文入口在 MAGA API，不执行本地调试脚本：

```text
POST /api/v1/content-agent/generation/start
POST /api/v1/content-agent/batches/start
```

MAGA 会读取 `executor_registry.hermes_maga_worker.invoke_url`：

- `mock://...`：使用 `platform-server` 内置 `MockExecutorInvocationClient`。
- `http(s)://...`：使用 `ExecutorInvocationClient`，同步 POST 到 worker 的 `/invoke`。

本地推荐链路：

```bash
make up
make init-clean-schema
make worker-start
```

然后由前端或接口调用：

```bash
curl -sS -X POST http://localhost:5100/api/v1/content-agent/generation/start \
  -H 'Content-Type: application/json' \
  -d '{"product_topic":"宝宝便便不规律","target_audience":"新手妈妈","style":"经验老道型","executor_code":"hermes_maga_worker","created_by":"ops"}'
```

`make init-clean-schema` 会把 `hermes_maga_worker` seed 到 `http://host.docker.internal:8765/invoke`，供 Docker 后端访问宿主机上的 worker。只需要平台内置 mock 时，显式执行：

```bash
MAGA_WORKER_INVOKE_URL=mock://maga-worker/invoke make init-clean-schema
```

## 当前 snapshot contract

MAGA 发送给 `maga-worker` 的核心输入是不可变 `generation_snapshot`：

- 单篇 `/generation/start`：构造最小 snapshot，`batch_context.source=single_generation`，保持和批量生成相同 worker contract。
- 批量 `/batches/start`：基于 `asset_registry` 生成每篇文章的 snapshot，包含痛点、卖点、参考表达、合规规则、资产引用和多样性约束。

MAGA 串行调度 `xhs.*` stages：

1. `xhs.interpret_brief`
2. `xhs.run_ae_analysis`
3. `xhs.generate_draft`
4. `xhs.run_ae_review`
5. `xhs.rewrite_draft`（只在审核需要改写时）

worker 可以在阶段内使用 repo 内 xhs runtime、静态 profile 兜底文件和 debug 输出，但正式 task/run/stage_call/artifact/feedback 的 source of truth 仍然在 MAGA。

## 注意

本地阶段可以显式读取历史 xhs-writer / maga-asset-steward 文件作为迁移参考，但默认启动和部署只依赖 MAGA repo。
生产阶段 worker 不应直连 MAGA DB，也不应把任一 Hermes profile workspace 当作 source of truth。
