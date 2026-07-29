"""Manage the reusable article inventory and exact-ratio delivery exports."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.article_delivery_inventory_service import (
    A2_REIYU_ASSET_KEY,
    DEFAULT_ARTICLE_INVENTORY_PATH,
    WANGYUE_ASSET_KEY,
    ArticleDeliveryInventoryService,
)


async def _sync_wangyue(db_path: Path, *, min_rule_version: int) -> dict[str, object]:
    from sqlalchemy import select

    from app.core.database import async_session_factory, engine
    from app.models.content_agent import (
        CommentDeliveryLedger,
        ContentBatchItem,
        ContentBatchJob,
    )
    from app.services.activity_quality_guard_service import (
        build_article_pool_context_list,
    )
    from app.services.content_batch_report_service import _final_postprocess_state

    async with async_session_factory() as db:
        result = await db.execute(
            select(ContentBatchItem, ContentBatchJob)
            .join(ContentBatchJob, ContentBatchJob.id == ContentBatchItem.batch_id)
            .where(ContentBatchJob.asset_key == WANGYUE_ASSET_KEY)
        )
        rows = result.all()
        ledger_entries = list(
            (
                await db.execute(
                    select(CommentDeliveryLedger).where(
                        CommentDeliveryLedger.asset_key == WANGYUE_ASSET_KEY
                    )
                )
            )
            .scalars()
            .all()
        )

    exportable_rows: list[dict[str, str]] = []
    exportable_bodies: list[str] = []
    for item, job in rows:
        rule_version = int((job.strategy_json or {}).get("rule_asset_version") or 0)
        body = str(item.body or "").strip()
        state = _final_postprocess_state(item.quality_json)
        if (
            rule_version < min_rule_version
            or item.status != "generated"
            or not body
            or not state["hard_pass"]
            or state["rewrite_required"]
        ):
            continue
        context_list = build_article_pool_context_list(item)
        business_rule = str((item.plan_json or {}).get("business_rule") or "旺玥")
        exportable_rows.append(
            {
                "content_id": f"wangyue-item-{item.id}",
                "标题": str(item.title or "").strip(),
                "正文": body,
                "分类": business_rule,
                "上下文变量(context_list)": json.dumps(
                    context_list, ensure_ascii=False
                ),
                "source_row": str(item.id),
                "batch_id": str(item.batch_id),
                "item_id": str(item.id),
                "rule_asset_version": str(rule_version),
            }
        )
        exportable_bodies.append(body)

    service = ArticleDeliveryInventoryService(db_path, asset_key=WANGYUE_ASSET_KEY)
    fieldnames = [
        "content_id",
        "标题",
        "正文",
        "分类",
        "上下文变量(context_list)",
        "source_row",
        "batch_id",
        "item_id",
        "rule_asset_version",
    ]
    with tempfile.TemporaryDirectory(prefix="wangyue-inventory-") as temp_dir:
        source_csv = Path(temp_dir) / "wangyue_exportable.csv"
        with source_csv.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(exportable_rows)
        imported = service.import_csv(
            source_csv,
            source_type="maga_batch_sync",
            default_review_status="machine_exportable",
            source_uri_override="mysql://maga/content_batch_item",
            source_row_column="source_row",
        )

    service.replace_usable_bodies(
        exportable_bodies,
        review_status="machine_exportable",
    )
    delivery_groups: dict[str, list[str]] = defaultdict(list)
    for entry in ledger_entries:
        source_uri = str(entry.source_uri or f"comment-delivery-ledger:{entry.id}")
        delivery_groups[source_uri].append(entry.comment_text)
    marked_delivered = 0
    for source_uri, bodies in delivery_groups.items():
        source_hash = hashlib.sha256(source_uri.encode("utf-8")).hexdigest()[:16]
        marked_delivered += service.record_historical_delivery(
            delivery_code=f"wangyue-ledger-{source_hash}",
            bodies=bodies,
            output_uri=source_uri,
        )
    payload = {
        "min_rule_version": min_rule_version,
        "source_exportable_count": len(exportable_rows),
        "import_result": imported.__dict__,
        "newly_marked_delivered": marked_delivered,
        "stats": service.stats(),
    }
    await engine.dispose()
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="文章交付库存：去重、分类、按比例导出、记录交付。"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_ARTICLE_INVENTORY_PATH,
        help="库存SQLite路径",
    )
    parser.add_argument(
        "--asset-key",
        default=A2_REIYU_ASSET_KEY,
        help="库存资产键；A2和旺玥通过asset_key共用同一套表",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import-csv", help="导入已审核可用CSV")
    import_parser.add_argument("input_csv", type=Path)
    import_parser.add_argument("--source-type", default="curated_csv")
    import_parser.add_argument("--review-status", default="approved_manual")
    import_parser.add_argument(
        "--allowed-review-tier",
        action="append",
        default=[],
        help="只导入指定审核档位，可重复传入；严格审核结果建议只传direct_pool",
    )
    import_parser.add_argument("--mark-delivered-code")
    import_parser.add_argument(
        "--existing-only",
        action="store_true",
        help="只给已存在文章补来源，不把未审核新文章加入库存",
    )

    export_parser = subparsers.add_parser("export", help="按比例抽取并导出CSV")
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--count", type=int, required=True)
    export_parser.add_argument("--can-ratio", type=float)
    export_parser.add_argument("--delivery-code", required=True)
    export_parser.add_argument("--seed", type=int, default=20260723)
    export_parser.add_argument(
        "--commit", action="store_true", help="确认交付并写入台账"
    )
    export_parser.add_argument("--allow-reuse", action="store_true")

    snapshot_parser = subparsers.add_parser("snapshot", help="导出全部可用库存快照")
    snapshot_parser.add_argument("--output", type=Path, required=True)
    snapshot_parser.add_argument("--never-delivered", action="store_true")

    diff_parser = subparsers.add_parser("diff-csv", help="只导出库存中尚不存在的新文章")
    diff_parser.add_argument("input_csv", type=Path)
    diff_parser.add_argument("--output", type=Path, required=True)

    audit_parser = subparsers.add_parser(
        "apply-audit", help="把审核结论回写到库存可用状态"
    )
    audit_parser.add_argument("audit_csv", type=Path)

    subparsers.add_parser("stats", help="查看库存和未交付数量")
    sync_wangyue_parser = subparsers.add_parser(
        "sync-wangyue",
        help="从本地MAGA批次同步旺玥机器可交付文章和历史交付台账",
    )
    sync_wangyue_parser.add_argument("--min-rule-version", type=int, default=88)

    args = parser.parse_args()
    if args.command == "sync-wangyue":
        payload = asyncio.run(
            _sync_wangyue(args.db, min_rule_version=args.min_rule_version)
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    service = ArticleDeliveryInventoryService(args.db, asset_key=args.asset_key)
    if args.command == "import-csv":
        result = service.import_csv(
            args.input_csv,
            source_type=args.source_type,
            default_review_status=args.review_status,
            allowed_review_tiers=args.allowed_review_tier,
            mark_delivered_code=args.mark_delivered_code,
            existing_only=args.existing_only,
        )
        payload = result.__dict__
    elif args.command == "export":
        result = service.export_delivery(
            args.output,
            count=args.count,
            can_ratio=args.can_ratio,
            delivery_code=args.delivery_code,
            seed=args.seed,
            commit=args.commit,
            allow_reuse=args.allow_reuse,
        )
        payload = result.__dict__
    elif args.command == "snapshot":
        payload = {
            "output_path": str(args.output.expanduser().resolve()),
            "row_count": service.export_inventory_snapshot(
                args.output,
                never_delivered_only=args.never_delivered,
            ),
        }
    elif args.command == "diff-csv":
        payload = {
            "input_path": str(args.input_csv.expanduser().resolve()),
            "output_path": str(args.output.expanduser().resolve()),
            "unseen_count": service.export_unseen_csv(args.input_csv, args.output),
        }
    elif args.command == "apply-audit":
        payload = service.apply_audit_csv(args.audit_csv).__dict__
    else:
        payload = service.stats()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
