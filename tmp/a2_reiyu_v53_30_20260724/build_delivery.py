from __future__ import annotations

import json
import random
import urllib.request
from pathlib import Path


BATCH_ID = 843
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v53_30_20260724")
REPORT_URL = f"http://127.0.0.1:5100/api/v1/content-agent/batches/{BATCH_ID}/report?full=true"

JUDGMENTS = {
    1: ("✅", "可用", "抽奖、每批检测、未来补货和老客体验衔接成立。"),
    2: ("✅", "可用", "抽奖奖品与每批检测表达清楚，没有虚构中奖。"),
    3: ("✅", "可用", "活动、检测和使用感受顺序成立。"),
    4: ("💣", "需修", "源活动内容只有“升级更用心”，正文自行补出“积分能换的东西变多、专属小玩意可以抽”，缺少素材承接。"),
    5: ("✅", "可用", "老客回归礼可以领取，小听粉表达在已确认放行边界内。"),
    6: ("✅", "可用", "短暂换过其他品牌后回到a2至初，经历可以成立。"),
    7: ("✅", "可用", "集罐表述没有把历史库存写成本次资格。"),
    8: ("✅", "可用", "多重福利来自本篇素材，未新增具体机制或奖品。"),
    9: ("✅", "可用", "3罐换小车车，活动和检测归属正确。"),
    10: ("✅", "可用", "活动期间补货参加，属于允许的未来购买。"),
    11: ("✅", "可用", "6罐换自行车，未出现旧罐参与。"),
    12: ("✅", "可用", "6罐换自行车与每批检测表达正确。"),
    13: ("💣", "轻修", "命中“薅”，替换为自然的福利表达后可用；本篇业务LLM审核同时未返回合法JSON。"),
    14: ("✅", "可用", "活动期间购买与历史饮用经历分开，没有旧罐资格暗示。"),
    15: ("💣", "轻修", "命中“朋友圈”，替换为pyq或puq后可用。"),
    16: ("✅", "可用", "18罐换婴儿车，没有虚构已经兑换。"),
    17: ("✅", "可用", "抽奖、检测和长期使用感均在当前放行边界内。"),
    18: ("💣", "轻修", "命中“眼睛”，按替换词处理后可用；奖品名称的自然变体不判错。"),
    19: ("✅", "可用", "业务LLM审核不可用，但人工复核积分、检测和使用经历均成立。"),
    20: ("✅", "可用", "“每次下单累计积分”由本篇活动素材直接提供，不属于模型扩写。"),
    21: ("✅", "可用", "老客回归礼和使用体验完整，没有虚构抽奖中奖。"),
    22: ("✅", "可用", "短暂转过其他品牌后继续喝a2至初，来源素材本身逻辑完整。"),
    23: ("✅", "可用", "活动期间购买参与集罐，没有连接家庭旧库存。"),
    24: ("💣", "轻修", "命中“朋友圈”，替换为pyq或puq后可用。"),
    25: ("✅", "可用", "业务LLM审核不可用，但人工复核3罐换小车车、检测和产品体验均成立。"),
    26: ("✅", "可用", "3罐换小车车与检测信息准确。"),
    27: ("✅", "可用", "6罐换自行车，没有把老客身份写成集罐进度。"),
    28: ("✅", "可用", "活动期间补货和自然说“攒一攒”均在已确认放行尺度内。"),
    29: ("💣", "需修", "“一箱差不多就够”自行建立一箱约等于12罐的数量关系，素材没有承接，不能直接使用。"),
    30: ("💣", "轻修", "命中“朋友圈、钱”，按替换词或自然改写处理后可用。"),
}


def item_section(item: dict) -> str:
    marker, label, reason = JUDGMENTS[int(item["item_no"])]
    return (
        f"### {marker} item {item['item_no']}｜{label}｜{item.get('title') or '无标题'}\n\n"
        f"判断：{reason}\n\n{item.get('body') or '无正文'}\n"
    )


def main() -> None:
    with urllib.request.urlopen(REPORT_URL) as response:
        payload = json.load(response)
    report = payload["data"]
    items = report["items"]
    summary = report["summary"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / f"batch{BATCH_ID}_full_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    sample = random.Random(20260724).choice(
        [
            item
            for item in items
            if item.get("hard_pass")
            and JUDGMENTS[int(item["item_no"])][0] == "✅"
        ]
    )
    prompt_path = OUTPUT_DIR / f"batch{BATCH_ID}_随机完整Prompt_item{sample['item_no']}.md"
    prompt_path.write_text(
        "\n".join(
            [
                f"# batch {BATCH_ID}｜item {sample['item_no']}｜{sample.get('title') or ''}",
                "",
                str((sample.get("generation_snapshot") or {}).get("rendered_prompt") or "").strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )

    usable = [number for number, value in JUDGMENTS.items() if value[0] == "✅"]
    light_fix = [number for number, value in JUDGMENTS.items() if value[1] == "轻修"]
    needs_fix = [number for number, value in JUDGMENTS.items() if value[1] == "需修"]
    priority = [
        item_section(item)
        for item in items
        if JUDGMENTS[int(item["item_no"])][0] in {"💣", "⚠️"}
    ]
    others = [
        item_section(item)
        for item in items
        if JUDGMENTS[int(item["item_no"])][0] not in {"💣", "⚠️"}
    ]

    preview_path = OUTPUT_DIR / f"batch{BATCH_ID}_A2礼遇30篇生成审核预览.md"
    preview_path.write_text(
        "\n".join(
            [
                "# a2礼遇｜v53 production 30篇生成审核预览",
                "",
                "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
                "",
                "## 结论",
                "",
                "v53已进入production，本批整体可用率较高。忽略正向词堆叠后，人工确认23篇可直接用、5篇只需替换词轻修、2篇存在内容事实扩写，暂不能直接用。",
                "",
                "## 关键指标",
                "",
                f"- 发起：30篇；原始生成：{summary['generated_count']}/30；生成失败：{summary['failed_count']}。",
                f"- 机器直接通过：{summary['hard_pass_count']}/30；本批未执行自动改写，改写后新增通过：0；机器最终通过：{summary['hard_pass_count']}/30。",
                f"- 机器需改写：{summary['remaining_rewrite_required_count']}篇；禁词命中：{summary['forbidden_hit_count']}次。",
                f"- 最大2-gram相似度：{summary['max_pairwise_jaccard_2gram']}；相似度告警：{summary['similarity_warning_count']}。",
                f"- 人工直接可用：{usable}；替换词轻修：{light_fix}；明确内容问题：{needs_fix}。",
                "- 业务LLM审核不可用：item [4, 13, 19, 25]；其中19、25已人工确认可用，13另有替换词轻修，4存在真实内容问题。",
                "- 本轮按要求不把正向词堆叠计入人工问题。",
                "",
                "## 候选变化",
                "",
                "- production asset：2021 / v53，由candidate 2020 / v52发布。",
                "- 16条规则均增加：正向词只作备选，挑最贴合上下文的自然带入，不在同一句或相邻句连续罗列。",
                "- 正向词槽位标签改为：活动分享正向表达备选词池（只挑最贴合上下文的自然带入）。",
                "- 原始正向词语料未压缩、未改写。",
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
                "- production asset：2021 / v53",
                f"- JSON报告：`{report_path}`",
                f"- 随机完整Prompt：`{prompt_path}`",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "batch_id": BATCH_ID,
                "preview_path": str(preview_path),
                "prompt_path": str(prompt_path),
                "report_path": str(report_path),
                "machine_direct_pass": summary["hard_pass_count"],
                "post_rewrite_pass": 0,
                "machine_final_pass": summary["hard_pass_count"],
                "human_direct_usable": len(usable),
                "human_light_fix": len(light_fix),
                "human_content_needs_fix": len(needs_fix),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
