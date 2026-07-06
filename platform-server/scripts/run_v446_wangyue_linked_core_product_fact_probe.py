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
EXPERIMENT_ID = "v446_linked_core_product_fact_probe"
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
只按用户给定的一条核心链路写一篇自然种草笔记，不要发明新的文章结构。
输出 JSON object，字段只能是 title 和 body。"""


CORE_PROMPT = """任务：写一篇小红书妈妈UGC正向种草笔记。

核心内容只用这一条，产品事实必须和它绑定：
1. 妈妈晚上有空了，或者在一个很普通的带娃间隙，来小红书记录一下带娃日常。
2. 她想起以前孩子精神经常不太好，玩一会儿就累，从外面回来也容易有点小状况。
3. 这段时间喝旺玥之后，孩子精神头、活动后状态和日常小状态确实变好了。
4. 中间描述一两个孩子现在的日常表现。
5. 结尾说其他有类似困扰的妈妈也可以试试旺玥。

本篇匹配产品事实：
- 旺玥是3岁以上、3-6岁学龄前儿童喝的4段儿童奶粉。
- 本篇只讲“进阶保护力”这一个方向：乳铁蛋白、HMO，承接孩子精神头、活动后状态、外出回来小状态这些变化。
- 不要写钙铁锌、30+营养、DHA、燕窝酸、眼脑、长高、长肉、饭量这些不属于本篇核心的卖点。
- 本篇会给一个“旧卖点表达参考”，这是已有卖点表达槽位的素材，不是新槽位。只借它的保护力表达，不要逐字照抄。

硬边界：
- 不写这些词：🍼、厌奶、体质、肠胃、脾胃、天然、儿保、抵抗力、宝宝、宝妈、自护力、底气、源乳、初乳、换季、流感、春游、秋游、😅。
- 不写3岁以下、三段、奶瓶、便携小包、书包侧袋、水杯侧袋。
- 不写孩子自己泡奶粉、自己冲奶粉、自己舀粉。
- 不写当前季节或当前疾病大环境。
- 不要写成医生建议、治疗、保证有效。
- 不出现“可能、也许、不知道是不是、功劳”这类免责声明式表达；要用妈妈大白话正面说喝下来看到的变化。
- 不写“自护力”这个词，虽然本篇讲的是类似方向；正文用保护力、状态稳、精神头这些妈妈能接受的说法。

写法：
- 标题不超过20字，emoji算2字；标题可以很简单。
- 正文120-180字左右。
- 像妈妈顺手发，不要像广告brief。
- 不要把“生活现场、以前状态、现在变化、产品理由、推荐收尾”写成清单，要让前一句自然推着后一句走。
- 每篇只围绕一个今天的小现场，不要同时塞“朋友问我、买东西顺手、孩子喝奶、对比选择”等多个入口。

本篇随机方向：
{seed_json}
"""


SEEDS = {
    "today_trigger": [
        "晚上终于有空，想来小红书记一下这段时间",
        "晚饭后收拾桌面，看到孩子今天状态还挺在线",
        "孩子从外面回来还在客厅玩，妈妈突然想记录一下",
        "洗杯子时想到这段时间孩子变化挺明显",
        "孩子喝完旺玥又跑去玩，妈妈顺手记一笔",
        "陪孩子玩到晚上，发现他今天精神头还挺足",
        "睡前收拾客厅，想起最近孩子出门回来不太蔫了",
        "带娃回来坐下歇口气，发现孩子还在旁边说个不停",
    ],
    "past_state": [
        "以前孩子精神经常不太够，玩一会儿就喊累",
        "以前从外面回来经常蔫蔫的，还容易有点小状况",
        "以前活动量一大，后半天就不太在线",
        "以前下午精神头掉得快，妈妈总要多盯着",
        "以前出门玩回来就不太想动，状态不算稳",
        "以前看着不差，但精神头总差一口气",
    ],
    "now_change": [
        "这段时间精神头明显更在线",
        "现在从外面回来还能接着玩一会儿",
        "活动后不容易蔫下去，小状态比之前稳",
        "出去玩回来还会叽叽喳喳说个不停",
        "下午那股劲比以前撑得住",
        "日常状态稳了，妈妈肉眼能看出来",
    ],
    "ending": [
        "这罐我会继续买",
        "家里有同阶段孩子的可以试试",
        "至少我家这段时间喝下来挺认可",
        "这罐确实算我买对的一罐",
        "后面应该还会继续喝旺玥",
        "我觉得挺适合3岁后的日常安排",
    ],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL") or None)
    parser.add_argument("--seed", type=int, default=442)
    args = parser.parse_args()

    random.seed(args.seed)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = _load_model_config(args.database_url, args.model)
    selling_expressions = _load_selling_expressions()

    seeds = [_sample_seed(index, selling_expressions) for index in range(1, args.count + 1)]
    batch_code = f"{EXPERIMENT_ID}_{int(time.time())}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = [
            executor.submit(_generate_one, config, item_no, seed)
            for item_no, seed in enumerate(seeds, start=1)
        ]
        items = [future.result() for future in concurrent.futures.as_completed(futures)]
    items.sort(key=lambda item: item["item_no"])

    summary = _summary(items)
    response = {
        "experiment_id": EXPERIMENT_ID,
        "batch_id": "local_v446",
        "batch_code": batch_code,
        "model": config.model,
        "core_chain": "妈妈晚上/带娃间隙记录日常 -> 想起以前孩子精神不好、玩会累、外出回来小状况 -> 这段时间喝旺玥后精神头和活动后状态变好 -> 推荐相似困扰妈妈试试",
        "selling_expression_sources": [str(REAL_UGC_SELLING_PATH), str(STRONG_SELLING_PATH)],
        "items": items,
        "report": {"summary": summary, "candidate_slots": _candidate_slots()},
    }

    response_path = OUTPUT_DIR / f"{EXPERIMENT_ID}_response.json"
    preview_path = OUTPUT_DIR / f"{EXPERIMENT_ID}_preview.md"
    prompt_path = OUTPUT_DIR / f"{EXPERIMENT_ID}_item1_rendered_prompt.md"
    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    prompt_path.write_text(_format_prompt_sample(items[0]), encoding="utf-8")
    _write_preview(preview_path, response_path, prompt_path, response)

    print(json.dumps({
        "response_path": str(response_path),
        "preview_path": str(preview_path),
        "prompt_path": str(prompt_path),
        "summary": summary,
    }, ensure_ascii=False, indent=2))


def _sample_seed(index: int, selling_expressions: list[dict[str, str]]) -> dict[str, str]:
    selling = random.choice(selling_expressions)
    return {
        "item_no": str(index),
        "today_trigger": random.choice(SEEDS["today_trigger"]),
        "past_state": random.choice(SEEDS["past_state"]),
        "now_change": random.choice(SEEDS["now_change"]),
        "selling_point": selling["selling_point"],
        "selling_expression_reference": selling["expression"],
        "selling_expression_source": selling["source"],
        "ending": random.choice(SEEDS["ending"]),
    }


def _load_selling_expressions() -> list[dict[str, str]]:
    expressions: list[dict[str, str]] = []
    if REAL_UGC_SELLING_PATH.exists():
        with REAL_UGC_SELLING_PATH.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                selling_point = _clean_text(row.get("卖点"))
                expression = _clean_text(row.get("卖点表述"))
                if selling_point == "进阶保护力" and _expression_usable(expression):
                    expressions.append({
                        "selling_point": selling_point or "卖点表达",
                        "expression": expression,
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
            if selling_point == "进阶保护力" and _expression_usable(expression) and 8 <= len(expression) <= 90:
                expressions.append({
                    "selling_point": selling_point or "卖点表达",
                    "expression": expression,
                    "source": "卖点表述-已完成.csv",
                })

    if not expressions:
        return [
            {
                "selling_point": "进阶保护力",
                "expression": "乳铁蛋白和HMO这块配置我比较看重，喝下来孩子状态确实更稳",
                "source": "fallback",
            }
        ]
    return expressions


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
    )
    if any(term in expression for term in dirty_terms):
        return False
    if re.search(r"\d{2,}", expression):
        return False
    return True


def _generate_one(config: ModelConfig, item_no: int, seed: dict[str, str]) -> dict[str, Any]:
    prompt = CORE_PROMPT.format(seed_json=json.dumps(seed, ensure_ascii=False, indent=2))
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

    title = _clean_text(raw.get("title"))
    body = _clean_text(raw.get("body"))
    issues = _local_issues(title, body)
    return {
        "item_no": item_no,
        "seed": seed,
        "title": title,
        "body": body,
        "raw": raw,
        "error": error,
        "generated": bool(title or body),
        "machine_pass": bool((title or body) and not issues),
        "human_business_usable": bool((title or body) and not issues),
        "issues": issues,
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
    if hits := [term for term in FORBIDDEN_TERMS if term in text]:
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
    if any(term in text for term in ("可能", "也许", "不知道是不是", "功劳", "大概是", "应该是", "缘故")):
        issues.append("uncertain_or_disclaimer_expression")
    if len(body) < 80:
        issues.append("too_short_for_review")
    if len(body) > 260:
        issues.append("too_long_for_review")
    return issues


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
        "llm_review_issue_count": 0,
        "ai_flavor_issue_count": 0,
    }


def _write_preview(path: Path, response_path: Path, prompt_path: Path, response: dict[str, Any]) -> None:
    summary = response["report"]["summary"]
    lines = [
        "# v446 linked-core-product-fact probe preview",
        "",
        f"- source JSON: `{response_path}`",
        f"- sampled rendered prompt: `{prompt_path}`",
        f"- batch_id: `{response['batch_id']}`",
        f"- batch_code: `{response['batch_code']}`",
        f"- model: `{response['model']}`",
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
        f"- LLM review issue count: {summary['llm_review_issue_count']}",
        f"- AI flavor / marketing-density issue count: {summary['ai_flavor_issue_count']}",
        "",
        "## First-Principles Assessment",
        "",
        "这批验证一个更小的核心：妈妈记录带娃日常，回想以前精神头差/玩会累/外出回来小状况，再写喝旺玥后精神头和活动后状态变好。",
        "本版把核心内容和产品事实绑定：只允许进阶保护力方向，产品事实只给乳铁蛋白/HMO，不再把所有卖点堆进全局产品事实。",
        "",
        "## Scope Note",
        "",
        "本轮不新增 Product Reason，也不正式抽多个槽位；只验证“核心内容 + 匹配产品事实 + 旧卖点表达”能否有机链接。",
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
            f"- seed: `{json.dumps(item.get('seed') or {}, ensure_ascii=False)}`",
            "",
            item.get("body") or "",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _format_prompt_sample(item: dict[str, Any]) -> str:
    return "\n".join([
        "# v446 item1 rendered generation prompt",
        "",
        f"- batch_id: `local_v446`",
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
        "selling_expression：复用旧卖点表达槽位，不新增 Product Reason",
        "linked_product_fact：本轮不是新槽位，而是把核心内容和产品事实写成同一个小核",
        "state_change_observation：只是观察到前后状态表达仍重复，暂不作为正式槽位",
        "ending_observation：只是观察到结尾表达仍重复，暂不作为正式槽位",
    ]


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


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
