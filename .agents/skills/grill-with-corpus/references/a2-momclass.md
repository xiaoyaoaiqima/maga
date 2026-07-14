# A2 Momclass Corpus Grilling Reference

Use this reference when working on A2 妈妈班/月子中心 UGC posts in `/Users/luxifa/maga`.

## Current Evidence Anchors

Primary local files:

- `关键词语料/a2妈妈班活动demo母池.csv`
- `关键词语料/a2妈妈班活动demo母池_概要切片.csv`
- `关键词语料/a2妈妈班叙事结构槽位_20260705.csv`
- `关键词语料/a2妈妈班产品卖点槽位_20260703.csv`
- `关键词语料/a2妈妈班待产包礼遇多样表达槽位_20260705.csv`
- `outputs/a2_mom_class_ugc_20260705/a2_store_momclass_eventchain_ab_variant_10_deepseek_preview.md`

Useful scripts:

- `.local/archive/content-generation-scripts/20260704_ugc_ppl_script_cleanup/scripts/run_a2_store_momclass_one_by_one.py`
- `.local/archive/content-generation-scripts/20260704_ugc_ppl_script_cleanup/scripts/audit_a2_store_momclass_realness.py`

## Known Baselines

As of the 2026-07-05 experiment:

- Downloads mother pool `a2妈妈班_月子中心活动 AI训练 - a2妈妈班活动母池.csv`:真人感均分 73.3 under current audit.
- Local mixed mother pool `关键词语料/a2妈妈班活动demo母池.csv`:真人感均分 63.8 under current audit.
- slot baseline 10-item generation:真人感均分 60.2.
- event-chain v1 10-item generation:真人感均分 85.6.
- event-chain v2 with extra micro-rules regressed to 56.
- numbered 8-beat event-chain v3 regressed to 69.9 and felt like task-step replay.

Interpretation: event-chain v1 is the current best prompt mode, but the next quality lift should come from plan/corpus slot quality, not more prompt bans.

## Business Anchors

Mom stage:

- Only pregnant/waiting states: 孕晚期、待产、临近预产期、备产、二胎待产.
- Do not write already born, postpartum, sitting the month, or the writer's baby already using/transferring formula.

Must naturally appear:

- 妈妈班
- 待产包/新客礼盒/新生儿奶粉 at least one, depending on title/body
- a2/a2至初 product benefit
- detection/report/can-code/batch report
- first milk / first can quality logic

Key causality:

- A2蛋白/母R同型 supports 小肚肚适应、亲和、好吸收.
- 品质安心 must be supported by detection report, can-code, batch traceability, milk source, clean formula, production clarity, or similar evidence.
- Gift/maternity bag supports现场收获、喜欢、实用、清单对照; it must not be the reason for品质安心.

## Current Seeding Standard

For this A2 妈妈班生文需求,种草性优先级高于极致软真人感.

Strict usable can include posts that clearly say:

- 第一罐会考虑 a2 至初
- 把 a2 至初放进第一罐备选
- 对 a2 至初好感上来, 会重点看看
- 新生儿第一口奶更倾向 a2 至初

Do not reject an item only because the seed is stronger than ordinary diary-style UGC. It should be rejected only when the stronger seed breaks the story, sounds like an ad slogan, uses unsupported causality, or violates business boundaries.

Required support for strong seed:

- The mother has a real reason to care about first milk / first can.
- a2/a2至初 appears through the momclass, teacher, staff, display, or can-code/report action.
- Product benefit must bind to a2/a2至初 in the same sentence or immediate nearby context. Do not let "A2蛋白/母R同型" float as a generic classroom fact and only reveal a2 later from the gift.
- Product benefit matches the pain.
- 品质安心 is supported by detection/report/can-code/milk source/clean formula/production clarity.
- Gift/maternity bag does not carry the final trust argument by itself.

Placement rule:

- Use **evidence-after strong close** as the default.
- The strong seed sentence should appear right after product benefit + detection/report/can-code evidence.
- It can say 第一罐会考虑a2至初 / 放进第一罐备选 / 更倾向a2至初.
- If the post later writes待产包/新客礼盒, that礼遇段 should only be现场收获、喜欢、实用、清单对照, not another selection conclusion.
- Avoid ending with strong seed immediately after gift/maternity bag unless the sentence explicitly returns to report/can-code/product evidence.
- If the gift/maternity bag only says it has 新生儿奶粉, it cannot carry 对a2好感/选择a2. To support a2 attitude, the sentence must either say the gift contains a2至初 or return to product/report evidence.

## Failure Patterns To Grill

Ask which layer owns the fix:

- Product benefit and detection appear as two adjacent facts with no bridge.
- Pain appears immediately after seeing a display/can/gift, without a prior doing-homework/list/first-can-not-set/secondhand-worry setup.
- A real-life detail appears, then has no consequence.
- Gift/maternity bag says "happy/like" without a reason such as looking good, checklist reference, useful for preparation, or saving a new mom effort.
- Gift appears at the end and then the post suddenly makes a new selection conclusion.
- Gift says only generic 新生儿奶粉, then the post claims 对a2好感 or 第一罐考虑a2.
- A2蛋白/母R同型 is mentioned without nearby a2/a2至初, then a2 is revealed later through the gift.
- After 散场/课后/结束, the post jumps back to "老师还提到/老师说" as if the class timeline rewound.
- Phrases like "罐底码就能对应" or "品质心里踏实了" are incomplete/not fluent and should be rejected, not treated as harmless口语.
- Strong first-can close says "第一次好好选/不用折腾转奶" but does not explicitly target a2至初 or return to report/product evidence.
- Standalone soft closes like "对a2好感上来了，这个点记住了" are not enough; close must attach to recent evidence or a concrete action.
- Do not rewrite 母R同型 into 妈妈天生同型 / 母亲同型 / 母体同型. Keep 母R.
- Titles containing 顺手 or hard separators like "｜" are not acceptable for strict strong-seed output.
- Title hard-piles keywords.
- Plan combines incompatible pain and benefit.
- Prompt contains so many safeguards that the model writes a checklist or returns empty.
- Audit punishes strong but business-useful seed.

## High-Leverage Questions

Use one at a time:

- When a post is smooth but strongly seeded, should it pass, or should seed strength be capped?
- Should the gift be an entry hook, a middle prop, or a final收获 in this item?
- Is the mother's main reason to post learning, relief, surprise, or decision narrowing?
- Which evidence actually earns品质安心 in this item: report, milk source, clean formula, or batch traceability?
- Does the pain belong to the writer herself, a secondhand worry, or the现场 question?
- If the product were removed, would the post still have a reason to exist?
- If the gift were removed, would the post still have a reason to exist?
- Is this a plan-slot problem, corpus-slot problem, prompt problem, audit problem, or post-filter problem?

## Output Discipline

For A2 momclass experiments:

- Use small tests, usually 10 items.
- Do not backfill usable items unless asked.
- Export preview Markdown and a sampled complete rendered prompt when generation happens.
- Strict usable CSV should include only human-approved usable items.
- `context_list` and `维度` should not be exported for this A2 momclass scene.
- First CSV column should remain `batch_id`.
