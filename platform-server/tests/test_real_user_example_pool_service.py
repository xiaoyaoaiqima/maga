"""Tests for real-user example pool import and sampling."""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.maga_assets import AssetImportRun, AssetRegistry
from app.services.real_user_example_pool_service import (
    REAL_USER_EXAMPLE_POOL_ASSET_TYPE,
    append_real_user_example_pool_from_export_dir,
    infer_real_user_tags,
    infer_real_user_example_layer,
    import_real_user_example_pool_from_export_dir,
    select_real_user_examples,
)


def _write_export_dir(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    (base / "xhs_notes_full.csv").write_text(
        "\n".join(
            [
                "note_id,title,content,author_id,author_name,source_keyword,note_url,publish_time,likes",
                "n1,挑奶粉挑到头大,对比几款奶粉后还是看营养和孩子愿不愿意喝，价格贵点也认了,u1,用户1,奶粉,http://n1,2026-06-01,3",
                "n1,重复,重复内容,u1,用户1,奶粉,http://n1,2026-06-01,3",
                "n2,育儿师推荐,作为育儿师深耕奶粉行业多年，今天给大家安利闭眼入款,u2,用户2,奶粉,http://n2,2026-06-01,3",
                "n3,只表情,[笑哭R][笑哭R],u3,用户3,奶粉,http://n3,2026-06-01,3",
            ]
        ),
        encoding="utf-8",
    )
    (base / "xhs_comments_full.csv").write_text(
        "\n".join(
            [
                "comment_id,note_id,content,user_id,user_name,note_title,note_source_keyword,note_url,comment_type,comment_likes",
                "c1,n1,不是有点贵，是太贵了,u1,用户1,挑奶粉挑到头大,奶粉,http://n1,root,1",
                "c2,n1,[偷笑R],u2,用户2,挑奶粉挑到头大,奶粉,http://n1,root,",
                "c1,n1,不是有点贵，是太贵了,u1,用户1,挑奶粉挑到头大,奶粉,http://n1,root,1",
            ]
        ),
        encoding="utf-8",
    )


def test_infer_real_user_tags_does_not_treat_activity_amount_as_price():
    tags = infer_real_user_tags("孩子活动量大，日常保护力和眼脑营养都要看")

    assert "户外" in tags
    assert "价格" not in tags
    assert "户外" in infer_real_user_tags("户外跑跳多，日常保护力和眼脑营养都要看")
    assert "价格" in infer_real_user_tags("蹲活动的时候买了一罐，价格还是肉疼")


@pytest.mark.asyncio
async def test_import_real_user_example_pool_dry_run_filters_and_removes_personal_fields(tmp_path):
    export_dir = tmp_path / "export"
    _write_export_dir(export_dir)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AssetRegistry.__table__, AssetImportRun.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        result = await import_real_user_example_pool_from_export_dir(session, export_dir, dry_run=True)

    assert result.asset is None
    assert result.summary["note"]["read"] == 4
    assert result.summary["note"]["kept"] == 1
    assert result.summary["comment"]["kept"] == 1
    assert result.summary["total_items"] == 2
    assert all("user_name" not in item and "author_name" not in item for item in result.items)
    assert all("user_id" not in item and "author_id" not in item for item in result.items)
    assert {item["source_type"] for item in result.items} == {"note", "comment"}


@pytest.mark.asyncio
async def test_append_real_user_example_pool_preserves_existing_and_adds_new_items(tmp_path):
    export_dir = tmp_path / "export"
    _write_export_dir(export_dir)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AssetRegistry.__table__, AssetImportRun.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        incoming = await import_real_user_example_pool_from_export_dir(session, export_dir, dry_run=True)
        existing_item = incoming.items[0]
        old_only_item = {
            "source_type": "note",
            "text": "老资产里已有的一条真人表达",
            "title": "老资产",
            "tags": ["选奶"],
            "risk_tags": [],
            "quality_score": 10,
            "dedupe_hash": "old-only",
        }
        session.add(
            AssetRegistry(
                asset_type=REAL_USER_EXAMPLE_POOL_ASSET_TYPE,
                asset_key="test_pool",
                display_name="test",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={"items": [existing_item, old_only_item], "schema_version": "1.1"},
                metadata_json={},
                created_by="test",
            )
        )
        await session.commit()

    async with session_factory() as session:
        result = await append_real_user_example_pool_from_export_dir(session, export_dir, asset_key="test_pool")
        await session.commit()

    assert result.summary["existing_item_count"] == 2
    assert result.summary["incoming_item_count"] == 2
    assert result.summary["appended_item_count"] == 1
    assert result.summary["duplicate_item_count"] == 1
    assert result.summary["total_items"] == 3

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AssetRegistry).where(
                    AssetRegistry.asset_type == REAL_USER_EXAMPLE_POOL_ASSET_TYPE,
                    AssetRegistry.asset_key == "test_pool",
                )
            )
        ).scalars().all()

    assert {row.version_no: row.status for row in rows} == {1: "archived", 2: "active"}
    active = next(row for row in rows if row.status == "active")
    assert [item["dedupe_hash"] for item in active.content_json["items"]] == [
        existing_item["dedupe_hash"],
        "old-only",
        incoming.items[1]["dedupe_hash"],
    ]


def test_select_real_user_examples_uses_note_and_comment_counts():
    items = [
        {
            "source_type": "note",
            "text": f"选奶看营养和成长，第{i}条",
            "title": "选奶记录",
            "tags": ["选奶", "营养", "成长"],
            "risk_tags": [],
            "quality_score": 15,
            "dedupe_hash": f"n{i}",
        }
        for i in range(8)
    ] + [
        {
            "source_type": "comment",
            "text": f"有点贵但孩子爱喝，第{i}条",
            "title": "评论",
            "tags": ["价格", "喝奶接受度"],
            "risk_tags": ["评论口吻"],
            "quality_score": 12,
            "dedupe_hash": f"c{i}",
        }
        for i in range(4)
    ]

    selected, meta = select_real_user_examples(
        items,
        query_text="成长阶段营养补充，选奶时看旺玥",
        note_count=5,
        comment_count=2,
    )

    assert len(selected) == 7
    assert meta["selected"] == {"note": 5, "comment": 2}
    assert meta["source_type_counts"] == {"note": 5, "comment": 2}
    assert "营养" in meta["tag_counts"]


def test_select_real_user_examples_filters_prompt_view_without_changing_pool():
    items = [
        {
            "source_type": "note",
            "text": "A2至初断货后只能重新选奶，孩子口粮快没了",
            "title": "断货记录",
            "tags": ["选奶", "营养"],
            "risk_tags": ["竞品品牌"],
            "quality_score": 30,
            "dedupe_hash": "bad-note",
        },
        {
            "source_type": "note",
            "text": "对比几款儿童奶粉，最后还是看营养全面和孩子喝不喝",
            "title": "选奶记录",
            "source_keyword": "a2断货",
            "tags": ["选奶", "营养"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "good-note",
        },
        {
            "source_type": "comment",
            "text": "召回这个事看得我有点慌",
            "title": "",
            "tags": ["选奶"],
            "risk_tags": ["评论口吻"],
            "quality_score": 20,
            "dedupe_hash": "bad-comment",
        },
        {
            "source_type": "comment",
            "text": "不便宜但娃愿意喝就先这样",
            "title": "",
            "tags": ["价格", "喝奶接受度"],
            "risk_tags": ["评论口吻"],
            "quality_score": 10,
            "dedupe_hash": "good-comment",
        },
    ]

    selected, meta = select_real_user_examples(
        items,
        query_text="选奶看营养",
        note_count=1,
        comment_count=1,
        exclude_risk_tags=["竞品品牌"],
        exclude_terms=["断货", "召回"],
    )

    assert [item["dedupe_hash"] for item in selected] == ["good-note", "good-comment"]
    assert meta["filters"]["exclude_risk_tags"] == ["竞品品牌"]
    assert meta["filters"]["exclude_terms"] == ["断货", "召回"]


def test_real_user_example_layer_rejects_noise_without_rejecting_cup_drinking():
    reject_item = {
        "source_type": "note",
        "title": "小黄人快闪",
        "text": "旺玥联名快闪空降草坪，玩家速来一起打怪。",
        "source_keyword": "旺玥",
        "risk_tags": [],
    }
    cup_item = {
        "source_type": "note",
        "title": "喝奶记录",
        "text": "每天早上自己拿杯子喝完，除了贵点没毛病。",
        "source_keyword": "旺玥",
        "risk_tags": [],
    }
    bad_action_item = {
        "source_type": "note",
        "title": "喝奶记录",
        "text": "孩子自己泡奶粉，喝完就塞书包去上课。",
        "source_keyword": "旺玥",
        "risk_tags": [],
    }

    assert infer_real_user_example_layer(reject_item)[0] == "reject"
    assert infer_real_user_example_layer(cup_item)[0] != "reject"
    assert infer_real_user_example_layer(bad_action_item)[0] == "reject"


def test_select_real_user_examples_layers_route_and_texture():
    items = [
        {
            "source_type": "note",
            "text": "上幼儿园后接触人多，选旺玥就是看中日常保护力。",
            "title": "入园记录",
            "tags": ["幼儿园", "保护力"],
            "risk_tags": [],
            "quality_score": 16,
            "dedupe_hash": "route-1",
        },
        {
            "source_type": "note",
            "text": "除了贵点没毛病。",
            "title": "短句",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-1",
        },
        {
            "source_type": "note",
            "text": "我不是很懂，先喝着吧。",
            "title": "短句",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-2",
        },
        {
            "source_type": "note",
            "text": "旺玥联名快闪空降草坪。",
            "title": "快闪",
            "tags": ["选奶"],
            "risk_tags": [],
            "quality_score": 20,
            "dedupe_hash": "reject-1",
        },
    ]

    selected, meta = select_real_user_examples(
        items,
        query_text="孩子上幼儿园后容易中招，关注保护力",
        note_count=4,
        comment_count=0,
        route_count=1,
        texture_count=2,
    )

    assert [item["example_layer"] for item in selected] == ["route", "texture", "texture"]
    assert {item["dedupe_hash"] for item in selected} == {"route-1", "texture-1", "texture-2"}
    assert selected[0]["route_family"] == "school_collective"
    assert meta["route_family_counts"] == {"school_collective": 1}


def test_select_real_user_examples_layers_route_detail_texture_and_ending():
    items = [
        {
            "source_type": "note",
            "text": "上幼儿园后接触人多，选旺玥就是看中日常保护力。",
            "title": "入园记录",
            "tags": ["幼儿园", "保护力"],
            "risk_tags": [],
            "quality_score": 20,
            "dedupe_hash": "route-1",
        },
        {
            "source_type": "note",
            "text": "餐桌边那个杯子总放在老位置，晚上收的时候还能看到一点奶渍。",
            "title": "日常细节",
            "tags": ["喝奶接受度"],
            "risk_tags": [],
            "quality_score": 18,
            "dedupe_hash": "detail-1",
        },
        {
            "source_type": "note",
            "text": "除了贵点没毛病。",
            "title": "短句",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-1",
        },
        {
            "source_type": "note",
            "text": "后面能少折腾点就行。",
            "title": "收尾",
            "tags": ["喝奶接受度"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "ending-1",
            "example_layer": "ending",
            "layer_reason": "test_ending",
        },
    ]

    selected, meta = select_real_user_examples(
        items,
        query_text="孩子上幼儿园后容易中招，关注保护力",
        note_count=5,
        comment_count=0,
        route_count=1,
        detail_count=1,
        texture_count=1,
        ending_count=1,
    )

    assert [item["example_layer"] for item in selected] == ["route", "detail", "texture", "ending"]
    assert [item["dedupe_hash"] for item in selected] == ["route-1", "detail-1", "texture-1", "ending-1"]
    assert meta["selected"]["detail"] == 1
    assert meta["selected"]["ending"] == 1
    assert meta["layer_counts"] == {"route": 1, "detail": 1, "texture": 1, "ending": 1}


def test_select_real_user_examples_can_filter_source_keyword_by_layer():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "当妈后才懂这种日常。",
                "title": "当妈后才懂",
                "source_keyword": "general_title_pool",
                "tags": ["营养"],
                "risk_tags": [],
                "quality_score": 20,
                "dedupe_hash": "title-1",
                "example_layer": "title_shape",
            },
            {
                "source_type": "note",
                "text": "说白了就是普通妈妈的碎碎念。",
                "title": "轻业务",
                "source_keyword": "row3_light_business_texture_curated",
                "tags": ["营养"],
                "risk_tags": [],
                "quality_score": 20,
                "dedupe_hash": "texture-curated",
                "example_layer": "texture",
                "prompt_text": "说白了就是普通妈妈的碎碎念。",
                "prompt_text_source": "manual_curation_from_real_daily_texture",
                "layer_reason": "row3_light_business_texture:low_business_semantics",
            },
            {
                "source_type": "note",
                "text": "除了贵点没毛病。",
                "title": "旧纹理",
                "source_keyword": "wangyue_old_texture_pool",
                "tags": ["营养"],
                "risk_tags": [],
                "quality_score": 99,
                "dedupe_hash": "texture-old",
                "example_layer": "texture",
            },
        ],
        query_text="注意力不集中，眼脑营养观察",
        note_count=2,
        comment_count=0,
        title_shape_count=1,
        texture_count=1,
        layer_source_keyword_include={
            "texture": ["row3_light_business_texture_curated"],
        },
    )

    assert [item["example_layer"] for item in selected] == ["title_shape", "texture"]
    assert selected[0]["source_dedupe_hash"] == "title-1"
    assert selected[1]["dedupe_hash"] == "texture-curated"
    assert meta["layer_source_keyword_include"] == {
        "texture": ["row3_light_business_texture_curated"],
    }


def test_select_real_user_examples_layers_title_shape_and_opening_texture():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "上幼儿园以后才发现，孩子每天那杯奶我还挺认真看的。",
                "title": "当妈后才懂",
                "tags": ["幼儿园", "选奶"],
                "risk_tags": [],
                "quality_score": 20,
                "dedupe_hash": "good-title-opening",
            },
            {
                "source_type": "note",
                "text": "栏目感太重的标题不适合进入标题形态池。",
                "title": "旺玥保护小课堂开课啦",
                "tags": ["保护力"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "bad-title-column",
            },
            {
                "source_type": "note",
                "text": "这个标题带年龄也不适合。",
                "title": "3岁宝宝奶粉攻略",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "bad-title-age",
            },
            {
                "source_type": "note",
                "text": "跨品类标题不适合进入标题形态池。",
                "title": "好奇的深睡大师和屁屁面膜有影响吗",
                "tags": ["成分"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "bad-title-cross-category",
            },
            {
                "source_type": "note",
                "text": "缺货语境标题不适合进入标题形态池。",
                "title": "买不到，根本买不到",
                "tags": ["价格"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "bad-title-stock",
            },
            {
                "source_type": "note",
                "text": "缺货情绪标题不适合进入标题形态池。",
                "title": "实在是等不了了",
                "tags": ["价格"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "bad-title-stock-emotion",
            },
            {
                "source_type": "note",
                "text": "安全事故标题不适合进入标题形态池。",
                "title": "315后儿童用品安全清单",
                "tags": ["成分"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "bad-title-safety-list",
            },
            {
                "source_type": "note",
                "text": "科技标题不适合进入标题形态池。",
                "title": "Claude Agent SDK 的几个隐藏坑",
                "tags": ["成分"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "bad-title-tech",
            },
            {
                "source_type": "note",
                "text": "竞品型号标题不适合进入标题形态池。",
                "title": "断断续续记录下，为何选至熠",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "bad-title-product",
            },
            {
                "source_type": "note",
                "text": "截断广告标题不适合进入标题形态池。",
                "title": "胆子大了 奶粉说换就换了😂（不是广",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "bad-title-ad-fragment",
            },
            {
                "source_type": "note",
                "text": "谁懂啊，选奶这件事真的会越看越纠结。",
                "title": "选奶记录",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 16,
                "dedupe_hash": "opening-only",
                "example_layer": "opening_texture",
                "layer_reason": "curated_opening:test",
            },
        ],
        query_text="孩子上幼儿园后容易中招，关注保护力",
        note_count=3,
        comment_count=0,
        title_shape_count=1,
        opening_or_ending_count=1,
    )

    assert [item["example_layer"] for item in selected] == ["title_shape", "opening_texture"]
    prompt_texts = {item["prompt_text"] for item in selected}
    assert prompt_texts & {"当妈后才懂", "选奶记录"}
    assert "旺玥保护小课堂开课啦" not in prompt_texts
    assert "3岁宝宝奶粉攻略" not in prompt_texts
    assert "好奇的深睡大师和屁屁面膜有影响吗" not in prompt_texts
    assert "买不到，根本买不到" not in prompt_texts
    assert "实在是等不了了" not in prompt_texts
    assert "315后儿童用品安全清单" not in prompt_texts
    assert "Claude Agent SDK 的几个隐藏坑" not in prompt_texts
    assert "断断续续记录下，为何选至熠" not in prompt_texts
    assert "胆子大了 奶粉说换就换了😂（不是广" not in prompt_texts
    assert meta["selected"]["title_shape"] == 1
    assert meta["selected"]["opening_texture"] == 1
    assert set(meta["prompt_text_by_layer"]["title_shape"]) <= {"当妈后才懂", "选奶记录"}


def test_select_real_user_examples_avoids_repeated_title_shape_prompt_text():
    used_hashes: set[str] = set()
    items = [
        {
            "source_type": "note",
            "text": f"第{i}条选奶记录，价格和营养都会看。",
            "title": "我的消费观好像在被刷新",
            "tags": ["价格", "营养"],
            "risk_tags": [],
            "quality_score": 30,
            "dedupe_hash": f"same-title-source-{i}",
        }
        for i in range(5)
    ] + [
        {
            "source_type": "note",
            "text": "另一条选奶记录，孩子喝着合适就行。",
            "title": "奶粉这钱省不了",
            "tags": ["母婴奶粉"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "different-title-source",
        }
    ]

    first, first_meta = select_real_user_examples(
        items,
        query_text="孩子容易中招，选奶看保护力和价格",
        note_count=1,
        comment_count=0,
        title_shape_count=1,
        used_dedupe_hashes=used_hashes,
    )
    second, second_meta = select_real_user_examples(
        items,
        query_text="孩子容易中招，选奶看保护力和价格",
        note_count=1,
        comment_count=0,
        title_shape_count=1,
        used_dedupe_hashes=used_hashes,
    )

    selected_titles = {first[0]["prompt_text"], second[0]["prompt_text"]}
    assert selected_titles == {"我的消费观好像在被刷新", "奶粉这钱省不了"}
    assert first[0]["dedupe_hash"] != first[0]["source_dedupe_hash"]
    assert second[0]["dedupe_hash"] != second[0]["source_dedupe_hash"]
    assert set(first_meta["prompt_text_by_layer"]["title_shape"]) <= selected_titles
    assert set(second_meta["prompt_text_by_layer"]["title_shape"]) <= selected_titles


def test_title_shape_rejects_safe_title_when_source_context_is_blocked():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "A2断货后只能重新做功课，这段正文不应该作为标题形态进入 prompt。",
                "title": "我的消费观好像在被刷新",
                "tags": ["价格", "选奶"],
                "risk_tags": [],
                "quality_score": 20,
                "dedupe_hash": "title-safe-body-blocked",
            }
        ],
        query_text="孩子容易中招，选奶看保护力",
        note_count=1,
        comment_count=0,
        title_shape_count=1,
        exclude_terms=["A2", "断货"],
    )

    assert selected == []
    assert meta["selected"]["title_shape"] == 0


def test_title_shape_uses_curated_prompt_text_even_when_raw_title_is_blocked():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "结果前置型标题：把妈妈关心的状态放前面，但不要写成保证句。",
                "prompt_text": "结果前置型标题：把妈妈关心的状态放前面，但不要写成保证句。",
                "prompt_text_source": "curated_real_ugc_wangyue_title_reference_v1",
                "title": "a2联名礼盒挖到宝",
                "raw_title": "a2联名礼盒挖到宝",
                "source_keyword": "儿童奶粉 少请假",
                "tags": ["标题形态", "结果前置型"],
                "risk_tags": [],
                "quality_score": 20,
                "dedupe_hash": "curated-title-shape",
                "example_layer": "title_shape",
                "layer_reason": "curated_real_ugc_title_reference:shape_only",
            }
        ],
        query_text="孩子容易中招，选奶看保护力",
        note_count=1,
        comment_count=0,
        title_shape_count=1,
        exclude_terms=["a2", "联名"],
    )

    assert selected[0]["example_layer"] == "title_shape"
    assert selected[0]["prompt_text"] == "结果前置型标题：把妈妈关心的状态放前面，但不要写成保证句。"
    assert selected[0]["title"] == ""
    assert meta["selected"]["title_shape"] == 1
    assert meta["prompt_text_by_layer"]["title_shape"] == ["结果前置型标题：把妈妈关心的状态放前面，但不要写成保证句。"]


def test_title_shape_keeps_clean_title_when_source_context_is_clean():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "孩子活动多以后，家里那罐奶粉我会看得更认真一点。",
                "title": "我的消费观好像在被刷新",
                "tags": ["营养"],
                "risk_tags": [],
                "quality_score": 20,
                "dedupe_hash": "title-clean-context",
            }
        ],
        query_text="孩子容易中招，选奶看保护力",
        note_count=1,
        comment_count=0,
        title_shape_count=1,
        exclude_terms=["A2", "断货"],
    )

    assert selected[0]["example_layer"] == "title_shape"
    assert selected[0]["prompt_text"] == "我的消费观好像在被刷新"
    assert meta["selected"]["title_shape"] == 1


def test_select_real_user_examples_avoids_used_route_family_before_reuse():
    items = [
        {
            "source_type": "note",
            "text": "上幼儿园后接触人多，选旺玥就是看中日常保护力。",
            "title": "入园记录",
            "tags": ["幼儿园", "保护力"],
            "risk_tags": [],
            "quality_score": 20,
            "dedupe_hash": "school-route",
        },
        {
            "source_type": "note",
            "text": "户外活动量大以后，妈妈更关注孩子每天那杯奶。",
            "title": "户外记录",
            "tags": ["户外", "营养"],
            "risk_tags": [],
            "quality_score": 16,
            "dedupe_hash": "outdoor-route",
        },
        {
            "source_type": "note",
            "text": "除了贵点没毛病。",
            "title": "短句",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-1",
        },
    ]

    selected, meta = select_real_user_examples(
        items,
        query_text="孩子上幼儿园后容易中招，关注保护力",
        note_count=2,
        comment_count=0,
        route_count=1,
        texture_count=1,
        used_route_families={"school_collective"},
    )

    assert selected[0]["dedupe_hash"] == "outdoor-route"
    assert selected[0]["route_family"] == "outdoor_activity"
    assert meta["route_family_counts"] == {"outdoor_activity": 1}


def test_select_real_user_examples_balances_route_family_counts():
    items = [
        {
            "source_type": "note",
            "text": "选奶做了功课，最后还是看中旺玥的营养。",
            "title": "选奶记录",
            "tags": ["选奶", "营养"],
            "risk_tags": [],
            "quality_score": 30,
            "dedupe_hash": "selection-route",
        },
        {
            "source_type": "note",
            "text": "户外活动量大以后，妈妈更关注孩子每天那杯奶。",
            "title": "户外记录",
            "tags": ["户外", "营养"],
            "risk_tags": [],
            "quality_score": 20,
            "dedupe_hash": "outdoor-route",
        },
    ]

    selected, meta = select_real_user_examples(
        items,
        query_text="孩子成长阶段营养补充，选旺玥",
        note_count=1,
        comment_count=0,
        route_count=1,
        texture_count=0,
        used_route_families={"selection_research": 3, "outdoor_activity": 1},
    )

    assert selected[0]["dedupe_hash"] == "outdoor-route"
    assert selected[0]["route_family"] == "outdoor_activity"
    assert meta["route_family_counts"] == {"outdoor_activity": 1}


def test_route_selection_dedupes_weakened_prompt_text():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "上幼儿园后接触人多，选旺玥就是看中日常保护力。",
                "title": "入园记录1",
                "tags": ["幼儿园", "保护力"],
                "risk_tags": [],
                "quality_score": 20,
                "dedupe_hash": "school-route-1",
            },
            {
                "source_type": "note",
                "text": "孩子上学以后接触人多，我选奶会多看保护力。",
                "title": "入园记录2",
                "tags": ["幼儿园", "保护力"],
                "risk_tags": [],
                "quality_score": 19,
                "dedupe_hash": "school-route-2",
            },
        ],
        query_text="孩子上学容易中招 保护力",
        note_count=2,
        comment_count=0,
        route_count=2,
        texture_count=0,
    )

    assert len(selected) == 1
    assert meta["prompt_text_by_layer"]["route"] == ["上学后接触人多；担心容易中招，关注保护力"]


def test_route_family_prefers_prompt_text_over_tags():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "娃长身体这阵补营养就选的它。",
                "title": "记录",
                "tags": ["幼儿园", "营养"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "nutrition-route",
            }
        ],
        query_text="营养补充",
        note_count=1,
        comment_count=0,
        route_count=1,
        texture_count=0,
    )

    assert selected[0]["route_family"] == "nutrition_growth"
    assert meta["route_family_counts"] == {"nutrition_growth": 1}


def test_curated_route_prompt_text_and_family_override_are_used():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "原文里有很多广告和清单内容，不能直接进 prompt。",
                "prompt_text": "兴趣班人多，选旺玥时我会先看保护力",
                "prompt_text_source": "manual_curation",
                "route_family": "interest_collective",
                "title": "记录",
                "tags": ["幼儿园", "保护力"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "curated-route",
                "example_layer": "route",
                "layer_reason": "curated_route:interest_collective",
            }
        ],
        query_text="容易中招 保护力",
        note_count=1,
        comment_count=0,
        route_count=1,
        texture_count=0,
    )

    assert selected[0]["prompt_text"] == "兴趣班人多，选旺玥时我会先看保护力"
    assert selected[0]["route_family"] == "interest_collective"
    assert meta["route_family_counts"] == {"interest_collective": 1}


def test_real_ugc_route_prompt_text_is_preserved():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "我们也是旺玥，妥妥的幼儿园全勤孩子。",
                "prompt_text": "我们也是旺玥，妥妥的幼儿园全勤孩子。",
                "route_family": "row2_real_strong_feedback",
                "title": "真实反馈",
                "tags": ["幼儿园", "保护力"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "real-ugc-route",
                "example_layer": "route",
                "layer_reason": "real_ugc_sellpoint_row64",
            }
        ],
        query_text="上学 接触多 保护力",
        note_count=1,
        comment_count=0,
        route_count=1,
        texture_count=0,
        route_family_include=["row2_real_strong_feedback"],
    )

    assert selected[0]["prompt_text"] == "我们也是旺玥，妥妥的幼儿园全勤孩子。"
    assert selected[0]["route_family"] == "row2_real_strong_feedback"
    assert meta["prompt_text_by_layer"]["route"] == ["我们也是旺玥，妥妥的幼儿园全勤孩子。"]
    assert meta["route_family_counts"] == {"row2_real_strong_feedback": 1}


def test_curated_route_with_eye_brain_and_protection_keeps_entry_anchor():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "原文里有选奶和成分表过程，不直接进 prompt。",
                "prompt_text": "选儿童奶粉时会看成分，旺玥同时关注保护力和眼脑营养",
                "prompt_text_source": "manual_curation",
                "route_family": "selection_research",
                "title": "记录",
                "tags": ["选奶", "成分", "保护力", "眼脑"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "curated-eye-protection-route",
                "example_layer": "route",
                "layer_reason": "curated_route:selection_research",
            }
        ],
        query_text="保护力 眼脑营养",
        note_count=1,
        comment_count=0,
        route_count=1,
        texture_count=0,
    )

    assert selected[0]["prompt_text"] == "选儿童奶粉时会看成分，旺玥同时关注保护力和眼脑营养"
    assert meta["prompt_text_by_layer"]["route"] == ["选儿童奶粉时会看成分，旺玥同时关注保护力和眼脑营养"]


def test_curated_route_with_nutrition_and_growth_keeps_entry_anchor():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "原文里有选奶和喝奶接受过程，不直接进 prompt。",
                "prompt_text": "孩子成长阶段更关注日常营养补充，营养跟上了小身板也结实",
                "prompt_text_source": "manual_curation",
                "route_family": "nutrition_growth",
                "title": "记录",
                "tags": ["营养", "成长"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "curated-growth-nutrition-route",
                "example_layer": "route",
                "layer_reason": "curated_route:nutrition_growth",
            }
        ],
        query_text="营养补充 成长",
        note_count=1,
        comment_count=0,
        route_count=1,
        texture_count=0,
    )

    assert selected[0]["prompt_text"] == "孩子成长阶段更关注日常营养补充，营养跟上了小身板也结实"
    assert meta["prompt_text_by_layer"]["route"] == ["孩子成长阶段更关注日常营养补充，营养跟上了小身板也结实"]


def test_route_selection_can_include_specific_route_families():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "原文不直接进 prompt。",
                "prompt_text": "上学以后接触的人多，选旺玥主要看保护力",
                "prompt_text_source": "manual_curation",
                "route_family": "school_collective",
                "title": "记录",
                "tags": ["幼儿园", "保护力"],
                "risk_tags": [],
                "quality_score": 40,
                "dedupe_hash": "school-route",
                "example_layer": "route",
                "layer_reason": "curated_route:school_collective",
            },
            {
                "source_type": "note",
                "text": "原文不直接进 prompt。",
                "prompt_text": "看儿童奶粉时，我会先看保护力，再看眼脑营养是不是一起顾到",
                "prompt_text_source": "manual_curation",
                "route_family": "selection_research",
                "title": "记录",
                "tags": ["选奶", "保护力", "营养", "成分"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "selection-route",
                "example_layer": "route",
                "layer_reason": "curated_route:selection_research",
            },
        ],
        query_text="保护力 眼脑营养",
        note_count=1,
        comment_count=0,
        route_count=1,
        texture_count=0,
        route_family_include=["selection_research"],
        route_prompt_include_terms=["眼脑"],
    )

    assert selected[0]["dedupe_hash"] == "selection-route"
    assert selected[0]["prompt_text"] == "看儿童奶粉时，我会先看保护力，再看眼脑营养是不是一起顾到"
    assert meta["route_family_include"] == ["selection_research"]
    assert meta["route_prompt_include_terms"] == ["眼脑"]


def test_route_selection_can_exclude_prompt_terms_after_weakened_view():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "原文不直接进 prompt。",
                "prompt_text": "孩子吃饭挑挑拣拣，我选旺玥是想把营养和保护力一起顾到",
                "prompt_text_source": "manual_curation",
                "route_family": "picky_acceptance",
                "title": "记录",
                "tags": ["营养", "保护力"],
                "risk_tags": [],
                "quality_score": 40,
                "dedupe_hash": "mixed-route",
                "example_layer": "route",
                "layer_reason": "curated_route:picky_acceptance",
            },
            {
                "source_type": "note",
                "text": "原文不直接进 prompt。",
                "prompt_text": "孩子成长阶段更关注日常营养补充，营养跟上了小身板也结实",
                "prompt_text_source": "manual_curation",
                "route_family": "nutrition_growth",
                "title": "记录",
                "tags": ["营养", "成长"],
                "risk_tags": [],
                "quality_score": 20,
                "dedupe_hash": "nutrition-route",
                "example_layer": "route",
                "layer_reason": "curated_route:nutrition_growth",
            },
        ],
        query_text="营养 成长",
        note_count=1,
        comment_count=0,
        route_count=1,
        texture_count=0,
        route_family_include=["picky_acceptance", "nutrition_growth"],
        route_prompt_exclude_terms=["保护力", "中招"],
    )

    assert selected[0]["dedupe_hash"] == "nutrition-route"
    assert selected[0]["prompt_text"] == "孩子成长阶段更关注日常营养补充，营养跟上了小身板也结实"
    assert meta["route_prompt_exclude_terms"] == ["中招", "保护力"]


def test_detail_selection_can_filter_prompt_terms():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "看成分表看到头大，配料到底干嘛用的我也没看懂。",
                "title": "记录",
                "tags": ["营养"],
                "risk_tags": [],
                "quality_score": 80,
                "dedupe_hash": "ingredient-detail",
                "example_layer": "detail",
                "layer_reason": "curated_detail:test",
            },
            {
                "source_type": "note",
                "text": "一天至少两大杯旺玥。",
                "title": "记录",
                "tags": ["营养", "保护力"],
                "risk_tags": [],
                "quality_score": 20,
                "dedupe_hash": "two-cups-detail",
                "example_layer": "detail",
                "layer_reason": "curated_detail:test",
            },
        ],
        query_text="营养 保护力",
        note_count=1,
        comment_count=0,
        route_count=0,
        detail_count=1,
        texture_count=0,
        detail_prompt_include_terms=["两大杯"],
        detail_prompt_exclude_terms=["配料"],
    )

    assert selected[0]["dedupe_hash"] == "two-cups-detail"
    assert selected[0]["prompt_text"] == "一天至少两大杯旺玥"
    assert meta["detail_prompt_include_terms"] == ["两大杯"]
    assert meta["detail_prompt_exclude_terms"] == ["配料"]


def test_detail_selection_can_filter_detail_family():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "看成分表看到头大，配料到底干嘛用的我也没看懂。",
                "title": "记录",
                "tags": ["营养"],
                "risk_tags": [],
                "quality_score": 90,
                "dedupe_hash": "ingredient-detail",
                "example_layer": "detail",
                "detail_family": "ingredient_note",
                "layer_reason": "curated_detail:test",
            },
            {
                "source_type": "note",
                "text": "上幼儿园第二学期快结束了，只请过8天假。",
                "title": "记录",
                "tags": ["幼儿园", "保护力"],
                "risk_tags": ["强功效"],
                "quality_score": 20,
                "dedupe_hash": "absence-detail",
                "example_layer": "detail",
                "detail_family": "row2_real_life_grain",
                "layer_reason": "curated_detail:test",
            },
        ],
        query_text="保护力 幼儿园",
        note_count=1,
        comment_count=0,
        route_count=0,
        detail_count=1,
        texture_count=0,
        detail_family_include=["row2_real_life_grain"],
    )

    assert selected[0]["dedupe_hash"] == "absence-detail"
    assert selected[0]["detail_family"] == "row2_real_life_grain"
    assert meta["detail_family_include"] == ["row2_real_life_grain"]
    assert meta["detail_family_counts"] == {"row2_real_life_grain": 1}


def test_detail_selection_checks_exclude_terms_against_prompt_view():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "原文里有宝宝和转奶这些噪音，但不进入 prompt。",
                "prompt_text": "玩嗨了回来，状态还能继续在线。",
                "title": "记录",
                "tags": ["户外", "保护力"],
                "risk_tags": [],
                "quality_score": 20,
                "dedupe_hash": "safe-prompt-detail",
                "example_layer": "detail",
                "detail_family": "row2_real_life_grain",
                "layer_reason": "curated_detail:test",
            },
        ],
        query_text="户外 保护力",
        note_count=1,
        comment_count=0,
        route_count=0,
        detail_count=1,
        texture_count=0,
        exclude_terms=["宝宝", "转奶"],
        detail_family_include=["row2_real_life_grain"],
    )

    assert selected[0]["dedupe_hash"] == "safe-prompt-detail"
    assert selected[0]["prompt_text"] == "玩嗨了回来，状态还能继续在线。"
    assert meta["detail_family_counts"] == {"row2_real_life_grain": 1}


def test_route_selection_prefers_curated_prompt_view_over_raw_high_score_route():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "黄金成长奶粉清单，DHA燕窝酸乳铁蛋白全都安排上，闭眼入不踩坑。",
                "title": "广告路线",
                "tags": ["营养", "保护力"],
                "risk_tags": ["广告口吻"],
                "quality_score": 80,
                "dedupe_hash": "raw-ad-route",
            },
            {
                "source_type": "note",
                "text": "原文保留，不直接进入 prompt。",
                "prompt_text": "上学以后接触的人多，选旺玥主要看保护力",
                "prompt_text_source": "manual_curation",
                "route_family": "school_collective",
                "title": "记录",
                "tags": ["幼儿园", "保护力"],
                "risk_tags": [],
                "quality_score": 10,
                "dedupe_hash": "curated-route",
                "example_layer": "route",
                "layer_reason": "curated_route:school_collective",
            },
        ],
        query_text="容易中招 保护力",
        note_count=1,
        comment_count=0,
        route_count=1,
        texture_count=0,
    )

    assert selected[0]["dedupe_hash"] == "curated-route"
    assert selected[0]["prompt_text"] == "上学以后接触的人多，选旺玥主要看保护力"
    assert meta["route_family_counts"] == {"school_collective": 1}


def test_route_selection_reuses_curated_prompt_view_before_raw_route():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "黄金成长奶粉清单，DHA燕窝酸乳铁蛋白全都安排上，闭眼入不踩坑。",
                "title": "广告路线",
                "tags": ["营养", "保护力"],
                "risk_tags": ["广告口吻"],
                "quality_score": 80,
                "dedupe_hash": "raw-ad-route",
            },
            {
                "source_type": "note",
                "text": "原文保留，不直接进入 prompt。",
                "prompt_text": "上学以后接触的人多，选旺玥主要看保护力",
                "prompt_text_source": "manual_curation",
                "route_family": "school_collective",
                "title": "记录",
                "tags": ["幼儿园", "保护力"],
                "risk_tags": [],
                "quality_score": 10,
                "dedupe_hash": "curated-route",
                "example_layer": "route",
                "layer_reason": "curated_route:school_collective",
            },
        ],
        query_text="容易中招 保护力",
        note_count=1,
        comment_count=0,
        route_count=1,
        texture_count=0,
        used_dedupe_hashes={"curated-route"},
    )

    assert selected[0]["dedupe_hash"] == "curated-route"
    assert meta["fallback_reused_dedupe_hashes"] == ["curated-route"]


def test_opening_selection_uses_explicit_opening_instead_of_texture():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "童童吃饭除了没那么喜欢绿叶菜以外，一直没什么问题，饭量大，爱吃鸡蛋芝士牛肉蛋白质等等。",
                "title": "原文开头",
                "tags": ["挑食", "营养"],
                "risk_tags": [],
                "quality_score": 80,
                "dedupe_hash": "raw-opening",
            },
            {
                "source_type": "note",
                "text": "我都不是很懂，对比来对比去也没对比个所以然来。",
                "title": "真人开头",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 10,
                "dedupe_hash": "curated-texture",
                "example_layer": "texture",
                "layer_reason": "curated_real_ugc_case_row:25",
            },
            {
                "source_type": "note",
                "text": "又开一听新的旺玥奶粉。",
                "title": "真人开头",
                "tags": ["母婴奶粉"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "curated-opening",
                "example_layer": "opening_texture",
                "layer_reason": "curated_real_ugc_opening_row:14",
            },
        ],
        query_text="营养补充",
        note_count=1,
        comment_count=0,
        route_count=0,
        texture_count=0,
        opening_count=1,
    )

    assert selected[0]["dedupe_hash"] == "curated-opening"
    assert selected[0]["prompt_text"] == "又开一听新的旺玥奶粉"
    assert meta["prompt_text_by_layer"]["opening_texture"] == ["又开一听新的旺玥奶粉"]


def test_opening_selection_does_not_treat_route_or_texture_as_opening():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "童童吃饭除了没那么喜欢绿叶菜以外，一直没什么问题，饭量大，爱吃鸡蛋芝士牛肉蛋白质等等。",
                "prompt_text": "孩子吃饭挑挑拣拣，我选旺玥是想把营养和保护力一起顾到",
                "prompt_text_source": "manual_curation",
                "route_family": "picky_acceptance",
                "title": "人工 route",
                "tags": ["挑食", "营养"],
                "risk_tags": [],
                "quality_score": 80,
                "dedupe_hash": "curated-route-raw-opening",
                "example_layer": "route",
                "layer_reason": "curated_route:picky_acceptance",
            },
            {
                "source_type": "note",
                "text": "好烦，我真的比不来这些小孩子的东西噱头真多啊。",
                "title": "真人开头",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 10,
                "dedupe_hash": "curated-opening",
                "example_layer": "texture",
                "layer_reason": "curated_real_ugc_case_row:25",
            },
        ],
        query_text="营养补充",
        note_count=1,
        comment_count=0,
        route_count=0,
        texture_count=0,
        opening_count=1,
    )

    assert selected == []
    assert meta["selected"]["opening_texture"] == 0


def test_texture_selection_does_not_reuse_curated_prompt_view_before_raw_texture():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "身高没啥太大的变化，就是免疫力提高了不少。",
                "title": "功效片段",
                "tags": ["成长", "保护力"],
                "risk_tags": ["强功效"],
                "quality_score": 80,
                "dedupe_hash": "raw-texture",
            },
            {
                "source_type": "note",
                "text": "除了贵，没毛病。",
                "title": "真人口气",
                "tags": ["价格"],
                "risk_tags": [],
                "quality_score": 10,
                "dedupe_hash": "curated-texture",
                "example_layer": "texture",
                "layer_reason": "curated_real_ugc_case_row:12",
            },
        ],
        query_text="保护力",
        note_count=1,
        comment_count=0,
        route_count=0,
        texture_count=1,
        used_dedupe_hashes={"curated-texture"},
    )

    assert selected == []
    assert meta["selected"]["texture"] == 0
    assert meta["fallback_reused_dedupe_hashes"] == []


def test_route_prompt_blocks_explicit_age_and_school_stage():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "3-6 岁真是关键阶段，旺玥营养挺全。",
                "title": "阶段记录",
                "tags": ["营养"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "age-route",
            },
            {
                "source_type": "note",
                "text": "娃初中开始补营养就选的它。",
                "title": "学段记录",
                "tags": ["营养"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "school-stage-route",
            },
            {
                "source_type": "note",
                "text": "有沒有在喝這款奶粉的呀 小孩幾歲開始喝。",
                "title": "问法",
                "tags": ["保护力"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "question-route",
            },
            {
                "source_type": "note",
                "text": "晚自习刷题能跟上老师思路，营养补充确实要认真看。",
                "title": "学业记录",
                "tags": ["营养"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "study-route",
            },
        ],
        query_text="营养补充",
        note_count=1,
        comment_count=0,
        route_count=1,
        texture_count=0,
    )

    assert selected == []
    assert meta["selected"]["route"] == 0


def test_route_layer_can_salvage_safe_snippet_from_rejected_note():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "宝宝这个词只在前面出现。孩子上幼儿园后容易中招，妈妈就会重新看奶粉。",
                "title": "记录",
                "tags": ["幼儿园", "保护力"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "salvaged-route",
            },
            {
                "source_type": "note",
                "text": "宝宝这个词只在前面出现。普通聊天没有明确路线。",
                "title": "记录",
                "tags": ["营养"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "unsafe-fallback",
            },
        ],
        query_text="容易中招 幼儿园",
        note_count=1,
        comment_count=0,
        route_count=1,
        texture_count=0,
    )

    assert selected[0]["dedupe_hash"] == "salvaged-route"
    assert selected[0]["prompt_text"] == "上学后接触人多；担心容易中招，关注保护力"
    assert selected[0]["route_family"] == "school_collective"
    assert meta["selected"]["route"] == 1


def test_route_layer_does_not_fallback_to_professional_ad_fragment():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "针对眼脑发育更是用心，P磷脂酰丝氨酸S+DHA协同作用，对大脑很友好。",
                "title": "成分记录",
                "tags": ["营养", "成分"],
                "risk_tags": [],
                "quality_score": 20,
                "dedupe_hash": "professional-ad-route",
            },
            {
                "source_type": "note",
                "text": "孩子活动量大以后，选奶我会多看保护力和日常营养。",
                "title": "日常记录",
                "tags": ["保护力", "营养", "户外"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "daily-route",
            },
        ],
        query_text="活动量 保护力",
        note_count=1,
        comment_count=0,
        route_count=1,
        texture_count=0,
    )

    assert [item["dedupe_hash"] for item in selected] == ["daily-route"]
    assert selected[0]["prompt_text"] == "户外活动多、活动量大；担心容易中招，关注保护力"
    assert meta["selected"]["route"] == 1


def test_prompt_views_filter_ad_route_and_texture_pollutants():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "娃天天在户外疯跑撒欢，抵抗力差的话特别容易中招，终于挖到了皇家美素佳儿旺玥儿童营养奶粉。",
                "title": "广告路线",
                "tags": ["户外", "保护力", "营养"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "ad-route",
            },
            {
                "source_type": "note",
                "text": "孩子活动量大以后，我选奶会多看保护力和日常营养。",
                "title": "日常路线",
                "tags": ["户外", "保护力", "营养"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "safe-route",
            },
            {
                "source_type": "note",
                "text": "值得信赖的大品牌，非广，我个人也非专业人士，普通顾客对比选择后分享出思考过程而已。",
                "title": "广告口气",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 28,
                "dedupe_hash": "ad-texture",
            },
            {
                "source_type": "note",
                "text": "好烦，我真的比不来这些小孩子的东西噱头真多啊。",
                "title": "真人口气",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 10,
                "dedupe_hash": "safe-texture",
            },
        ],
        query_text="户外活动量大，保护力",
        note_count=2,
        comment_count=0,
        route_count=1,
        texture_count=1,
    )

    route_prompt = meta["prompt_text_by_layer"]["route"][0]
    assert route_prompt in {
        "户外活动多、活动量大；担心容易中招，关注保护力",
        "担心容易中招，关注保护力",
    }
    assert "挖到" not in route_prompt
    assert "儿童营养奶粉" not in route_prompt
    assert selected[1]["dedupe_hash"] == "safe-texture"
    assert meta["prompt_text_by_layer"]["texture"] == ["好烦，我真的比不来这些小孩子的东西噱头真多啊"]


def test_prompt_views_filter_formula_qa_and_comment_like_pollutants():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "如果是喝儿童成长奶粉的话，上面只写早晚各一次，我家的奶瘾大，一天喝3，4顿。",
                "title": "说明书问答",
                "tags": ["保护力"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "dosage-qa-route",
            },
            {
                "source_type": "note",
                "text": "5种HMO：营养全面，助力成长。",
                "title": "配方清单",
                "tags": ["营养", "成分"],
                "risk_tags": [],
                "quality_score": 29,
                "dedupe_hash": "formula-list-route",
            },
            {
                "source_type": "note",
                "text": "新一代皇家突破性营养配方，不额外添加蔗糖与香精，天然奶香、口味清淡，妈妈的首选。",
                "title": "广告配方",
                "tags": ["营养", "成分"],
                "risk_tags": [],
                "quality_score": 28,
                "dedupe_hash": "brand-ad-route",
            },
            {
                "source_type": "note",
                "text": "加上学龄前期正是大脑、视力快速发育的关键期。",
                "title": "阶段科普",
                "tags": ["成长", "成分"],
                "risk_tags": [],
                "quality_score": 27,
                "dedupe_hash": "stage-route",
            },
            {
                "source_type": "note",
                "text": "孩子上学以后接触人多，我选奶会多看保护力和日常营养。",
                "title": "日常路线",
                "tags": ["幼儿园", "保护力", "营养"],
                "risk_tags": [],
                "quality_score": 10,
                "dedupe_hash": "safe-route",
            },
            {
                "source_type": "note",
                "text": "有姐妹给点建议吗。",
                "title": "问答口气",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 20,
                "dedupe_hash": "comment-texture",
            },
            {
                "source_type": "note",
                "text": "需要的小红薯可以参考一下（纯个人的感受哈~~~）。",
                "title": "平台口气",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 19,
                "dedupe_hash": "platform-texture",
            },
            {
                "source_type": "note",
                "text": "我都不是很懂。",
                "title": "短句",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 8,
                "dedupe_hash": "safe-texture",
            },
        ],
        query_text="上学 容易中招 保护力",
        note_count=2,
        comment_count=0,
        route_count=1,
        texture_count=1,
    )

    assert [item["dedupe_hash"] for item in selected] == ["safe-route", "safe-texture"]
    assert meta["prompt_text_by_layer"]["route"] == ["上学后接触人多；担心容易中招，关注保护力"]
    assert meta["prompt_text_by_layer"]["texture"] == ["我都不是很懂"]


def test_opening_layer_filters_service_ad_and_ai_closure_fragments():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "如果您有好的建议或相关经验，欢迎留言。",
                "title": "留言",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "service-opening",
            },
            {
                "source_type": "note",
                "text": "皇家美素佳儿旺玥儿童营养奶粉，顶级儿童粉配方。",
                "title": "配方",
                "tags": ["营养", "成分"],
                "risk_tags": [],
                "quality_score": 28,
                "dedupe_hash": "ad-opening",
            },
            {
                "source_type": "note",
                "text": "配方选对，带娃真的省心很多。",
                "title": "省心",
                "tags": ["保护力"],
                "risk_tags": [],
                "quality_score": 26,
                "dedupe_hash": "closure-opening",
            },
            {
                "source_type": "note",
                "text": "说实话，选奶这件事真的会越看越纠结。",
                "title": "选奶",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "real-opening",
                "example_layer": "opening_texture",
                "layer_reason": "curated_opening:test",
            },
        ],
        query_text="选奶 营养",
        note_count=1,
        comment_count=0,
        route_count=0,
        texture_count=0,
        opening_count=1,
    )

    assert [item["dedupe_hash"] for item in selected] == ["real-opening"]
    assert selected[0]["prompt_text"] == "说实话，选奶这件事真的会越看越纠结"
    assert meta["selected"]["opening_texture"] == 1


def test_texture_selection_does_not_reuse_hash_when_layer_pool_is_exhausted():
    items = [
        {
            "source_type": "note",
            "text": "上幼儿园后接触人多，选旺玥就是看中日常保护力。",
            "title": "入园记录",
            "tags": ["幼儿园", "保护力"],
            "risk_tags": [],
            "quality_score": 16,
            "dedupe_hash": "route-1",
        },
        {
            "source_type": "note",
            "text": "除了贵点没毛病。",
            "title": "短句",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-1",
        },
    ]

    selected, meta = select_real_user_examples(
        items,
        query_text="营养补充",
        note_count=1,
        comment_count=0,
        route_count=0,
        texture_count=1,
        used_dedupe_hashes={"texture-1"},
    )

    assert selected == []
    assert meta["selected"]["texture"] == 0
    assert meta["fallback_reused_dedupe_hashes"] == []


def test_texture_selection_does_not_reuse_same_prompt_text_from_different_sources():
    items = [
        {
            "source_type": "note",
            "text": "除了贵，其他都还行。",
            "title": "短句1",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-source-1",
        },
        {
            "source_type": "note",
            "text": "除了贵。",
            "title": "短句2",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 11,
            "dedupe_hash": "texture-source-2",
        },
    ]
    used_hashes: set[str] = set()

    first, _ = select_real_user_examples(
        items,
        query_text="营养补充",
        note_count=1,
        comment_count=0,
        route_count=0,
        texture_count=1,
        used_dedupe_hashes=used_hashes,
    )
    second, meta = select_real_user_examples(
        items,
        query_text="营养补充",
        note_count=1,
        comment_count=0,
        route_count=0,
        texture_count=1,
        used_dedupe_hashes=used_hashes,
    )

    assert first[0]["prompt_text"] == "除了贵"
    assert second == []
    assert meta["selected"]["texture"] == 0


def test_texture_selection_falls_back_to_safe_uncurated_after_curated_used():
    items = [
        {
            "source_type": "note",
            "text": "好烦，我真的比不来这些小孩子的东西噱头真多啊",
            "prompt_text": "好烦，我真的比不来这些小孩子的东西噱头真多啊",
            "title": "短句1",
            "tags": ["选奶"],
            "risk_tags": [],
            "quality_score": 14,
            "dedupe_hash": "curated-texture",
            "example_layer": "texture",
            "layer_reason": "curated_texture",
        },
        {
            "source_type": "note",
            "text": "我都不是很懂，对比来对比去也没对比个所以然来",
            "title": "短句2",
            "tags": ["选奶"],
            "risk_tags": [],
            "quality_score": 13,
            "dedupe_hash": "uncurated-texture",
            "example_layer": "texture",
        },
    ]
    used_hashes: set[str] = set()

    first, _ = select_real_user_examples(
        items,
        query_text="选奶",
        note_count=1,
        comment_count=0,
        route_count=0,
        texture_count=1,
        used_dedupe_hashes=used_hashes,
    )
    second, meta = select_real_user_examples(
        items,
        query_text="选奶",
        note_count=1,
        comment_count=0,
        route_count=0,
        texture_count=1,
        used_dedupe_hashes=used_hashes,
    )

    assert first[0]["dedupe_hash"] == "curated-texture"
    assert second[0]["dedupe_hash"] == "uncurated-texture"
    assert second[0]["prompt_text"] == "我都不是很懂"
    assert meta["selected"]["texture"] == 1


def test_prompt_family_stack_avoid_prefers_non_selection_texture_after_selection_route():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "选奶粉这事我绕不开保护力，旺玥就是这样进备选的",
                "prompt_text": "选奶粉这事我绕不开保护力，旺玥就是这样进备选的",
                "title": "",
                "tags": ["保护力", "选奶"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "route-selection",
                "example_layer": "route",
                "route_family": "daily_protection",
                "layer_reason": "manual_route",
            },
            {
                "source_type": "note",
                "text": "我都不是很懂，对比来对比去也没对比个所以然来",
                "prompt_text": "我都不是很懂，对比来对比去也没对比个所以然来",
                "title": "",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 25,
                "dedupe_hash": "texture-selection",
                "example_layer": "texture",
                "layer_reason": "curated_texture",
            },
            {
                "source_type": "note",
                "text": "刚开始喝，还不知道如何",
                "prompt_text": "刚开始喝，还不知道如何",
                "title": "",
                "tags": ["母婴奶粉"],
                "risk_tags": [],
                "quality_score": 10,
                "dedupe_hash": "texture-plain",
                "example_layer": "texture",
                "layer_reason": "curated_texture",
            },
        ],
        query_text="精力不足，保护力和眼脑营养",
        note_count=2,
        comment_count=0,
        route_count=1,
        texture_count=1,
        prompt_family_stack_avoid=["selection_process"],
    )

    assert [item["dedupe_hash"] for item in selected] == ["route-selection", "texture-plain"]
    assert meta["prompt_family_stack_avoid"] == ["selection_process"]
    assert meta["prompt_family_counts"]["selection_process"] == 1


def test_prompt_family_stack_avoid_falls_back_when_only_stacked_family_available():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "选奶粉这事我绕不开保护力，旺玥就是这样进备选的",
                "prompt_text": "选奶粉这事我绕不开保护力，旺玥就是这样进备选的",
                "title": "",
                "tags": ["保护力", "选奶"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "route-selection",
                "example_layer": "route",
                "route_family": "daily_protection",
                "layer_reason": "manual_route",
            },
            {
                "source_type": "note",
                "text": "我都不是很懂，对比来对比去也没对比个所以然来",
                "prompt_text": "我都不是很懂，对比来对比去也没对比个所以然来",
                "title": "",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 25,
                "dedupe_hash": "texture-selection",
                "example_layer": "texture",
                "layer_reason": "curated_texture",
            },
        ],
        query_text="精力不足，保护力和眼脑营养",
        note_count=2,
        comment_count=0,
        route_count=1,
        texture_count=1,
        prompt_family_stack_avoid=["selection_process"],
    )

    assert [item["dedupe_hash"] for item in selected] == ["route-selection", "texture-selection"]
    assert meta["prompt_family_counts"]["selection_process"] == 2


def test_prompt_family_stack_avoid_prefers_non_sellpoint_pairing_texture():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "孩子活动多以后，我会把保护力和眼脑营养一起看",
                "prompt_text": "孩子活动多以后，我会把保护力和眼脑营养一起看",
                "title": "",
                "tags": ["保护力", "眼脑", "营养"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "route-pairing",
                "example_layer": "route",
                "route_family": "daily_protection",
                "layer_reason": "manual_route",
            },
            {
                "source_type": "note",
                "text": "保护力和眼脑这两块我都会一起看",
                "prompt_text": "保护力和眼脑这两块我都会一起看",
                "title": "",
                "tags": ["保护力", "眼脑"],
                "risk_tags": [],
                "quality_score": 25,
                "dedupe_hash": "texture-pairing",
                "example_layer": "texture",
                "layer_reason": "curated_texture",
            },
            {
                "source_type": "note",
                "text": "活动量上来以后，我不太敢只看孩子跑得欢不欢",
                "prompt_text": "活动量上来以后，我不太敢只看孩子跑得欢不欢",
                "title": "",
                "tags": ["户外"],
                "risk_tags": [],
                "quality_score": 10,
                "dedupe_hash": "texture-activity",
                "example_layer": "texture",
                "layer_reason": "curated_texture",
            },
        ],
        query_text="精力不足，保护力和眼脑营养",
        note_count=2,
        comment_count=0,
        route_count=1,
        texture_count=1,
        prompt_family_stack_avoid=["sellpoint_pairing"],
    )

    assert [item["dedupe_hash"] for item in selected] == ["route-pairing", "texture-activity"]
    assert meta["prompt_family_stack_avoid"] == ["sellpoint_pairing"]
    assert meta["prompt_family_counts"]["sellpoint_pairing"] == 1


def test_prompt_family_include_exclude_filters_texture_without_blocking_title_shape():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "带娃日常",
                "prompt_text": "带娃日常",
                "title": "带娃日常",
                "tags": ["母婴奶粉"],
                "risk_tags": [],
                "quality_score": 10,
                "dedupe_hash": "title-plain",
                "example_layer": "title_shape",
                "layer_reason": "curated_title_shape",
            },
            {
                "source_type": "note",
                "text": "写得可能有点碎，但真实带娃本来就挺碎。",
                "prompt_text": "写得可能有点碎，但真实带娃本来就挺碎。",
                "title": "",
                "tags": ["母婴奶粉"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "texture-pure",
                "example_layer": "texture",
                "layer_reason": "curated_texture",
            },
            {
                "source_type": "note",
                "text": "当妈以后才发现，小孩每天也有自己的小世界。",
                "prompt_text": "当妈以后才发现，小孩每天也有自己的小世界。",
                "title": "",
                "tags": ["母婴奶粉"],
                "risk_tags": [],
                "quality_score": 25,
                "dedupe_hash": "texture-observation",
                "example_layer": "texture",
                "layer_reason": "curated_texture",
            },
            {
                "source_type": "note",
                "text": "除了贵没毛病，选奶粉这事我还是纠结了很久。",
                "prompt_text": "除了贵没毛病，选奶粉这事我还是纠结了很久。",
                "title": "",
                "tags": ["选奶", "价格"],
                "risk_tags": [],
                "quality_score": 40,
                "dedupe_hash": "texture-product",
                "example_layer": "texture",
                "layer_reason": "curated_texture",
            },
            {
                "source_type": "note",
                "text": "睡前那杯喝完以后，我心里踏实不少。",
                "prompt_text": "睡前那杯喝完以后，我心里踏实不少。",
                "title": "",
                "tags": ["母婴奶粉"],
                "risk_tags": [],
                "quality_score": 35,
                "dedupe_hash": "texture-milk",
                "example_layer": "texture",
                "layer_reason": "curated_texture",
            },
        ],
        query_text="注意力不集中，眼脑营养",
        note_count=3,
        comment_count=0,
        title_shape_count=1,
        texture_count=2,
        prompt_family_include=["pure_voice", "mom_observation"],
        prompt_family_exclude=["product_decision", "price_complaint", "milk_action", "result_claim"],
    )

    assert [item["example_layer"] for item in selected] == ["title_shape", "texture", "texture"]
    assert [item["dedupe_hash"] for item in selected[1:]] == ["texture-pure", "texture-observation"]
    assert meta["prompt_family_include"] == ["mom_observation", "pure_voice"]
    assert meta["prompt_family_exclude"] == [
        "milk_action",
        "price_complaint",
        "product_decision",
        "result_claim",
    ]
    assert meta["prompt_family_counts"] == {"mom_observation": 1, "pure_voice": 1}


def test_texture_layer_can_use_short_snippet_from_route_note():
    items = [
        {
            "source_type": "note",
            "text": "上幼儿园后接触人多，选旺玥就是看中日常保护力。",
            "title": "入园记录",
            "tags": ["幼儿园", "保护力"],
            "risk_tags": [],
            "quality_score": 16,
            "dedupe_hash": "route-1",
        },
        {
            "source_type": "note",
            "text": "谁懂啊！3岁以后选儿童奶粉真的很头疼，既要看营养，也要看孩子愿不愿意喝。",
            "title": "选奶记录",
            "tags": ["选奶", "营养", "喝奶接受度"],
            "risk_tags": [],
            "quality_score": 16,
            "dedupe_hash": "route-with-texture",
        },
    ]

    selected, meta = select_real_user_examples(
        items,
        query_text="孩子上幼儿园后容易中招，关注保护力",
        note_count=2,
        comment_count=0,
        route_count=1,
        texture_count=1,
    )

    assert [item["example_layer"] for item in selected] == ["route", "texture"]
    assert selected[1]["dedupe_hash"] == "route-with-texture"
    assert selected[1]["prompt_text"] == "谁懂啊"
    assert selected[1]["layer_reason"] == "texture_snippet:谁懂"
    assert meta["layer_counts"] == {"route": 1, "texture": 1}
    assert meta["selected"]["route"] == 1
    assert meta["selected"]["texture"] == 1


def test_texture_layer_filters_short_noise_without_texture_snippet():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "有没有喝皇家旺玥的，打开湿湿的",
                "title": "短问",
                "tags": ["成分"],
                "risk_tags": ["竞品品牌"],
                "quality_score": 12,
                "dedupe_hash": "wet-texture",
            },
            {
                "source_type": "note",
                "text": "嘴巴真刁啊",
                "title": "短句",
                "tags": ["喝奶接受度"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "real-texture",
            },
        ],
        query_text="保护力",
        note_count=1,
        comment_count=0,
        route_count=0,
        texture_count=1,
    )

    assert [item["dedupe_hash"] for item in selected] == ["real-texture"]
    assert meta["selected"]["texture"] == 1


def test_ending_layer_prefers_curated_prompt_text_without_keyword_hit():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "没有什么夸张结论，就当一条日常记录。",
                "prompt_text": "没有什么夸张结论，就当一条日常记录。",
                "title": "",
                "tags": ["营养", "成长", "母婴奶粉"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "curated-ending",
                "example_layer": "ending",
                "layer_reason": "curated ending prompt view",
            },
        ],
        query_text="成长阶段关注日常营养",
        note_count=1,
        comment_count=0,
        route_count=0,
        ending_count=1,
    )

    assert [item["example_layer"] for item in selected] == ["ending"]
    assert selected[0]["prompt_text"] == "没有什么夸张结论，就当一条日常记录。"
    assert selected[0]["layer_reason"] == "curated ending prompt view"
    assert meta["selected"]["ending"] == 1


def test_ending_layer_does_not_reuse_curated_route_prompt_text():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "孩子活动多以后，我会把保护力和眼脑营养一起看",
                "prompt_text": "孩子活动多以后，我会把保护力和眼脑营养一起看",
                "title": "",
                "tags": ["保护力", "眼脑", "营养"],
                "risk_tags": [],
                "quality_score": 30,
                "dedupe_hash": "route-pairing",
                "example_layer": "route",
                "route_family": "daily_protection",
                "layer_reason": "manual_curated_route",
            },
            {
                "source_type": "note",
                "text": "没有什么夸张结论，就当一条日常记录。",
                "prompt_text": "没有什么夸张结论，就当一条日常记录。",
                "title": "",
                "tags": ["营养", "母婴奶粉"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "curated-ending",
                "example_layer": "ending",
                "layer_reason": "curated ending prompt view",
            },
        ],
        query_text="精力不足，保护力和眼脑营养",
        note_count=1,
        comment_count=0,
        route_count=0,
        ending_count=1,
    )

    assert [item["dedupe_hash"] for item in selected] == ["curated-ending"]
    assert meta["prompt_text_by_layer"]["ending"] == ["没有什么夸张结论，就当一条日常记录。"]


def test_opening_layer_prefers_curated_prompt_text_over_raw_text():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "能正常喝，营养也看得过去，我先不折腾。",
                "prompt_text": "营养看得过去，我先不折腾。",
                "title": "",
                "tags": ["营养", "成长", "母婴奶粉"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "curated-opening",
                "example_layer": "ending",
                "layer_reason": "curated ending prompt view",
            },
        ],
        query_text="成长阶段关注日常营养",
        note_count=1,
        comment_count=0,
        route_count=0,
        opening_count=1,
    )

    assert [item["example_layer"] for item in selected] == ["opening_texture"]
    assert selected[0]["prompt_text"] == "营养看得过去，我先不折腾。"
    assert "能正常喝" not in selected[0]["prompt_text"]
    assert meta["prompt_text_by_layer"]["opening_texture"] == ["营养看得过去，我先不折腾。"]


def test_texture_layer_prefers_curated_prompt_text_over_raw_text():
    selected, meta = select_real_user_examples(
        [
            {
                "source_type": "note",
                "text": "嘴巴真刁啊，试了好几个其他品牌全都不喝。",
                "prompt_text": "我都不是很懂。",
                "title": "",
                "tags": ["选奶"],
                "risk_tags": [],
                "quality_score": 12,
                "dedupe_hash": "curated-texture",
                "example_layer": "texture",
                "layer_reason": "curated texture prompt view",
            },
        ],
        query_text="儿童奶粉怎么选",
        note_count=1,
        comment_count=0,
        route_count=0,
        texture_count=1,
    )

    assert [item["example_layer"] for item in selected] == ["texture"]
    assert selected[0]["prompt_text"] == "我都不是很懂。"
    assert "嘴巴真刁" not in selected[0]["prompt_text"]
    assert meta["prompt_text_by_layer"]["texture"] == ["我都不是很懂。"]
