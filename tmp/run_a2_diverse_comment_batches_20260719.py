"""Run draft-only A2 comment batches with deterministic expression-path rotation."""
from __future__ import annotations

import argparse
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


BASE_URL = "http://127.0.0.1:3104/api/v1/content-agent/comment-batches/start"
ASSET_KEY = "a2_sentiment_comment_activity"

GENERATION_INSTRUCTION = "生成一条小红书的真实用户评论，口语化，有活人感"

STOCK_PATHS = [
    "直接陈述这件事，结尾带一个自然小感叹。",
    "从顺手看到的日常场景切入，再说反应。",
    "写成一句自然询问，像在回复楼主。",
    "先说个人感受，再落到内容素材。",
    "先说内容素材，再轻轻夸一句。",
    "省略主语，写成评论区随手接的一句。",
    "用一个克制的口语词开头，不要夸张。",
    "不用时间词，直接写反应。",
    "从聊天、群消息或熟人提醒切入。",
    "从门店、页面或小程序里看到的信息切入。",
    "用短句停顿，像边看边说。",
    "写成确认口吻，不质疑内容素材。",
]

FACT_PATHS = [
    "直接陈述这件事，结尾带一个自然小感叹。",
    "写成一句自然询问，像在回复楼主。",
    "先说个人感受，再落到内容素材。",
    "先说内容素材，再轻轻夸一句。",
    "省略主语，写成评论区随手接的一句。",
    "用一个克制的口语词开头，不要夸张。",
    "不用时间词，直接写反应。",
    "用短句停顿，像边看边说。",
    "写成确认口吻，不质疑内容素材。",
    "从能查、看得见或能对应里选一个点来说。",
    "一句话说清事实和反应，不增加经历。",
    "先轻轻肯定，再补一句素材事实。",
]

MEMBER_PATHS = [
    "直接说活动动作，结尾带一个自然小感叹。",
    "写成一句自然询问，像在回复楼主。",
    "先说个人反应，再落到一个权益动作。",
    "先说一个权益动作，再轻轻夸一句。",
    "省略多余背景，写成评论区随手接的一句。",
    "用一个克制的口语词开头，不要夸张。",
    "不用时间词，直接写反应。",
    "用短句停顿，像边看边说。",
    "写成确认口吻，不质疑内容素材。",
    "只说一个礼品或一个活动动作。",
    "一句话说清活动和反应，不增加结果。",
    "像老用户顺手提醒一句，别写成宣传。",
]

WAVE2_PATHS = {
    "有货-直给": [
        "从渠道或地点起句，不用刚、终于。",
        "从消息来源起句，不用刚、终于。",
        "直接用供货状态起句，结尾自然问一句。",
        "用咦、诶、原来等轻口语起句。",
        "从自己现在的反应起句，再说有货。",
        "从生活里的时间场景起句，但不用刚、终于。",
        "先问哪里能买，再确认有货。",
        "用一句报喜口吻，不写购买动作。",
        "从货架或页面更新起句，但不用刚。",
        "从朋友或群消息起句，但不用刚。",
        "用这下、总算或没想到一类口吻起句。",
        "省略时间词，用短句确认供货状态。",
    ],
    "罐底扫码、三方质检报告": [
        "从报告页面或入口起句，不以扫开头。",
        "从自己这罐能对应起句，不以扫开头。",
        "用疑问句从这个码或物流码起句。",
        "用原来、没想到或咦起句。",
        "先说信息清楚，再补扫码事实。",
        "先说自己能查，再补物流码。",
        "从罐底位置起句。",
        "像回复楼主一样确认确实能查。",
        "从三方质检报告起句。",
        "从查起来方便的感受起句。",
        "用短句停顿，不以扫开头。",
        "直接问报告入口在哪里。",
    ],
    "会员权益、集罐换奶粉、抽奖、礼遇升级": [
        "从一个礼品名字起句，句中带a2。",
        "从活动规则起句，句中带a2。",
        "从老用户身份起句，句中带a2。",
        "用疑问句起句，句中带a2。",
        "从空罐、积分或会员页起句。",
        "用原来、没想到或咦起句。",
        "先说心动，再落一个a2活动动作。",
        "先说a2活动，再问一句规则。",
        "像顺手提醒姐妹一句。",
        "不用刚或a2开头，但句中带a2。",
        "从准备参与的动作起句，句中带a2。",
        "用短句确认一个a2会员活动。",
    ],
}

WAVE2_COUNTS = {
    "a2_direct_01": 30,
    "a2_direct_43": 30,
    "a2_direct_48": 30,
    "a2_direct_49": 30,
    "a2_direct_28": 20,
    "a2_direct_31": 20,
    "a2_direct_33": 20,
    "a2_direct_34": 20,
}

CATEGORY_REVIEW = {
    "enabled": True,
    "expression_frequency": [
        {"group_key": "opener_gang", "label": "刚字开头", "terms": ["刚"], "match_mode": "prefix", "max_ratio": 0.12},
        {"group_key": "opener_zhongyu", "label": "终于开头", "terms": ["终于"], "match_mode": "prefix", "max_ratio": 0.08},
        {"group_key": "opener_kandao", "label": "看到开头", "terms": ["看到"], "match_mode": "prefix", "max_ratio": 0.08},
        {"group_key": "opener_sao", "label": "扫字开头", "terms": ["扫"], "match_mode": "prefix", "max_ratio": 0.12},
    ],
    "opening_prefix_frequency": {"prefix_chars": 3, "max_count": 4},
    "opening_clause_frequency": {"max_count": 2},
}


def bundle(content_direction: str, materials: list[str], notes: list[str], length: str) -> dict[str, Any]:
    return {
        "generation_instruction": GENERATION_INSTRUCTION,
        "content_direction": content_direction,
        "activity_material": materials,
        "writing_requirements": [length],
        "notes": notes,
    }


RULES: dict[str, dict[str, Any]] = {
    "a2_direct_01": {
        "category": "有货-直给",
        "full_count": 70,
        "paths": STOCK_PATHS,
        "bundle": bundle(
            "基于内容素材，写直接、自然的反应、询问或夸赞。信息渠道和句式可以变化。",
            ["a2或a2至初已经到货、来货，或重新能买到。"],
            ["不要说缺货、断粮等消极词。", "不要用一包、一袋形容奶粉。"],
            "尽量在30字以内，表达自然优先",
        ),
    },
    "a2_direct_43": {
        "category": "有货-直给",
        "full_count": 70,
        "paths": STOCK_PATHS,
        "bundle": bundle(
            "基于内容素材，写直接、自然的反应、询问或夸赞。信息渠道和句式可以变化。",
            ["a2已经到货、来货，或重新能买到。生成时不要提产品名。"],
            ["不要说缺货、断粮等消极词。", "不要用一包、一袋形容奶粉。"],
            "尽量在30字以内，表达自然优先",
        ),
    },
    "a2_direct_45": {
        "category": "批批检、批次报告、检测透明",
        "full_count": 50,
        "paths": FACT_PATHS,
        "bundle": bundle(
            "基于内容素材，写直接、自然的反应、询问或夸赞。不要写成品牌口号。",
            ["a2公开每批检测信息。"],
            ["不写具体检测项目、数值或绝对安全结论。", "少用当妈的、硬核、路转粉等口号式表达。"],
            "字数尽量在30字以内，表达自然优先",
        ),
    },
    "a2_direct_46": {
        "category": "批批检、批次报告、检测透明",
        "full_count": 50,
        "paths": FACT_PATHS,
        "bundle": bundle(
            "基于内容素材，写直接、自然的反应、询问或夸赞。可以说报告能查、内容看得见或信息能对应。",
            ["a2对应批次报告可以查询。"],
            ["不写具体检测项目、数值或绝对安全结论。", "不要虚构扫码、购买、开罐或喂养经历。"],
            "字数尽量在30字以内，表达自然优先",
        ),
    },
    "a2_direct_47": {
        "category": "批批检、批次报告、检测透明",
        "full_count": 50,
        "paths": FACT_PATHS,
        "bundle": bundle(
            "基于内容素材，写直接、自然的认可、询问或夸赞。不要写成品牌口号。",
            ["a2公开每批检测信息，对应批次报告可以查询。"],
            ["不写具体检测项目、数值或绝对安全结论。", "不写观望、再观察或质疑。", "不要虚构扫码、购买、开罐或喂养经历。"],
            "字数尽量在30字以内，表达自然优先",
        ),
    },
    "a2_direct_48": {
        "category": "罐底扫码、三方质检报告",
        "full_count": 65,
        "paths": FACT_PATHS,
        "bundle": bundle(
            "基于内容素材，写扫码后直接、自然的反应、询问或夸赞。可以说能查到、能对应或入口清楚。",
            ["扫a2罐底物流码可以查看自己这罐对应批次报告。"],
            ["不写具体检测项目、数值或绝对安全结论。", "避免每条都用刚扫了开头。"],
            "字数尽量在35字以内，表达自然优先",
        ),
    },
    "a2_direct_49": {
        "category": "罐底扫码、三方质检报告",
        "full_count": 65,
        "paths": FACT_PATHS,
        "bundle": bundle(
            "基于内容素材，写查到报告后直接、自然的反应、询问或夸赞。可以说报告能查、信息清楚或自己能看。",
            ["扫a2罐底物流码可以查看自己这罐对应批次的三方质检报告。"],
            ["不写具体检测项目、数值或绝对安全结论。", "统一写三方质检报告。", "避免每条都用刚扫了开头。"],
            "字数尽量在35字以内，表达自然优先",
        ),
    },
    "a2_direct_28": {
        "category": "会员权益、集罐换奶粉、抽奖、礼遇升级",
        "full_count": 40,
        "paths": MEMBER_PATHS,
        "bundle": bundle(
            "基于内容素材，写看到活动后的直接反应、询问或夸赞。每条只落一个礼品或一个准备动作。",
            ["a2会员集罐活动可以兑换扭扭车、自行车、奶粉或婴儿推车。"],
            ["评论里带a2，并说清集罐或换礼动作。", "不写已经兑换成功、宝宝使用礼品或礼品效果。", "不补活动素材外的礼品、门槛、领取或兑换结果。"],
            "字数尽量在35字以内，表达自然优先",
        ),
    },
    "a2_direct_31": {
        "category": "会员权益、集罐换奶粉、抽奖、礼遇升级",
        "full_count": 40,
        "paths": MEMBER_PATHS,
        "bundle": bundle(
            "基于内容素材，写看到活动后的直接反应、询问或夸赞。每条只落一个礼品或一个准备动作。",
            ["a2会员活动包含溯源抽奖。", "礼品包括新西兰溯源、a2&小马宝莉黄金手串、宝宝夏凉被、a2营养全家礼和积分。"],
            ["评论里带a2，并说清抽奖动作。", "不写已经中奖、收到礼品或礼品使用效果。", "不补活动素材外的礼品、门槛、领取或中奖结果。", "新西兰溯源是礼品名称，不改写成免费游或旅行。"],
            "字数尽量在35字以内，表达自然优先",
        ),
    },
    "a2_direct_33": {
        "category": "会员权益、集罐换奶粉、抽奖、礼遇升级",
        "full_count": 40,
        "paths": MEMBER_PATHS,
        "bundle": bundle(
            "基于内容素材，写直接、自然的反应、询问或夸赞。可以是老用户顺手关注规则。",
            ["a2会员权益有升级或加码，老用户也可以关注活动规则。"],
            ["评论里带a2，并说清会员权益升级或加码。", "不补活动素材外的礼品、门槛、领取或中奖结果。", "不要写成会员权益一定更便宜。"],
            "字数尽量在35字以内，表达自然优先",
        ),
    },
    "a2_direct_34": {
        "category": "会员权益、集罐换奶粉、抽奖、礼遇升级",
        "full_count": 40,
        "paths": MEMBER_PATHS,
        "bundle": bundle(
            "基于内容素材，写直接、自然的反应、询问或夸赞。每条只落一个具体活动动作。",
            ["a2会员活动可以包含集罐、积分、抽奖、换礼、老客礼或礼品。"],
            ["评论里带a2，并说清会员、集罐、积分、抽奖、换礼或老客礼中的一个动作。", "不补活动素材外的礼品、门槛、领取或中奖结果。", "不要把积分换礼写成积分抽奖。"],
            "字数尽量在35字以内，表达自然优先",
        ),
    },
}

PROBE_RULES = {"a2_direct_43", "a2_direct_47", "a2_direct_49", "a2_direct_28"}


def request_payload(rule_id: str, count: int, created_by: str, *, wave2: bool = False) -> dict[str, Any]:
    definition = RULES[rule_id]
    paths = WAVE2_PATHS[definition["category"]] if wave2 else definition["paths"]
    return {
        "asset_key": ASSET_KEY,
        "rule_id": rule_id,
        "draft_rule_id": rule_id,
        "draft_comment_prompt_bundle": definition["bundle"],
        "comment_prompt_slots": {"本条表达路径": paths},
        "comment_batch_variation_review": CATEGORY_REVIEW,
        "count": count,
        "concurrency": 10,
        "executor_code": "maga_direct_llm_executor",
        "created_by": created_by,
    }


def post(payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        BASE_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("probe", "full", "wave2"))
    parser.add_argument("--output-dir", default="tmp/a2_diverse_batches_20260719")
    args = parser.parse_args()

    selected_rule_ids = sorted(
        PROBE_RULES if args.mode == "probe" else WAVE2_COUNTS if args.mode == "wave2" else RULES
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        for rule_id in selected_rule_ids:
            count = (
                10
                if args.mode == "probe"
                else int(WAVE2_COUNTS[rule_id])
                if args.mode == "wave2"
                else int(RULES[rule_id]["full_count"])
            )
            payload = request_payload(
                rule_id,
                count,
                f"a2-diverse-{args.mode}-20260719",
                wave2=args.mode == "wave2",
            )
            futures[executor.submit(post, payload)] = (rule_id, payload)
        for future in as_completed(futures):
            rule_id, payload = futures[future]
            response = future.result()
            data = response.get("data") or {}
            results[rule_id] = {
                "category": RULES[rule_id]["category"],
                "batch_id": data.get("batch_id"),
                "execution": data.get("execution"),
                "request": payload,
            }
            print(json.dumps({rule_id: results[rule_id]}, ensure_ascii=False))

    output = output_dir / f"{args.mode}_batches.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output.resolve()), "batch_ids": {key: value["batch_id"] for key, value in results.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
