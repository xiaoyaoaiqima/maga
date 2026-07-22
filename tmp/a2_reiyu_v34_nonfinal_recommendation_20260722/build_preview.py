"""Build the matched closing-placement experiment preview."""
from __future__ import annotations

import json
from pathlib import Path


BASELINE_PATH = Path(
    "/Users/luxifa/maga/outputs/a2_reiyu_v33_usage_merge_20260722/batch808_candidate_report.json"
)
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v34_nonfinal_recommendation_20260722")
CANDIDATE_PATH = OUTPUT_DIR / "batch809_report.json"
PROMPT_PATH = OUTPUT_DIR / "batch809_随机完整Prompt_item6.md"
PREVIEW_PATH = OUTPUT_DIR / "batch809_取消结尾强制推荐_10篇匹配回测.md"

ACTION_GROUPS = {
    "明确推荐": ["推荐", "只推"],
    "分享安利": ["安利", "分享给", "发到", "发给", "拉上姐妹", "拉上朋友"],
    "号召尝试": ["冲就对", "去冲", "试试", "听劝", "闭眼入"],
    "持续选择": ["回购", "值得囤", "继续喝", "继续用"],
}

JUDGMENTS = {
    1: ("⚠️", "重点看", "正文事实可用；机器业务审核未返回JSON。结尾仍是“放心＋安利＋冲”。"),
    2: ("⚠️", "重点看", "正文事实可用；机器业务审核未返回JSON。结尾仍叠了试试、安利、值得推荐。"),
    3: ("💣", "需修", "后链路改写失败，最终命中“母乳”；该问题与本次收尾规则无关。"),
    4: ("✅", "可用", "推荐先出现，最后停在“妈妈心里更有数”，顺序比基线更自然。"),
    5: ("✅", "可用", "最后停在分享动作，没有再补品牌总结句。"),
    6: ("👀", "观察", "最后停在分享动作，但“选对了就是选对了”有轻微重复。"),
    7: ("💣", "需修", "“以前总担心批次问题”形成产品批次负面暗示，需要改写。"),
    8: ("💣", "需修", "“囤货也能攒罐”重新带出攒罐联想，不符合当前集罐表达边界。"),
    9: ("✅", "可用", "最后只保留一条推荐给闺蜜的动作，未连续堆推荐词。"),
    10: ("✅", "可用", "认可和体验完整，最后用朋友询问场景承接推荐。"),
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _tail_action_stats(report: dict, window: int = 80) -> tuple[int, int, dict[int, list[str]]]:
    per_item: dict[int, list[str]] = {}
    for item in report.get("items") or []:
        tail = str(item.get("body") or "").replace("\n", "")[-window:]
        hits = [
            group
            for group, phrases in ACTION_GROUPS.items()
            if any(phrase in tail for phrase in phrases)
        ]
        per_item[int(item["item_no"])] = hits
    any_action = sum(bool(hits) for hits in per_item.values())
    stacked = sum(len(hits) >= 2 for hits in per_item.values())
    return any_action, stacked, per_item


def _machine_split(report: dict) -> tuple[list[int], list[int]]:
    direct: list[int] = []
    rewritten: list[int] = []
    for item in report.get("items") or []:
        if item.get("hard_pass") is not True:
            continue
        review = ((item.get("quality") or {}).get("review_report") or {})
        initial = ((review.get("forbidden_terms_review") or {}).get("initial_hits") or [])
        (rewritten if initial else direct).append(int(item["item_no"]))
    return direct, rewritten


def _peace_ratio(report: dict) -> float:
    clusters = ((report.get("summary") or {}).get("closure_cluster_stats") or {}).get("clusters") or []
    cluster = next((item for item in clusters if item.get("cluster_code") == "peace_of_mind"), {})
    return float(cluster.get("ratio") or 0)


def _section(item: dict) -> str:
    item_no = int(item["item_no"])
    marker, label, reason = JUDGMENTS[item_no]
    return (
        f"### {marker} item {item_no}｜{label}｜{item.get('title') or '无标题'}\n\n"
        f"判断：{reason}\n\n{item.get('body') or '无正文'}\n"
    )


def main() -> None:
    baseline = _load(BASELINE_PATH)
    candidate = _load(CANDIDATE_PATH)
    base_summary = baseline.get("summary") or {}
    cand_summary = candidate.get("summary") or {}
    base_any, base_stacked, _ = _tail_action_stats(baseline)
    cand_any, cand_stacked, cand_actions = _tail_action_stats(candidate)
    base_direct, base_rewritten = _machine_split(baseline)
    cand_direct, cand_rewritten = _machine_split(candidate)
    items = list(candidate.get("items") or [])

    priority = [
        _section(item)
        for item in items
        if JUDGMENTS[int(item["item_no"])][0] in {"💣", "⚠️"}
    ]
    others = [
        _section(item)
        for item in items
        if JUDGMENTS[int(item["item_no"])][0] not in {"💣", "⚠️"}
    ]

    table = "\n".join(
        [
            "| 指标 | batch 808基线 | batch 809候选 |",
            "|---|---:|---:|",
            f"| 原始正文 | 10/10 | 10/10 |",
            f"| 最终生成状态 | {base_summary.get('generated_count')}/10 | {cand_summary.get('generated_count')}/10 |",
            f"| 机器直接通过 | {len(base_direct)}/10 | {len(cand_direct)}/10 |",
            f"| 改写后机器通过 | {len(base_rewritten)}/10 | {len(cand_rewritten)}/10 |",
            f"| 机器最终hard pass | {base_summary.get('hard_pass_count')}/10 | {cand_summary.get('hard_pass_count')}/10 |",
            "| 人工业务可用 | 9/10 | 7/10 |",
            f"| 结尾仍有推荐动作 | {base_any}/10 | {cand_any}/10 |",
            f"| 结尾叠加两类以上推荐动作 | {base_stacked}/10 | {cand_stacked}/10 |",
            f"| 安心类收尾占比 | {_peace_ratio(baseline):.4f} | {_peace_ratio(candidate):.4f} |",
            f"| 最大2-gram相似度 | {base_summary.get('max_pairwise_jaccard_2gram')} | {cand_summary.get('max_pairwise_jaccard_2gram')} |",
        ]
    )

    preview = "\n".join(
        [
            "# a2礼遇｜取消结尾强制推荐｜10篇匹配回测",
            "",
            "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
            "",
            "## 结论",
            "",
            "单改这一句只有部分效果：结尾的推荐动作堆叠从6/10降到3/10，安心类收尾也下降；但10/10仍然把某种推荐或分享动作放在结尾。说明真正的强制来源还在“产品体验里的推荐态度原话”和正向表达槽位，本候选不能单独解决收尾多样性。",
            "",
            "## 关键指标",
            "",
            table,
            "",
            f"- 候选机器直接通过：item {cand_direct}；改写后通过：item {cand_rewritten}。",
            "- 候选人工可用：item [1, 2, 4, 5, 6, 9, 10]；需修：[3, 7, 8]。其中item 1、2正文可用，但机器业务审核不可用。",
            "- 本次目标指标：推荐动作仍在结尾10/10；两类以上推荐动作堆叠降为3/10。",
            "- 各篇结尾动作类型："
            + "；".join(f"item {item_no}={','.join(hits) or '无'}" for item_no, hits in cand_actions.items()),
            "",
            "## 候选变化",
            "",
            "- 修改前：最后或结尾自然表达对a2的认可和推荐意愿。",
            "- 修改后：活动和使用感受里能自然看出她更认可a2、愿意向熟人推荐即可，不规定放在结尾，也不要求另起一段集中总结。",
            "- batch 809完整复用了batch 808的10份计划；活动、来源、原因、体验、品牌认可和正向词均相同，只改内容方向里的这一条。",
            "- production未修改，候选未写入资产表。",
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
            "- baseline batch_id：808",
            "- candidate batch_id：809",
            "- candidate：匹配计划draft，未写入资产表",
            f"- JSON报告：`{CANDIDATE_PATH}`",
            f"- 完整Prompt：`{PROMPT_PATH}`",
            f"- 实验manifest：`{OUTPUT_DIR / 'experiment_manifest.json'}`",
            "",
        ]
    )
    PREVIEW_PATH.write_text(preview, encoding="utf-8")
    print(json.dumps({"preview": str(PREVIEW_PATH), "prompt": str(PROMPT_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
