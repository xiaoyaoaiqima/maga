"""Build human-review previews and sampled prompts for a2 礼遇 v29 validation."""
from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.content_agent import ContentAgentStageCall, ContentBatchItem
from app.services.content_batch_report_service import ContentBatchReportService


BATCH_IDS = (792, 793, 794)
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v29_release_validation_20260722")

HUMAN_REVIEW = {
    792: {
        3: ("needs_fix", "积分素材只说换的东西实用，正文自行补写湿巾和小玩具，属于积分礼品编造。"),
    },
    793: {
        1: ("needs_fix", "命中硬禁表达“囤了好几罐”，已被后链路阻断。"),
        10: ("needs_fix", "“认真做用户关系和品质沟通”直接照抄正式素材，口吻不像普通宝妈。"),
    },
    794: {
        3: ("needs_fix", "活动福利后突然接“转奶很丝滑”，活动感受和使用经历黏在一起，逻辑跳。"),
        9: ("watch", "正文人工看可用，但本次业务审核服务未返回有效结果，机器已安全阻断。"),
    },
}

MARKERS = {
    "needs_fix": ("💣", "需修"),
    "watch": ("⚠️", "重点看"),
    "usable": ("✅", "可用"),
    "failed": ("⛔", "生成失败"),
}


def _review_for(batch_id: int, item: dict) -> tuple[str, str]:
    override = HUMAN_REVIEW.get(batch_id, {}).get(int(item["item_no"]))
    if override:
        return override
    if item.get("status") != "generated":
        return "failed", "生成或后链路处理失败。"
    return "usable", "当前人工业务判断可直接使用。"


def _had_successful_rewrite(item: dict) -> bool:
    quality = item.get("quality") or {}
    review_report = quality.get("review_report") or {}
    forbidden = review_report.get("forbidden_terms_review") or {}
    return bool(forbidden.get("initial_hits")) and item.get("hard_pass") is True


def _machine_metrics(items: list[dict]) -> dict:
    final_pass = [int(item["item_no"]) for item in items if item.get("hard_pass") is True]
    post_rewrite_pass = [int(item["item_no"]) for item in items if _had_successful_rewrite(item)]
    direct_pass = [item_no for item_no in final_pass if item_no not in post_rewrite_pass]
    raw_generated = [
        int(item["item_no"])
        for item in items
        if str(item.get("title") or "").strip() and str(item.get("body") or "").strip()
    ]
    return {
        "raw_generated": raw_generated,
        "direct_pass": direct_pass,
        "post_rewrite_pass": post_rewrite_pass,
        "final_pass": final_pass,
    }


def _human_metrics(batch_id: int, items: list[dict]) -> dict[str, list[int]]:
    result = {"usable": [], "watch": [], "needs_fix": [], "failed": []}
    for item in items:
        label, _reason = _review_for(batch_id, item)
        result[label].append(int(item["item_no"]))
    return result


def _conclusion(batch_id: int) -> str:
    return {
        792: "不建议单批直接转正：积分路径仍出现1篇具体礼品编造，虽已被机器hold-out。",
        793: "不建议单批直接转正：1篇被硬禁表达阻断，另有1篇正式素材照抄需要人工轻修。",
        794: "不建议单批直接转正：2篇业务审核不可用，其中1篇同时存在活动与使用经历衔接问题。",
    }[batch_id]


def _preview_markdown(batch_id: int, report: dict, prompt_path: Path) -> str:
    items = list(report.get("items") or [])
    summary = report.get("summary") or {}
    machine = _machine_metrics(items)
    human = _human_metrics(batch_id, items)
    priority = []
    others = []
    for item in items:
        label, reason = _review_for(batch_id, item)
        marker, label_text = MARKERS[label]
        section = (
            f"### {marker} item {item['item_no']}｜{label_text}｜{item.get('title') or '无标题'}\n\n"
            f"判断：{reason}\n\n{item.get('body') or '无正文'}\n"
        )
        (priority if label in {"needs_fix", "watch", "failed"} else others).append(section)

    forbidden_items = [
        int(item["item_no"])
        for item in items
        if item.get("forbidden_hits")
        or ((item.get("quality") or {}).get("review_report") or {}).get("forbidden_terms_review", {}).get("initial_hits")
    ]
    business_stats = (summary.get("business_usability_stats") or {}).get("item_nos_by_tier") or {}
    return "\n".join(
        [
            f"# a2礼遇｜v29发布验证｜batch {batch_id}",
            "",
            "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
            "",
            "## 结论",
            "",
            _conclusion(batch_id),
            "",
            "## 关键指标",
            "",
            f"- 发起：10篇；原始完整产出：{len(machine['raw_generated'])}篇；最终状态失败：{summary.get('failed_count', 0)}篇。",
            f"- 机器直接通过：{len(machine['direct_pass'])}篇，item {machine['direct_pass']}。",
            f"- 改写后通过：{len(machine['post_rewrite_pass'])}篇，item {machine['post_rewrite_pass']}；机器最终hard pass：{len(machine['final_pass'])}/10。",
            f"- 业务入池：direct {business_stats.get('direct_pool', [])}；light-fix {business_stats.get('light_fix_usable', [])}；hold-out {business_stats.get('hold_out', [])}。",
            f"- 禁词或替换链涉及：item {forbidden_items}；最大2-gram相似度：{summary.get('max_pairwise_jaccard_2gram')}；相似度告警：{summary.get('similarity_warning_count', 0)}篇。",
            f"- 人工可用：{human['usable']}；重点看：{human['watch']}；需修：{human['needs_fix']}；失败：{human['failed']}。",
            "",
            "## 候选变化",
            "",
            "v29只加强source row 9的活动期新购锚点：集罐只计算活动期内新购买a2至初后产生的有效罐码；不写家庭现有库存可以马上参加。其他原始槽位语料保持不变。",
            "",
            "## 重点看",
            "",
            *(priority or ["本批没有💣或⚠️项目。"]),
            "",
            "## 其他产出",
            "",
            *others,
            "",
            "## 调试信息",
            "",
            f"- batch_id：{batch_id}",
            "- candidate asset：1989 / v29 / active candidate",
            "- model：deepseek-v4-flash，temperature 0.8，max_tokens 2048",
            f"- JSON报告：`{OUTPUT_DIR / f'batch{batch_id}_report.json'}`",
            f"- 随机完整Prompt：`{prompt_path}`",
            "",
        ]
    )


async def _sample_prompt(db, batch_id: int, items: list[dict]) -> tuple[int, str, str]:
    candidates = [item for item in items if item.get("run_id") and item.get("body")]
    selected = secrets.choice(candidates)
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
    prompt = str((stage.input_snapshot or {}).get("rendered_prompt") or "").strip()
    if not prompt:
        raise RuntimeError(f"batch {batch_id} item {selected['item_no']} has no rendered prompt")
    return int(selected["item_no"]), str(selected.get("title") or ""), prompt


def _overall_markdown(reports: dict[int, dict]) -> str:
    all_items = [(batch_id, item) for batch_id, report in reports.items() for item in report.get("items") or []]
    raw_count = sum(bool(item.get("title") and item.get("body")) for _batch_id, item in all_items)
    final_pass = sum(item.get("hard_pass") is True for _batch_id, item in all_items)
    human_counts = {"usable": 0, "watch": 0, "needs_fix": 0, "failed": 0}
    issue_refs = []
    for batch_id, item in all_items:
        label, reason = _review_for(batch_id, item)
        human_counts[label] += 1
        if label != "usable":
            issue_refs.append(f"batch {batch_id} item {item['item_no']}：{reason}")
    max_similarity = max(float((report.get("summary") or {}).get("max_pairwise_jaccard_2gram") or 0) for report in reports.values())
    unresolved_machine = 30 - sum(
        len((((report.get("summary") or {}).get("business_usability_stats") or {}).get("item_nos_by_tier") or {}).get("direct_pool", []))
        for report in reports.values()
    )
    return "\n".join(
        [
            "# a2礼遇 v29｜三批生产发布验证总结",
            "",
            "## 结论",
            "",
            "暂不将v29升为production。安全审核已经能阻断问题内容，但直接生产可用性尚未达到正式发布门槛。",
            "",
            "## 汇总指标",
            "",
            f"- 同版本、同模型、同审核口径：3批，共30次生成。",
            f"- 原始完整产出：{raw_count}/30；机器最终hard pass：{final_pass}/30。",
            f"- 人工直接可用：{human_counts['usable']}/30；重点看：{human_counts['watch']}；需修：{human_counts['needs_fix']}；失败：{human_counts['failed']}。",
            f"- 机器未进入direct pool：{unresolved_machine}/30。",
            f"- 最大2-gram相似度：{max_similarity:.4f}。",
            "- 16条业务规则分支：100%覆盖。",
            "",
            "## 未通过发布门槛的原因",
            "",
            "- 原始生成出现1篇积分礼品编造，属于活动事实问题；虽然机器成功hold-out，但不能用后处理抵消源头P0。",
            "- 1篇命中“囤了好几罐”被硬阻断，说明生成源头仍会产出明确禁用表达。",
            "- 2篇业务LLM审核不可用，安全兜底正确，但平台稳定性和直接入池率仍受影响。",
            "- 1篇照抄“认真做用户关系和品质沟通”，暴露source row 4认可素材仍偏正式。",
            "- 机器未进入direct pool比例高于5%的正式发布门槛。",
            "",
            "## 非可用项目",
            "",
            *[f"- {item}" for item in issue_refs],
            "",
            "## 建议下一步",
            "",
            "只处理两个源头问题后再复测：积分路径禁止自行补具体礼品；把source row 4的正式认可原话换成自然老客表达。老罐继续由当前确定性审核兜底，不再扩充禁词。",
            "",
        ]
    )


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reports: dict[int, dict] = {}
    async with async_session_factory() as db:
        for batch_id in BATCH_IDS:
            report = (await ContentBatchReportService(db).get_batch_report(batch_id)).model_dump(mode="json")
            reports[batch_id] = report
            (OUTPUT_DIR / f"batch{batch_id}_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            item_no, title, prompt = await _sample_prompt(db, batch_id, list(report.get("items") or []))
            prompt_path = OUTPUT_DIR / f"batch{batch_id}_随机完整Prompt_item{item_no}.md"
            prompt_path.write_text(
                f"# batch {batch_id}｜item {item_no}｜{title}\n\n{prompt}\n",
                encoding="utf-8",
            )
            preview_path = OUTPUT_DIR / f"batch{batch_id}_10篇发布验证预览.md"
            preview_path.write_text(_preview_markdown(batch_id, report, prompt_path), encoding="utf-8")

    (OUTPUT_DIR / "a2礼遇_v29_三批发布验证总结.md").write_text(
        _overall_markdown(reports), encoding="utf-8"
    )
    print(json.dumps({"output_dir": str(OUTPUT_DIR), "batch_ids": list(BATCH_IDS)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
