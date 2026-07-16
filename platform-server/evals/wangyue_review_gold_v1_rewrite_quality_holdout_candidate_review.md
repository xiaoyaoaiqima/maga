# 旺玥 Rewrite Quality Holdout 候选 Review

## 审核职责

本切片只比较 before/after：

- 是否引入病句或难以理解的表达；
- 是否造成上下文、指代或时间关系断裂；
- 是否无故删除人物、产品、时间、数量、使用关系和关键反馈。

不审核：硬违禁词、产品动作、卖点合规、目标问题是否真正修掉。那些由代码硬审和对应 Focused Judge 在下一关复审。

## 候选分布

| 建议标签 | 数量 |
|---|---:|
| accept | 10 |
| retry | 1 |
| reject | 4 |

## 候选清单

| case | 来源 | 建议 | 核心判断 |
|---|---|---|---|
| WYR-001 | batch497 item5 | reject | `换季 -> 时候交替` 制造病句 |
| WYR-002 | approved fix | accept | 删除目标词且保留时间关系 |
| WYR-003 | batch521 item9 | reject | 无故删除每日冲泡和孩子接受事实 |
| WYR-004 | batch521 item5 | accept | 清理尾部符号，后续合规另审 |
| WYR-005 | batch510 item6 | accept | 局部降调，主线和反馈保留 |
| WYR-006 | batch506 item2 | accept | 目标风险降调，主要事实保留 |
| WYR-007 | batch504 item4 | reject | 删错使用事实，真正目标仍存在 |
| WYR-008 | batch519 item2 | accept | 中文与事实成立，目标收口另复审 |
| WYR-009 | batch518 item1 | accept | 生硬搭配改自然 |
| WYR-010 | batch517 item6 | accept | 只删除目标睡眠效果 |
| WYR-011 | batch514 item6 | accept | 改写质量成立，产品动作由代码复审 |
| WYR-012 | batch449 item4 | retry | 重复“朋友也跟着换了”，局部可修 |
| WYR-013 | batch437 item14 | reject | 过度删除多个独立正向反馈 |
| WYR-014 | batch436 item16 | accept | 只删孩子自行冲泡目标句 |
| WYR-015 | batch63 item198 | accept | `晚上完奶 -> 晚上喝完奶` |

## 重点边界

### 改写质量通过，不等于最终可写回

WYR-004、WYR-008、WYR-011 都故意保留这个区别：after 可以通顺、事实保留，因此 Rewrite Quality 为 accept；但目标合规问题是否清除，仍必须由代码硬审或对应 Focused Judge 决定。

### 删除目标问题不算事实损失

WYR-010、WYR-014 删除的正是目标违规句，应 accept。

### 过度删除仍要拒绝

WYR-003、WYR-007、WYR-013 删除了目标之外的独立使用事实或正向反馈，应 reject。

## 人工状态

当前为 `candidate`，未合并进 approved `rewrite_quality_v1`。人工确认标签后再运行 Validator 对比并决定是否调整验收 Prompt。

2026-07-16 补充：WYR-007、WYR-012、WYR-013 的原文均经人工确认无需进入改写。三条首先作为上游审核/路由回归处理，不用于直接扩写 Rewrite Quality rubric。它们的 after 仍可用于观察“错误改写造成事实损失或逻辑问题”，但不能反推原文需要修改。

## 多模型基线

同一批 15 条候选分别测试当前 DeepSeek 路径、Qwen 和经 AIHubMix 路由的 Doubao：

| 模型 | 命中 | 一致率 | unavailable |
|---|---:|---:|---:|
| deepseek-v4-flash | 7/15 | 46.7% | 6 |
| qwen-plus | 12/15 | 80.0% | 0 |
| qwen3-max | 12/15 | 80.0% | 0 |
| doubao-seed-1-8 | 11/15 | 73.3% | 2 |
| doubao-seed-2-0-pro | 12/15 | 80.0% | 0 |
| doubao-seed-2-1-pro | 9/15 | 60.0% | 4 |

结论：`qwen-plus`、`qwen3-max` 和 `doubao-seed-2-0-pro` 在候选标签上并列 12/15。豆包 2.0 Pro 没有 unavailable，但平均单条耗时约 88 秒，不适合作为当前在线 Rewrite Quality grader 的首选；Qwen 两个模型更稳定。

2026-07-16 人工确认选择 `qwen-plus` 作为 Rewrite Quality 专用 grader。运行时通过 `llm_model_route` 解析 `aliyun/qwen-plus`，不再继承原文章生成模型。Fluency Judge 同样使用 `qwen-plus`。该选择只影响审核与改写验收模型，不代表 Focused Pipeline 已切生产。

## Doubao 运行表现

| 模型 | 平均单条耗时 | 运行判断 |
|---|---:|---|
| doubao-seed-1-8 | 26.3 秒 | 较快，但 2 条网络失败，且漏掉 WYR-007、WYR-013 的事实损失 |
| doubao-seed-2-0-pro | 87.7 秒 | 标签准确率并列最高，但明显偏慢 |
| doubao-seed-2-1-pro | 226.7 秒 | 4 条超时，不适合当前链路 |

三款 Doubao 都把 WYR-007 判成 `accept`；三款有结果时也都没有稳定识别 WYR-013 的过度删除。说明这两个“关键使用事实/独立正向反馈不可无故删除”的边界，仍需由人工确认金标后再决定是否校准短 rubric，不能仅靠换模型解决。

## qwen-plus 分歧

| case | 人工候选 | qwen-plus | 分歧 |
|---|---|---|---|
| WYR-006 | accept | retry | 模型认为公共疾病细节被泛化后，原因果支撑变弱；候选口径认为目标风险被删除是正常改写，不由本 Validator 审核 |
| WYR-007 | reject | accept | 模型认为低龄事实仍保留即可；候选口径认为无故删除持续冲泡和孩子接受属于关键使用事实损失 |
| WYR-012 | retry | accept | 模型漏掉 after 连续两次出现“朋友也跟着换了”的重复事件 |

WYR-001 的 `reject` 已在 approved `rewrite_quality_v1` 中确认，不因本轮 qwen-plus 返回 `retry` 重新开放。

## qwen3-max 分歧

| case | 人工候选 | qwen3-max | 分歧 |
|---|---|---|---|
| WYR-007 | reject | accept | 漏掉持续冲泡和孩子接受事实被无故删除 |
| WYR-012 | retry | reject | 将可局部修正的重复事件升级为整篇拒绝 |
| WYR-013 | reject | accept | 漏掉多个独立正向反馈被过度删除 |

## doubao-seed-2-0-pro 分歧

| case | 人工候选 | Doubao | 分歧 |
|---|---|---|---|
| WYR-001 | reject | retry | 识别到病句，但认为局部修正即可；approved 金标仍保持 reject |
| WYR-007 | reject | accept | 漏掉关键使用事实损失 |
| WYR-013 | reject | accept | 将被删除的多个独立反馈视为目标问题内容 |
