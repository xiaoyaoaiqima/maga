from __future__ import annotations

import asyncio
import csv
import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory, engine
from app.models.content_agent import ContentBatchItem
from app.services.activity_quality_guard_service import build_article_pool_context_list


BATCH_ID = 876
OUTPUT_DIR = Path(
    "/Users/luxifa/maga/outputs/0705_wangyue_product_relation_evidence/"
    "20260727_wangyue_v92_production_100_online"
)
LIVE_REPORT = Path("/tmp/wangyue_batch876_report_live.json")
REPORT_OUTPUT = OUTPUT_DIR / "20260727_124057_wangyue_batch876_report_full.json"
AUDIT_OUTPUT = OUTPUT_DIR / "20260727_wangyue_batch876_human_review.csv"
CANDIDATE_OUTPUT = OUTPUT_DIR / "20260727_wangyue_batch876_online_import_77.csv"
FINAL_DELIVERY_OUTPUT = OUTPUT_DIR / "20260727_wangyue_batch876_online_import_incremental.csv"
PREVIEW_OUTPUT = OUTPUT_DIR / "20260727_124057_wangyue_batch876_preview.md"
PROMPT_OUTPUT = OUTPUT_DIR / "20260727_124057_wangyue_batch876_item46_rendered_prompt.md"

NEEDS_FIX_REASONS = {
    1: "单杯后从疲惫即时转为精神，属于即时硬反转。",
    2: "人物关系和指代前后矛盾。",
    8: "引入当前 v92 卖点资产未提供的 PS、ARA、益生元等配方词。",
    12: "出现孩子主动催泡奶。",
    20: "把保护力成分错误归因到体格变壮。",
    21: "‘蛋白质和钙含量相对高’缺少可靠比较依据。",
    24: "引入当前 v92 卖点资产未提供的配方词。",
    27: "引入当前 v92 卖点资产未提供的配方词。",
    28: "‘这个含量相对高’缺比较对象且表达残缺。",
    39: "后链路改写后仍残留‘每天主动要喝一杯’。",
    42: "引入当前 v92 卖点资产未提供的配方词。",
    45: "展开了请病假的具体场景。",
    61: "写成冲泡时勺子在罐里搅动，产品操作不合理。",
    68: "‘蛋白质含量高’缺少可靠比较依据。",
    86: "单杯后从疲惫即时转为精神，属于即时硬反转。",
    90: "引入当前 v92 卖点资产未提供的配方词。",
    92: "‘钙含量相对高’缺少可靠比较依据。",
}


def body_hash(body: str) -> str:
    return hashlib.sha256(body.strip().encode("utf-8")).hexdigest()


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


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def item_section(marker: str, label: str, item: dict[str, object], reason: str | None = None) -> str:
    item_no = int(item["item_no"])
    title = str(item.get("title") or "（无标题）")
    body = str(item.get("body") or "")
    lines = [f"### {marker} item {item_no}｜{label}｜{title}", ""]
    if reason:
        lines.extend([f"问题：{reason}", ""])
    lines.append(body or "未生成可用正文。")
    return "\n".join(lines)


async def main() -> None:
    payload = json.loads(LIVE_REPORT.read_text(encoding="utf-8"))
    if payload.get("code") != 200:
        raise RuntimeError(f"live report failed: {payload}")
    report = payload["data"]
    if int(report["batch_id"]) != BATCH_ID:
        raise RuntimeError(f"unexpected batch id: {report['batch_id']}")

    items = sorted(report["items"], key=lambda row: int(row["item_no"]))
    generated = [row for row in items if row.get("status") == "generated" and str(row.get("body") or "").strip()]
    failed = [row for row in items if row.get("status") != "generated" or not str(row.get("body") or "").strip()]
    needs_fix = [row for row in generated if int(row["item_no"]) in NEEDS_FIX_REASONS]
    usable = [row for row in generated if int(row["item_no"]) not in NEEDS_FIX_REASONS]
    if (len(items), len(generated), len(failed), len(needs_fix), len(usable)) != (100, 94, 6, 17, 77):
        raise RuntimeError(
            "unexpected counts: "
            f"items={len(items)} generated={len(generated)} failed={len(failed)} "
            f"needs_fix={len(needs_fix)} usable={len(usable)}"
        )
    if {int(row["item_no"]) for row in needs_fix} != set(NEEDS_FIX_REASONS):
        raise RuntimeError("needs-fix item set does not match the human decision set")

    contexts = await load_contexts()
    if any(int(row["item_no"]) not in contexts for row in usable):
        raise RuntimeError("missing article-pool context for a usable item")

    hashes = [body_hash(str(row["body"])) for row in usable]
    if len(hashes) != len(set(hashes)):
        raise RuntimeError("duplicate body found inside the 77 usable rows")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    audit_rows: list[dict[str, object]] = []
    for row in items:
        item_no = int(row["item_no"])
        if row in failed:
            tier = "failed"
            reason = str(row.get("error_message") or "生成失败")
        elif item_no in NEEDS_FIX_REASONS:
            tier = "hold_out"
            reason = NEEDS_FIX_REASONS[item_no]
        else:
            tier = "direct_pool"
            reason = "人工复核可直接使用。"
        audit_rows.append(
            {
                "item_no": item_no,
                "item_id": row.get("item_id") or "",
                "生成状态": row.get("status") or "",
                "审核档位": tier,
                "审核结论": reason,
                "标题": row.get("title") or "",
                "正文": row.get("body") or "",
            }
        )
    write_csv(
        AUDIT_OUTPUT,
        ["item_no", "item_id", "生成状态", "审核档位", "审核结论", "标题", "正文"],
        audit_rows,
    )

    candidate_rows = [
        {
            "标题": row.get("title") or "",
            "正文": row.get("body") or "",
            "上下文变量(context_list)": json.dumps(
                contexts[int(row["item_no"])], ensure_ascii=False
            ),
        }
        for row in usable
    ]
    write_csv(CANDIDATE_OUTPUT, ["标题", "正文", "上下文变量(context_list)"], candidate_rows)

    summary = report["summary"]
    needs_fix_nos = [int(row["item_no"]) for row in needs_fix]
    failed_nos = [int(row["item_no"]) for row in failed]
    usable_nos = [int(row["item_no"]) for row in usable]
    preview = [
        "# 旺玥 v92 生产 100 次｜batch 876 最终人工预览",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 结论",
        "",
        "本批可直接导入 77 篇；17 篇进入后链路待修，6 篇生成失败，不补产。",
        "",
        "## 关键指标",
        "",
        "- 请求/尝试生成：100",
        "- 原始生成成功 / 失败：94 / 6",
        "- Focused 首轮直接通过：88",
        "- 后链路原文复审释放：5（item 3、23、46、49、62）",
        "- 后链路改写后机器通过：1（item 39；人工仍判需修）",
        "- 机器最终通过：94",
        f"- 机器禁用命中：{summary['forbidden_hit_count']}",
        f"- 最大两两相似度：{summary['max_pairwise_jaccard_2gram']}；相似度告警：{summary['similarity_warning_count']}",
        f"- 人工可用：77（{', '.join(map(str, usable_nos))}）",
        f"- 人工需修：17（{', '.join(map(str, needs_fix_nos))}）",
        f"- 生成失败：6（{', '.join(map(str, failed_nos))}）",
        "- 批次观察：安心/省心/踏实结尾簇 40/94；本批不据此单篇拦截。",
        "",
        "## 候选变化",
        "",
        "无生产资产变化。本轮使用 active v92，只做真实生产、机器审核、人工筛选和交付入池。",
        "",
        "## 重点看",
        "",
    ]
    for row in needs_fix:
        preview.extend(
            [
                item_section(
                    "💣", "需修", row, NEEDS_FIX_REASONS[int(row["item_no"])]
                ),
                "",
            ]
        )
    for row in failed:
        preview.extend(
            [
                item_section(
                    "⛔",
                    "生成失败",
                    row,
                    str(row.get("error_message") or "生成失败"),
                ),
                "",
            ]
        )
    preview.extend(["## 其他产出", ""])
    for row in usable:
        preview.extend([item_section("✅", "可用", row), ""])
    preview.extend(
        [
            "## 调试信息",
            "",
            "- batch_id：876",
            "- batch_code：batch_4c0e27812e56",
            "- active asset：wangyue_v3_core_storyline_article_rules v92 / id 2029",
            f"- 完整报告：`{REPORT_OUTPUT}`",
            f"- 人工审核明细：`{AUDIT_OUTPUT}`",
            f"- 77 篇候选 CSV：`{CANDIDATE_OUTPUT}`",
            f"- 最终线上导入 CSV：`{FINAL_DELIVERY_OUTPUT}`",
            "- 库存交付码：`wangyue-batch876-online-import-20260727`（77 篇已标记导出）",
            f"- 随机完整 Prompt：`{PROMPT_OUTPUT}`（item 46）",
            "",
        ]
    )
    PREVIEW_OUTPUT.write_text("\n".join(preview), encoding="utf-8")

    print(
        json.dumps(
            {
                "batch_id": BATCH_ID,
                "generated": len(generated),
                "failed": len(failed),
                "human_usable": len(usable),
                "human_needs_fix": len(needs_fix),
                "candidate_csv": str(CANDIDATE_OUTPUT),
                "audit_csv": str(AUDIT_OUTPUT),
                "preview": str(PREVIEW_OUTPUT),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
