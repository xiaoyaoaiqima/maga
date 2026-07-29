from __future__ import annotations

import asyncio
import csv
import json
import random
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory, engine
from app.models.content_agent import ContentBatchItem
from app.services.activity_quality_guard_service import build_article_pool_context_list


BATCH_ID = 877
ROOT = Path("/Users/luxifa/maga")
OUTPUT_DIR = (
    ROOT
    / "outputs/0705_wangyue_product_relation_evidence"
    / "20260727_wangyue_v92_production_100_round2"
)
REPORT_PATH = OUTPUT_DIR / "report_full.json"
START_RESPONSE_PATH = OUTPUT_DIR / "start_response.json"
AUDIT_PATH = OUTPUT_DIR / "20260727_wangyue_batch877_human_review.csv"
USABLE_CSV_PATH = OUTPUT_DIR / "20260727_wangyue_batch877_strict_usable_80.csv"
PREVIEW_PATH = OUTPUT_DIR / "20260727_wangyue_batch877_review_preview.md"
PROMPT_PATH = OUTPUT_DIR / "20260727_wangyue_batch877_sampled_rendered_prompt.md"
SUMMARY_PATH = OUTPUT_DIR / "20260727_wangyue_batch877_review_summary.json"

NEEDS_FIX_REASONS = {
    7: "“一罐早餐冲一杯”语序残缺，正文不可直接使用。",
    8: "出现孩子运动后主动要喝，命中孩子主动要奶边界。",
    16: "标题“这罐奶香淡定”语义不成立。",
    23: "标题和正文均未出现旺玥或皇家美素佳儿，种草对象缺失。",
    24: "写成运动后喝一杯、隔天脸色变亮，属于单杯短周期硬反转。",
    26: "写孩子回来自己倒一杯，产品操作主体不合理。",
    33: "用“少生病”直接承接保护力效果，属于疾病结果表达。",
    50: "active v92 本轮选中的卖点表达要求回顾做功课和选奶，与本行明确禁止回头写选奶/做功课的内容方向冲突。",
    54: "“钙和蛋白质含量相对高”缺少可靠比较依据。",
    66: "逐项贬低其他产品，且引入当前 v92 卖点资产未提供的 α-乳白蛋白。",
    69: "用小喷嚏很快过去证明保护力，属于具体症状效果链。",
    80: "写成把冲好的旺玥带去爬山，命中随身即饮产品形态错误。",
    81: "用秋冬阶段没操心证明保护力，属于季节性疾病环境锚点。",
    82: "用请病假次数证明保护力，属于疾病/出勤效果表达。",
    97: "正文重复残留旧提示词句，模板拼接明显。",
}


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def item_section(
    marker: str,
    label: str,
    item: dict[str, object],
    reason: str | None = None,
) -> str:
    title = str(item.get("title") or "（无标题）")
    body = str(item.get("body") or "")
    lines = [f"### {marker} item {item['item_no']}｜{label}｜{title}", ""]
    if reason:
        lines.extend([f"问题：{reason}", ""])
    lines.append(body or "未生成可用正文。")
    return "\n".join(lines)


async def load_contexts() -> dict[int, dict[str, str]]:
    async with async_session_factory() as db:
        items = list(
            (
                await db.execute(
                    select(ContentBatchItem)
                    .where(ContentBatchItem.batch_id == BATCH_ID)
                    .order_by(ContentBatchItem.item_no)
                )
            )
            .scalars()
            .all()
        )
    contexts = {
        int(item.item_no): build_article_pool_context_list(item)
        for item in items
    }
    await engine.dispose()
    return contexts


async def main() -> None:
    payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    if payload.get("code") != 200 or int(payload["data"]["batch_id"]) != BATCH_ID:
        raise RuntimeError("unexpected batch report")

    report = payload["data"]
    items = sorted(report["items"], key=lambda row: int(row["item_no"]))
    generated = [
        row
        for row in items
        if row.get("status") == "generated" and str(row.get("body") or "").strip()
    ]
    failed = [row for row in items if row not in generated]
    needs_fix = [row for row in generated if int(row["item_no"]) in NEEDS_FIX_REASONS]
    usable = [row for row in generated if int(row["item_no"]) not in NEEDS_FIX_REASONS]

    expected = (100, 95, 5, 15, 80)
    actual = (len(items), len(generated), len(failed), len(needs_fix), len(usable))
    if actual != expected:
        raise RuntimeError(f"unexpected counts: expected={expected}, actual={actual}")
    if {int(row["item_no"]) for row in needs_fix} != set(NEEDS_FIX_REASONS):
        raise RuntimeError("needs-fix item set mismatch")

    contexts = await load_contexts()
    if any(int(row["item_no"]) not in contexts for row in usable):
        raise RuntimeError("missing article-pool context")

    audit_rows: list[dict[str, object]] = []
    for row in items:
        item_no = int(row["item_no"])
        if row in failed:
            tier = "failed"
            conclusion = str(row.get("reject_reasons") or "生成失败")
        elif item_no in NEEDS_FIX_REASONS:
            tier = "hold_out"
            conclusion = NEEDS_FIX_REASONS[item_no]
        else:
            tier = "direct_pool"
            conclusion = "人工复核可直接使用。"
        audit_rows.append(
            {
                "item_no": item_no,
                "item_id": row.get("item_id") or "",
                "生成状态": row.get("status") or "",
                "机器最终通过": "是" if row.get("hard_pass") is True else "否",
                "审核档位": tier,
                "审核结论": conclusion,
                "标题": row.get("title") or "",
                "正文": row.get("body") or "",
            }
        )
    write_csv(
        AUDIT_PATH,
        [
            "item_no",
            "item_id",
            "生成状态",
            "机器最终通过",
            "审核档位",
            "审核结论",
            "标题",
            "正文",
        ],
        audit_rows,
    )

    usable_rows = [
        {
            "标题": row.get("title") or "",
            "正文": row.get("body") or "",
            "上下文变量(context_list)": json.dumps(
                contexts[int(row["item_no"])], ensure_ascii=False
            ),
        }
        for row in usable
    ]
    write_csv(
        USABLE_CSV_PATH,
        ["标题", "正文", "上下文变量(context_list)"],
        usable_rows,
    )

    sample = random.Random(BATCH_ID).choice(usable)
    rendered_prompt = str((sample.get("generation_snapshot") or {}).get("rendered_prompt") or "")
    if not rendered_prompt.strip():
        raise RuntimeError("sampled item has no rendered prompt")
    PROMPT_PATH.write_text(
        "\n".join(
            [
                "# 旺玥 batch 877｜随机完整 rendered prompt",
                "",
                f"- batch_id：{BATCH_ID}",
                f"- item_no：{sample['item_no']}",
                f"- title：{sample.get('title') or ''}",
                "",
                "## Rendered Prompt",
                "",
                rendered_prompt,
                "",
            ]
        ),
        encoding="utf-8",
    )

    summary = report["summary"]
    machine_adjusted = [
        int(row["item_no"])
        for row in generated
        if str(row.get("rewrite_reason") or "").startswith("命中违禁词已自动改写")
    ]
    machine_direct = len(generated) - len(machine_adjusted)
    failed_nos = [int(row["item_no"]) for row in failed]
    needs_fix_nos = [int(row["item_no"]) for row in needs_fix]
    usable_nos = [int(row["item_no"]) for row in usable]

    preview = [
        "# 旺玥 v92 生产 100 次｜batch 877 审核预览",
        "",
        "## 结论",
        "",
        "本批 80 篇可直接使用；15 篇需修，5 篇生成失败，本轮不补产。",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 关键指标",
        "",
        "- 请求 / 尝试生成：100",
        f"- 原始生成成功 / 失败：{len(generated)} / {len(failed)}",
        f"- 机器直接通过：{machine_direct}",
        f"- 自动替换后通过：{len(machine_adjusted)}（item {', '.join(map(str, machine_adjusted))}）",
        f"- 机器最终通过：{summary['hard_pass_count']}",
        f"- 机器禁用命中：{summary['forbidden_hit_count']}",
        f"- 最大两两相似度：{summary['max_pairwise_jaccard_2gram']}；相似度告警：{summary['similarity_warning_count']}",
        f"- 人工可用：{len(usable)}（{', '.join(map(str, usable_nos))}）",
        f"- 人工需修：{len(needs_fix)}（{', '.join(map(str, needs_fix_nos))}）",
        f"- 生成失败：{len(failed)}（{', '.join(map(str, failed_nos))}）",
        "- 批次观察：安心 / 省心 / 踏实结尾簇 43 / 95；本批不据此单篇拦截。",
        "",
        "## 候选变化",
        "",
        "无生产资产变化。本轮直接使用 active v92，只做真实生成、机器审核和人工业务筛选。",
        "",
        "## 重点看",
        "",
    ]
    for row in needs_fix:
        preview.extend(
            [
                item_section(
                    "💣",
                    "需修",
                    row,
                    NEEDS_FIX_REASONS[int(row["item_no"])],
                ),
                "",
            ]
        )
    for row in failed:
        reason = "；".join(str(value) for value in (row.get("reject_reasons") or []))
        preview.extend([item_section("⛔", "生成失败", row, reason or "生成失败"), ""])

    preview.extend(["## 其他产出", ""])
    for row in usable:
        preview.extend([item_section("✅", "可用", row), ""])

    preview.extend(
        [
            "## 调试信息",
            "",
            f"- batch_id：{BATCH_ID}",
            "- batch_code：batch_3ca46419fb58",
            "- active asset：wangyue_v3_core_storyline_article_rules v92 / id 2029",
            f"- 启动响应：`{START_RESPONSE_PATH}`",
            f"- 完整报告：`{REPORT_PATH}`",
            f"- 人工审核明细：`{AUDIT_PATH}`",
            f"- 严格可用 CSV：`{USABLE_CSV_PATH}`",
            f"- 随机完整 Prompt：`{PROMPT_PATH}`（item {sample['item_no']}）",
            "",
        ]
    )
    PREVIEW_PATH.write_text("\n".join(preview), encoding="utf-8")

    output_summary = {
        "batch_id": BATCH_ID,
        "attempted": len(items),
        "generated": len(generated),
        "failed": len(failed),
        "machine_direct_pass": machine_direct,
        "machine_adjusted_pass": len(machine_adjusted),
        "machine_final_pass": int(summary["hard_pass_count"]),
        "human_usable": len(usable),
        "human_needs_fix": len(needs_fix),
        "needs_fix_item_nos": needs_fix_nos,
        "failed_item_nos": failed_nos,
        "sampled_prompt_item_no": int(sample["item_no"]),
        "preview_path": str(PREVIEW_PATH),
        "prompt_path": str(PROMPT_PATH),
        "audit_path": str(AUDIT_PATH),
        "usable_csv_path": str(USABLE_CSV_PATH),
    }
    SUMMARY_PATH.write_text(
        json.dumps(output_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output_summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
