# MAGA Agent 质量循环

MAGA 的 Agent 能力围绕现有业务链路运行，不另建一个脱离平台的自由写作入口。

```text
source / rule evidence
-> context layer check
-> real content.generate execution
-> evaluator review
-> failure attribution
-> minimal rerun
-> batch report
-> durable review memory
```

## 一次可审计迭代的最小记录

- 使用的 source、业务规则和资产版本；
- 实际调用的 API、服务或脚本；
- 批次规模、样本范围和模型参数；
- 质量评估矩阵及代表性样本；
- 失败归因层和证据；
- 本轮唯一的最小改动；
- before/after 结果、回归情况和最终决策。

## 边界

- 真实生成链路、数据库、业务资产和运行产物归 MAGA 管理；
- 活动/品牌事实不能写进全局写作规则，必须留在对应资产包；
- 真实用户素材需要经过授权、去标识和质量筛选后才能作为参考；
- 质量目标是可验证的批次改进，不是每次都追求单篇“更漂亮”。
