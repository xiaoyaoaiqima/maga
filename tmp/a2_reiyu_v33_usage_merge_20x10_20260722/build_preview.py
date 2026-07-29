"""Build the 20-item human review preview for batch 816."""
from __future__ import annotations

import json
from pathlib import Path


OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v33_usage_merge_audit_v7_20260722")
REPORT_PATH = OUTPUT_DIR / "batch816_report.json"
PROMPT_PATH = OUTPUT_DIR / "batch816_随机完整Prompt_item1.md"
PREVIEW_PATH = OUTPUT_DIR / "batch816_20篇并发10_审核预览.md"

EXPERIENCE_CATEGORIES = {
    "冲泡": ["粉质", "冲泡", "冲开", "好冲", "不结块", "挂壁"],
    "奶香口感": ["奶香", "清甜", "口感", "不甜腻", "喝光", "喝得", "喝完", "喝起来"],
    "肚肚吸收": ["肚肚", "肠胃", "吸收", "消化", "奶瓣", "绿💩", "嗯嗯", "负担"],
    "长肉状态": ["长肉", "肉嘟嘟", "麻杆", "小肉球", "轻飘飘", "胳膊都酸", "长势", "气色", "体质", "壮壮实实"],
    "转奶适应": ["转奶", "过渡", "适应"],
    "睡眠": ["睡得", "睡眠", "安稳觉"],
    "抵抗力": ["抵抗力", "感冒", "换季", "少跑🏥"],
    "配方成分": ["A2蛋白", "乳铁蛋白", "HMO", "营养全面", "配方"],
}

JUDGMENTS = {
    1: ("👀", "观察", "业务审核未返回JSON；人工复核后，抽奖、每批检测和老客体验均可用。"),
    2: ("✅", "可用", "积分活动、每批检测和奶香肚肚体验衔接自然。"),
    3: ("👀", "观察", "业务审核未返回JSON；人工复核后，老客回归礼、检测报告和长期体验可用。"),
    4: ("✅", "可用", "多重福利、每批检测和冲泡长肉体验清楚。"),
    5: ("✅", "可用", "3罐小车车档位正确，没有旧罐或已兑换暗示。"),
    6: ("✅", "可用", "6罐自行车是活动规则描述，没有再写成已经换到奖品。"),
    7: ("✅", "可用", "12罐换奶粉正确，检测严格和冲泡体验均可用。"),
    8: ("💣", "需修", "检测语境明确写“扫罐码能看到信息”；罐码用于集罐，报告应扫罐底码，已被机器hold-out。"),
    9: ("✅", "可用", "抽奖奖品、每批检测和长期使用体验完整。"),
    10: ("✅", "可用", "积分活动与每批检测承接自然，身份一致。"),
    11: ("⚠️", "轻修", "“认真在做客户关系”偏品牌汇报腔；事实正确，局部改成老客被重视的自然感受即可。"),
    12: ("✅", "可用", "活动内容、页面检测和老客体验没有机制错误。"),
    13: ("✅", "可用", "活动期补货参加集罐，没有现有旧罐暗示。"),
    14: ("✅", "可用", "未来买好几罐参加活动，6罐自行车档位正确。"),
    15: ("⚠️", "轻修", "“用心建立信任”偏品牌总结；活动和产品事实本身可用。"),
    16: ("👀", "观察", "业务审核未返回JSON；“每罐都能查”表示可查询信息，不等于每罐检测，人工放行。"),
    17: ("✅", "可用", "品质溯源、每批报告和冲泡体验归属清楚。"),
    18: ("✅", "可用", "积分活动、每批检测和长肉转奶经历无因果错误。"),
    19: ("⚠️", "轻修", "“用心做客户关系”偏品牌汇报腔；改成老客觉得被重视即可。"),
    20: ("✅", "可用", "多重福利、每批检测和冲泡体验完整。"),
}


def _load() -> dict:
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


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


def _experience_stats(report: dict) -> tuple[int, float, dict[int, list[str]]]:
    per_item: dict[int, list[str]] = {}
    for item in report.get("items") or []:
        body = str(item.get("body") or "")
        hits = [
            name
            for name, phrases in EXPERIENCE_CATEGORIES.items()
            if any(phrase in body for phrase in phrases)
        ]
        per_item[int(item["item_no"])] = hits
    coverage = sum(bool(hits) for hits in per_item.values())
    average = round(sum(len(hits) for hits in per_item.values()) / max(1, len(per_item)), 2)
    return coverage, average, per_item


def _section(item: dict) -> str:
    item_no = int(item["item_no"])
    marker, label, reason = JUDGMENTS[item_no]
    return (
        f"### {marker} item {item_no}｜{label}｜{item.get('title') or '无标题'}\n\n"
        f"判断：{reason}\n\n{item.get('body') or '无正文'}\n"
    )


def main() -> None:
    report = _load()
    summary = report.get("summary") or {}
    direct, rewritten = _machine_split(report)
    coverage, average, experience_hits = _experience_stats(report)
    items = list(report.get("items") or [])
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

    preview = "\n".join(
        [
            "# a2礼遇｜审核闭环 batch 816｜20篇并发10",
            "",
            "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
            "",
            "## 结论",
            "",
            "本批人工可用19/20：16篇无需修改，3篇轻修可用；唯一硬问题item 8已被确定性审核正确拦截。最新审核链路能明确区分扫罐码/罐底码，并能把品牌汇报腔降为light-fix。候选继续留在draft训练，不发布。",
            "",
            "## 关键指标",
            "",
            "- 发起20篇；LLM原始正文20篇；最终生成状态20篇；失败0篇。",
            "- 并发：10；总耗时约92.7秒。",
            f"- 机器直接通过：{len(direct)}/20，item {direct}。",
            f"- 改写后机器通过：{len(rewritten)}/20，item {rewritten}；机器最终hard pass：{summary.get('hard_pass_count')}/20。",
            f"- 最终禁词命中：{summary.get('forbidden_hit_count')}篇；最大2-gram相似度：{summary.get('max_pairwise_jaccard_2gram')}；相似度告警：{summary.get('similarity_warning_count')}篇。",
            "- 人工可用：19/20；无需修改item [1, 2, 3, 4, 5, 6, 7, 9, 10, 12, 13, 14, 16, 17, 18, 20]；轻修可用item [11, 15, 19]；需修item [8]。",
            "- 机器审核不可用但人工复核可用：item [1, 3, 16]。",
            "- 确定性guard：item 8=scan_code_mechanism_error；item [11, 15, 19]=corporate_summary_tone。",
            f"- 使用体验覆盖：{coverage}/20；平均体验类别：{average}。",
            "- 每篇体验类别："
            + "；".join(f"item {item_no}={','.join(hits)}" for item_no, hits in experience_hits.items()),
            "",
            "## 候选变化",
            "",
            "- 生文候选未改：仍使用合并双认可路径，原始来源、原因、活动内容、产品体验和品牌认可未压缩。",
            "- 本轮只改审核：扩大旧库存检测窗口；新增逐罐/流程扩写、跨句检测因果、扫罐码查检测、品牌大小写、虚构已兑换和品牌汇报腔guard。",
            "- corporate_summary_tone只标light-fix，不作为事实硬错；A2蛋白保持大写并放行。",
            "- production未修改；候选未写入资产表。",
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
            "- batch_id：816",
            "- generation concurrency：10",
            "- candidate：v33合并双认可路径draft，未写入资产表",
            f"- JSON报告：`{REPORT_PATH}`",
            f"- 随机完整Prompt：`{PROMPT_PATH}`",
            f"- 实验manifest：`{OUTPUT_DIR / 'experiment_manifest.json'}`",
            "",
        ]
    )
    PREVIEW_PATH.write_text(preview, encoding="utf-8")
    print(json.dumps({"preview": str(PREVIEW_PATH), "prompt": str(PROMPT_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
