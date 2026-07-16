# 旺玥流畅性审核评测 v1

## 状态

`fluency_v1` 已于 2026-07-16 完成人工确认，共 15 条，冻结为 `approved` 金标。当前尚未接入生产审核或改写。

- `pass`：6 条
- `watch`：1 条
- `block`：8 条

## 本批只判断

- 病句和不自然搭配
- 模型压缩造成的残句、词语碰撞和语义断裂
- 标题与正文方向冲突
- 生成指令或提示词泄露
- 口语毛边究竟是自然 UGC，还是确实无法理解

不判断产品事实、疾病宣称、时间逻辑、内容方向或种草强弱。

## 建议重点 review

### WYL-001 / WYL-002｜饭菜与饭量最小对照

- `饭菜经常不稳定`：block
- `饭量却不太稳定。有时候吃得香，有时候随便对付`：pass

问题不是“不稳定”三个字，而是主语和后续表达是否成立。

### WYL-003｜建议 block

> 放学回来照样能吃饭、玩会儿乐高。

`照样`缺少清楚参照，两个动作也像模型压缩后的并列提纲。

### WYL-004 / WYL-005｜建议 block

> 他整个人不会一下子就掉下去。

> 做安静动作，画两笔旧换东西，妈妈观察能接住。

都不是普通 AI 味，而是句子含义已经无法稳定理解。

### WYL-006｜建议 block

标题写“回来直接趴沙发”，正文却写“回家也不蔫”，阶段没有交代，标题正文方向相反。

### WYL-011 至 WYL-014｜建议 pass

以下表达不要因为口语化而修：

- 蔫蔫的、精神头足
- 保护屏障撑起来
- 省心——不对，是开心
- 狗都嫌的年纪

### WYL-015｜建议 watch，可接受 pass

“状态在线、家里安排没那么乱”略泛，但句子成立。不要为了写得更漂亮自动改写。

## 实现边界

人工标签已经确认，可以建立 `WangyueFluencyJudgeService`。它只输出 `pass/watch/block + issue_code + evidence`。`block` 才进入说人话局部改写，watch 不自动改。

## 现有审核基线

### AI Flavor 正则

当前 `AIFlavorReview` 主要检测标题卖点、解释腔、营销密度和模板收口，不具备通用中文流畅性判断能力。

| 指标 | 结果 |
|---|---:|
| 一致率 | 40.0% |
| block 召回率 | 0% |
| 非 block 误杀率 | 14.3% |

8 条病句、残句和标题正文冲突全部漏检；同时把 `WYL-012 / 保护力慢慢撑起来了` 因标题出现“保护力”误判为需要改写。

### 当前超级审核 Prompt

使用当前生产 `ProductExperienceLLMReviewService` 和 `deepseek-v4-flash` 运行，不增加格式重试；解析失败按生产真实行为记为 `unavailable`。

| 指标 | 结果 |
|---|---:|
| 一致率（含 unavailable） | 20.0% |
| block 召回率 | 12.5% |
| 非 block 误杀率 | 14.3% |
| unavailable | 11 条 |
| 总 tokens | 91205 |
| 累计模型延迟 | 210279 ms |

超级 Prompt 既没有稳定抓住病句，又因为输出字段过多、解释过长而频繁生成非法或截断 JSON。`WYL-015` 这种意思清楚但略泛的句子还被误判为 `unnatural_product_appearance / rewrite`。

### Rewrite Quality Validator

现有 `RewriteQualityValidatorService` 的职责是比较 before/after，不能替代生成结果的首次流畅性审核；当前 approved 金标也只有 2 条。它应保留为改写后的独立验收步骤，后续扩充样本，不与 `fluency_v1` 合并。

## Focused Judge 模型选择

`deepseek-v4-flash` 在细粒度中文流畅性判断上不稳定，多次把人工确认的病句解释为“可以理解”。模型对比中，`qwen-plus` 首轮一致率为 100%，`deepseek-v4-pro` 为 93.3%。

首次 `qwen-plus` 3 轮稳定性测试中，唯一波动是 `WYL-012 / 保护屏障撑起来`：两次 pass、一次 watch。补充“人工通过判例必须 pass”的最小边界后，于 2026-07-16 重跑 3 轮：

| 指标 | 结果 |
|---|---:|
| 调用次数 | 45 |
| 接受标签一致率 | 100% |
| block 召回率 | 100% |
| 非 block 误杀率 | 0% |
| WYL-012 | 3/3 pass |
| 全量标签跨轮波动 | 0 |

因此流畅性 Focused Judge 固定使用独立的 `qwen-plus` 路由，不继承文章生成模型。调用时通过 `llm_model_route` 和 `llm_provider_config` 动态解析 Aliyun provider、实际模型名和凭证，仍只作 Shadow 记录，不影响 `hard_pass`、改写、导出或入池。
