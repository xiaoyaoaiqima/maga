# 小红书真人感语料资产说明

> 生成时间：2026-06-01  
> 资产定位：把昨晚采集的小红书帖子、评论、正文/tag、情感和战场评分整理成 MAGA 可复用的真人感语料来源。  
> 操作边界：本说明不移动、不删除数据文件；只明确主产物、使用口径和后续资产化方向。

## 一、资产结论

这批数据应作为 MAGA 的高价值真人感语料底座保留。它不是普通评论样本，而是同时带有：

- 真实搜索词：来自 `小红书完整词包_综合排序_强意图降权版.xlsx` 的战场关键词。
- 真实帖子上下文：标题、作者、正文、互动数据、发布时间、tag。
- 真实评论表达：评论正文、评论用户、点赞、评论时间。
- 真实业务战场：`转奶争夺战场`、`品类信任教育战场`。
- 真实疑虑与情绪：已产出情感、词云、关键词/战场评分报告。

后续应优先从 `_with_body.csv` 两张合并表读取，而不是只读评论主表；因为真人感语料需要评论和原帖上下文一起看。

评论切角优化时，不建议再直接回看原始大表。已在 [小红书爬取评论/帖子复用筛选结论](./XHS_CRAWLED_COMMENT_REUSE_GUIDE.md) 中完成一次性筛选，后续优先使用该文档里的可用口吻、排除规则和分切角改写方向。

## 二、最终主产物

| 层级 | 用途 | 文件 |
|------|------|------|
| 输入词包 | 搜索词、战场来源 | `小红书完整词包_综合排序_强意图降权版.xlsx` |
| 转奶全量评论+正文 | 真人评论、原帖上下文、tag 分析主入口 | `xhs_转奶争夺战场_top20x200_fast_comments_with_body.csv` |
| 品类信任全量评论+正文 | 真人评论、原帖上下文、tag 分析主入口 | `xhs_品类信任教育战场_top20x200_detail_comments_with_body.csv` |
| 转奶评论原表 | 不需要正文/tag 时的轻量评论分析 | `xhs_转奶争夺战场_top20x200_fast_comments.csv` |
| 品类信任评论原表 | 不需要正文/tag 时的轻量评论分析 | `xhs_品类信任教育战场_top20x200_detail_comments.csv` |
| 转奶逐帖正文/tag | 帖子级正文和话题分析 | `local_data/xhs_note_body_transfer_full/note_tags.csv` |
| 品类信任逐帖正文/tag | 帖子级正文和话题分析 | `local_data/xhs_note_body_trust_full/note_tags.csv` |
| 转奶情感增强评论 | 情感、主题、风险标签后的评论结果 | `local_data/xhs_comment_analysis_transfer_0601_lexicon/xhs_comments_enriched_full.csv` |
| 品类信任情感增强评论 | 情感、主题、风险标签后的评论结果 | `local_data/xhs_comment_analysis_trust_0601_lexicon/xhs_comments_enriched_full.csv` |
| 一图一战场词云 | 快速看真人表达高频词 | `local_data/xhs_wordcloud_one_per_battle_0601/` |
| 关键词情感评分 | 按关键词 TopN 评论计算情感 | `local_data/xhs_keyword_topn_sentiment_0601/keyword_topn_sentiment_scores.csv` |
| 战场评分报告 | 汇报口径和战场对比 | `local_data/xhs_battle_report_format_0601_note_tuned_negative_total/` |
| 真人感评论语料 | 去重后的可消费真人评论样本，不含用户昵称/profile/raw JSON | `local_data/xhs_real_user_corpus_0601/real_user_comment_corpus_0601.csv` |
| 真人感语料摘要 | 语料生成口径、去重口径、分战场数量 | `local_data/xhs_real_user_corpus_0601/real_user_comment_corpus_0601.summary.json` |
| 全量清单 | 文件状态、行数、大小、使用口径 | `local_data/collection_outputs_manifest.csv` |

## 三、数据规模

| 战场 | 评论行数 | 去重评论 | 去重帖子 | 评论用户 | 帖子作者 | 搜索词 | 有正文行 | 有 tag 行 |
|------|---------:|---------:|---------:|---------:|---------:|------:|---------:|---------:|
| 转奶争夺战场 | 26773 | 14656 | 2288 | 12631 | 1973 | 20 | 26420 | 21751 |
| 品类信任教育战场 | 25336 | 14726 | 2390 | 11471 | 2023 | 20 | 24962 | 20281 |

说明：

- 评论行数是 CSV 行数；去重评论按 `comment_id` 统计。
- 去重帖子按 `note_id` 统计。
- 有正文行按 `note_desc` 非空统计；有 tag 行按 `note_tags` 非空统计。
- 两张合并表字段一致，主字段包括：`battle_category`、`keyword`、`note_id`、`note_title`、`note_desc`、`note_likes`、`note_comments_count`、`comment_text`、`comment_likes`、`comment_time`、`note_tags`。
- 已生成可消费语料 `real_user_comment_corpus_0601.csv`，从 52109 行评论中保留 28929 条去重真人评论样本；其中转奶 14433 条、品类信任 14496 条。该文件不包含 `comment_user_name`、`comment_user_profile`、`raw_note_json`、`raw_comment_json`。

## 四、推荐使用口径

### 4.1 真人感语料抽取

主入口：

- `local_data/xhs_real_user_corpus_0601/real_user_comment_corpus_0601.csv`
- `xhs_转奶争夺战场_top20x200_fast_comments_with_body.csv`
- `xhs_品类信任教育战场_top20x200_detail_comments_with_body.csv`

建议抽取字段：

- 场景：`battle_category`、`keyword`、`note_title`、`note_desc`、`note_tags`
- 真人表达：`comment_text`
- 权重信号：`comment_likes`、`note_likes`、`note_comments_count`
- 去重键：`note_id`、`comment_id`

适合产出：

- 真实评论句式库
- 真实妈妈语气库
- 疑虑/求证表达库
- 评论区短句、追问、反驳、补充经验样本
- 文章正文里可借鉴的自然叙事表达

### 4.2 业务洞察和战场分析

主入口：

- `local_data/xhs_comment_analysis_transfer_0601_lexicon/xhs_comment_analysis_report_full.md`
- `local_data/xhs_comment_analysis_trust_0601_lexicon/xhs_comment_analysis_report_full.md`
- `local_data/xhs_keyword_topn_sentiment_0601/keyword_topn_sentiment_scores.csv`
- `local_data/xhs_battle_report_format_0601_note_tuned_negative_total/battle_report_format_negative_total.md`

适合产出：

- 哪些关键词负向更多
- 哪些战场疑虑更集中
- 用户不信任点、转奶阻力点、真实购买/使用阻力
- 给运营看的战场汇报

### 4.3 质量治理和反 AI 腔

主入口：

- 两张 `_with_body.csv`
- `local_data/xhs_wordcloud_one_per_battle_0601/transfer_word_frequencies_top200.csv`
- `local_data/xhs_wordcloud_one_per_battle_0601/trust_word_frequencies_top200.csv`

适合产出：

- 真人评论常见短句长度、停顿和断句方式
- AI 腔判别负例：过完整、过顺、过解释、过广告
- 同质化检测参照：真实评论不是一套固定结构
- 评论切角规则优化：从真实评论里补充不完整、接话式、随手反馈式表达

## 五、分层保存建议

当前不建议移动文件，先以文档和 manifest 作为入口。后续如果要真正资产化，可以按下面分层：

| 资产层 | 内容 | 当前来源 | 目标形态 |
|--------|------|----------|----------|
| 原始采集层 | 主评论表、state、retry 记录 | 根目录主 CSV、state、`local_data/retry_*` | 冷存，不直接给业务改 |
| 清洗全量层 | 评论+正文/tag 合并表 | 两张 `_with_body.csv` | 业务分析默认入口 |
| 汇报分析层 | 情感、词云、评分、战场报告 | `local_data/xhs_*_0601*` | 给业务直接阅读 |
| 语料资产层 | 真人句式、疑虑表达、自然评论样本 | 从 `_with_body.csv` 抽取 | 后续生成 `real_user_corpus_*` |
| 训练/提示词层 | 可喂给 MAGA 的 few-shot、规则反例、质检样本 | 从语料资产层筛选 | 进入 `prompts/` 或业务规则资产 |

## 六、下一步建议

1. 已生成 `real_user_comment_corpus_0601.csv`：从两张 `_with_body.csv` 抽出可消费评论语料，保留战场、关键词、帖子上下文、评论、点赞、tag。
2. 再做 `real_user_expression_patterns_0601.csv`：抽取短句、追问、接话、反驳、经验补充、疑虑求证等表达模式。
3. 建立“真人感评分参照”：把真实评论作为正样本，把当前生成内容里过完整/过广告/过顺的表达作为负样本。
4. 回流到 MAGA：评论生成、文章正文、同质化治理、痛点标签器、反馈回流工作台都应优先使用这批资产。
