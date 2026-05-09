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
