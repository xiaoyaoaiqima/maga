import json
import random
import re
from pathlib import Path
from statistics import mean


OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_slot_ab_20260721")
CONFIGS = {
    "current": {
        "label": "现有压缩槽位",
        "batch_id": 716,
        "response": OUTPUT_DIR / "current_batch_response.json",
        "details": OUTPUT_DIR / "current_batch_details.json",
        "preview": OUTPUT_DIR / "现有压缩槽位_10篇预览.md",
        "prompt_prefix": "现有压缩槽位_随机完整Prompt",
        "conclusion": "不建议直接使用：机制控制稳定，但正文偏短、模板式认可和推荐收束明显。",
        "change": "活动内容、产品体验、消费者认可使用上一版整理后的短槽位，每类通常3个选项。",
        "manual": {
            1: ("watch", "正文195字，略低于200字；其余结构和机制较稳。"),
            2: ("fix", "正文176字且未分段，内容明显低于要求长度。"),
            3: ("fix", "正文出现禁用词“顺便”，且小听粉被额外扩成出门携带场景。"),
            4: ("watch", "正文256字，略超250字；福利信息完整但偏活动介绍。"),
            5: ("fix", "正文175字，出现“顺手”，且认可收束较模板。"),
            6: ("fix", "正文158字且单行超过100字，内容明显偏短。"),
            7: ("watch", "正文192字，略短；整体自然度在本组相对较好。"),
            8: ("fix", "出现“顺便攒罐”，同时触碰禁用词和旧罐联想。"),
            9: ("fix", "正文143字且单行过长，并出现“顺手”。"),
            10: ("fix", "标题19字超过上限，虽然正文长度合格。"),
        },
    },
    "original": {
        "label": "原始语料槽位",
        "batch_id": 717,
        "response": OUTPUT_DIR / "original_batch_response.json",
        "details": OUTPUT_DIR / "original_batch_details.json",
        "preview": OUTPUT_DIR / "原始语料槽位_10篇预览.md",
        "prompt_prefix": "原始语料槽位_随机完整Prompt",
        "conclusion": "方向更有真人细节，但仍不建议直接转正：长原句让正文更鲜活，也更容易超字数、复制素材和写成强种草。",
        "change": "仅把活动内容、产品体验、消费者认可换回过滤后的原始语料；活动内容每类1-12条、产品体验10条、夸奖41条。",
        "manual": {
            1: ("fix", "正文出现禁用词“小红书”，且整段超过100字。"),
            2: ("fix", "正文309字严重超长，产品体验几乎整段照搬。"),
            3: ("fix", "标题22字、正文136字，并出现“顺手”。"),
            4: ("watch", "标题正文格式合格，细节更鲜活；但成分、功效、正向词叠得较满，偏广告。"),
            5: ("fix", "标题20字超限，产品体验和推荐收束偏强种草。"),
            6: ("fix", "标题19字、正文264字，双双超限，卖点堆叠明显。"),
            7: ("fix", "正文181字，出现“顺手”，还引入‘之前不太信’的负向转折。"),
            8: ("watch", "正文199字只差1字，生活化和产品变化更具体；结尾‘赶紧冲’偏促销。"),
            9: ("fix", "正文164字且单行过长，产品体验更像成分背书。"),
            10: ("fix", "正文195字且单行过长，虽有生活感但仍未满足格式。"),
        },
    },
}

BANNED = [
    "顺手",
    "顺口",
    "顺便",
    "小红书",
    "肠胃",
    "肚子",
    "敏感",
    "便便",
    "粑粑",
    "薅羊毛",
    "报名活动",
    "旧罐",
    "空罐",
    "以前的罐",
    "攒罐子",
    "数空罐",
    "翻罐",
]
DETAIL_TERMS = [
    "奶香",
    "清甜",
    "不甜腻",
    "不挂壁",
    "粉质",
    "结块",
    "咕咚",
    "A2蛋白",
    "乳铁蛋白",
    "HMO",
    "小肉球",
    "肉嘟嘟",
    "肚肚",
    "睡",
]
AD_TERMS = ["姐妹们冲", "赶紧冲", "必须分享", "真香", "太香", "安利", "鼎力推荐", "按头", "贼给力"]
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
MARKERS = {"usable": "✅", "watch": "⚠️", "fix": "💣", "failed": "⛔"}
LABELS = {"usable": "可用", "watch": "重点看", "fix": "需修", "failed": "生成失败"}


def body_length(body: str) -> int:
    return len(body.replace("\n", ""))


def max_line_length(body: str) -> int:
    return max((len(line) for line in body.splitlines() if line), default=0)


def automatic_issues(item: dict) -> list[str]:
    title = item["title"]
    body = item["body"]
    issues = []
    if not 7 <= len(title) <= 18:
        issues.append(f"标题{len(title)}字")
    length = body_length(body)
    if not 200 <= length <= 250:
        issues.append(f"正文{length}字")
    line_length = max_line_length(body)
    if line_length > 100:
        issues.append(f"最长单行{line_length}字")
    emoji_count = len(EMOJI_RE.findall(body))
    if not 1 <= emoji_count <= 4:
        issues.append(f"正文emoji {emoji_count}个")
    hits = [term for term in BANNED if term in title or term in body]
    if hits:
        issues.append("禁用词：" + "、".join(hits))
    if "a2至初" not in body:
        issues.append("缺少a2至初")
    return issues


def metrics(items: list[dict]) -> dict:
    auto = {item["item_no"]: automatic_issues(item) for item in items}
    return {
        "avg_body_chars": round(mean(body_length(item["body"]) for item in items), 1),
        "title_length_pass": sum(7 <= len(item["title"]) <= 18 for item in items),
        "body_length_pass": sum(200 <= body_length(item["body"]) <= 250 for item in items),
        "line_length_pass": sum(max_line_length(item["body"]) <= 100 for item in items),
        "emoji_pass": sum(1 <= len(EMOJI_RE.findall(item["body"])) <= 4 for item in items),
        "banned_item_nos": [item["item_no"] for item in items if any(term in item["title"] or term in item["body"] for term in BANNED)],
        "detail_term_avg": round(mean(sum(term in item["body"] for term in DETAIL_TERMS) for item in items), 2),
        "ad_tone_item_nos": [item["item_no"] for item in items if any(term in item["title"] or term in item["body"] for term in AD_TERMS)],
        "auto_issues": auto,
    }


def write_prompt(config: dict, details: list[dict]) -> Path:
    item = random.SystemRandom().choice(details)
    path = OUTPUT_DIR / f"{config['prompt_prefix']}_item{item['item_no']}.md"
    path.write_text(
        "\n".join(
            [
                f"# {config['label']}随机完整Prompt",
                "",
                f"- batch_id: {config['batch_id']}",
                f"- item_no: {item['item_no']}",
                f"- title: {item['title']}",
                f"- business_rule: {item['business_rule']}",
                "",
                "```text",
                item["rendered_prompt"],
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def write_preview(name: str, config: dict, response: dict, details: list[dict], prompt_path: Path) -> dict:
    report = response["data"]["report"]
    summary = report["summary"]
    manual = config["manual"]
    result_metrics = metrics(details)
    groups = {key: [] for key in ("fix", "watch", "usable", "failed")}
    for item in details:
        label, reason = manual.get(item["item_no"], ("usable", "当前人工规则下可直接使用。"))
        groups[label].append(item["item_no"])

    machine_direct = list(range(1, 11))
    machine_rewritten = []
    if name == "original":
        machine_direct = [1, 2, 3, 5, 6, 7, 8, 9, 10]
        machine_rewritten = [4]

    lines = [
        f"# {config['label']}｜10篇预览",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 结论",
        "",
        config["conclusion"],
        "",
        "## 关键指标",
        "",
        f"- 生成：{summary['generated_count']}/10；失败：{summary['failed_count']}",
        f"- 机器直接通过：{len(machine_direct)}篇，item {machine_direct}",
        f"- 机器改写后通过：{len(machine_rewritten)}篇" + (f"，item {machine_rewritten}" if machine_rewritten else ""),
        f"- 机器最终通过：{summary['hard_pass_count']}/10；机器违禁词命中：{summary['forbidden_hit_count']}",
        f"- 最大两两2-gram相似度：{summary['max_pairwise_jaccard_2gram']}；相似度预警：{summary['similarity_warning_count']}",
        f"- 人工可用：{len(groups['usable'])}篇，item {groups['usable']}",
        f"- 人工重点看：{len(groups['watch'])}篇，item {groups['watch']}",
        f"- 人工需修：{len(groups['fix'])}篇，item {groups['fix']}",
        f"- 标题字数合格：{result_metrics['title_length_pass']}/10；正文字数合格：{result_metrics['body_length_pass']}/10；单行长度合格：{result_metrics['line_length_pass']}/10",
        f"- 正文emoji合格：{result_metrics['emoji_pass']}/10；人工扫描禁用词条目：{result_metrics['banned_item_nos']}",
        f"- 平均正文长度：{result_metrics['avg_body_chars']}字；平均产品细节词：{result_metrics['detail_term_avg']}个/篇",
        "",
        "## 候选变化",
        "",
        f"- {config['change']}",
        "",
        "## 重点看",
        "",
    ]

    ordered = groups["fix"] + groups["watch"]
    by_no = {item["item_no"]: item for item in details}
    for item_no in ordered:
        item = by_no[item_no]
        label, reason = manual[item_no]
        auto = result_metrics["auto_issues"][item_no]
        issue_line = reason + (f" 自动检查：{'；'.join(auto)}。" if auto else "")
        lines.extend(
            [
                f"### {MARKERS[label]} item {item_no}｜{LABELS[label]}｜{item['title']}",
                "",
                f"问题：{issue_line}",
                "",
                item["body"],
                "",
            ]
        )

    lines.extend(["## 其他产出", ""])
    for item_no in groups["usable"]:
        item = by_no[item_no]
        lines.extend(
            [
                f"### ✅ item {item_no}｜可用｜{item['title']}",
                "",
                item["body"],
                "",
            ]
        )
    if not groups["usable"]:
        lines.extend(["本批没有达到当前全部人工硬规则、可直接交付的文章。", ""])

    lines.extend(
        [
            "## 调试信息",
            "",
            f"- batch_id: {config['batch_id']}",
            f"- batch_code: {report['batch_code']}",
            f"- response: `{config['response']}`",
            f"- details: `{config['details']}`",
            f"- rendered prompt: `{prompt_path}`",
            "",
        ]
    )
    config["preview"].write_text("\n".join(lines), encoding="utf-8")
    return {
        "groups": groups,
        "metrics": result_metrics,
        "machine": {
            "direct": machine_direct,
            "rewritten": machine_rewritten,
            "final_pass": summary["hard_pass_count"],
            "similarity": summary["max_pairwise_jaccard_2gram"],
        },
        "prompt_path": prompt_path,
    }


results = {}
for name, config in CONFIGS.items():
    response = json.loads(config["response"].read_text(encoding="utf-8"))
    details = json.loads(config["details"].read_text(encoding="utf-8"))
    prompt_path = write_prompt(config, details)
    results[name] = write_preview(name, config, response, details, prompt_path)

comparison = OUTPUT_DIR / "a2礼遇槽位语料_A_B对比结论.md"
current = results["current"]
original = results["original"]
comparison.write_text(
    "\n".join(
        [
            "# a2礼遇槽位语料 A/B 对比",
            "",
            "## 结论",
            "",
            "原始语料组的方向更好，但不能把长原句无处理地直接作为高权重槽位。它明显增加了生活细节、产品体感和情绪起伏，同时也带来超字数、素材照搬、强安利和卖点堆叠。现有压缩组更稳，却太容易生成短、平、像统一模板的文章。",
            "",
            "建议下一版采用混合方案：活动内容恢复过滤后的原始说法；产品体验保留原始细节但拆短；夸奖按“推荐/深度认可/安心”分池；删除或降频独立正向词槽，避免同一篇重复夸三遍。",
            "",
            "| 指标 | 现有压缩槽位 | 原始语料槽位 |",
            "|---|---:|---:|",
            f"| 生成成功 | 10 | 10 |",
            f"| 机器直接通过 | {len(current['machine']['direct'])} | {len(original['machine']['direct'])} |",
            f"| 机器最终通过 | {current['machine']['final_pass']} | {original['machine']['final_pass']} |",
            f"| 人工可用 | {len(current['groups']['usable'])} | {len(original['groups']['usable'])} |",
            f"| 人工重点看 | {len(current['groups']['watch'])} | {len(original['groups']['watch'])} |",
            f"| 人工需修 | {len(current['groups']['fix'])} | {len(original['groups']['fix'])} |",
            f"| 平均正文长度 | {current['metrics']['avg_body_chars']} | {original['metrics']['avg_body_chars']} |",
            f"| 正文200-250字 | {current['metrics']['body_length_pass']}/10 | {original['metrics']['body_length_pass']}/10 |",
            f"| 标题7-18字 | {current['metrics']['title_length_pass']}/10 | {original['metrics']['title_length_pass']}/10 |",
            f"| 禁用词条目 | {len(current['metrics']['banned_item_nos'])} | {len(original['metrics']['banned_item_nos'])} |",
            f"| 平均产品细节词 | {current['metrics']['detail_term_avg']} | {original['metrics']['detail_term_avg']} |",
            f"| 最大2-gram相似度 | {current['machine']['similarity']} | {original['machine']['similarity']} |",
            "",
            "## 为什么原始组读起来更好",
            "",
            "- 会写出淡淡奶香、咕咚喝光、小麻杆变小肉球等具体画面，不再只剩“粉质细腻、品质在线”。",
            "- 活动内容保留了“错过几个亿”“平摊下来省不少”等真实情绪，转折更像普通用户。",
            "- 两两相似度略低，正文平均更长，信息和情绪更饱满。",
            "",
            "## 为什么仍不能直接全量换回",
            "",
            "- 长产品体验后面又叠加消费者夸奖和正向词，导致同一篇连续夸三次。",
            "- 原始句里的“小红书、顺手、肠胃”等会与当前禁用规则打架，模型或后处理不一定都能拦住。",
            "- 10篇里只有3篇正文满足200-250字，长素材并没有自动解决格式稳定性。",
            "- 强推荐原句会把纯分享推向“姐妹们冲、按头安利、赶紧冲”的导购感。",
            "",
            "## 文件",
            "",
            f"- [现有压缩槽位10篇预览]({CONFIGS['current']['preview']})",
            f"- [原始语料槽位10篇预览]({CONFIGS['original']['preview']})",
            f"- [现有压缩槽位随机完整Prompt]({current['prompt_path']})",
            f"- [原始语料槽位随机完整Prompt]({original['prompt_path']})",
            f"- [原始语料槽位对照CSV]({OUTPUT_DIR / 'a2礼遇UGC分享贴_原始语料槽位对照.csv'})",
            "",
        ]
    ),
    encoding="utf-8",
)

print(json.dumps({"comparison": str(comparison), "results": results}, ensure_ascii=False, indent=2, default=str))
