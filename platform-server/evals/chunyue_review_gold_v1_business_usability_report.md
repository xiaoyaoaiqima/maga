# 莼悦业务可用性审核金标 v1

## 复现入口

- 金标：`evals/chunyue_review_gold_v1_business_usability.json`
- rubric code：`chunyue_business_usability_v1`
- replay：`POST /api/v1/content-agent/batches/{batch_id}/business-usability-review`，请求传 `{"force":true}`
- 持久化位置：每篇 `quality_json.product_experience_llm_quality_review.review_rubric_code`

## 人工确认边界

- 只拦原始表达与已确认莼悦基础事实之外新增或改变的硬产品事实。
- 莼悦含 5 重有机 HMO、有机 GOS、有机活性 OPN 和有机乳源 OPO 类似结构脂；这些已确认事实可以跨本篇原始表达出现。
- 睡眠、便便、肠胃、自护力、吸收、长肉等宝宝使用效果可以自然外扩并组成完整效果链，不因种草性强自动降级。
- 欧盟有机规则禁止激素和生长促进剂，个体兽医治疗存在例外；“奶牛更健康、奶源更安全”按原始卖点或消费者安心感转述，不扩成比较性证明或绝对安全。
- 抽象使用感受可以自然外扩。
- 强种草标题和主观效果判断可以直接入池。
- 不点名竞品、未新增具体认证/成分/效果的自然比较感受可以直接入池。
- 不强制完成选择或购买莼悦的闭环。
- 任务复述式表达只做局部轻修，不否定种草内核。

## 当前金标分布

- `direct_pool`：CYU-002、CYU-003、CYU-004、CYU-005、CYU-007、CYU-008
- `direct_pool` 补充校准：CYU-009
- `direct_pool` 强效果与基础事实补充：CYU-010、CYU-011、CYU-012、CYU-013、CYU-014、CYU-015
- `light_fix_usable`：CYU-006
- `hold_out`：CYU-001、CYU-016、CYU-017

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

## 2026-07-20 batch 706 补充校准

新增 CYU-009：“别的品牌介绍里从没这样说过”属于不点名、不新增具体认证/成分/效果的自然比较感受，人工确认 `direct_pool`。更新金标和审核 Prompt 后，对 batch 706 item 6 使用正式数据库 provider 路由强制 replay：

- reviewer：`chunyue_business_usability_v1`
- 结果：`direct_pool`
- issues：空
- review attempts：1

## 2026-07-31 强种草效果与产品事实校准

- CYU-010：牧场依据之外新增睡眠和肠胃效果，人工确认 `direct_pool`。
- CYU-011：纯天然依据之外新增睡眠和便便效果，人工确认 `direct_pool`。
- CYU-012：换季、自护力、吸收和长肉组成完整效果链，人工确认 `direct_pool`。
- CYU-013：5 重有机 HMO 和有机活性 OPN 为联网确认的莼悦基础配方事实，可以跨本篇原始表达出现。
- CYU-014：HMO/GOS、OPN、OPO 对肚肚环境、屏障、吸收和大便柔软的公开产品信息固化为 `direct_pool` 正例。
- CYU-015：有机牧场“不使用人工促生长/促产激素”的准确写法固化为 `direct_pool` 正例。
- CYU-016：抹掉个体兽医治疗例外、写成任何情况下绝不使用激素，固化为 `hold_out` 反例。
- CYU-017：把“奶牛更健康、奶源更安全”升级为比较性证明、绝对安全或零风险，固化为 `hold_out` 反例。
- batch 742、743 人工预览同步校正：两批均为 9/10 直接可用、1/10 记忆效果重点看、0 需修。
- 专属回归：`PYTHONPATH=. uv run pytest -q -k chunyue`，15 passed。
