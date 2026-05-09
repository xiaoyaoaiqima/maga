# MAGA Agent 执行层改造方案

## 一、结论

MAGA 不改造成通用 Agent 平台。

MAGA 的定位保持为：

- 面向营销内容生成的业务工作台
- 品牌、产品、活动、语料、Prompt、Expert、内容结果和质量闭环的业务系统
- 内容 Agent 的控制平面、数据平面和资产中心

Hermes 的定位是：

- 当前默认 Agent 执行层
- 以 `xhs-writer` profile 作为小红书内容生成 worker
- 负责复杂推理、工具调用、GE/AE 编排、模型调用和结果回写

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
- 当前 executor 是 Hermes profile `xhs-writer`
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
- title/body/hashtags
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

#### Profile 级专职能力

`xhs-writer` profile 表示一个专职小红书写作 worker。

后续可以继续新增：

- `xhs-critic`
- `xhs-rewriter`
- `xhs-prompt-optimizer`
- `xhs-corpus-curator`

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

例如：`xhs-writer` 如何按 GE/AE 流程生文，如何处理低分重写。

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
│ Hermes profile: xhs-writer│
│  阶段内并行 + LLM 调用     │
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
| executor_code | 例如 `hermes_xhs_writer` |
| executor_type | 例如 `hermes_profile` / `http_worker` / `langgraph_service` |
| display_name | 展示名称 |
| protocol_version | 与协议 major 版本对齐，默认 `0.1` |
| invoke_url | MAGA 调 Executor 的 base URL（push 模式发起点） |
| supported_capabilities_json | 实际能力清单，含 `capability` 与 `schema_version` |
| auth_token_secret_ref | Executor → MAGA 的 Bearer token 的密钥管理引用 |
| hmac_secret_ref | MAGA → Executor 的 HMAC 签名密钥引用 |
| config_json | 非密配置 |
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
| priority | 优先级 |
| executor_code | 指向 executor_registry |
| brand_id/product_id/campaign_id | 业务引用 |
| brief_id | brief 引用 |
| input_snapshot_json | 执行时输入快照 |
| output_summary_json | 结果摘要 |
| error_message | 失败原因 |
| retry_count | 重试次数 |
| created_by | 创建人 |
| create_time/update_time | 时间 |

### 3. content_agent_run

一次 task 可以有多次 run。

| 字段 | 说明 |
|---|---|
| id | 主键 |
| task_id | 关联 content_agent_task |
| run_code | run 编码 |
| run_token | 每个 run 启动时生成的 ULID；所有 Executor → MAGA 写动作必须带，用于 INV-6 防抢占 |
| executor_code | 执行器 |
| executor_type | 执行器类型快照 |
| external_run_id | Hermes 或其他 worker 侧 run id |
| status | run 状态 |
| status_substate | 协议第四章定义的子状态，如 `running.drafting` |
| current_stage_call_id | 当前激活 stage call；用于快速定位 |
| rewrite_round | 已完成的改写轮数 |
| weighted_score_summary_json | MAGA 聚合后的 hard/soft 分数缓存，便于前台展示 |
| model_summary_json | 使用模型摘要 |
| config_snapshot_json | 执行配置快照 |
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
| schema_version | capability schema 版本 |
| invoke_mode | `sync` / `async` |
| status | `pending/running/succeeded/failed/cancelled/timeout` |
| input_snapshot_json | 入参信封的 input 部分 |
| output_snapshot_json | 出参信封的 output 部分 |
| stats_json | 出参信封的 stats（耗时、token 汇总） |
| error_code | 协议第 8.1 节的错误码 |
| error_message | 错误信息 |
| retry_of_stage_call_id | 重试链上一跳；首次为 null |
| started_at | 调用 invoke 时间 |
| finished_at | complete/fail 落库时间 |
| deadline_at | invoke 时声明的 deadline |
| create_time/update_time | 时间 |

### 5. content_agent_event

结构化 trace event。分组键为 `stage_call_id`。

| 字段 | 说明 |
|---|---|
| id | 主键 |
| run_id | 关联 content_agent_run |
| stage_call_id | 关联 content_agent_stage_call，必填 |
| event_type | `llm_call/tool_call/artifact_created/error/status` |
| expert_code | 可选，如 `ai_smell`, `legal` |
| model_code | 可选 |
| input_snapshot_json | 输入快照 |
| output_snapshot_json | 输出快照 |
| otel_attributes_json | OpenTelemetry GenAI 字段（见协议第十章） |
| message | 简要说明 |
| latency_ms | 耗时 |
| token_usage_json | token 使用 |
| metadata_json | 扩展数据 |
| idempotency_key | 与 run_id 联合唯一；用于 Executor 上报的幂等 |
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
| metadata_json | 扩展数据 |
| idempotency_key | 与 run_id 联合唯一 |
| create_time | 时间 |

### 7. content_agent_human_review

人审 gate 的一等公民表，对应协议 7.2 `request_human_review`。

| 字段 | 说明 |
|---|---|
| id | 主键 |
| run_id | 关联 content_agent_run |
| stage_call_id | 关联触发评审的 stage call；可空（如 MAGA 自发触发） |
| reason | `max_rewrites_reached/hard_ae_failed/executor_requested` 等 |
| payload_json | Executor 上报的待评审数据（draft、score_report 等引用） |
| response_schema_json | 提交响应必须遵循的 JSON Schema |
| ui_hint | `review_form/side_by_side_diff/free_form` |
| status | `pending/responded/cancelled/expired` |
| responder_user_id | 处理人 |
| response_json | 用户提交内容 |
| requested_at | 触发时间 |
| responded_at | 处理时间 |
| create_time/update_time | 时间 |

### 8. 索引与唯一约束

| 表 | 索引/约束 | 用途 |
|---|---|---|
| content_agent_stage_call | UNIQUE(stage_call_id) | 协议幂等 |
| content_agent_stage_call | UNIQUE(run_id, sequence_no) | 顺序保证 |
| content_agent_stage_call | INDEX(status, deadline_at) | 超时扫描 |
| content_agent_event | UNIQUE(run_id, idempotency_key) | Executor 上报幂等 |
| content_agent_event | INDEX(stage_call_id, create_time) | 阶段内事件回放 |
| content_agent_artifact | UNIQUE(run_id, idempotency_key) | 上传幂等 |
| content_agent_artifact | UNIQUE(artifact_code) | 对外引用 |
| content_agent_run | UNIQUE(run_token) | 防抢占校验 |
| executor_registry | UNIQUE(executor_code) | 注册唯一性 |

---

## 七、xhs-writer 现状与迁移映射

当前 Hermes `xhs-writer` profile 中已经有一套可运行的本地原型：

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
| `tools/xhs_runtime.py` | Hermes worker 执行逻辑，短期保留在 Hermes |
| `notes/*-debug/` | content_agent_event / content_agent_artifact |

迁移顺序不要一次性全部迁完。优先保证任务、run、artifact、trace 能进入 MAGA。

---

## 八、推荐落地阶段

### 阶段 1：MAGA 存任务、run、结果，Hermes 实现 invoke endpoint

目标：验证"工作台 + Agent worker"闭环（push 模式）。

做法：

1. MAGA 按 §六 建表：executor_registry / content_agent_task / content_agent_run / content_agent_stage_call / content_agent_event / content_agent_artifact / content_agent_human_review。
2. MAGA 实现 [EXECUTOR_PROTOCOL.md](./EXECUTOR_PROTOCOL.md) §7.2 的回调 endpoints（events / artifacts / human-review / complete / fail / heartbeat），以及调度器主动调 Executor `/invoke` 的 push 路径与状态机推进逻辑。
3. Hermes `xhs-writer` 暴露 `/invoke` endpoint，按协议接收 capability 调用；本地仍读 `experts/`、`ge_writer/`、`campaigns/` 作为资产源（snapshot 由 MAGA 在 invoke 入参中传入或本地兜底）。
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

### 阶段 3：人机协作和 Prompt 闭环

目标：把生成质量迭代沉淀到 MAGA。

能力：

- 人工审核 final/draft
- 标记问题类型
- 触发 rewrite task
- 触发 prompt_optimize task
- 采纳/拒绝/编辑 prompt patch
- 保存新 PromptVersion
- 用测试集对比新旧 prompt

### 阶段 4：多 worker，但仍保持营销内容专用

可新增 Hermes profile：

- `xhs-critic`
- `xhs-rewriter`
- `xhs-prompt-optimizer`
- `xhs-corpus-curator`

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

Hermes xhs-writer = 当前默认内容生成 Agent worker
```

MAGA 不追求成为所有 Agent 的统一平台。

MAGA 追求成为营销内容生成这个垂直领域里，最稳定、最可控、最可复盘、最容易持续优化的业务工作台。
