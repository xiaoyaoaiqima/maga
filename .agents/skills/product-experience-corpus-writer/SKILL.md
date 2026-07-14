---
name: product-experience-corpus-writer
description: Generate, normalize, or review Chinese 产品使用体验 corpus entries for long-form brand content generation. Use when working on 产品使用体验_子关键词导出.csv, 生文业务规则, month-age/use-duration/topic rules, operator-filled one-block product experience prompts, or checking whether product-experience rules are usable as templates for运营.
---

# Product Experience Corpus Writer

## Purpose

Help operators write one free-form `语料` block for `产品使用体验` long-form generation. Keep the operator workflow simple: they imitate a good example and fill one block, while the technical side later handles personas, perturbation rules, content structure, generation instruction, diversity, and QA.

This skill is for **business-rule corpus** such as `产品使用体验_子关键词导出.csv`. For short comment-angle rules, use `comment-angle-corpus-writer`. For loosening existing strict or homogeneous rules, use `prompt-corpus-loosener` as a companion.

## Core Model

`产品使用体验` is a 3-part business key:

```text
月龄，使用时间，体验主题
```

Example:

```text
0-6个月，3个月内，奶量补充
7-12个月，3-6个月，消化吸收
1-3岁，6个月以上，过敏相关
```

The `语料` block then describes how this business key should be written in long-form content.

## Default Output Shape

```text
## 产品使用体验

你宝宝的月龄：XX。
喝源悦时间：XX。
本文围绕XX相关体验来写。

提示：
- 像在聊XX月龄宝宝的XX体验，语气像真实妈妈分享，不要写成品牌介绍。
- 使用时间可以自然带到XX，但不要和当前时间范围冲突，也别每篇同一种说法。
- 可以从A、B、C这些生活细节里带出体验。
- 表达收着点，别写成承诺、治疗、保证或夸张功效。
- 行为和细节注意符合当前宝宝月龄。

可参考素材：
- 真人感素材1
- 真人感素材2
- 真人感素材3

注意：参考素材只提供语义方向，生成时换一种自然说法。
```

Keep CSV fields simple: usually only `产品使用体验` and `语料`.

## Workflow

1. Inspect nearby examples first.
   - Read rows from `产品使用体验_子关键词导出.csv` when available.
   - Preserve the current one-block format: title, fixed baby info lines, `提示`, `可参考素材`, `注意`.

2. Search public real-user wording when真人感 matters.
   - When generating or improving a product-experience rule, do one web search pass unless the user explicitly says not to.
   - Prefer public searchable sources: 妈妈网、宝宝树、亲宝宝、育儿问答、电商问答、公开评论/问答 pages.
   - Query shape: `宝宝 + 奶粉 + 体验主题 + 月龄/使用时间 + 宝妈/真实反馈/问答`.
   - Do not scrape Xiaohongshu directly; abstract interaction tone only.
   - Use medical/authority pages only for observation dimensions and safety boundaries, not as真人素材.
   - Summarize patterns; do not paste long third-party text.

3. Preserve operator simplicity.
   - Do not ask运营 to fill many fields at the beginning.
   - Let them imitate the block and write one `语料` cell.
   - Technical-side QA can later check format, diversity, compliance, and conflicts.

4. Run the business-rule technical check before import.
   - Treat the operator's block as a draft, not final system prompt.
   - First do structural checks: key format, section completeness, age/use-duration conflicts, missing素材, hard-rule words, and compliance risks.
   - Then do a真人感补强 pass: search public real-user wording for the same topic and age/use-duration context; extract only patterns, openings, scenes, and concrete details.
   - Then let AI revise the prompt block: loosen rigid instructions, replace summary-like AI phrasing with concrete life details, add or swap reference material, and split highly overloaded rules if needed.
   - Keep the original business intent. AI may polish, loosen, and diversify, but should not invent new claims or change the brand's required boundary.
   - Only after this pass should the corpus be imported into the generation system.

5. Keep business rules separate from technical diversity.
   - Business rule says: what topic, baby stage, use duration, lived details, claim boundary.
   - Technical strategy says: persona, perturbation rules, content structure, title style, generation instruction, tone variation.
   - Do not overload `产品使用体验` with full article outlines.
   - For post-generation product-experience work, keep the business rule focused on user motive and the product's core selling point. Do not keep adding one-off fixes such as odd phrases, dangling fragments, product-form mistakes, or generic AI endings into the operator-facing rule; route those to backend guard, deterministic cleanup, or at most one narrow rewrite pass.
   - Preserve strong real-user expressions by default when they sound like actual user wording. Do not ban phrases such as `少跑医院`, `不生病`, `体质稳`, or `自己扛得住` unless the user explicitly asks; judge them by batch frequency and context instead of treating them as automatic risk words.

6. Respect baby stage and use duration.
   - `0-6个月`: avoid behaviors for older babies; focus on milk, burping, sleep, diaper, holding, early feeding.
   - `7-12个月`: can include crawling, sitting, teething,辅食, more activity, sleep rhythm.
   - `1-3岁`: can include meals, walking/running, daycare-like routines, stronger preferences.
   - `3个月内`: use `刚喝一阵`, `不到两个月`, `刚换`.
   - `3-6个月`: use `3个多月`, `4个月左右`, `快小半年`.
   - `6个月以上`: use `一直喝`, `喝了大半年`, `从之前喝到现在`, while avoiding conflicts with baby age.

7. Keep prompt language loose.
   - Prefer `像在聊...`, `可以从...里带出`, `别每篇都...`.
   - Avoid `必须`, `只写`, `生成重点必须`, `固定数字`, and rigid article routes.
   - Keep compliance boundaries lightly but clearly.

8. Make reference material useful.
   - Use 3-5 `可参考素材` snippets for most rows.
   - Materials should be long-form-ish, with lived detail and a natural mom voice.
   - They are semantic material, not copyable output.
   - Avoid all materials having the same structure such as `之前X，喝了Y，现在Z`.

## Theme Guidance

- `奶量补充`: milk amount, feeding tug-of-war, leftover bottle, willingness to drink, parent anxiety. Avoid every article using exact ml changes.
- `生长发育`: body shape, weight, clothes fit, baby checkup, holding weight, growth curve. Avoid exaggerated growth claims.
- `容易生病`: daily state, season changes, feeding/sleep/activity steadiness. Avoid prevention, treatment, or “less sick” promises.
- `消化吸收`: belly state, burping, spit-up, poop, post-feed comfort. Avoid diagnosis or treatment wording.
- `便便问题`: poop rhythm, softness, color, effort, diaper-checking anxiety. Avoid professional diagnosis or drug-like effect.
- `过敏相关`: sensitive baby context, cautious milk choice, small-can trial, formula checking, daily observation. Avoid anti-allergy, treatment, test conclusions, or guaranteed results.

## Quality Checklist

Before finishing:

- CSV parses if a CSV was edited.
- Each row has `产品使用体验` and `语料`.
- The key has `月龄，使用时间，体验主题`.
- The block includes baby age, use duration, theme sentence, `提示`, `可参考素材`, and `注意`.
- Use duration does not conflict with baby age.
- Baby behaviors fit the age range.
- Rule is not a full article outline.
- Reference materials are varied and真人感.
- 网络真人感 patterns were considered when the task is generation, diversification, or AI味修正.
- AI revision preserved运营业务意图 while reducing rigid rules and homogeneous phrasing.
- Claims are cautious for growth, allergy, sickness, digestion, and poop.
- If web search was used, mention source types or query directions in the response.

## Validation Snippet

```bash
python3 - <<'PY'
import csv, io
p = "PATH_TO_CSV"
with open(p, "r", encoding="utf-8-sig") as f:
    content = "".join(line for line in f if not line.startswith("#"))
rows = list(csv.DictReader(io.StringIO(content)))
print("rows", len(rows))
print("ok" if all(r.get("产品使用体验") and r.get("语料") for r in rows) else "bad")
PY
```
