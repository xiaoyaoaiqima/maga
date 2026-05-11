# MAGA Agent 执行层改造方案

## 一、结论

MAGA 不改造成通用 Agent 平台。

MAGA 的定位保持为：

- 面向营销内容生成的业务工作台
- 品牌、产品、活动、语料、Prompt、Expert、内容结果和质量闭环的业务系统
- 内容 Agent 的控制平面、数据平面和资产中心

Hermes 的定位是：

- 当前默认 Agent 执行层
- 以 `maga-worker` profile 作为前期统一内容 worker
- 负责复杂推理、工具调用、GE/AE 编排、模型调用、资产提案、反馈训练提案和结果回写

前期为了降低本地开发和服务器部署复杂度，不拆 `xhs-writer` / `maga-asset-steward` / `feedback-trainer` 三个 profile；统一收敛到一个 Hermes profile：`maga-worker`。能力边界用 capability 区分，数据边界仍由 MAGA API 保证。

未来可以替换 Hermes，或新增其他 Agent runtime，但 MAGA 的核心护城河不放在 runtime，而放在营销内容生成的业务逻辑、资产、流程、trace、评估和人机协作闭环中。

一句话：

```text
MAGA 负责“管什么、存什么、怎么看、怎么评估”；
Hermes 负责“怎么执行、怎么推理、怎么调用工具”。
```

---

## 二、为什么不做通用 Agent 工作台

### 1. MAGA 的业务护城河是营销内容生成

MAGA 的领域能力深度绑定营销内容生成业务（详见 §三.1）。把 MAGA 抽象成泛 Agent 工作台会稀释产品定位，也会增加不必要复杂度。

### 2. 只保留轻量执行层兼容

MAGA 不做泛平台，但需要避免和 Hermes 绑定死。

需要兼容的是“执行层”，不是“业务形态”。

也就是说：

- MAGA 可以登记多个 executor
- 当前 executor 是 Hermes profile `maga-worker`
- 未来 executor 可以是 LangGraph 服务、自研 Python worker、Dify workflow、OpenAI Assistants、Claude/Codex 类 worker 等
- 无论 executor 怎么变，MAGA 仍然掌握业务资产、任务、trace、结果和评估

---

## 三、系统分工

### 1. MAGA 负责什么

MAGA 是 source of truth，负责所有需要被人看、改、复用、审计和评估的内容。

#### 业务资产

- 品牌资料
- 产品资料
- 活动 brief
- 人群、人设、场景、痛点、卖点
- 小红书语料
- 风格模板
- 禁用词、替换词、平台规则
- Expert 配置
- GE/AE persona
- score rubric
- Prompt 资产和版本
- 测试集和评估样本

#### 任务和状态

- 内容生成任务
- Agent run
- 执行状态
- 重试次数
- 失败原因
- 人工审核状态
- 发布状态

#### Trace 和审计

- 每一步执行事件
- 每次模型调用输入输出
- 使用的 prompt/persona/rubric/corpus 版本
- 使用的模型和参数
- token usage
- latency
- 工具调用
- AE 评分
- rewrite 决策
- 错误堆栈

#### 产物和结果

- brief snapshot
- AE instruction
- draft v0/v1/v2
- final content
- title/body（前台只展示标题 + 正文；hashtag 可作为内部草稿字段存在，但不进入 MVP 交付结果）
- score report
- conflict report
- prompt patch
- 人工反馈

#### 人机协作

- 内容审核
- 选择 draft
- 采纳/拒绝 prompt patch
- 编辑最终稿
- 请求重写
- 标记可发布
- 质量复盘

### 2. Hermes 负责什么

Hermes 是 execution worker，负责执行过程中的复杂动作。

#### 执行逻辑

- 拉取 MAGA 任务
- 读取任务 brief 和资产引用
- 组织 GE/AE 调用
- 运行小红书生成流程
- 处理冲突和红线
- 根据 AE 分数重写
- 生成草稿和最终稿
- 将 trace、artifact、状态写回 MAGA

#### 临时工作区

Hermes workspace 可以存：

- 当前 run 的 scratch 文件
- 临时 prompt/debug 文件
- 中间草稿
- 本地缓存
- 临时脚本

但 Hermes workspace 不是最终数据源。正式资产和正式产物必须回写 MAGA。

#### Profile 级能力

`maga-worker` profile 表示前期统一内容 worker，内部承载多组专职 capability：

- `xhs.*`：小红书产文、审核、改写，承接原 `xhs-writer` 能力
- `asset.*`：资料清洗、资产变更提案，承接 Asset Steward 能力
- `feedback.*`：人工反馈总结、训练建议、资产/规则优化建议
- `prompt.*`：Prompt patch 提案和优化建议

后续如果某组能力变复杂，再拆成独立 profile 或服务；拆分不应改变 MAGA 的业务表和 API 边界。

但品牌、产品、活动、语料不应该通过复制 profile 表达，而应该存在 MAGA 中。

---

## 四、边界原则

### 1. 需要人看、人改、人审核、人复用的，放 MAGA

例如：prompt、persona、rubric、corpus、brief、生成结果、评分、人工反馈。

### 2. 需要版本化和复盘的，放 MAGA

例如：一次生成用了哪个 prompt version、哪个 corpus version、哪个模型、哪个 Expert 输出。

### 3. 快速变化的执行逻辑，放 Hermes

例如：如何组织 prompt、如何多轮重写、如何调用工具、如何容错、如何临时实验。

### 4. 和业务对象绑定的，放 MAGA

例如：美素佳儿品牌资料、a2 产品资料、某个活动 brief、某组小红书语料。

### 5. 和 Agent 工作习惯绑定的，放 Hermes profile/skill

例如：`maga-worker` 内部的 `xhs.*` 能力如何按 GE/AE 流程生文，如何处理低分重写；`asset.*` 能力如何把资料整理成资产变更提案。

### 6. 临时文件放 Hermes，正式 artifact 放 MAGA

Hermes 可以落本地 debug 文件，但最终可追溯结果必须写回 MAGA。

### 7. Hermes 不直连 MAGA 数据库

Hermes 通过 MAGA API 拉任务、取资产、写 trace、传 artifact、更新状态。

不要让 Hermes 直接读写 MySQL。这样未来替换执行层更容易，也能保证权限、校验、版本和状态流转统一。

---

## 五、推荐架构

```text
┌──────────────────────────┐
│        MAGA UI            │
│  营销内容生成工作台        │
└─────────────┬────────────┘
              │
┌─────────────▼─────────────┐
│       MAGA Backend         │
│  FastAPI / MySQL / Redis   │
│  调度器 + 状态机 + 决策     │
└─────────────┬─────────────┘
              │ ① invoke_capability  (push)
              │ ② event/artifact/human-review (callback)
              ▼
┌──────────────────────────┐
│ Hermes profile: maga-worker│
│  xhs/asset/feedback/prompt  │
│  capabilities + LLM 调用    │
└──────────────────────────┘
```

控制流（详见 [EXECUTOR_PROTOCOL.md](./EXECUTOR_PROTOCOL.md) §三）：

1. MAGA 创建 run，决定首阶段 capability
2. MAGA 主动调 Executor `/invoke` 启动 stage，传入资产 snapshot
3. Executor 在阶段内并行多 LLM、流式回写 events、上传 artifacts
4. Executor 调 `complete_capability` 返回 stage 结果
5. MAGA 校验、聚合、决定下一阶段（继续 / 重写 / 人审 / 终止）
6. 循环 2-5 直到 run 进入终态

关键：MAGA 是 push 调度方，每阶段后由 MAGA 决策；Hermes 是被动 endpoint，不持有 run 级状态机。

---

## 六、v0.1 数据模型

MAGA 内部需要抽象 executor，但不要把业务模型泛化掉。本节定义 v0.1 协议的物理表结构（与 [EXECUTOR_PROTOCOL.md](./EXECUTOR_PROTOCOL.md) v0.1 对齐）。

### 1. executor_registry

用于登记外部执行器。只描述"谁来执行"，不承载业务逻辑。

| 字段 | 说明 |
|---|---|
| id | 主键 |
| executor_code | 例如 `hermes_maga_worker` |
| executor_type | 例如 `hermes_profile` / `http_worker` / `langgraph_service` |
| display_name | 展示名称 |
| invoke_url | MAGA 调 Executor 的 base URL（push 模式发起点） |
| auth_token | 双向 bearer token 的明文或环境变量名（MVP 简化方案） |
| enabled | 是否启用 |
| create_time/update_time | 时间 |

### 2. content_agent_task

内容生成任务表。保持内容业务语义，不命名成泛化的 `agent_task`。

| 字段 | 说明 |
|---|---|
| id | 主键 |
| task_code | 任务编码 |
| task_type | `xhs_generate` / `xhs_rewrite` / `prompt_optimize` |
| status | `pending/running/succeeded/failed/needs_review/cancelled` |
| executor_code | 指向 executor_registry |
| brand_id/product_id/campaign_id | 业务引用 |
| brief_id | brief 引用 |
| input_snapshot_json | 执行时输入快照 |
| error_message | 失败原因 |
| created_by | 创建人 |
| create_time/update_time | 时间 |

### 3. content_agent_run

一次 task 可以有多次 run。

| 字段 | 说明 |
|---|---|
| id | 主键 |
| task_id | 关联 content_agent_task |
| run_code | run 编码 |
| executor_code | 执行器 |
| status | run 状态 |
| rewrite_round | 已完成的改写轮数 |
| started_at/finished_at | 时间 |
| error_message | 错误 |
| create_time/update_time | 时间 |

### 4. content_agent_stage_call

协议中"Stage Call"的物理对应。一次 run 内每个 capability 调用都落一行，是 trace 与 artifact 的中观分组键。

| 字段 | 说明 |
|---|---|
| id | 主键 |
| stage_call_id | 协议层 ULID（见 EXECUTOR_PROTOCOL §6.1），全局唯一 |
| run_id | 关联 content_agent_run |
| sequence_no | run 内序号，从 1 起递增；同一 capability 多次调用（如 rewrite）每次新一行 |
| capability | 如 `xhs.interpret_brief` / `xhs.run_ae_analysis` |
| status | `pending/running/succeeded/failed/timeout` |
| input_snapshot_json | 入参信封的 input 部分 |
| output_snapshot_json | 出参信封的 output 部分 |
| stats_json | 出参信封的 stats（耗时、token 汇总） |
| error_code | 协议第 8.1 节的错误码 |
| error_message | 错误信息 |
| started_at | 调用 invoke 时间 |
| finished_at | 响应落库时间 |
| create_time/update_time | 时间 |

### 5. content_agent_event

结构化 trace event。分组键为 `stage_call_id`。Token 用量、模型 ID 等结构化数据全部落 `otel_attributes_json`，不另开列。

| 字段 | 说明 |
|---|---|
| id | 主键 |
| run_id | 关联 content_agent_run |
| stage_call_id | 关联 content_agent_stage_call，必填 |
| event_type | `llm_call/warning/info` |
| expert_code | 可选，如 `ai_smell`, `legal` |
| input_snapshot_json | 输入快照 |
| output_snapshot_json | 输出快照 |
| otel_attributes_json | OpenTelemetry GenAI 字段（见协议第十章） |
| message | 简要说明 |
| latency_ms | 耗时（denormalize 自 otel，便于按延迟排序） |
| create_time | 时间 |

### 6. content_agent_artifact

执行产物。

| 字段 | 说明 |
|---|---|
| id | 主键 |
| run_id | 关联 content_agent_run |
| stage_call_id | 关联 content_agent_stage_call |
| artifact_code | 协议返回的对外 ID（如 `art_01HF7Z...`），与自增 `id` 区分 |
| artifact_type | `brief_snapshot/draft/final_content/score_report/conflict_report/prompt_patch/debug_log` |
| name | 名称 |
| content_text | 文本内容 |
| content_json | JSON 内容 |
| file_url | 文件型产物地址 |
| version_no | 改写轮次（rewrite_round），便于前台对比 |
| create_time | 时间 |

### 7. content_agent_human_review

人审 gate 的一等公民表，对应协议 7.2 `request_human_review`。**run 内阻塞型**：Executor 主动请求暂停，等运营响应后 resume 同一 run。MVP 评审表单 UI 硬编码在前端，不在表里存 schema。

| 字段 | 说明 |
|---|---|
| id | 主键 |
| run_id | 关联 content_agent_run |
| stage_call_id | 关联触发评审的 stage call；可空（如 MAGA 自发触发） |
| reason | `max_rewrites_reached/hard_ae_failed/executor_requested` 等 |
| payload_json | Executor 上报的待评审数据（draft、score_report 等引用） |
| status | `pending/responded/cancelled/expired` |
| responder_user_id | 处理人 |
| response_json | 用户提交内容 |
| requested_at | 触发时间 |
| responded_at | 处理时间 |
| create_time/update_time | 时间 |

### 8. content_feedback

**run 外异步型**人工反馈表。运营在拿到生成结果之后做通过、要求修改、人工改写或局部批注，不阻塞任何 run，用于沉淀到训练反馈和 prompt 优化外循环。

MVP 阶段刻意保持极简。批量工作台先以 `batch_id/item_id/version_id` 串起反馈和人工版本；如果反馈来自具体 artifact，再补 `artifact_id`。所有 stage_call_id / prompt_version_id / expert_code 等聚合维度后续由后端通过 `run_id` / `artifact_id` JOIN 推导，运营前端不感知。

| 字段 | 说明 |
|---|---|
| id | 主键 |
| batch_id | 可选，关联批量生成批次 |
| item_id | 关联批量文章，当前 MVP 必填 |
| version_id | 可选，关联人工反馈/改写版本 |
| task_id | 可选，关联 content_agent_task |
| run_id | 可选，关联 content_agent_run |
| artifact_id | 可选，关联 content_agent_artifact，用于定位具体 final/draft |
| action | `approve` / `request_revision` / `manual_edit` |
| review_status | `approved` / `needs_revision` / `manual_edited` |
| quoted_text | 可选，有问题的原文片段，如 `"明明吃得也不少"` |
| comment | 为什么有问题 / 该怎么改，运营自由文本；批量反馈中来自 `feedback_text` |
| submitter | 提交人 |
| metadata_json | 来源、item_no、是否人工改写等扩展信息 |
| create_time | 提交时间 |

未来扩展（不在 MVP 范围）：

- `category` 自动分类（由后端 LLM 打标，运营仍不感知）
- 反馈聚合视图：按 prompt_version_id 列出 feedback 喂给 prompt_optimizer

### 9. 索引与唯一约束

| 表 | 索引/约束 | 用途 |
|---|---|---|
| content_agent_stage_call | UNIQUE(stage_call_id) | 协议幂等 |
| content_agent_stage_call | UNIQUE(run_id, sequence_no) | 顺序保证 |
| content_agent_event | INDEX(stage_call_id, create_time) | 阶段内事件回放 |
| content_agent_artifact | UNIQUE(artifact_code) | 对外引用 |
| content_feedback | INDEX(item_id, create_time) / INDEX(run_id, create_time) / INDEX(artifact_id, create_time) | 按文章、run 或 artifact 聚合 feedback |
| executor_registry | UNIQUE(executor_code) | 注册唯一性 |

---

## 七、maga-worker 与 xhs-writer 迁移映射

目标生产 profile 统一命名为 `maga-worker`。当前本地 `xhs-writer` profile 中已经有一套可运行的小红书产文原型，短期作为 `maga-worker` 的 `xhs.*` 能力来源逐步迁入：

```text
/Users/luxifa/.hermes/profiles/xhs-writer/workspace
├── campaigns/
├── experts/
├── ge_writer/
├── notes/
└── tools/xhs_runtime.py
```

建议映射关系：

| xhs-writer 文件资产 | MAGA 目标位置 |
|---|---|
| `experts/_registry.yaml` | Expert 配置 / executor 可读的 expert registry |
| `experts/_brief_types.yaml` | brief_type 到 AE 集合的业务规则 |
| `experts/*/persona.md` | PromptAsset / PromptVersion，类型 `expert_persona` |
| `experts/*/corpus.yaml` | CorpusTemplate / 语料系统 |
| `experts/*/score_rubric.md` | PromptAsset / PromptVersion，类型 `score_rubric` |
| `ge_writer/style_templates.md` | 风格模板资产 |
| `campaigns/_current/brief.yaml` | 内容任务 brief |
| `tools/xhs_runtime.py` | `maga-worker` 的 `xhs.*` 执行逻辑，短期保留在 Hermes |
| `notes/*-debug/` | content_agent_event / content_agent_artifact |

迁移顺序不要一次性全部迁完。优先保证任务、run、artifact、trace 能进入 MAGA。

---

## 八、推荐落地阶段

### 阶段 1：MAGA 存任务、run、结果，maga-worker 实现 invoke endpoint

目标：验证"工作台 + Agent worker"闭环（push 模式）。

做法：

1. MAGA 按 §六 建表：executor_registry / content_agent_task / content_agent_run / content_agent_stage_call / content_agent_event / content_agent_artifact / content_agent_human_review。
2. MAGA 实现 [EXECUTOR_PROTOCOL.md](./EXECUTOR_PROTOCOL.md) §7.2 的回调 endpoints（events / artifacts / human-review），以及调度器主动调 Executor `/invoke` 的 push 路径与状态机推进逻辑。
3. Hermes `maga-worker` 暴露 `/invoke` endpoint，按协议接收 capability 调用；其中 `xhs.*` 能力短期复用 `xhs-writer` runtime，本地仍可读 `experts/`、`ge_writer/`、`campaigns/` 作为迁移兜底（snapshot 由 MAGA 在 invoke 入参中传入）。
4. Hermes 在阶段内回写 events/artifacts，capability 完成后调 `complete_capability`；run 终态由 MAGA 据 stage 结果决定。
5. MAGA 前端展示任务状态、最终稿和基础 trace。

这个阶段不迁移所有语料和 prompt。

### 阶段 2：MAGA 接管关键资产

目标：让 MAGA 成为 source of truth。

迁移顺序：

1. brief
2. persona / prompt
3. score rubric
4. style templates
5. corpus
6. expert registry
7. brief_type mapping

Hermes 从 MAGA API 拉资产，本地只做缓存和临时执行。

### 阶段 3：人机协作和 Prompt 外循环

目标：把生成质量沉淀回 prompt 资产。

外循环数据流：

1. 运营在生成结果上通过、要求修改、人工改写或做 inline 批注 → 落入 `content_feedback`（当前批量工作台至少记录 item/version/action/review_status/comment）
2. MAGA 后台按 `run_id` / `artifact_id` JOIN 反查到 `prompt_version_id` / `expert_code`，按 prompt_version 维度聚合 feedback
3. 当某 prompt_version 累计 feedback 达到阈值或运营手动触发 → 开 `task_type=prompt_optimize` 任务
4. prompt_optimize task 由 prompt_optimizer 服务消费（短期是 MAGA 内部 service，对应已有 [prompt_optimizer_service.py](../platform-server/app/services/prompt_optimizer_service.py)；长期可拆为 Hermes profile `xhs-prompt-optimizer`，capability 命名 `prompt.optimize_from_feedback`）
5. 优化器读取 feedback → 产出 `prompt_patch` artifact
6. 运营审 patch → 采纳保存为新 PromptVersion → 后续 run 的 capability 入参自动用新版本

MVP 阶段刻意不做：

- 不做 feedback 自动分类（quoted_text + comment 是运营自由文本，后端聚合时也不强制分类）
- 不做评测集自动对比（v0.2 加 `eval.*` capability 域）
- 不做 feedback 工作流状态机（先收，再说）

### 阶段 4：按需拆分 worker，但仍保持营销内容专用

前期保持一个 `maga-worker`。当某组能力出现独立部署、扩缩容或权限隔离需求时，再拆出 Hermes profile，例如：

- `xhs-writer`
- `maga-asset-steward`
- `feedback-trainer`
- `xhs-prompt-optimizer`

MAGA 仍是营销内容生成工作台，不升级为通用 Agent 平台。

---

## 九、当前阶段不要做什么

不要做：

- 通用 Agent marketplace
- 通用 DAG / workflow 编排器
- 面向所有业务的万能 Agent 控制台
- 用通用 JSON 表单替代内容生成任务页
- 让普通用户看到 Agent/Expert/Tool/Trace 的复杂概念
- 让 Hermes 直接写 MAGA MySQL
- 让 MAGA 强依赖 Hermes 本地文件路径

这些会拖慢 MVP，并削弱 MAGA 的营销内容生成定位。

---

## 十、最终定位

最终产品形态：

```text
MAGA = 营销内容生成工作台
     + 内容资产中心
     + 内容 Agent 控制平面
     + Trace / Eval / Human Review 系统

Hermes maga-worker = 当前默认统一内容 Agent worker
```

MAGA 不追求成为所有 Agent 的统一平台。

MAGA 追求成为营销内容生成这个垂直领域里，最稳定、最可控、最可复盘、最容易持续优化的业务工作台。
