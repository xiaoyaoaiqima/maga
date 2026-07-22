# 旺玥疾病宣称与公共疾病环境候选金标 v1

## 状态

这 17 条已于 2026-07-21 按最新人工边界更新为 `approved` 金标，并同步生产确定性审核、改写和 focused judge。

- `pass`：4 条
- `watch`：0 条
- `block`：13 条

## 这批只看什么

- 允许保留的抽象表达：少中招、容易中招、保护力在线、状态稳、小状况少些
- 不论过去或现在都阻断的具体场景：感冒、咳嗽、传染、发烧、医院、请假、同伴生病
- 全勤或普通出勤记录本轮不单独阻断；与具体疾病、就医或请假情节同现时阻断
- 当下症状后立即用旺玥补救或加量
- 医生背书、治疗、防病和绝对保证
- 当前流感季或群体生病环境

项目硬边界：`流感` 已升级为旺玥确定性 `block_only` 禁词，无论当前或过去语境，出现即直接阻断、不改写。短 Judge 对当前流感环境仍应输出 block，但最终 ban 不依赖 LLM。

不在这批判断一般时间矛盾、年龄、冲泡、产品形态、人味或种草强弱。

## 建议重点 review

### WYC-001 / WYC-002 / WYC-004～WYC-007｜block

旧金标曾允许过去感冒、请假、感冒变少和过去式同伴生病。本轮统一收紧：这些都属于具体疾病、就医或请假场景，不再因过去时或长期观察跨度放行。

### WYC-003｜pass

> 家里旺玥一直喝着，这学期孩子到现在还是全勤，周末也照常出去玩。

全勤本轮不单独扩禁；这条没有展开感冒、咳嗽、发烧、医院或请假情节，可以保留。

### WYC-015～WYC-017｜pass

> 旺玥喝了一阵再回看，孩子平时小状况比以前少些，出去玩状态也在线。

> 喝了一阵，感觉孩子平时少中招，状态也稳。

> 保护力在线，日常状态挺稳。

这些是允许保留的抽象保护力或状态表达，不能因“中招、保护力、状态、小状况”等词被误杀。

### WYC-014｜建议 block

> 最近班里好多孩子都生病请假了，我家因为一直喝旺玥，到现在还稳稳的。

这里同时具备当前群体疾病环境、竞对式对照和明确产品因果，是这批公共疾病环境的 block 边界。

## 生产同步

- 确定性 phrase guard 增加 `wangyue_concrete_disease_scenario`，直接进入 blocking hits。
- 改写只删除具体疾病、就医、请假或同伴生病情节，保留抽象“少中招/保护力在线/状态稳”等表达，不发明新疾病或医疗事实。
- focused judge 增加 `concrete_disease_scenario`，聚合到 `compliance_cleanup`。
- 长 LLM review 与本金标保持同一边界。

## 短 Judge 校准

候选服务：`WangyueClaimPublicDiseaseJudgeService`

模型只输出：

```json
{"label":"pass|watch|block","issue_code":"枚举值","evidence":"原文证据"}
```

旧版 15 条校准结果已失效，不再作为当前边界依据。新金标以本轮 17 条回归和 production 小批结果为准。

## Shadow 验证

已增加显式批次接口：

```text
POST /content-agent/batches/{batch_id}/claim-public-disease-shadow-review
```

在 batch 497 的 1 条真实生成内容上完成调用：Judge 返回 `pass`，结果写入 `quality_json` 和 `review_report`，原 `hard_pass=true` 保持不变，且明确记录 `shadow=true / affects_hard_pass=false`。

该 Judge 仍是 shadow，不单独改变 hard pass；生产阻断由确定性 phrase guard 承担，focused 结果用于独立观测和聚合验证。
