# 旺玥 Focused Review Pipeline 切流验证

## 状态

2026-07-16 使用组合 Shadow API 对 6 个真实旺玥批次做镜像双跑。新链路只写入 `wangyue_focused_pipeline_shadow_review`，不修改正文、`hard_pass`、导出或入池。

本轮覆盖：

- 精力不足 / 复购长期使用
- 容易中招 / 使用反馈
- 成长发育需求 / 使用反馈
- 成长发育需求 / 家庭清单
- 注意力不集中 / 轻测评
- 营养不足 / 问题解决

## 整体结果

| 指标 | 结果 |
|---|---:|
| 文章数 | 50 |
| Focused pass | 35 |
| Focused watch | 5 |
| Focused block | 10 |
| Judge 调用失败 | 0 |
| 旧 reviewer 可比较 | 38 |
| 新旧 rewrite 决策一致 | 34 |
| 新旧 rewrite 决策不一致 | 4 |
| 旧 reviewer 不可用 | 12 |
| Focused 总 tokens | 178857 |

旧 reviewer 可用时，新旧 rewrite 决策一致率为 `34/38 = 89.5%`。这个指标只表示行为差异，不代表旧 reviewer 是真值。

## 已确认的新链路增益

### 1. 旧 reviewer 不可用时仍能给出可观测结果

batch 498 的 10 篇旧 reviewer 全部没有可用结果，Focused Pipeline 全部完成。其中两篇原本已被代码硬审拦住，聚合器保持 block，不额外发起 LLM 改写。

### 2. 抓住真实改写病句

batch 497 item 5：

> 回想之前时候交替总要请几天假。

新链路判为 `fluency / unnatural_collocation / block`，路由到 `fluency_humanize`。

### 3. 家庭清单历史判断已被后续人工口径修正

本轮曾将“家庭清单只写旺玥、没有其它家庭物件或清单项”判为 `post_type_mismatch / block`。2026-07-16 后续人工确认：这类内容单篇可以使用，家庭清单展开程度只属于生成多样化和批量分布优化，应改为 pass/watch，不应自动改写。本节历史 block 结论不再作为切流增益。

## 切流前的疑似误杀

下面 3 篇不应直接根据本轮结果改 Prompt，需要先人工确认，再进金标。

### batch 498 item 7

Focused Fluency 判 `semantic_discontinuity`，理由是没有交代以前状态。但正文已经写了：

> 以前总要我托一把的。

从中文连续性看，大概率是 Fluency Judge 漏读上下文。

### batch 514 item 5

Focused Fluency 认为“晚饭没吃好 -> 旺玥做日常营养补充 -> 不用太慌”没有逻辑承接。但这个链路本身是完整的问题解决型表达，更像过度审核。

### batch 514 item 6

Focused Temporal 将“一顿饭没吃好，后来泡杯旺玥补日常营养”判为 `immediate_rescue_causality`。当前 temporal 金标的立即补救主要针对打喷嚏、不舒服和疾病症状，是否应扩到单顿饭营养补充需要人工定边界。

## 改写验收

现有 product-experience LLM 改写已改为：

```text
before
  -> content.rewrite candidate
  -> RewriteQualityValidator
     accept: 才写回
     retry: 带验收证据再试 1 次
     reject: 不写回，hard_pass=false，转人工
     unavailable: 不写回，不自动放行
```

这个验收层同时保护当前旧 reviewer 改写和后续 Focused Pipeline 改写。

### Cutover rehearsal

组合 Shadow API 现支持可选的改写演练：

```json
{
  "force": true,
  "limit": 5,
  "concurrency": 5,
  "rehearse_rewrites": true
}
```

演练只把候选和验收结果写入：

```text
wangyue_focused_pipeline_cutover_rehearsal
```

不修改正文、`hard_pass`、导出或入池。候选必须依次通过：

1. 代码硬审复跑：硬违禁词、产品事实、产品动作和时间环境等确定性边界；
2. before/after Rewrite Quality Validator；
3. 原 block 对应的 Focused Judge 复审，确认目标问题不再是 block。

任一环节失败都保留原文并标记 `manual_review`。

### 真实改写演练

对 batch 497 前 5 篇做真实演练。首次演练中 item 5 的候选把病句：

> 回想之前时候交替总要请几天假

改成：

> 回想之前换季总要请几天假

Rewrite Quality Validator 和 Fluency Judge 都判通过，但候选重新命中硬违禁词 `换季`。补上代码硬审复跑后，再次演练得到：

| 指标 | 结果 |
|---|---:|
| Focused pass | 3 |
| Focused watch | 1 |
| Focused block | 1 |
| 不需要改写 | 4 |
| 自动接受候选 | 0 |
| 转人工 | 1 |
| Judge 调用失败 | 0 |

item 5 原文和 `hard_pass` 保持不变，候选因命中 `季节` 时间环境 guard 被拒绝。这证明改写后不能只做 LLM 验收，必须重新跑确定性硬审。

同一轮还发现 batch 497 item 4 的 Content Fit 判断在两次相同输入中从 `post_type_mismatch/block` 漂移为 `pass`。争议是“只喝两周、没有复购或补货关系”是否满足目标帖子类型“复购/长期使用”。在人工定标前不调整 Prompt，也不允许据此切生产。

## 切流建议

当前结论：

- 可开启自动镜像流量。
- 不建议让 Focused Pipeline 立即接管改写和入池。
- 先确认上述 3 条疑似误杀，以及 batch 497 item 4 的帖子类型边界，加入 holdout 金标后再重跑。

## 人工定标后的第二轮验证

人工确认：

- batch 498 item 7：`pass`，真实 UGC 不要求完整旧状态参照；
- batch 514 item 5：`pass`，日常营养补充不需要解释如何改善食欲；
- batch 514 item 6：`pass`，一顿饭没吃好后冲泡旺玥不属于立即补救；
- batch 497 item 4：`pass`，两周是复购/长期使用的最低成立线，不要求必须补货。

上述口径已进入 approved gold：

- Fluency：17 条；
- Temporal：16 条；
- Content Fit：16 条。

三个 Focused Judge 的完整金标回归为 `49/49`。Fluency 另做 3 轮稳定性测试，共 `51/51`，原有 8 条病句 block 全部保持召回。

### 50 篇真实重跑

对原 6 个批次、50 篇文章重新执行组合 Shadow：

| 指标 | 校准前 | 校准后 |
|---|---:|---:|
| Focused pass | 35 | 35 |
| Focused watch | 5 | 7 |
| Focused block | 10 | 8 |
| Judge 调用失败 | 0 | 0 |
| Focused 总 tokens | 178857 | 237385 |

校准后的 8 个 block 组成：

- 1 篇真实病句：batch 497 item 5，“之前时候交替”；
- 2 篇代码硬审失败：batch 498 item 2、item 9；
- 5 篇当时被判为家庭清单类型不成立：batch 498 item 4、item 10，batch 507 item 2、item 5、item 6；该边界已被后续人工改为 pass/watch，当前统计需重跑。

不再包含人工确认的 4 条误杀。

### 动作级新旧比较

旧指标只比较“是否改写”，会把 `Focused manual_review` 与 `legacy pool` 错记为 match。聚合器现新增：

```text
legacy_action / focused_action / action_match
```

旧 reviewer 可用的 38 篇中：

- action match：35；
- action mismatch：3；
- mismatch 全部来自 batch 507 的家庭清单类型判断；该边界已被后续人工改为 pass/watch，因此这些 mismatch 不再算有效拦截；
- 旧 reviewer 不可用：12。

这 3 条按最新人工口径属于过度审核。原动作比较结论已失效，需要使用更新后的 Content Fit Judge 重跑 50 篇。

### 改写演练复验

batch 497 item 5 是本轮唯一需要自动局部改写的文章。改写候选再次把“时候交替”改成“换季”，确定性硬审命中 `换季`，结果为：

```text
manual_review
原文未修改
hard_pass 未修改
候选未写回
```

说明切流后的改写验收能够阻止 LLM 用硬违禁词修复病句。

## 当前结论

- Focused Judge 的已知误杀已按人工口径消除；
- 聚合、动作比较和 Shadow 改写验收已具备；
- 本节记录的是切流前结论，已由下方正式切流结果替代。

## 正式切流结果

2026-07-16 已完成旺玥 V3 production takeover：

- 自动后处理和手动业务复审均不再调用旧 `ProductExperienceLLMReviewService` 超级审核 Prompt；
- `watch` 原文保留并允许入池；
- `block` 只有通过局部改写、代码硬审、Rewrite Quality Validator 和四个 Focused Judge 完整复审后才写回；
- 任一 Judge 不可用时进入 hold，不静默回退；
- 非旺玥业务继续使用原审核链路；
- 自动 shadow 开关已删除，手动 shadow API 仅用于排查。

真实验证 batch `550`：

| 指标 | 结果 |
|---|---|
| 生成 | 1/1 |
| Focused status / decision | pass / pass |
| 可自动入池 | true |
| 旧超级审核字段 | 不存在 |
| Temporal / Claim / Content Fit | deepseek-v4-flash |
| Fluency | qwen-plus |

完整后端回归：`1344 passed`。

## 运行时契约与 unavailable 修复

真实重跑发现 DeepSeek 在 `pass` 时经常省略 `evidence` 或 `issue_code`。解析器本来会把 pass 安全归一为 `issue_code=none`，旧运行时却先重复调用模型，造成不必要 token。

当前契约调整为：

- `pass`：允许省略 `evidence` 和 `issue_code`；
- `watch/block`：必须返回合法 issue code 和非空 evidence；
- 第二次仍不满足契约：明确抛出 unavailable，不伪装成空 evidence 的 watch。

batch 509 的 10 篇成本复验中，总 token 从一次高重试运行的 `55310` 降到 `43641`，约下降 `21.1%`。模型输出存在波动，因此该数字只用于确认重试浪费有所下降，不作为固定成本承诺。

同时修复了强制 Shadow 重跑失败后的旧状态污染：

```text
旧行为：本轮 Judge 失败 -> 聚合仍读取上一次成功结果 -> 可能继续显示 pass
新行为：本轮 Judge 失败 -> 对应维度写 unavailable -> decision=watch -> focused_action=hold -> can_auto_pool=false
```

动作比较也会把 unavailable 与旧 reviewer 的 pool 判为 mismatch，不再显示成 action match。

完整后端回归：`1338 passed`。

历史自动镜像开关已在正式切流时删除。需要排查时使用手动 Shadow API，不再保留自动双跑配置。
