#!/usr/bin/env python3
"""Local Wangyue orthogonal human-event/product-bridge experiment.

This does not replace the production content.generate path. It tests whether
removing business-row leakage from the human-event planner improves realness.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

import run_v380_wangyue_row18_distributed_variants_batch as helper


SOURCE_ASSET_KEY = "wangyue_v395_targeted_row_tuning_article_rules"
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/0705_wangyue_product_relation_evidence")
EXPERIMENT_ID = "v406_orthogonal_human_event"

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

TITLE_REPAIR_TERMS = ["🍼", "😅", "宝宝", "宝妈"]
SURFACE_ONLY_TERMS = ["🍼", "😅"]

DIRECT_CAUSE_PATTERNS = [
    r"旺玥.{0,12}(让|使|带来|导致|改善|提升)",
    r"(因为|靠|多亏).{0,12}旺玥",
    r"(对眼睛|对脑子|专注提升|起作用|有帮助)",
    r"(对保护力|保护力).{0,8}有帮助",
    r"营养.{0,6}(到位|跟上)",
    r"支持.{0,8}(成长|保护力|精力|活动)",
]

SEASON_ENV_PATTERNS = [
    r"天气变化.{0,12}(没|不|挺|状态|精神|蔫|折腾)",
    r"周围.{0,12}(倒|请假|咳|中招)",
    r"班里.{0,12}(倒|请假|咳|中招)",
]

FIDELITY_PATTERNS: dict[str, list[str]] = {
    "fixed_usage_added": [
        r"每天.{0,8}(一杯|早晚|喝)",
        r"早晚.{0,8}(一杯|喝)",
        r"每天早晚",
        r"早餐奶",
        r"每天.{0,10}(早餐|早上).{0,10}(睡前|晚上)",
        r"(早餐|早上).{0,12}(睡前|晚上)",
        r"睡前.{0,8}(喝|一杯|冲|泡)",
        r"(早上|晚上).{0,8}(固定|都|会).{0,8}(喝|冲|泡)",
        r"每到喝奶时间",
    ],
    "formulaic_closure_added": [
        r"(安心|省心|放心|踏实|心里有底|心安)$",
        r"(继续喝|继续喝着|继续喝下去|回购|续上|常备着|囤着吧|没犹豫)[。～~！!]*$",
        r"(选对了|没选错|挺值|值得)[。～~！!]*$",
    ],
    "marketing_title_tone": [
        r"不慌",
        r"安排上",
        r"选对",
        r"谢旺玥",
        r"救场",
        r"帮我",
        r"基础营养清晰",
        r"宝藏奶粉",
        r"营养要跟上",
    ],
    "new_product_action_added": [
        r"回购",
        r"续上",
        r"囤",
        r"常备",
        r"继续喝",
    ],
    "new_usage_process_added": [
        r"冲好",
        r"泡给",
        r"喝光",
        r"喝完",
        r"自己拿",
        r"自己端",
        r"每次都",
    ],
    "extra_evidence_added": [
        r"睡得香",
        r"睡觉稳",
        r"脸色红润",
        r"胃口.*稳定",
        r"身高体重",
        r"感冒",
        r"拉肚子",
        r"小状况",
    ],
}

PLAN_GATE_PATTERNS: dict[str, list[str]] = {
    "fixed_usage_in_plan": [
        r"每天.{0,10}(一杯|喝|冲|泡|来一杯)",
        r"早晚.{0,10}(一杯|喝|冲|泡)",
        r"加一杯",
        r"固定.{0,8}(喝|安排)",
        r"早餐奶",
        r"每天.{0,10}(早餐|早上).{0,10}(睡前|晚上)",
        r"(早餐|早上).{0,12}(睡前|晚上)",
        r"睡前.{0,8}(喝|一杯|冲|泡)",
        r"(早上|晚上).{0,8}(固定|都|会).{0,8}(喝|冲|泡)",
        r"每到喝奶时间",
    ],
    "direct_benefit_in_plan": [
        r"有帮助",
        r"营养.{0,6}(到位|跟上)",
        r"起作用",
        r"靠它",
        r"支持.{0,8}(成长|保护力|精力|活动)",
        r"满足.{0,8}(成长|活动|营养)",
    ],
    "emotion_shortcut_in_plan": [
        r"安心",
        r"省心",
        r"放心",
        r"踏实",
        r"心里有底",
        r"心安",
    ],
    "product_as_answer_in_plan": [
        r"救场",
        r"不慌",
        r"帮我",
        r"搞定",
        r"解决.{0,8}(问题|困扰|饭菜|营养|挑食|焦虑)",
        r"补上",
        r"兜底",
        r"托底",
        r"保障",
    ],
}

LIFE_THEME_POOL: list[dict[str, str]] = [
    {
        "theme_id": "mom_daily_after_school_chat",
        "source": "v297 妈妈日常机制池：放学路上孩子分享欲很强",
        "life_theme": "放学路上，孩子一路说学校里的小事，妈妈只是边听边记住几个细节。",
        "natural_stop_hint": "停在孩子说的一句话或回家路上的一个小动作。",
    },
    {
        "theme_id": "mom_daily_kitchen_table",
        "source": "v297 妈妈日常机制池：早上/饭桌混乱后收拾",
        "life_theme": "饭桌或厨房刚收拾完，妈妈回想这一顿吃得顺不顺、自己有没有追着催。",
        "natural_stop_hint": "停在收拾碗筷、擦桌子、孩子跑去玩这类生活尾巴。",
    },
    {
        "theme_id": "mom_daily_home_mess",
        "source": "v297 妈妈日常机制池：家里刚收拾好另一边又乱",
        "life_theme": "家里刚收拾好一块地方，另一边又被孩子翻乱，妈妈顺手记录这种日常循环。",
        "natural_stop_hint": "停在一个还没收完的小角落，不做人生总结。",
    },
    {
        "theme_id": "mom_daily_waiting_gate",
        "source": "v297 妈妈日常机制池：幼儿园门口等孩子出来",
        "life_theme": "妈妈在门口等孩子出来，看见孩子排队或小跑过来的样子，突然注意到他这阵子的状态。",
        "natural_stop_hint": "停在牵手回家、孩子继续讲话或路边小事。",
    },
    {
        "theme_id": "mom_daily_morning_rush",
        "source": "v297 妈妈日常机制池：早上赶时间连续做小事",
        "life_theme": "早上赶时间，穿衣、洗漱、早餐、出门挤在一起，妈妈在碎片里注意到孩子的一个小表现。",
        "natural_stop_hint": "停在终于出门、赶上时间或孩子催妈妈快点。",
    },
    {
        "theme_id": "mom_daily_child_sentence",
        "source": "v297 妈妈日常机制池：孩子一句突然的话或要求",
        "life_theme": "孩子突然说了一句话或提出一个小要求，妈妈被逗到或被触动，想顺手记下来。",
        "natural_stop_hint": "停在孩子原话，不拔高。",
    },
    {
        "theme_id": "mom_daily_play_after_school",
        "source": "v297 妈妈日常机制池：放学后还要在附近玩一会儿",
        "life_theme": "放学后孩子还想在附近玩一会儿，妈妈一边看着一边观察他活动后的状态。",
        "natural_stop_hint": "停在孩子还想再玩一会儿，或妈妈准备喊他回家。",
    },
    {
        "theme_id": "mom_daily_room_album",
        "source": "旺玥 v405 验证有效样本：整理房间翻到成长相册",
        "life_theme": "整理房间或相册时翻到一段旧照片，妈妈想起当时自己为孩子做过的一次选择。",
        "natural_stop_hint": "停在把照片放回去、继续收拾或轻轻感慨时间过得快。",
    },
]


@dataclass
class ModelConfig:
    api_key: str
    base_url: str
    model: str
    timeout: int = 120


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL") or None)
    parser.add_argument("--seed", type=int, default=397)
    args = parser.parse_args()

    random.seed(args.seed)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = helper._connect(args.database_url)
    try:
        rows = _load_rows(conn, SOURCE_ASSET_KEY)
        model_config = _load_model_config(conn, args.model)
    finally:
        conn.close()

    selected = rows[: args.count]
    batch_code = f"{EXPERIMENT_ID}_{int(time.time())}"
    response_path = OUTPUT_DIR / f"{EXPERIMENT_ID}_response.json"
    preview_path = OUTPUT_DIR / f"{EXPERIMENT_ID}_preview.md"
    prompt_path = OUTPUT_DIR / f"{EXPERIMENT_ID}_item1_rendered_prompt.md"
    plan_csv_path = OUTPUT_DIR / f"{EXPERIMENT_ID}_plans.csv"

    items: list[dict[str, Any]] = []
    prompt_sample = ""
    fallback_prompt_sample = ""
    for index, row in enumerate(selected, start=1):
        human_event_prompt = _build_human_event_prompt(row, index)
        human_event = _call_json_with_retry(model_config, system=HUMAN_EVENT_SYSTEM, user=human_event_prompt, max_tokens=1200, temperature=0.65)
        bridge_prompt = _build_bridge_prompt(row, human_event, index)
        product_bridge = _call_json_with_retry(model_config, system=PRODUCT_BRIDGE_SYSTEM, user=bridge_prompt, max_tokens=1600, temperature=0.5)
        plan = _merge_event_bridge(human_event, product_bridge)
        plan_valid, plan_issues = _validate_plan(plan)
        if not plan_valid:
            retry_bridge_prompt = (
                f"{bridge_prompt}\n\n上一版产品桥问题：{'; '.join(plan_issues)}\n"
                "请只修产品进入关系，不要重写人类事件；不要出现固定喝法、直接功效、安心省心收口或产品救场逻辑。"
            )
            product_bridge = _call_json_with_retry(
                model_config,
                system=PRODUCT_BRIDGE_SYSTEM,
                user=retry_bridge_prompt,
                max_tokens=1600,
                temperature=0.4,
            )
            plan = _merge_event_bridge(human_event, product_bridge)
            plan_valid, plan_issues = _validate_plan(plan)

        writer_prompt = ""
        if plan_valid:
            writer_prompt = _build_writer_prompt(row, plan, plan_valid=plan_valid, plan_issues=plan_issues)
            article = _call_json_with_retry(model_config, system=WRITER_SYSTEM, user=writer_prompt, max_tokens=1800, temperature=0.75)
            title = _clean_text(article.get("title"))
            body = _clean_text(article.get("body"))
            surface = _surface_guard(title, body)
            title = surface["title"]
            quality = _local_quality(title, body, plan)
            fidelity = _fidelity_gate(title, body, plan)
            coherence = _coherence_review(model_config, plan, title, body)
            quality["flags"].extend(fidelity["flags"])
            quality["flags"].extend(surface["flags"])
            quality["flags"].extend(coherence["flags"])
            quality["forbidden_hits"] = sorted(set(quality["forbidden_hits"]) | set(surface["forbidden_hits"]))
            quality["hard_pass"] = bool(quality["hard_pass"] and fidelity["pass"] and surface["pass"] and coherence["pass"])
            if not fidelity["pass"]:
                quality["business_tier"] = "fidelity_failed"
                quality["business_reason"] = "writer 背叛已审核主线：" + "；".join(fidelity["flags"])
            if not surface["pass"]:
                quality["business_tier"] = "surface_failed"
                quality["business_reason"] = "表面卫生未通过：" + "；".join(surface["flags"])
            if not coherence["pass"]:
                quality["business_tier"] = "storyline_failed"
                quality["business_reason"] = "正文没有沿一条发帖主线推进：" + coherence["reason"]
        else:
            title = ""
            body = ""
            quality = {
                "hard_pass": False,
                "flags": ["plan_gate_failed"],
                "forbidden_hits": [],
                "business_tier": "plan_rejected",
                "business_reason": "主线规划未通过，未进入正文写作",
            }
            fidelity = {"pass": False, "flags": ["plan_gate_failed"]}
            surface = {"pass": False, "flags": ["plan_gate_failed"], "forbidden_hits": [], "title": title, "repaired": False}
            coherence = {"pass": False, "flags": ["plan_gate_failed"], "reason": "主线规划未通过，未写正文"}
        item = {
            "item_no": index,
            "source_row_no": row.get("source_row_no") or row.get("item_no") or index,
            "title": title,
            "body": body,
            "plan": plan,
            "plan_valid": plan_valid,
            "plan_issues": plan_issues,
            "hard_pass": quality["hard_pass"],
            "rewrite_required": not quality["hard_pass"],
            "business_usability_tier": quality["business_tier"],
            "business_usability_reason": quality["business_reason"],
            "quality_flags": quality["flags"],
            "fidelity_pass": fidelity["pass"],
            "fidelity_flags": fidelity["flags"],
            "surface_pass": surface["pass"],
            "surface_flags": surface["flags"],
            "surface_repaired": surface["repaired"],
            "coherence_pass": coherence["pass"],
            "coherence_flags": coherence["flags"],
            "coherence_reason": coherence["reason"],
            "forbidden_hits": quality["forbidden_hits"],
        }
        items.append(item)
        if not fallback_prompt_sample:
            fallback_prompt_sample = _format_prompt_sample(human_event_prompt, bridge_prompt, writer_prompt, human_event, product_bridge, plan)
        if not prompt_sample and writer_prompt:
            prompt_sample = _format_prompt_sample(human_event_prompt, bridge_prompt, writer_prompt, human_event, product_bridge, plan)

    summary = _summary(items)
    response = {
        "experiment_id": EXPERIMENT_ID,
        "batch_id": "local_v406",
        "batch_code": batch_code,
        "source_asset": SOURCE_ASSET_KEY,
        "model": model_config.model,
        "items": items,
        "report": {"summary": summary},
    }
    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    prompt_path.write_text(prompt_sample or fallback_prompt_sample, encoding="utf-8")
    _write_plan_csv(plan_csv_path, items)
    _write_preview(preview_path, response_path, prompt_path, plan_csv_path, response)

    print(json.dumps({
        "response_path": str(response_path),
        "preview_path": str(preview_path),
        "prompt_path": str(prompt_path),
        "plan_csv_path": str(plan_csv_path),
        "summary": summary,
    }, ensure_ascii=False, indent=2))


def _load_rows(conn, asset_key: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select content_json
            from asset_registry
            where asset_key=%s and asset_stage='production' and status='active'
            order by version_no desc, id desc
            limit 1
            """,
            (asset_key,),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError(f"missing active asset: {asset_key}")
    content = helper._json_value(row["content_json"])
    items = [item for item in content.get("items") or [] if isinstance(item, dict)]
    return sorted(items, key=lambda item: int(item.get("source_row_no") or item.get("item_no") or 0))


def _load_model_config(conn, model_override: str | None) -> ModelConfig:
    with conn.cursor() as cur:
        cur.execute(
            """
            select provider_code, api_key, base_url, default_model, timeout
            from llm_provider_config
            where enabled=1 and is_deleted=0 and api_key is not null and api_key <> ''
            order by priority desc, id asc
            limit 1
            """
        )
        provider = cur.fetchone()
    if provider:
        return ModelConfig(
            api_key=provider["api_key"],
            base_url=provider["base_url"],
            model=model_override or provider.get("default_model") or "deepseek-v4-flash",
            timeout=int(provider.get("timeout") or 120),
        )
    api_key = os.getenv("AIHUBMIX_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("missing LLM api key")
    return ModelConfig(
        api_key=api_key,
        base_url=os.getenv("AIHUBMIX_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://aihubmix.com/v1",
        model=model_override or "deepseek-v4-flash",
    )


def _chat_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _call_json(config: ModelConfig, *, system: str, user: str, max_tokens: int, temperature: float) -> dict[str, Any]:
    payload = {
        "model": config.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
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
    raw = response.json()["choices"][0]["message"]["content"]
    return _parse_json_object(raw)


def _call_json_with_retry(config: ModelConfig, *, system: str, user: str, max_tokens: int, temperature: float) -> dict[str, Any]:
    try:
        return _call_json(config, system=system, user=user, max_tokens=max_tokens, temperature=temperature)
    except Exception:
        retry_user = (
            f"{user}\n\n上一次输出不是合法 JSON。请重新输出，必须是一个完整 JSON object，"
            "不要 Markdown，不要解释，不要省略字段。"
        )
        return _call_json(
            config,
            system=system,
            user=retry_user,
            max_tokens=max_tokens + 400,
            temperature=min(temperature, 0.3),
        )


HUMAN_EVENT_SYSTEM = """你是小红书母婴UGC的人类事件规划器。
你不写正文，也不写产品。
目标是：先规划一个没有旺玥、没有奶粉、没有成分、没有卖点也能成立的妈妈发帖冲动。
输出 JSON，字段只能是：
posting_motive, human_event, emotional_impulse, life_entry, natural_stop, no_product_post, avoid_links, self_check。
要求：
- 不出现旺玥、奶粉、配方、成分、卖点、喝法、补货。
- 用“孩子”或“娃”，不要用“宝宝/宝妈”。
- human_event 写一个具体生活事件，不要写成商业 brief。
- no_product_post 写如果完全不提产品，这条帖子为什么仍然像妈妈会发。
- 不写换季、流感、春游、秋游、公共疾病环境或当前季节。
"""


PRODUCT_BRIDGE_SYSTEM = """你是小红书母婴UGC的产品进入桥规划器。
你只基于 approved_human_event 判断旺玥有没有进入资格。
输出 JSON，字段只能是：
product_permission, bridge_logic, product_role, single_selling_point, positive_evidence, ending_stop, avoid_links, self_check。
要求：
- product_permission 可以是 false；如果旺玥进入会显得强插，就直接 false。
- 不重写 approved_human_event，不新增第二个生活入口。
- 旺玥只能作为这个人类事件里的一个解释因素或日常安排，不是答案、救场、兜底或解决方案。
- 强种草可以正面，但产品价值必须顺着 human_event 进入。
- 成分可以出现，但不要直接写成导致孩子变化的原因。
- 不规划固定喝法，例如每天一杯、早晚一杯、加一杯、早餐奶、睡前喝。
- 不写瓶装、盒装、小包、便携装、随身带；旺玥按儿童奶粉语境处理。
- 不用安心、省心、放心、踏实、心里有底当结尾逻辑。
- 不写换季、流感、春游、秋游、公共疾病环境或当前季节。
"""


WRITER_SYSTEM = """你是小红书妈妈UGC写手。
你只能根据给定主线写标题和正文，不重新规划新事实。
输出 JSON，字段只能是 title 和 body。
写法要求：
- 正文先服务 approved_story_plan.storyline；每句话都要能接上这条主线。
- approved_story_plan.human_event 是生活主线，approved_story_plan.product_bridge 只是产品进入方式。
- 正文自然出现旺玥，产品价值要写到位，但不要把 source_row 里的素材逐项覆盖。
- 像妈妈顺手发帖，不像广告 brief。
- 允许具体生活细节，但只能服务同一条主线。
- 如果生活入口、被问起、产品理由、效果观察放在一起不顺，就删掉其中一个，不要硬拼。
- 不写禁词，不写当前季节/公共疾病大环境。
- 不写孩子自己泡奶粉、奶瓶、便携袋、水杯侧袋。
- 不写奶粉小包、放一包、便携装、条装、随身带这些产品形态。
- 标题不超过20字，emoji算2字。
- 不要把主线没有写的固定喝法、回购、继续喝、安心省心总结、第二个效果证明补进去。
- 标题不要使用奶瓶、奶粉、哭笑等符号；如果没有必要，标题不加 emoji。
"""


def _build_human_event_prompt(row: dict[str, Any], index: int) -> str:
    theme = LIFE_THEME_POOL[(index - 1) % len(LIFE_THEME_POOL)]
    payload = {
        "item_index": index,
        "child_context": "3-6岁学龄前孩子；不要写低龄、断奶、辅食或三段场景。",
        "life_theme": theme,
        "input_boundary": (
            "本阶段不接收产品、卖点、痛点、成分或种草任务。"
            "只生成一个不提产品也成立的妈妈发帖事件。"
        ),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_bridge_prompt(row: dict[str, Any], human_event: dict[str, Any], index: int) -> str:
    payload = {
        "source_row": _row_payload(row, index),
        "approved_human_event": human_event,
        "bridge_task": "只判断旺玥如何进入这个人类事件；不要重写人类事件，不要把产品写成答案。",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _merge_event_bridge(human_event: dict[str, Any], product_bridge: dict[str, Any]) -> dict[str, Any]:
    storyline = (
        f"{human_event.get('human_event') or human_event.get('posting_motive') or ''}"
        f" -> {product_bridge.get('bridge_logic') or product_bridge.get('product_permission') or ''}"
        f" -> {product_bridge.get('ending_stop') or human_event.get('natural_stop') or ''}"
    )
    return {
        "human_event": human_event,
        "product_bridge": product_bridge,
        "posting_motive": human_event.get("posting_motive") or human_event.get("emotional_impulse"),
        "storyline": storyline,
        "life_entry": human_event.get("life_entry") or human_event.get("human_event"),
        "product_permission": product_bridge.get("product_permission"),
        "product_role": product_bridge.get("product_role"),
        "single_selling_point": product_bridge.get("single_selling_point"),
        "positive_evidence": product_bridge.get("positive_evidence"),
        "ending_stop": product_bridge.get("ending_stop") or human_event.get("natural_stop"),
        "avoid_links": product_bridge.get("avoid_links") or human_event.get("avoid_links"),
        "self_check": {
            "human_event_check": human_event.get("self_check"),
            "product_bridge_check": product_bridge.get("self_check"),
        },
    }


def _build_writer_prompt(row: dict[str, Any], plan: dict[str, Any], *, plan_valid: bool, plan_issues: list[str]) -> str:
    payload = {
        "product_fact": "旺玥是给3岁以上孩子的儿童奶粉；不要写成低龄、断奶、辅食或三段场景。",
        "source_row_no": row.get("source_row_no") or row.get("item_no"),
        "approved_story_plan": plan,
        "plan_gate": {"valid": plan_valid, "issues": plan_issues},
        "storyline_contract": "approved_story_plan.storyline 是唯一主线；不要额外补齐选择过程、使用动作、第二个效果证明或广告式收口。",
        "writer_task": "把 approved_story_plan 写成一篇 120-180 字左右的小红书妈妈UGC正向种草笔记。",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _row_payload(row: dict[str, Any], index: int) -> dict[str, Any]:
    keys = [
        "source_row_no",
        "post_type",
        "painpoint",
        "selling_point",
        "selling_description",
        "story_spine",
        "corpus",
        "scene_motive_bucket",
    ]
    payload = {key: row.get(key) for key in keys if row.get(key)}
    payload["item_index"] = index
    return payload


def _validate_plan(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    human_event = plan.get("human_event") or {}
    product_bridge = plan.get("product_bridge") or {}
    product_bridge_text = json.dumps({
        key: product_bridge.get(key)
        for key in (
            "bridge_logic",
            "product_role",
            "single_selling_point",
            "positive_evidence",
            "ending_stop",
        )
    }, ensure_ascii=False)
    human_event_text = json.dumps({
        key: human_event.get(key)
        for key in (
            "posting_motive",
            "human_event",
            "emotional_impulse",
            "life_entry",
            "natural_stop",
            "no_product_post",
        )
    }, ensure_ascii=False)
    story_text = json.dumps({
        key: plan.get(key)
        for key in (
            "posting_motive",
            "storyline",
            "life_entry",
            "product_permission",
            "product_role",
            "single_selling_point",
            "positive_evidence",
            "ending_stop",
        )
    }, ensure_ascii=False)
    issues: list[str] = []
    required = [
        "posting_motive",
        "storyline",
        "life_entry",
        "product_permission",
        "product_role",
        "single_selling_point",
        "positive_evidence",
        "ending_stop",
        "avoid_links",
    ]
    for key in required:
        if not str(plan.get(key) or "").strip():
            issues.append(f"missing:{key}")
    if not _permission_true(plan.get("product_permission")):
        issues.append("product_permission_false")
    human_product_hits = _hits(human_event_text, ["旺玥", "奶粉", "配方", "成分", "乳铁蛋白", "HMO", "钙铁锌", "DHA", "燕窝酸", "补货", "喝奶"])
    if human_product_hits:
        issues.append(f"human_event_contains_product:{','.join(human_product_hits)}")
    if hits := _hits(story_text, FORBIDDEN_TERMS):
        issues.append(f"forbidden:{','.join(hits)}")
    if _pattern_hits(story_text, DIRECT_CAUSE_PATTERNS):
        issues.append("direct_causality")
    if _pattern_hits(story_text, SEASON_ENV_PATTERNS):
        issues.append("season_or_environment_anchor")
    if any(word in product_bridge_text for word in ("安心", "省心", "放心", "心里有底", "心安")):
        issues.append("closure_shortcut")
    for flag, patterns in PLAN_GATE_PATTERNS.items():
        hits = _pattern_hits(story_text, patterns)
        if not hits:
            continue
        if flag == "product_as_answer_in_plan" and _only_negated_product_answer(story_text, hits):
            continue
        issues.append(flag)
    return not issues, issues


def _local_quality(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    text = f"{title}\n{body}"
    flags: list[str] = []
    forbidden_hits = _hits(text, FORBIDDEN_TERMS)
    if forbidden_hits:
        flags.append("forbidden")
    if "旺玥" not in text:
        flags.append("missing_product")
    if len(title) > 20:
        flags.append("title_too_long")
    if _pattern_hits(text, DIRECT_CAUSE_PATTERNS):
        flags.append("direct_causality")
    if _pattern_hits(text, SEASON_ENV_PATTERNS):
        flags.append("season_or_environment_anchor")
    if any(word in text[-36:] for word in ("安心", "省心", "放心", "踏实", "心里有底")):
        flags.append("formulaic_closure")
    if any(word in text for word in ("奶瓶", "自己泡", "书包侧袋", "水杯侧袋", "便携", "一包", "一瓶旺玥", "一盒旺玥", "小包", "条装", "随身带")):
        flags.append("product_action_or_carrier_risk")
    hard_pass = not flags
    return {
        "hard_pass": hard_pass,
        "flags": flags,
        "forbidden_hits": forbidden_hits,
        "business_tier": "direct_pool" if hard_pass else "needs_manual_review",
        "business_reason": "本地架构实验粗审通过" if hard_pass else "；".join(flags),
    }


def _surface_guard(title: str, body: str) -> dict[str, Any]:
    repaired_title = title
    repaired = False
    for term in TITLE_REPAIR_TERMS:
        if term in repaired_title:
            repaired_title = repaired_title.replace(term, "")
            repaired = True
    repaired_title = re.sub(r"\s{2,}", " ", repaired_title).strip(" ｜|·-—_")
    flags: list[str] = []
    text = f"{repaired_title}\n{body}"
    forbidden_hits = _hits(text, FORBIDDEN_TERMS)
    body_forbidden = _hits(body, FORBIDDEN_TERMS)
    title_forbidden = _hits(repaired_title, FORBIDDEN_TERMS)
    if body_forbidden:
        flags.append("body_forbidden_term")
    if title_forbidden:
        flags.append("title_forbidden_term")
    if len(repaired_title) > 20:
        flags.append("title_too_long")
    if not repaired_title:
        flags.append("empty_title_after_repair")
    if any(term in body for term in ("换季", "流感", "春游", "秋游")):
        flags.append("season_surface_term")
    if any(term in body for term in ("一包", "一瓶旺玥", "一盒旺玥", "小包", "条装", "便携装", "随身带")):
        flags.append("product_form_surface_risk")
    return {
        "pass": not flags,
        "flags": flags,
        "forbidden_hits": forbidden_hits,
        "title": repaired_title,
        "repaired": repaired,
    }


def _fidelity_gate(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    plan_story = _plan_story_text(plan)
    text = f"{title}\n{body}"
    closing = body[-40:]
    flags: list[str] = []

    for flag, patterns in FIDELITY_PATTERNS.items():
        target = title if flag == "marketing_title_tone" else text
        if flag == "formulaic_closure_added":
            target = closing
        hits = _pattern_hits(target, patterns)
        if not hits:
            continue
        if _pattern_hits(plan_story, patterns):
            continue
        flags.append(flag)

    emotion_patterns = [r"安心", r"省心", r"放心", r"踏实", r"心里有底", r"心安"]
    if _pattern_hits(text, emotion_patterns) and not _pattern_hits(plan_story, emotion_patterns):
        flags.append("emotion_shortcut_added")

    reason_count = _count_any(text, ["乳铁蛋白", "HMO", "钙铁锌", "DHA", "燕窝酸", "关键营养", "基础营养", "维生素"])
    if reason_count >= 4:
        flags.append("too_many_product_reasons")

    if _count_any(text, ["吃饭", "睡", "精神", "胃口", "身高", "脸色", "请假", "感冒", "拼图", "专注", "长高"]) >= 4:
        flags.append("too_many_evidence_points")

    return {"pass": not flags, "flags": flags}


COHERENCE_REVIEW_SYSTEM = """你是小红书母婴UGC的主线一致性审核员。
你只判断正文是否沿 approved_story_plan.storyline 自然推进。
不要审核禁词、合规、标题长度或营销强弱。
输出 JSON，字段只能是 pass, flags, reason。
审核标准：
- pass=true：正文像一个妈妈因为一个生活触发想发这条，旺玥和正向观察都顺着同一条主线出现。
- pass=false：正文把多个入口并列堆起来，例如生活入口、被问起、产品理由、效果证明各说各的；或者产品突然跳进来；或者结尾和开头不是同一件事。
- 如果只是强种草、正面表达、效果证明较明显，但主线仍然顺，不能判 false。
flags 从以下选择，可多选：slot_stacking, product_jump, motive_break, ending_break, source_row_dump, other。
"""


def _coherence_review(config: ModelConfig, plan: dict[str, Any], title: str, body: str) -> dict[str, Any]:
    payload = {
        "approved_story_plan": plan,
        "title": title,
        "body": body,
        "review_task": "只判断正文是不是由 approved_story_plan.storyline 推出来；不要因为强种草或正面效果证明而判失败。",
    }
    try:
        result = _call_json_with_retry(
            config,
            system=COHERENCE_REVIEW_SYSTEM,
            user=json.dumps(payload, ensure_ascii=False, indent=2),
            max_tokens=800,
            temperature=0.1,
        )
    except Exception as exc:  # noqa: BLE001 - local experiment should keep evidence instead of crashing the batch.
        return {"pass": False, "flags": ["coherence_review_error"], "reason": str(exc)}

    flags = result.get("flags") or []
    if isinstance(flags, str):
        flags = [flags]
    flags = [str(flag) for flag in flags if str(flag).strip()]
    review_pass = bool(result.get("pass"))
    reason = str(result.get("reason") or "").strip()
    return {"pass": review_pass, "flags": flags, "reason": reason}


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    generated = [item for item in items if item.get("body")]
    hard_pass = [item["item_no"] for item in generated if item.get("hard_pass")]
    rewrite = [item["item_no"] for item in generated if not item.get("hard_pass")]
    plan_valid = [item["item_no"] for item in generated if item.get("plan_valid")]
    plan_rejected = [item["item_no"] for item in items if not item.get("plan_valid")]
    fidelity_pass = [item["item_no"] for item in generated if item.get("fidelity_pass")]
    fidelity_fail = [item["item_no"] for item in generated if not item.get("fidelity_pass")]
    surface_pass = [item["item_no"] for item in generated if item.get("surface_pass")]
    surface_fail = [item["item_no"] for item in generated if not item.get("surface_pass")]
    surface_repaired = [item["item_no"] for item in generated if item.get("surface_repaired")]
    coherence_pass = [item["item_no"] for item in generated if item.get("coherence_pass")]
    coherence_fail = [item["item_no"] for item in generated if not item.get("coherence_pass")]
    return {
        "total_count": len(items),
        "generated_count": len(generated),
        "failed_count": len(items) - len(generated),
        "machine_final_pass_count": len(hard_pass),
        "machine_final_pass_items": hard_pass,
        "machine_needs_review_count": len(rewrite),
        "machine_needs_review_items": rewrite,
        "plan_valid_count": len(plan_valid),
        "plan_valid_items": plan_valid,
        "plan_rejected_count": len(plan_rejected),
        "plan_rejected_items": plan_rejected,
        "fidelity_pass_count": len(fidelity_pass),
        "fidelity_pass_items": fidelity_pass,
        "fidelity_fail_count": len(fidelity_fail),
        "fidelity_fail_items": fidelity_fail,
        "surface_pass_count": len(surface_pass),
        "surface_pass_items": surface_pass,
        "surface_fail_count": len(surface_fail),
        "surface_fail_items": surface_fail,
        "surface_repaired_count": len(surface_repaired),
        "surface_repaired_items": surface_repaired,
        "coherence_pass_count": len(coherence_pass),
        "coherence_pass_items": coherence_pass,
        "coherence_fail_count": len(coherence_fail),
        "coherence_fail_items": coherence_fail,
        "max_pairwise_jaccard_2gram": _max_pairwise_jaccard([item.get("body") or "" for item in generated]),
        "closure_hit_count": _closure_hit_count(generated),
        "forbidden_hit_count": sum(len(item.get("forbidden_hits") or []) for item in generated),
        "business_usability_stats": {
            "counts": {
                "direct_pool": len(hard_pass),
                "needs_manual_review": len(rewrite),
                "fidelity_failed": sum(1 for item in generated if item.get("business_usability_tier") == "fidelity_failed"),
                "surface_failed": sum(1 for item in generated if item.get("business_usability_tier") == "surface_failed"),
                "storyline_failed": sum(1 for item in generated if item.get("business_usability_tier") == "storyline_failed"),
            },
            "item_nos_by_tier": {
                "direct_pool": hard_pass,
                "needs_manual_review": rewrite,
            },
        },
    }


def _write_plan_csv(path: Path, items: list[dict[str, Any]]) -> None:
    fields = [
        "item_no",
        "source_row_no",
        "plan_valid",
        "plan_issues",
        "posting_motive",
        "human_event",
        "bridge_logic",
        "storyline",
        "life_entry",
        "product_permission",
        "product_role",
        "single_selling_point",
        "positive_evidence",
        "ending_stop",
        "title",
        "body",
        "quality_flags",
        "fidelity_pass",
        "fidelity_flags",
        "surface_pass",
        "surface_flags",
        "surface_repaired",
        "coherence_pass",
        "coherence_flags",
        "coherence_reason",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for item in items:
            plan = item.get("plan") or {}
            writer.writerow({
                "item_no": item.get("item_no"),
                "source_row_no": item.get("source_row_no"),
                "plan_valid": item.get("plan_valid"),
                "plan_issues": ",".join(item.get("plan_issues") or []),
                "posting_motive": plan.get("posting_motive"),
                "human_event": (plan.get("human_event") or {}).get("human_event"),
                "bridge_logic": (plan.get("product_bridge") or {}).get("bridge_logic"),
                "storyline": plan.get("storyline"),
                "life_entry": plan.get("life_entry"),
                "product_permission": plan.get("product_permission"),
                "product_role": plan.get("product_role"),
                "single_selling_point": plan.get("single_selling_point"),
                "positive_evidence": plan.get("positive_evidence"),
                "ending_stop": plan.get("ending_stop"),
                "title": item.get("title"),
                "body": item.get("body"),
                "quality_flags": ",".join(item.get("quality_flags") or []),
                "fidelity_pass": item.get("fidelity_pass"),
                "fidelity_flags": ",".join(item.get("fidelity_flags") or []),
                "surface_pass": item.get("surface_pass"),
                "surface_flags": ",".join(item.get("surface_flags") or []),
                "surface_repaired": item.get("surface_repaired"),
                "coherence_pass": item.get("coherence_pass"),
                "coherence_flags": ",".join(item.get("coherence_flags") or []),
                "coherence_reason": item.get("coherence_reason"),
            })


def _write_preview(path: Path, response_path: Path, prompt_path: Path, plan_csv_path: Path, response: dict[str, Any]) -> None:
    summary = response["report"]["summary"]
    lines = [
        "# v406 orthogonal human-event architecture experiment preview",
        "",
        f"- source JSON: `{response_path}`",
        f"- sampled rendered prompt: `{prompt_path}`",
        f"- plan CSV: `{plan_csv_path}`",
        f"- source asset: `{response['source_asset']}`",
        f"- batch_id: `{response['batch_id']}`",
        f"- batch_code: `{response['batch_code']}`",
        "",
        "## Metrics",
        "",
        f"- total count: {summary['total_count']}",
        f"- generated count: {summary['generated_count']}",
        f"- failed count: {summary['failed_count']}",
        f"- local machine pass: {summary['machine_final_pass_count']} / {summary['generated_count']} -> {summary['machine_final_pass_items']}",
        f"- local needs review: {summary['machine_needs_review_count']} -> {summary['machine_needs_review_items']}",
        f"- plan valid: {summary['plan_valid_count']} / {summary['generated_count']} -> {summary['plan_valid_items']}",
        f"- plan rejected: {summary['plan_rejected_count']} -> {summary['plan_rejected_items']}",
        f"- fidelity pass: {summary['fidelity_pass_count']} / {summary['generated_count']} -> {summary['fidelity_pass_items']}",
        f"- fidelity fail: {summary['fidelity_fail_count']} -> {summary['fidelity_fail_items']}",
        f"- surface pass: {summary['surface_pass_count']} / {summary['generated_count']} -> {summary['surface_pass_items']}",
        f"- surface fail: {summary['surface_fail_count']} -> {summary['surface_fail_items']}",
        f"- surface repaired: {summary['surface_repaired_count']} -> {summary['surface_repaired_items']}",
        f"- storyline coherence pass: {summary['coherence_pass_count']} / {summary['generated_count']} -> {summary['coherence_pass_items']}",
        f"- storyline coherence fail: {summary['coherence_fail_count']} -> {summary['coherence_fail_items']}",
        f"- max pairwise similarity: {summary['max_pairwise_jaccard_2gram']}",
        f"- forbidden hit count: {summary['forbidden_hit_count']}",
        f"- closure hit count: {summary['closure_hit_count']}",
        "",
        "## First-Principles Assessment",
        "",
        "这一版验证架构假设：human_event 只吃生活主题，不吃业务 row；product_bridge 才接收旺玥卖点和痛点。",
        "本地粗审不是生产审核，重点看 human_event 是否真正无产品、product_bridge 是否有进入资格、writer 是否又补完整广告链。",
        "",
        "## Items",
        "",
    ]
    for item in response["items"]:
        plan = item.get("plan") or {}
        lines.extend([
            f"### {item['item_no']}. {item.get('title') or ''}",
            "",
            f"- source_row_no: `{item.get('source_row_no')}`",
            f"- plan valid: `{item.get('plan_valid')}`; issues: `{', '.join(item.get('plan_issues') or [])}`",
            f"- local machine pass: `{item.get('hard_pass')}`; flags: `{', '.join(item.get('quality_flags') or [])}`",
            f"- fidelity pass: `{item.get('fidelity_pass')}`; flags: `{', '.join(item.get('fidelity_flags') or [])}`",
            f"- surface pass: `{item.get('surface_pass')}`; flags: `{', '.join(item.get('surface_flags') or [])}`; repaired: `{item.get('surface_repaired')}`",
            f"- storyline coherence pass: `{item.get('coherence_pass')}`; flags: `{', '.join(item.get('coherence_flags') or [])}`",
            f"- storyline coherence reason: {item.get('coherence_reason') or ''}",
            f"- posting motive: {plan.get('posting_motive') or ''}",
            f"- human event: {(plan.get('human_event') or {}).get('human_event') or ''}",
            f"- bridge logic: {(plan.get('product_bridge') or {}).get('bridge_logic') or ''}",
            f"- storyline: {plan.get('storyline') or ''}",
            f"- life entry: {plan.get('life_entry') or ''}",
            f"- product role: {plan.get('product_role') or ''}",
            f"- positive evidence: {plan.get('positive_evidence') or ''}",
            "",
            item.get("body") or "",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _format_prompt_sample(
    human_event_prompt: str,
    bridge_prompt: str,
    writer_prompt: str,
    human_event: dict[str, Any],
    product_bridge: dict[str, Any],
    plan: dict[str, Any],
) -> str:
    return "\n".join([
        "# v406 orthogonal human-event sampled rendered prompt",
        "",
        "## Human Event Planner System",
        "",
        "```text",
        HUMAN_EVENT_SYSTEM,
        "```",
        "",
        "## Human Event Planner User",
        "",
        "```json",
        human_event_prompt,
        "```",
        "",
        "## Human Event Planner Output",
        "",
        "```json",
        json.dumps(human_event, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Product Bridge Planner System",
        "",
        "```text",
        PRODUCT_BRIDGE_SYSTEM,
        "```",
        "",
        "## Product Bridge Planner User",
        "",
        "```json",
        bridge_prompt,
        "```",
        "",
        "## Product Bridge Planner Output",
        "",
        "```json",
        json.dumps(product_bridge, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Approved Story Plan",
        "",
        "```json",
        json.dumps(plan, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Writer System",
        "",
        "```text",
        WRITER_SYSTEM,
        "```",
        "",
        "## Writer User",
        "",
        "```json",
        writer_prompt,
        "```",
        "",
        "## Coherence Review System",
        "",
        "```text",
        COHERENCE_REVIEW_SYSTEM,
        "```",
        "",
    ])


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


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term and term in text]


def _pattern_hits(text: str, patterns: list[str]) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text)]


def _only_negated_product_answer(text: str, hits: list[str]) -> bool:
    for pattern in hits:
        for match in re.finditer(pattern, text):
            start = max(0, match.start() - 8)
            prefix = text[start:match.start()]
            if not any(neg in prefix for neg in ("不是", "不要", "不写", "不能", "不把")):
                return False
    return bool(hits)


def _permission_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"true", "yes", "allowed", "allow", "可以", "可进入", "有资格"}


def _plan_story_text(plan: dict[str, Any]) -> str:
    return json.dumps({
        key: plan.get(key)
        for key in (
            "posting_motive",
            "storyline",
            "life_entry",
            "product_permission",
            "product_role",
            "single_selling_point",
            "positive_evidence",
            "ending_stop",
        )
    }, ensure_ascii=False)


def _count_any(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if term in text)


def _max_pairwise_jaccard(bodies: list[str]) -> float:
    max_score = 0.0
    for index, left in enumerate(bodies):
        for right in bodies[index + 1 :]:
            max_score = max(max_score, _jaccard_2gram(left, right))
    return round(max_score, 4)


def _jaccard_2gram(left: str, right: str) -> float:
    def grams(text: str) -> set[str]:
        compact = re.sub(r"\s+", "", text)
        return {compact[i : i + 2] for i in range(max(0, len(compact) - 1))}

    left_set = grams(left)
    right_set = grams(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def _closure_hit_count(items: list[dict[str, Any]]) -> int:
    phrases = ["安心", "省心", "放心", "踏实", "心里有底", "继续喝", "回购", "续上", "没选错", "选对"]
    count = 0
    for item in items:
        closing = (item.get("body") or "")[-40:]
        if any(phrase in closing for phrase in phrases):
            count += 1
    return count


if __name__ == "__main__":
    main()
