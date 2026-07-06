#!/usr/bin/env python3
"""Probe one simple Wangyue diary-style seeding chain.

This intentionally avoids the previous multi-slot planner. The goal is to test
one user-approved core chain first, then inspect repetition and extract slots.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
import pymysql


OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/0705_wangyue_product_relation_evidence")
EXPERIMENT_ID = "v455_frequency_grounded_expansion_probe"
REAL_UGC_SELLING_PATH = Path("/Users/luxifa/maga/关键词语料/旺玥真实ugc卖点表述.csv")
STRONG_SELLING_PATH = Path("/Users/luxifa/maga/关键词语料/旺玥活动（ai训练确认信息）-规则库 - 卖点表述-已完成.csv")

FORBIDDEN_TERMS = [
    "🍼",
    "厌奶",
    "体质",
    "肠胃",
    "脾胃",
    "天然",
    "儿保",
    "抵抗力",
    "宝宝",
    "宝妈",
    "自护力",
    "底气",
    "源乳",
    "初乳",
    "换季",
    "流感",
    "春游",
    "秋游",
    "😅",
]

POST_GENERATION_HARD_REPLACEMENTS = {
    "自护力": "保护力",
    "抵抗力": "保护力",
}

ALLOWED_PROPRIETARY_TERMS = {
    "天然乳脂": "PROPRIETARY_TIANRANRUZHI",
}

FORM_RISK_TERMS = [
    "奶瓶",
    "三段",
    "3段",
    "二段",
    "2段",
    "1段",
    "小包",
    "一包",
    "条装",
    "便携装",
    "随身带",
    "书包侧袋",
    "水杯侧袋",
    "自己泡",
    "自己冲",
    "自己舀粉",
    "自己加水",
]

LOW_AGE_PATTERNS = [
    r"[一二两12]岁(?!半?多?以?上)",
    r"[一二两12]岁半",
    r"[0-2]\s*岁",
    r"[0-2]\s*周岁",
    r"\d+\s*个月",
    r"[一二三四五六七八九十]+个月",
    r"三岁前",
    r"3岁前",
]

WRONG_STAGE_PATTERNS = [
    r"一段奶粉",
    r"1段奶粉",
    r"二段奶粉",
    r"2段奶粉",
    r"三段奶粉",
    r"3段奶粉",
    r"喝一段(?!时间)",
]

CURRENT_TIME_RISK_PATTERNS = [
    r"现在.{0,4}(春天|夏天|秋天|冬天)",
    r"最近.{0,8}(流感|换季|中招季)",
    r"这阵子.{0,8}(流感|换季|中招季)",
]


@dataclass(frozen=True)
class ModelConfig:
    api_key: str
    base_url: str
    model: str
    timeout: int = 120


DIARY_CHAIN_SYSTEM = """你是小红书妈妈UGC写手。
只按给定的“核心内容”写一篇自然种草笔记，不要另起结构。
输出 JSON object，字段只能是 title 和 body。"""


CORE_PROMPT = """任务：写一篇小红书妈妈UGC正向种草笔记。

{core_label}：
{core_content}

收尾意图标签：
{ending_direction}

硬边界：
- 不写这些词：🍼、厌奶、体质、肠胃、脾胃、天然、儿保、宝宝、宝妈、底气、源乳、初乳、换季、流感、春游、秋游、😅。
- 不写3岁以下、三段、奶瓶、便携小包、书包侧袋、水杯侧袋。
- 不写孩子自己泡奶粉、自己冲奶粉、自己舀粉。
- 不写当前季节或当前疾病大环境。
- 不要写成医生建议、治疗、保证有效。

写法：
- 标题不超过20字，emoji算2字；长短和风格要随机，从正文里自然提炼。
- 标题可以是短词、生活动作、轻感叹、结果观察、妈妈自言自语等不同类型；不要都写成“记录/变化/带娃日常”。
- 正文120-180字左右。
- 像妈妈顺手发，不要像广告brief。
- 正文必须自然出现“旺玥”一次。
- 写过去状态和现在变化时，要让读者能从本句或前后句判断是在说孩子，不要让人误会成妈妈自己的状态。
- 中文口语可以省略主语，但上下文里要先点出孩子、娃、他或她这类指代。
- 上面这件事里已经包含主线和卖点；收尾意图标签是内部标签，不要照抄或翻译标签本身。
- 结尾要像妈妈顺着正文自然收一句，不要把收尾写成固定口号。
- 结尾不要只落在安心、放心、踏实、省心这类泛情绪词。
- 可以调整句序、口气和细节，不要逐句翻译。
- 不要再补新的选择理由或第二个生活入口。
"""


SEEDS = {
    "today_trigger": [
        "晚上终于有空，想来小红书记一下这段时间",
        "晚饭后收拾桌面，孩子还在客厅转悠",
        "孩子从外面回来还在客厅玩，妈妈突然想记录一下",
        "洗杯子时想到这段时间孩子变化挺明显",
        "孩子喝完旺玥又跑去玩，妈妈顺手记一笔",
        "陪孩子玩到晚上，才想起来记一笔",
        "睡前收拾客厅，想起最近孩子出门回来不太蔫了",
        "带娃回来刚坐下，孩子又去找玩具了",
        "进门放好东西的时候，发现孩子还想继续玩",
        "收拾水杯的时候，想到孩子最近没那么容易累",
        "晚饭后看孩子还在客厅转悠，突然想记一下",
        "从外面回来，他没急着歇，先去客厅翻玩具",
        "洗杯子的时候，顺手把这阵子的变化记一下",
        "放学后在外面玩了一圈，到家还没急着躺下",
        "晚上把玩具收一半，发现孩子还在旁边忙活",
    ],
    "past_state": [
        "以前玩一会儿就喊累",
        "以前从外面回来经常蔫蔫的，还容易有点小状况",
        "以前活动量一大，后半天就不太在线",
        "以前下午后半段容易蔫，我得多看着点",
        "以前孩子出门玩回来就不太想动，状态不算稳",
        "以前平时看着还行，一出门玩久了就明显累",
        "以前从外面回来，经常要缓一阵",
        "以前一到傍晚就不太愿意动",
        "以前玩到后半段，总要喊着歇一会儿",
    ],
    "state_observation": [
        "外面跑了一圈回来也没蔫，进门还在客厅转来转去",
        "下午玩得不少，回家后还有劲跟着大人收拾小玩具",
        "晚饭后还能自己找点事做，不用我一直哄着歇",
        "出去一趟回来没有马上躺着，洗完手还想再玩一会儿",
        "活动量大一点也撑得住，后半段还能跟上家里节奏",
        "晚上陪到挺晚，也没像以前那样一动就喊累",
        "回家路上没有一直喊累，到家后还愿意自己玩一阵",
        "外出回来还能自己玩一会儿",
        "下午那股劲比以前足，回家后还能跟着家里节奏走",
        "一天下来没那么快散架，妈妈肉眼能看出来",
        "出门玩完还有余量，回家后不需要一直催着哄着",
        "晚一点也没明显蔫下去，整个人看着更有劲",
        "回到家还愿意跟着大人收拾东西，不是直接瘫着",
        "下午活动完还有点余量，晚上节奏也没乱",
        "出去玩完还能自己玩一会儿，不用我一直盯着",
        "进门后还能自己找事做，不是直接躺着不动",
        "后半天还能跟上家里的节奏，看着没那么疲",
        "玩到晚一点也没有明显蔫下去",
        "回家后愿意自己找玩具玩一会儿，不是一直喊累",
        "活动回来还能坐下来吃点东西，不用先缓半天",
        "傍晚那会儿没有突然蔫下去，妈妈看着很明显",
        "白天玩得多，晚上也没乱套",
        "回家后还会跟着把玩具归一下",
        "晚一点也没急着喊累",
        "放学后又玩了一阵，回家还能自己洗手吃东西",
        "到家没有先瘫着，而是自己翻了一会儿玩具",
        "一整天下来节奏更均匀，不是前面疯玩后面歇菜",
    ],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL") or None)
    parser.add_argument("--seed", type=int, default=442)
    parser.add_argument("--core-label", default="这篇要写的事")
    parser.add_argument("--core-content-format", choices=("narrative", "child_state_labels"), default="child_state_labels")
    parser.add_argument("--output-suffix", default="")
    args = parser.parse_args()

    random.seed(args.seed)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = _load_model_config(args.database_url, args.model)
    selling_expressions = _load_selling_expressions()

    seeds = [_sample_seed(index, selling_expressions, args.core_content_format) for index in range(1, args.count + 1)]
    batch_code = f"{EXPERIMENT_ID}_{int(time.time())}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = [
            executor.submit(_generate_one, config, item_no, seed, args.core_label)
            for item_no, seed in enumerate(seeds, start=1)
        ]
        items = [future.result() for future in concurrent.futures.as_completed(futures)]
    items.sort(key=lambda item: item["item_no"])

    summary = _summary(items)
    response = {
        "experiment_id": EXPERIMENT_ID,
        "batch_id": "local_v455",
        "batch_code": batch_code,
        "model": config.model,
        "core_label": args.core_label,
        "core_content_format": args.core_content_format,
        "core_chain": "short inline core brief: diary trigger + prior weak state + varied Wangyue product-reason phrase + child-state observation + ending direction",
        "selling_expression_sources": [str(REAL_UGC_SELLING_PATH), str(STRONG_SELLING_PATH)],
        "items": items,
        "report": {"summary": summary, "candidate_slots": _candidate_slots()},
    }

    artifact_stem = EXPERIMENT_ID
    if args.output_suffix:
        artifact_stem = f"{EXPERIMENT_ID}_{_safe_suffix(args.output_suffix)}"
    response_path = OUTPUT_DIR / f"{artifact_stem}_response.json"
    preview_path = OUTPUT_DIR / f"{artifact_stem}_preview.md"
    prompt_path = OUTPUT_DIR / f"{artifact_stem}_item1_rendered_prompt.md"
    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    prompt_path.write_text(_format_prompt_sample(items[0]), encoding="utf-8")
    _write_preview(preview_path, response_path, prompt_path, response)

    print(json.dumps({
        "response_path": str(response_path),
        "preview_path": str(preview_path),
        "prompt_path": str(prompt_path),
        "summary": summary,
    }, ensure_ascii=False, indent=2))


def _sample_seed(index: int, selling_expressions: list[dict[str, str]], core_content_format: str) -> dict[str, str]:
    selling = random.choice(selling_expressions)
    seed = {
        "item_no": str(index),
        "today_trigger": random.choice(SEEDS["today_trigger"]),
        "past_state": random.choice(SEEDS["past_state"]),
        "state_observation": random.choice(SEEDS["state_observation"]),
        "ending_direction": random.choice([
            "positive_repurchase_after_visible_change",
            "positive_child_fit_after_observation",
            "positive_keep_as_home_routine_choice",
            "positive_home_routine_after_visible_change",
            "positive_brand_preference_after_observation",
        ]),
        "selling_point": selling["selling_point"],
        "selling_expression_reference": selling["expression"],
        "selling_expression_inline": random.choice(selling["inline_options"]),
        "selling_expression_source": selling["source"],
    }
    seed["product_reason_clause"] = _build_product_reason_clause(seed["selling_expression_inline"])
    seed["core_content"] = _build_core_content(seed, core_content_format)
    return seed


def _build_product_reason_clause(selling_expression_inline: str) -> str:
    subject = _product_reason_subject(selling_expression_inline)
    shapes = [
        f"家里后来一直喝旺玥，主要也是想把{selling_expression_inline}补上",
        f"后来换到旺玥，主要图{selling_expression_inline}",
        f"三岁后日常口粮里，我会更在意{selling_expression_inline}，所以家里一直喝旺玥",
        f"旺玥喝到现在，{selling_expression_inline}确实是我当时留意过的",
        f"当时对比完，旺玥里面{subject}这些更合我心里那个标准",
        f"给他换旺玥那会儿，我主要是想把{selling_expression_inline}跟上",
        f"我那时比较在意{selling_expression_inline}，才选了旺玥",
    ]
    return random.choice(shapes)


def _product_reason_subject(selling_expression_inline: str) -> str:
    subject = selling_expression_inline.strip()
    replacements = (
        ("这些保护力配置", ""),
        ("这些配置", ""),
        ("这一组", ""),
        ("这组配置", ""),
        ("这块", ""),
    )
    for source, target in replacements:
        subject = subject.replace(source, target)
    return subject.strip("，、 ")


def _build_core_content(seed: dict[str, str], core_content_format: str) -> str:
    past_state = _child_past_state_phrase(seed["past_state"])
    state_observation = _child_state_phrase(seed["state_observation"])
    if core_content_format == "child_state_labels":
        return "\n".join([
            f"生活触发：{seed['today_trigger']}",
            f"孩子以前状态：{past_state}",
            f"旺玥关系：{seed['product_reason_clause']}",
            f"孩子现在状态：{state_observation}",
        ])
    shapes = [
        (
            f"{seed['today_trigger']}。"
            f"{past_state}；{seed['product_reason_clause']}。"
            f"现在{state_observation}。"
        ),
        (
            f"晚上想记一笔：{seed['today_trigger']}。"
            f"{past_state}。"
            f"{seed['product_reason_clause']}，这段时间{state_observation}。"
        ),
        (
            f"{seed['today_trigger']}，才反应过来这阵子变化挺明显。"
            f"{past_state}。"
            f"{seed['product_reason_clause']}。"
            f"现在{state_observation}。"
        ),
        (
            f"带娃日常随手记：{seed['today_trigger']}。"
            f"{past_state}，{seed['product_reason_clause']}。"
            f"家里喝到现在，{state_observation}。"
        ),
        (
            f"{seed['today_trigger']}。"
            f"{past_state}。"
            f"{seed['product_reason_clause']}。"
            f"{state_observation}。"
        ),
    ]
    return random.choice(shapes)


def _child_past_state_phrase(text: str) -> str:
    phrase = _strip_leading_time_markers(text)
    for subject in ("孩子", "小朋友", "小家伙", "他", "她"):
        if phrase.startswith(subject):
            phrase = phrase[len(subject):].strip()
            break
    return f"孩子以前{phrase}"


def _child_state_phrase(text: str) -> str:
    phrase = _strip_leading_time_markers(text)
    if phrase.startswith(("孩子", "小朋友", "小家伙", "他", "她")):
        return phrase
    return f"孩子{phrase}"


def _strip_leading_yiqian(text: str) -> str:
    return _strip_leading_time_markers(text)


def _strip_leading_time_markers(text: str) -> str:
    return re.sub(r"^以前", "", text.strip())


def _load_selling_expressions() -> list[dict[str, str]]:
    expressions: list[dict[str, str]] = []
    if REAL_UGC_SELLING_PATH.exists():
        with REAL_UGC_SELLING_PATH.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                selling_point = _clean_text(row.get("卖点"))
                expression = _clean_text(row.get("卖点表述"))
                inline_options = _normalize_selling_expression(expression)
                if selling_point == "进阶保护力" and inline_options and _expression_usable(expression):
                    expressions.append({
                        "selling_point": selling_point or "卖点表达",
                        "expression": expression,
                        "inline_options": inline_options,
                        "source": "旺玥真实ugc卖点表述.csv",
                    })

    if STRONG_SELLING_PATH.exists():
        with STRONG_SELLING_PATH.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        for row in rows[2:]:
            if len(row) < 7:
                continue
            selling_point = _clean_text(row[5])
            expression = _clean_text(row[6])
            inline_options = _normalize_selling_expression(expression)
            if selling_point == "进阶保护力" and inline_options and _expression_usable(expression) and 8 <= len(expression) <= 90:
                expressions.append({
                    "selling_point": selling_point or "卖点表达",
                    "expression": expression,
                    "inline_options": inline_options,
                    "source": "卖点表述-已完成.csv",
                })

    ingredient_expressions = [
        item for item in expressions
        if any(term in item["expression"] for term in ("免疫球蛋白", "乳铁蛋白", "HMO", "hmo"))
    ]
    if len(ingredient_expressions) >= 8:
        expressions = ingredient_expressions

    if not expressions:
        return [
            {
                "selling_point": "进阶保护力",
                "expression": "乳铁蛋白和HMO这块配置我比较看重，喝下来孩子状态确实更稳",
                "inline_options": ["乳铁蛋白和HMO这块"],
                "source": "fallback",
            }
        ]
    return expressions


def _normalize_selling_expression(expression: str) -> list[str]:
    """Turn source selling copy into phrase fragments that can sit inside a sentence."""
    if not expression:
        return []
    if any(term in expression for term in ("好处很多", "安利", "助力孩子成长", "支持体格", "身高体重", "体格长得", "爱喝", "奶味")):
        return []

    options: list[str] = []
    has_ig = "免疫球蛋白" in expression
    has_ltf = "乳铁蛋白" in expression
    has_hmo = "HMO" in expression or "hmo" in expression
    has_protection = "保护力" in expression or "助力保护" in expression

    if has_ig and has_ltf and has_hmo:
        options.extend([
            "免疫球蛋白、乳铁蛋白和HMO这一组",
            "乳铁蛋白、HMO这些保护力配置",
            "免疫球蛋白加乳铁蛋白、HMO这块",
        ])
    elif has_ltf and has_hmo:
        options.extend([
            "乳铁蛋白和HMO这块",
            "乳铁蛋白、HMO这些配置",
        ])
    elif has_ig and has_ltf:
        options.extend([
            "免疫球蛋白和乳铁蛋白这块",
            "免疫球蛋白、乳铁蛋白这组配置",
        ])
    elif has_ig:
        options.append("免疫球蛋白这块")
    elif has_ltf:
        options.append("乳铁蛋白这块")
    elif has_hmo:
        options.append("HMO这块")

    if has_protection and options:
        pass
    elif has_protection:
        options.append("保护力配置这块")

    return list(dict.fromkeys(options))


def _expression_usable(expression: str) -> bool:
    if not expression:
        return False
    if any(term in expression for term in FORBIDDEN_TERMS):
        return False
    dirty_terms = (
        "小卫士",
        "防护网",
        "防护",
        "防线",
        "堡垒",
        "爱的护甲",
        "隐形护盾",
        "防护盾",
        "保护盾",
        "三重盾",
        "保护罩",
        "保护力全家桶",
        "坏菌菌",
        "每天两杯",
        "一天两杯",
        "一天一杯",
        "早晚两杯",
        "每天一杯",
        "早餐奶",
        "睡前",
        "价格",
        "侄子",
        "14岁",
        "175",
        "185",
        "寄宿",
        "小包",
        "一包",
        "奶瓶",
        "硬核",
        "bb",
        "BB",
        "嘎嘎",
        "全勤",
        "妥妥",
        "全方位",
        "明星",
        "➕",
        "~",
        "开挂",
        "拉满",
        "强强联合",
        "强强联手",
        "强护",
        "铁三角",
        "三大明星",
        "三重",
        "协同",
        "内守外防",
        "专属研发",
        "保驾护航",
        "天气",
        "冬天",
        "降温",
        "多变环境",
        "班里",
        "请假",
        "功课",
        "省心",
        "焦虑",
        "感冒",
        "中招",
        "保护伞",
        "荷兰",
        "进口",
        "原装",
        "回购",
        "长那么高",
        "幼儿园总是",
        "适应多变",
        "多变",
        "坏菌",
        "长高",
        "长个",
        "长肉",
        "肉肉",
        "生长曲线",
        "身高",
        "体重",
        "眼脑",
        "专注",
        "DHA",
        "燕窝酸",
        "钙铁锌",
        "30+",
        "饭量",
        "吃饭",
        "不肯吃饭",
        "营养一站式",
        "营养均衡",
        "营养丰富",
        "踏实",
        "放心",
        "安心",
        "免疫力",
    )
    if any(term in expression for term in dirty_terms):
        return False
    if re.search(r"[\U0001F300-\U0001FAFF]", expression):
        return False
    if re.search(r"\d{2,}", expression):
        return False
    return True


def _generate_one(config: ModelConfig, item_no: int, seed: dict[str, str], core_label: str) -> dict[str, Any]:
    prompt = CORE_PROMPT.format(
        core_label=core_label,
        core_content=seed["core_content"],
        ending_direction=seed["ending_direction"],
    )
    raw: dict[str, Any]
    error = ""
    try:
        raw = _call_json_with_retry(
            config,
            system=DIARY_CHAIN_SYSTEM,
            user=prompt,
            max_tokens=1200,
            temperature=0.82,
        )
    except Exception as exc:  # noqa: BLE001 - local probe should preserve failed evidence.
        raw = {}
        error = str(exc)

    raw_title = _clean_generated_text(raw.get("title"))
    raw_body = _clean_generated_text(raw.get("body"))
    title, title_replacements = _apply_post_generation_hard_replacements(raw_title)
    body, body_replacements = _apply_post_generation_hard_replacements(raw_body)
    post_replacements = title_replacements + body_replacements
    issues = _local_issues(title, body)
    quality_notes = _quality_notes(title, body)
    return {
        "item_no": item_no,
        "seed": seed,
        "title": title,
        "body": body,
        "raw_title": raw_title,
        "raw_body": raw_body,
        "raw": raw,
        "error": error,
        "generated": bool(title or body),
        "machine_pass": bool((title or body) and not issues),
        "human_business_usable": bool((title or body) and not issues),
        "issues": issues,
        "quality_notes": quality_notes,
        "post_generation_hard_replacements": post_replacements,
        "rendered_prompt": prompt,
    }


def _load_model_config(database_url: str | None, model_override: str | None) -> ModelConfig:
    try:
        conn = _connect(database_url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select api_key, base_url, default_model, timeout
                    from llm_provider_config
                    where enabled=1 and is_deleted=0 and api_key is not null and api_key <> ''
                    order by priority desc, id asc
                    limit 1
                    """
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row:
            return ModelConfig(
                api_key=row["api_key"],
                base_url=row["base_url"],
                model=model_override or row.get("default_model") or "deepseek-v4-flash",
                timeout=int(row.get("timeout") or 120),
            )
    except Exception:
        pass

    api_key = os.getenv("AIHUBMIX_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("missing LLM api key")
    return ModelConfig(
        api_key=api_key,
        base_url=os.getenv("AIHUBMIX_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://aihubmix.com/v1",
        model=model_override or "deepseek-v4-flash",
    )


def _connect(database_url: str | None) -> pymysql.Connection:
    cfg = _parse_db_url(database_url)
    return pymysql.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        charset="utf8mb4",
        connect_timeout=5,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _parse_db_url(database_url: str | None) -> dict[str, Any]:
    raw = str(database_url or "").strip()
    if raw:
        if raw.startswith("mysql+"):
            raw = "mysql://" + raw.split("://", 1)[1]
        parsed = urlparse(raw)
        return {
            "host": parsed.hostname or "127.0.0.1",
            "port": int(parsed.port or 3306),
            "user": unquote(parsed.username or "maga"),
            "password": unquote(parsed.password or "maga123456"),
            "database": (parsed.path or "/maga").lstrip("/") or "maga",
        }
    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "maga"),
        "password": os.getenv("MYSQL_PASSWORD", "maga123456"),
        "database": os.getenv("MYSQL_DATABASE", "maga"),
    }


def _call_json_with_retry(config: ModelConfig, *, system: str, user: str, max_tokens: int, temperature: float) -> dict[str, Any]:
    try:
        return _call_json(config, system=system, user=user, max_tokens=max_tokens, temperature=temperature)
    except Exception:
        retry = (
            f"{user}\n\n上一版不是合法 JSON 或字段不对。只输出一个 JSON object，"
            "字段只能是 title 和 body，不要 Markdown，不要解释。"
        )
        return _call_json(config, system=system, user=retry, max_tokens=max_tokens + 300, temperature=0.35)


def _call_json(config: ModelConfig, *, system: str, user: str, max_tokens: int, temperature: float) -> dict[str, Any]:
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=config.timeout) as client:
        response = client.post(
            _chat_url(config.base_url),
            headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return _parse_json_object(content)


def _chat_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("model response is not a JSON object")
    return value


def _local_issues(title: str, body: str) -> list[str]:
    text = f"{title}\n{body}"
    issues: list[str] = []
    if not title:
        issues.append("empty_title")
    if not body:
        issues.append("empty_body")
    if "旺玥" not in text:
        issues.append("missing_wangyue")
    if _title_len(title) > 20:
        issues.append("title_over_20")
    forbidden_check_text = _mask_allowed_proprietary_terms(text)
    if hits := [term for term in FORBIDDEN_TERMS if term in forbidden_check_text]:
        issues.append("forbidden:" + ",".join(hits))
    if hits := [term for term in FORM_RISK_TERMS if term in text]:
        issues.append("product_form_or_action:" + ",".join(hits))
    if _pattern_hits(text, WRONG_STAGE_PATTERNS):
        issues.append("wrong_product_stage")
    if _pattern_hits(text, LOW_AGE_PATTERNS):
        issues.append("low_age_or_wrong_stage")
    if _pattern_hits(text, CURRENT_TIME_RISK_PATTERNS):
        issues.append("current_time_or_disease_anchor")
    if any(term in text for term in ("医生建议", "治疗", "保证", "立刻见效")):
        issues.append("medical_or_guarantee_claim")
    if _has_subjectless_child_state(body):
        issues.append("missing_child_subject_in_state")
    if len(body) < 80:
        issues.append("too_short_for_review")
    if len(body) > 260:
        issues.append("too_long_for_review")
    return issues


def _has_subjectless_child_state(body: str) -> bool:
    subject_terms = (
        "孩子",
        "娃",
        "他",
        "她",
        "小朋友",
        "小家伙",
        "这位",
        "小子",
        "小丫头",
        "我家的",
        "家里这个",
        "家里这位",
    )
    risky_starts = (
        "以前一到",
        "以前玩",
        "以前活动",
        "以前从外面",
        "以前下午",
        "以前平时",
        "以前出门",
        "之前一到",
        "之前玩",
        "之前活动",
        "之前从外面",
        "之前下午",
        "之前平时",
        "之前出门",
    )
    previous_sentence = ""
    for sentence in re.split(r"[。！？\n]", body):
        sentence = sentence.strip()
        if not sentence:
            continue
        if not sentence.startswith(risky_starts):
            previous_sentence = sentence
            continue
        context = f"{previous_sentence}。{sentence}" if previous_sentence else sentence
        if not any(term in context for term in subject_terms):
            return True
        previous_sentence = sentence
    return False


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    generated = [item for item in items if item.get("generated")]
    machine_pass = [item["item_no"] for item in generated if item.get("machine_pass")]
    needs_fix = [item["item_no"] for item in generated if not item.get("machine_pass")]
    human_usable = [item["item_no"] for item in generated if item.get("human_business_usable")]
    return {
        "total_count": len(items),
        "generated_count": len(generated),
        "failed_count": len(items) - len(generated),
        "direct_pass_count": len(machine_pass),
        "direct_pass_items": machine_pass,
        "post_rewrite_pass_count": 0,
        "post_rewrite_pass_items": [],
        "machine_final_pass_count": len(machine_pass),
        "machine_final_pass_items": machine_pass,
        "machine_needs_fix_count": len(needs_fix),
        "machine_needs_fix_items": needs_fix,
        "human_business_usable_count": len(human_usable),
        "human_business_usable_items": human_usable,
        "human_business_unusable_or_needs_fix_count": len(needs_fix),
        "human_business_unusable_or_needs_fix_items": needs_fix,
        "max_pairwise_similarity": _max_pairwise_jaccard([item.get("body") or "" for item in generated]),
        "closure_warning_count": _count_closure_warnings(generated),
        "forbidden_issue_count": sum(1 for item in generated for issue in item.get("issues", []) if issue.startswith("forbidden:")),
        "phrase_guard_issue_count": sum(len(item.get("issues") or []) for item in generated),
        "post_generation_hard_replacement_count": sum(len(item.get("post_generation_hard_replacements") or []) for item in generated),
        "post_generation_hard_replacement_items": [item["item_no"] for item in generated if item.get("post_generation_hard_replacements")],
        "ending_phrase_counts": _ending_phrase_counts(generated),
        "quality_note_total_count": sum(len(item.get("quality_notes") or []) for item in generated),
        "quality_note_items": [item["item_no"] for item in generated if item.get("quality_notes")],
        "quality_note_item_count": sum(1 for item in generated if item.get("quality_notes")),
        "quality_note_counts": _quality_note_counts(generated),
        "llm_review_issue_count": 0,
        "ai_flavor_issue_count": 0,
    }


def _write_preview(path: Path, response_path: Path, prompt_path: Path, response: dict[str, Any]) -> None:
    summary = response["report"]["summary"]
    lines = [
        "# v455 frequency-grounded-expansion probe preview",
        "",
        f"- source JSON: `{response_path}`",
        f"- sampled rendered prompt: `{prompt_path}`",
        f"- batch_id: `{response['batch_id']}`",
        f"- batch_code: `{response['batch_code']}`",
        f"- model: `{response['model']}`",
        f"- core label: `{response.get('core_label') or '这篇要写的事'}`",
        f"- selling expression sources: `{', '.join(response.get('selling_expression_sources') or [])}`",
        "",
        "## Metrics",
        "",
        f"- attempted / total: {summary['total_count']}",
        f"- raw generated: {summary['generated_count']}",
        f"- failed: {summary['failed_count']}",
        f"- direct pass without post-rewrite: {summary['direct_pass_count']} -> {summary['direct_pass_items']}",
        f"- pass after post-rewrite: {summary['post_rewrite_pass_count']} -> {summary['post_rewrite_pass_items']}",
        f"- machine final pass: {summary['machine_final_pass_count']} -> {summary['machine_final_pass_items']}",
        f"- machine needs fix: {summary['machine_needs_fix_count']} -> {summary['machine_needs_fix_items']}",
        f"- human/business usable: {summary['human_business_usable_count']} -> {summary['human_business_usable_items']}",
        f"- human/business unusable or needs fix: {summary['human_business_unusable_or_needs_fix_count']} -> {summary['human_business_unusable_or_needs_fix_items']}",
        f"- max pairwise similarity: {summary['max_pairwise_similarity']}",
        f"- closure warnings: {summary['closure_warning_count']}",
        f"- forbidden issue count: {summary['forbidden_issue_count']}",
        f"- phrase guard issue count: {summary['phrase_guard_issue_count']}",
        f"- post-generation hard replacements: {summary['post_generation_hard_replacement_count']} -> {summary['post_generation_hard_replacement_items']}",
        f"- ending phrase counts: `{json.dumps(summary['ending_phrase_counts'], ensure_ascii=False)}`",
        f"- human quality note items: {summary['quality_note_item_count']} -> {summary['quality_note_items']}",
        f"- human quality note total labels: {summary['quality_note_total_count']}",
        f"- human quality note types: `{json.dumps(summary['quality_note_counts'], ensure_ascii=False)}`",
        f"- LLM review issue count: {summary['llm_review_issue_count']}",
        f"- AI flavor / marketing-density issue count: {summary['ai_flavor_issue_count']}",
        "",
        "## First-Principles Assessment",
        "",
        "这批继续验证单条妈妈日记型种草链路：先把生活入口、过去状态、旺玥相关卖点、现在变化和推荐出口合成一件妈妈要写的事，再交给模型扩写。",
        "相对 v454，本版按 evidence table 做降频：正确旧表达保留并新增同机制表达，不好的高频诱导表达直接替换。",
        "注意：machine pass 只代表硬边界通过；human quality notes 会记录可用但仍有优化价值的问题，例如标题偏常规种草、推荐收口偏模板、产品理由太直给。",
        "",
        "## Scope Note",
        "",
        "本轮不新增 Product Reason，也不正式抽多个槽位；只验证基于真人语料机制的扩充/替换能否降低“精神头/状态/喝下来”频次。",
        "下面这些是内容观察点，不应直接沉淀成新槽位，除非后续有足够真人语料可填。",
        "",
    ]
    for slot in response["report"]["candidate_slots"]:
        lines.append(f"- {slot}")
    lines.extend(["", "## Items", ""])

    for item in response["items"]:
        lines.extend([
            f"### {item['item_no']}. {item.get('title') or ''}",
            "",
            f"- machine status: `{'pass' if item.get('machine_pass') else 'needs_fix'}`",
            f"- direct/post route: `direct_only_no_rewrite`",
            f"- human judgment: `{'usable' if item.get('human_business_usable') else 'needs_fix'}`",
            f"- issue summary: `{', '.join(item.get('issues') or []) or 'none'}`",
            f"- quality notes: `{', '.join(item.get('quality_notes') or []) or 'none'}`",
            f"- post-generation hard replacements: `{', '.join(item.get('post_generation_hard_replacements') or []) or 'none'}`",
            f"- seed: `{json.dumps(item.get('seed') or {}, ensure_ascii=False)}`",
            "",
            item.get("body") or "",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _apply_post_generation_hard_replacements(text: str) -> tuple[str, list[str]]:
    replaced = text
    hits: list[str] = []
    for source, target in POST_GENERATION_HARD_REPLACEMENTS.items():
        count = replaced.count(source)
        if not count:
            continue
        replaced = replaced.replace(source, target)
        hits.append(f"{source}->{target} x{count}")
    return replaced, hits


def _quality_notes(title: str, body: str) -> list[str]:
    """Non-blocking human review notes for issues worth tracking in previews."""
    notes: list[str] = []
    text = f"{title}\n{body}"
    tail = body[-48:]
    if any(term in title for term in ("没白选", "没选错", "活力满满", "欣慰", "太惊喜", "省心")):
        notes.append("title_common_selling_tone")
    template_closures = (
        "可以看看旺玥",
        "可以试试旺玥",
        "参考看看",
        "这罐旺玥我会继续买",
        "这罐我会继续买",
        "这罐我肯定回购",
        "同阶段孩子可以看看旺玥",
    )
    if any(term in tail for term in template_closures):
        notes.append("recommendation_common_selling_closure")
    direct_reason_markers = (
        "就是看中",
        "冲着",
        "比较看重",
        "更看重",
        "特别在意",
        "是因为",
        "才选了旺玥",
        "图的就是",
        "更合我心里那个标准",
    )
    if any(term in text for term in direct_reason_markers):
        notes.append("product_reason_direct_but_acceptable")
    return notes


def _quality_note_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        for note in item.get("quality_notes") or []:
            counts[note] = counts.get(note, 0) + 1
    return counts


def _safe_suffix(value: str) -> str:
    suffix = re.sub(r"\W+", "_", value.strip(), flags=re.UNICODE).strip("_")
    return suffix or "variant"


def _ending_phrase_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    text = "\n".join(f"{item.get('title') or ''}\n{item.get('body') or ''}" for item in items)
    terms = [
        "继续买",
        "继续回购",
        "继续囤",
        "继续选",
        "还会买",
        "选对了",
        "选得对",
        "选得不错",
        "挺好",
        "合适",
        "延续",
        "沿用",
        "不会轻易换",
        "换来换去",
    ]
    return {term: text.count(term) for term in terms if text.count(term)}


def _format_prompt_sample(item: dict[str, Any]) -> str:
    return "\n".join([
        "# v455 item1 rendered generation prompt",
        "",
        f"- batch_id: `local_v455`",
        f"- item_no: `{item.get('item_no')}`",
        f"- title: `{item.get('title') or ''}`",
        "",
        "## System",
        "",
        "```text",
        DIARY_CHAIN_SYSTEM,
        "```",
        "",
        "## User",
        "",
        "```text",
        item.get("rendered_prompt") or "",
        "```",
    ])


def _candidate_slots() -> list[str]:
    return [
        "selling_expression：复用旧卖点表达槽位，不新增 Product Reason；进入正文主事前先归一化成可入句短语",
        "inline_core_brief：本轮不是新槽位，而是把可替换描述直接嵌入“这篇要写的事”",
        "state_observation：由 now_change + daily_scene 合并而来，仍是正文主事内部的可替换描述，不作为末尾素材包",
        "ending_observation：只是观察到结尾表达仍重复，暂不作为正式槽位",
    ]


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_generated_text(value: Any) -> str:
    text = _clean_text(value)
    text = _strip_topic_tags(text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_topic_tags(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"#[^\s#，。！？、；;]{1,40}\[话题\]#?", "", text)
    cleaned = re.sub(r"#[^\s#，。！？、；;]{1,40}#", "", cleaned)
    cleaned = re.sub(r"(?:\s*#[^\s#，。！？、；;]{1,40})+\s*$", "", cleaned)
    cleaned = re.sub(r"\[[^\[\]]{1,12}话题[^\[\]]{0,12}\]", "", cleaned)
    return cleaned.strip()


def _mask_allowed_proprietary_terms(text: str) -> str:
    masked = text
    for term, placeholder in ALLOWED_PROPRIETARY_TERMS.items():
        masked = masked.replace(term, placeholder)
    return masked


def _pattern_hits(text: str, patterns: list[str]) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text)]


def _title_len(title: str) -> int:
    total = 0
    for char in title:
        total += 2 if ord(char) > 0xFFFF else 1
    return total


def _max_pairwise_jaccard(texts: list[str]) -> float:
    max_score = 0.0
    token_sets = [_bigrams(text) for text in texts if text]
    for i, left in enumerate(token_sets):
        for right in token_sets[i + 1 :]:
            union = left | right
            if not union:
                continue
            max_score = max(max_score, len(left & right) / len(union))
    return round(max_score, 4)


def _bigrams(text: str) -> set[str]:
    chars = [char for char in re.sub(r"\s+", "", text) if char.strip()]
    return {"".join(chars[i : i + 2]) for i in range(max(0, len(chars) - 1))}


def _count_closure_warnings(items: list[dict[str, Any]]) -> int:
    return sum(
        1
        for item in items
        if any(term in (item.get("body") or "")[-36:] for term in ("安心", "省心", "放心", "踏实", "心里有底"))
    )


if __name__ == "__main__":
    main()
