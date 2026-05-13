# MAGA ↔ Executor Protocol v0.1

## 〇、本文件定位

定义 MAGA（控制面）和任意 Executor（执行面，例如前期统一 Hermes `maga-worker` profile）之间的稳定接口契约。

适用范围：

- 营销内容生成业务的 Agent 执行层
- MAGA 与外部 Executor 的所有跨进程交互

不在本文范围：

- MAGA 内部业务表设计（见 [MAGA_MVP_ARCHITECTURE.md](./MAGA_MVP_ARCHITECTURE.md)）
- 工作流分工的取舍过程（见 [AGENT_EXECUTION_LAYER_PLAN.md](./AGENT_EXECUTION_LAYER_PLAN.md)）
- Hermes profile 内部实现细节

协议版本：`0.1`。所有跨端报文必须带 `X-Maga-Protocol-Version: 0.1` 头。Major 版本不向后兼容。

---

## 一、不变量（INVARIANTS）

以下七条是协议的硬约束。任何实现、任何 Executor 都必须满足。改动需要 bump 协议 major 版本。

### INV-1：Executor 是纯函数

Capability 调用形式上是

```
(snapshot_inputs) → (outputs + event_stream + artifacts)
```

Executor 在 capability 执行期间不得发起任何"自主"的外部访问。允许与禁止：

| 类型 | 例子 | 是否允许 |
|---|---|---|
| 资产查询（回查 MAGA） | 跑到一半再 `GET /products/{id}` | 禁 |
| 外部信息检索 | web_search、查 xhs 热门、第三方审核 API | 禁 |
| 本地纯计算 | calculator、json_validator、本地 regex | 允许（视为内部实现） |
| 协议内回写 | report_event / upload_artifact / request_human_review / complete_capability | 允许（这是协议本身） |

LLM 提供商内置工具（如某些模型的 web_search）默认禁用。v0.1 不开启用机制，需要时 v0.2 协议扩展。

### INV-2：MAGA 是 source of truth

所有需要被人看、改、复用、审计、评估的内容，权威副本在 MAGA。

Executor 端可以有本地 cache、debug 文件、临时草稿，但任何 cache 都不构成业务事实。

### INV-3：资产以 snapshot + 版本号传入

Capability 入参中的所有资产（brand / product / persona / rubric / corpus / style / brief / prompt 等）必须是 inline 的快照，并附 `version_id`。

资产太大时（如全量 corpus），允许使用签名 URL，但 URL 中必须 hash 版本号；Executor 仅可下载字节，不得"搜索/发现"。

### INV-4：Executor 不直连 MAGA 数据库

Executor 与 MAGA 的所有交互必须通过本协议定义的 RPC。任何直连 MySQL / Redis 的实现违反协议。

### INV-5：业务规则归属 MAGA

下列规则的解释权在 MAGA，Executor 不得在内部硬编码：

- `brief_type → ae_codes` 映射
- 评分阈值、权重、`max_rewrites`
- hard / soft AE 划分
- 状态机转移规则
- 模型路由（每个 AE/GE 用什么模型）

MAGA 解释完后，把结果（如 `ae_codes[]`、`weights{}`、`model_code`）作为 capability 入参显式传给 Executor。

### INV-6：状态转移由 MAGA 校验

Executor 不直接写 run 状态。Executor 通过 `complete_capability` / `fail_capability` / `request_human_review` 等动作请求转移；MAGA 校验合法性后落库。

### INV-7：Trace 使用 OTel GenAI 语义约定

所有 LLM 调用事件必须使用 OpenTelemetry GenAI semantic conventions 字段（见第十章）。MAGA 域扩展使用 `maga.*` 前缀。Hermes 私有字段使用 `hermes.*` 前缀，但不得替代标准字段。

---

## 二、术语

| 术语 | 含义 |
|---|---|
| Task | 一次业务请求（如"生成一篇小红书种草笔记"） |
| Run | 一次具体执行尝试。一个 Task 可有多次 Run（重试或人工触发的复跑） |
| Stage | Run 内的一个阶段，对应一次 capability 调用 |
| Capability | Executor 提供的、可被 MAGA 调用的能力单元 |
| Profile | 某个 Executor 实例的能力组合（如 `hermes:maga-worker`） |
| Stage Call | 一次具体的 capability 调用，由 `stage_call_id` 唯一标识 |
| Artifact | Capability 产出的可追溯对象（draft、final、score_report 等） |
| Event | Capability 执行过程中的细粒度可观测事件（llm_call、tool_call、warning 等） |
| Snapshot | 资产在某一时刻的不可变副本，附 `version_id` |

---

## 三、拓扑与控制流

```
┌────────────┐   ① invoke_capability        ┌─────────────┐
│            │ ─────────────────────────►   │             │
│   MAGA     │                              │  Executor   │
│  (control) │ ◄─── ② report_event*  ────── │  (Hermes)   │
│            │ ◄─── ③ upload_artifact* ──── │             │
│            │ ◄─── ④ request_human_review  │             │
│            │ ◄─── ⑤ complete_capability   │             │
└────────────┘                              └─────────────┘
       │                                          ▲
       │  ⑥ resume (after human review)           │
       └──────────────────────────────────────────┘
```

控制流要点：

- MAGA 串行驱动 Run 在阶段间的推进。每一个 Stage 由 MAGA 用一次 `invoke_capability` 启动。
- Executor 接受调用后，可在阶段内并行多个 LLM 调用、流式回报 `report_event`、上传 `upload_artifact`。
- Stage 完成时 Executor 调 `complete_capability`，MAGA 校验、落库、决定下一阶段。
- 阶段之间天然是 gate：MAGA 可在任意阶段间插入人审、超时、重试、取消。

阶段间通信：**sync HTTP**。`invoke_capability` 阻塞返回 stage 结果；events / artifacts / human-review 在阶段执行期间通过协议固定路径回写到 MAGA（路径见 §6.1）。Capability 必须在 `executor_hints.timeout_seconds` 内完成；超时由 MAGA 端 HTTP 客户端处理，标 stage `failed(timeout)`。MVP 不支持 async ack 模式。

---

## 四、Run 状态机

```
                  ┌──────────┐
                  │  pending │
                  └────┬─────┘
                       │ start
                       ▼
                  ┌──────────┐  cancel    ┌────────────┐
                  │  running │ ─────────► │ cancelled  │
                  └────┬─────┘            └────────────┘
                       │
   ┌───────────────────┼────────────────────┐
   │                   │                    │
   ▼                   ▼                    ▼
needs_review        succeeded            failed
(human gate)        (terminal)          (terminal)
   │
   │ resume(human_response)
   ▼
running
```

`running` 子状态（仅 MAGA 内部观察）：

```
running.interpreting_brief
running.analyzing
running.drafting
running.reviewing
running.rewriting
```

合法转移由 MAGA 校验。Executor 调用任何会转移状态的 RPC 时，MAGA 必须做以下检查：

- `run.status` 在转移前置集合内
- `stage_call_id` 与 MAGA 当前期望的 stage 一致

不合法转移返回 `409 Conflict`，Executor 应**停止该 run 的工作**而不是重试。

---

## 五、Capability 清单（v0.1，xhs 域）

五个 capability，按调用顺序：

| # | Capability | 职责 | 期望耗时 |
|---|---|---|---|
| 1 | `xhs.interpret_brief` | 解析 brief 为结构化输入 | <10s |
| 2 | `xhs.run_ae_analysis` | 一组前置 AE 并行分析（痛点/卖点/叙事/人设等） | <30s |
| 3 | `xhs.generate_draft` | GE 拼 prompt + 生 draft | <20s |
| 4 | `xhs.run_ae_review` | 一组评分 AE 并行评分（hard 0/1 + soft 0-100） | <30s |
| 5 | `xhs.rewrite_draft` | 基于评分反馈改写 draft | <20s |

Capability 命名约定：`<domain>.<verb_noun>`。MAGA 用 `domain` 选 Executor，用 `verb_noun` 选 capability。

新增 capability 不需要 bump 协议 major 版本，但 capability 自身的入参/出参 schema 有自己的 `schema_version`。

Capability 域可扩展。`xhs.*` 是 v0.1 唯一启用的内容生成域；未来 prompt 优化、评测回放等会在 `prompt.*`、`eval.*` 等域下新增 capability。新增域不破坏 v0.1 协议——Executor 在调用 MAGA 注册 endpoint 时声明自己实现的 capability 列表即可（v0.2 加 `executor_registry` 字段或独立配置）。

---

## 六、Capability 入参与出参 Schema

约定：所有 schema 用 JSON 表示。`?` 表示可选字段。`@` 表示该字段为版本化资产 snapshot，必带 `version_id`。

### 6.1 公共信封

每次 `invoke_capability` 入参的外层信封：

```json
{
  "protocol_version": "0.1",
  "stage_call_id": "stage_01HF7Z3Q...",
  "run_id": "run_01HF7Z2K...",
  "task_id": "task_01HF7Z1A...",
  "capability": "xhs.interpret_brief",
  "executor_hints": {
    "model_overrides": { "ge_main": "deepseek-v3.2" },
    "timeout_seconds": 60
  },
  "input": { /* capability-specific, 见下 */ }
}
```

回调地址不在入参中传递。Executor 启动时配 `MAGA_BASE_URL` 环境变量，按协议固定路径拼接：

```
{MAGA_BASE_URL}/api/v1/content-agent/runs/{run_id}/events
{MAGA_BASE_URL}/api/v1/content-agent/runs/{run_id}/artifacts
{MAGA_BASE_URL}/api/v1/content-agent/runs/{run_id}/human-review
```

回调路径是协议契约的一部分，MAGA 不可单方面变更。v0.2 视需求加 `callback_overrides` 字段允许指向不同服务（如 artifacts 走 OSS）。

出参（sync `/invoke` 响应 body）信封：

```json
{
  "stage_call_id": "stage_01HF7Z3Q...",
  "status": "succeeded",
  "output": { /* capability-specific */ },
  "stats": {
    "total_latency_ms": 18234,
    "llm_calls": 9,
    "total_input_tokens": 12450,
    "total_output_tokens": 2340
  }
}
```

失败时响应 body：

```json
{
  "stage_call_id": "stage_01HF7Z3Q...",
  "status": "failed",
  "error_code": "model_error" | "input_invalid" | "internal_error",
  "error_message": "..."
}
```

### 6.2 `xhs.interpret_brief`

**Input**

```json
{
  "brief": "@brief_snapshot",
  "assets": {
    "brand":   "@brand_snapshot",
    "product": "@product_snapshot?",
    "campaign":"@campaign_snapshot?"
  },
  "model_code": "provider-default-or-explicit-model",
  "prompt": "@prompt_snapshot"
}
```

**Output**

```json
{
  "structured_brief": {
    "brief_type": "xhs_product_seeding_professional_advisor",
    "target_audience": "二胎经验妈妈",
    "key_painpoints": ["夜醒频繁", "...."],
    "key_sellingpoints": ["...."],
    "tone_hints": ["专业育婴建议", "情绪共情"],
    "must_mention": ["a2 蛋白", "..."],
    "must_avoid":   ["疗效暗示", "..."]
  },
  "interpreter_notes": "..."
}
```

注意：`brief_type` 由 interpreter 推断，但 MAGA 在 stage 完成后会用自己的规则**校验**它，并据此决定第二阶段 `ae_codes`。Executor 不能据 `brief_type` 决定下一阶段。

### 6.3 `xhs.run_ae_analysis`

**Input**

```json
{
  "structured_brief": { /* 上一阶段 output */ },
  "assets": {
    "brand":   "@brand_snapshot",
    "product": "@product_snapshot?",
    "persona": "@persona_snapshot?",
    "corpus":  "@corpus_snapshot?"
  },
  "ae_specs": [
    {
      "ae_code": "painpoint_anchor",
      "model_code": "doubao-seed-2-0-mini",
      "persona": "@prompt_snapshot",
      "rubric":  "@prompt_snapshot?",
      "score_type": null,
      "output_mode": "fixed"
    },
    { "ae_code": "sellingpoint_logic", "...": "..." }
  ]
}
```

**Output**

```json
{
  "analyses": {
    "painpoint_anchor":   { "analysis": "...", "extracted": {...} },
    "sellingpoint_logic": { "analysis": "...", "extracted": {...} },
    "...": "..."
  },
  "failed_aes": []
}
```

并行策略：Executor 内部并行执行多个 AE，并行度自决。

部分失败处理：MVP 任一 AE 失败 = 整 capability 失败。`failed_aes` 字段保留为 v0.2 partial-success 语义预留，v0.1 总是空数组。

### 6.4 `xhs.generate_draft`

**Input**

```json
{
  "structured_brief": {...},
  "analyses": { /* 上一阶段 output.analyses */ },
  "assets": {
    "brand":          "@brand_snapshot",
    "product":        "@product_snapshot?",
    "style_template": "@style_template_snapshot",
    "corpus":         "@corpus_snapshot?",
    "voice_dictionary":"@voice_dictionary_snapshot?",
    "lessons":        "@lessons_snapshot?"
  },
  "ge_spec": {
    "ge_code": "ge_main",
    "model_code": "deepseek-v3.2",
    "persona":  "@prompt_snapshot",
    "output_mode": "article_output"
  },
  "rewrite_context": null
}
```

`rewrite_context` 在首次生成时为 `null`；改写阶段由 `xhs.rewrite_draft` 使用，不在本 capability。

**Output**

```json
{
  "draft_artifact_id": "art_01HF7Z..."
}
```

`draft_artifact_id` 引用 Executor 在阶段内通过 `upload_artifact` 上传的 draft；output 不冗余传 draft 全文。MAGA 后续阶段读 draft 时按 artifact_id 查表。

### 6.5 `xhs.run_ae_review`

**Input**

```json
{
  "draft": { "title": "...", "body": "..." },
  "structured_brief": {...},
  "assets": { "brand": "@brand_snapshot", "...": "..." },
  "hard_ae_specs": [
    {
      "ae_code": "brand_product_guard",
      "model_code": "doubao-seed-2-0-mini",
      "persona": "@prompt_snapshot",
      "rubric":  "@prompt_snapshot",
      "score_type": "0/1"
    }
  ],
  "soft_ae_specs": [
    {
      "ae_code": "xhs_structure",
      "model_code": "doubao-seed-2-0-mini",
      "persona": "@prompt_snapshot",
      "rubric":  "@prompt_snapshot",
      "score_type": "0-100"
    }
  ]
}
```

**Output**

```json
{
  "hard_results": [
    { "ae_code": "brand_product_guard", "pass": true,  "feedback": "..." },
    { "ae_code": "compliance_redline",  "pass": false, "feedback": "..." }
  ],
  "soft_scores": [
    { "ae_code": "xhs_structure",          "score": 88, "feedback": "..." },
    { "ae_code": "naturalness_ai_smell",   "score": 76, "feedback": "..." }
  ],
  "failed_aes": []
}
```

注意：

- Executor **不**返回加权总分。聚合 `Σ(score × weight)` 在 MAGA 完成（INV-5）。
- `feedback` 必须是结构化文本，能直接喂给下一轮 `rewrite_draft`。
- hard AE 任一不过 → MAGA 决定走 rewrite 或 needs_review。

### 6.6 `xhs.rewrite_draft`

**Input**

```json
{
  "previous_draft": { "title": "...", "body": "..." },
  "structured_brief": {...},
  "assets": { "brand": "@brand_snapshot", "...": "..." },
  "review_report": {
    "hard_results": [
      { "ae_code": "compliance_redline", "pass": false, "feedback": "..." }
    ],
    "soft_scores": [
      { "ae_code": "naturalness_ai_smell", "score": 76, "feedback": "..." }
    ],
    "failed_aes": ["compliance_redline"]
  },
  "rewrite_round": 1,
  "ge_spec": { "ge_code": "ge_main", "model_code": "deepseek-v3.2", "persona": "@prompt_snapshot" }
}
```

**Output**

```json
{
  "final": { "title": "...", "body": "..." },
  "rewrite_notes": "..."
}
```

`final` 是改写后的可交付内容。MVP 对外交付只取 `title` + `body`；如果 Executor 内部草稿包含 hashtags，MAGA 也不会把它并入 `final_content`。

由 MAGA 中转 feedback（rewrite-decision-1：feedback 不在 Executor 端缓存）。`rewrite_round` 用于让 GE 知道是第几轮（影响 prompt 风格），不是控制流变量。

---

## 七、协议 RPC

### 7.1 MAGA → Executor

#### `POST {executor_base}/invoke`

发起一次 capability 调用。Body 为第 6.1 节的入参信封。

响应：`200 OK` + 出参信封（含 `output` 或 `error_code`）。MVP 不区分 sync/async，全部 sync 阻塞返回。

幂等：相同 `stage_call_id` 重入应返回与首次相同的结果。

### 7.2 Executor → MAGA

所有从 Executor 发起的 RPC 必须带：

```
X-Maga-Protocol-Version: 0.1
Authorization: Bearer <executor_token>
X-Stage-Call-Id: <stage_call_id>
```

#### `POST /api/v1/content-agent/runs/{run_id}/events`

流式上报 capability 执行内的事件（在 sync `/invoke` 调用持有期间，通过独立连接回写）。Body：

```json
{
  "stage_call_id": "stage_...",
  "event_type": "llm_call" | "warning" | "info",
  "occurred_at": "2026-05-08T12:34:56.789Z",
  "expert_code": "ai_smell",
  "input_snapshot":  { "...": "..." },
  "output_snapshot": { "...": "..." },
  "otel_attributes": {
    "gen_ai.request.model": "doubao-seed-2-0-mini",
    "gen_ai.usage.input_tokens": 1234,
    "gen_ai.usage.output_tokens": 567,
    "maga.run_id": "run_...",
    "maga.expert_code": "ai_smell"
  },
  "latency_ms": 1234,
  "message": "..."
}
```

可批量上报：body 也可为 `{ "events": [...] }`。

#### `POST /api/v1/content-agent/runs/{run_id}/artifacts`

```json
{
  "stage_call_id": "stage_...",
  "artifact_type": "draft" | "final_content" | "score_report" | "conflict_report" | "prompt_patch" | "debug_log",
  "name": "draft_v1",
  "content_text": "...",
  "content_json": null,
  "file_url": null,
  "version_no": 1
}
```

响应：`{ "artifact_id": "art_..." }`，供后续 stage output 引用。

#### `POST /api/v1/content-agent/runs/{run_id}/human-review`

```json
{
  "stage_call_id": "stage_...",
  "reason": "max_rewrites_reached" | "hard_ae_failed" | "executor_requested",
  "payload": { "...": "..." }
}
```

请求该 run 进入 `needs_review` 状态。MAGA 校验后返回 `200 OK`；Executor 应停止该 stage 的进一步动作并退出。MVP 阶段评审表单 UI 硬编码在前端，不在协议中传 schema。

后续由 MAGA 在用户提交反馈后，通过 `invoke_capability` 重启一个新 stage（或新 run）。Executor 不直接接收 human response，需要的字段会以 input 形式重新传入。

---

## 八、错误码与幂等

### 8.1 错误码

Capability 失败时 `/invoke` 响应 `status=failed` + `error_code`：

| `error_code` | 含义 |
|---|---|
| `input_invalid` | schema 校验失败、缺字段 |
| `model_error` | 模型 API 调用失败 |
| `executor_timeout` | 超 `executor_hints.timeout_seconds` |
| `executor_internal` | Executor 自身崩溃 |
| `business_reject` | 模型连续生成不合规内容；MAGA 转 `needs_review` |

MVP 不做自动重试。失败的 stage 直接落 `failed`，由运营手动决定重新开 task 还是放弃。v0.2 再加重试策略。

### 8.2 幂等

MAGA → Executor 的 `/invoke` 通过 `stage_call_id` 幂等：相同 ID 重入应返回与首次相同的结果。

Executor → MAGA 的写动作（events / artifacts / human-review）MVP 不做去重；假定单 worker 单连接不会重发。如出现极少量重复行，前台展示侧合并。v0.2 视实际情况加 `Idempotency-Key`。

---

## 九、安全与认证

MVP 简化方案：

- MAGA 为每个 Executor 配一个 `executor_token`（长期 bearer），双向使用：Executor 调 MAGA 带 `Authorization: Bearer <token>`，MAGA 调 Executor 也带同一 token。
- 严格说这是 shared secret 而非 bearer，token 泄露双向都受影响。MVP 单 worker 内网部署可接受，**v0.2 必须拆为两个独立 token**（`executor_inbound_token` / `maga_inbound_token`），可独立轮转。
- MVP 假定内网或本地部署。

v0.2 再加（公网部署前必须做）：

- 双向 token 拆分（见上）
- HMAC 签名（防中间人篡改）
- 资产签名 URL 的密钥管理
- Token 自动轮转
- 多租户 / 行级权限

---

## 十、OpenTelemetry GenAI 字段映射

LLM 调用事件 `otel_attributes` MVP 必须包含的最小字段（采用 OTel GenAI 命名以便未来无缝接入观测平台）：

| 字段 | 含义 |
|---|---|
| `gen_ai.request.model` | 模型 ID |
| `gen_ai.usage.input_tokens` | 输入 token |
| `gen_ai.usage.output_tokens` | 输出 token |

MAGA 域扩展 MVP 必传：

| 字段 | 含义 |
|---|---|
| `maga.run_id` | 关联 run |
| `maga.stage_call_id` | 关联 stage call |
| `maga.expert_code` | 当前 AE/GE |
| `maga.prompt_version_id` | 使用的 prompt 版本（外循环聚合用） |

其他 OTel 字段（`gen_ai.system` / `temperature` / `finish_reasons` 等）和 MAGA 字段（`task_id` / `capability` / `brand_id` 等）best-effort 上报，不强制。v0.2 视聚合分析需求再约束。

Hermes 私有扩展使用 `hermes.*`，仅供调试。

---

## 十一、与现有数据模型的对应

协议概念到 MAGA 表的映射，详见 [AGENT_EXECUTION_LAYER_PLAN.md](./AGENT_EXECUTION_LAYER_PLAN.md) §六 数据模型。

---

## 十二、验收标准

协议合格的判定不是"跑通了"，而是以下三项：

### V-1：替换执行器零业务表改动

把现有 Hermes `maga-worker` 替换为另一个 Executor（例如一个 LangGraph 服务、一个 OpenAI Assistants worker），需要的改动**仅限**：

- `executor_registry` 新增一行
- 新 Executor 实现五个 capability 的 invoke endpoint
- 一个适配层（如有必要）

不允许的改动：`content_agent_task` / `content_agent_run` / `content_agent_event` / `content_agent_artifact` 任何字段调整。

### V-2：业务规则改动零 Executor 变更

在 MAGA 调整下列任一项，**不**应触发 Executor 部署或代码改动：

- `_brief_types.yaml` 中加新 brief_type
- 修改 `score_threshold` / `weights` / `max_rewrites`
- 修改 hard / soft AE 划分
- 给 AE 换底座模型
- 改 prompt 内容

### V-3：单 run 完全可复现

给定同一份 task input 和同一组资产 snapshot 版本：

- 重跑应得到相同 trace 结构（不要求 LLM 输出逐字相同，但事件序列、stage 次数、capability 调用次数相同）
- 资产版本号在 trace 中可还原

---

## 十三、未决问题（v0.1 暂不规约，先用默认值）

1. **多 Executor 并发抢同一 run**：当前假设每个 run 只有一个 Executor 实例处理。多实例池化、负载均衡 v0.2 规约。
2. **流式 token 输出**：v0.1 不在协议层支持 token-level streaming；需要的话由 Executor 内部完成不暴露。
3. **资产签名 URL 的具体格式**：v0.1 留空，由 MAGA 实现侧自定。
4. **Cancel 的传播延迟上限**：v0.1 不强约束，建议 Executor 在 5s 内响应。
5. **Capability schema 演进**：当前用 `schema_version` 字段做版本号，但破坏性变更的兼容窗口策略未定。
6. **多 run 的批处理优化**：例如同一批 AE 评分跨 run 合并到一个 LLM 调用。v0.1 不允许（违反 INV-3 的快照独立性），v0.2 评估。
7. **离线 / 批量回放**：用历史 trace + snapshot 回放某次 run 用于评估的协议形态。

---

## 十四、变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 0.1 | 2026-05-08 | 初稿。定义不变量、状态机、五个 xhs capability、RPC、OTel 映射、验收标准。 |
