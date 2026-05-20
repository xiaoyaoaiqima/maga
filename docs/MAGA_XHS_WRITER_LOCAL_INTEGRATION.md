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

MAGA 端由 `ContentAgentOrchestrator` 串行调度 `xhs.*` stages：

1. `xhs.interpret_brief`
2. `xhs.run_ae_analysis`
3. `xhs.generate_draft`
4. `xhs.review_and_rewrite`

worker 可以在阶段内使用 repo 内 xhs runtime、静态 profile 兜底文件和 debug 输出，但正式 task/run/stage_call/artifact/feedback 的 source of truth 仍然在 MAGA。

## 当前生文流程（2026-05-18）

### 1. 入口

单篇入口：

```text
POST /api/v1/content-agent/generation/start
```

批量入口：

```text
POST /api/v1/content-agent/batches/start
```

单篇和批量最终都会创建 `ContentAgentTask`、`ContentAgentRun` 和多条 `ContentAgentStageCall`。区别是：

- 单篇：MAGA 基于请求字段构造最小 `generation_snapshot`，`batch_context.source=single_generation`。
- 批量：MAGA 先基于 `asset_registry` 规划每篇文章，再为每个 `ContentBatchItem` 构造独立 `generation_snapshot`。

批量执行默认并发数为 5。每个 batch item 使用独立 DB session 执行，避免多个异步 worker 共享同一个 `AsyncSession`。

### 2. 用户输入与 MAGA 快照

当前 MVP 用户侧核心字段：

```json
{
  "asset_key": "yuanyue",
  "product_topic": "宝宝便便不规律",
  "target_audience": "新手妈妈",
  "style": "经验老道型",
  "count": 5,
  "executor_code": "hermes_maga_worker",
  "created_by": "ops"
}
```

MAGA 在进入 worker 前会补齐不可变 `generation_snapshot`，主要包含：

- `brief`：主题、人群、风格、字数等约束。
- `assets`：痛点、卖点、参考例文、写法模式、合规规则。
- `diversity_slot`：开头类型、结构类型、情绪底色、CTA、叙事焦点等多样化约束。
- `batch_context`：批次、item 编号、来源。
- `prompt_bundle_snapshot`：MAGA 管理的 prompt / corpus / registry 当前版本快照。
- `model_config`：MAGA 侧模型配置，运行时下发为 `XHS_RUNTIME_MODEL_GE`、`XHS_RUNTIME_MODEL_AE`。

worker 不直连 MAGA DB。正式运行只消费这份 snapshot 和 `/invoke` envelope。

### 3. 执行器选择

MAGA 根据 `executor_registry.hermes_maga_worker.invoke_url` 决定执行路径：

- `mock://...`：走 `platform-server` 内置 deterministic mock，只用于本地早期 smoke。
- `http(s)://...`：同步 POST 到真实 worker `/invoke`。

本地真实 worker 默认：

```text
http://host.docker.internal:8765/invoke
```

宿主机 worker 本身监听：

```text
http://127.0.0.1:8765
```

### 4. MAGA 编排的四段 stage

当前 stage 顺序固定：

| 顺序 | Capability | MAGA 输入 | 当前职责 |
| --- | --- | --- | --- |
| 1 | `xhs.interpret_brief` | 用户字段 + `generation_snapshot` | 编译 `structured_brief`、`runtime_brief` 和 `brief_warnings` |
| 2 | `xhs.run_ae_analysis` | `structured_brief` + `runtime_brief` + snapshot | 返回前置分析结果；mock/占位路径返回 `business_logic` 分析 |
| 3 | `xhs.generate_draft` | `structured_brief` + `runtime_brief` + `analyses` + snapshot | 只生成初稿；`runtime_fast` 复用已编译的 `runtime_brief` 调用 GE，写出 `draft.md` |
| 4 | `xhs.review_and_rewrite` | draft + `structured_brief` + `runtime_brief` + snapshot | 基于同一份 `runtime_brief` 并行运行 4 个审核模块，根据反馈最多 2 轮精准改写和复审，返回最终稿与 `review_report` |

`xhs.run_ae_review` 和 `xhs.rewrite_draft` 仍保留为兼容能力；主生文链路不再把审核和平台级改写拆成两个额外 stage。相似度降重仍会通过 `xhs.rewrite_draft` 追加独立 trace。

### 5. worker 真实生成路径

`make worker-start` 默认使用 repo 内 worker：

```text
worker code: /Users/luxifa/maga/worker
worker profile: /Users/luxifa/maga/worker/profiles/maga-worker
worker outputs: /Users/luxifa/maga/.local/worker/outputs
```

当前本地默认执行模式是 `runtime_fast`：

```text
MAGA_WORKER_EXECUTION_MODE=runtime_fast
MAGA_WORKER_RUNTIME_FAST_FAKE=0
```

`runtime_fast` 的实际行为：

1. 在 `xhs.interpret_brief` 把 `generation_snapshot` 转成 xhs runtime `brief`，作为 `runtime_brief` 写入 stage 输出。
2. 构造 fast writing spec，包含主题、人群、痛点、卖点、参考例文、写法模式、多样性 slot、合规禁用表达。
3. 读取 MAGA 下发的 prompt bundle，优先使用：
   - `xhs_writer.ge.system`
   - `xhs_writer.ge.style_templates`
   - `xhs_writer.ge.voice_dictionary`
4. 在 `xhs.generate_draft` 复用 `runtime_brief` 调用 GE 生成草稿，写出 `draft.md`。
5. 在 `xhs.review_and_rewrite` 复用同一份 `runtime_brief`，并行调用 `compliance_redline`、`expression_writing`、`time_logic` 和 `legal_tencent`。
6. 如果任一审核返回硬失败、替换项或建议，则最多做 2 轮精准改写和复审。
7. 写出 debug 文件和 `final.md` 到 `.local/worker/outputs/...`。

注意：`runtime_fast` 当前不是完整 AE 委员会。它的真实审核路径是 3 个 AE 模型审核加腾讯云法律审核，且 4 个审核并行执行。完整 `runtime` 路径保留在 `xhs_runtime.run_full_flow`，但不是本地默认启动路径。

### 6. 当前 AE 口径

MAGA 管理后的主流程只保留三个 AE：

| AE | 类型 | 阶段语义 | Prompt 名 |
| --- | --- | --- | --- |
| `business_logic` | analysis | 前置业务逻辑分析：痛点、卖点因果链、结构和真人感 | `xhs_writer.ae.business_logic.system` |
| `compliance_redline` | hard 0/1 | 红线审核：母婴/健康/医疗表达、功效承诺、时间效果链 | `xhs_writer.ae.compliance_redline.system` |
| `expression_writing` | hard 0/1 | 表达写作审核：套话、AI 味、夸张表达、结构表达问题 | `xhs_writer.ae.expression_writing.system` |
| `time_logic` | hard 0/1 | 时间逻辑审核：前后时间线、效果时间链、因果顺序 | `xhs_writer.ae.time_logic.system` |
| `legal_tencent` | hard 0/1 | 腾讯云法律/内容安全审核 | 腾讯云审核接口 |

`worker/profiles/maga-worker/experts/_brief_types.yaml` 中新版 `xhs_product_seeding_professional_advisor` 启用 `business_logic` 前置分析，以及 3 个模型审核 AE。`legal_tencent` 由 runtime 直接调用腾讯云审核，不作为 prompt AE 注册。

`worker/profiles/maga-worker/experts/_registry.yaml` 中旧拆分 AE 仍保留为历史素材，但 `must=false`，不会作为当前主流程 active AE 导入 MAGA。静态资产导入会清理/归档非 active AE 的 prompt 与 `expert_corpus`。

当前本地 DB active AE prompt 应只剩：

```text
xhs_writer.ae.brand_product_guard.system
xhs_writer.ae.business_logic.system
xhs_writer.ae.business_logic.score_rubric
xhs_writer.ae.compliance_redline.system
```

当前本地 DB active `expert_corpus` 应只剩：

```text
brand_product_guard
business_logic
compliance_redline
```

### 7. 产物、报告和 trace

MAGA 侧持久化：

- `content_agent_task`
- `content_agent_run`
- `content_agent_stage_call`
- `content_batch_job`
- `content_batch_item`
- `content_feedback`

批量 item 生成后写入：

- `title`
- `body`
- `quality_json.review_report`
- `quality_json.hard_pass`
- `quality_json.soft_score_avg`
- `diversity_json`
- `run_id` / `task_id`

前端批量报告的 trace 来自 `content_agent_stage_call`。`xhs.generate_draft` 现在只代表初稿生成耗时；审核、改写和复审耗时落在 `xhs.review_and_rewrite` stage。总耗时仍按整条 run / batch item 统计。

worker 侧本地 debug 产物写入：

```text
/Users/luxifa/maga/.local/worker/outputs/
```

包括 brief、GE prompt/response、AE prompt/response、`draft.md`、`final.md` 等，仅用于本地排查，不是业务 source of truth。

### 8. 多样化与相似度处理

批量规划阶段会为每篇文章生成不同 `diversity_slot`，控制：

- 开头类型
- 结构类型
- 情绪底色
- CTA 类型
- 叙事焦点
- 内容角度
- 人设 lens
- 场景类型
- 证据类型
- 禁止重叠组

批量生成后，`ContentBatchExecutionService` 会做 2-gram Jaccard 相似度检查：

- 同批次相似度阈值：`0.42`
- 历史文章相似度阈值：`0.48`
- 历史回看数量：最近 50 篇
- 最多相似度改写轮次：2

相似度改写仍通过同一个 `xhs.rewrite_draft` stage 进入 run trace。

## 注意

本地阶段可以显式读取历史 xhs-writer / maga-asset-steward 文件作为迁移参考，但默认启动和部署只依赖 MAGA repo。
生产阶段 worker 不应直连 MAGA DB，也不应把任一 Hermes profile workspace 当作 source of truth。
