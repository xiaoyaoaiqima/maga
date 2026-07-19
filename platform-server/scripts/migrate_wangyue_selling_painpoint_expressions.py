"""Move Wangyue selling-painpoint expressions out of rule corpus text."""
from __future__ import annotations

import argparse
import asyncio
import copy
import csv
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update

from app.models.maga_assets import AssetImportRun, AssetRegistry


ASSET_TYPE = "article_business_rule_set"
ASSET_KEY = "wangyue_v3_core_storyline_article_rules"
DEFAULT_CSV = Path(
    "/Users/luxifa/maga/outputs/019f68a6-a6bf-7da2-bcd1-41fee24c58b6/"
    "旺玥卖点表达_导入_卖点加痛点.csv"
)
SELLING_EXPRESSION_SECTION = re.compile(
    r"\n*【卖点表达(?:槽位)?】[ \t]*\n"
    r"(?:[ \t]*-[ \t]*卖点表达：[^\n]+(?:\n[ \t]+注意：[^\n]+)?(?:\n|$))+"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="结构化迁移旺玥卖点痛点表达。")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", "mysql+aiomysql://maga:maga123456@127.0.0.1:3306/maga"),
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--created-by", default="codex-wangyue-selling-painpoint-migration")
    parser.add_argument("--backup-dir", type=Path, default=Path(".local/asset-config-backups"))
    return parser


def read_expressions(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["卖点", "语料"]:
            raise ValueError(f"CSV 表头必须是 卖点,语料，实际为 {reader.fieldnames}")
        rows = []
        for source_row_no, row in enumerate(reader, start=2):
            group = str(row.get("卖点") or "").strip()
            expression = str(row.get("语料") or "").strip()
            if not group or not expression:
                raise ValueError(f"CSV 第 {source_row_no} 行存在空卖点痛点组或空表达")
            rows.append(
                {
                    "selling_painpoint_group": group,
                    "expression": expression,
                    "source_row_no": source_row_no,
                }
            )
    if not rows:
        raise ValueError("卖点痛点表达 CSV 为空")
    return rows


def group_for_rule(rule: dict[str, Any], available_groups: set[str]) -> str:
    existing = str(rule.get("selling_painpoint_group") or "").strip()
    if existing:
        return existing
    routable_groups = {group.removesuffix("-ugc") for group in available_groups}
    painpoint = str(rule.get("painpoint") or "").strip()
    selling_point = str(rule.get("selling_point") or "").strip()
    candidate = f"{selling_point}+{painpoint}" if selling_point and painpoint else ""
    if candidate in routable_groups:
        return candidate
    matching = sorted(group for group in routable_groups if group.endswith(f"+{painpoint}"))
    if len(matching) == 1:
        return matching[0]
    raise ValueError(
        f"规则 {rule.get('rule_id')} 无法确定 selling_painpoint_group："
        f"candidate={candidate!r}, painpoint={painpoint!r}, matching={matching}"
    )


def normalized_business_rule_name(rule: dict[str, Any], group: str) -> str:
    item_no = int(rule.get("item_no") or str(rule.get("rule_id") or "").rsplit("_", 1)[-1])
    post_type = str(rule.get("post_type") or "").strip()
    if not post_type:
        raise ValueError(f"规则 {rule.get('rule_id')} 缺少 post_type")
    return f"V3M-{item_no:02d}｜{group}｜{post_type}"


def migrate_content(
    content_json: dict[str, Any],
    metadata_json: dict[str, Any],
    expressions: list[dict[str, Any]],
    *,
    source_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    content = copy.deepcopy(content_json)
    metadata = copy.deepcopy(metadata_json)
    available_groups = {item["selling_painpoint_group"] for item in expressions}
    migrated_items = []
    removed_blocks = 0
    renamed_rules = 0
    rule_group_counts: Counter[str] = Counter()
    for raw_rule in content.get("items") or []:
        if not isinstance(raw_rule, dict):
            continue
        rule = copy.deepcopy(raw_rule)
        group = group_for_rule(rule, available_groups)
        corpus = str(rule.get("corpus") or "")
        cleaned_corpus, count = SELLING_EXPRESSION_SECTION.subn("\n", corpus)
        removed_blocks += count
        rule["corpus"] = re.sub(r"\n{3,}", "\n\n", cleaned_corpus).strip()
        rule["selling_painpoint_group"] = group
        normalized_name = normalized_business_rule_name(rule, group)
        if str(rule.get("business_rule") or "").strip() != normalized_name:
            renamed_rules += 1
        rule["business_rule"] = normalized_name
        rule.pop("painpoint", None)
        rule.pop("selling_point", None)
        migrated_items.append(rule)
        rule_group_counts[group] += 1

    if not migrated_items:
        raise ValueError("当前旺玥规则资产没有 items")
    if removed_blocks not in {0, len(migrated_items)}:
        raise ValueError(
            f"卖点表达块迁移状态不一致，规则数={len(migrated_items)}，实际移除={removed_blocks}"
        )

    group_counts = Counter(item["selling_painpoint_group"] for item in expressions)
    content["schema_version"] = "3.3"
    content["items"] = migrated_items
    content["selling_painpoint_expression_label"] = "卖点痛点表达"
    content["selling_painpoint_expressions"] = expressions

    for key in (
        "eligible_source_rows",
        "hard_or_time_filtered_rows",
        "painpoint_selling_mapping",
        "selected_pool_counts",
        "selected_unique_expression_rows",
        "selection_policy",
    ):
        metadata.pop(key, None)
    metadata.update(
        {
            "structure_sections": [
                "生文指令",
                "内容方向",
                "本篇灵感线索",
                "事实与合规边界",
                "成文要求",
            ],
            "structured_expression_section": "卖点痛点表达",
            "selling_painpoint_expression_source": str(source_path),
            "selling_painpoint_expression_count": len(expressions),
            "selling_painpoint_group_count": len(group_counts),
            "selling_painpoint_group_counts": dict(group_counts),
            "selling_painpoint_rule_group_counts": dict(rule_group_counts),
            "selling_painpoint_storage": "content_json.selling_painpoint_expressions",
            "corpus_selling_expression_blocks_removed": max(
                int(metadata.get("corpus_selling_expression_blocks_removed") or 0),
                removed_blocks,
            ),
            "business_rule_naming_pattern": "V3M-{item_no}｜{selling_painpoint_group}｜{post_type}",
            "business_rule_names_normalized": len(migrated_items),
            "source_expression_rows": len(expressions),
        }
    )
    summary = {
        "rule_count": len(migrated_items),
        "expression_count": len(expressions),
        "group_counts": dict(group_counts),
        "rule_group_counts": dict(rule_group_counts),
        "removed_corpus_blocks": removed_blocks,
        "renamed_rule_count": renamed_rules,
    }
    return content, metadata, summary


async def run(args: argparse.Namespace) -> None:
    os.environ["DATABASE_URL"] = args.database_url
    from app.core.database import async_session_factory

    source_path = args.csv.expanduser().resolve()
    source_bytes = source_path.read_bytes()
    expressions = read_expressions(source_path)
    source_hash = hashlib.sha256(source_bytes).hexdigest()

    async with async_session_factory() as session:
        current = await session.scalar(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type == ASSET_TYPE,
                AssetRegistry.asset_key == ASSET_KEY,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
        )
        if current is None:
            raise ValueError(f"找不到当前生产资产：{ASSET_KEY}")

        content, metadata, summary = migrate_content(
            current.content_json or {},
            current.metadata_json or {},
            expressions,
            source_path=source_path,
        )
        max_version = await session.scalar(
            select(func.max(AssetRegistry.version_no)).where(
                AssetRegistry.asset_type == ASSET_TYPE,
                AssetRegistry.asset_key == ASSET_KEY,
            )
        )
        next_version = int(max_version or 0) + 1
        result = {
            "asset_id": current.id,
            "current_version": current.version_no,
            "next_version": next_version,
            "source": str(source_path),
            "source_hash": source_hash,
            **summary,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not args.apply:
            print("DRY-RUN: add --apply to create the new production version.")
            return

        args.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = args.backup_dir / (
            f"{ASSET_KEY}-v{current.version_no}-"
            f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        )
        backup_path.write_text(
            json.dumps(
                {
                    "id": current.id,
                    "version_no": current.version_no,
                    "content_json": current.content_json,
                    "metadata_json": current.metadata_json,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        await session.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == ASSET_TYPE,
                AssetRegistry.asset_key == ASSET_KEY,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        new_asset = AssetRegistry(
            asset_type=ASSET_TYPE,
            asset_key=ASSET_KEY,
            display_name=f"0705旺玥活动-V3-卖点痛点表达-v{next_version}",
            version_no=next_version,
            status="active",
            asset_stage="production",
            source_name=source_path.name,
            source_uri=source_path.as_uri(),
            source_hash=source_hash,
            content_json=content,
            metadata_json=metadata,
            created_by=args.created_by,
        )
        session.add(new_asset)
        await session.flush()
        session.add(
            AssetImportRun(
                source_name=source_path.name,
                source_uri=source_path.as_uri(),
                source_hash=source_hash,
                status="succeeded",
                imported_assets=1,
                summary_json={
                    "asset_id": new_asset.id,
                    "asset_key": ASSET_KEY,
                    "asset_type": ASSET_TYPE,
                    "version_no": next_version,
                    "display_name": new_asset.display_name,
                    **summary,
                },
                created_by=args.created_by,
            )
        )
        await session.commit()
        print(f"APPLIED: created asset id={new_asset.id}, version={next_version}")
        print(f"BACKUP: {backup_path.resolve()}")


def main() -> None:
    asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    main()
