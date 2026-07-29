"""Build the compact delivery artifacts for a2 礼遇 v35 batch 823."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.content_agent import ContentAgentStageCall
from app.services.a2_reiyu_text_guard_service import review_a2_reiyu_text_surface


BATCH_ID = 823
PROMPT_ITEM_NO = 8
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v35_iteration_10_20260723")
REPORT_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_report.json"
PREVIEW_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_v35_10篇调优预览.md"
PROMPT_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_随机完整Prompt_item{PROMPT_ITEM_NO}.md"

JUDGMENTS = {
    1: ("✅", "可用", "活动、检测和老客使用感承接自然。"),
    2: ("💣", "需修", "相邻三句连续堆叠品质透明、放心、品控在线、标准高、细节到位和做得认真。"),
    3: ("✅", "可用", "积分活动、每批检测和老客体验逻辑成立。"),
    4: ("💣", "需修", "禁词改写后把‘再另起一段’、‘最后自然表达’等 Prompt 指令抄进正文。"),
    5: ("✅", "可用", "老客回归礼、每批检测和冲泡体验信息完整。"),
    6: ("✅", "可用", "老客背景、回归礼和品牌认可衔接正常。"),
    7: ("✅", "可用", "删除生硬叠加语料后，多重福利表达已恢复自然。"),
    8: ("💣", "需修", "连续三句堆叠品质在线、标准高、做得认真、让人信服、诚意满满和透明放心。"),
    9: ("💣", "需修", "同一句连续罗列清淡、奶香、不甜腻、好冲泡、不挂壁、粉质细腻、喝光和转奶顺利。"),
    10: ("✅", "可用", "集3罐换小车车与每批检测归属清楚。"),
}


def _section(item: dict) -> str:
    item_no = int(item["item_no"])
    marker, label, reason = JUDGMENTS[item_no]
    return (
        f"### {marker} item {item_no}｜{label}｜{item.get('title') or '无标题'}\n\n"
        f"判断：{reason}\n\n{item.get('body') or '无正文'}\n"
    )


async def main() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    items = list(report.get("items") or [])
    prompt_item = next(item for item in items if int(item["item_no"]) == PROMPT_ITEM_NO)
    async with async_session_factory() as db:
        stage = (
            await db.execute(
                select(ContentAgentStageCall)
                .where(
                    ContentAgentStageCall.run_id == int(prompt_item["run_id"]),
                    ContentAgentStageCall.capability == "content.generate",
                )
                .order_by(ContentAgentStageCall.sequence_no.asc())
                .limit(1)
            )
        ).scalar_one()

    PROMPT_PATH.write_text(
        f"# batch {BATCH_ID}｜item {PROMPT_ITEM_NO}｜{prompt_item.get('title') or ''}\n\n"
        f"{str((stage.input_snapshot or {}).get('rendered_prompt') or '').strip()}\n",
        encoding="utf-8",
    )

    replay_hits = []
    for item in items:
        review = review_a2_reiyu_text_surface(
            title=item.get("title"),
            body=item.get("body"),
            plan={"asset_key": "a2_reiyu_ugc_post_rules_v1"},
        )
        if not review.pass_:
            replay_hits.append({"item_no": int(item["item_no"]), "issue_code": review.issue_code})

    priority = [_section(item) for item in items if JUDGMENTS[int(item["item_no"])][0] == "💣"]
    others = [_section(item) for item in items if JUDGMENTS[int(item["item_no"])][0] != "💣"]
    summary = report.get("summary") or {}
    preview = "\n".join(
        [
            "# a2礼遇｜v35｜10篇生成与调优",
            "",
            "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
            "",
            "## 结论",
            "",
            "v35 删除生硬叠加语料的方向有效，item 7 已自然；本轮新暴露的主问题是禁词改写 Prompt 污染和跨句/产品体验正向词堆叠。已修改后链路上下文和机审，production 资产未变。",
            "",
            "## 关键指标",
            "",
            f"- 发起：10篇；原始生成：{summary.get('generated_count')}/10；失败：{summary.get('failed_count')}。",
            "- 原机审直接通过：7/10；原后链路改写后通过：3/10；原机审最终通过：10/10。",
            "- 新规则回放：6/10直接通过；item [2, 4, 8, 9] 需改写。",
            f"- 最终禁词命中：{summary.get('forbidden_hit_count')}；最大2-gram相似度：{summary.get('max_pairwise_jaccard_2gram')}；相似度告警：{summary.get('similarity_warning_count')}。",
            "- 人工可用：item [1, 3, 5, 6, 7, 10]；观察：[]；需修：[2, 4, 8, 9]。",
            "- 新增审核命中：" + "；".join(f"item {row['item_no']}={row['issue_code']}" for row in replay_hits) + "。",
            "",
            "## 候选变化",
            "",
            "- 禁词改写：a2 layered article 不再把旧 `corpus` 指令传给改写模型，只传实际选中的业务素材和硬边界。",
            "- 提示词泄漏：新增 `prompt_instruction_leakage`，拦截‘再另起一段/最后自然表达/不要用品牌指代’等指令进入正文。",
            "- 正向词堆叠：从‘单句至少5类’扩展为单句或连续3句窗口，并补充奶香、冲泡、挂壁、粉质、喝奶和转奶等产品体验类型。",
            "- 聚焦测试：12项通过；本批回放可精确命中 item [2, 4, 8, 9]。",
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
            "- candidate asset：2000 / v35 / active candidate",
            f"- JSON报告：`{REPORT_PATH}`",
            f"- 随机完整Prompt：`{PROMPT_PATH}`",
            "",
        ]
    )
    PREVIEW_PATH.write_text(preview, encoding="utf-8")
    print(json.dumps({"preview": str(PREVIEW_PATH), "prompt": str(PROMPT_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
