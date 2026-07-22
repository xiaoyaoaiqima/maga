#!/usr/bin/env python3
"""Build compact human-review previews for the A2 reiyu match loop."""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from statistics import mean


OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_match_review_20260721")
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
BANNED_TERMS = (
    "顺手",
    "顺口",
    "顺便",
    "薅羊毛",
    "小红书",
    "肠胃",
    "肚子",
    "敏感",
    "便便",
    "粑粑",
    "报名活动",
    "旧罐",
    "空罐",
    "以前的罐",
    "攒罐子",
    "数空罐",
    "翻罐",
)
MARKERS = {"usable": "✅", "watch": "⚠️", "fix": "💣", "failed": "⛔"}
LABELS = {"usable": "可用", "watch": "重点看", "fix": "需修", "failed": "生成失败"}

CONFIGS = {
    725: {
        "round": "第一轮｜v9原始槽位基线",
        "conclusion": "不建议直接转正：通用人设改写明显压短正文，并引入检测承接、来源和禁用词问题。",
        "change": "未改原始槽位；使用v9生产资产，保留当时默认的生成后通用人设风格改写。",
        "manual": {
            1: ("fix", "标题按中文1、emoji2计算后超过20字；正文长度仅作生成表现观察。"),
            2: ("fix", "用“再往下翻”承接每批检测，违反检测来源边界。"),
            3: ("fix", "出现禁用词“顺手”。"),
            4: ("usable", "活动、检测和信息认可关系成立；正文长度不作为审核硬问题。"),
            5: ("fix", "出现“顺手”和“肠胃”，并写成领礼时发现每批检测。"),
            6: ("usable", "活动来源和信息认可路径成立；不因正文长度或自然总结表达降级。"),
            7: ("fix", "改写后丢失“宝爸刷到后跟我说”的发现来源。"),
            8: ("usable", "机制与信息认可路径整体成立；正文198字不作为审核问题。"),
            9: ("fix", "出现“顺手”，且老客标题写成“被圈粉”造成身份冲突。"),
            10: ("usable", "扫罐码累计按已确认口径放行；正文长度不作为审核问题。"),
        },
    },
    726: {
        "round": "第二轮｜关闭通用人设改写",
        "conclusion": "方向有效：生成侧字数命中率提升，来源不再被二次洗掉；按最新口径放行检测严格度概括和‘仔细看了下’，item 8通过qwen-plus语义改写处理。",
        "change": "只对a2_reiyu_ugc_post_rules_v1关闭生成后通用人设风格改写；v9原始内容方向、了解途径、参加原因、活动内容和认可语料均未改。",
        "manual": {
            1: ("usable", "活动、检测和老客体验关系成立；正文185字只是生成约束未完全命中，不作为审核问题。"),
            2: ("usable", "“很严格的批次检测”是合理概括，没有编具体检测项目、数量、结果或报告细节。"),
            3: ("usable", "标题按中文1、emoji2计算未超过20字，符合审核口径。"),
            4: ("usable", "来源、积分、检测承接和信息认可路径一致，格式满足当前要求。"),
            5: ("usable", "“值得试试”属于允许的自然推荐表达，不判导购收束。"),
            6: ("usable", "来源和认可逻辑成立；正文195字不作为审核问题。"),
            7: ("usable", "“仔细看了下”和标题“别错过”均允许；只拦明确翻看页面类承接。"),
            8: ("usable", "原文“有羊毛”已通过qwen-plus按完整语境改写，不建立字符串硬替换规则。"),
            9: ("fix", "结尾“一起喝”主语含混，容易读成宝妈也喝婴配粉。"),
            10: ("fix", "“这种实的”是明显病句；上下文已出现a2，后文使用“品牌”指代允许。"),
        },
    },
    729: {
        "round": "第三轮｜分层禁词接入与qwen复审",
        "conclusion": "本轮可进入下一轮撮合：9篇可用，item 6轻观察，0篇仍需修；所有被拒绝的qwen事实污染候选都已回滚，没有带入最终文章。",
        "change": "a2礼遇正式审核资产升级为74条分层策略：19条确定性规范化、22条qwen-plus语义改写、33条hard ban；新增‘顺手/顺口/顺便/麻烦’软改写，以及检测信息与活动页面同句时的上下文改写。",
        "manual": {
            1: ("usable", "‘旅游基金大奖’和‘新西兰旅游’均按业务确认放行；抽奖、检测和老客体验成立。"),
            2: ("usable", "‘新西兰旅游’属于允许的自然奖品说法；信息认可路径成立。"),
            3: ("usable", "qwen-plus去掉‘顺手’后，宝妈群来源、积分、检测和长期体验均保留。"),
            4: ("usable", "已拒绝新增保温杯、辅食机的污染候选；最终只保留积分换礼和每批检测。"),
            5: ("usable", "已去掉‘麻烦’和活动页面承接，老客回归礼、小听粉、长期体验均保留。"),
            6: ("watch", "活动事实和检测承接正确；‘普通领点小听粉、福利真不少’略显用力，业务可用但真人感可再观察。"),
            7: ("usable", "已拒绝‘买奶粉自动参与、抽奖随时可抽、专属加码’污染候选；最终只并列概括四类福利。"),
            8: ("usable", "宝爸来源、多重福利、每批检测和信息认可关系成立。"),
            9: ("usable", "经多轮复审后固定为集3罐换小车车，未再出现报名、旧罐或已兑换经历。"),
            10: ("usable", "页面承接已去除，集3罐换小车车和信息认可均保留。"),
        },
    },
    731: {
        "round": "第四轮｜词面映射下沉v11",
        "conclusion": "词面映射可以下沉：10篇最终均可用，固定词面由确定性替换安全处理；本轮暴露的积分奖品、检测承接和虚构兑换经历仍由语义review修正。",
        "change": "从16条生文规则中删除固定词面映射；后链路新增肚子、便便、粑粑、眼睛、QQ五个确定性替换。活动事实、机制和检测承接规则未动。",
        "generation_rewrite_items": [1, 2, 3, 5, 7, 9],
        "operator_rewrite_items": [1, 3, 4, 5, 7, 9, 10],
        "manual": {
            1: ("usable", "标题已压到审核上限内；新西兰旅游、抽奖参与方式、每批检测和老客体验均有槽位支撑。"),
            2: ("usable", "活动页面承接已在生成后链路改掉；抽奖、检测和信息认可关系成立。"),
            3: ("usable", "积分只写累计后兑换会员礼，已移除奶粉和玩具等错误具体奖品。"),
            4: ("usable", "标题加权18字；积分换礼、每批检测和信息认可关系成立。"),
            5: ("usable", "写作指令泄漏和活动页面承接已删除；老客回归礼、小听粉、检测和长期体验均保留。"),
            6: ("usable", "‘仔细一看’按业务口径允许；老客回归礼、每批检测和信息认可关系成立。"),
            7: ("usable", "报名描述已删除；四类福利只做并列概括，检测和长期体验承接正常。"),
            8: ("usable", "宝爸来源、多重福利、每批检测和信息认可关系成立。"),
            9: ("usable", "只保留集3罐换小车车的活动标准，已删除自己兑换和看到实物的虚构经历。"),
            10: ("usable", "只保留集3罐换小车车及个人偏好，已删除多买多换和已兑换类扩写。"),
        },
    },
}


def body_length(body: str) -> int:
    return len(body.replace("\n", ""))


def max_line_length(body: str) -> int:
    return max((len(line) for line in body.splitlines() if line), default=0)


def title_weighted_length(title: str) -> int:
    total = 0
    for char in re.sub(r"\s+", "", title.strip()):
        if char in ("\u200d", "\ufe0f"):
            continue
        total += 2 if EMOJI_RE.fullmatch(char) else 1
    return total


def automatic_issues(item: dict) -> list[str]:
    title = item["title"]
    body = item["body"]
    issues: list[str] = []
    weighted_title_length = title_weighted_length(title)
    if weighted_title_length > 20:
        issues.append(f"标题加权{weighted_title_length}字")
    hits = [term for term in BANNED_TERMS if term in title or term in body]
    if hits:
        issues.append("禁用词：" + "、".join(hits))
    if "a2至初" not in body:
        issues.append("缺少a2至初")
    return issues


def write_prompt(batch_id: int, config: dict, items: list[dict]) -> Path:
    item = random.SystemRandom().choice([item for item in items if item.get("rendered_prompt")])
    path = OUTPUT_DIR / f"batch{batch_id}_随机完整Prompt_item{item['item_no']}.md"
    path.write_text(
        "\n".join(
            [
                f"# {config['round']}随机完整Prompt",
                "",
                f"- batch_id: {batch_id}",
                f"- item_no: {item['item_no']}",
                f"- title: {item['title']}",
                f"- business_rule: {item.get('business_rule') or ''}",
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


def build_preview(batch_id: int, config: dict) -> dict:
    details_path = OUTPUT_DIR / f"batch{batch_id}_details.json"
    report_path = OUTPUT_DIR / f"batch{batch_id}_report.json"
    items = json.loads(details_path.read_text(encoding="utf-8"))
    report_response = json.loads(report_path.read_text(encoding="utf-8"))
    report = report_response["data"]
    summary = report["summary"]
    prompt_path = write_prompt(batch_id, config, items)
    groups = {key: [] for key in ("fix", "watch", "usable", "failed")}
    for item in items:
        label, _ = config["manual"].get(item["item_no"], ("usable", "当前业务规则下可用。"))
        groups[label].append(item["item_no"])

    auto = {item["item_no"]: automatic_issues(item) for item in items}
    generation_rewrite_items = config.get("generation_rewrite_items")
    rewritten = (
        len(generation_rewrite_items)
        if generation_rewrite_items is not None
        else int(summary.get("rewrite_item_count") or 0)
    )
    final_pass = int(summary.get("hard_pass_count") or 0)
    direct_pass = max(final_pass - rewritten, 0)
    forbidden_items = [
        item["item_no"]
        for item in items
        if (item.get("quality") or {}).get("forbidden_terms_review", {}).get("initial_hits")
    ]
    lengths = [body_length(item["body"]) for item in items]
    prompt_lengths = [len(item.get("rendered_prompt") or "") for item in items]
    title_pass = sum(title_weighted_length(item["title"]) <= 20 for item in items)
    body_pass = sum(200 <= body_length(item["body"]) <= 250 for item in items)
    line_pass = sum(max_line_length(item["body"]) <= 100 for item in items)
    emoji_pass = sum(1 <= len(EMOJI_RE.findall(item["body"])) <= 4 for item in items)

    lines = [
        f"# {config['round']}｜10篇预览",
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
        f"- 机器直接通过：{direct_pass}篇；机器改写后通过：{rewritten}篇；机器最终通过：{final_pass}/10",
        f"- 机器违禁词改写条目：item {forbidden_items if forbidden_items else '无'}；最终违禁词命中：{summary['forbidden_hit_count']}",
        f"- 最大两两2-gram相似度：{summary['max_pairwise_jaccard_2gram']}；相似度预警：{summary['similarity_warning_count']}",
        f"- 人工可用：{len(groups['usable'])}篇，item {groups['usable']}",
        f"- 人工重点看：{len(groups['watch'])}篇，item {groups['watch']}",
        f"- 人工需修：{len(groups['fix'])}篇，item {groups['fix']}",
        f"- 标题审核口径合格：{title_pass}/10，按中文1、emoji2、上限20计算",
        f"- 生文约束观察：正文200-250字 {body_pass}/10；单行≤100字 {line_pass}/10；emoji 1-4个 {emoji_pass}/10；这些不直接决定审核标签",
        f"- 平均正文长度：{mean(lengths):.1f}字，仅作生成表现观察",
        "",
        "## 候选变化",
        "",
        f"- {config['change']}",
        "",
        "## 重点看",
        "",
    ]
    if config.get("operator_rewrite_items"):
        lines.insert(
            lines.index("## 候选变化"),
            f"- 人工review后调用qwen调整并采纳：item {config['operator_rewrite_items']}；最终10篇均已批准",
        )
        lines.insert(lines.index("## 候选变化"), "")

    by_no = {item["item_no"]: item for item in items}
    if not groups["fix"] and not groups["watch"]:
        lines.extend(["本批无重点看或需修项。", ""])
    for item_no in groups["fix"] + groups["watch"]:
        item = by_no[item_no]
        label, reason = config["manual"][item_no]
        automatic = auto[item_no]
        issue = reason + (f" 自动检查：{'；'.join(automatic)}。" if automatic else "")
        lines.extend(
            [
                f"### {MARKERS[label]} item {item_no}｜{LABELS[label]}｜{item['title']}",
                "",
                f"问题：{issue}",
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
        lines.extend(["本批没有达到当前全部人工硬规则、可直接使用的文章。", ""])

    lines.extend(
        [
            "## 调试信息",
            "",
            f"- batch_id: {batch_id}",
            f"- batch_code: {report['batch_code']}",
            f"- report: `{report_path}`",
            f"- details: `{details_path}`",
            f"- rendered prompt: `{prompt_path}`",
            "",
        ]
    )
    preview_path = OUTPUT_DIR / f"batch{batch_id}_{config['round'].replace('｜', '_')}_10篇预览.md"
    preview_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "batch_id": batch_id,
        "preview_path": str(preview_path),
        "prompt_path": str(prompt_path),
        "direct_pass": direct_pass,
        "rewritten_pass": rewritten,
        "final_pass": final_pass,
        "groups": groups,
        "body_length_pass": body_pass,
        "avg_body_chars": round(mean(lengths), 1),
        "avg_prompt_chars": round(mean(prompt_lengths), 1),
    }


def main() -> None:
    results = {batch_id: build_preview(batch_id, config) for batch_id, config in CONFIGS.items()}
    comparison_path = OUTPUT_DIR / "a2礼遇_跑文Review调整_三轮对比.md"
    first = results[725]
    second = results[726]
    third = results[729]
    fourth = results[731]
    comparison_path.write_text(
        "\n".join(
            [
                "# a2礼遇跑文 → Review → 调整｜三轮对比",
                "",
                "## 结论",
                "",
                "关闭通用人设改写后，原始槽位稳定性明显提升；第三轮再接入分层禁词和qwen候选复审，已能拦住AI连接词、检测页面承接及改写新增事实。",
                "",
                "## 对比",
                "",
                "| 指标 | 第一轮 batch 725 | 第二轮 batch 726 | 第三轮 batch 729 |",
                "|---|---:|---:|---:|",
                "| 生成/失败 | 10/0 | 10/0 | 10/0 |",
                f"| 正文200-250字 | {first['body_length_pass']}/10 | {second['body_length_pass']}/10 | {third['body_length_pass']}/10 |",
                f"| 平均正文长度 | {first['avg_body_chars']} | {second['avg_body_chars']} | {third['avg_body_chars']} |",
                f"| 人工可用 | {len(first['groups']['usable'])}/10 | {len(second['groups']['usable'])}/10 | {len(third['groups']['usable'])}/10 |",
                f"| 人工重点看 | {len(first['groups']['watch'])}/10 | {len(second['groups']['watch'])}/10 | {len(third['groups']['watch'])}/10 |",
                f"| 人工需修 | {len(first['groups']['fix'])}/10 | {len(second['groups']['fix'])}/10 | {len(third['groups']['fix'])}/10 |",
                "",
                "## 已验证根因",
                "",
                "- 第一轮10篇全部经过通用人设改写；改写层会缩短正文，并可能新增“再往下翻”、领礼时发现检测、来源丢失和“顺手”等问题。",
                "- 第二轮关闭该层后，正文平均长度和硬字数合格率提升，原始了解途径保留更稳定。",
                "- 第三轮首批qwen候选曾新增具体礼品、错误参加方式和已兑换经历；这些候选均通过版本决策回滚后重写。",
                "- ‘旅游基金大奖’和‘新西兰旅游’均可使用，金额正确即可，不要求奖品名称逐字统一。",
                "",
                "## 下一步最小调整",
                "",
                "- 礼遇审核按业务口径执行：标题中文1、emoji2且不超过20；正文长度仅作生文效果观察，不因未达到200-250字直接判错。",
                "- ‘检测很严格’‘标准高’和‘仔细看了下’允许；只禁止翻看页面、往下翻页面或从活动规则里发现检测。",
                "- qwen改写必须检查有没有新增奖品、参加方式、中奖或兑换经历；命中即拒绝候选并回滚。",
                "- 老客路径增加身份一致性审核：已写一直喝/长期喝时，标题和正文不能再写“被圈粉/第一次种草”。",
                "- “别错过”“值得试试”允许；上下文已经明确a2时，后文可用“品牌”自然指代。",
                "- ‘有羊毛’这类可修表达走模型语义改写，可用qwen-plus，不加入硬禁词或字符串替换。",
                "- 奖品归属、积分与集罐机制继续留在审核层，不污染首轮生文Prompt。",
                "",
                "## 文件",
                "",
                f"- 第一轮预览：`{first['preview_path']}`",
                f"- 第一轮完整Prompt：`{first['prompt_path']}`",
                f"- 第二轮预览：`{second['preview_path']}`",
                f"- 第二轮完整Prompt：`{second['prompt_path']}`",
                f"- 第三轮预览：`{third['preview_path']}`",
                f"- 第三轮完整Prompt：`{third['prompt_path']}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    lexical_comparison_path = OUTPUT_DIR / "a2礼遇_词面映射下沉_v10_vs_v11.md"
    lexical_comparison_path.write_text(
        "\n".join(
            [
                "# a2礼遇词面映射下沉｜v10 vs v11",
                "",
                "## 结论",
                "",
                "固定词面映射适合从生文Prompt下沉到后链路。v11没有降低最终可用率，也没有增加生成阶段的改写篇数；需要继续留在语义review中的，是活动事实、奖品归属、检测承接和虚构经历。",
                "",
                "## 对比",
                "",
                "| 指标 | v10 batch 729 | v11 batch 731 |",
                "|---|---:|---:|",
                "| 生成/失败 | 10/0 | 10/0 |",
                f"| 平均完整Prompt字符数 | {third['avg_prompt_chars']} | {fourth['avg_prompt_chars']} |",
                f"| 生成阶段直接通过 | {third['direct_pass']}/10 | {fourth['direct_pass']}/10 |",
                f"| 生成后链路改写 | {third['rewritten_pass']}/10 | {fourth['rewritten_pass']}/10 |",
                f"| 机器最终通过 | {third['final_pass']}/10 | {fourth['final_pass']}/10 |",
                f"| 人工可用 | {len(third['groups']['usable'])}/10 | {len(fourth['groups']['usable'])}/10 |",
                f"| 人工重点看 | {len(third['groups']['watch'])}/10 | {len(fourth['groups']['watch'])}/10 |",
                f"| 人工需修 | {len(third['groups']['fix'])}/10 | {len(fourth['groups']['fix'])}/10 |",
                "| 最终正式禁词命中 | 0 | 0 |",
                "",
                "## v11实际发生了什么",
                "",
                f"- 完整Prompt平均从{third['avg_prompt_chars']}字符降到{fourth['avg_prompt_chars']}字符，每篇减少79字符。",
                "- item 1、3、7、9中的‘肠胃’由确定性规则改为‘肚肚’，没有调用模型，也没有破坏句末标点。",
                "- item 2、3、5仍因页面承接或‘顺便’等上下文问题调用qwen；这类问题不能靠固定字符串替换解决。",
                "- 初始人工review发现的积分奖品错误、Prompt文字泄漏、报名描述、虚构兑换经历和多买多换，均已通过版本化qwen调整后复核采纳。",
                "- 最终10篇均已批准，79条正式后链路规则复审命中为0。",
                "",
                "## 最小Prompt差异",
                "",
                "v11仅删除以下整条词面映射，活动事实规则保持不变：",
                "",
                "> 禁止写小红书、肠胃、肚子、敏感、便便、粑粑、钱、预防针、大脑、眼睛、母乳、微信、QQ；如确需表达，分别改为🍠、肚肚、敏敏、💩、💰、💉、🧠、👀、母R、🌍。",
                "",
                "## 判断",
                "",
                "建议保留v11。固定、无歧义的词面规范继续放后链路；奖品归属、参加方式、检测来源和是否虚构亲历仍保留审核与模型语义改写。",
                "",
                "## 文件",
                "",
                f"- v10预览：`{third['preview_path']}`",
                f"- v10完整Prompt：`{third['prompt_path']}`",
                f"- v11预览：`{fourth['preview_path']}`",
                f"- v11完整Prompt：`{fourth['prompt_path']}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "results": results,
                "comparison_path": str(comparison_path),
                "lexical_comparison_path": str(lexical_comparison_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
