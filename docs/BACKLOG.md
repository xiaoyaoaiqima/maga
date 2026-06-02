# MAGA 生文流程开发清单

> 最后更新：2026-06-02

本文档只保留当前 MAGA 生文主链路相关事项。旧 RAAP Job、Prompt Optimizer、旧关键词语料、旧 XHS worker chain、自动学习类计划不再放入当前 Backlog。

## 当前主链路

运营主流程：

1. 上传业务规则包。
2. 选择规则包生成文章或评论。
3. 查看生成结果、Trace、审核和改写记录。
4. 对内容通过、提交修改意见、人工编辑或加入业务违禁词。

系统配置面：

- 系统提示词关键词
- 生文 Expert
- 模型配置
- 业务违禁词

执行能力：

- `asset.import`
- `content.generate`
- `content.rewrite`

## P0 收敛项

| 任务 | 说明 | 状态 |
|------|------|------|
| 旧 XHS capability 下线 | `xhs.*` 不再作为运行能力，文章和评论统一走 `content.generate` | 已完成 |
| 评论独立 capability 下线 | `comment.generate` 不再存在，评论由 `content.generate` 按 `content_type=comment` 输出 | 已完成 |
| 单篇正式入口下线 | `/content-agent/generation/start` 不再作为运营正式入口 | 已完成 |
| Prompt Optimizer 运行时清理 | 旧优化工作台 API/service/model/schema 从运行代码移除，历史表不 drop | 已完成 |
| Worker profile 收敛 | `maga-worker` 只描述当前三类 capability 和统一生文链路 | 已完成 |

## P1 下一步

| 任务 | 说明 |
|------|------|
| 改写质量提升 | `content.rewrite` 需要更明确地保留原意、解决反馈点，并输出改动说明用于前端对比 |
| 评价反馈闭环 | 反馈页继续强化“通过 / 修改意见 / 人工编辑 / 加违禁词”的主操作，不做自动学习 |
| 业务规则包体验 | 规则包名称、类型、默认生成量、示例统计和风险提示继续优化 |
| Expert 版本管理 | 生文、审核、改写 Expert 的版本差异、启停和默认选择要更清楚 |

## P2 后续

| 任务 | 说明 |
|------|------|
| 批次质量看板 | 围绕通过率、改写率、违禁词命中、人工编辑率做运营看板 |
| 批次内重复度控制 | 相似度审核已经在后端执行，后续补更可解释的报告和阈值配置 |
| 多活动规则包 | 源悦评论、源悦生文之外的活动按同一规则包机制扩展 |

## 不做项

- 不恢复旧 Prompt Optimizer 工作台。
- 不恢复 `xhs.*` worker chain。
- 不新增 `comment.generate` 专用能力。
- 不把业务违禁词塞进首轮生文 prompt。
- 不做自动学习、自动训练、自动改规则。
