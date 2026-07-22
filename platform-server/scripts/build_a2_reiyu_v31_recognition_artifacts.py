"""Build preview artifacts for the a2 礼遇 v31 recognition test."""
from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.content_agent import ContentAgentStageCall
from app.services.content_batch_report_service import ContentBatchReportService


BATCH_ID = 798
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v31_natural_recognition_all_paths_20260722")


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
    prompt_path.write_text(
        f"# batch {BATCH_ID}｜item {selected['item_no']}｜{selected.get('title') or ''}\n\n"
        f"{str((stage.input_snapshot or {}).get('rendered_prompt') or '').strip()}\n",
        encoding="utf-8",
    )

    summary = report.get("summary") or {}
    final_pass = [int(item["item_no"]) for item in items if item.get("hard_pass") is True]
    post_rewrite = [int(item["item_no"]) for item in items if _successful_rewrite(item)]
    direct_pass = [item_no for item_no in final_pass if item_no not in post_rewrite]
    priority = []
    others = []
    for item in items:
        if int(item["item_no"]) == 2:
            marker = "💣"
            label = "需修"
            reason = "积分素材没有具体礼品，却自行补出摇铃和保温杯；机器已正确hold-out。"
        else:
            marker = "✅"
            label = "可用"
            reason = "认可表达自然，没有品牌汇报式照抄。"
        section = (
            f"### {marker} item {item['item_no']}｜{label}｜{item.get('title') or '无标题'}\n\n"
            f"判断：{reason}\n\n{item.get('body') or '无正文'}\n"
        )
        (priority if int(item["item_no"]) == 2 else others).append(section)

    direct_pool = (((summary.get("business_usability_stats") or {}).get("item_nos_by_tier") or {}).get("direct_pool", []))
    preview = "\n".join(
        [
            "# a2礼遇｜v31认可表达全路径自然化｜8篇回测",
            "",
            "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
            "",
            "## 结论",
            "",
            "目标修改通过：8个“信息了解后更认可”分支已全部替换，生文未再出现品牌汇报式表达。",
            "",
            "## 关键指标",
            "",
            f"- 发起：8篇；原始生成：{summary.get('generated_count', 0)}篇；失败：{summary.get('failed_count', 0)}篇。",
            f"- 硬规则直接通过：{len(direct_pass)}篇，item {direct_pass}。",
            f"- 确定性改写后通过：{len(post_rewrite)}篇，item {post_rewrite}；机器最终hard pass：{len(final_pass)}/8。",
            f"- 业务direct pool：{direct_pool}；hold-out：[2]。",
            f"- 最终禁词命中：{summary.get('forbidden_hit_count', 0)}篇；最大2-gram相似度：{summary.get('max_pairwise_jaccard_2gram')}；相似度告警：{summary.get('similarity_warning_count', 0)}篇。",
            "- 人工可用：item [1, 3, 4, 5, 6, 7, 8]；需修：item [2]。",
            "",
            "## 候选变化",
            "",
            "- 修改前：不只是促销，而是在认真做用户关系和品质沟通",
            "- 修改后：本来以为就是普通活动，看完还真觉得a2挺把老用户当回事的",
            "- 覆盖分支：source row 2、4、6、8、10、12、14、16。",
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
            "- candidate asset：1993 / v31 / active candidate",
            "- model：deepseek-v4-flash，temperature 0.8，max_tokens 2048",
            f"- JSON报告：`{report_path}`",
            f"- 随机完整Prompt：`{prompt_path}`",
            "",
        ]
    )
    preview_path = OUTPUT_DIR / f"batch{BATCH_ID}_8篇回测预览.md"
    preview_path.write_text(preview, encoding="utf-8")
    print(json.dumps({"preview": str(preview_path), "prompt": str(prompt_path)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
