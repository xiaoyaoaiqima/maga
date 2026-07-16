# 旺玥 Focused Judge 模型选择

## 结论

不要把所有审核统一切到 qwen-plus。不同职责使用不同专用模型：

| 场景 | 推荐模型 | 结论依据 |
|---|---|---|
| 代码硬审 | 不使用 LLM | 年龄、产品形态、冲泡动作、硬违禁词继续由代码判断 |
| Temporal Logic Judge | deepseek-v4-flash | 与 qwen-plus 同为 28/28，但 DeepSeek 平均 11.4 秒，qwen-plus 26.0 秒 |
| Claim/Public Disease Judge | deepseek-v4-flash | DeepSeek 15/15；qwen-plus 14/15，并漏掉一个当前公共疾病环境 block |
| Content Fit Judge | deepseek-v4-flash | DeepSeek 19/19；qwen-plus 17/19，误杀两个正常省心/选奶收口样本 |
| Fluency Judge | qwen-plus | 中文病句和语义断裂金标上更稳定，已经固定专用路由 |
| Rewrite Quality Validator | qwen-plus | before/after 比较比 DeepSeek 稳定，已经固定专用路由 |

## Temporal 同轮 A/B

| 模型 | 人工允许标签 | exact label+issue | block 召回 | 误杀 | unavailable | 平均耗时 |
|---|---:|---:|---:|---:|---:|---:|
| deepseek-v4-flash | 28/28 | 27/28 | 100% | 0 | 0 | 11.4 秒 |
| qwen-plus | 28/28 | 27/28 | 100% | 0 | 0 | 26.0 秒 |

两者判断质量持平，切 qwen-plus 没有收益。

## Claim/Public Disease 同轮 A/B

| 模型 | 人工允许标签 | block 召回 | 误杀 | unavailable | 平均耗时 |
|---|---:|---:|---:|---:|---:|
| deepseek-v4-flash | 15/15 | 100% | 0 | 0 | 3.8 秒 |
| qwen-plus | 14/15 | 85.7% | 0 | 0 | 8.4 秒 |

qwen-plus 将 WYC-014 从 block 降为 watch：

> 最近班里好多孩子都生病请假了，我家因为一直喝旺玥，到现在还稳稳的。

该句使用当前群体疾病环境和明确产品因果，人工标准是 block。

## Content Fit 同轮 A/B

| 模型 | 人工允许标签 | block 召回 | 误杀 | unavailable | 平均耗时 |
|---|---:|---:|---:|---:|---:|
| deepseek-v4-flash | 19/19 | 100% | 0 | 0 | 16.7 秒 |
| qwen-plus | 17/19 | 100% | 2 | 0 | 24.9 秒 |

qwen-plus 误杀：

- WYF-002：已有成分和自家反馈，仍把“终于不用再纠结奶粉了”判成 block。
- WYF-017：把“对比下来选了旺玥”和“选对奶粉，当妈的省心不少”判成抽象 brief，违反最新人工口径。

## 路由原则

模型按任务选，不按“哪个总体更强”统一。qwen-plus 更适合中文流畅性和改写前后比较；DeepSeek 在短、明确的时间/疾病/内容适配分类上更快，且当前金标召回更好。

该模型分工现已用于旺玥 V3 正式审核链路。

## 路由实施状态

已按上表固化专用模型路由：

- Temporal Logic、Claim/Public Disease、Content Fit 固定请求 `deepseek-v4-flash`。
- Fluency Judge、Rewrite Quality Validator 固定请求 `qwen-plus`。
- 正式审核、手动复审和改写候选复审共用同一套维度到模型映射，不再继承文章生成模型。
- 专用 route 缺失时标记 unavailable 或进入人工 hold，不静默回退。
- provider 凭证只在调用前临时注入，不写回文章 plan。

旺玥 V3 已停止调用旧 `ProductExperienceLLMReviewService` 超级审核 Prompt。代码硬审后由 Focused Pipeline 正式决定入池、观察、局部改写或 hold；其他业务暂时继续使用原审核链路。手动 shadow API 仅保留用于排查，不参与自动后处理。
