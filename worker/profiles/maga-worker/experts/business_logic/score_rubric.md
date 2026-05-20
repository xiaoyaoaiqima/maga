# 业务逻辑总审 AE 评分规则 (0-100)

## 评分维度

| 维度 | 分值 | 说明 |
|---|---:|---|
| 痛点理解 | 20 | 主题/痛点类别是否准确，是否抓住妈妈真实关注点 |
| 卖点匹配 | 25 | 核心卖点是否匹配痛点，是否避免卖点错位 |
| 因果链 | 20 | 是否按“痛点表现 -> 背后关注 -> 卖点依据”展开 |
| 写作结构 | 15 | 是否符合小红书短标题、短段落、场景化表达 |
| 人设视角 | 10 | 是否保持经验型建议视角，不混乱不装专家 |
| 真人感 | 10 | 是否避免模板化、说明书化、AI味 |

## 直接扣分项

- 把乳铁蛋白作为吐奶、便便、肚肚不适的核心解决原因：最多给 75。
- 把 8种HMO 作为吐奶/便便问题的直接解决原因：最多给 80。
- 连续罗列 3 个以上卖点并共同承担同一痛点解决逻辑：最多给 80。
- 人设视角混乱，出现专家、宝妈亲历、品牌方混杂：最多给 82。
- 文章像说明书或投放硬广，缺少具体场景：最多给 78。

## 输出格式

```yaml
score: 78
painpoint_match: true
sellingpoint_match: false
causal_chain_valid: false
persona_pov_valid: true
narrative_structure_valid: true
naturalness_valid: false
wrong_sellingpoint_as_core:
  - 乳铁蛋白
overstacked_sellingpoints: true
ai_smell_hits:
  - 说明书式卖点罗列
hits:
  - rule: 卖点错位
    location: 正文第2段
    suggestion: 将乳铁蛋白改为辅助信息，核心改成天然乳脂/OPO和肚肚舒适的判断链路。
suggestions:
  - 先补一句妈妈担心便便节奏的具体场景，再自然带出脂肪结构相关卖点。
verdict: fail
```
