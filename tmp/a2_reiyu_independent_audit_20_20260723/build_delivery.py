"""Build compact delivery artifacts for a2 礼遇 batch 825."""
from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.content_agent import ContentAgentStageCall, ContentBatchJob
from app.services.content_batch_report_service import ContentBatchReportService


BATCH_ID = 825
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_independent_audit_20_20260723")
REPORT_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_full_report.json"
PREVIEW_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_A2礼遇20篇生成审核预览.md"
RESPONSE_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_generation_response.json"

JUDGMENTS = {
    1: ("✅", "可用", "抽奖、每批检测和老客使用感承接完整；推荐语偏强但在当前边界内可用。"),
    2: ("💣", "需修", "命中“朋友圈”，按已确认口径改为pyq/puq后再用。"),
    3: ("✅", "可用", "积分、每批检测和长期使用体验逻辑清楚。"),
    4: ("💣", "需修", "把积分礼品写成绘本、小玩具，奖品事实无素材承接。"),
    5: ("💣", "需修", "“免费小听”需按运营口径替换成“🆓小听”。"),
    6: ("✅", "可用", "老客回归礼、小听粉和每批检测表达自然。"),
    7: ("⚠️", "重点看", "主体逻辑成立，但“不鼎力推荐真说不过去”明显生硬。"),
    8: ("💣", "需修", "照抄了已确认应删除的源语料“叠加的踏实感真的很舒服”。"),
    9: ("✅", "可用", "3罐换小车车，没有把现有库存直接写成参与资格。"),
    10: ("✅", "可用", "3罐换小车车和每批检测归属清楚。"),
    11: ("💣", "需修", "明确把家里已囤的罐子写成可攒着换自行车，属于旧罐风险。"),
    12: ("⚠️", "重点看", "“质量肯定稳定、没出过问题”语气过满，建议降调。"),
    13: ("💣", "需修", "“免费兑1罐”需按运营口径替换为“🆓兑1罐”。"),
    14: ("✅", "可用", "金标调用异常进入watch，但人工复核后活动、检测和推荐逻辑成立。"),
    15: ("✅", "可用", "18罐换婴儿车，未虚构已经兑换到手。"),
    16: ("✅", "可用", "18罐换婴儿车和活动后了解检测的顺序正确。"),
    17: ("⚠️", "重点看", "经历和活动事实成立，但“不鼎力推荐”再次出现，收尾不自然。"),
    18: ("⚠️", "重点看", "品控在线、质量稳定、标准高、细节到位集中堆叠，广告感偏重。"),
    19: ("💣", "需修", "机器已命中连续正向词堆叠，需要模型局部改写。"),
    20: ("⚠️", "重点看", "整体可读，但“经得起研究”不像普通宝妈自然表达。"),
}


def _item_section(item: dict) -> str:
    item_no = int(item["item_no"])
    marker, label, reason = JUDGMENTS[item_no]
    return (
        f"### {marker} item {item_no}｜{label}｜{item.get('title') or '无标题'}\n\n"
        f"判断：{reason}\n\n{item.get('body') or '无正文'}\n"
    )


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    async with async_session_factory() as db:
        report_model = await ContentBatchReportService(db).get_batch_report(
            BATCH_ID,
            include_details=True,
        )
        report = report_model.model_dump(mode="json")
        items = list(report.get("items") or [])
        job = await db.get(ContentBatchJob, BATCH_ID)
        direct_items = [item for item in items if item.get("business_usability_tier") == "direct_pool"]
        sampled = secrets.choice(direct_items or items)
        stage = (
            await db.execute(
                select(ContentAgentStageCall)
                .where(
                    ContentAgentStageCall.run_id == int(sampled["run_id"]),
                    ContentAgentStageCall.capability == "content.generate",
                )
                .order_by(ContentAgentStageCall.sequence_no.asc())
                .limit(1)
            )
        ).scalar_one()

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    response_payload = {
        "batch_id": BATCH_ID,
        "batch_code": report.get("batch_code"),
        "requested_count": 20,
        "raw_generated_count": report.get("summary", {}).get("generated_count"),
        "generation_failed_count": report.get("summary", {}).get("failed_count"),
        "audit_state": (job.strategy_json or {}).get("a2_reiyu_audit") if job else None,
    }
    RESPONSE_PATH.write_text(
        json.dumps(response_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    prompt_path = OUTPUT_DIR / f"batch{BATCH_ID}_随机完整Prompt_item{sampled['item_no']}.md"
    prompt_path.write_text(
        f"# batch {BATCH_ID}｜item {sampled['item_no']}｜{sampled.get('title') or ''}\n\n"
        f"{str((stage.input_snapshot or {}).get('rendered_prompt') or '').strip()}\n",
        encoding="utf-8",
    )

    summary = report.get("summary") or {}
    machine_stats = summary.get("business_usability_stats") or {}
    machine_counts = machine_stats.get("counts") or {}
    usable = [item_no for item_no, value in JUDGMENTS.items() if value[0] == "✅"]
    watch = [item_no for item_no, value in JUDGMENTS.items() if value[0] in {"⚠️", "👀"}]
    needs_fix = [item_no for item_no, value in JUDGMENTS.items() if value[0] == "💣"]
    priority = [_item_section(item) for item in items if JUDGMENTS[int(item["item_no"])][0] in {"💣", "⚠️"}]
    others = [_item_section(item) for item in items if JUDGMENTS[int(item["item_no"])][0] not in {"💣", "⚠️"}]

    preview = "\n".join(
        [
            "# a2礼遇｜20篇生成与独立审核验证",
            "",
            "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
            "",
            "## 结论",
            "",
            "新生成-独立审核链路工作正常，但本批不建议整体直接交付：机器最终通过13/20，人工直接可用8/20；源语料残留和旧罐仍是主要问题。",
            "",
            "## 关键指标",
            "",
            f"- 发起：20篇；原始生成：{summary.get('generated_count')}/20；生成失败：{summary.get('failed_count')}。",
            f"- 生成接口返回时：audit_skipped 20/20；独立审核完成后：audit_skipped {summary.get('audit_skipped_count')}/20。",
            f"- 金标直接入池：{machine_counts.get('direct_pool', 0)}/20；本链路未执行改写，改写后新增通过：0；机器最终通过：{summary.get('hard_pass_count')}/20。",
            "- 机器轻修：[2, 5, 13, 19]；硬拦：[4, 11]；金标调用失败：[14, 19]，其中14进入watch，19另有文本Guard轻修结论。",
            f"- 禁词命中：{summary.get('forbidden_hit_count')}；最大2-gram相似度：{summary.get('max_pairwise_jaccard_2gram')}；相似度告警：{summary.get('similarity_warning_count')}。",
            f"- 人工可用：{usable}；重点看：{watch}；需修：{needs_fix}。",
            "- 文本堆叠Guard：item [19]；旧罐Guard：item [11]；错误奖品：item [4]；金标调用失败：item [14, 19]。",
            "",
            "## 候选变化",
            "",
            "- 本轮没有修改production语料，只验证新链路：生成完成立即返回，随后独立执行Guard和金标Judge。",
            "- 新暴露的回源问题：item 8 的 activity_content 仍是“好几层活动，这种叠加的踏实感真的很舒服😌”，与之前确认删除的语料一致，应从当前资产移除。",
            "- 后链路当前只审核不改写，所以“朋友圈/免费”被正确标成轻修，但不会自动变为pyq/🆓。",
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
            f"- production asset：a2_reiyu_ugc_post_rules_v1 v{report.get('asset_version') or 32}",
            f"- JSON报告：`{REPORT_PATH}`",
            f"- 生成响应：`{RESPONSE_PATH}`",
            f"- 随机完整Prompt：`{prompt_path}`",
            "",
        ]
    )
    PREVIEW_PATH.write_text(preview, encoding="utf-8")
    print(
        json.dumps(
            {
                "batch_id": BATCH_ID,
                "preview_path": str(PREVIEW_PATH),
                "prompt_path": str(prompt_path),
                "report_path": str(REPORT_PATH),
                "response_path": str(RESPONSE_PATH),
                "machine_final_pass": summary.get("hard_pass_count"),
                "human_usable": len(usable),
                "human_watch": len(watch),
                "human_needs_fix": len(needs_fix),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
