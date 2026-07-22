#!/usr/bin/env python3
"""Publish Wangyue energy rules with business-approved dual selling-point pairs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pymysql


ASSET_TYPE = "article_business_rule_set"
ASSET_KEY = "wangyue_v3_core_storyline_article_rules"
OLD_ENERGY_PAIR_BOUNDARY = (
    "精力不足场景必须由双卖点共同承接：进阶保护力+眼脑双引擎，或进阶保护力+营养丰富；"
    "不能只用免疫球蛋白、乳铁蛋白、HMO等保护成分解释精力、活力或体能。"
)
ENERGY_PAIR_BOUNDARY = (
    "精力不足使用进阶保护力+眼脑双引擎或进阶保护力+营养丰富作为生成方向；"
    "正文自然带到保护力、眼脑或营养丰富中的一个相关支点即可，不要求两侧卖点全部写齐。"
)
ENERGY_RULE_GROUPS = {
    14: "进阶保护力+眼脑双引擎+精力不足",
    17: "进阶保护力+营养丰富+精力不足-ugc",
    20: "进阶保护力+眼脑双引擎+精力不足-ugc",
}
ENERGY_PAIR_EXPRESSIONS = {
    1: (
        "进阶保护力+眼脑双引擎+精力不足",
        "旺玥有免疫球蛋白、含量优秀的乳铁蛋白和5大HMO共同支持保护力，"
        "还搭配DHA与燕窝酸补充眼脑营养，孩子户外活动后的体力消耗和回家后的用眼用脑可以一起兼顾。",
    ),
    2: (
        "进阶保护力+眼脑双引擎+精力不足",
        "保护力黄金三角由免疫球蛋白、乳铁蛋白和5大HMO组成，再加上DHA与燕窝酸的眼脑营养，"
        "更适合写孩子活动量大、还要专注探索的精力场景。",
    ),
    3: (
        "进阶保护力+眼脑双引擎+精力不足",
        "旺玥一边用免疫球蛋白、乳铁蛋白和5大HMO打好保护力基础，"
        "一边用DHA与燕窝酸补充眼脑营养，从户外活力到安静用脑都能找到产品依据。",
    ),
    4: (
        "进阶保护力+营养丰富+精力不足",
        "旺玥的免疫球蛋白、乳铁蛋白和5大HMO支持保护力，同时有钙铁锌和30多种关键营养，"
        "适合孩子活动量大、日常营养消耗也多的阶段。",
    ),
    5: (
        "进阶保护力+营养丰富+精力不足",
        "看精力场景不能只看保护力，旺玥既有免疫球蛋白、乳铁蛋白和5大HMO，"
        "也有钙铁锌与30多种关键营养，把保护力和日常营养两块一起顾上。",
    ),
    63: (
        "进阶保护力+眼脑双引擎+精力不足-ugc",
        "我当时不只看乳铁蛋白和HMO，DHA、燕窝酸也一起看了。孩子户外跑得多，回家还会画画拼图，保护力和眼脑营养都想兼顾。",
    ),
    64: (
        "进阶保护力+眼脑双引擎+精力不足-ugc",
        "活动量大以后，我选奶粉会把保护力和眼脑营养放一起看。旺玥这两块都有，孩子跑完回来还有心思安静玩一会儿。",
    ),
    65: (
        "进阶保护力+眼脑双引擎+精力不足-ugc",
        "旺玥的乳铁蛋白、免疫球蛋白、HMO这块我会看，DHA和燕窝酸也没落下，正好兼顾孩子白天跑跳和用眼用脑。",
    ),
    66: (
        "进阶保护力+眼脑双引擎+精力不足-ugc",
        "孩子白天在外面跑，回来又爱拼图画画，我更想把保护力和眼脑营养一起顾上，旺玥这个组合比较对路。",
    ),
    67: (
        "进阶保护力+营养丰富+精力不足-ugc",
        "孩子活动量大，吃饭又不算稳定，我选旺玥时既看乳铁蛋白和HMO，也看钙铁锌、30多种关键营养，保护力和日常营养两块都想顾上。",
    ),
    68: (
        "进阶保护力+营养丰富+精力不足-ugc",
        "我不是只冲着保护力去的，旺玥的钙铁锌和30多种关键营养也一起看了。孩子天天跑跳，营养这块也得跟上。",
    ),
    69: (
        "进阶保护力+营养丰富+精力不足-ugc",
        "活动多、饭量又有点飘的时候，我会把保护力和整体营养一起看。旺玥有乳铁蛋白、HMO，也有钙铁锌和多种关键营养。",
    ),
    70: (
        "进阶保护力+营养丰富+精力不足-ugc",
        "孩子白天消耗大，我选儿童奶粉不会只看一个成分。旺玥的保护力配方和日常营养配置都比较全，写精力场景更顺。",
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="发布旺玥精力双卖点规则。")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    parser.add_argument("--user", default=os.getenv("MYSQL_USER", "maga"))
    parser.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", "maga123456"))
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "maga"))
    parser.add_argument("--backup-dir", type=Path, default=Path(".local/asset-config-backups"))
    return parser


def _json_value(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def build_next_content(source_content: dict[str, Any]) -> dict[str, Any]:
    content = copy.deepcopy(source_content)
    items_by_no = {
        int(item.get("item_no")): item
        for item in content.get("items") or []
        if isinstance(item, dict) and item.get("item_no") is not None
    }
    missing_items = sorted(set(ENERGY_RULE_GROUPS) - set(items_by_no))
    if missing_items:
        raise RuntimeError(f"missing energy rules: {missing_items}")

    for item_no, group in ENERGY_RULE_GROUPS.items():
        item = items_by_no[item_no]
        display_group = group.removesuffix("-ugc")
        item["selling_painpoint_group"] = group
        item["business_rule"] = f"V3M-{item_no:02d}｜{display_group}｜{item.get('post_type') or ''}"

    expressions_by_row = {
        int(item.get("source_row_no")): item
        for item in content.get("selling_painpoint_expressions") or []
        if isinstance(item, dict) and item.get("source_row_no") is not None
    }
    missing_rows = sorted(set(ENERGY_PAIR_EXPRESSIONS) - set(expressions_by_row))
    if missing_rows:
        raise RuntimeError(f"missing energy expression rows: {missing_rows}")
    for source_row_no, (group, expression) in ENERGY_PAIR_EXPRESSIONS.items():
        item = expressions_by_row[source_row_no]
        item["selling_painpoint_group"] = group
        item["expression"] = expression

    hard_boundaries = [
        boundary
        for boundary in (content.get("hard_boundaries") or [])
        if boundary != OLD_ENERGY_PAIR_BOUNDARY
    ]
    if ENERGY_PAIR_BOUNDARY not in hard_boundaries:
        hard_boundaries.append(ENERGY_PAIR_BOUNDARY)
    content["hard_boundaries"] = hard_boundaries
    return content


def main() -> None:
    args = build_parser().parse_args()
    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select id, display_name, version_no, source_name, source_uri,
                       content_json, metadata_json
                from asset_registry
                where asset_type=%s and asset_key=%s
                  and asset_stage='production' and status='active'
                order by version_no desc, id desc
                limit 1
                """,
                (ASSET_TYPE, ASSET_KEY),
            )
            current = cursor.fetchone()
            if not current:
                raise RuntimeError(f"active asset not found: {ASSET_KEY}")
            cursor.execute(
                """
                select coalesce(max(version_no), 0) as max_version
                from asset_registry
                where asset_type=%s and asset_key=%s
                """,
                (ASSET_TYPE, ASSET_KEY),
            )
            next_version = int((cursor.fetchone() or {}).get("max_version") or 0) + 1

        source_content = _json_value(current.get("content_json")) or {}
        content = build_next_content(source_content)
        metadata = copy.deepcopy(_json_value(current.get("metadata_json")) or {})
        metadata.update(
            {
                "energy_selling_pair_base_asset_id": int(current["id"]),
                "energy_selling_pair_base_version_no": int(current["version_no"]),
                "energy_selling_pair_published_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        if source_content.get("inspiration_usage_interval") != content.get("inspiration_usage_interval"):
            raise RuntimeError("inspiration_usage_interval changed unexpectedly")
        if source_content.get("variation_slots") != content.get("variation_slots"):
            raise RuntimeError("asset variation_slots changed unexpectedly")

        source_hash = hashlib.sha256(
            json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        result = {
            "source_asset_id": int(current["id"]),
            "source_version_no": int(current["version_no"]),
            "target_version_no": next_version,
            "energy_rule_groups": ENERGY_RULE_GROUPS,
            "energy_expression_rows": sorted(ENERGY_PAIR_EXPRESSIONS),
            "hard_boundary_added": ENERGY_PAIR_BOUNDARY not in (source_content.get("hard_boundaries") or []),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not args.apply:
            conn.rollback()
            print("DRY-RUN: add --apply to create the new active production version.")
            return

        args.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = args.backup_dir / (
            f"{ASSET_KEY}-v{current['version_no']}-"
            f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        )
        backup_path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        with conn.cursor() as cursor:
            cursor.execute(
                """
                update asset_registry
                set status='archived'
                where asset_type=%s and asset_key=%s
                  and asset_stage='production' and status='active'
                """,
                (ASSET_TYPE, ASSET_KEY),
            )
            cursor.execute(
                """
                insert into asset_registry (
                    asset_type, asset_key, display_name, version_no, status, asset_stage,
                    source_name, source_uri, source_hash, content_json, metadata_json, created_by
                ) values (%s,%s,%s,%s,'active','production',%s,%s,%s,cast(%s as json),cast(%s as json),%s)
                """,
                (
                    ASSET_TYPE,
                    ASSET_KEY,
                    f"0705旺玥活动-V3-分层框架-精力双卖点-v{next_version}",
                    next_version,
                    current.get("source_name"),
                    current.get("source_uri"),
                    source_hash,
                    json.dumps(content, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                    "codex_wangyue_energy_selling_pairs_20260721",
                ),
            )
            new_asset_id = int(cursor.lastrowid)
        conn.commit()
        print(f"APPLIED: created asset id={new_asset_id}, version={next_version}")
        print(f"BACKUP: {backup_path.resolve()}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
