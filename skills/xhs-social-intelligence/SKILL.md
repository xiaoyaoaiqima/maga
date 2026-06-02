---
name: xhs-social-intelligence
description: 小红书/XHS 舆情与真人语料工作流 Skill。用于用户要求采集小红书笔记/评论、按关键词或战场爬取评论、拉取帖子正文/tag、做 A2/奶粉评论或帖子情感分析、生成关键词 TopN 情感评分、月度正负向趋势、突发负向舆情报告、沉淀真实评论/真人感语料时。
---

# 小红书舆情与真人语料工作流

这个 Skill 复用 MAGA 仓库现有脚本，不重写爬虫或情感逻辑。默认在 MAGA 仓库根目录执行命令；如果当前不在仓库根目录，先定位或让用户设置 `MAGA_REPO_ROOT`。

## 先判断任务类型

- 只采帖子列表：用 `crawl_xhs_notes.mjs`。
- 采评论：优先用 `crawl_xhs_note_details_comments.mjs`，它能把帖子详情字段重复到评论行；只要轻量评论表时才用 `crawl_xhs_comments.mjs`。
- 做 LLM 情感标注：评论用 `llm_comment_sentiment.py`，帖子用 `llm_note_sentiment.py`。
- 做规则/词库型汇总报告：用 `scripts/analyze_xhs_comments.mjs`。
- 做关键词 TopN 情感分：用 `scripts/score_xhs_keyword_topn_sentiment.mjs`。
- 做帖子或战场月度趋势：用 `scripts/analyze_xhs_post_monthly_sentiment.mjs` 或 `scripts/analyze_xhs_monthly_sentiment_by_battle.mjs`。
- 看突发负向舆情：用 `scripts/analyze_xhs_event_negative_trend.mjs`。
- 拉帖子正文/tag：用 `scripts/extract_xhs_note_tags.mjs`。

如果用户要大规模爬取但没给范围，先确认关键词/战场、每词帖子数、是否抓子评论、是否断点续跑；小样本调试可以直接用默认 test 模式。

## 鉴权与环境

采集脚本需要 TikHub 鉴权，读取 MAGA 仓库 `.env` 或环境变量：

```bash
TIKHUB_AUTHORIZATION="Bearer <token>"
TIKHUB_BEARER_TOKEN="<token>"
TIKHUB_TOKEN="<token>"
```

LLM 情感脚本需要 OpenAI-compatible API：

```bash
LLM_API_KEY=...
LLM_API_BASE=https://.../v1
LLM_MODEL=deepseek-v4-flash
```

不要在回复里泄露 token。网络或模型调用失败时，保留失败摘要、输出文件和 resume 命令。

## 常用采集命令

单关键词帖子列表：

```bash
node crawl_xhs_notes.mjs \
  --keyword "a2至初" \
  --limit 100 \
  --max-pages 5 \
  --output local_data/xhs_runs/a2_notes.csv
```

单关键词评论+帖子详情，适合后续情感和语料：

```bash
node crawl_xhs_note_details_comments.mjs \
  --keyword "a2至初" \
  --full \
  --limit 100 \
  --fast \
  --detail-comment-limit 20 \
  --concurrency 2 \
  --resume \
  --output local_data/xhs_runs/a2_detail_comments.csv
```

从关键词 Excel 按战场批量采集：

```bash
node crawl_xhs_note_details_comments.mjs \
  --excel "小红书完整词包_综合排序_强意图降权版.xlsx" \
  --sheet "调整后综合排序" \
  --battle-category "转奶争夺战场" \
  --keyword-limit 20 \
  --full \
  --limit 200 \
  --fast \
  --resume \
  --output "xhs_转奶争夺战场_top20x200_fast_comments.csv"
```

采子评论时加：

```bash
--include-sub-comments --max-sub-comment-pages-per-root 1
```

断点/进度：

```bash
node crawl_xhs_note_details_comments.mjs --output <output.csv> --print-progress
node crawl_xhs_note_details_comments.mjs --output <output.csv> --resume
```

## LLM 情感标注

评论输入必须包含：

```text
comment_type,parent_comment_id,comment_id,comment_text
```

评论标注：

```bash
python3 llm_comment_sentiment.py input_comments.csv \
  -o local_data/xhs_runs/comments_sentiment.csv \
  --label-mode ternary \
  --batch-size 50 \
  --concurrency 8 \
  --resume
```

帖子输入必须包含：

```text
note_id,note_desc
```

帖子标注会按 `note_id` 去重：

```bash
python3 llm_note_sentiment.py input_posts.csv \
  -o local_data/xhs_runs/notes_sentiment.csv \
  --label-mode ternary \
  --batch-size 20 \
  --concurrency 8 \
  --resume
```

当前 LLM prompt 是 A2/奶粉目标产品视角。若用户换品牌或品类，先说明需要调整脚本内目标品牌/竞品口径，不能直接沿用 A2 视角。

## 规则/词库分析与报告

评论词库分析，产出增强 CSV、Markdown 报告、词云和情感分布：

```bash
node scripts/analyze_xhs_comments.mjs \
  --comments "xhs_转奶争夺战场_top20x200_fast_comments.csv" \
  --detail "xhs_转奶争夺战场_top20x200_fast_comments.csv" \
  --lexicon "0601-a2评论-正负向词库.xlsx" \
  --full \
  --out-dir local_data/xhs_comment_analysis_transfer
```

关键词 TopN 情感评分：

```bash
node scripts/score_xhs_keyword_topn_sentiment.mjs \
  --input "xhs_转奶争夺战场_top20x200_fast_comments.csv" \
  --note-cache "local_data/xhs_note_body_transfer_full/xhs_转奶争夺战场_top20x200_fast_comments.csv.note_detail_tags.jsonl" \
  --lexicon "0601-a2评论-正负向词库.xlsx" \
  --top-ns 20,50 \
  --out-dir local_data/xhs_keyword_topn_sentiment_transfer
```

拉取/分析帖子正文与 tag：

```bash
node scripts/extract_xhs_note_tags.mjs \
  --input "xhs_转奶争夺战场_top20x200_fast_comments.csv" \
  --out-dir local_data/xhs_note_body_transfer_full
```

月度帖子趋势：

```bash
node scripts/analyze_xhs_post_monthly_sentiment.mjs \
  --lexicon "0601-a2评论-正负向词库.xlsx" \
  --out-dir local_data/xhs_post_monthly_sentiment
```

战场月度趋势：

```bash
node scripts/analyze_xhs_monthly_sentiment_by_battle.mjs \
  --lexicon "0601-a2评论-正负向词库.xlsx" \
  --out-dir local_data/xhs_monthly_sentiment_by_battle
```

突发负向舆情：

```bash
node scripts/analyze_xhs_event_negative_trend.mjs \
  --input local_data/xhs_post_monthly_sentiment/post_monthly_sentiment_detail.csv \
  --out-dir local_data/xhs_event_negative_trend
```

## 产物阅读顺序

优先看 Markdown 报告，再看 summary JSON/CSV，最后下钻明细：

- 评论分析：`xhs_comment_analysis_report_full.md`、`xhs_comments_enriched_full.csv`。
- 关键词评分：`keyword_topn_sentiment_scores.csv`、`keyword_topn_sentiment_scores.meta.json`。
- 月度趋势：`monthly_sentiment_by_battle_report.md`、`monthly_sentiment_all_summary.csv`。
- 帖子趋势：`post_monthly_sentiment_overall_report.md`、`post_monthly_sentiment_detail.csv`。
- 突发负向：`event_spike_report.md`、`may_event_negative_examples.csv`。

已有资产入口参考 MAGA 仓库 `docs/XHS_REAL_USER_CORPUS_ASSET.md`。做真人感语料时优先使用 `_with_body.csv` 或 `local_data/xhs_real_user_corpus_0601/real_user_comment_corpus_0601.csv`，不要默认使用包含用户昵称、profile、raw JSON 的原始字段。

## 输出给用户

完成后用高信号摘要说明：

- 跑了哪条链路、输入和输出路径。
- 样本规模：关键词数、帖子数、评论数、失败数或 `llm_error` 数。
- 关键发现：正负向比例、Top 风险标签、负向增长月份/关键词。
- 后续动作：是否需要补爬、调词库、改 LLM 标签口径、沉淀成 MAGA 语料。

不要把长报告整篇贴出来；给路径和结论，必要时摘最重要的 3-5 条。
