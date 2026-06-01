# RAAP 开发任务清单

> **最后更新**: 2026-01-09  
> **项目分支**: `feature/raap-business-module-20251210`

本文档集中管理所有待开发任务和进度追踪。设计文档请参考 [docs/plan.md](./docs/plan.md)。

---

## 一、进度概览

**整体完成度**: 96% (核心功能)

| 模块 | 完成度 | 说明 |
|------|--------|------|
| 🟢 **基础框架** | 100% | 认证、权限、菜单 |
| 🟢 **业务管理** | 100% | 租户、活动、Agent |
| 🟢 **配置管理** | 100% | Plugin、ExpertConfig、PluginContext |
| 🟢 **Job 工作台** | 98% | 待补可视化图表 |
| 🟢 **Expert 调试器** | 100% | 单步调试、Prompt 预览 |
| 🟢 **Dashboard** | 95% | 核心指标 SQL 已就绪 |
| 🟢 **调用追踪** | 100% | 全链路追踪 |
| 🟡 **A/B 实验** | 60% | 后端已完成，前端待开发 |
| 🟢 **LLM Provider** | 100% | 多模型适配、路由、熔断 |
| 🟡 **Ban V2 防幻觉** | 80% | 代码完成，待测试部署 |
| 🟢 **RLHF 喜欢采纳** | 95% | 统计报表与任务待补 |
| 🟢 **内容池分发** | 100% | Match/Acquire/Ack API 已上线 |
| 🟢 **系统信息** | 100% | K8s/DB/Redis 健康检查 |
| 🟢 **Redash 集成** | 100% | K8s 部署 + 统一查询 API |
| 🟢 **Copilot 智能助手** | 100% | LangGraph + 前端浮球 |
| 🟢 **关键词语料系统** | 90% | 核心功能完成，策略映射完善中 |

---

## 二、待开发任务

### 🔴 P1 高优先级

| 任务 | 说明 | 预计时间 | 相关文档 |
|------|------|---------|---------|
| **提示词优化工作台 MVP - 数据闭环** | 将现有自动优化提示词脚本系统化，支持 Prompt/Run/Patch 存储、三类优化模式、结构化结果查询 | 2 天 | [PROMPT_OPTIMIZER_WORKBENCH_MVP.md](./PROMPT_OPTIMIZER_WORKBENCH_MVP.md) |
| **Ban V2 防幻觉审核** | 解决 LLM 审核误报违禁词问题，证据驱动 + 后验证 | 1 天 | [ENHANCED_BAN_GUIDE.md](../raap-service-ag/docs/ENHANCED_BAN_GUIDE.md) |
| **A/B 实验前端** | 实验配置与管理页面 `/trace/experiments` | 2 天 | [plan.md#3.12](./docs/plan.md) |
| **微服务版本管理** | `system_version` 表 + 版本显示逻辑 | 0.5 天 | [plan.md#二](./docs/plan.md) |

### 🟡 P2 中优先级

| 任务 | 说明 | 预计时间 | 相关文档 |
|------|------|---------|---------|
| **提示词优化工作台 MVP - 人工审阅** | 支持 patch 接受/拒绝/编辑、唯一命中自动应用、保存为新 Prompt 版本、版本 diff | 2 天 | [PROMPT_OPTIMIZER_WORKBENCH_MVP.md](./PROMPT_OPTIMIZER_WORKBENCH_MVP.md) |
| **RLHF 统计报表** | 前端页面 `/rlhf/stats` | 1 天 | [RLHF_SYSTEM_DESIGN.md](./docs/RLHF_SYSTEM_DESIGN.md) |
| **RLHF 每日统计任务** | `GET /api/v1/rlhf/stats/daily` Scheduler | 0.5 天 | [plan.md#3.16.4](./docs/plan.md) |
| **对齐治理中心指标** | 输入治理/多样性/内容丰富度/平台对抗（10+项） | 2 天 | [METRICS_SYSTEM_DESIGN.md](./docs/METRICS_SYSTEM_DESIGN.md) |

### 🟢 P3 低优先级

| 任务 | 说明 | 预计时间 | 相关文档 |
|------|------|---------|---------|
| **Job 流程可视化** | `JobFlowChart.vue` (VueFlow) | 1 天 | [plan.md#4.2](./docs/plan.md) |

### ⬜ Backlog（长期规划）

| 任务 | 说明 | 相关文档 |
|------|------|---------|
| 活人感 Expert | AG Expert 组扩展 | [EXPERT_DEVELOPMENT_GUIDE.md](./docs/EXPERT_DEVELOPMENT_GUIDE.md) |
| Expert CLI 脚手架 | 快速生成 Expert 模板 | [EXPERT_DEVELOPMENT_GUIDE.md](./docs/EXPERT_DEVELOPMENT_GUIDE.md) |
| Expert 测试套件 | 自动化测试框架 | [EXPERT_DEVELOPMENT_GUIDE.md](./docs/EXPERT_DEVELOPMENT_GUIDE.md) |

---

## 三、待开发指标（详细）

> 详细设计见 [METRICS_SYSTEM_DESIGN.md](./docs/METRICS_SYSTEM_DESIGN.md) 和 [DASHBOARD_QUERY_DEV.md](./docs/DASHBOARD_QUERY_DEV.md)

### 3.1 全链路指标（0/1）

| 指标 | 状态 | 说明 |
|------|------|------|
| `available_content_per_unit_cost` (ACPU) | ⬜ | 需等待 AG 拦截数据积累 |

### 3.2 AI 算力看板（待开发 5/13）

| 指标 | 状态 | 说明 |
|------|------|------|
| `total_compute_cost` | ⬜ | 需对接 K8s Metrics |
| `cost_per_quality_point` | ⬜ | 需关联内容评分数据 |
| `storage_cost` | ⬜ | 需对接存储账单 |
| `rlhf_labeling_cost` | ⬜ | 需对接人工工时/单价 |
| `stage_quality_impact` | ⬜ | 需离线分析模型 |

### 3.3 对齐治理中心 AG（待开发 13/15）

| 指标 | 状态 | 阻塞点 |
|------|------|--------|
| `ag_illegal_expert_reject_count/percent` | ⬜ | 需细化 Expert 维度 |
| `ag_unreasonable_expert_reject_count` | ⬜ | 需细化 Expert 维度 |
| `ag_misaligned_expert_reject_count/percent` | ⬜ | 需细化 Expert 维度 |
| `ag_persona_count/usage_rate/coverage_rate` | ⬜ | 需 Persona 库统计 |
| `ag_richness_score_avg/variance/low_rate` | ⬜ | 需 Critic 模型打分 |
| `ag_platform_compliance_score` | ⬜ | 需 Critic 模型打分 |
| `ag_violation_type_distribution` | ⬜ | 需 Critic 模型打分 |

### 3.4 RLHF（待开发 4/10）

| 指标 | 状态 | 说明 |
|------|------|------|
| `brand_mismatch_rate` | ⬜ | 需模型自动评估 |
| `persona_consistency_score` | ⬜ | 需模型自动评估 |
| `batch_similarity_score` | ⬜ | 需批次内计算相似度矩阵 |
| `batch_valid_output_rate` | ⬜ | 需定义"有效"标准 |

---

## 五、近期完成任务

| 日期 | 任务 | 说明 |
|------|------|------|
| 2026-01-09 | Ban V2 幻觉问题分析 | 数据分析 + 解决方案设计（详见下方） |
| 2026-01-08 | 插件策略映射功能 | 变量映射 + 快捷跳转按钮 |
| 2026-01-08 | 内容策略缓存优化 | Redis 缓存 4 个核心 API |
| 2026-01-08 | Bug 知识库建立 | BUG-001/002/003 |
| 2025-12-23 | 系统信息监控页面 | K8s/DB/Redis 健康检查 |
| 2025-12-23 | Adminer 集成 | 数据库管理工具（免密登录） |
| 2025-12-17 | AG 追踪 SDK 接入 | raap-service-ag 全链路追踪 |
| 2025-12-17 | 核心指标定义 | 30 个业务指标 Constants |
| 2025-12-16 | 内容池 API | Match/Acquire/Ack |
| 2025-12-15 | RLHF 数据回流修复 | 锁定交互优化 |

---

## 六、阻塞问题

当前无阻塞问题。

---

## 七、相关文档索引

| 类型 | 文档 | 说明 |
|------|------|------|
| **系统设计** | [docs/plan.md](./docs/plan.md) | 架构、数据库、API 设计 |
| **Bug 知识库** | [bugs/README.md](./bugs/README.md) | 常见错误及解决方案 |
| **开发规范** | [../AGENTS.md](../AGENTS.md) | 代码规范、工作流 |
| **核心概念** | [docs/BASE.md](./docs/BASE.md) | Tenant/Activity/Agent/Expert/Job |

---

---

## 八、待开发任务详情

### 8.1 Ban V2 防幻觉审核

> **问题背景**：LLM 审核（CriticIllegal）存在幻觉问题，声称检测到违禁词但实际不存在于原文中。

#### 📊 数据分析（2026-01-09）

| 审核类型 | 拒绝次数 | 有证据记录 | 幻觉风险 |
|----------|----------|-----------|----------|
| **CriticIllegal** (LLM审核) | 709 | ❌ 0 条 (0%) | ⚠️ **无法验证** |
| CriticKeywordFilter (精确匹配) | 94 | ✅ 33 条 | 低 |
| CriticCounterproductive | 107 | ❌ 0 条 | ⚠️ 无法验证 |
| CriticUnreasonable | 73 | ❌ 0 条 | ⚠️ 无法验证 |

**核心问题**：
- LLM 审核的 709 次拒绝，**无一条记录具体违禁词**
- `reason` 字段仅存模糊描述：`"功效宣称类违禁"`、`"负面诋毁类违禁"`、`"其他违禁内容"`
- **无法追溯验证**这些拒绝是否为幻觉（误判）

#### ✅ 解决方案：Ban V2 (CriticBanV2)

| 机制 | 作用 |
|------|------|
| **证据驱动 Prompt** | 要求 LLM 返回 `exact_text`（精确原文）、`position`（位置）、`context`（上下文） |
| **后验证机制** | 自动检查 LLM 声称的违禁词是否真的出现在原文中 |
| **自动纠错** | 若所有报告的违规词都是幻觉，自动改判为 `passed` |
| **结构化记录** | 保存验证结果到 `post_validation` 字段，支持事后分析 |

#### 📁 相关文件

| 文件 | 说明 |
|------|------|
| `raap-service-ag/docs/ENHANCED_BAN_GUIDE.md` | 详细设计文档 |
| `raap-service-ag/app/agents/ban/base_ban_enhanced.py` | 基类实现（证据驱动 + 后验证） |
| `raap-service-ag/app/agents/ban/ban_v2.py` | Ban V2 Expert 类 |
| `raap-service-ag/app/services/ban_v2_service.py` | HTTP 服务函数 |
| `raap-service-ag/app/api/v1/endpoints/dapr_http_invoke.py` | `/critic.CriticService/CriticBanV2` 端点 |
| `raap-service-ag/scripts/add_ban_v2_expert.sql` | 数据库配置 SQL |

#### 🎯 待完成事项

- [ ] 执行 SQL 添加 `CriticBanV2` Expert 配置
- [ ] 测试 Ban V2 端点功能
- [ ] 在 Expert 调试器中验证防幻觉效果
- [ ] 替换现有 CriticIllegal 或作为可选升级

---

> **更新说明**：本文档应随开发进度实时更新。设计变更请同步修改 `docs/` 下对应的设计文档。

---

## 九、历史 Codex Session 整理（2026-06-01）

> 扫描范围：`/Users/luxifa/.codex/sessions` 中 `cwd=/Users/luxifa/maga`、近 90 天的本地 session，共 42 条。  
> 整理原则：不删除本地 session；仅判断哪些可以归档、哪些作为参考、哪些应转成后续任务。旧小红书抓取线程 `019e7dd5...`、`019e7e9d...` 的原始 JSONL 未在本地路径找到，其关键上下文已转移到 `019e8104...` / `019e810b...`。  
> 归档执行记录：2026-06-01 已在 Codex App 中归档 `019e810f...`、`019e8104...`、`019e63d6...`、`019e4ebe...`；更早的本地 JSONL session 未进入 App 可管理线程索引，仅保留“可归档”标记。

### 9.1 可归档 Session（24 条）

这些 session 已完成、结果已落到代码/文档/配置中，或属于环境排查、周报、桥接、一次性问答。保留本地日志即可，不建议继续从这些线程恢复。

| Session | 主题 | 归档原因 |
|---------|------|----------|
| `019df1e4-40e7-7871-8658-604f7fdf6bcb` | 周报整理 | 文案产物已完成，无项目待办 |
| `019dfc5d-5b29-78f1-8258-eb637302eb0e` | 霓虹闲聊 | 无项目上下文 |
| `019dfc59-dc17-7882-af4d-54570fa861ee` | 提示词优化输出转义 | 修复已落到 `scripts/optimize_prompt_from_txts.py` |
| `019dfcaf-2934-7b82-9562-a049be0d17a5` | `gpt-5.5` token 参数修复 | 脚本兼容已完成 |
| `019e0188-bb49-71f1-9424-c3f171513728` | 人工反馈优化脚本空输出 | 修复已完成 |
| `019e0071-b060-74a1-b193-5f4a827b64f2` | 统一启动脚本 | `start_dev.sh` 已完成 |
| `019e057e-f6b0-70b2-bfcb-915c0e4c9d61` | Docker 空间回收 | 一次性环境清理 |
| `019e068e-9c9c-7e31-bfc2-cd7095dd3685` | Docker 启动方式排查 | 环境状态型问题，后续用当前启动文档 |
| `019e0c54-7f4d-7a13-bab3-1060370cb6fc` | 减少提示词冗余规则 | 脚本策略已更新 |
| `019e1523-8fc5-78d0-bf88-e8f93c50b1be` | `problem-file` 可选 | 脚本行为已更新 |
| `019e1a06-34c2-70e3-84ad-2a0f26e4cce7` | debug 文件读取排查 | 已定位为输入文件问题 |
| `019e1fe5-4090-7fd1-b52a-545fb5ba3962` | 源悦候选语料写入 | 已通过 MAGA API 写入 candidate 资产 |
| `019e23ee-bf8a-7591-be80-7df94c663116` | 本地目录说明 | 一次性解释 |
| `019e2adb-7b2d-7cc2-b2f2-c171811b4dba` | 前端端口调整 | `platform-console` 端口已改为 3102 |
| `019e390c-221c-7f52-9004-3acdb3d461f6` | 审核规则措辞优化 | 规则建议型对话，无独立待办 |
| `019e431f-cd32-76b1-b2c0-e6defa1772d5` | `.env` / commit | 代码已提交 |
| `019e4ebe-efd0-7770-aeb1-6e2dcc27153a` | 审核提示词优化脚本 | 错误审核/漏审拆分已完成 |
| `019e63d6-fb36-7720-a958-2f312e2825e1` | 产品使用体验素材清理 | CSV 已清理 |
| `019e6779-1b87-7aa3-bff9-ddea8b8d0580` | 评论训练模型 final 清理 | final CSV 已收敛成 3 列 |
| `019e6850-2d5e-7142-8bcc-ef697e8d772e` | 推送代码 | `origin/main` 已同步 |
| `019e717a-b652-7522-b066-d0d42256f9be` | `maga-worker` 模型配置 | 本地 Hermes profile 已改 |
| `019e7214-7557-7212-80a1-bd7763bf6096` | 评论切角局部更新 | CSV 已更新 |
| `019e8104-b5f8-70d0-9650-4d2f3d234a0f` | 旧小红书会话桥接 | 已把上下文转移到新线程 |
| `019e810f-6272-7790-ab23-8b5bed1b4693` | 自动化说明 | 无后续项目任务 |

### 9.2 保留参考 Session（10 条）

这些 session 不一定要继续打开执行，但里面有可复用的架构判断、业务边界或历史决策。后续做相关功能时应先查这些 session 或已落地文档。

| Session | 可参考内容 | 对应资产/建议 |
|---------|------------|---------------|
| `019d8c17-7af1-7dc3-bb12-2e70974eb8b2` | 关键词语料管理、规则优先级、后置检查、审核误判分类 | 作为“规则治理不是无限加 prompt”的方法论参考 |
| `019e206e-fa98-7183-821e-d2b259963720` | `diversity_slot` 与 `diversity_json` 区别 | 继续做多样性治理时参考 |
| `019e20c2-750e-75e1-9e35-cc4f9c1c8896` | Hermes profile 提示词归入 MAGA 管理 | 已影响 `generation_snapshot.prompt_bundle_snapshot` 读取逻辑 |
| `019e1106-812b-75f1-9726-cd0a4cda8677` | MAGA 生文流程、启动、文档沉淀 | 主要参考 [MAGA_XHS_WRITER_LOCAL_INTEGRATION.md](/Users/luxifa/maga/docs/MAGA_XHS_WRITER_LOCAL_INTEGRATION.md) |
| `019e2aea-0c32-7ce3-a334-0277f244c0e4` | 新 MAGA 与旧 RAAP `content` 表兼容 | 主要参考 [MAGA_COMPAT_OLD_RAAP_CONTENT_MATCH.md](/Users/luxifa/maga/docs/MAGA_COMPAT_OLD_RAAP_CONTENT_MATCH.md) |
| `019e39bd-21e4-7442-9975-16e0df31e7a9` | Hermes 融入 RAAP 的定位 | 结论：先做 RAAP Copilot / 调试器，不急着改主执行链路 |
| `019e5e92-a183-71d3-ab9b-0248ceadebd6` | 产品使用体验语料整体更新经验 | 参考“语料清洗要避免规则话术进入素材” |
| `019e6211-ea38-7903-ad85-a312ca56219f` | 评论切角从示例中抽象规则 | 参考评论规则拆解方法，但同质化问题需继续治理 |
| `019e6e14-44b3-7fa0-af2d-4e9d823f7e37` | 少堆提示词、多用案例仿写；飞书 CLI 权限拆分 | 后续接飞书表格时参考最小权限方案 |
| `019e3540-0b57-7e11-939d-7f5588ca0bb3` | `runtime_brief` 编译与复用 | 继续改生文链路时参考该运行时边界 |

### 9.3 需要继续推进 Session（8 条）

| 优先级 | Session | 继续方向 | 下一步产物 |
|--------|---------|----------|------------|
| P0 | `019e6c66-ef0a-77b0-963d-d6a9592a3ec4` | 运营反馈回流自动化，做成半自动 Prompt PR：提取问题、定位规则、生成修改建议、人工确认 | `反馈回流工作台` 方案与最小可用接口 |
| P0 | `019e731a-558f-7531-9c36-04d8dd36dff6` | 批次级“反馈优化建议单”已实现，需要验证接口、前端展示和测试覆盖 | `GET /api/v1/content-agent/batches/{batch_id}/feedback-insights` 验证报告 |
| P1 | `019e4317-2501-76a1-879d-8c93a32d6d09` | 小红书关键词搜索爆款文章与本地例文库能力 | 把现有小红书全量帖子/评论数据接入素材池或关键词语料入口 |
| P1 | `019e6d46-4a78-71d2-878c-59725f5faa4c` | 内容结构同质化治理 | 从“开头不重复”升级到“正文逻辑、证据类型、表达路径”多样性评估 |
| P1 | `019e636d-f1ee-7e03-926f-22408b5b57f4` | 生长发育评论切角过窄 | 更新切角规则并用生成样本回测重复表达 |
| P1 | `019e67c5-7377-7883-b98b-c0e2ceb482ee` | 小红书文章痛点识别 prompt | 固化为结构化 JSON 标签器，先限制在 6 个核心痛点 |
| P2 | `019e72a7-1c7c-7051-b11f-80b1c3922953` | 提示词优化脚本产品化 | 对齐现有 `/api/v1/prompt-optimizer`，补人工审阅、版本 diff、应用记录 |
| P2 | `019e810b-ee1d-74d3-ab43-ae93ffc3fce3` | 小红书帖子/评论全量数据整理与 session skill 创建 | 保持为当前工作线程，完成后再归档 |

### 9.4 建议转成近期 Backlog

| 优先级 | 任务 | 来源 Session | 说明 |
|--------|------|--------------|------|
| P0 | 反馈回流工作台 MVP | `019e6c66...`, `019e731a...` | 先做半自动，不自动写回 asset；核心是从批次反馈生成可审阅建议单 |
| P1 | 小红书全量帖子/评论数据资产化 | `019e4317...`, `019e810b...` | 把 2026-06-01 整理出的全量帖子、评论、正文/tag、情感与词云报告变成可复用素材入口 |
| P1 | 同质化治理评估器 | `019e6d46...`, `019e636d...`, `019e6211...` | 用生成样本检测固定句式、固定证据链、固定切角，并反推规则调整 |
| P1 | 小红书痛点识别标签器 | `019e67c5...` | 做成稳定 JSON 输出，供帖子分析、素材归类、评论切角推荐复用 |
| P2 | Prompt Optimizer 产品化 | `019e72a7...`, `019d8c17...` | 把脚本能力沉淀成工作台：Run、Patch、Review、Apply、Version |
| P2 | Hermes Copilot / 调试器 | `019e39bd...`, `019e20c2...` | 先服务排查、预览、解释和局部调用，不改主执行链路 |

### 9.5 使用建议

- 新开需求前，优先从 `9.3` 的 continue session 取上下文，而不是从全部 42 条里翻。
- 做代码实现时，优先打开对应已落地文档和文件，再回看 session 原文；session 只作为决策依据，不作为唯一事实来源。
- 可归档 session 暂不删除。若后续要在 Codex 侧真正 archive 线程，应先确认待归档列表，再批量操作。
- 当前工作区有未跟踪的小红书爬取/分析文件，session 整理不应误删这些数据产物。
