---
name: comment-angle-corpus-writer
description: Generate, normalize, or review Chinese 评论切角 corpus entries for brand content generation when operators fill one free-form prompt block by imitating examples. Use when creating new 评论切角语料, turning运营业务规则 into a ready-to-import CSV row, checking whether a 评论切角 block is template-worthy, adding真人感 examples, or keeping the rule simple enough for运营 to copy.
---

# Comment Angle Corpus Writer

## Purpose

Help operators write one free-form `语料` block for a `评论切角` without forcing them to fill many structured fields. Keep the format easy to imitate while making it useful for generation: clear identity, loose boundary, real-feeling examples, and one light caution.

This skill is for **writing or normalizing new corpus blocks**. For fixing existing blocks that are too strict, homogeneous, or AI-like, use `prompt-corpus-loosener` as a companion.

## Default Output Shape

Each `语料` block should look like this:

```text
子方向标题：

像……。语气……。可以……，但别……。

示例：
- 真人感示例1
- 真人感示例2
- 真人感示例3
- 真人感示例4
- 真人感示例5

注意：示例只作为语义素材，不是正文原句，生成时换一种自然说法。
可以补一句“别都写成什么”。
```

Keep the actual CSV simple: usually only `评论切角` and `语料` are needed. Do not introduce extra columns unless the user asks.

## Workflow

1. Inspect examples first.
   - If the task references existing files, read nearby rows from files such as `评论切角_子关键词导出.csv`, `源悦种草活动-ai训练规则-评论切角.csv`, and `源悦-评论 - 评论训练模型.csv`.
   - Use existing good rows as the operator-facing template.

2. Search public real-user wording before writing when真人感 matters.
   - When the user asks to generate, diversify, or improve a 评论切角, do one web search pass unless they explicitly say not to.
   - Prefer public searchable sources: 妈妈网、宝宝树、亲宝宝、育儿问答、电商问答、公开评论/问答 pages.
   - Query shape: `宝宝 + 奶粉 + 切角关键词 + 问答/宝妈/评论/真实反馈`.
   - Do not scrape or quote Xiaohongshu directly; only abstract interaction tone such as `蹲蹲`, `求反馈`, `有同款吗`, `找到了踢我`, `宝妈群里也有人说`.
   - Use authority/medical pages only to add observation dimensions, not as真人语料.
   - Summarize patterns; do not paste long third-party text into the corpus.

3. Preserve the operator-friendly one-block format.
   - Do not ask运营 to split fields like audience, boundary, example, and compliance unless the user asks.
   - Write one paragraph of guidance, then examples, then a short note.
   - If a切角 naturally has multiple directions, keep the same `评论切角` value and create multiple rows with different titles.

4. Keep the rule loose.
   - Prefer `像在聊...`, `可以带...`, `语气像...`, `别都...`.
   - Avoid `必须`, `只写`, `生成重点必须`, `可写方向`, `固定数字`, long checklists, and hard route-setting.
   - Keep compliance boundaries, but write them lightly.

5. Make examples真人感.
   - Examples should sound like comments, not brand copy.
   - Prefer small life details, hesitation, casual openings, imperfect grammar, and short questions.
   - Use 5-8 examples for most rows. Too few makes generation narrow; too many makes the block hard for operators to imitate.

6. Check boundary overlap.
   - If multiple rows share the same `评论切角`, each title needs a different generation entrance.
   - Example split:
     - `整体适应`: broad first-impression observation.
     - `拍嗝吐奶`: milk coming back up, burping, holding upright.
     - `肚肚状态`: twisting, fussing, bloating, sleeping after milk.
   - Do not create several rows that all ask the same thing with synonyms.

## Operator Template Guidance

When explaining the template to运营, keep it simple:

- `标题`: 写清这个子方向在聊什么。
- `一句松规则`: 像谁在什么场景下说话，语气怎样，可以聊什么，别写成什么。
- `示例`: 放真人感句子，越像评论区越好。
- `注意`: 固定保留“示例只作为语义素材，不是正文原句”。

Do not make运营 fill a complex form at the beginning. Let them imitate a good block first; technical checks can happen after import.

## Quality Checklist

Before finishing, check:

- The CSV parses if you edited a CSV.
- Each row has `评论切角` and `语料`.
- The block contains a title, guidance, examples, and a note.
- Examples are not all the same sentence pattern.
- The rule is loose enough for generation diversity.
- 已购/未购身份 is consistent.
- Product claims are not too certain, especially for过敏、生病、消化、长高长肉.
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
print("ok" if all(r.get("评论切角") and r.get("语料") for r in rows) else "bad")
PY
```
