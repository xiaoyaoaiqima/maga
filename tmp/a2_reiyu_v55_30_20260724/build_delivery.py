from __future__ import annotations

import json
import random
import urllib.request
from pathlib import Path


BATCH_ID = 844
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v55_30_20260724")
REPORT_URL = f"http://127.0.0.1:5100/api/v1/content-agent/batches/{BATCH_ID}/report?full=true"
START_RESPONSE = Path("/tmp/a2_v55_30_start.json")

JUDGMENTS = {
    1: ("✅", "可用", "业务LLM审核不可用；人工复核抽奖、检测和老客体验均成立。"),
    2: ("💣", "轻修", "命中“朋友圈”，替换为pyq或puq后可用。"),
    3: ("💣", "需修", "积分礼品自行补成辅食碗、绘本，素材无承接；同时存在从出生一直喝与转奶经历冲突。"),
    4: ("✅", "可用", "积分、未来补货和每批检测表达成立。"),
    5: ("✅", "可用", "业务LLM审核不可用；人工复核老客回归礼、罐底码检测和使用体验均成立。"),
    6: ("💣", "轻修", "命中“免费”，替换为🆓后可用。"),
    7: ("✅", "可用", "多重福利未新增具体奖品，检测和使用体验成立。"),
    8: ("💣", "需修", "素材只说多重福利叠加，正文自行补出“积分翻倍、专属赠品”，属于活动机制和福利扩写，机器漏审。"),
    9: ("✅", "可用", "活动后购买好几罐，3罐换小车车，没有旧罐参与。"),
    10: ("✅", "可用", "3罐换小车车和每批检测归属清楚。"),
    11: ("💣", "轻修", "命中“顺手”；“闭眼入不踩雷”是正向语境，不作为问题。"),
    12: ("✅", "可用", "6罐换自行车，未出现旧罐或虚构兑换到手。"),
    13: ("✅", "可用", "12罐换1罐，老客经历和活动资格没有混用。"),
    14: ("💣", "轻修", "命中“钱”，替换为💰或自然改成划算后可用。"),
    15: ("✅", "可用", "18罐换婴儿车，没有虚构已兑换。"),
    16: ("✅", "可用", "18罐换婴儿车和检测承接成立。"),
    17: ("💣", "轻修", "命中“朋友圈”，替换为pyq或puq后可用。"),
    18: ("✅", "可用", "业务LLM审核不可用；奖品与2w表达来自本篇素材，人工复核可用。"),
    19: ("✅", "可用", "会员积分与购买累计关系未写成集罐换积分，当前边界内可用。"),
    20: ("💣", "需修", "积分礼品自行补成“玩具到奶粉”，素材未提供且奶粉属于集罐奖品；金标已判hard/hold_out。"),
    21: ("✅", "可用", "老客回归礼、检测与使用体验成立。"),
    22: ("💣", "轻修", "命中“免费”，替换为🆓后可用。"),
    23: ("✅", "可用", "多重福利概括未新增具体机制，检测和老客体验成立。"),
    24: ("✅", "可用", "抽奖和回馈礼概括在活动素材范围内。"),
    25: ("✅", "可用", "3罐换小车车和罐底码检测表达成立。"),
    26: ("✅", "可用", "未来补货，3罐换小车车，没有旧罐暗示。"),
    27: ("✅", "可用", "自然说攒罐子不等于旧罐参与，6罐换自行车事实正确。"),
    28: ("✅", "可用", "集罐换自行车和未来补货表达成立。"),
    29: ("✅", "可用", "12罐换1罐，没有再出现一箱等于12罐的错误换算。"),
    30: ("✅", "可用", "12罐兑换产品与检测信息成立，没有数量换算错误。"),
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

    response_path = OUTPUT_DIR / f"batch{BATCH_ID}_generation_response.json"
    if START_RESPONSE.exists():
        response_path.write_text(START_RESPONSE.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        response_path.write_text(
            json.dumps(
                {
                    "batch_id": BATCH_ID,
                    "requested_count": 30,
                    "generated_count": summary["generated_count"],
                    "failed_count": summary["failed_count"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

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
                "# a2礼遇｜v55 production 30篇生成审核预览",
                "",
                "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
                "",
                "## 结论",
                "",
                "v55本批生成30/30。忽略正向词堆叠后，人工确认21篇可直接用、6篇只需替换词轻修、3篇存在活动奖品扩写或经历冲突。",
                "",
                "## 关键指标",
                "",
                f"- 发起：30篇；原始生成：{summary['generated_count']}/30；生成失败：{summary['failed_count']}。",
                f"- 机器直接通过：{summary['hard_pass_count']}/30；本批未执行自动改写，改写后新增通过：0；机器最终通过：{summary['hard_pass_count']}/30。",
                f"- 机器需改写：{summary['remaining_rewrite_required_count']}篇；禁词命中：{summary['forbidden_hit_count']}次。",
                f"- 最大2-gram相似度：{summary['max_pairwise_jaccard_2gram']}；相似度告警：{summary['similarity_warning_count']}。",
                f"- 人工直接可用：{usable}；替换词轻修：{light_fix}；明确内容问题：{needs_fix}。",
                "- 业务LLM审核不可用：item [1, 5, 11, 18]；其中1、5、18人工确认可用，11另有替换词轻修。",
                "- 金标明确拦截：item [3, 20]；人工新增漏审：item [8]。",
                "- 本轮按要求不把正向词堆叠计入人工问题。",
                "",
                "## 候选变化",
                "",
                "- production asset：2023 / v55。",
                "- 删除activity_content：这次升级会员体系确实比以前用心了，共2处。",
                "- 新增确定性硬拦截：12罐兑换与“一箱差不多就够/刚好12罐”等数量等价关系同时出现时，判activity_quantity_error。",
                "- 修复审核最终状态：金标pass=false或hold_out时不能再计入hard_pass。",
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
                "- production asset：2023 / v55",
                f"- JSON报告：`{report_path}`",
                f"- 生成响应：`{response_path}`",
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
                "response_path": str(response_path),
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
