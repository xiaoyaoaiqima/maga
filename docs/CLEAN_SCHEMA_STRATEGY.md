# MAGA Clean Schema Strategy

Date: 2026-05-08

## 背景判断

MAGA 当前 `platform-server` 是从老系统演化来的，仓库里同时存在：

1. 新 MAGA 内容生成工作台需要的核心模型。
2. 老系统残留的 Job / SubJob / ExpertBusinessResult / RLHF / graph / plugin / system admin 等模型。
3. 为兼容旧接口和旧前台而保留的 endpoint / service。

因此第一阶段不应该再被历史 Alembic migration 链拖住。开发期 schema 以“最新 SQLAlchemy model / 新 MAGA clean model”为准，历史 migration 只作为参考，不作为 source of truth。

## 原则

- 不修历史 migration 链。
- 不为了旧表继续扩展新功能。
- 新开发优先走 clean schema。
- 老系统模型不再默认保留；确认不在当前运行路径后可以物理删除，历史表由 migration 记录保留，不额外 drop。
- 生产边界仍是 MAGA API，不让 Hermes `maga-worker` 或历史 `xhs-writer` runtime 直连 MAGA DB。
- 本地开发库可以 drop/create；需要保留旧数据时另建库，不在同一库里混迁移。

## 建议的模型分层

### Tier 1: Phase 1 必须保留 / 继续演进

这些是 MAGA 作为营销内容 source of truth 和执行控制平面的核心：

- ContentBrief：业务 brief / 生文需求快照。
- ContentTask：待执行内容任务。
- ContentRun：一次执行。
- RunEvent：执行 trace / AE instruct / score / decision。
- Artifact：brief.yaml / draft / final / score report / trace。
- ExecutorRegistry：Hermes `maga-worker` 等执行器登记。

当前已落地的近似模型：

- `ContentAgentTask`
- `ContentAgentRun`
- `ContentAgentEvent`
- `ContentAgentArtifact`
- `ExecutorRegistry`

短期可继续用这些名字推进第一阶段；中期可以再重命名成更业务化的 `ContentTask` / `ContentRun` / `RunEvent` / `Artifact`。

### Tier 2: MAGA 资产中心需要，但应 clean 重建

这些概念有价值，但老系统模型未必可直接继承：

- BrandRuleSet
- Product / ProductAsset
- PainpointSellingMap
- ExpertDefinition
- ExpertRuleSet
- GenerationStrategy
- ScoreRubric
- HumanReview
- Corpus / CorpusItem
- StyleTemplate

旧系统里可能有相近模型，例如：

- `ExpertConfig`
- `Agent`
- `Activity`
- `Tenant`
- `ContentStrategy`
- `CorpusTemplate`
- `BanTerm`
- `KnowledgeBase`

但它们不应默认作为新 MAGA schema 的核心。可以迁移数据或借鉴字段，不应该让新执行层依赖它们。

### Tier 3: Legacy / 暂不作为新 MAGA 主路径

这些明显偏旧执行系统、旧 RLHF、旧管理后台或旧实验功能：

- `Job`
- `SubJob`
- `Content`
- `ExpertBusinessResult`
- `ExpertCallTrace`
- `ExpertTask`
- `JobCreateDraft`
- `JobVariant`
- `RLHFFeedback`
- `RLHFOperationHistory`
- `RLHFIssueTag`
- `RLHFDailyStats`
- `CriticScoreRecord`
- `CriticScoreDailyStats`
- `ExpertEvalRun`
- `ExpertEvalResult`
- `ABExperiment` / `ABTest`
- `GraphNode` / `GraphEdge` / `NodePropertyMeta`
- `Plugin` / `PluginContext`
- `SysUser` / `SysRole` / `SysMenu` / role/menu relation tables
- `Message` / `MessageRecipient`
- `CalibrationTask` / `CalibrationRecord`
- `MetricDefinition`

这些不建议进入第一阶段新链路。

## Clean schema 开发策略

## Clean API 运行模式

生产环境优先启用：

```bash
MAGA_APP_MODE=clean
```

clean 模式先收敛运行面，不删除旧代码和旧表：

- 只注册 MAGA 当前生产工作台需要的 API：`auth`、`health`、`content-agent`、`assets`、`content-generation-experts`、`llm-providers`、`files`、`system/info`。
- 不注册旧 RAAP 的 `jobs`、`expert-tasks`、`rlhf`、`ab-tests`、`plugins`、`plugin-contexts`、`dashboard`、`critic/generation internal` 等路由。
- 启动时跳过旧 Job / ExpertTask / dashboard cache scheduler，不再把历史定时任务放进生产运行面。
- 默认管理员初始化仍保留，确保控制台可以正常登录。

`MAGA_APP_MODE=full` 保留完整历史路由，适合本地排查旧功能或迁移数据。生产 compose 默认使用 clean 模式。

### 本地开发库

建议保留两个库：

- `maga`：旧开发库，暂不破坏。
- `maga_clean` 或 `maga_phase1`：新 MAGA clean schema 试验库。

对 clean 库使用：

```bash
cd /Users/luxifa/maga/platform-server
MYSQL_HOST=127.0.0.1 MYSQL_DATABASE=maga_clean ../.venv/bin/python scripts/create_clean_schema.py
```

当前仓库根目录提供了统一入口：

```bash
make init-clean-schema
```

该命令会创建/补齐 MAGA clean schema，并 seed 默认执行器：

- `hermes_maga_worker`：统一的 Hermes `maga-worker` 执行器。

默认 `MAGA_WORKER_INVOKE_URL` 为 `http://host.docker.internal:8765/invoke`，适合 Docker 后端调用宿主机上运行的 `maga-worker` HTTP 服务。如果只想先跑平台内置 mock，可以显式切回：

```bash
MAGA_WORKER_INVOKE_URL=mock://maga-worker/invoke make init-clean-schema
```

脚本行为：

1. 导入 clean model registry。
2. `Base.metadata.drop_all()` 可选，仅限明确设置 `--drop`。
3. `Base.metadata.create_all()`。
4. 写入最小 seed：executor registry。

### Alembic

短期：

- 不再依赖 001-028 历史链验证新功能。
- 028 可以保留作迁移参考，但第一阶段验证以 clean schema 为准。

中期：

- 新建 clean baseline migration，例如 `001_clean_maga_baseline.py`，只包含新 MAGA 核心表。
- 或者创建新的 Alembic version location，例如 `alembic_clean/`，避免与老系统 revision 混在一起。

### App model registry

现状 `app/models/__init__.py` 导入了所有老模型，导致 `Base.metadata.create_all()` 会创建大量 legacy 表。

建议增加一个 clean registry：

- `app/models/clean/__init__.py`
- 或 `app/models/maga_core.py`

只导入新 MAGA 核心模型。clean schema 脚本只使用这个 registry。

旧模型文件不再作为默认保护对象。只要没有当前 router/service/test/import 依赖，就应该从运行代码移除；历史 migration 可以继续保留对应表结构信息。

## 对第一阶段执行层的影响

第一阶段后续开发只依赖：

- content-agent API
- content-agent service
- content-agent clean models
- `maga-worker` `/invoke` HTTP 服务

不要依赖：

- `Job`
- `SubJob`
- `Content`
- `ExpertBusinessResult`
- `ExpertCallTrace`
- 老 `Agent` / `ExpertConfig` 编排表

当前内容生成配置以业务规则包、系统关键词和生文 Expert 为 source of truth，不再维护历史 `xhs.*` 执行链。

## 下一步代码调整建议

1. 给 app 增加配置开关，例如 `MAGA_SCHEMA_MODE=clean|legacy`：
   - clean：只注册新 MAGA 路由。
   - legacy：保持当前全量 router。
2. 继续收敛 `/invoke` push 链路：
   - 批量文章和评论都由 MAGA 构造 unified generation input。
   - MAGA 按 `executor_registry.invoke_url` 调 `maga-worker`。
   - `mock://...` 只作为显式 smoke/mock 模式。
   - `http(s)://...` 作为本地和服务器推荐执行模式。
3. 补齐资产和反馈治理：
   - `asset_registry` 继续作为资料 source of truth。
   - `content_feedback` 记录通过、要求修改、人工改写等反馈。
   - 反馈只产出人工可读建议，不做自动学习和自动改规则。
4. 中期再把模型命名从 `ContentAgent*` 收敛为更稳定的业务名。
