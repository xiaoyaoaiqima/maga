# MAGA 调通 Hermes maga-worker Phase 1 开发计划

创建时间：2026-05-09

## 目标

让 MAGA 的 `/api/v1/content-agent/generation/start` 可以通过 Executor Protocol v0.1 同步调用 Hermes `maga-worker` 的真实 `/invoke` 服务，跑通一篇小红书内容生成的 MVP 主链路，并把最终 `title/body` 返回给 MAGA 前台 API。

前期 profile 收敛约定：只管理一个 Hermes worker profile，命名为 `maga-worker`。它内部承载三类能力：

- `xhs.*`：实际产文、审核、改写，承接历史 `xhs-writer` runtime。
- `asset.*`：资料清洗、资产变更提案，承接历史 `maga-asset-steward` 思路。
- `feedback.*` / `prompt.*`：人工反馈总结、训练建议、Prompt/策略提案。

MAGA 仍是 source of truth；`maga-worker` 只作为执行器，不直连 MAGA DB。

## 最新协议摘要

以 `docs/EXECUTOR_PROTOCOL.md` 为准：

1. MAGA 是 source of truth，Executor 不直连 MAGA DB。
2. MAGA 串行推进 stage；每个 stage 调一次 `POST {executor_base}/invoke`。
3. `/invoke` 是同步阻塞 `200 OK` 主路径；MVP 不支持 async `202 ack`。
4. Envelope 顶层必须包含：
   - `protocol_version: "0.1"`
   - `run_id`
   - `task_id`
   - `stage_call_id`
   - `capability`
   - `executor_hints.timeout_seconds`
   - `input`
5. MAGA -> Executor header 必须带：
   - `X-Maga-Protocol-Version: 0.1`
   - `Authorization: Bearer <executor_token>`
6. Executor -> MAGA callbacks 只保留：
   - `/runs/{run_id}/events`
   - `/runs/{run_id}/artifacts`
   - `/runs/{run_id}/human-review`
7. Executor -> MAGA callbacks 必须带：
   - `X-Maga-Protocol-Version: 0.1`
   - `Authorization: Bearer <executor_token>`
   - `X-Stage-Call-Id: <stage_call_id>`
8. 五个 capability：
   - `xhs.interpret_brief`
   - `xhs.run_ae_analysis`
   - `xhs.generate_draft`
   - `xhs.run_ae_review`
   - `xhs.rewrite_draft`
9. `xhs.generate_draft` 协议输出应是 `draft_artifact_id`，draft 正文通过 artifact 回写 MAGA。
10. MVP 对外输出只返回 `title/body`。

## 当前代码现状

### MAGA 已具备

- `ExecutorRegistry`、`ContentAgentTask`、`ContentAgentRun`、`ContentAgentStageCall`、`ContentAgentEvent`、`ContentAgentArtifact`、`ContentAgentHumanReview` 基础表。
- `ExecutorInvocationClient` 能同步 POST `/invoke`，拒绝 202。
- `ContentAgentOrchestrator.run_mvp_generation_chain` 已能按 `executor_registry.invoke_url` 选择 mock 或真实 HTTP executor，并串行跑 stage。
- `/generation/start` 已能返回 `task_id/run_id/title/body`。
- `/generation/start` 已构造最小 `generation_snapshot`，与批量生成共用 worker contract。
- `/batches/start` 已能基于 `asset_registry` 规划多篇内容，逐篇传带资产和多样性约束的 `generation_snapshot`。
- clean schema seed 写入 `hermes_maga_worker`，并保留历史 `hermes_xhs_writer` 兼容别名；根目录 `make init-clean-schema` 默认指向 `http://host.docker.internal:8765/invoke`。

### MAGA 与最新协议差距

- artifact-based draft flow 还未完全按 `draft_artifact_id -> artifact -> review input` 收敛，当前仍兼容直接从 stage output 传 draft。
- rewrite 后的 review 闭环已具备基础条件，但仍需要继续用真实低分/硬审失败样本补测试。
- callback endpoint 的协议校验已具备雏形，后续还要补生产级 token/secret 管理。

### maga-worker / 历史 xhs-writer 现状

- 当前主运行时代码在：`/Users/luxifa/.hermes/profiles/maga-worker/workspace/tools/xhs_runtime.py`。
- 历史能力来源在：`/Users/luxifa/.hermes/profiles/xhs-writer/workspace/tools/xhs_runtime.py`，只作为迁移参考和回退依据。
- 当前入口是本地函数 `run_full_flow(brief_path)`，端到端跑 10 步并写 notes/debug 文件。
- `maga-worker` 目标 profile 路径为：`/Users/luxifa/.hermes/profiles/maga-worker`。
- 协议 v0.1 HTTP `/invoke` 服务已迁入 `maga-worker`，历史 `xhs-writer` workspace 可暂时保留兼容副本。
- runtime 中已有可复用函数：`call_ae`、`build_writing_spec`、`call_ge`、`aggregate_scores`、`run_full_flow`。
- 最小接通可以先实现一个 `maga-worker` HTTP executor adapter，逐步把 `xhs.*` capability 映射到这些函数。

## 分阶段计划

### Step 1：先补协议安全最小闭环（MAGA 侧）

目的：让 MAGA 调真实 `maga-worker` 服务时具备协议要求的 bearer header，并为 `maga-worker` 回调做好校验基础。

任务：

1. TDD：新增 `ExecutorInvocationClient` 测试，要求传入 executor token 后 header 包含 `Authorization: Bearer ...`。
2. 实现 `ExecutorInvocationClient.invoke(..., executor_token=None)`。
3. orchestrator 从 `ExecutorRegistry` 读取 token：
   - MVP 本地开发优先从 `config_json.executor_token` 取。
   - 不输出 token；测试用 fake token。
   - 后续再接 secret ref。
4. TDD：callback endpoint 缺 `X-Maga-Protocol-Version`、缺 `X-Stage-Call-Id`、缺/错 Authorization 返回 401/409。
5. 实现最小 callback auth helper。

验收：

- executor invocation tests 通过。
- content-agent protocol API tests 通过。
- 不打印、不落文档真实 token。

### Step 2：实现 maga-worker `/invoke` skeleton

目的：让 `maga-worker` workspace 有一个可启动 HTTP 服务，能按协议接收 MAGA 调用。

位置建议：

- `/Users/luxifa/.hermes/profiles/maga-worker/workspace/tools/maga_executor_server.py`
- `/Users/luxifa/.hermes/profiles/maga-worker/workspace/tests/test_maga_executor_server.py`

迁移期如果 skeleton 仍暂存于历史 `xhs-writer` workspace，应把它视为 `maga-worker` 的 `xhs.*` 能力来源，而不是独立生产 profile。

任务：

1. TDD：用 FastAPI TestClient 或 httpx ASGITransport 测 `/invoke`。
2. `/invoke` 校验：
   - `X-Maga-Protocol-Version == 0.1`
   - `Authorization: Bearer <MAGA_WORKER_EXECUTOR_TOKEN>`（环境变量）
   - body 必须含 `stage_call_id/capability/input`
3. 对 unknown capability 返回 `200 {status: failed, error_code: input_invalid}`。
4. 对五个 xhs capability 返回协议 envelope。
5. 先用 deterministic stub 确保 MAGA 能网络调通。

验收：

- 能执行：`uvicorn tools.maga_executor_server:app --host 127.0.0.1 --port 8765`。
- curl `/invoke` 返回 `status=succeeded` 或协议 failed envelope。

### Step 3：MAGA 指向真实 maga-worker skeleton 做端到端 smoke

目的：替换 mock executor URL，验证 MAGA 能走 HTTP 到 `maga-worker`。

任务：

1. seed clean schema 时支持：
   - `--maga-worker-invoke-url http://127.0.0.1:8765/invoke`
   - executor token 写入本地 `config_json` 或由环境注入测试 fixture。
2. 启动 `maga-worker` server。
3. 通过 MAGA TestClient 或本地 uvicorn 调 `/generation/start`。
4. 验证 MAGA DB 中：
   - task/run/stage_call 创建成功
   - stage output 写入
   - run succeeded
   - API 返回 title/body

验收：

- 不依赖 mock client 的 MAGA -> `maga-worker` skeleton E2E 通过。

### Step 4：接入 xhs_runtime 的 capability adapter

目的：让 skeleton 从 deterministic stub 逐步升级为真实 `maga-worker` 的 `xhs.*` 运行。

优先顺序：

1. `xhs.interpret_brief`
   - 把 MAGA input 转为 xhs structured brief。
   - 可先不调用 LLM，做轻量结构化。
2. `xhs.run_ae_analysis`
   - 根据 MAGA 传入 `ae_specs` 调 `call_ae(..., mode="instruct")`。
   - 输出 `analyses`。
3. `xhs.generate_draft`
   - 用 `build_writing_spec + call_ge` 生 draft。
   - 通过 callback 上传 artifact 到 MAGA。
   - `/invoke` response 只返回 `draft_artifact_id`。
4. `xhs.run_ae_review`
   - 从 MAGA orchestrator 传入的 draft 调 `aggregate_scores` 或逐 AE score。
   - 输出 hard_results / soft_scores，不返回加权总分。
5. `xhs.rewrite_draft`
   - 用 `call_ge(... feedback, prev_draft)` 改写。
   - 输出 `final`。

验收：

- 至少能在有模型凭证的本地环境完成一次真实生成。
- 无模型凭证时 server 以明确 `model_error` failed envelope 失败，不 crash。

### Step 5：修 MAGA artifact-based draft flow 与 review/rewrite 闭环

目的：严格贴合最新协议。

任务：

1. `generate_draft` stage output 改为 `draft_artifact_id`。
2. orchestrator 根据 artifact_id 查 MAGA artifact，解析 draft title/body。
3. `run_ae_review` input 从 artifact 读取 draft。
4. hard fail / soft 低分时调用 `rewrite_draft`。
5. rewrite 后再跑一次 `run_ae_review`。
6. 仍失败时进入 failed 或 needs_review（MVP 可先 failed，后续接人审）。

验收：

- tests 覆盖 happy path、hard fail rewrite once、missing artifact failed。
- `/generation/start` 仍只返回 title/body。

## 第一批开发切片

马上开始 Step 1 + Step 2 skeleton：

1. 先写 MAGA `ExecutorInvocationClient` bearer token RED 测试。
2. 实现 bearer token header。
3. 写 `maga-worker` `/invoke` skeleton 测试。
4. 实现 `maga-worker` `maga_executor_server.py`，先 deterministic stub。
5. 跑聚焦测试与 compileall。

## 非目标

- 不改历史 Alembic migration。
- 不让 `maga-worker` 或历史 `xhs-writer` runtime 直连 MAGA DB。
- 不在前台暴露 stage trace。
- 不把 MAGA 改成泛 Agent 平台。
- 不把真实 API key/token 写入代码、测试、文档或输出。

## 进展记录（2026-05-09）

已完成 Step 1-3 的最小可运行切片：

1. MAGA -> Executor 已支持 `Authorization: Bearer <executor_token>`；本地 MVP token 来源为 `ExecutorRegistry.config_json.executor_token`。
2. 迁移期历史 xhs-writer workspace 已新增 FastAPI `/invoke` skeleton，已在 2026-05-11 搬迁到 `maga-worker`；历史路径仅保留兼容副本：
   - `/Users/luxifa/.hermes/profiles/xhs-writer/workspace/tools/maga_executor_server.py`
   - `/Users/luxifa/.hermes/profiles/xhs-writer/workspace/tests/test_maga_executor_server.py`
3. MAGA 新增真实 HTTP E2E 测试：
   - `/Users/luxifa/maga/platform-server/tests/test_maga_xhs_writer_http_e2e.py`
   - 测试会启动 skeleton server，把 `executor_registry.invoke_url` 指向真实 `http://127.0.0.1:<port>/invoke`，通过 `/api/v1/content-agent/generation/start` 调用，验证 DB 中四个 stage 均 succeeded，且 stats 来自真实 executor 而不是 mock。
4. `/generation/start` 现在按 `executor_registry.invoke_url` 选择 invocation client：
   - `mock://...` 使用 `MockExecutorInvocationClient`，保留本地 smoke/旧测试能力。
   - `http(s)://...` 使用真实 `ExecutorInvocationClient`，可直接调 `maga-worker` skeleton。
5. 当前验证结果：
   - MAGA E2E + 回归：`36 passed in 1.66s`
   - `maga-worker` / 历史 xhs-writer skeleton：`5 passed in 0.13s`

下一步进入 Step 4/5：逐步把 skeleton deterministic handler 替换为 `xhs_runtime.py` 薄 adapter，并按最新协议把 `xhs.generate_draft` 改成 artifact-based flow（response 只返回 `draft_artifact_id`）。

## 进展记录（2026-05-11）

已把执行入口从历史 `xhs-writer` workspace 收敛到 `maga-worker` workspace：

1. `maga-worker` workspace 已具备独立 `/invoke` skeleton 和 `xhs.*` runtime adapter：
   - `/Users/luxifa/.hermes/profiles/maga-worker/workspace/tools/maga_executor_server.py`
   - `/Users/luxifa/.hermes/profiles/maga-worker/workspace/tools/maga_runtime_adapter.py`
   - `/Users/luxifa/.hermes/profiles/maga-worker/workspace/tools/xhs_runtime.py`
2. runtime 的 profile/workspace 路径已改为按当前文件位置自定位，不再硬编码历史 `xhs-writer` 目录。
3. 历史 `xhs-writer` 的专家资产、GE 风格库、campaign/brief 只作为本地迁移兜底复制到 `maga-worker/workspace`；生产 source of truth 仍是 MAGA API。
4. MAGA E2E 测试已改为启动 `maga-worker/workspace` 下的 `/invoke` server。

当前验证结果：

- `maga-worker` workspace：`17 passed in 0.36s`

### 2026-05-11 补充：批量生成默认执行模式

批量产文会由 MAGA 根据 `asset_registry` 生成 `generation_snapshot`，再把 snapshot 传给 `maga-worker`。`maga-worker` 的 `xhs.generate_draft` 执行模式约定如下：

1. 显式环境变量 `MAGA_WORKER_EXECUTION_MODE` 优先，可选值按 worker 实现解释。
2. 兼容迁移期旧变量 `XHS_WRITER_EXECUTION_MODE`。
3. 未显式配置且输入含 `generation_snapshot` 时，默认走 `runtime_fast`。
4. 未显式配置且没有 snapshot 时，保留 `deterministic`，用于单篇 smoke 和无模型本地调试。

测试环境可设置 `MAGA_WORKER_RUNTIME_FAST_FAKE=1`，让 worker 走 `runtime_fast` 的协议分支但不发起真实模型调用，便于 MAGA HTTP E2E 稳定验证：

- `xhs.generate_draft.output.runtime_result.mode == "runtime_fast"`
- 批量报告 `items[].runtime_mode == "runtime_fast"`
- 批量报告 `items[].generation_duration_ms` 展示生文阶段耗时

当前验证结果：

- `maga-worker` workspace：`20 passed in 0.30s`
- MAGA `platform-server`：`60 passed in 3.39s`

### 2026-05-11 补充：本地启动与单篇真实 worker 链路

已补齐本地开发命令和单篇 snapshot 链路：

1. 根目录 `Makefile` 新增/收敛 worker 命令：
   - `make worker-start`
   - `make worker-stop`
   - `make worker-status`
   - `make worker-logs`
2. `make dev` 启动 Docker 后端栈和前端，并执行 clean schema seed；`maga-worker` 仍需单独 `make worker-start`。
3. `make init-clean-schema` 默认把 `hermes_maga_worker.invoke_url` 写成 `http://host.docker.internal:8765/invoke`，让 Docker 后端调用宿主机 worker。
4. `/generation/start` 和 `/batches/start` 都会把 `generation_snapshot` 透传给所有 `xhs.*` stage。
5. 本地 `make worker-start` 默认 `MAGA_WORKER_EXECUTION_MODE=runtime_fast`、`MAGA_WORKER_RUNTIME_FAST_FAKE=0`，会走真实 fast runtime；只做协议冒烟测试时可临时设置 `MAGA_WORKER_RUNTIME_FAST_FAKE=1` 后重启 worker。

当前最近验证结果：

- MAGA 聚焦回归：`12 passed`
- 真实 HTTP E2E：`2 passed`
- Docker 后端 smoke：`POST /api/v1/content-agent/generation/start` 返回 200，后端日志出现 4 次到 `host.docker.internal:8765/invoke` 的 stage 调用。

## MVP 输入结构补充约定（2026-05-09）

用户侧不是一句话自由输入，而是选择/填写几个结构化字段。推荐内部 payload：

```json
{
  "product_topic": "宝宝便便不规律",
  "target_audience": "新手妈妈",
  "style": "经验老道型",
  "content_constraints": {
    "word_count": 200
  }
}
```

但 `word_count` 不作为用户必填输入；默认字数/篇幅由 MAGA 的内部生成策略管理，并通过 `generation_snapshot.brief.content_constraints.word_count` 下发给 executor。当前 MVP 默认是 `150-250` 中文字，前台仍保持 3 个用户可见字段：产品/主题、目标人群、风格。

## Asset Steward / 资产管理进展（2026-05-09）

已新增 MAGA 统一资产底座和 Asset Steward API 最小闭环：

1. 数据表模型：
   - `asset_registry`：版本化业务资产，存品牌资料、产品卖点、痛点模型、UGC 表述、审核规则等。
   - `asset_import_run`：记录 Excel/语料导入批次。
   - `asset_change_request`：运营自然语言资产变更需求。
   - `asset_change_proposal`：Asset Steward 生成的结构化变更草案，可审核后 apply。
2. 源悦 Excel 已导入本地 MAGA 开发库：
   - `brand_profile:yuanyue`
   - `product_selling_points:yuanyue`
   - `painpoint_model:yuanyue`
   - `ugc_expression_corpus:yuanyue`
   - `compliance_rules:yuanyue`
3. API：
   - `GET /api/v1/assets?asset_key=yuanyue`
   - `GET /api/v1/assets/{asset_type}/{asset_key}`
   - `POST /api/v1/assets/change-requests`
   - `POST /api/v1/assets/change-proposals`
   - `POST /api/v1/assets/change-proposals/{proposal_id}/apply`
4. `maga-worker` 的 `asset.*` 能力后续应只通过这些 API 工作：
   - 读现有 `asset_registry`
   - 根据运营需求创建 `asset_change_request`
   - 生成 `asset_change_proposal`
   - 人审/确认后调用 `apply` 生成新版本资产
   - 再触发 `/content-agent/generation/start` 做 smoke generation
