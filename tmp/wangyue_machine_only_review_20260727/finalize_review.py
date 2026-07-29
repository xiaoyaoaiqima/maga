from __future__ import annotations

import csv
import json
import random
import re
from pathlib import Path

from app.services.forbidden_term_review_service import WANGYUE_STATIC_FORBIDDEN_TERMS


ROOT = Path("/Users/luxifa/maga")
OUTPUT_DIR = (
    ROOT
    / "outputs/0705_wangyue_product_relation_evidence"
    / "20260727_wangyue_machine_only_pool_review"
)
PACKET_PATH = OUTPUT_DIR / "20260727_wangyue_machine_only_150_review_packet.json"
DECISIONS_PATH = (
    ROOT / "tmp/wangyue_machine_only_review_20260727/review_decisions.json"
)
AUDIT_PATH = OUTPUT_DIR / "20260727_wangyue_machine_only_150_human_audit.csv"
PREVIEW_PATH = OUTPUT_DIR / "20260727_wangyue_machine_only_150_human_preview.md"
PROMPT_PATH = OUTPUT_DIR / "20260727_wangyue_machine_only_150_sampled_rendered_prompt.md"
SUMMARY_PATH = OUTPUT_DIR / "20260727_wangyue_machine_only_150_review_summary.json"
SIMILARITY_THRESHOLD = 0.42


def text_2grams(text: str) -> set[str]:
    clean = re.sub(r"\s+", "", text or "")
    return {
        clean[index : index + 2]
        for index in range(max(len(clean) - 1, 0))
        if clean[index : index + 2].strip()
    }


def jaccard(left: str, right: str) -> float:
    left_tokens = text_2grams(left)
    right_tokens = text_2grams(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def main() -> None:
    rows = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    decisions = json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    inventory_ids = {str(row["inventory_id"]) for row in rows}
    unknown_ids = sorted(set(decisions) - inventory_ids)
    if unknown_ids:
        raise ValueError(f"unknown inventory ids: {unknown_ids}")

    for row in rows:
        decision = decisions.get(str(row["inventory_id"])) or {}
        row["human_tier"] = str(decision.get("tier") or "direct_pool")
        row["human_reason"] = str(decision.get("reason") or "")

    warning_ordinals: set[int] = set()
    warning_pairs: list[dict[str, object]] = []
    max_similarity = 0.0
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            score = round(jaccard(str(left["body"]), str(right["body"])), 4)
            max_similarity = max(max_similarity, score)
            if score >= SIMILARITY_THRESHOLD:
                warning_ordinals.update((int(left["ordinal"]), int(right["ordinal"])))
                warning_pairs.append(
                    {
                        "left_ordinal": int(left["ordinal"]),
                        "right_ordinal": int(right["ordinal"]),
                        "score": score,
                    }
                )

    forbidden_rows = []
    for row in rows:
        text = f"{row['title']}\n{row['body']}"
        hits = [term for term in WANGYUE_STATIC_FORBIDDEN_TERMS if term in text]
        if hits:
            forbidden_rows.append(
                {"ordinal": int(row["ordinal"]), "hits": list(dict.fromkeys(hits))}
            )

    fieldnames = [
        "标题",
        "正文",
        "审核档位",
        "人工原因",
        "inventory_id",
        "content_id",
        "batch_id",
        "item_no",
        "rule_asset_version",
        "内容方向",
    ]
    with AUDIT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "标题": row["title"],
                    "正文": row["body"],
                    "审核档位": row["human_tier"],
                    "人工原因": row["human_reason"],
                    "inventory_id": row["inventory_id"],
                    "content_id": row["content_id"],
                    "batch_id": row["batch_id"],
                    "item_no": row.get("item_no") or "",
                    "rule_asset_version": row["rule_asset_version"],
                    "内容方向": row["category"],
                }
            )

    direct_rows = [row for row in rows if row["human_tier"] == "direct_pool"]
    needs_rows = [row for row in rows if row["human_tier"] == "needs_fix"]
    watch_rows = [row for row in rows if row["human_tier"] == "watch"]
    source_batches = sorted({int(row["batch_id"]) for row in rows})

    sample_candidates = [row for row in direct_rows if str(row.get("rendered_prompt") or "").strip()]
    sampled = random.Random(20260727).choice(sample_candidates)
    PROMPT_PATH.write_text(
        "\n".join(
            [
                "# 旺玥仅机审库存复核｜随机完整 rendered prompt",
                "",
                f"- source batch_id：{sampled['batch_id']}",
                f"- source item_no：{sampled.get('item_no')}",
                f"- inventory_id：{sampled['inventory_id']}",
                f"- title：{sampled['title']}",
                "",
                "## Rendered Prompt",
                "",
                str(sampled["rendered_prompt"]),
                "",
            ]
        ),
        encoding="utf-8",
    )

    lines = [
        "# 旺玥未导出库存｜仅机审 150 篇人工复核",
        "",
        "## 结论",
        "",
        f"本轮 150 篇中，{len(direct_rows)} 篇可直接保留，{len(needs_rows)} 篇需修，{len(watch_rows)} 篇观察。",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 关键指标",
        "",
        "- 待复核库存：150；来源文章均为历史机器最终通过。",
        f"- 人工可用 {len(direct_rows)}：{', '.join(str(row['ordinal']) for row in direct_rows)}",
        f"- 人工观察 {len(watch_rows)}：{', '.join(str(row['ordinal']) for row in watch_rows) or '无'}",
        f"- 人工需修 {len(needs_rows)}：{', '.join(str(row['ordinal']) for row in needs_rows)}",
        f"- 当前静态禁词命中：{len(forbidden_rows)} 篇。",
        f"- 最大两两 2gram Jaccard：{max_similarity:.4f}；相似度告警：{len(warning_ordinals)} 篇 / {len(warning_pairs)} 对。",
        f"- 来源批次：{', '.join(str(batch_id) for batch_id in source_batches)}。",
        "",
        "## Candidate Change",
        "",
        "- 本轮不修改旺玥生产资产，只把历史仅机审库存按当前人工口径重新分层。",
        "- 强因果、明显效果、长高长肉、专注改善和广告营销感不单独判错。",
        "- 只处理产品事实、竞品拉踩、疾病就医、孩子错误动作、旧 Prompt 残留和明显病句。",
        "",
        "## 重点看",
        "",
    ]
    for row in [*needs_rows, *watch_rows]:
        marker = "💣" if row["human_tier"] == "needs_fix" else "👀"
        status = "需修" if row["human_tier"] == "needs_fix" else "观察"
        lines.extend(
            [
                f"### {marker} item {row['ordinal']}｜{status}｜{row['title']}",
                "",
                f"- 来源：batch {row['batch_id']} item {row.get('item_no')}｜v{row['rule_asset_version']}｜inventory {row['inventory_id']}",
                f"- 问题：{row['human_reason']}",
                "",
                str(row["body"]),
                "",
            ]
        )
    lines.extend(["## 其他产出", ""])
    for row in direct_rows:
        lines.extend(
            [
                f"### ✅ item {row['ordinal']}｜可用｜{row['title']}",
                "",
                str(row["body"]),
                "",
            ]
        )
    lines.extend(
        [
            "## 调试信息",
            "",
            f"- 审核 CSV：`{AUDIT_PATH}`",
            f"- 原始复核包：`{PACKET_PATH}`",
            f"- 随机完整 rendered prompt：`{PROMPT_PATH}`",
            "- 文章池：`/Users/luxifa/maga/local_data/a2_reiyu_delivery/article_inventory.sqlite3`",
            "",
        ]
    )
    PREVIEW_PATH.write_text("\n".join(lines), encoding="utf-8")

    summary = {
        "input_count": len(rows),
        "machine_final_pass": len(rows),
        "human_direct_pool": len(direct_rows),
        "human_watch": len(watch_rows),
        "human_needs_fix": len(needs_rows),
        "forbidden_item_count": len(forbidden_rows),
        "forbidden_rows": forbidden_rows,
        "max_pairwise_jaccard_2gram": round(max_similarity, 4),
        "similarity_warning_item_count": len(warning_ordinals),
        "similarity_warning_pair_count": len(warning_pairs),
        "similarity_warning_pairs": warning_pairs,
        "source_batches": source_batches,
        "sampled_prompt": {
            "batch_id": sampled["batch_id"],
            "item_no": sampled.get("item_no"),
            "inventory_id": sampled["inventory_id"],
            "title": sampled["title"],
        },
        "audit_path": str(AUDIT_PATH),
        "preview_path": str(PREVIEW_PATH),
        "prompt_path": str(PROMPT_PATH),
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
