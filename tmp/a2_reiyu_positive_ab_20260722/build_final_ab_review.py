from __future__ import annotations

import csv
import io
import json
import random
import re
from pathlib import Path


OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_positive_words_ab_20260722")
SOURCE_CSV = Path("/Users/luxifa/Downloads/正向词_子关键词导出 (1).csv")
A_REPORT = OUTPUT_DIR / "matched_A_full_raw_batch776_report.json"
B_REPORT = OUTPUT_DIR / "matched_B_light_remove_highfreq_3_batch778_report.json"
A_MANIFEST = OUTPUT_DIR / "matched_ab_plan_manifest.json"
B_MANIFEST = OUTPUT_DIR / "matched_ab_highfreq_plan_manifest.json"
V17_PREVIEW = Path(
    "/Users/luxifa/maga/outputs/a2_reiyu_v17_title_hard_drop_20260721/"
    "batch768_v17标题硬淘汰验证_10篇预览.md"
)

HUMAN = {
    "A": {
        1: ("usable", "活动、检测、老客经历和推荐关系成立。"),
        2: ("dropped", "标题加权超过20，按现行规则直接淘汰。"),
        3: ("fix", "虚构已经用积分兑到小玩具，且小玩具不属于已知活动奖品。"),
        4: ("fix", "信息了解后的认可路径被正向词带成宝宝长期使用结果，路径串线。"),
        5: ("usable", "老客回归礼、检测和长期使用感受承接自然。"),
        6: ("dropped", "标题加权超过20，按现行规则直接淘汰。"),
        7: ("usable", "活动主干清楚，冲泡体验与正向表达自然。"),
        8: ("watch", "信息认可路径带入粉质、冲泡等产品体验，未形成硬错但路径变重。"),
        9: ("usable", "集3罐换小车车、检测和老客体验成立。"),
        10: ("fix", "信息认可路径被正向词带入换季、体质和少跑医院等使用结果，路径串线。"),
    },
    "B": {
        1: ("usable", "活动、检测、老客经历和推荐关系成立。"),
        2: ("watch", "‘人人都能中个小奖’带出中奖概率暗示，建议重点看。"),
        3: ("dropped", "标题超20；正文还写‘每批到货都带检测报告’和‘之前买亏了’，事实与时间含义不稳。"),
        4: ("dropped", "标题超20；信息认可路径又补了宝宝长势结果。"),
        5: ("fix", "后链路改写失败，仍出现母乳等需替换表达。"),
        6: ("usable", "老客回归礼、每批检测和品牌认可自然。"),
        7: ("dropped", "标题加权超过20，按现行规则直接淘汰。"),
        8: ("watch", "信息认可路径带入粉质和冲泡体验，表达可读但路径偏重。"),
        9: ("usable", "集3罐换小车车、检测和老客经历成立。"),
        10: ("fix", "信息认可路径被正向词带入换季、抵抗力和少跑医院等使用结果，路径串线。"),
    },
}

MARKER = {"usable": "✅", "watch": "⚠️", "fix": "💣", "dropped": "⛔"}
LABEL = {"usable": "可用", "watch": "重点看", "fix": "需修", "dropped": "标题/链路淘汰"}
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def weighted_title_length(title: str) -> int:
    total = 0
    for char in re.sub(r"\s+", "", title):
        if char in ("\u200d", "\ufe0f"):
            continue
        total += 2 if EMOJI_RE.fullmatch(char) else 1
    return total


def parse_terms(value: str) -> list[str]:
    if "：" in value:
        value = value.split("：", 1)[1]
    return [term.strip() for term in value.removesuffix("。").split("、") if term.strip()]


def source_terms() -> list[str]:
    content = "".join(
        line for line in SOURCE_CSV.read_text(encoding="utf-8-sig").splitlines(keepends=True)
        if not line.startswith("#")
    )
    rows = list(csv.DictReader(io.StringIO(content)))
    terms = []
    for row in rows:
        for line in str(row.get("语料") or "").splitlines():
            terms.extend(parse_terms(line))
    return sorted(set(terms), key=lambda term: (-len(term), term))


def exact_hits(body: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term in body]


def report_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def selected_positive_by_item(manifest_path: Path, *, b_key: str | None = None) -> dict[int, str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    key = b_key or "a_positive"
    return {int(item["item_no"]): str(item.get(key) or "") for item in manifest["items"]}


def metrics(arm: str, payload: dict, selected: dict[int, str], all_terms: list[str]) -> dict:
    report = payload["report"]
    items = report["items"]
    generated = [item for item in items if item.get("body")]
    selected_hit_counts = []
    all_hit_counts = []
    selected_hit_items = []
    item_metrics = {}
    llm_rewrite_items = []
    title_drop_items = []
    for item in items:
        item_no = int(item["item_no"])
        body = str(item.get("body") or "")
        selected_terms = parse_terms(selected.get(item_no, ""))
        selected_hits = exact_hits(body, selected_terms)
        global_hits = exact_hits(body, all_terms)
        if body:
            selected_hit_counts.append(len(selected_hits))
            all_hit_counts.append(len(global_hits))
            if selected_hits:
                selected_hit_items.append(item_no)
        if any(
            stage.get("capability") == "content.rewrite"
            for stage in item.get("trace_stage_calls") or []
        ):
            llm_rewrite_items.append(item_no)
        if "标题加权长度超过20" in str(item.get("rewrite_reason") or ""):
            title_drop_items.append(item_no)
        item_metrics[item_no] = {
            "selected_terms": selected_terms,
            "selected_hits": selected_hits,
            "global_hits": global_hits,
            "title_weighted_length": weighted_title_length(str(item.get("title") or "")),
        }
    human_counts = {status: 0 for status in MARKER}
    human_items = {status: [] for status in MARKER}
    for item_no, (status, _) in HUMAN[arm].items():
        human_counts[status] += 1
        human_items[status].append(item_no)
    summary = report["summary"]
    return {
        "attempted": len(items),
        "body_produced": len(generated),
        "generated_status": int(summary["generated_count"]),
        "failed_status": int(summary["failed_count"]),
        "machine_final_pass": int(summary["hard_pass_count"]),
        "postprocess_items": int(summary["rewrite_item_count"]),
        "remaining_rewrite": int(summary["remaining_rewrite_required_count"]),
        "llm_rewrite_items": llm_rewrite_items,
        "title_drop_items": title_drop_items,
        "forbidden_hits": int(summary["forbidden_hit_count"]),
        "max_similarity": float(summary["max_pairwise_jaccard_2gram"]),
        "similarity_warnings": int(summary["similarity_warning_count"]),
        "selected_hit_item_count": len(selected_hit_items),
        "selected_hit_items": selected_hit_items,
        "avg_selected_hits": round(sum(selected_hit_counts) / len(selected_hit_counts), 2),
        "max_selected_hits": max(selected_hit_counts, default=0),
        "avg_global_hits": round(sum(all_hit_counts) / len(all_hit_counts), 2),
        "human_counts": human_counts,
        "human_items": human_items,
        "item_metrics": item_metrics,
    }


def save_prompt(payload: dict, label: str) -> Path:
    candidates = [
        item for item in payload["report"]["items"]
        if (item.get("generation_snapshot") or {}).get("rendered_prompt")
    ]
    sample = random.SystemRandom().choice(candidates)
    path = OUTPUT_DIR / f"batch{payload['batch_id']}_{label}_随机完整Prompt_item{sample['item_no']}.md"
    prompt = sample["generation_snapshot"]["rendered_prompt"]
    path.write_text(
        "\n".join(
            [
                f"# a2礼遇正向词单变量｜{label}｜随机完整 Prompt",
                "",
                f"- batch_id: {payload['batch_id']}",
                f"- item_no: {sample['item_no']}",
                f"- title: {sample.get('title') or ''}",
                "",
                "```text",
                prompt,
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def item_section(arm: str, item: dict, metric: dict) -> list[str]:
    item_no = int(item["item_no"])
    status, reason = HUMAN[arm][item_no]
    hits = "、".join(metric["selected_hits"]) or "无精确命中"
    return [
        f"### {MARKER[status]} item {item_no}｜{LABEL[status]}｜{item.get('title') or ''}",
        "",
        f"判断：{reason}",
        f"标题加权：{metric['title_weighted_length']}；本条正向槽精确命中：{hits}",
        "",
        str(item.get("body") or "（无正文）"),
        "",
    ]


def main() -> None:
    all_terms = source_terms()
    a_payload = report_payload(A_REPORT)
    b_payload = report_payload(B_REPORT)
    a_selected = selected_positive_by_item(A_MANIFEST)
    b_selected = selected_positive_by_item(B_MANIFEST, b_key="b_positive")
    a_metrics = metrics("A", a_payload, a_selected, all_terms)
    b_metrics = metrics("B", b_payload, b_selected, all_terms)
    a_prompt = save_prompt(a_payload, "A完整原始语料")
    b_prompt = save_prompt(b_payload, "B轻删3个高频泛词")

    lines = [
        "# a2礼遇｜正向词素材单变量 A/B｜10+10篇配对回测",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 结论",
        "",
        "暂不替换正式v17。两组都能让正文自然命中更多正向表达，但人工直接可用只有4/10和3/10，低于v17的7/10。只删放心、省心、真香没有提升机器通过或人工可用；真正反复出现的问题，是宝宝状态和使用结果类正向词污染了‘信息了解后的认可’路径。下一轮应只改路由：完整原始正向词仅进入老客使用感受，信息认可路径不挂宝宝状态正向词。",
        "",
        "## 关键指标",
        "",
        "| 指标 | A 完整原始语料 | B 仅删放心/省心/真香 |",
        "|---|---:|---:|",
        f"| 发起/正文产出 | {a_metrics['attempted']}/{a_metrics['body_produced']} | {b_metrics['attempted']}/{b_metrics['body_produced']} |",
        f"| 链路最终生成状态 | {a_metrics['generated_status']}/10 | {b_metrics['generated_status']}/10 |",
        f"| 机器最终通过 | {a_metrics['machine_final_pass']}/10 | {b_metrics['machine_final_pass']}/10 |",
        f"| 后链路处理条数 | {a_metrics['postprocess_items']} | {b_metrics['postprocess_items']} |",
        f"| LLM content.rewrite | {len(a_metrics['llm_rewrite_items'])}次，item {a_metrics['llm_rewrite_items']} | {len(b_metrics['llm_rewrite_items'])}次，item {b_metrics['llm_rewrite_items']} |",
        f"| 正向槽有精确命中的文章 | {a_metrics['selected_hit_item_count']}/10 | {b_metrics['selected_hit_item_count']}/10 |",
        f"| 每篇平均正向槽命中数 | {a_metrics['avg_selected_hits']} | {b_metrics['avg_selected_hits']} |",
        f"| 每篇平均原始池正向词命中数 | {a_metrics['avg_global_hits']} | {b_metrics['avg_global_hits']} |",
        f"| 最大2-gram相似度 | {a_metrics['max_similarity']} | {b_metrics['max_similarity']} |",
        f"| 人工可用/重点看/需修或淘汰 | {a_metrics['human_counts']['usable']}/{a_metrics['human_counts']['watch']}/{a_metrics['human_counts']['fix'] + a_metrics['human_counts']['dropped']} | {b_metrics['human_counts']['usable']}/{b_metrics['human_counts']['watch']}/{b_metrics['human_counts']['fix'] + b_metrics['human_counts']['dropped']} |",
        "",
        "参考基线v17 batch768：机器最终通过7/10、人工直接可用7篇、LLM rewrite 0次。原始池没有带来总体可用率提升。",
        "",
        "## 候选变化",
        "",
        "- A：正向词CSV的12行原始语料完整回填，不压缩、不改写。",
        "- B：基于A只删除3个高频泛词：放心、省心、真香；其他原始词保持不动。",
        "- 两批逐篇复用同一份业务规则、来源、原因、活动内容、检测、认可表达和模型配置；非正向词计划差异为0。",
        "- B实际变化落在item 1、3、7；其他7篇是同Prompt随机对照。",
        "- 先前batch774/775/777因抽样位相或删项未落样，只作为诊断，不计入最终结论。",
        "",
        "## A 完整原始语料｜重点看",
        "",
    ]
    a_items = {int(item["item_no"]): item for item in a_payload["report"]["items"]}
    b_items = {int(item["item_no"]): item for item in b_payload["report"]["items"]}
    for status in ("dropped", "fix", "watch"):
        for item_no in a_metrics["human_items"][status]:
            lines.extend(item_section("A", a_items[item_no], a_metrics["item_metrics"][item_no]))
    lines.extend(["## A 完整原始语料｜其他产出", ""])
    for item_no in a_metrics["human_items"]["usable"]:
        lines.extend(item_section("A", a_items[item_no], a_metrics["item_metrics"][item_no]))

    lines.extend(["## B 轻删3个高频泛词｜重点看", ""])
    for status in ("dropped", "fix", "watch"):
        for item_no in b_metrics["human_items"][status]:
            lines.extend(item_section("B", b_items[item_no], b_metrics["item_metrics"][item_no]))
    lines.extend(["## B 轻删3个高频泛词｜其他产出", ""])
    for item_no in b_metrics["human_items"]["usable"]:
        lines.extend(item_section("B", b_items[item_no], b_metrics["item_metrics"][item_no]))

    lines.extend(
        [
            "## 调试信息",
            "",
            "- A batch_id: 776；candidate asset_id: 1975 / v19 / archived candidate",
            "- B batch_id: 778；candidate asset_id: 1977 / v21 / archived candidate",
            "- 正式生产资产已恢复：asset_id 1972 / v17 / active production",
            f"- A report: `{A_REPORT}`",
            f"- B report: `{B_REPORT}`",
            f"- A rendered prompt: `{a_prompt}`",
            f"- B rendered prompt: `{b_prompt}`",
            f"- v17 baseline review: `{V17_PREVIEW}`",
            "",
        ]
    )
    preview_path = OUTPUT_DIR / "a2礼遇_正向词素材单变量_AB_10加10篇回测预览.md"
    preview_path.write_text("\n".join(lines), encoding="utf-8")
    metrics_path = OUTPUT_DIR / "a2礼遇_正向词素材单变量_AB_metrics.json"
    metrics_path.write_text(
        json.dumps({"A": a_metrics, "B": b_metrics}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "preview": str(preview_path),
                "a_prompt": str(a_prompt),
                "b_prompt": str(b_prompt),
                "metrics": str(metrics_path),
                "A_summary": {key: value for key, value in a_metrics.items() if key != "item_metrics"},
                "B_summary": {key: value for key, value in b_metrics.items() if key != "item_metrics"},
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
