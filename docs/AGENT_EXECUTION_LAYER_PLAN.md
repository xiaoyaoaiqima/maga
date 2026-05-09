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

MAGA 当前最重要的领域能力包括：

- 品牌和产品资料建模
- 活动 brief 管理
- 小红书内容生成链路
- 人设、痛点、卖点、场景、风格、语料体系
- GE/AE Expert 分工
- 法律、平台、品牌约束
- AI 味、优雅度、内容丰富度、人群多样性等质量评估
- Prompt 资产治理和版本迭代
- 人工反馈、内容改写、Prompt 优化闭环

这些能力都强依赖营销内容生成业务。如果为了兼容数据分析、客服、BI、知识库问答等场景，把 MAGA 抽象成泛 Agent 工作台，会稀释产品定位，也会增加不必要复杂度。

### 2. 数据分析 Agent 应该是另一个业务工作台

如果未来要做数据分析 Agent，更合理的形态是新建一个数据分析业务工作台，而不是塞进 MAGA。

原因：

| 维度 | 营销内容生成 | 数据分析 |
|---|---|---|
| 核心对象 | 品牌、产品、活动、语料、文案 | 数据源、表、指标、SQL、图表、报告 |
| 用户问题 | 帮我生成一篇能发的小红书笔记 | 为什么转化率下降，按维度拆解原因 |
| 输出形态 | 标题、正文、hashtag、评分、改写建议 | SQL、表格、图表、洞察、报告 |
| 风险重点 | 合规、平台规则、品牌一致性、AI 味 | 数据准确性、口径一致性、权限、可复现 |
| 护城河 | 内容生产流程和语料/Prompt 闭环 | 语义层、指标体系、分析归因和数据治理 |

两类产品可以复用 Agent 执行协议、trace viewer、artifact 存储等技术模式，但不应该强行共用同一个业务工作台。

### 3. 只保留轻量执行层兼容

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
┌─────────────▼────────────┐
│       MAGA Backend        │
│  FastAPI / MySQL / Redis  │
└─────────────┬────────────┘
              │
      API: task / asset / trace / artifact / status
              │
┌─────────────▼────────────┐
│ Hermes profile: xhs-writer│
│  GE/AE 编排 + 模型调用     │
└──────────────────────────┘
```

MAGA 提供任务、资产和回写接口。

Hermes 作为 worker：

1. claim 一个 pending task
2. 拉取 brief 和资产
3. 执行 GE/AE 生文流程
4. 逐步回写 trace event
5. 上传 draft/final/score report 等 artifact
6. 标记 task 成功、失败或需要人工审核

---

## 六、轻量执行层兼容设计

MAGA 内部需要抽象 executor，但不要把业务模型泛化掉。

### 1. executor_registry

用于登记外部执行器。

建议字段：

| 字段 | 说明 |
|---|---|
| id | 主键 |
| executor_code | 例如 `hermes_xhs_writer` |
| executor_type | 例如 `hermes_profile` / `http_worker` / `langgraph_service` |
| profile_name | Hermes profile 名，如 `xhs-writer` |
| display_name | 展示名称 |
| capabilities | 能力列表，如 `xhs_generate`, `xhs_rewrite` |
| trigger_mode | `polling` / `webhook` / `manual` |
| endpoint | 可选，HTTP worker 地址 |
| config_json | 非密配置 |
| enabled | 是否启用 |
| create_time/update_time | 时间 |

注意：executor_registry 只描述“谁来执行”，不承载业务逻辑。

### 2. content_agent_task

内容生成任务表。保持内容业务语义，不命名成泛化的 `agent_task`。

建议字段：

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

建议字段：

| 字段 | 说明 |
|---|---|
| id | 主键 |
| task_id | 关联 content_agent_task |
| run_code | run 编码 |
| executor_code | 执行器 |
| executor_type | 执行器类型快照 |
| external_run_id | Hermes 或其他 worker 侧 run id |
| status | run 状态 |
| model_summary_json | 使用模型摘要 |
| config_snapshot_json | 执行配置快照 |
| started_at/finished_at | 时间 |
| error_message | 错误 |
| create_time/update_time | 时间 |

### 4. content_agent_event

结构化 trace event。

建议字段：

| 字段 | 说明 |
|---|---|
| id | 主键 |
| run_id | 关联 content_agent_run |
| step | 例如 `ae_score`, `ge_generate`, `rewrite` |
| event_type | `llm_call/tool_call/artifact_created/error/status` |
| expert_code | 可选，如 `ai_smell`, `legal` |
| model_code | 可选 |
| input_snapshot_json | 输入快照 |
| output_snapshot_json | 输出快照 |
| message | 简要说明 |
| latency_ms | 耗时 |
| token_usage_json | token 使用 |
| metadata_json | 扩展数据 |
| create_time | 时间 |

### 5. content_agent_artifact

执行产物。

建议字段：

| 字段 | 说明 |
|---|---|
| id | 主键 |
| run_id | 关联 content_agent_run |
| artifact_type | `brief_snapshot/draft/final_content/score_report/conflict_report/prompt_patch` |
| name | 名称 |
| content_text | 文本内容 |
| content_json | JSON 内容 |
| file_url | 文件型产物地址 |
| version_no | 版本 |
| metadata_json | 扩展数据 |
| create_time | 时间 |

---

## 七、MAGA 与 Hermes 的 API 边界

### 1. Hermes 拉取任务

```http
POST /api/v1/content-agent/tasks/claim
```

请求：

```json
{
  "executor_code": "hermes_xhs_writer",
  "capabilities": ["xhs_generate"]
}
```

响应：

```json
{
  "task_id": 123,
  "run_id": 456,
  "task_type": "xhs_generate",
  "input": {
    "brand": "meadjohnson",
    "product": "a2_dueltz",
    "style": "情绪共情标题",
    "target_audience": "二胎经验妈妈"
  },
  "asset_refs": {
    "brief_id": 10,
    "expert_registry_version": 3,
    "style_template_version": 7
  }
}
```

### 2. Hermes 拉取资产

```http
GET /api/v1/content-agent/tasks/{task_id}/context
```

返回执行所需上下文：

- brief
- expert registry
- brief_type mapping
- persona/rubric/corpus 引用
- style templates
- redline/policy
- model routing hints

### 3. Hermes 回写 event

```http
POST /api/v1/content-agent/runs/{run_id}/events
```

请求：

```json
{
  "step": "ae_score",
  "event_type": "llm_call",
  "expert_code": "ai_smell",
  "model_code": "doubao-seed-2-0-mini-260428",
  "input_snapshot": {},
  "output_snapshot": {},
  "latency_ms": 1200,
  "token_usage": {}
}
```

### 4. Hermes 上传 artifact

```http
POST /api/v1/content-agent/runs/{run_id}/artifacts
```

请求：

```json
{
  "artifact_type": "draft",
  "name": "draft_v1",
  "content_text": "...",
  "metadata": {
    "rewrite_round": 1
  }
}
```

### 5. Hermes 更新 run 状态

```http
POST /api/v1/content-agent/runs/{run_id}/status
```

请求：

```json
{
  "status": "succeeded",
  "output_summary": {
    "title": "...",
    "score": 86,
    "final_artifact_id": 789
  }
}
```

---

## 八、xhs-writer 现状与迁移映射

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

## 九、推荐落地阶段

### 阶段 1：MAGA 存任务、run、结果，Hermes 继续本地执行

目标：验证“工作台 + Agent worker”闭环。

做法：

1. MAGA 增加 executor_registry、content_agent_task、content_agent_run、content_agent_event、content_agent_artifact。
2. MAGA 增加最小 API：claim task、get context、post event、post artifact、update status。
3. Hermes `xhs-writer` 仍然读本地 `experts/`、`ge_writer/`、`campaigns/`。
4. Hermes 跑完后将 draft、final、score report、trace 写回 MAGA。
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

## 十、当前阶段不要做什么

不要做：

- 通用 Agent marketplace
- 通用 DAG / workflow 编排器
- 面向所有业务的万能 Agent 控制台
- 用通用 JSON 表单替代内容生成任务页
- 为未来数据分析提前建 datasource/metric/chart/report 模型
- 让普通用户看到 Agent/Expert/Tool/Trace 的复杂概念
- 让 Hermes 直接写 MAGA MySQL
- 让 MAGA 强依赖 Hermes 本地文件路径

这些会拖慢 MVP，并削弱 MAGA 的营销内容生成定位。

---

## 十一、与 MAGA MVP 架构的关系

本方案补充 `MAGA_MVP_ARCHITECTURE.md` 的“内部生文架构”。

原 MVP 原则保持不变：

- 前台极简
- 后台复杂
- 语料可选
- 编排隐藏
- 输出直接可用

本方案进一步明确：

- 后台复杂度由 MAGA 管理和沉淀
- Agent 执行可外置到 Hermes profile
- MAGA 不把 Hermes 当成护城河，而把业务资产和质量闭环当成护城河
- Hermes 只是当前执行层，未来可替换

---

## 十二、最终定位

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
