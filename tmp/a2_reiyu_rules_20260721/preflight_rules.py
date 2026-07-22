import asyncio
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.content_agent import ContentBatchItem
from app.services.content_batch_planner import ContentBatchPlanner
from app.services.unified_content_generation_service import UnifiedContentGenerationService


ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
OUTPUT = Path(
    "/Users/luxifa/maga/outputs/a2_reiyu_business_rules_20260721/"
    "a2礼遇UGC分享贴_真实链路预检.md"
)


async def main() -> None:
    async with async_session_factory() as session:
        job = await ContentBatchPlanner(session).create_batch_plan(
            asset_key=ASSET_KEY,
            product_topic=None,
            target_audience="普通宝妈",
            style="纯分享",
            count=8,
            created_by="codex-preflight",
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
        full_prompt = ""
        for item in items:
            plan = dict(item.plan_json or {})
            snapshot = await UnifiedContentGenerationService(session).build_snapshot(
                content_type="article",
                business_rule=plan,
                item_no=item.item_no,
                output_fields=["title", "body"],
                keyword_asset_key=plan.get("keyword_asset_key"),
                model_config=plan.get("model_config") or {},
            )
            prompt = snapshot.input_snapshot["rendered_prompt"]
            slots = {slot["slot_code"]: slot["value"] for slot in plan.get("variation_slots") or []}
            assert list(slots) == [
                "content_direction",
                "info_source",
                "participation_motive",
                "activity_content",
                "batch_detection",
                "product_experience",
                "consumer_praise",
                "positive_expression",
            ]
            assert prompt.index("活动内容：") < prompt.index("批批检素材：")
            assert prompt.index("批批检素材：") < prompt.index("活动后的产品体验：")
            assert snapshot.input_snapshot.get("selected_keywords") == []
            assert snapshot.input_snapshot.get("keyword_asset") is None
            assert '只输出 JSON：{"title":"...","body":"..."}。' in prompt
            rows.append(
                (
                    item.item_no,
                    plan["business_rule"],
                    slots["info_source"],
                    slots["participation_motive"],
                    slots["activity_content"],
                )
            )
            if "12罐" in plan["business_rule"]:
                full_prompt = prompt
                assert slots["info_source"] == "去门店时导购聊到这次升级。"
                assert slots["participation_motive"] == "觉得a2至初花这么大力气升级，挺不错的。"
                assert slots["activity_content"].startswith("认真算了下，集12罐能兑换1罐奶粉")
                assert slots["product_experience"].startswith("冲奶最怕结块，a2至初粉质很细腻")

        await session.rollback()

    lines = [
        "# a2礼遇UGC分享贴真实链路预检",
        "",
        f"- 资产：`{ASSET_KEY}`",
        f"- 规则数：{len(rows)}",
        "- 结果：8条均经过真实 planner 和 layered_article prompt composer；无默认关键词资产污染。",
        "- 素材顺序：活动内容 → 批批检 → 产品体验 → 消费者认可/正向表达。",
        "",
        "| 序号 | 业务规则 | 了解途径 | 参加原因 | 活动内容 |",
        "|---:|---|---|---|---|",
    ]
    for item_no, name, source, motive, activity in rows:
        lines.append(f"| {item_no} | {name} | {source} | {motive} | {activity} |")
    lines.extend(["", "## 12罐换奶粉完整渲染Prompt", "", "```text", full_prompt, "```", ""])
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
