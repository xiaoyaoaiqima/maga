---
name: maga-wangyue-batch-delivery
description: "Use for MAGA/Wangyue article batch generation or training tasks, especially when the user asks to 产20篇, 跑一批, 训练, run batch, 看效果, 导出预览, or inspect generated UGC posts. Enforces the required delivery format: a batch preview Markdown with machine and human usability metrics plus one randomly sampled complete rendered generation prompt."
---

# MAGA Wangyue Batch Delivery

## Core Rule

When running or reviewing a MAGA/Wangyue article batch, always deliver two artifacts:

1. A generation preview Markdown.
2. One randomly sampled complete rendered generation prompt Markdown.

Do not give only JSON or only a prose summary. If a batch was already run in the current turn, use that batch. If not, run the requested batch first.

## Production Count Policy

When the user requests a production quantity such as `生产150篇`, interpret it as `start 150 generation attempts`, not `keep generating until 150 final usable articles exist`.

Do not auto-backfill failed or unusable items unless the user explicitly asks to supplement usable output. Repeated backfilling slows production too much.

Reports must separate:

- requested/attempted generation count
- raw generated count
- machine final pass count
- human/business usable count
- failed or needs-fix count

## Preview Markdown Requirements

Create a Markdown file under the current Wangyue output directory when available, usually:

`/Users/luxifa/maga/outputs/0705_wangyue_product_relation_evidence/`

The preview is for human business review first, not for dumping the full machine report. Keep it compact and scannable. Put detailed machine fields, traces, full JSON, and complete rendered prompts in separate debug artifacts and link to them from the preview.

Every item section must start with a visible review marker so long previews are easy to scan:

- `💣` means needs-fix / not directly usable.
- `⚠️` means重点看; not necessarily wrong, but requires human business review.
- `👀` means观察; light watch item, high-frequency phrase, or minor risk.
- `✅` means usable by current human/business judgment.
- `⛔` means generation failed or no usable article body was produced.
- `🧪` means draft/candidate test output that has not been imported into the active asset.

Include a short legend near the top of the preview:

`标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试`

Use the marker in the heading itself, for example:

`### 💣 item 16｜需修｜标题`

The compact preview Markdown must use this order:

1. **Conclusion**: one short decision line, e.g. `不建议直接转正，但方向有效`.
2. **Key Metrics**: only the numbers needed to decide whether to keep iterating:
   - generated / failed
   - machine final pass
   - forbidden hits
   - max pairwise similarity and similarity warning count
   - human usable / watch / needs-fix item numbers
   - phrase guard or LLM review issue item numbers only when non-empty
3. **Candidate Change**: show only the changed `这篇要写的事` block or the smallest relevant corpus diff. Do not paste the full prompt here.
4. **重点看**: put `💣` and `⚠️` items first, each with title, one-line issue, and full body.
5. **其他产出**: show remaining `✅` or `👀` items with title and full body. Omit repeated machine status lines when all are identical.
6. **调试信息**: put `batch_id`, `draft_id`, JSON report path, response path, and rendered prompt path at the end.

Do not repeat these fields on every item when they are the same across the batch:

- `final_pass=True`
- `rewrite_required=False`
- full rule name like `V3M-15｜成长营养｜求助后回访｜成长发育需求`
- `无明显机器问题`
- internal JSON field names unless they explain a real review decision

Translate confusing internal field names into human-facing language. For example, do not expose `hard_pass` without explaining whether it means final machine pass in the local report.

## Human Judgment Policy

Separate machine audit status from human business usability.

Do not mark an item unusable only because it has:

- strong seeding
- a full decision chain
- multiple positive effect proofs
- product benefits stated directly

These are allowed for Wangyue business goals if product facts are correct and the post type supports the product presence.

Still mark as needs-fix when there is:

- product fact error
- under-3 or low-age usage chain
- child self-brewing or child operating formula
- portable/sachet/side-bag/water-bottle product form error
- seasonal or disease-environment anchor such as 换季, 流感, 春游, 秋游, 中招季
- ingredient-benefit mismatch, especially protection ingredients tied to body growth
- medical/treatment/doctor/guarantee language
- hidden negative such as price negativity
- obvious AI/brief translation tone or formulaic ad closure

For `brief_translation_tone`, distinguish:

- concrete ingredient plain speech is usually OK: `钙铁锌看着挺全`, `DHA和燕窝酸写得清楚`, `乳铁蛋白和HMO我看了一眼`
- abstract business-summary speech is risky: `这个方向我会看`, `这个点值得关注`, `保护力这块我比较在意`, `日常口粮里多留意这一块`

## Random Rendered Prompt Requirement

Also export one randomly sampled complete rendered generation prompt from the same batch.

The prompt artifact must:

- be a separate `.md` file
- include `batch_id`, `item_no`, and title if available
- contain the complete rendered generation prompt, not a summary
- preserve prompt section order and wording

Prefer sampling from a generated item that is representative of the batch. If the user asks for a specific item, use that item instead of random.

## Final Response

After finishing, reply with concise links:

- preview Markdown path
- sampled prompt Markdown path
- batch_id
- the key metrics: direct pass, post-rewrite pass, machine final pass, human usable, human needs-fix

Mention tests or service restarts only if they were run.
