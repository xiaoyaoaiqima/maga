#!/usr/bin/env python3
"""Generate A2 comments from the compact direct-prompt rule bank."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SCRIPT_DIR = REPO_ROOT / ".local/archive/content-generation-scripts/20260704_ugc_ppl_script_cleanup/scripts"


DEFAULT_RULE_BANK = Path(
    "outputs/a2_sentiment_comments_20260705/a2_direct_prompt_rule_bank_active_no_nestle_20260705.csv"
)

FORBIDDEN = [
    "缺货",
    "断货",
    "没货",
    "断粮",
    "断档",
    "焦虑",
    "恐慌",
    "小程序",
    "微信",
    "召回",
    "FDA",
    "热线",
    "呕吐毒素",
    "医疗护理",
    "美版",
    "毒奶",
    "假货",
    "保证没问题",
    "绝对安全",
    "无风险",
    # 业务新要求：暂不露出蜡样/蜡毒检测数值和检测报告/检测项目的明确数量。
    "0.03",
    "60+",
    "60多项",
]

AUDIT_ONLY_FORBIDDEN = [
    "没找到",
    "找不到",
    "难买",
    "心焦",
    "心急",
]

A2_DIRECT_COMPETITOR_BRAND_TERMS = (
    "超启能恩",
    "皇家美素",
    "美赞臣",
    "星飞帆",
    "爱他美",
    "君乐宝",
    "贝因美",
    "合生元",
    "诺优能",
    "达能",
    "雀巢",
    "美素",
    "皇美",
    "飞鹤",
    "惠氏",
    "启赋",
    "雅培",
)


def load_model_helpers():
    sys.path.insert(0, str(ARCHIVE_SCRIPT_DIR))
    from run_a2_month_center_direction_batch import call_model, load_dotenv

    return call_model, load_dotenv


def parse_target(raw: str) -> tuple[str, int]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("target must be NAME=COUNT")
    name, count = raw.split("=", 1)
    try:
        return name.strip(), int(count)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("target count must be integer") from exc


def load_rules(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def parse_comments(raw: str) -> list[str]:
    value = raw.strip()
    value = re.sub(r"^```(?:json|text)?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*```$", "", value).strip()
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            comments: list[str] = []
            for item in parsed:
                if isinstance(item, str):
                    text = item.strip()
                elif isinstance(item, dict):
                    text = ""
                    for key in ["content", "内容", "comment", "评论", "回复", "text"]:
                        if isinstance(item.get(key), str):
                            text = item[key].strip()
                            break
                    if not text:
                        text = next((str(v).strip() for v in item.values() if isinstance(v, str) and v.strip()), "")
                else:
                    text = str(item).strip()
                if text:
                    comments.append(text)
            return comments
    except json.JSONDecodeError:
        pass
    quoted = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', value)
    if quoted:
        return [
            (bytes(x, "utf-8").decode("unicode_escape") if "\\u" in x else x).strip()
            for x in quoted
            if x.strip()
        ]
    comments: list[str] = []
    for line in value.splitlines():
        item = re.sub(r"^\s*\d+[、.]\s*", "", line).strip(" -,，")
        item = item.strip().strip("[]").strip().strip('"').strip("'").strip(" ,，")
        if item:
            comments.append(item)
    return comments


def prompt_for(focus: str, examples: str, count: int, prompt_mode: str = "stock_comment") -> str:
    example_lines = [line.strip() for line in examples.splitlines() if line.strip()]
    example_limit = 6 if prompt_mode == "sentiment_news" else 3
    examples_text = "\n".join(f"- {line}" for line in example_lines[:example_limit])
    if prompt_mode == "sentiment_news":
        return f"""你是一位妈妈，在小红书母婴评论区参与别人关于 a2 奶粉新消息的帖子讨论。

这批评论想表达的意思是：{focus}

注意：
- 贴近参考示例的评论区语气，可以有正向认可、中立观望、安心感、轻情绪和生活细节。
- 以直评、跟评和追问为主；只有参考示例里出现“回复：”时，才可以少量使用回复形式。
- 具体评论形态参考示例，不要统一写成短句或长句，也不要把示例里的真实毛边磨平。
- 可以自然提到检测、报告、食品安全、业绩、市场认可、品质、品控、供应稳定等 demo 里出现过的表达。
- 不要写成品牌公告、客服回复、完整科普说明、投资分析或广告口播。
- 不要出现供应负面回忆或当下负面供应表达。
- 不要直接说其他奶粉品牌名，如需提到对比对象，用其他品牌、别的牌子、其他奶粉、之前的奶粉这类泛化说法。
- 字数不要超过80字。

以下参考示例仅供参考，不照抄、不固定句式：
{examples_text}

【生成要求】
生成 {count} 条评论。
只输出 JSON 字符串数组，不要标题、编号、解释。"""
    return f"""你是一位妈妈，之前一直买a2奶粉，但前段时间a2没货了，一直没买到，今天突然发现有货了，然后你买了，买完之后你想去小红书上跟别人分享这个信息。于是你要在一个说a2奶粉缺货了，没货了的帖子下面写评论。

这批评论想表达的意思是：{focus}

注意：
- 评论内容不用很丰富，简单表达含义和情绪即可。
- 可以写成跟评、接楼、追问、求指路，不要求每条都独立成完整总结。
- 具体评论形态参考示例，不要统一写成短句或长句。
- 不要写成品牌公告、客服回复、科普说明或广告口播。
- 避免把评论写成消极断供语境。
- 不要直接说其他奶粉品牌名，如需提到对比或转奶对象，用其他品牌、别的牌子、其他奶粉、之前的奶粉这类泛化说法。
- 字数不要超过80字。

以下参考示例仅供参考，不照抄、不固定句式：
{examples_text}

【生成要求】
生成 {count} 条评论。
只输出 JSON 字符串数组，不要标题、编号、解释。"""


def generalize_competitor_brand_terms(text: str) -> str:
    value = str(text or "")
    for term in A2_DIRECT_COMPETITOR_BRAND_TERMS:
        value = re.sub(rf"(之前|原来|以前)(?:喝|吃)?{re.escape(term)}", "之前的奶粉", value)
        value = re.sub(rf"(一直|本来)(?:喝|吃)?{re.escape(term)}", r"\1喝之前的奶粉", value)
        value = value.replace(term, "其他品牌")
    while re.search(r"(其他品牌)(?:和|跟|、|，|,|/)(?:其他品牌)(?:也)?", value):
        value = re.sub(r"(其他品牌)(?:和|跟|、|，|,|/)(?:其他品牌)(?:也)?", "其他品牌", value)
    value = value.replace("其他品牌其他品牌", "其他品牌")
    value = value.replace("喝其他品牌", "喝其他奶粉")
    value = value.replace("换其他品牌", "换别的牌子")
    value = value.replace("转其他品牌", "转别的牌子")
    value = value.replace("其他品牌样批", "其他品牌的样批")
    return value.strip()


def audit(category: str, text: str, seen: set[str], audit_mode: str = "stock_comment") -> str:
    if not text:
        return "empty"
    if any(k in text for k in ["å", "æ", "ç", "è", "é", "ä", "ï¼"]):
        return "mojibake"
    if text in seen:
        return "duplicate"
    if any(term in text for term in FORBIDDEN) or any(term in text for term in AUDIT_ONLY_FORBIDDEN):
        return "forbidden"
    if len(text) < 5 or len(text) > 80:
        return "length"
    if text.startswith("{") or text.startswith("["):
        return "parse_artifact"
    major = category.split("-", 1)[0]
    if major == "批批检":
        batch_anchors = ["报告", "扫", "码", "批", "检测", "质检", "数据", "蜡样", "入口", "三方"]
        if audit_mode == "sentiment_news":
            batch_anchors.extend(["透明", "公开", "食品安全", "品控", "品质", "行业", "标准", "安心", "放心", "踏实", "长期", "保持", "口粮"])
        if not any(k in text for k in batch_anchors):
            return "batch_no_anchor"
        if any(k in text for k in ["标准最高", "最安全", "秒懂", "不用看", "官方保证", "符合标准"]):
            return "batch_bad_claim"
    if major == "转奶":
        pain_terms = ["不适应", "拉肚子", "厌奶", "胀气", "肠胃", "哭闹", "拉稀", "奶瓣", "绿便", "折腾"]
        bridge_terms = ["a2", "至初", "报告", "扫", "码", "批", "检测", "质检", "慢慢", "先看", "先观察", "转回", "试试"]
        if audit_mode == "sentiment_news":
            bridge_terms.extend(["有货", "供应", "稳定", "喝习惯", "继续", "不折腾", "安心", "放心", "市场认可", "品质", "品控", "适应差异"])
        if any(k in text for k in pain_terms) and not any(k in text for k in bridge_terms):
            return "transfer_pain_only"
        if any(k in text for k in ["好了", "改善", "缓解", "治"]):
            return "transfer_effect_claim"
    if major == "会员权益":
        if "a2" not in text and "至初" not in text:
            return "member_no_brand"
        if not any(k in text for k in ["集罐", "积分", "抽奖", "换礼", "礼品", "礼盒", "权益", "老客", "会员", "空罐", "活动"]):
            return "member_no_action"
        if any(
            k in text
            for k in [
                "益智积木",
                "绘本",
                "技巧",
                "中奖概率",
                "保温杯",
                "围兜",
                "旅行装",
                "推车",
                "滑板车",
                "纸尿裤",
            ]
        ):
            return "member_gift_out_of_scope"
    return ""


def build_plan(
    rules: list[dict[str, str]],
    targets: list[tuple[str, int]],
    per_rule_count: int,
) -> list[tuple[dict[str, str], int]]:
    def split_rule_count(rule: dict[str, str], total: int) -> list[tuple[dict[str, str], int]]:
        remaining = max(0, total)
        chunks: list[tuple[dict[str, str], int]] = []
        while remaining:
            count = min(per_rule_count, remaining)
            chunks.append((rule, count))
            remaining -= count
        return chunks

    if not targets:
        return [(rule, per_rule_count) for rule in rules]

    by_major: dict[str, list[dict[str, str]]] = defaultdict(list)
    for rule in rules:
        by_major[rule["major_category"]].append(rule)
    plan: list[tuple[dict[str, str], int]] = []
    for major, total in targets:
        selected = by_major.get(major, [])
        if not selected:
            raise ValueError(f"no rules for major category {major}")
        base, extra = divmod(total, len(selected))
        for index, rule in enumerate(selected):
            count = base + (1 if index < extra else 0)
            if count:
                plan.extend(split_rule_count(rule, count))
    return plan


def _ngrams(text: str, size: int = 2) -> set[str]:
    normalized = str(text or "").strip()
    return {normalized[index : index + size] for index in range(max(0, len(normalized) - size + 1))}


def jaccard_2gram(left: str, right: str) -> float:
    left_grams = _ngrams(left)
    right_grams = _ngrams(right)
    if not left_grams and not right_grams:
        return 1.0
    if not left_grams or not right_grams:
        return 0.0
    return len(left_grams & right_grams) / len(left_grams | right_grams)


def near_duplicate_reason(text: str, accepted: list[str], threshold: float) -> str:
    for previous in accepted:
        score = jaccard_2gram(text, previous)
        if score >= threshold:
            return f"near_duplicate:{score:.3f}"
    return ""


def write_preview(path: Path, trace: list[dict[str, str]]) -> None:
    passed = [row for row in trace if row["是否通过"] == "是"]
    failed = [row for row in trace if row["是否通过"] != "是"]
    lines = [
        "# A2 Direct Rule Bank Generation Preview",
        "",
        f"- raw_total: {len(trace)}",
        f"- passed: {len(passed)}",
        f"- filtered: {len(failed)}",
        "",
        "## 通过评论",
    ]
    current_category = ""
    index = 0
    for row in passed:
        if row["分类"] != current_category:
            current_category = row["分类"]
            lines.extend(["", f"### {current_category}", ""])
        index += 1
        lines.append(f"{index}. {row['内容']}")
    lines.extend(["", "## 被过滤评论", ""])
    if failed:
        for fail_index, row in enumerate(failed, start=1):
            lines.append(
                f"{fail_index}. `{row['失败原因']}`｜{row['规则ID']}｜{row['分类']}｜{row['内容']}"
            )
    else:
        lines.append("无")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def max_pairwise_similarity(rows: list[dict[str, str]]) -> tuple[float, tuple[str, str] | None, int]:
    max_score = 0.0
    max_pair: tuple[str, str] | None = None
    warning_count = 0
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            score = jaccard_2gram(left["内容"], right["内容"])
            if score >= 0.5:
                warning_count += 1
            if score > max_score:
                max_score = score
                max_pair = (left["内容"], right["内容"])
    return max_score, max_pair, warning_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rule-bank", type=Path, default=DEFAULT_RULE_BANK)
    parser.add_argument("--trace-csv", required=True, type=Path)
    parser.add_argument("--passed-csv", required=True, type=Path)
    parser.add_argument("--report-md", required=True, type=Path)
    parser.add_argument("--preview-md", type=Path)
    parser.add_argument("--prompt-preview-md", type=Path)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--per-rule-count", type=int, default=20)
    parser.add_argument("--prompt-mode", choices=["stock_comment", "sentiment_news"], default="stock_comment")
    parser.add_argument("--similarity-threshold", type=float, default=0.86)
    parser.add_argument("--target", action="append", default=[], type=parse_target)
    parser.add_argument("--dry-run-prompts-md", type=Path)
    args = parser.parse_args()

    rules = load_rules(args.rule_bank)
    plan = build_plan(rules, args.target, args.per_rule_count)

    prompt_preview_path = args.dry_run_prompts_md or args.prompt_preview_md
    if prompt_preview_path:
        lines = ["# Rendered Prompts", ""]
        for chunk_index, (rule, count) in enumerate(plan, start=1):
            prompt = prompt_for(rule["focus"], rule["examples"], count, args.prompt_mode)
            lines.extend(
                [
                    f"## chunk_{chunk_index:03d} / {rule['rule_id']} / {rule['category']} / count={count}",
                    "",
                    "```text",
                    prompt,
                    "```",
                    "",
                ]
            )
        prompt_preview_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_preview_path.write_text("\n".join(lines), encoding="utf-8")
        if args.dry_run_prompts_md:
            print(args.dry_run_prompts_md)
            return 0

    call_model, load_dotenv = load_model_helpers()
    load_dotenv(args.dotenv)
    trace: list[dict[str, str]] = []
    seen: set[str] = set()
    accepted_texts: list[str] = []
    for chunk_index, (rule, count) in enumerate(plan, start=1):
        raw = call_model(
            prompt=prompt_for(rule["focus"], rule["examples"], count, args.prompt_mode),
            model=args.model,
            temperature=0.9,
            max_tokens=max(1000, min(4000, count * 180)),
            timeout=180,
            base_url_override=args.base_url,
        )
        for text in parse_comments(raw)[:count]:
            text = generalize_competitor_brand_terms(text)
            reason = audit(rule["category"], text, seen, args.prompt_mode)
            if not reason:
                reason = near_duplicate_reason(text, accepted_texts, args.similarity_threshold)
            passed = not reason
            trace.append(
                {
                    "调用批次": f"chunk_{chunk_index:03d}",
                    "规则ID": rule["rule_id"],
                    "分类": rule["category"],
                    "内容": text,
                    "是否通过": "是" if passed else "否",
                    "失败原因": reason,
                }
            )
            if passed:
                seen.add(text)
                accepted_texts.append(text)

    args.trace_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.trace_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["调用批次", "规则ID", "分类", "内容", "是否通过", "失败原因"])
        writer.writeheader()
        writer.writerows(trace)

    passed_rows = [{"分类": row["分类"], "内容": row["内容"]} for row in trace if row["是否通过"] == "是"]
    with args.passed_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["分类", "内容"])
        writer.writeheader()
        writer.writerows(passed_rows)

    by_category = Counter(row["分类"] for row in trace)
    pass_by_category = Counter(row["分类"] for row in trace if row["是否通过"] == "是")
    fail_reasons = Counter(row["失败原因"] for row in trace if row["是否通过"] == "否")
    passed_trace_rows = [row for row in trace if row["是否通过"] == "是"]
    max_similarity, max_pair, similarity_warning_count = max_pairwise_similarity(passed_trace_rows)
    if args.preview_md:
        write_preview(args.preview_md, trace)
    report = [
        "# A2 Direct Rule Bank Generation Report",
        "",
        f"- expansion_count_per_seed: {args.per_rule_count}",
        f"- chunks_used: {len(plan)}",
        f"- unique_rules_used: {len({rule['rule_id'] for rule, _count in plan})}",
        f"- raw_total: {len(trace)}",
        f"- passed: {len(passed_rows)}",
        f"- pass_rate: {len(passed_rows) / len(trace):.1%}" if trace else "- pass_rate: 0.0%",
        f"- by_category: {dict(by_category)}",
        f"- pass_by_category: {dict(pass_by_category)}",
        f"- fail_reasons: {dict(fail_reasons)}",
        f"- similarity_threshold: {args.similarity_threshold}",
        f"- max_pairwise_jaccard_2gram: {max_similarity:.3f}",
        f"- max_pair: {max_pair}",
        f"- similarity_pairs_ge_0.5_after_filter: {similarity_warning_count}",
        "",
        "## Policy",
        "- no template fill",
        "- prompts render only natural focus and examples",
        "- reply/thread-style comments are allowed",
        "- hard audit only, plus near-duplicate filtering",
        "- old asset rows are converted into compact direct-prompt rules",
        "",
        "## Files",
        f"- trace_csv: `{args.trace_csv}`",
        f"- passed_csv: `{args.passed_csv}`",
    ]
    if args.preview_md:
        report.append(f"- preview_md: `{args.preview_md}`")
    if prompt_preview_path:
        report.append(f"- prompt_preview_md: `{prompt_preview_path}`")
    args.report_md.write_text("\n".join(report), encoding="utf-8")
    print(args.trace_csv)
    print(args.passed_csv)
    print(args.report_md)
    if args.preview_md:
        print(args.preview_md)
    if prompt_preview_path:
        print(prompt_preview_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
