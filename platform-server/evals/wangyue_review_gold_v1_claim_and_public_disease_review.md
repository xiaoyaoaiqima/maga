# 旺玥疾病宣称与公共疾病环境候选金标 v1

## 状态

这 15 条已于 2026-07-15 完成人工确认，冻结为 `approved` 金标。当前仍未接入生产审核、改写或入池判断。

- `pass`：5 条
- `watch`：3 条
- `block`：7 条

## 这批只看什么

- 过去发生的感冒、请假、全勤、少中招等自家观察
- 过去式同伴生病或班级请假
- 当下症状后立即用旺玥补救或加量
- 医生背书、治疗、防病和绝对保证
- 当前流感季或群体生病环境

项目硬边界：`流感` 已升级为旺玥确定性 `block_only` 禁词，无论当前或过去语境，出现即直接阻断、不改写。短 Judge 对当前流感环境仍应输出 block，但最终 ban 不依赖 LLM。

不在这批判断一般时间矛盾、年龄、冲泡、产品形态、人味或种草强弱。

## 建议重点 review

### WYC-003｜建议 pass

> 家里旺玥一直喝着，这学期孩子到现在还是全勤，周末也照常出去玩。

这里把“全勤”视为自家长期观察，不视为产品保证不生病。

### WYC-005｜建议 watch，可接受 pass

> 坚持喝了一阵，整体状态挺在线，回头看连感冒都比以前少了。

按已有人工反馈，这类表达可以用；标 watch 只是为了观察疾病效果承接，不自动改写。

### WYC-006 / WYC-007｜建议 watch，可接受 pass

过去式朋友家娃生病、过去式班级请假不 hard fail。它们和当前公共疾病环境分开处理。

### WYC-014｜建议 block

> 最近班里好多孩子都生病请假了，我家因为一直喝旺玥，到现在还稳稳的。

这里同时具备当前群体疾病环境、竞对式对照和明确产品因果，是这批公共疾病环境的 block 边界。

## 人工确认后再做

人工 review 已通过。下一步只建立独立短 Judge 和 shadow 评测，不直接调整确定性规则。当前生产长 Prompt 和现有审核行为保持不变。

## 短 Judge 校准

候选服务：`WangyueClaimPublicDiseaseJudgeService`

模型只输出：

```json
{"label":"pass|watch|block","issue_code":"枚举值","evidence":"原文证据"}
```

使用 `deepseek-v4-flash` 对这 15 条 approved 金标进行首次同集校准：

| 指标 | 结果 |
|---|---:|
| 人工允许标签一致率 | 100% |
| block 召回率 | 100% |
| 非 block 误杀率 | 0% |
| 总 tokens | 7847 |
| 累计模型延迟 | 26940 ms |

模型输出分布为 `pass 8 / block 7 / watch 0`。3 条人工允许 `pass/watch` 的边界样本全部被判为 `pass`，因此当前只能确认它没有误杀，不能确认 watch 灵敏度已经校准。

## Shadow 验证

已增加显式批次接口：

```text
POST /content-agent/batches/{batch_id}/claim-public-disease-shadow-review
```

在 batch 497 的 1 条真实生成内容上完成调用：Judge 返回 `pass`，结果写入 `quality_json` 和 `review_report`，原 `hard_pass=true` 保持不变，且明确记录 `shadow=true / affects_hard_pass=false`。

该 Judge 当前不参与默认生文、入池、导出、拦截或改写。下一步应补独立 holdout 样本和更多 watch 边界，再讨论生产替换。
