from __future__ import annotations

import json
import random
import re
from pathlib import Path


OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_positive_usage_and_loyalty_20260722")
REPORTS = {
    "B": OUTPUT_DIR / "batch783_B_old_one_or_two_rule_report.json",
    "C": OUTPUT_DIR / "batch781_C_positive_usage_report.json",
    "D": OUTPUT_DIR / "batch782_D_loyal_customer_recognition_report.json",
}
MANIFEST_PATH = OUTPUT_DIR / "matched_cd_plan_manifest.json"

HUMAN = {
    "B": {
        1: ("usable", "活动、检测、长肉与转奶经历成立。"),
        2: ("usable", "信息认可路径清楚，正向词没有堆砌。"),
        3: ("usable", "积分、检测、长肉和冲泡体验承接自然。"),
        4: ("fix", "活动素材只说积分可换礼，正文自行新增玩具、绘本和小家电。"),
        5: ("fix", "素材只说可以领小听粉，正文虚构自己已经领取。"),
        6: ("usable", "老客礼和检测带出的品牌认可成立。"),
        7: ("dropped", "标题加权25超过20，按现行规则直接淘汰。"),
        8: ("dropped", "标题加权22超过20，按现行规则直接淘汰。"),
        9: ("usable", "3罐换小车车与老客使用体验成立。"),
        10: ("usable", "集罐、检测和品牌认可逻辑成立。"),
    },
    "C": {
        1: ("usable", "正向词使用更自由，但长肉、转奶、安心没有明显机械罗列。"),
        2: ("usable", "信息路径未改，活动和检测认可成立。"),
        3: ("usable", "粉质、冲泡、奶香等多项正向词融入自然。"),
        4: ("fix", "把内容方向原句‘再另起一段……’直接写进正文。"),
        5: ("dropped", "标题加权21超过20，按现行规则直接淘汰。"),
        6: ("usable", "老客身份、活动和检测认可自然。"),
        7: ("usable", "正向词较多但都围绕真实冲泡和宝宝接受体验。"),
        8: ("dropped", "标题加权21超过20，按现行规则直接淘汰。"),
        9: ("usable", "机器复核异常不等于内容错误；正文事实与老客体验成立。"),
        10: ("usable", "集罐与检测认可简洁清楚。"),
    },
    "D": {
        1: ("usable", "老客使用感受路径未变，正文成立。"),
        2: ("usable", "先交代老客背景，再由活动和每批检测带出更认可，路径成立。"),
        3: ("usable", "老客使用感受路径未变，正文成立。"),
        4: ("dropped", "老客更认可的语义成立，但标题加权21超过20，直接淘汰。"),
        5: ("usable", "老客背景和使用感受成立；疾病效果按当前业务反馈不判错。"),
        6: ("usable", "‘家里一直喝’只是老客背景，认可提升来自老客礼和每批检测。"),
        7: ("usable", "老客使用感受路径未变，正文成立。"),
        8: ("watch", "老客更认可的逻辑正确，结尾‘愿意推荐给周围妈妈，踏实’略生硬。"),
        9: ("usable", "老客使用感受路径未变，正文成立。"),
        10: ("fix", "路径逻辑成立，但结尾‘经得起比较推荐给宝妈们’缺少停顿，句子粘连。"),
    },
}

MARKER = {"usable": "✅", "watch": "⚠️", "fix": "💣", "dropped": "⛔"}
LABEL = {"usable": "可用", "watch": "重点看", "fix": "需修", "dropped": "标题淘汰"}
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def weighted_title_length(title: str) -> int:
    total = 0
    for char in re.sub(r"\s+", "", title):
        if char in ("\u200d", "\ufe0f"):
            continue
        total += 2 if EMOJI_RE.fullmatch(char) else 1
    return total


def parse_terms(value: str) -> list[str]:
    terms = []
    for line in value.splitlines():
        if "：" in line:
            line = line.split("：", 1)[1]
        terms.extend(
            term.strip()
            for term in line.removesuffix("。").split("、")
            if term.strip()
        )
    return terms


def exact_hits(body: str, positive_expression: str) -> list[str]:
    return [term for term in parse_terms(positive_expression) if term in body]


def load_payload(label: str) -> dict:
    return json.loads(REPORTS[label].read_text(encoding="utf-8"))


def metrics(label: str, payload: dict, plan_items: dict[int, dict]) -> dict:
    report = payload["report"]
    items = report["items"]
    human_counts = {status: 0 for status in MARKER}
    human_items = {status: [] for status in MARKER}
    llm_rewrite_items = []
    hit_counts = []
    old_path_hit_counts = []
    item_hits = {}
    for item in items:
        item_no = int(item["item_no"])
        status, _ = HUMAN[label][item_no]
        human_counts[status] += 1
        human_items[status].append(item_no)
        if any(
            stage.get("capability") == "content.rewrite"
            for stage in item.get("trace_stage_calls") or []
        ):
            llm_rewrite_items.append(item_no)
        hits = exact_hits(
            str(item.get("body") or ""),
            str(plan_items[item_no].get("positive_expression") or ""),
        )
        item_hits[item_no] = hits
        if item.get("body"):
            hit_counts.append(len(hits))
            if "老客使用感受" in str(plan_items[item_no].get("c_business_rule") or ""):
                old_path_hit_counts.append(len(hits))
    summary = report["summary"]
    return {
        "attempted": len(items),
        "body_count": sum(1 for item in items if item.get("body")),
        "generated_status": int(summary["generated_count"]),
        "failed_status": int(summary["failed_count"]),
        "machine_final_pass": int(summary["hard_pass_count"]),
        "llm_rewrite_items": llm_rewrite_items,
        "forbidden_hits": int(summary["forbidden_hit_count"]),
        "max_similarity": float(summary["max_pairwise_jaccard_2gram"]),
        "similarity_warnings": int(summary["similarity_warning_count"]),
        "avg_selected_hits": round(sum(hit_counts) / len(hit_counts), 2) if hit_counts else 0,
        "avg_old_path_hits": (
            round(sum(old_path_hit_counts) / len(old_path_hit_counts), 2)
            if old_path_hit_counts
            else 0
        ),
        "human_counts": human_counts,
        "human_items": human_items,
        "item_hits": item_hits,
    }


def save_prompt(label: str, payload: dict, eligible_item_nos: list[int]) -> Path:
    candidates = [
        item
        for item in payload["report"]["items"]
        if int(item["item_no"]) in eligible_item_nos
        and (item.get("generation_snapshot") or {}).get("rendered_prompt")
    ]
    sample = random.SystemRandom().choice(candidates)
    path = OUTPUT_DIR / f"batch{payload['batch_id']}_{label}_随机完整Prompt_item{sample['item_no']}.md"
    path.write_text(
        "\n".join(
            [
                f"# a2礼遇｜{label}｜随机完整 Prompt",
                "",
                f"- batch_id: {payload['batch_id']}",
                f"- item_no: {sample['item_no']}",
                f"- title: {sample.get('title') or ''}",
                "",
                "```text",
                sample["generation_snapshot"]["rendered_prompt"],
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def item_section(label: str, item: dict, metric: dict) -> list[str]:
    item_no = int(item["item_no"])
    status, reason = HUMAN[label][item_no]
    hits = "、".join(metric["item_hits"][item_no]) or "无精确命中"
    return [
        f"### {MARKER[status]} {label} item {item_no}｜{LABEL[status]}｜{item.get('title') or ''}",
        "",
        f"判断：{reason}",
        f"标题加权：{weighted_title_length(str(item.get('title') or ''))}；本条正向词精确命中：{hits}",
        "",
        str(item.get("body") or "（无正文）"),
        "",
    ]


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    plan_items = {int(item["item_no"]): item for item in manifest["items"]}
    payloads = {label: load_payload(label) for label in REPORTS}
    all_metrics = {
        label: metrics(label, payload, plan_items) for label, payload in payloads.items()
    }

    old_path_items = [1, 3, 5, 7, 9]
    information_items = [2, 4, 6, 8, 10]
    prompt_paths = {
        "B": save_prompt("B旧一两个规则", payloads["B"], old_path_items),
        "C": save_prompt("C使用适合融入文章的正向词", payloads["C"], old_path_items),
        "D": save_prompt("D老客了解信息后更认可", payloads["D"], information_items),
    }

    b = all_metrics["B"]
    c = all_metrics["C"]
    d = all_metrics["D"]
    lines = [
        "# a2礼遇｜正向词数量与老客更认可路径｜配对回测",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 结论",
        "",
        "两条调整都可以保留在候选方向，但暂不替换正式v17。把‘只挑一两个’改成‘使用适合融入文章的正向词’后，老客路径的正向词精确命中均值上升，人工可用从6/10到7/10，没有出现明显机械堆词。把信息路径改成‘老客了解信息后更认可’后，老客身份、长期购买和简短使用背景不再是假冲突；认可提升仍由活动与每批检测承接。D的直接可用仍是7/10，剩余问题来自标题和句子粘连，不是路径定义。",
        "",
        "## 关键指标",
        "",
        "| 指标 | B 旧‘一两个’ | C 使用适合融入的正向词 | D 老客了解后更认可 |",
        "|---|---:|---:|---:|",
        f"| 发起/正文产出 | 10/{b['body_count']} | 10/{c['body_count']} | 10/{d['body_count']} |",
        f"| 机器最终通过 | {b['machine_final_pass']}/10 | {c['machine_final_pass']}/10 | {d['machine_final_pass']}/10 |",
        f"| LLM content.rewrite | {len(b['llm_rewrite_items'])} | {len(c['llm_rewrite_items'])} | {len(d['llm_rewrite_items'])} |",
        f"| 老客路径平均正向词精确命中 | {b['avg_old_path_hits']} | {c['avg_old_path_hits']} | {d['avg_old_path_hits']} |",
        f"| 最大2-gram相似度 | {b['max_similarity']} | {c['max_similarity']} | {d['max_similarity']} |",
        f"| 人工可用 | {b['human_counts']['usable']}/10 | {c['human_counts']['usable']}/10 | {d['human_counts']['usable']}/10 |",
        f"| 重点看 | {b['human_counts']['watch']} | {c['human_counts']['watch']} | {d['human_counts']['watch']} |",
        f"| 需修/标题淘汰 | {b['human_counts']['fix'] + b['human_counts']['dropped']} | {c['human_counts']['fix'] + c['human_counts']['dropped']} | {d['human_counts']['fix'] + d['human_counts']['dropped']} |",
        "",
        "B与C逐篇使用同一来源、原因、活动内容、认可表达和正向词；只在5条老客路径中改变正向词使用句。C与D同样逐篇配对，只改变5条信息路径的认可定义。",
        "",
        "## 候选变化",
        "",
        "### 变量1｜正向词数量",
        "",
        "- 旧：正向表达只挑和本篇体验贴合的一两个自然带入，不必覆盖整组词。",
        "- 新：使用适合融入文章的正向词。",
        "- 只改8条老客使用感受规则的‘写法’列；信息路径原本没有旧句。",
        "",
        "### 变量2｜认可路径",
        "",
        "- 旧：信息了解后的认可，只根据活动和每批检测表达品牌感受，不补长期使用、转奶或回归经历。",
        "- 新：老客了解信息后更认可，可以自然交代长期购买、老客身份或简短使用背景；认可提升由活动和每批检测承接，不必展开宝宝状态或产品效果。",
        "- 允许：‘家里一直喝’‘买了挺久’‘作为老用户’等背景。",
        "- 仍不建议：为了证明更认可，额外铺开长肉、转奶、抵抗力等宝宝结果；这些应留在老客使用感受路径。",
        "",
        "## B/C 重点看",
        "",
    ]
    items_by_label = {
        label: {int(item["item_no"]): item for item in payload["report"]["items"]}
        for label, payload in payloads.items()
    }
    for label in ("B", "C"):
        metric = all_metrics[label]
        for status in ("dropped", "fix", "watch"):
            for item_no in metric["human_items"][status]:
                lines.extend(item_section(label, items_by_label[label][item_no], metric))
    lines.extend(["## B/C 其他产出", ""])
    for label in ("B", "C"):
        metric = all_metrics[label]
        for item_no in metric["human_items"]["usable"]:
            lines.extend(item_section(label, items_by_label[label][item_no], metric))

    lines.extend(["## D 重点看", ""])
    for status in ("dropped", "fix", "watch"):
        for item_no in d["human_items"][status]:
            lines.extend(item_section("D", items_by_label["D"][item_no], d))
    lines.extend(["## D 其他产出", ""])
    for item_no in d["human_items"]["usable"]:
        lines.extend(item_section("D", items_by_label["D"][item_no], d))

    lines.extend(
        [
            "## 调试信息",
            "",
            "- B batch_id: 783；base asset_id: 1978 / v22 / archived candidate",
            "- C batch_id: 781；candidate asset_id: 1980 / v23 / archived candidate",
            "- D batch_id: 782；candidate asset_id: 1981 / v24 / archived candidate",
            "- 正式生产资产：1972 / v17 / active production",
            f"- B report: `{REPORTS['B']}`",
            f"- C report: `{REPORTS['C']}`",
            f"- D report: `{REPORTS['D']}`",
            f"- B prompt: `{prompt_paths['B']}`",
            f"- C prompt: `{prompt_paths['C']}`",
            f"- D prompt: `{prompt_paths['D']}`",
            "",
        ]
    )
    preview_path = OUTPUT_DIR / "a2礼遇_正向词数量与老客更认可路径_配对回测预览.md"
    preview_path.write_text("\n".join(lines), encoding="utf-8")
    metrics_path = OUTPUT_DIR / "a2礼遇_正向词数量与老客更认可路径_metrics.json"
    metrics_path.write_text(
        json.dumps(all_metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "preview": str(preview_path),
                "prompts": {key: str(value) for key, value in prompt_paths.items()},
                "metrics": str(metrics_path),
                "B": {key: value for key, value in b.items() if key not in {"item_hits"}},
                "C": {key: value for key, value in c.items() if key not in {"item_hits"}},
                "D": {key: value for key, value in d.items() if key not in {"item_hits"}},
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
