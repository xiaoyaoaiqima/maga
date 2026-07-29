from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.services.article_delivery_inventory_service import (
    A2_REIYU_ASSET_KEY,
    WANGYUE_ASSET_KEY,
    ArticleDeliveryInventoryService,
)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["content_id", "标题", "正文", "分类"]
        )
        writer.writeheader()
        writer.writerows(rows)


def test_import_deduplicates_body_and_preserves_sources(tmp_path: Path) -> None:
    source_a = tmp_path / "a.csv"
    source_b = tmp_path / "b.csv"
    _write_csv(
        source_a,
        [{"content_id": "a", "标题": "标题A", "正文": "同一篇 正文", "分类": "12罐"}],
    )
    _write_csv(
        source_b,
        [{"content_id": "b", "标题": "标题B", "正文": "同一篇\n正文", "分类": "其他"}],
    )
    service = ArticleDeliveryInventoryService(tmp_path / "inventory.sqlite3")

    first = service.import_csv(
        source_a, source_type="test", default_review_status="approved"
    )
    second = service.import_csv(
        source_b, source_type="test", default_review_status="approved"
    )

    assert first.inserted_articles == 1
    assert second.duplicate_articles == 1
    assert service.stats()["total_usable"] == 1


def test_export_uses_exact_mix_and_committed_rows_are_not_reused(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.csv"
    rows = []
    for index in range(8):
        category = "12罐" if index < 4 else "其他"
        rows.append(
            {
                "content_id": f"content-{index}",
                "标题": f"标题{index}",
                "正文": f"正文{index}",
                "分类": category,
            }
        )
    _write_csv(source, rows)
    service = ArticleDeliveryInventoryService(tmp_path / "inventory.sqlite3")
    service.import_csv(source, source_type="test", default_review_status="approved")

    output = tmp_path / "delivery.csv"
    result = service.export_delivery(
        output,
        count=4,
        can_ratio=0.5,
        delivery_code="delivery-1",
        seed=1,
        commit=True,
    )
    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = list(csv.DictReader(handle))

    assert result.can_collection_count == 2
    assert sum(row["分类"] in {"12罐", "其他罐"} for row in exported) == 2
    assert service.stats()["never_delivered"] == 4

    with pytest.raises(ValueError, match="insufficient inventory"):
        service.export_delivery(
            tmp_path / "second.csv",
            count=6,
            can_ratio=0.5,
            delivery_code="delivery-2",
            seed=2,
            commit=False,
        )


def test_historical_delivery_is_recorded_on_import(tmp_path: Path) -> None:
    source = tmp_path / "used.csv"
    _write_csv(
        source,
        [
            {
                "content_id": "used-1",
                "标题": "标题",
                "正文": "已经用过的正文",
                "分类": "其他罐",
            }
        ],
    )
    service = ArticleDeliveryInventoryService(tmp_path / "inventory.sqlite3")

    service.import_csv(
        source,
        source_type="historical",
        default_review_status="approved",
        mark_delivered_code="used-300",
    )

    stats = service.stats()
    assert stats["total_usable"] == 1
    assert stats["never_delivered"] == 0


def test_existing_only_does_not_add_unreviewed_article(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    _write_csv(
        source,
        [{"content_id": "new-1", "标题": "标题", "正文": "尚未审核", "分类": "其他"}],
    )
    service = ArticleDeliveryInventoryService(tmp_path / "inventory.sqlite3")

    result = service.import_csv(
        source,
        source_type="source_link",
        default_review_status="source_only",
        existing_only=True,
    )

    assert result.inserted_articles == 0
    assert result.skipped_rows == 1
    assert service.stats()["total_usable"] == 0


def test_export_unseen_csv_only_keeps_new_bodies(tmp_path: Path) -> None:
    existing = tmp_path / "existing.csv"
    incoming = tmp_path / "incoming.csv"
    output = tmp_path / "unseen.csv"
    _write_csv(
        existing,
        [{"content_id": "1", "标题": "旧", "正文": "已经存在", "分类": "其他"}],
    )
    _write_csv(
        incoming,
        [
            {"content_id": "2", "标题": "重复", "正文": "已经\n存在", "分类": "其他"},
            {"content_id": "3", "标题": "新增", "正文": "新增正文", "分类": "12罐"},
        ],
    )
    service = ArticleDeliveryInventoryService(tmp_path / "inventory.sqlite3")
    service.import_csv(existing, source_type="test", default_review_status="approved")

    assert service.export_unseen_csv(incoming, output) == 1
    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["content_id"] for row in rows] == ["3"]


def test_apply_audit_withholds_non_direct_rows(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    audit = tmp_path / "audit.csv"
    _write_csv(
        source,
        [
            {"content_id": "1", "标题": "通过", "正文": "可用正文", "分类": "12罐"},
            {"content_id": "2", "标题": "待修", "正文": "待修正文", "分类": "其他"},
        ],
    )
    with audit.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["标题", "正文", "审核档位"])
        writer.writeheader()
        writer.writerows(
            [
                {"标题": "通过", "正文": "可用正文", "审核档位": "direct_pool"},
                {"标题": "待修", "正文": "待修正文", "审核档位": "light_fix_usable"},
            ]
        )
    service = ArticleDeliveryInventoryService(tmp_path / "inventory.sqlite3")
    service.import_csv(
        source, source_type="test", default_review_status="approved_manual"
    )

    result = service.apply_audit_csv(audit)

    assert result.usable_articles == 1
    assert result.withheld_articles == 1
    assert service.stats()["total_usable"] == 1


def test_duplicate_source_content_ids_are_made_unique(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    _write_csv(
        source,
        [
            {
                "content_id": "same-id",
                "标题": "第一篇",
                "正文": "正文一",
                "分类": "12罐",
            },
            {
                "content_id": "same-id",
                "标题": "第二篇",
                "正文": "正文二",
                "分类": "其他",
            },
        ],
    )
    service = ArticleDeliveryInventoryService(tmp_path / "inventory.sqlite3")
    service.import_csv(
        source, source_type="test", default_review_status="approved_manual"
    )
    output = tmp_path / "snapshot.csv"

    service.export_inventory_snapshot(output)

    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len({row["content_id"] for row in rows}) == 2


def test_assets_share_tables_without_sharing_inventory(tmp_path: Path) -> None:
    db_path = tmp_path / "inventory.sqlite3"
    source = tmp_path / "source.csv"
    _write_csv(
        source,
        [{"content_id": "same-id", "标题": "标题", "正文": "同一正文", "分类": "其他"}],
    )
    a2 = ArticleDeliveryInventoryService(db_path, asset_key=A2_REIYU_ASSET_KEY)
    wangyue = ArticleDeliveryInventoryService(db_path, asset_key=WANGYUE_ASSET_KEY)

    a2.import_csv(source, source_type="test", default_review_status="approved_manual")
    wangyue.import_csv(
        source, source_type="test", default_review_status="machine_exportable"
    )

    assert a2.stats()["total_usable"] == 1
    assert wangyue.stats()["total_usable"] == 1
    a2.record_historical_delivery(
        delivery_code="a2-delivery",
        bodies=["同一正文"],
        output_uri="a2.csv",
    )
    assert a2.stats()["never_delivered"] == 0
    assert wangyue.stats()["never_delivered"] == 1


def test_wangyue_export_uses_article_pool_columns_and_prevents_reuse(
    tmp_path: Path,
) -> None:
    source = tmp_path / "wangyue.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "content_id",
                "标题",
                "正文",
                "分类",
                "上下文变量(context_list)",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "content_id": "wangyue-1",
                "标题": "记录一下",
                "正文": "旺玥使用记录",
                "分类": "使用反馈",
                "上下文变量(context_list)": '{"业务规则":"使用反馈"}',
            }
        )
    service = ArticleDeliveryInventoryService(
        tmp_path / "inventory.sqlite3",
        asset_key=WANGYUE_ASSET_KEY,
    )
    service.import_csv(
        source,
        source_type="test",
        default_review_status="machine_exportable",
    )
    output = tmp_path / "delivery.csv"

    service.export_delivery(
        output,
        count=1,
        can_ratio=None,
        delivery_code="wangyue-delivery",
        commit=True,
    )

    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == ["标题", "正文", "上下文变量(context_list)"]
    assert json.loads(rows[0]["上下文变量(context_list)"]) == {"业务规则": "使用反馈"}
    assert service.stats()["never_delivered"] == 0

    with pytest.raises(ValueError, match="insufficient inventory"):
        service.export_delivery(
            tmp_path / "second.csv",
            count=1,
            can_ratio=None,
            delivery_code="wangyue-delivery-2",
        )


def test_replace_usable_bodies_keeps_current_sync_exact(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    _write_csv(
        source,
        [
            {"content_id": "1", "标题": "旧", "正文": "旧正文", "分类": "使用反馈"},
            {"content_id": "2", "标题": "新", "正文": "新正文", "分类": "使用反馈"},
        ],
    )
    service = ArticleDeliveryInventoryService(
        tmp_path / "inventory.sqlite3",
        asset_key=WANGYUE_ASSET_KEY,
    )
    service.import_csv(
        source,
        source_type="test",
        default_review_status="machine_exportable",
    )

    assert (
        service.replace_usable_bodies(
            ["新正文"],
            review_status="machine_exportable",
        )
        == 1
    )
    assert service.stats()["total_usable"] == 1


def test_current_audit_withheld_row_survives_later_sync(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    audit = tmp_path / "audit.csv"
    _write_csv(
        source,
        [{"content_id": "1", "标题": "待修", "正文": "待修正文", "分类": "使用反馈"}],
    )
    with audit.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["标题", "正文", "审核档位"])
        writer.writeheader()
        writer.writerow({"标题": "待修", "正文": "待修正文", "审核档位": "needs_fix"})
    service = ArticleDeliveryInventoryService(
        tmp_path / "inventory.sqlite3",
        asset_key=WANGYUE_ASSET_KEY,
    )
    service.import_csv(
        source,
        source_type="test",
        default_review_status="machine_exportable",
    )
    service.apply_audit_csv(audit)

    assert service.stats()["total_usable"] == 0
    service.import_csv(
        source,
        source_type="test",
        default_review_status="machine_exportable",
    )
    assert (
        service.replace_usable_bodies(
            ["待修正文"],
            review_status="machine_exportable",
        )
        == 0
    )
    assert service.stats()["total_usable"] == 0
