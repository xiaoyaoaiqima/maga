---
name: prompt-corpus-loosener
description: Loosen and revise Chinese prompt corpus or sub-keyword CSV entries for content-generation training. Use when working on files such as 子关键词导出.csv, 评论切角语料, 产品使用体验语料, prompt examples, comment-angle corpora, or any task asking to reduce homogeneity, make rules less strict, preserve 真人感 examples, split long prompt entries under the same enum, search public real-user wording, or diagnose why generated copy is too templated.
---

# Prompt Corpus Loosener

## Purpose

Revise prompt-corpus entries so they guide tone and boundaries without forcing a single generation path. Preserve real examples as the voice source; loosen instructions that make the model produce formulaic, homogeneous text.

## Workflow

1. Inspect the source file before editing.
   - For CSV exports with comment prefaces, skip leading `#` lines and parse with `csv.DictReader`.
   - Identify columns such as `评论切角`, `语料`, `评论示例`, `评论补充`, `子关键词`, or similar.
   - Confirm row count and that every edited row still parses after changes.

2. Separate real examples from rules.
   - Treat `评论示例` / `评论补充` / existing bullet examples as the source of 真人感.
   - Preserve reference examples whenever possible. When the user wants more diversity, first add or broaden examples as horizontal expansion, rather than adding many explanatory rule bullets.
   - Do not invent examples unless the user explicitly asks.
   - If examples are sparse, say so and prefer loosening boundaries over fabricating a new corpus.

3. Search public real-user wording before rewriting when the issue is 真人感.
   - When the user says `多样化`, `同质化`, `这个切角太像 AI`, `不真人`, or asks to loosen a prompt because generation is too templated, do one web search pass before editing.
   - Prefer public, searchable sources and summarize patterns instead of copying text verbatim:
     - 母婴社区问答: 妈妈网、宝宝树、亲宝宝、育儿问答类页面。
     - 电商问答语气: 京东问大家、淘宝/天猫问答、商品评论区里公开可搜索的内容。
     - Search query shape: `宝宝 + 奶粉 + 切角关键词 + 问答/宝妈/评论/真实反馈`.
     - 小红书风格词: do not scrape Xiaohongshu content directly; only abstract public interaction tone such as `蹲蹲`, `求反馈`, `有同款吗`, `宝妈群里也有人说`.
     - 权威/科普资料: use only to add observation dimensions such as 生长曲线、喂养量、转奶观察点; never treat it as 真人语料.
   - Convert search findings into a small pattern note: common openings, question shapes, hesitation markers, casual endings, and words to avoid. Then revise the corpus using those patterns.
   - Keep provenance at the level of source type / query / pattern. Do not paste large chunks of third-party user content into the corpus.

4. Diagnose over-constrained rules.
   - Flag words and structures such as `只写`, `必须`, `生成重点必须`, `主线必须`, `可写方向`, `数字按`, `同一批`, `禁止照搬`, `固定数字`, long enumerated paths, and repeated `不要...`.
   - These are not always wrong, but too many in one entry make the model execute a checklist instead of imitating real comments.
   - Anti-copying and compliance constraints such as `禁止照搬`, `固定数字`, brand/legal red lines, 月龄/周期/痛点 boundaries, and 未购/已购 identity consistency are retention candidates. Compress their wording if needed, but do not delete them just to make the corpus looser.

5. Loosen without losing the boundary.
   - Replace hard route-setting with soft scene-setting:
     - `只写...` -> `像在聊...`, `偏向...`, `主要像...`
     - `必须落在...` -> `整体像在聊...`
     - `可写方向:` lists -> delete or compress into one loose sentence.
     - `数字按月龄规则走...` -> `可以带一点数字，但别每条都写成“从X到Y”。`
     - `禁止照搬原句、固定数字...` -> `示例只作为语义素材，不是正文原句，生成时换一种自然说法。`
   - Keep safety or compliance boundaries when needed, but write them lightly.
   - Preserve real strong expressions when they sound like actual user wording. Do not automatically replace phrases such as `小感冒都没沾上`, `这学期没怎么请假`, or `第二天照样往外跑` with over-safe abstract wording like `没有动不动就掉状态`; that kind of replacement often creates AI味. Only press down expressions that become explicit guarantees, medical claims, or brand promises such as `喝了就不感冒`, `预防感冒`, or `保证不中招`.
   - Do not solve every new weird generated phrase by thickening the corpus rule. If the issue is a dangling fragment, product-form mistake, generic AI ending, or other one-off artifact, prefer backend guard/deterministic cleanup/one narrow rewrite pass. Change the corpus only when the same pattern repeats across a batch.

6. Split long entries under the same enum when useful.
   - Do not create new enum values unless the user allows it.
   - If one enum has multiple natural sub-modes, keep the same first-column key and create two shorter `语料` rows with distinct titles.
   - Example: same `已购，品牌忠实老客，生长发育`, two rows titled `体感外观` and `身高体重`.

7. Preserve diversity signals.
   - Examples are the preferred scaling unit for diversity: like adding machines for more capacity, add varied reference examples before adding heavier instructions.
   - Keep a few light “cross-topic” real examples when they add life, but place them as auxiliary examples rather than making them the main rule.
   - Avoid telling the model exactly how to combine factors, such as `价格 + 宝宝爱喝 + 值了`.
   - Prefer “别都挤在...” over strict batch-level instructions.

## Editing Style

- Keep entries short: title, one or two loose boundary sentences, examples, one light note.
- Preserve original Chinese tone, punctuation, and real examples where possible.
- Prefer editing existing rows over creating new files.
- Use structured CSV parsing for inspection; use careful patches for edits.

## Validation

After editing:

```bash
python3 - <<'PY'
import csv, io
p = "PATH_TO_CSV"
with open(p, "r", encoding="utf-8-sig") as f:
    content = "".join(line for line in f if not line.startswith("#"))
rows = list(csv.DictReader(io.StringIO(content)))
print("rows", len(rows))
for i, r in enumerate(rows, 1):
    if not any(r.values()):
        print("empty row", i)
PY
```

Also scan for remaining hard-rule words:

```bash
rg -n "必须|可写方向|同一批|数字按|生成重点|主线|只写|禁止照搬|固定数字" PATH_TO_CSV
```

Remaining matches are acceptable only when intentionally kept.
