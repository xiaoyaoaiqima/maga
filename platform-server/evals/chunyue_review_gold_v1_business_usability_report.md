# 莼悦业务可用性审核金标 v1

## 复现入口

- 金标：`evals/chunyue_review_gold_v1_business_usability.json`
- rubric code：`chunyue_business_usability_v1`
- replay：`POST /api/v1/content-agent/batches/{batch_id}/business-usability-review`，请求传 `{"force":true}`
- 持久化位置：每篇 `quality_json.product_experience_llm_quality_review.review_rubric_code`

## 人工确认边界

- 只拦原始表达之外新增或改变的可核验产品事实。
- 抽象使用感受可以自然外扩。
- 强种草标题和主观效果判断可以直接入池。
- 不强制完成选择或购买莼悦的闭环。
- 任务复述式表达只做局部轻修，不否定种草内核。

## batch 704 金标分布

- `direct_pool`：CYU-002、CYU-003、CYU-004、CYU-005、CYU-007、CYU-008
- `light_fix_usable`：CYU-006
- `hold_out`：CYU-001

后续每次人工边界变化都必须同步修改：金标行、审核 Prompt、回归报告和测试。只改预览 Markdown 不算完成校准。

## 2026-07-19 batch 704 正式 replay

使用 `chunyue_business_usability_v1` 强制回放 batch 704：

- 实际审核：8
- 跳过：0
- 失败：0
- 金标一致：8/8
- rubric code 持久化：8/8
- `direct_pool`：6
- `light_fix_usable`：1
- `hold_out`：1
- 本轮格式重试：0

校准过程中曾发现 item 6 的审核 JSON 因输出预算不足被截断。当前莼悦 reviewer 使用精简 JSON 契约、2400 输出预算，并在解析失败时最多重试一次；最终正式 replay 无失败。

复现报告：`outputs/chunyue_migration/history_runs/batch_704/business_usability_replay_v1_verified.json`
