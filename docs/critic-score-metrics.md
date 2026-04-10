# Critic 评分指标体系设计

> 版本: v1.0  
> 更新日期: 2025-12-12  
> 作者: RAAP Team

## 一、概述

本文档定义了基于 RAAP 内容生成系统的 9 个打分模型的业务指标体系，用于监控内容生产质量、识别问题、优化决策。

### 1.1 打分模型清单

| 模型编码 | 模型名称 | 业务层级 | 分值范围 | 说明 |
|----------|----------|----------|----------|------|
| `CriticIllegal` | 不合法检测 | 红线层 | **0/1** | 违规内容检测，涉政/涉黄/敏感词等 |
| `CriticUnreasonable` | 不合理检测 | 红线层 | **0/1** | 逻辑错误、事实性错误检测 |
| `CriticCounterproductive` | 不合目的检测 | 红线层 | **0/1** | 是否偏离营销目标 |
| `CriticGrace` | 文章优雅性 | 质量层 | 0-100 | 文字流畅度、可读性、表达美感 |
| `CriticQuality` | 内容质量 | 质量层 | 0-100 | 内容整体水平综合评估 |
| `CriticCreativity` | 创造力 | 质量层 | 0-100 | 内容创新性、吸引力 |
| `CriticBrandMatch` | 品牌匹配 | 业务层 | 0-100 | 与品牌调性的契合程度 |
| `CriticPersona` | 人设真实感 | 业务层 | 0-100 | 虚拟人设的一致性和真实感 |
| `CriticMarketing` | 营销效果 | 业务层 | 0-100 | 商业转化潜力评估 |

> **注意**：红线层采用二值判断（0=不通过，1=通过），质量层和业务层采用百分制评分。

### 1.2 业务层级说明

```
┌─────────────────────────────────────────────────────────────┐
│                      业务层（能不能用）                       │
│         品牌匹配 / 人设真实感 / 营销效果                       │
│                  → 决定内容是否可发布                         │
├─────────────────────────────────────────────────────────────┤
│                      质量层（内容好不好）                      │
│           文章优雅性 / 内容质量 / 创造力                       │
│                  → 决定内容的水平高低                         │
├─────────────────────────────────────────────────────────────┤
│                      红线层（必须通过）                        │
│          不合法 / 不合理 / 不合目的                           │
│              → 不通过即废弃，无条件拦截                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、核心指标定义

### 2.1 红线指标（安全仪表盘）

用于监控内容安全底线，任何异常都需要立即关注。

> **红线层评分规则**：0=不通过，1=通过

| 指标名称 | 指标编码 | 计算公式 | 单位 | 业务含义 |
|----------|----------|----------|------|----------|
| **违规率** | `illegal_rate` | 不合法评分=0 的内容数 / 总内容数 × 100 | % | 内容合规风险，必须趋近于0 |
| **逻辑错误率** | `unreasonable_rate` | 不合理评分=0 的内容数 / 总内容数 × 100 | % | 事实/逻辑错误比例 |
| **目标偏离率** | `counterproductive_rate` | 不合目的评分=0 的内容数 / 总内容数 × 100 | % | 偏离营销目标的比例 |
| **红线通过率** | `redline_pass_rate` | 三项红线均=1 的内容数 / 总内容数 × 100 | % | 内容安全基础通过率 |
| **品牌安全指数** | `brand_safety_index` | 100 - 违规率 | 分 | 品牌风控总体水平 |

**告警阈值建议：**

| 指标 | 正常 | 警告 | 严重 |
|------|------|------|------|
| 违规率 | < 0.1% | 0.1% - 1% | > 1% |
| 逻辑错误率 | < 5% | 5% - 15% | > 15% |
| 目标偏离率 | < 10% | 10% - 25% | > 25% |
| 品牌安全指数 | > 99.9 | 99 - 99.9 | < 99 |

---

### 2.2 内容质量指标（生产力仪表盘）

用于评估内容生产的效率和质量水平。

| 指标名称 | 指标编码 | 计算公式 | 单位 | 业务含义 |
|----------|----------|----------|------|----------|
| **一次通过率** | `first_pass_rate` | 红线层均=1 且 质量层/业务层均>=60 的内容数 / 总生成数 × 100 | % | 衡量 Prompt/模型的有效性 |
| **优质内容占比** | `high_quality_rate` | 红线层均=1 且 质量层/业务层均>=80 的内容数 / 总生成数 × 100 | % | 真正优秀的内容比例 |
| **平均迭代次数** | `avg_iteration_count` | 总评分次数 / 去重内容数 | 次 | 内容达标平均需要几轮 |
| **综合质量得分 (CQI)** | `cqi` | 文章优雅性×0.3 + 内容质量×0.4 + 创造力×0.3 | 分 | 内容质量的单一综合指标（仅质量层） |

**一次通过率计算逻辑：**

```python
first_pass = (
    # 红线层：必须全部通过（=1）
    illegal_score == 1 
    and unreasonable_score == 1 
    and counterproductive_score == 1
    # 质量层 + 业务层：必须全部 >= 60
    and grace_score >= 60
    and quality_score >= 60
    and creativity_score >= 60
    and brand_match_score >= 60
    and persona_score >= 60
    and marketing_score >= 60
)
```

**CQI 计算公式：**

```
CQI = grace_score × 0.3 + quality_score × 0.4 + creativity_score × 0.3
```

**业务决策参考：**

| 现象 | 可能原因 | 优化方向 |
|------|----------|----------|
| 一次通过率 < 70% | Prompt 不够清晰 / 模型能力不足 | 优化 Prompt、换模型 |
| 平均迭代次数 > 2 | 生产成本过高 | 分析失败原因、针对性优化 |
| CQI < 70 | 内容整体水平偏低 | 加强质量类 Prompt 引导 |

---

### 2.3 业务效果指标（营销仪表盘）

用于评估内容能否达成业务目标。

| 指标名称 | 指标编码 | 计算公式 | 单位 | 业务含义 |
|----------|----------|----------|------|----------|
| **品牌契合度** | `brand_alignment` | 品牌匹配评分平均值 | 分 | 内容是否"像这个品牌说的话" |
| **人设稳定性** | `persona_consistency` | 人设真实感评分平均值 | 分 | 虚拟人设是否一致、真实 |
| **营销潜力指数 (MPI)** | `mpi` | 营销效果评分平均值 | 分 | 内容的商业转化潜力 |
| **业务可用率** | `business_usable_rate` | 品牌匹配、人设、营销三项均>=70 的内容比例 × 100 | % | 真正能发布的内容 |

**业务可用率计算逻辑：**

```python
business_usable = (
    # 红线层必须全部通过
    illegal_score == 1
    and unreasonable_score == 1
    and counterproductive_score == 1
    # 业务层必须全部 >= 70
    and brand_match_score >= 70 
    and persona_score >= 70 
    and marketing_score >= 70
)
business_usable_rate = count(business_usable) / total_count × 100
```

**业务决策参考：**

| 指标 | 低于阈值时的影响 | 优化方向 |
|------|------------------|----------|
| 品牌契合度 < 70 | 内容"不像这个品牌"，用户感知不一致 | 强化品牌调性描述 |
| 人设稳定性 < 70 | 人设表达不稳定，用户难以建立信任 | 细化人设画像 |
| 营销潜力 < 70 | 内容"不带货"，难以达成转化目标 | 优化 CTA 和卖点表达 |

---

### 2.4 效率与成本指标（ROI 仪表盘）

用于优化模型选择和成本控制。

| 指标名称 | 指标编码 | 计算公式 | 单位 | 业务含义 |
|----------|----------|----------|------|----------|
| **模型平均分** | `model_avg_score` | 按模型分组的各维度平均分 | 分 | 不同模型的质量表现 |
| **模型通过率** | `model_pass_rate` | 按模型分组的一次通过率 | % | 不同模型的成功率 |
| **模型平均耗时** | `model_avg_duration` | 按模型分组的平均响应时间 | ms | 不同模型的速度 |
| **成本效率比** | `cost_efficiency` | CQI / 平均 Token 消耗 | 分/千Token | 哪个模型性价比高 |

**模型对比示例：**

| 模型 | 平均分 | 通过率 | 平均耗时 | 成本效率比 | 推荐场景 |
|------|--------|--------|----------|------------|----------|
| GPT-4o | 82 | 85% | 3200ms | 0.82 | 高质量要求 |
| DeepSeek R1 | 76 | 78% | 1800ms | 1.52 | 日常批量生产 |
| Qwen Max | 74 | 75% | 2100ms | 1.23 | 中等质量要求 |

---

### 2.5 问题诊断指标（优化仪表盘）

用于识别系统性问题，指导优化方向。

| 指标名称 | 指标编码 | 计算方式 | 业务含义 |
|----------|----------|----------|----------|
| **短板维度** | `weakness_dimension` | 9个维度中平均分最低的维度 | 明确当前最需要改进的方向 |
| **问题热词 Top10** | `problem_hotwords` | problem_context_list 词频统计 Top10 | 识别系统性问题 |
| **失败原因分布** | `failure_distribution` | 按导致不通过的维度统计占比 | 哪个环节最常失败 |
| **质量波动系数** | `quality_volatility` | 各维度分数的标准差 | 内容质量是否稳定 |

**失败原因分布示例：**

```
不合法:        ████ 8%
不合理:        ██████████ 20%
不合目的:      ████████████ 24%
文章优雅性:    ██ 4%
内容质量:      ████ 8%
创造力:        ██████ 12%
品牌匹配:      ██████ 12%
人设真实感:    ██ 4%
营销效果:      ████ 8%
```

---

### 2.6 场景对比指标（运营仪表盘）

用于跨场景分析，发现最佳实践。

| 指标名称 | 指标编码 | 分组维度 | 业务含义 |
|----------|----------|----------|----------|
| **活动效果对比** | `job_comparison` | job_id | 不同活动/任务的内容质量对比 |
| **配置效果对比** | `config_comparison` | expert_config_code | 不同 Prompt 配置的效果对比 |
| **时段效率分析** | `time_efficiency` | 小时/日期 | 识别高效生产时段 |
| **品牌/租户对比** | `tenant_comparison` | tenant_id | 不同品牌的内容质量差异 |

---

## 三、顶层聚合指标

### 3.1 内容生产健康度 (CPH)

**Content Production Health** - 用于一眼判断内容生产系统的整体状态。

**计算公式：**

```
CPH = 红线通过率 × 0.2 
    + 一次通过率 × 0.3 
    + 业务可用率 × 0.3 
    + (CQI / 100) × 100 × 0.2
```

**说明：**
- 红线通过率：三项红线检测（0/1评分）均=1 的内容占比
- 一次通过率：红线层均=1 且 质量层/业务层均>=60 的内容占比
- 业务可用率：红线层均=1 且 业务层均>=70 的内容占比
- CQI：质量层三项（优雅性/质量/创造力）的加权平均分

**等级划分：**

| CPH 范围 | 状态 | 颜色 | 行动建议 |
|----------|------|------|----------|
| >= 85 | 健康 | 🟢 绿色 | 保持当前策略 |
| 70 - 84 | 需关注 | 🟡 黄色 | 分析短板维度，针对性优化 |
| < 70 | 需干预 | 🔴 红色 | 立即排查问题，调整策略 |

---

## 四、指标计算 SQL 参考

### 4.1 红线指标计算

> 红线层评分：0=不通过，1=通过

```sql
-- 违规率（不合法评分=0 的比例）
SELECT 
    COUNT(CASE WHEN score = 0 AND expert_func = 'CriticIllegal' THEN 1 END) * 100.0 
    / COUNT(DISTINCT content_id) AS illegal_rate
FROM critic_score_record
WHERE create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY);

-- 逻辑错误率
SELECT 
    COUNT(CASE WHEN score = 0 AND expert_func = 'CriticUnreasonable' THEN 1 END) * 100.0 
    / COUNT(DISTINCT content_id) AS unreasonable_rate
FROM critic_score_record
WHERE create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY);

-- 目标偏离率
SELECT 
    COUNT(CASE WHEN score = 0 AND expert_func = 'CriticCounterproductive' THEN 1 END) * 100.0 
    / COUNT(DISTINCT content_id) AS counterproductive_rate
FROM critic_score_record
WHERE create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY);

-- 红线通过率（三项红线均=1）
WITH content_redline AS (
    SELECT 
        content_id,
        MAX(CASE WHEN expert_func = 'CriticIllegal' THEN score END) AS illegal,
        MAX(CASE WHEN expert_func = 'CriticUnreasonable' THEN score END) AS unreasonable,
        MAX(CASE WHEN expert_func = 'CriticCounterproductive' THEN score END) AS counterproductive
    FROM critic_score_record
    WHERE create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    GROUP BY content_id
)
SELECT 
    COUNT(CASE WHEN illegal = 1 AND unreasonable = 1 AND counterproductive = 1 THEN 1 END) * 100.0 
    / COUNT(*) AS redline_pass_rate
FROM content_redline;

-- 品牌安全指数
SELECT 100 - (
    COUNT(CASE WHEN score = 0 AND expert_func = 'CriticIllegal' THEN 1 END) * 100.0 
    / COUNT(DISTINCT content_id)
) AS brand_safety_index
FROM critic_score_record
WHERE create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY);
```

### 4.2 CQI 计算

```sql
SELECT 
    content_id,
    SUM(CASE WHEN expert_func = 'CriticGrace' THEN score * 0.3 ELSE 0 END) +
    SUM(CASE WHEN expert_func = 'CriticQuality' THEN score * 0.4 ELSE 0 END) +
    SUM(CASE WHEN expert_func = 'CriticCreativity' THEN score * 0.3 ELSE 0 END) AS cqi
FROM critic_score_record
WHERE expert_func IN ('CriticGrace', 'CriticQuality', 'CriticCreativity')
GROUP BY content_id;
```

### 4.3 模型对比

```sql
SELECT 
    model_code,
    COUNT(*) AS total_count,
    AVG(score) AS avg_score,
    SUM(passed) * 100.0 / COUNT(*) AS pass_rate,
    AVG(duration_ms) AS avg_duration_ms
FROM critic_score_record
WHERE create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY model_code
ORDER BY avg_score DESC;
```

### 4.4 问题热词统计

```sql
SELECT 
    problem_context,
    COUNT(*) AS count
FROM critic_score_record,
    JSON_TABLE(problem_context_list, '$[*]' COLUMNS (problem_context VARCHAR(500) PATH '$')) AS jt
WHERE create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY problem_context
ORDER BY count DESC
LIMIT 10;
```

---

## 五、Dashboard 可视化设计

### 5.1 总览页布局

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CPH: 82% 🟡 需关注                          │
├──────────────────┬──────────────────┬──────────────────┬────────────┤
│  红线通过率       │   一次通过率      │   业务可用率      │    CQI     │
│    98.5%         │     78%          │     65%          │    73      │
│    🟢            │     🟡           │     🟡           │    🟡      │
├──────────────────┴──────────────────┴──────────────────┴────────────┤
│  红线明细: 违规率 0.2% 🟡 | 逻辑错误率 0.8% 🟢 | 目标偏离率 0.5% 🟢   │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 详情页组件

| 组件 | 内容 | 图表类型 |
|------|------|----------|
| 趋势折线图 | CPH / 各指标随时间变化 | Line Chart |
| 维度雷达图 | 9个打分维度的平均分 | Radar Chart |
| 模型对比柱状图 | 各模型的通过率/平均分 | Bar Chart |
| 分数分布直方图 | 0-100 分段分布 | Histogram |
| 失败原因饼图 | 各维度失败占比 | Pie Chart |
| 问题热词云 | problem_context 词频 | Word Cloud |

---

## 六、告警规则

| 指标 | 条件 | 告警级别 | 通知方式 |
|------|------|----------|----------|
| 违规率 | > 0.5% | P0 严重 | 电话 + 短信 + 邮件 |
| 违规率 | > 0.1% | P1 警告 | 短信 + 邮件 |
| 一次通过率 | < 50% | P1 警告 | 邮件 |
| CPH | < 70 | P1 警告 | 邮件 |
| 业务可用率 | < 50% | P2 提示 | 邮件 |

---

## 七、数据源

所有指标数据来源于 `critic_score_record` 表：

| 字段 | 用途 |
|------|------|
| `expert_func` | 区分打分维度 |
| `score` | 计算平均分/通过率（红线层为0/1，其他为0-100） |
| `passed` | 通过率统计 |
| `model_code` | 模型对比 |
| `problem_context_list` | 问题热词分析 |
| `duration_ms` | 效率分析 |
| `create_time` | 时间趋势分析 |
| `job_id` / `content_id` | 场景对比分析 |

**分值范围说明：**

| expert_func | 分值范围 | 通过判断 |
|-------------|----------|----------|
| CriticIllegal | 0/1 | =1 通过 |
| CriticUnreasonable | 0/1 | =1 通过 |
| CriticCounterproductive | 0/1 | =1 通过 |
| 其他（质量层/业务层） | 0-100 | >=60 通过，>=80 优质 |

---

## 附录：指标编码速查表

| 类别 | 指标编码 | 中文名称 | 备注 |
|------|----------|----------|------|
| 红线 | `illegal_rate` | 违规率 | 基于 0/1 评分 |
| 红线 | `unreasonable_rate` | 逻辑错误率 | 基于 0/1 评分 |
| 红线 | `counterproductive_rate` | 目标偏离率 | 基于 0/1 评分 |
| 红线 | `redline_pass_rate` | 红线通过率 | 三项红线均=1 |
| 红线 | `brand_safety_index` | 品牌安全指数 | 100-违规率 |
| 质量 | `first_pass_rate` | 一次通过率 |
| 质量 | `high_quality_rate` | 优质内容占比 |
| 质量 | `avg_iteration_count` | 平均迭代次数 |
| 质量 | `cqi` | 综合质量得分 |
| 业务 | `brand_alignment` | 品牌契合度 |
| 业务 | `persona_consistency` | 人设稳定性 |
| 业务 | `mpi` | 营销潜力指数 |
| 业务 | `business_usable_rate` | 业务可用率 |
| 效率 | `model_avg_score` | 模型平均分 |
| 效率 | `model_pass_rate` | 模型通过率 |
| 效率 | `cost_efficiency` | 成本效率比 |
| 诊断 | `weakness_dimension` | 短板维度 |
| 诊断 | `problem_hotwords` | 问题热词 |
| 聚合 | `cph` | 内容生产健康度 |
