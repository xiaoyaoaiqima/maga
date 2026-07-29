# 文章交付库存

## 目标

文章正文只入库一次，来源和交付记录单独保存。后续交付按未使用库存、活动分类和目标比例抽取，避免反复扫描历史 CSV，也避免重复交付。

当前共享库存：

- SQLite：`local_data/a2_reiyu_delivery/article_inventory.sqlite3`
- 管理命令：`platform-server/scripts/manage_article_delivery_inventory.py`
- A2 礼遇资产键：`a2_reiyu_ugc_post_rules_v1`
- 旺玥资产键：`wangyue_v3_core_storyline_article_rules`
- A2 默认交付列：`content_id, 标题, 正文, 分类`
- 旺玥默认交付列：`标题, 正文, 上下文变量(context_list)`

两种文章共用 `article_inventory`、`article_inventory_source`、
`article_delivery_batch` 和 `article_delivery_batch_item`，通过 `asset_key`
隔离；正文唯一键为 `asset_key + body_hash`，不同产品不会互相占用库存。
SQLite 路径暂时保留 A2 旧目录名，避免迁移现有库存。

## 旺玥同步

旺玥当前生产池以规则资产 v88 为最低版本，同步时只保留满足当前
文章池导出门槛的正文，并把 MySQL `comment_delivery_ledger` 中已交付正文
同步为已使用：

```bash
cd platform-server
python3 scripts/manage_article_delivery_inventory.py sync-wangyue \
  --min-rule-version 88
```

查看旺玥库存：

```bash
python3 scripts/manage_article_delivery_inventory.py \
  --asset-key wangyue_v3_core_storyline_article_rules stats
```

交付旺玥文章时不需要 A2 的集罐比例：

```bash
python3 scripts/manage_article_delivery_inventory.py \
  --asset-key wangyue_v3_core_storyline_article_rules export \
  --count 100 --delivery-code wangyue-100-20260725 \
  --output /path/to/旺玥_100篇.csv --commit
```

## 新 CSV 入库

先只导出库存中没有的新正文：

```bash
cd platform-server
python3 scripts/manage_article_delivery_inventory.py diff-csv /path/to/input.csv \
  --output /tmp/a2_new_only.csv
```

只对这个增量 CSV 跑 A2 严格审核：

```bash
python3 scripts/audit_a2_reiyu_csv.py /tmp/a2_new_only.csv \
  --output /tmp/a2_new_only_audit.csv --concurrency 10
```

只把严格通过的正文入库：

```bash
python3 scripts/manage_article_delivery_inventory.py import-csv /tmp/a2_new_only_audit.csv \
  --source-type strict_audit --review-status strict_reviewed \
  --allowed-review-tier direct_pool
```

最后给已存在正文补上原始 CSV 来源，不会误收未通过的新正文：

```bash
python3 scripts/manage_article_delivery_inventory.py import-csv /path/to/input.csv \
  --source-type external_csv --review-status source_duplicate --existing-only
```

## 按比例交付

先做不占用库存的预览：

```bash
python3 scripts/manage_article_delivery_inventory.py export \
  --count 500 --can-ratio 0.7 \
  --delivery-code a2-reiyu-500-preview \
  --output /path/to/A2礼遇_500篇_集罐70其他30.csv
```

确认实际交付时加 `--commit`。写入交付台账后，这批文章默认不会再次被抽中：

```bash
python3 scripts/manage_article_delivery_inventory.py export \
  --count 500 --can-ratio 0.7 \
  --delivery-code a2-reiyu-500-20260723 \
  --output /path/to/A2礼遇_500篇_集罐70其他30.csv \
  --commit
```

库存统计：

```bash
python3 scripts/manage_article_delivery_inventory.py stats
```

`集罐`是总类，内部继续保留 `12罐` 和 `其他罐` 两个分类；`其他`包含抽奖、老客回馈、会员体系等非集罐主活动。
