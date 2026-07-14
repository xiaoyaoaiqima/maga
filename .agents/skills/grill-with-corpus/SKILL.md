---
name: grill-with-corpus
description: >
  Use when the user wants to sharpen a content-generation plan, improve UGC
  真人感/种草性/high-score output, debug why generated posts feel modular or
  AI-like, or decide next experiments from mother pools, generated batches,
  audits, and feedback. This is a corpus-grounded grilling loop: inspect local
  evidence first, ask one hard question at a time only when files cannot answer
  it, then update the experiment plan or corpus rules.
---

# Grill With Corpus

Use this skill for content-generation quality work where the goal is not just to produce more text, but to make outputs more真人, more naturally种草, and less modular.

## Core Rule

Do not start by writing a new prompt or generating a new batch.

First inspect evidence:

- mother pool / demo pool
- generated CSV / preview Markdown
- rendered prompts
- audit JSON
- business feedback files
- local corpus slots or rules

Then ask the user exactly one high-leverage question only if the answer cannot be inferred from those files.

## Loop

1. **Evidence Pass**
   Find the relevant corpus and generated artifacts. Compare high-score and low-score examples. Name concrete failure patterns with item numbers or row references.

2. **Boundary Question**
   Ask one question that changes the decision tree. Avoid broad questions like "do you want it more real?" Prefer questions like "should strong seed be allowed when the story spine is smooth, or should it stay soft even if conversion weakens?"

3. **Decision Record**
   Convert the answer into a reusable rule:
   - scope
   - allowed pattern
   - risky pattern
   - examples
   - where it should live: plan slot, corpus slot, prompt, audit, or post-filter

4. **Small Experiment**
   Run a small batch, usually 10 items. Do not backfill unless asked. Produce preview Markdown and one sampled rendered prompt when generation happens.

5. **Compare Against Baselines**
   Compare against mother pool and previous generated batches using both machine metrics and human judgment. Do not over-trust one score.

## Question Discipline

- Ask one question at a time.
- If local files can answer it, do not ask; inspect first.
- Prefer adversarial questions that expose tradeoffs.
- Do not flatter the current plan.
- If a proposed fix adds complexity, ask what failure it prevents.

## Common Layer Decisions

- **Plan slot**: use when the issue is wrong story logic, incompatible pain/benefit pairing, bad scene order, or missing event cause.
- **Corpus slot**: use when the issue is expression diversity, reusable real-life wording, title patterns, or gift/report phrasing.
- **Prompt**: use only for global writing posture and hard constraints. Avoid piling micro-rules into prompt.
- **Audit**: use when a bad pattern is objectively detectable, or when the audit is wrongly punishing useful seed.
- **Post-filter**: use for hard risk removal, not for making prose more human.

## A2 Momclass Reference

For A2 门店妈妈班/月子中心 style UGC work, read `references/a2-momclass.md`.
