# A2 舆情改善评论审核规则

## 审核顺序

`生成评论 -> machine audit -> LLM review -> operator judgment`

- machine audit 负责违禁词、硬禁词、长度、重复度和确定性的分类锚点。
- 机器未通过项标记为 `machine_blocked / not_run`，不送给 LLM reviewer，也不计入 LLM 可用档位。
- LLM review 只判断分类贴合、事实支持、评论质感和修改成本，不重复审核机器硬规则。
- LLM reviewer 必须结合整句语义以及当前规则的 `focus + examples` 判断，不得维护逐词黑名单或白名单，也不得因为单个词语直接降档。
- 新的词面误判优先修正语义判断原则或所属机器规则，不在 LLM prompt 中逐个追加词语例外。
- 没有真实运营确认时，`operator judgment` 必须显示为 `not run`。

## 迭代记录

- 2026-07-11：模型测试中通过机器审核和 LLM review 的评论也属于候选资产，必须保留模型、分类、batch_id 和审核档位后汇总入池；Direct、LightFix 与 operator judgment 分开保存，不得因测试用途直接丢弃。
- 2026-07-11：LLM reviewer 移除具体违禁词、允许词及词面例外，只保留业务可用性判断；机器审核继续作为前置门禁。
