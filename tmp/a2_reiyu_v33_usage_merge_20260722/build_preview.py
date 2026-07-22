"""Build the compact human-review preview for batch 808."""
from __future__ import annotations

import json
from pathlib import Path


OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v33_usage_merge_20260722")
BASELINE_BATCH_ID = 807
CANDIDATE_BATCH_ID = 808

EXPERIENCE_CATEGORIES = {
    "冲泡": ["粉质", "冲泡", "冲开", "好冲", "不结块", "挂壁"],
    "奶香口感": ["奶香", "清甜", "口感", "不甜腻", "喝光", "喝得", "喝起来"],
    "肚肚吸收": ["肚肚", "肠胃", "吸收", "消化", "奶瓣", "绿💩", "嗯嗯", "负担"],
    "长肉状态": ["长肉", "肉嘟嘟", "麻杆", "小肉球", "轻飘飘", "胳膊都酸", "长势", "气色", "体质"],
    "转奶适应": ["转奶", "过渡", "适应"],
    "睡眠": ["睡得", "睡眠", "安稳觉"],
    "抵抗力": ["抵抗力", "感冒", "换季", "少跑🏥"],
    "配方成分": ["A2蛋白", "乳铁蛋白", "HMO", "营养全面", "配方"],
}

CANDIDATE_JUDGMENTS = {
    1: ("✅", "可用", "活动、检测、具体使用体验和老客认可衔接完整。"),
    2: ("✅", "可用", "积分活动后接冲泡和长肉体验，信息比v32同路径完整。"),
    3: ("💣", "需修", "正文仍命中硬禁词“薅”，自动改写失败；“A2蛋白贴肚肚”也略生硬。"),
    4: ("✅", "可用", "活动和长肉体验承接自然，没有把两类认可写成两段品牌总结。"),
    5: ("✅", "可用", "3罐小车车、每批检测和冲泡体验归属清楚。"),
    6: ("⚠️", "重点看", "正文事实可用；机器业务审核因返回非JSON不可用，不是正文事实错误。收尾略满。"),
    7: ("✅", "可用", "12罐换奶粉与长期使用反馈都有，未出现老罐或空罐暗示。"),
    8: ("👀", "观察", "事实可用，但结尾连续出现闭眼入、推荐、回购、逢人推荐，推荐密度偏高。"),
    9: ("✅", "可用", "抽奖、检测和老客体验完整；正向词又补了转奶体验，略丰富但仍能读通。"),
    10: ("✅", "可用", "积分、检测、奶香口感和肚肚体验衔接自然。"),
}


def _load(batch_id: int, label: str) -> dict:
    return json.loads((OUTPUT_DIR / f"batch{batch_id}_{label}_report.json").read_text(encoding="utf-8"))


def _experience_stats(report: dict) -> tuple[int, float, dict[int, list[str]]]:
    per_item: dict[int, list[str]] = {}
    for item in report.get("items") or []:
        body = str(item.get("body") or "")
        hits = [
            name
            for name, words in EXPERIENCE_CATEGORIES.items()
            if any(word in body for word in words)
        ]
        per_item[int(item["item_no"])] = hits
    values = list(per_item.values())
    coverage = sum(bool(value) for value in values)
    average = round(sum(len(value) for value in values) / max(1, len(values)), 2)
    return coverage, average, per_item


def _machine_pass_split(report: dict) -> tuple[list[int], list[int]]:
    direct: list[int] = []
    rewritten: list[int] = []
    for item in report.get("items") or []:
        if item.get("hard_pass") is not True:
            continue
        review = ((item.get("quality") or {}).get("review_report") or {})
        initial_hits = ((review.get("forbidden_terms_review") or {}).get("initial_hits") or [])
        (rewritten if initial_hits else direct).append(int(item["item_no"]))
    return direct, rewritten


def _item_section(item: dict) -> str:
    item_no = int(item["item_no"])
    marker, label, reason = CANDIDATE_JUDGMENTS[item_no]
    return (
        f"### {marker} item {item_no}｜{label}｜{item.get('title') or '无标题'}\n\n"
        f"判断：{reason}\n\n{item.get('body') or '无正文'}\n"
    )


def main() -> None:
    baseline = _load(BASELINE_BATCH_ID, "baseline")
    candidate = _load(CANDIDATE_BATCH_ID, "candidate")
    base_summary = baseline.get("summary") or {}
    candidate_summary = candidate.get("summary") or {}
    base_coverage, base_average, _ = _experience_stats(baseline)
    candidate_coverage, candidate_average, candidate_hits = _experience_stats(candidate)
    base_direct, base_rewritten = _machine_pass_split(baseline)
    candidate_direct, candidate_rewritten = _machine_pass_split(candidate)

    candidate_items = list(candidate.get("items") or [])
    priority = [
        _item_section(item)
        for item in candidate_items
        if CANDIDATE_JUDGMENTS[int(item["item_no"])][0] in {"💣", "⚠️"}
    ]
    others = [
        _item_section(item)
        for item in candidate_items
        if CANDIDATE_JUDGMENTS[int(item["item_no"])][0] not in {"💣", "⚠️"}
    ]

    prompt_path = OUTPUT_DIR / "batch808_candidate_prompt_item6.md"
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt.startswith("# batch 808"):
        item6 = next(item for item in candidate_items if int(item["item_no"]) == 6)
        prompt_path.write_text(
            f"# batch 808｜item 6｜{item6.get('title') or ''}\n\n{prompt}\n",
            encoding="utf-8",
        )

    comparison_rows = [
        ("LLM原始正文", "10/10", "10/10"),
        ("最终生成状态", f"{base_summary.get('generated_count')}/10", f"{candidate_summary.get('generated_count')}/10"),
        ("机器直接通过", f"{len(base_direct)}/10", f"{len(candidate_direct)}/10"),
        ("改写后机器通过", f"{len(base_rewritten)}/10", f"{len(candidate_rewritten)}/10"),
        ("机器最终hard pass", f"{base_summary.get('hard_pass_count')}/10", f"{candidate_summary.get('hard_pass_count')}/10"),
        ("人工业务可用", "7/10", "9/10"),
        ("含至少一类使用体验", f"{base_coverage}/10", f"{candidate_coverage}/10"),
        ("平均体验类别", str(base_average), str(candidate_average)),
        ("最大2-gram相似度", str(base_summary.get("max_pairwise_jaccard_2gram")), str(candidate_summary.get("max_pairwise_jaccard_2gram"))),
        (
            "安心类收尾占比",
            str((base_summary.get("closure_cluster_stats") or {}).get("clusters", [{}])[0].get("ratio")),
            str((candidate_summary.get("closure_cluster_stats") or {}).get("clusters", [{}])[0].get("ratio")),
        ),
    ]
    comparison_table = "\n".join(
        ["| 指标 | v32基线 | 合并候选 |", "|---|---:|---:|"]
        + [f"| {name} | {base} | {cand} |" for name, base, cand in comparison_rows]
    )

    preview = "\n".join(
        [
            "# a2礼遇｜合并双认可路径｜10篇对比回测",
            "",
            "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
            "",
            "## 结论",
            "",
            "方向有效，但先保留为🧪候选，不发布。使用体验覆盖从6/10升到10/10，人工可用从7/10升到9/10；事实错误没有增加。代价是安心/推荐类收尾更密，且仍有1篇因“薅”被后链路正确拦截。",
            "",
            "## 关键指标",
            "",
            comparison_table,
            "",
            f"- 候选机器直接通过：item {candidate_direct}；改写后通过：item {candidate_rewritten}。",
            "- 候选人工可用：item [1, 2, 4, 5, 6, 7, 8, 9, 10]；重点看：[6]；观察：[8]；需修：[3]。",
            "- 候选审核不可用：item [6]，原因是审核模型没有返回JSON；正文事实本身可用。",
            "- 候选违禁词改写失败：item [3]，最终仍命中“薅”。",
            "- 候选每篇体验类别："
            + "；".join(f"item {item_no}={','.join(hits)}" for item_no, hits in candidate_hits.items()),
            "",
            "## 候选变化",
            "",
            "- 修改前：同一活动拆成“老客使用感受”和“老客了解信息后更认可”两条，后者没有产品体验槽位。",
            "- 修改后：同一活动合并为一条；每篇同时抽一条原始产品使用体验和一条活动/检测后的品牌认可。",
            "- 原始来源、参加原因、活动内容、产品体验和品牌认可选项全部原样复制；静态校验8组均通过，没有压缩或改写原始槽位。",
            "- production v32未修改；候选只在本次batch计划中使用。",
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
            "- baseline batch_id：807",
            "- candidate batch_id：808",
            "- production asset：1994 / v32 / active production",
            "- candidate：内存draft，8条合并规则，未写入资产表",
            "- model：deepseek-v4-flash，temperature 0.8，max_tokens 2048；路由配置由系统表读取",
            f"- 候选定义：`{OUTPUT_DIR / 'candidate_v33_usage_merge.json'}`",
            f"- 基线JSON：`{OUTPUT_DIR / 'batch807_baseline_report.json'}`",
            f"- 候选JSON：`{OUTPUT_DIR / 'batch808_candidate_report.json'}`",
            f"- 候选完整Prompt：`{prompt_path}`",
            "",
        ]
    )
    preview_path = OUTPUT_DIR / "batch808_v33合并认可路径_10篇对比预览.md"
    preview_path.write_text(preview, encoding="utf-8")
    print(json.dumps({"preview": str(preview_path), "prompt": str(prompt_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
