#!/usr/bin/env python3
"""Strict-clean A2 direct-prompt comments and fill missing rows conservatively."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from itertools import product
from pathlib import Path


TARGETS = {
    "有货-到货直给": 75,
    "有货-渠道线索": 75,
    "批批检-罐底扫码": 40,
    "批批检-报告信息": 40,
    "转奶-先不换": 40,
    "转奶-继续熟悉款": 40,
    "会员权益-集罐换礼": 35,
    "会员权益-积分老客": 35,
}


GLOBAL_BAD = [
    "[",
    "]",
    '"',
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
    "医疗护理",
    "美版",
    "毒奶",
    "假货",
    "绝对",
    "保证",
    "无风险",
    "治好",
    "改善",
    "缓解",
    "客服",
    "正装",
    "购买记录",
    "辅食盒",
    "旅行装",
    "奶粉勺",
    "保温杯",
    "中奖概率",
    "概率",
    "买满",
    "抵现金",
    "抵现",
    "截止",
    "过期",
    "限量",
    "先到先得",
    "提交",
    "订单",
    "门槛",
    "检测合格",
    "合格",
    "当天",
    "不是摆设",
    "重金属",
    "功能",
    "检查报告图标",
    "3份",
    "4份",
    "两罐",
    "每罐",
    "没得看",
    "中奖率",
    "中奖",
    "抽奖中",
    "两个都关注",
    "顺手点",
    "可能有活动",
    "有份",
    "挺好的",
]


CATEGORY_BAD = {
    "有货": ["没", "没有", "急", "冲", "快去", "希望还有", "库存", "私信", "xx店", "广州", "丽家宝贝", "爱婴室", "搬", "堆"],
    "批批检": ["没啥问题", "每罐都有吗", "每批都有吗", "四份", "四五份", "两罐都有", "每罐都扫", "每一项", "最关注"],
    "转奶": ["拉", "吐", "肠胃", "大便", "便便", "皮肤", "作息", "哭", "闹", "厌奶", "翻车", "风险", "没毛病", "没出过问题", "不肯喝", "半个月", "便宜", "舒服", "乖", "打仗", "受罪", "痛苦", "同事", "瘦", "至少一周", "大人小孩", "刚缓过来", "懒得", "等喝够", "一直挺好", "好不容易适应", "挺好的"],
    "会员权益": ["捡", "洗干净", "同事", "两年", "一年", "换过", "抽中", "中了", "没中", "自动", "小样", "周边", "全国", "堆着", "找出来", "每天", "质量不错", "赠品", "链接", "试用装", "抵点", "额外礼", "规则挺清楚", "小罐"],
}


def major(category: str) -> str:
    return category.split("-", 1)[0]


def bad_reason(category: str, text: str, seen: set[str]) -> str:
    if not text or text in seen:
        return "empty_or_duplicate"
    if len(text) < 6 or len(text) > 52:
        return "length"
    for term in GLOBAL_BAD:
        if term in text:
            return f"global:{term}"
    for term in CATEGORY_BAD.get(major(category), []):
        if term in text:
            return f"category:{term}"
    if category.startswith("有货"):
        if not any(k in text for k in ["a2", "至初"]):
            return "stock_no_brand"
        if not any(k in text for k in ["到", "买", "拍", "货", "发货", "下单", "拿", "问", "山姆", "线上", "门店", "导购"]):
            return "stock_no_signal"
    if category.startswith("批批检"):
        if not any(k in text for k in ["报告", "扫", "码", "批", "检测", "质检", "数据", "蜡样", "入口"]):
            return "batch_no_anchor"
    if category.startswith("转奶"):
        if not any(k in text for k in ["a2", "至初"]):
            return "transfer_no_brand"
        if not any(k in text for k in ["转奶", "换", "折腾", "不适应", "喝顺", "熟悉", "不动", "不转"]):
            return "transfer_no_pain"
    if category.startswith("会员权益"):
        if not any(k in text for k in ["a2", "至初"]):
            return "member_no_brand"
        if not any(k in text for k in ["集罐", "积分", "抽奖", "换礼", "礼品", "老客", "会员", "空罐", "活动"]):
            return "member_no_action"
    return ""


def template_candidates(category: str) -> list[str]:
    if category == "有货-到货直给":
        leads = ["刚看到", "今天看到", "我也看到", "刚确认", "终于看到", "刚发现", "早上看到", "刷到"]
        signals = ["a2到货", "a2能买", "a2能拍", "a2来货", "a2上架", "至初能下单"]
        actions = ["我去看看", "先下一罐", "准备拍一罐", "先把熟悉款接上", "心里松了点", "去看一下", "先买一罐", "这下能接上"]
        return [f"{a}{b}了，{c}" for a, b, c in product(leads, signals, actions)]
    if category == "有货-渠道线索":
        channels = ["导购", "门店", "母婴店", "山姆", "线上", "妈妈群", "🍑"]
        signals = ["说a2到了", "看到a2有货", "刷到a2能拍", "通知a2到货", "说至初能买"]
        actions = ["我准备去看看", "可以先问问", "我先下了一罐", "准备下班去拿", "我也想去看下", "先问一下还有没有", "准备接上熟悉款"]
        return [f"{a}{b}，{c}" for a, b, c in product(channels, signals, actions)]
    if category == "批批检-罐底扫码":
        starts = ["刚拿到a2", "新到手这罐a2", "补到a2后", "回家拆罐时", "导购提醒后", "顺手试了一下"]
        actions = ["扫了罐底码", "扫了罐底物流码", "扫了一下罐底", "点开罐底那个码"]
        ends = ["报告能出来", "能看到这批报告", "报告入口能点开", "对应批次报告能看", "检测报告能打开"]
        return [f"{a}，{b}，{c}" for a, b, c in product(starts, actions, ends)]
    if category == "批批检-报告信息":
        subjects = ["报告入口", "检测报告", "质检那页", "60多项数据", "蜡样那项", "自己这批报告"]
        verbs = ["能点开看", "能扫出来", "能看到", "可以自己核一下", "我会多看一眼"]
        tails = ["不一定全懂，但能看到就行", "不用别人转述，自己能看", "名字记不全，但报告里有", "我只挑重点看了下", "像评论区说的那样能打开"]
        return [f"{a}{b}，{c}" for a, b, c in product(subjects, verbs, tails)]
    if category == "转奶-先不换":
        pains = ["转奶太折腾了", "怕宝宝不适应", "喝顺了就不想换", "转奶要慢慢来太麻烦", "换来换去也累", "熟悉款能接上就好"]
        returns = ["a2先继续", "先不换a2了", "还是喝a2", "a2能买就先喝着", "继续熟悉的a2", "先把a2接上"]
        tones = ["", "，我就这样想", "，先稳住", "，不折腾了", "，这次就算了"]
        return [f"{a}，{b}{c}" for a, b, c in product(pains, returns, tones)]
    if category == "转奶-继续熟悉款":
        openings = ["本来想换奶粉", "看过别的牌子", "之前也纠结过转奶", "本来想试试别的", "差点就准备换了", "也问过别的奶粉"]
        pains = ["但转奶太麻烦", "但怕宝宝不适应", "但喝顺了真不想动", "但换来换去太折腾", "但转奶要慢慢过渡"]
        returns = ["a2能买到就继续喝", "还是接着喝a2", "熟悉的a2能接上就行", "先不换了，继续a2", "a2到手就先喝原来的"]
        return [f"{a}，{b}，{c}" for a, b, c in product(openings, pains, returns)]
    if category == "会员权益-集罐换礼":
        openings = ["看到a2会员能集罐换礼", "a2集罐换奶粉这个我会看", "长期喝a2的话", "家里一直喝a2", "a2空罐先留着", "刚发现a2有集罐活动"]
        tails = ["空罐先不扔了", "感觉还挺实用", "家里一直喝的话用得上", "准备看看规则", "攒起来不浪费", "这点挺适合老用户"]
        return [f"{a}，{b}" for a, b in product(openings, tails)]
    if category == "会员权益-积分老客":
        openings = ["看到a2会员有积分换礼", "导购提醒看a2会员权益", "群里在说a2老客礼", "a2会员活动我准备看看", "a2积分和抽奖都有", "补货时顺便看了a2会员"]
        tails = ["长期买的话可以研究下", "我先看看自己符不符合", "准备先问问规则", "比只买奶粉多一点权益", "有需要的可以留意下", "老用户会更愿意看一眼"]
        return [f"{a}，{b}" for a, b in product(openings, tails)]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True, type=Path)
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument("--report-md", required=True, type=Path)
    args = parser.parse_args()

    with args.input_csv.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    accepted: list[dict[str, str]] = []
    seen: set[str] = set()
    rejects = Counter()
    for row in rows:
        category = row.get("分类", "").strip()
        text = row.get("内容", "").strip()
        reason = bad_reason(category, text, seen)
        if reason:
            rejects[reason] += 1
            continue
        accepted.append({"分类": category, "内容": text})
        seen.add(text)

    by_category = Counter(row["分类"] for row in accepted)
    final_rows: list[dict[str, str]] = []
    for category, target in TARGETS.items():
        kept = [row for row in accepted if row["分类"] == category][:target]
        final_rows.extend(kept)
        need = target - len(kept)
        if need <= 0:
            continue
        for candidate in template_candidates(category):
            if not bad_reason(category, candidate, seen):
                final_rows.append({"分类": category, "内容": candidate})
                seen.add(candidate)
                need -= 1
            if need == 0:
                break
        if need:
            raise RuntimeError(f"cannot fill {category}, need {need}")

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["分类", "内容"])
        writer.writeheader()
        writer.writerows(final_rows)

    counts = Counter(row["分类"] for row in final_rows)
    major_counts = Counter(major(row["分类"]) for row in final_rows)
    duplicate_count = len(final_rows) - len({row["内容"] for row in final_rows})
    report = [
        "# A2 简单提示词规则最终清洗补齐报告",
        "",
        f"- source_rows: {len(rows)}",
        f"- kept_after_strict_clean: {len(accepted)}",
        f"- final_rows: {len(final_rows)}",
        f"- major_counts: {dict(major_counts)}",
        f"- detail_counts: {dict(counts)}",
        f"- duplicates: {duplicate_count}",
        f"- rejects: {dict(rejects)}",
        "",
        "## Kept Before Fill",
        *[f"- {category}: {by_category.get(category, 0)}" for category in TARGETS],
    ]
    args.report_md.write_text("\n".join(report), encoding="utf-8")
    print(args.output_csv)
    print(args.report_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
