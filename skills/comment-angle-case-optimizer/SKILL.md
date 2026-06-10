---
name: comment-angle-case-optimizer
description: 按单个评论切角子方向逐条优化语料示例、吸收运营反馈、写回指定 MAGA asset 并跑小批量验证；适用于用户说“by case 看评论切角”“一个一个改示例”“改完用这个切角跑几条看看”。
---

# 评论切角 by case 优化

用于把运营现场反馈沉淀到某一个评论切角子方向里，再用小批量生文验证。调用时必须明确当前任务使用的 `asset_key`；不要在 skill 内硬编码具体活动资产。默认不要加重入口生成要求，优先改当前子方向的示例池。

## 工作流

1. 明确当前任务参数。
   - 必须从用户上下文、任务配置或本轮调查中确认 `asset_key`。
   - 必须确认定位方式：`rule_id`、`source_row_no` 或 `comment_angle` 三选一。
   - 不确定当前资产时，先查询/询问，不要凭历史记忆使用某个活动资产。
2. 读取当前激活 asset 的真实子方向，不凭记忆改。
   - 查看单条：`PYTHONPATH=. ../.venv/bin/python scripts/update_comment_angle_rule_item.py --asset-key <asset_key> --rule-id <rule_id> --show-current`
   - 也可用 `--source-row-no <row_no>` 或 `--comment-angle <name>` 定位。
3. 和用户逐条确认 case。
   - 先指出当前示例的问题：结构重复、生活感弱、活动入口太机械、剧情事实不准等。
   - 每次只给当前子方向的新示例，不一次性铺开 11 个方向。
4. 改示例时保持轻规则。
   - 规则只说明这个子方向在聊什么，边界写轻一点，别写成审核清单。
   - 多样性靠示例承担，避免把通用生成要求写成重规则。
   - 子方向规则不要堆“不要/必须/优先/禁止”长串；必要边界放一两句，剩下靠示例体现。
   - 示例要像评论区随手说话，允许结合当前业务自然出现生活碎片、时间点、社群聊天、门店顺路、使用场景等。
   - 具体业务口径只来自当前任务上下文、资料文件、运营确认和该 asset 现有规则，不从 skill 自行补充。
5. 用户给出草稿或你先拟好草稿时，优先用草稿跑小批量，不先写库。
   - 调用 `POST /api/v1/content-agent/comment-batches/start`。
   - 传 `draft_corpus`，并用 `draft_rule_id` / `draft_source_row_no` 定位草稿覆盖的子方向。
   - 如果草稿就是覆盖当前已选子方向，也可以传当前 `rule_id` / `source_row_no`，服务会用它们作为草稿定位。
   - 草稿只进入本次 batch 的 plan，不更新 active asset；batch 的 `strategy_json.draft_rule_override` 会记录本次用了草稿。
   - 跑 10 条看样例，用户确认后再写回正式语料。
6. 写回时同步 `corpus` 和 `examples`。
   - 把确认后的语料块保存到 `prompts/<asset_key>_<rule_id>.txt` 或相近命名。
   - dry-run：`PYTHONPATH=. ../.venv/bin/python scripts/update_comment_angle_rule_item.py --asset-key <asset_key> --rule-id <rule_id> --corpus-file <file> --sync-examples-from-corpus`
   - 发布：同命令加 `--apply`，默认使用 `new-version`。
7. 验证时只跑当前切角。
   - 优先调用 `POST /api/v1/content-agent/comment-batches/start`，传 `asset_key` + `rule_id` 或 `source_row_no` + `count`，精准重复当前子切角。
   - 只有在无法定位 `rule_id/source_row_no` 时，才退回用 `comment_angle` 过滤；此时要提醒用户同名/同类切角可能混在一起。
   - 跑完在回复里贴正文和问题摘要；如链路会产出文件，再给出 batch id 和文件路径。

## 精准试跑接口

后端已有单个子切角试跑能力，by case 优化时优先使用这个接口：

```http
POST /api/v1/content-agent/comment-batches/start
```

已发布版本试跑示例：

```json
{
  "asset_key": "<asset_key>",
  "rule_id": "<rule_id>",
  "source_row_no": 16,
  "count": 10,
  "created_by": "ops"
}
```

草稿语料试跑示例：

```json
{
  "asset_key": "<asset_key>",
  "rule_id": "<rule_id>",
  "draft_corpus": "这里放当前修改中的评论切角语料块",
  "count": 10,
  "created_by": "ops"
}
```

前端如果只传 `comment_angle`，只能按大切角名称过滤；当一个大切角下有多个子方向时，会混跑多个子方向。更顺的运营入口是：

- 表格每行提供“试跑10条”，传 `rule_id` 和 `source_row_no`。
- 编辑语料时提供“用当前草稿试跑”，传 `draft_corpus`，确认效果后再发布资产版本。

## 任务口径

- skill 不内置任何品牌、剧情、竞品、功效、检测、活动机制等业务结论。
- 如果当前任务已有专项口径，以用户最新确认和当前 asset 内容为准。
- 如果口径冲突，先向用户指出冲突并等待确认；不要自行合并成新的业务事实。
- 通用 prompt、系统关键词和守卫只做基础边界；业务信息优先沉淀到当前评论切角的规则和示例。

## 输出给用户

先给当前子方向的改后示例，让用户确认；写库和跑批后，给 batch id、产物路径、抽样正文和明显问题。不要只说“已优化”。
