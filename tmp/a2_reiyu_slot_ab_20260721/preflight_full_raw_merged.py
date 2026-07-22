import asyncio
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.content_agent import ContentBatchItem
from app.models.maga_assets import AssetRegistry
from app.services.content_batch_planner import ContentBatchPlanner
from app.services.unified_content_generation_service import UnifiedContentGenerationService


ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
OUTPUT = Path(
    "/Users/luxifa/maga/outputs/a2_reiyu_full_raw_merged_20260721/"
    "a2礼遇UGC分享贴_认可路径分流_真实Prompt预检.md"
)
LOYAL_SLOT_CODES = [
    "content_direction",
    "info_source",
    "participation_motive",
    "activity_content",
    "batch_detection",
    "consumer_recognition",
    "positive_expression",
]
INFORMED_SLOT_CODES = LOYAL_SLOT_CODES[:-1]


async def main() -> None:
    async with async_session_factory() as session:
        asset = (
            (
                await session.execute(
                    select(AssetRegistry)
                    .where(
                        AssetRegistry.asset_key == ASSET_KEY,
                        AssetRegistry.status == "active",
                    )
                    .order_by(AssetRegistry.version_no.desc())
                )
            )
            .scalars()
            .first()
        )
        assert asset is not None
        asset_version = asset.version_no
        asset_status = asset.status
        job = await ContentBatchPlanner(session).create_batch_plan(
            asset_key=ASSET_KEY,
            product_topic=None,
            target_audience="普通宝妈",
            style="纯分享",
            count=16,
            created_by="codex-recognition-route-preflight",
        )
        items = list(
            (
                await session.execute(
                    select(ContentBatchItem)
                    .where(ContentBatchItem.batch_id == job.id)
                    .order_by(ContentBatchItem.item_no)
                )
            )
            .scalars()
            .all()
        )
        rows = []
        multi_prompts = {}
        for item in items:
            plan = dict(item.plan_json or {})
            slots = {slot["slot_code"]: slot["value"] for slot in plan.get("variation_slots") or []}
            is_loyal = plan["business_rule"].endswith("｜老客使用感受")
            is_informed = plan["business_rule"].endswith("｜信息了解后的认可")
            assert is_loyal or is_informed
            assert list(slots) == (LOYAL_SLOT_CODES if is_loyal else INFORMED_SLOT_CODES)
            snapshot = await UnifiedContentGenerationService(session).build_snapshot(
                content_type="article",
                business_rule=plan,
                item_no=item.item_no,
                output_fields=["title", "body"],
                keyword_asset_key=plan.get("keyword_asset_key"),
                model_config=plan.get("model_config") or {},
            )
            prompt = snapshot.input_snapshot["rendered_prompt"]
            ordered_markers = [
                "- 活动名称：会员体系升级。",
                "- 检测承接：活动内容讲完后",
                "- 活动了解途径：",
                "- 参加活动原因：",
                "- 活动内容：",
                "- 批批检素材：",
                "- 认可表达：",
            ]
            if is_loyal:
                ordered_markers.append("- 活动分享正向表达：")
            positions = [prompt.index(marker) for marker in ordered_markers]
            assert positions == sorted(positions)
            assert "活动后的产品体验" not in prompt
            assert "活动后的消费者认可" not in prompt
            assert "抽奖奖品只有旅游基金大奖、金手链、夏凉被" not in prompt
            assert "不得新增、串换奖品" not in prompt
            recognition = slots["consumer_recognition"]
            if is_loyal:
                assert recognition.startswith("认可依据：家里长期喝a2至初后的实际感受。")
                assert "产品体验原话：" in recognition
                assert "推荐态度原话：" in recognition
                assert "品牌感受原话：" not in recognition
                assert "本条认可路径是老客使用感受" in prompt
            else:
                assert recognition.startswith(
                    "认可依据：从本次活动和a2至初每批检测信息形成的品牌感受。"
                )
                assert "品牌感受原话：" in recognition
                assert "产品体验原话：" not in recognition
                assert "推荐态度原话：" not in recognition
                assert "宝宝长期使用结果、转奶或回归经历" in prompt
                assert "活动分享正向表达：" not in prompt
                assert "从本条抽中的正向表达" not in prompt
            rows.append(
                (
                    item.item_no,
                    plan["business_rule"],
                    "老客使用感受" if is_loyal else "信息了解后的认可",
                    slots["content_direction"],
                    slots["info_source"],
                    slots["participation_motive"],
                    slots["activity_content"],
                    recognition,
                )
            )
            if plan["business_rule"].startswith("a2礼遇｜多重福利叠加｜"):
                multi_prompts["老客使用感受" if is_loyal else "信息了解后的认可"] = prompt
                assert slots["info_source"] == "宝爸刷到后跟我说"
                assert slots["activity_content"].startswith("积分、集罐、抽奖、回馈礼都有")
                if is_loyal:
                    assert slots["participation_motive"].startswith("家里本来就一直喝至初")
                else:
                    assert slots["participation_motive"] == "发现这次不是单层福利，想把能参加的都了解清楚。"
                    assert "发现福利不是单层的" in slots["content_direction"]
                assert (
                    "本条主活动是多重福利叠加，可以同时概括抽奖、集罐、积分、老客回馈。"
                ) in prompt
                assert (
                    "每篇只选择一个活动了解途径，不得把多个了解来源叠加成同一次发现经历。"
                ) in prompt
                assert "宝爸看到" not in slots["info_source"]
        assert len(items) == 16
        assert len({row[1] for row in rows}) == 16
        assert set(multi_prompts) == {"老客使用感受", "信息了解后的认可"}
        await session.rollback()

    lines = [
        "# a2礼遇完整原始槽位真实Prompt预检",
        "",
        f"- 资产：`{ASSET_KEY}`，版本：`v{asset_version}`，状态：`{asset_status}`。",
        "- 结果：8类活动拆为16条规则，均通过真实planner和layered_article Prompt组装。",
        "- 槽位顺序：活动名称 → 检测承接 → 活动了解途径 → 参加活动原因 → 活动内容 → 批批检 → 认可表达 → 正向表达。",
        "- 原始内容方向按逻辑分流：老客路径9条，信息认可路径3条；原文未压缩、未改写。",
        "- 老客路径只使用自家产品体验与推荐态度；信息路径只使用活动和每批检测带来的品牌感受。",
        "- ‘准备下单+长期使用结果’、‘转回来了但无转奶经历’等跨身份拼接已从路由层消除。",
        "- 奖品类型与归属的审核规则未注入生文Prompt，继续由审核金标控制。",
        "",
        "| 序号 | 业务规则 | 认可路径 | 原始内容方向 | 原始了解途径 | 原始参加原因 | 原始活动内容 | 本篇认可素材 |",
        "|---:|---|---|---|---|---|---|---|",
    ]
    for item_no, rule, route, direction, source, motive, activity, recognition in rows:
        lines.append(
            f"| {item_no} | {rule} | {route} | {direction.replace(chr(10), '<br>')} | "
            f"{source} | {motive} | {activity} | {recognition.replace(chr(10), '<br>')} |"
        )
    for route in ("老客使用感受", "信息了解后的认可"):
        lines.extend(
            [
                "",
                f"## 多重福利叠加｜{route}｜完整渲染Prompt",
                "",
                "```text",
                multi_prompts[route],
                "```",
            ]
        )
    lines.append("")
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    asyncio.run(main())
