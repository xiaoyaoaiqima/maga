# 提示词优化工作台 MVP

## 背景

当前仓库已经沉淀了多类自动优化提示词脚本：

- `scripts/optimize_prompt_from_txts.py`：根据原提示词、生成内容、运营审查问题，输出局部修补建议和 patches。
- `scripts/optimize_prompt_by_human_opinion.py`：根据原提示词和人类全局意见，输出去重、消矛盾、重构建议和 patches。
- `scripts/optimize_critic_prompt_from_txts.py`：针对审核提示词做优化建议。
- `scripts/batch_prompt_optimizer.py` / `scripts/batch_prompt_optimizer_from_txt.py`：面向批量样本输出优化建议。

这些脚本已经证明需求不再是一次性调 prompt，而是进入“提示词版本治理”阶段：需要记录问题、优化任务、patch 建议、人工采纳结果和修改后验证效果。

## MVP 目标

第一阶段不做全自动改写上线，而是做一个半自动的“提示词 PR 工作台”：

1. 选择或粘贴一份提示词。
2. 选择优化模式。
3. 输入人类意见、审查问题、生成内容或批量样本。
4. 调用优化器生成结构化 patches。
5. 人工逐条接受、拒绝、编辑。
6. 保存新提示词版本，并保留完整优化记录。
7. 可选地用测试样本跑修改前后对比。

核心价值是把脚本输出变成可追踪、可复盘、可逐步产品化的数据闭环。

## 范围

### 第一阶段包含

- 提示词资产管理：保存 prompt 原文、类型、版本、来源。
- 优化任务：支持局部修补、全局整理、critic prompt 优化三种模式。
- patch 审阅：展示 old_text、new_text、reason，支持采纳、拒绝、编辑。
- 版本保存：采纳 patch 后保存新版本，记录父版本。
- 运行记录：保存输入、模型参数、原始模型输出、解析结果、错误信息。
- 调试兼容：保留现有脚本作为底层能力，系统先调用同一套 prompt optimizer 逻辑。

### 第一阶段不包含

- 不做无人值守自动合并上线。
- 不做复杂权限和审批流。
- 不做完整实验平台。
- 不做跨 prompt 的智能推荐和自动归因。
- 不强制接入所有历史脚本，只先接入三类核心优化模式。

## 核心对象

### Prompt

提示词资产。

建议字段：

- `id`
- `tenant_code`
- `name`
- `prompt_type`：`generation` / `critic` / `other`
- `description`
- `current_version_id`
- `tags`
- `create_time`
- `update_time`

### PromptVersion

提示词版本。

建议字段：

- `id`
- `prompt_id`
- `version_no`
- `content`
- `parent_version_id`
- `source_run_id`
- `change_summary`
- `created_by`
- `create_time`

### PromptIssue

一次人类意见、运营审查问题或失败样本。

建议字段：

- `id`
- `prompt_id`
- `prompt_version_id`
- `issue_type`：`human_opinion` / `review_problem` / `batch_case`
- `problem_text`
- `generated_content`
- `generated_title`
- `metadata`
- `create_time`

### PromptOptimizerRun

一次优化任务。

建议字段：

- `id`
- `prompt_id`
- `prompt_version_id`
- `issue_id`
- `mode`：`local_patch` / `global_refactor` / `critic_patch` / `batch_patch`
- `model`
- `base_url`
- `temperature`
- `max_tokens`
- `status`：`pending` / `running` / `succeeded` / `failed`
- `input_snapshot`
- `raw_output`
- `parsed_output`
- `error_message`
- `create_time`
- `update_time`

### PromptPatch

结构化 patch 建议。

建议字段：

- `id`
- `run_id`
- `patch_index`
- `operation`：`replace` / `delete` / `insert_after` / `insert_before`
- `old_text`
- `new_text`
- `reason`
- `status`：`pending` / `accepted` / `rejected` / `edited`
- `edited_new_text`
- `review_comment`
- `create_time`
- `update_time`

### PromptEvaluation

修改后的验证记录，第一阶段可选。

建议字段：

- `id`
- `prompt_id`
- `base_version_id`
- `candidate_version_id`
- `test_set_id`
- `result_snapshot`
- `human_score`
- `critic_score`
- `summary`
- `create_time`

## 优化模式

### 局部修补 local_patch

输入：

- prompt
- generated_content
- problem

对应当前脚本：

- `scripts/optimize_prompt_from_txts.py`

适用场景：

- 某篇生成结果被运营指出明确问题。
- 目标是找到提示词中最小必要修改。

输出重点：

- 1 到数条局部 patches。
- 说明原提示词为什么没约束住这次问题。

### 全局整理 global_refactor

输入：

- prompt
- human_opinion / problem

对应当前脚本：

- `scripts/optimize_prompt_by_human_opinion.py`

适用场景：

- 人类认为提示词太冗长、重复、矛盾。
- 需要从全局视角清理结构，而不是围绕某篇内容修补。

输出重点：

- 去重、合并、删除、重组 patches。
- 风险提示 `risk_notes`。

### 审核提示词优化 critic_patch

输入：

- critic prompt
- content
- problem

对应当前脚本：

- `scripts/optimize_critic_prompt_from_txts.py`

适用场景：

- 审核提示词误判、漏判、泛化过度。
- 需要修正审核标准本身。

输出重点：

- 审核规则边界、扣分标准、误判防护。

### 批量修补 batch_patch

输入：

- prompt
- 多条 title/content/problem 样本

对应当前脚本：

- `scripts/batch_prompt_optimizer.py`
- `scripts/batch_prompt_optimizer_from_txt.py`

适用场景：

- 多篇内容暴露同一类稳定问题。
- 需要从样本集合中找高频根因。

输出重点：

- 聚合后的共性问题。
- 更保守的全局 patch 建议。

## 页面设计

### 页面入口

建议新增在专家域下：

- 路由：`/expert/prompt-optimizer`
- 菜单：`专家调试 / 提示词优化工作台`

这样和现有 `expert/debug`、`expert/eval` 更贴近。

### 页面布局

第一屏应是工作台，不做介绍页。

左侧输入区：

- Prompt 选择器或粘贴框。
- 版本选择。
- 优化模式 Tabs：局部修补 / 全局整理 / 审核优化 / 批量样本。
- 根据模式展示不同输入表单。
- 模型参数折叠区。

右侧结果区：

- 运行状态。
- prompt_issue / modify_suggestion / risk_notes。
- patches 列表。
- 每条 patch 的操作按钮：接受、拒绝、编辑。
- 应用预览：原 prompt 与候选 prompt diff。

底部：

- 保存为新版本。
- 复制 patches。
- 查看 debug input / raw output。

## 后端接口草案

### Prompt

- `GET /api/v1/prompt-optimizer/prompts`
- `POST /api/v1/prompt-optimizer/prompts`
- `GET /api/v1/prompt-optimizer/prompts/{prompt_id}`
- `GET /api/v1/prompt-optimizer/prompts/{prompt_id}/versions`
- `POST /api/v1/prompt-optimizer/prompts/{prompt_id}/versions`

### Run

- `POST /api/v1/prompt-optimizer/runs`
- `GET /api/v1/prompt-optimizer/runs`
- `GET /api/v1/prompt-optimizer/runs/{run_id}`
- `POST /api/v1/prompt-optimizer/runs/{run_id}/rerun`

### Patch

- `GET /api/v1/prompt-optimizer/runs/{run_id}/patches`
- `PATCH /api/v1/prompt-optimizer/patches/{patch_id}`
- `POST /api/v1/prompt-optimizer/runs/{run_id}/apply`

### Evaluation

- `POST /api/v1/prompt-optimizer/evaluations`
- `GET /api/v1/prompt-optimizer/evaluations`

## 后端实现建议

第一阶段不要直接 shell 调用脚本。建议把脚本里可复用的能力拆成 service：

- `PromptOptimizerService.optimize_local_patch(...)`
- `PromptOptimizerService.optimize_global_refactor(...)`
- `PromptOptimizerService.optimize_critic_patch(...)`

脚本保留 CLI 入口，但 CLI 内部调用 service。这样工作台和命令行共享同一套逻辑，后续不会出现“脚本能力”和“系统能力”分叉。

建议新增模块：

- `platform-server/app/models/prompt_optimizer.py`
- `platform-server/app/schemas/prompt_optimizer.py`
- `platform-server/app/services/prompt_optimizer_service.py`
- `platform-server/app/api/v1/endpoints/prompt_optimizer.py`
- `platform-server/alembic/versions/027_add_prompt_optimizer_tables.py`

## Patch 应用策略

第一阶段 patch 应用只做保守策略：

1. `old_text` 必须在当前版本中唯一命中，才允许自动应用。
2. 多个 patches 应按原文位置从后往前应用，避免位置偏移。
3. 如果 `old_text` 不存在或命中多次，标记为需要人工处理。
4. `insert_after` / `insert_before` 的锚点也必须唯一命中。
5. 所有应用结果先生成候选版本，不直接覆盖当前版本。

## 状态流转

```text
创建 run
  -> running
  -> succeeded / failed

patch generated
  -> pending
  -> accepted / rejected / edited

apply accepted patches
  -> candidate version
  -> human review
  -> save as new prompt version
```

## 迭代路线

### Milestone 1：数据闭环

- 建表。
- 后端 run 创建和查询。
- 接入三类优化模式。
- 保存 patches。
- 前端能发起任务、展示结果。

### Milestone 2：人工审阅

- patch 接受、拒绝、编辑。
- 自动应用唯一命中的 patch。
- 保存新版本。
- 展示版本 diff。

### Milestone 3：效果验证

- 绑定 test set。
- 修改前后生成对比。
- 接入 critic score。
- 人工评分和问题标签沉淀。

### Milestone 4：沉淀策略

- 高频问题统计。
- 常见 patch 模板。
- prompt 冗余度、冲突度、红线覆盖度分析。
- 优化器提示词自身的版本管理。

## 风险

- 自动 patch 可能误改关键红线，所以第一阶段必须人工确认。
- 全局整理会影响较大，需要保留完整版本回滚链路。
- LLM 输出的 old_text 可能无法唯一定位，必须在后端做校验。
- 优化器本身也会漂移，所有 run 必须记录模型、参数、系统提示词和用户输入快照。

## 推荐下一步

先实现 Milestone 1 和 Milestone 2 的最小闭环：

1. 建 `prompt_optimizer` 相关表。
2. 把现有脚本中的 LLM 调用和 JSON 解析抽成可复用 service。
3. 新增后端接口：创建 run、查询 run、更新 patch 状态、应用 patches。
4. 新增前端页面：输入、运行、patch 审阅、保存新版本。

这个范围足够把现有脚本积累变成系统能力，同时不会过早引入复杂实验平台。
