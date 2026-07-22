import json
import random
import re
from pathlib import Path


OUTPUT_DIR = Path(
    "/Users/luxifa/maga/outputs/a2_reiyu_v18_concise_prompt_20260721"
)
BATCH_ID = 769
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")

MANUAL = {
    1: ("usable", "活动、抽奖、每批检测和老客体验关系成立。"),
    2: ("dropped", "标题加权29直接淘汰；正文还扩写了‘从源头到出厂严格把控’。"),
    3: ("watch", "活动事实成立，但‘不鼎力推荐真的说不过去’略显生硬。"),
    4: ("dropped", "标题加权21直接淘汰；正文还扩写了‘从源头到出厂层层把关’。"),
    5: ("usable", "老客回馈、检测和长期使用感受承接自然。"),
    6: ("dropped", "标题加权22直接淘汰，且标题写成已经‘领了小听粉’，与素材提供的活动规则不一致。"),
    7: ("dropped", "标题加权23直接淘汰。"),
    8: ("fix", "直接照抄内容方向，并自行新增‘积分翻倍、专属礼品’。"),
    9: ("fix", "出现硬禁表达‘攒罐子’，后链路直接阻断。"),
    10: ("fix", "把罐底码写成集罐登记入口，活动机制错误。"),
}

MARKER = {"usable": "✅", "watch": "⚠️", "fix": "💣", "dropped": "⛔"}
LABEL = {"usable": "可用", "watch": "重点看", "fix": "需修", "dropped": "标题超限淘汰"}


def weighted_title_length(title: str) -> int:
    total = 0
    for char in re.sub(r"\s+", "", title):
        if char in ("\u200d", "\ufe0f"):
            continue
        total += 2 if EMOJI_RE.fullmatch(char) else 1
    return total


def main() -> None:
    details_path = OUTPUT_DIR / f"batch{BATCH_ID}_details.json"
    report_path = OUTPUT_DIR / f"batch{BATCH_ID}_report.json"
    items = json.loads(details_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))["data"]
    summary = report["summary"]
    by_no = {item["item_no"]: item for item in items}

    groups = {key: [] for key in ("usable", "watch", "fix", "dropped")}
    for item_no, (status, _) in MANUAL.items():
        groups[status].append(item_no)

    rendered = [item for item in items if item.get("rendered_prompt")]
    sample = random.SystemRandom().choice(rendered)
    prompt_path = OUTPUT_DIR / f"batch{BATCH_ID}_随机完整Prompt_item{sample['item_no']}.md"
    prompt_path.write_text(
        "\n".join(
            [
                "# a2礼遇 v18 精简候选随机完整 Prompt",
                "",
                f"- batch_id: {BATCH_ID}",
                f"- item_no: {sample['item_no']}",
                f"- title: {sample['title']}",
                f"- business_rule: {sample.get('business_rule') or ''}",
                "",
                "```text",
                sample["rendered_prompt"],
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    lines = [
        "# a2礼遇 v18｜精简生成要求候选｜10篇验证",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 结论",
        "",
        "不建议转正。Prompt长度和口癖重复明显下降，但源头约束删得过多，机器最终通过从v17的7/10降到4/10，人工直接可用从7篇降到2篇。",
        "",
        "## 关键指标",
        "",
        "- 发起生成：10篇；原始生文成功：10篇；后链路保留：5篇；失败：5篇",
        f"- 机器最终通过：{summary['hard_pass_count']}/10；v17为7/10",
        f"- 后链路发生处理：{summary['rewrite_item_count']}篇；LLM content.rewrite：5次；v17为0次；最终违禁词命中：{summary['forbidden_hit_count']}",
        "- 业务复审：direct_pool 3篇，hold_out 1篇；另有标题超限4篇、硬禁词阻断1篇、业务审核未完成1篇",
        "- 平均完整Prompt：717字；v17为1465字，减少51.1%",
        f"- 最大两两2-gram相似度：{summary['max_pairwise_jaccard_2gram']}；相似度预警：{summary['similarity_warning_count']}",
        f"- 人工直接可用：{len(groups['usable'])}篇，item {groups['usable']}；v17为7篇",
        f"- 人工重点看：{len(groups['watch'])}篇，item {groups['watch']}",
        f"- 人工需修：{len(groups['fix'])}篇，item {groups['fix']}",
        f"- 标题超20直接淘汰：{len(groups['dropped'])}篇，item {groups['dropped']}",
        "",
        "## 候选变化",
        "",
        "- 原始内容方向、来源、原因、活动内容、检测和认可槽位与v17完全一致。",
        "- 固定写作层替换为用户提供的1段写作要求和6条生成边界；旧‘写法’和旧‘生成要求’清空。",
        "- 口癖下降：‘而且’9→3篇，‘反正’7→0篇，‘本来以为’4→2篇，‘好家伙’3→0篇。",
        "- 代价：出现5次模型违禁词改写，并复现内容方向照抄、攒罐子和罐底码集罐。",
        "",
        "## 重点看",
        "",
    ]

    for item_no in groups["dropped"] + groups["fix"] + groups["watch"]:
        item = by_no[item_no]
        status, reason = MANUAL[item_no]
        lines.extend(
            [
                f"### {MARKER[status]} item {item_no}｜{LABEL[status]}｜{item['title']}",
                "",
                f"问题：{reason}",
                "",
                item["body"],
                "",
            ]
        )

    lines.extend(["## 其他产出", ""])
    for item_no in groups["usable"]:
        item = by_no[item_no]
        status, reason = MANUAL[item_no]
        lines.extend(
            [
                f"### {MARKER[status]} item {item_no}｜{LABEL[status]}｜{item['title']}",
                "",
                f"判断：{reason}",
                "",
                item["body"],
                "",
            ]
        )

    lines.extend(
        [
            "## 调试信息",
            "",
            f"- batch_id: {BATCH_ID}",
            "- candidate_asset_id: 1973",
            "- candidate_asset_version: 18",
            "- candidate_status: archived / candidate",
            "- production_restored: asset 1972 / version 17",
            f"- JSON report: `{report_path}`",
            f"- details/response: `{details_path}`",
            f"- rendered prompt: `{prompt_path}`",
            "",
        ]
    )

    preview_path = OUTPUT_DIR / f"batch{BATCH_ID}_v18精简候选_10篇对比预览.md"
    preview_path.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "preview_path": str(preview_path),
                "prompt_path": str(prompt_path),
                "title_lengths": {
                    item["item_no"]: weighted_title_length(item["title"]) for item in items
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
