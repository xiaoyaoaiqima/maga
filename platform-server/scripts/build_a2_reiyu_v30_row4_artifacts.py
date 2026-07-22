"""Build the preview and sampled prompt for a2 礼遇 v30 row-4 validation."""
from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.content_agent import ContentAgentStageCall
from app.services.content_batch_report_service import ContentBatchReportService


BATCH_ID = 796
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v30_row4_natural_recognition_20260722")
HUMAN_REVIEW = {
    6: ("needs_fix", "出现“福利挺多多”的口误，局部删掉一个“多”即可。"),
    8: ("watch", "本条主线是会员积分，但正文顺带写了抽奖；活动事实不算错，重点看是否接受这种扩展。"),
}
MARKERS = {
    "needs_fix": ("💣", "需修"),
    "watch": ("⚠️", "重点看"),
    "usable": ("✅", "可用"),
}


def _label(item_no: int) -> tuple[str, str]:
    return HUMAN_REVIEW.get(item_no, ("usable", "当前人工业务判断可直接使用。"))


def _successful_rewrite(item: dict) -> bool:
    review_report = ((item.get("quality") or {}).get("review_report") or {})
    forbidden = review_report.get("forbidden_terms_review") or {}
    return bool(forbidden.get("initial_hits")) and item.get("hard_pass") is True


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    async with async_session_factory() as db:
        report = (await ContentBatchReportService(db).get_batch_report(BATCH_ID)).model_dump(mode="json")
        items = list(report.get("items") or [])
        selected = secrets.choice([item for item in items if item.get("run_id") and item.get("body")])
        stage = (
            await db.execute(
                select(ContentAgentStageCall)
                .where(
                    ContentAgentStageCall.run_id == int(selected["run_id"]),
                    ContentAgentStageCall.capability == "content.generate",
                )
                .order_by(ContentAgentStageCall.sequence_no.asc())
                .limit(1)
            )
        ).scalar_one()

    report_path = OUTPUT_DIR / f"batch{BATCH_ID}_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    prompt_path = OUTPUT_DIR / f"batch{BATCH_ID}_随机完整Prompt_item{selected['item_no']}.md"
    prompt = str((stage.input_snapshot or {}).get("rendered_prompt") or "").strip()
    prompt_path.write_text(
        f"# batch {BATCH_ID}｜item {selected['item_no']}｜{selected.get('title') or ''}\n\n{prompt}\n",
        encoding="utf-8",
    )

    summary = report.get("summary") or {}
    final_pass = [int(item["item_no"]) for item in items if item.get("hard_pass") is True]
    post_rewrite = [int(item["item_no"]) for item in items if _successful_rewrite(item)]
    direct_pass = [item_no for item_no in final_pass if item_no not in post_rewrite]
    human = {"usable": [], "watch": [], "needs_fix": []}
    priority = []
    others = []
    for item in items:
        label, reason = _label(int(item["item_no"]))
        human[label].append(int(item["item_no"]))
        marker, label_text = MARKERS[label]
        section = (
            f"### {marker} item {item['item_no']}｜{label_text}｜{item.get('title') or '无标题'}\n\n"
            f"判断：{reason}\n\n{item.get('body') or '无正文'}\n"
        )
        (priority if label != "usable" else others).append(section)

    preview = "\n".join(
        [
            "# a2礼遇｜v30 row 4认可表达自然化｜10篇回测",
            "",
            "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
            "",
            "## 结论",
            "",
            "目标修改有效：没有再生成品牌汇报式的“认真做用户关系和品质沟通”；新表达自然可用。",
            "",
            "## 关键指标",
            "",
            f"- 发起：10篇；原始生成：{summary.get('generated_count', 0)}篇；失败：{summary.get('failed_count', 0)}篇。",
            f"- 硬规则直接通过：{len(direct_pass)}篇，item {direct_pass}。",
            f"- 确定性改写后通过：{len(post_rewrite)}篇，item {post_rewrite}；机器最终hard pass：{len(final_pass)}/10。",
            f"- 业务direct pool：{((summary.get('business_usability_stats') or {}).get('item_nos_by_tier') or {}).get('direct_pool', [])}。",
            f"- 最终禁词命中：{summary.get('forbidden_hit_count', 0)}篇；最大2-gram相似度：{summary.get('max_pairwise_jaccard_2gram')}；相似度告警：{summary.get('similarity_warning_count', 0)}篇。",
            f"- 人工可用：{human['usable']}；重点看：{human['watch']}；需修：{human['needs_fix']}。",
            "",
            "## 候选变化",
            "",
            "- 修改前：不只是促销，而是在认真做用户关系和品质沟通",
            "- 修改后：本来以为就是普通活动，看完还真觉得a2挺把老用户当回事的",
            "",
            "## 重点看",
            "",
            *priority,
            "",
            "## 其他产出",
            "",
            *others,
            "",
            "## 调试信息",
            "",
            f"- batch_id：{BATCH_ID}",
            "- candidate asset：1992 / v30 / active candidate",
            "- source row：4",
            "- model：deepseek-v4-flash，temperature 0.8，max_tokens 2048",
            f"- JSON报告：`{report_path}`",
            f"- 随机完整Prompt：`{prompt_path}`",
            "",
        ]
    )
    preview_path = OUTPUT_DIR / f"batch{BATCH_ID}_10篇回测预览.md"
    preview_path.write_text(preview, encoding="utf-8")
    print(json.dumps({"preview": str(preview_path), "prompt": str(prompt_path)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
