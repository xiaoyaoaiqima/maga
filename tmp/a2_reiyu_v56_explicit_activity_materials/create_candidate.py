from __future__ import annotations

import copy
import json
import urllib.parse
import urllib.request


BASE_URL = "http://127.0.0.1:5100/api/v1"
ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
ASSET_TYPE = "article_business_rule_set"

REPLACEMENTS = {
    "会员体系升级，用户权益也上来了": "会员体系升级后，每次下单会累计积分，积分可以按会员规则兑换礼品",
    "会员积分啥的就是给长期囤货的人准备的，挺划得来": "每次下单累计积分，长期回购的老客可以按会员规则用积分兑换礼品",
    "才注意到a2至初的会员体系，原来每次下单都能累计积分，还能换各种礼品": "才注意到a2至初的会员体系，每次下单会累计积分，积分可以按会员规则兑换礼品",
    "积分可以换礼品，这种特别适合我这种长期回购的用户": "积分达到会员规则要求后可以兑换礼品，长期回购更容易用上这个权益",
    "积分系统挺友好的，换的东西也实用": "下单会累计积分，积分能按会员规则兑换礼品，老客确实用得上",
    "之前还觉得活动就是抽个奖而已，发现真的是福利叠加": "这次不止有抽奖，集罐兑换和老客回馈礼也都按各自规则进行",
    "多层福利叠加，感觉每一笔消费都更有价值了": "抽奖、集罐兑换、老客回馈礼是不同福利，各自看对应活动规则",
    "多重福利一起上，a2这次是真的很舍得🎁": "既有抽奖，也有集罐兑换，符合条件的老客还有回馈礼🎁",
    "多重福利叠加起来真的很香✌️": "抽奖看手气，集罐按罐数兑换，老客回馈礼则看老客资格✌️",
    "抽奖、集罐礼、老客回馈都有，多重福利真的用心了": "本来以为只有抽奖，后来发现还有集罐兑换和老客回馈礼",
    "本来以为就一个活动，结果发现福利层层叠加，越看越觉得划算😂": "集罐按罐数兑换对应礼品，另外还有抽奖和老客回馈礼😂",
    "罐子能换、抽奖也能参与，这种组合活动很实在了呀😊": "抽奖、集罐礼、老客回馈礼都有，每种活动按自己的规则参加😊",
    "集罐、抽奖、回馈礼都有，叠加起来真的很香": "集罐兑换、抽奖和老客回馈礼都有，活动内容确实不少",
}


def request_json(url: str, *, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers)) as response:
        return json.load(response)


def replace_values(value: object, counts: dict[str, int]) -> object:
    if isinstance(value, dict):
        return {key: replace_values(child, counts) for key, child in value.items()}
    if isinstance(value, list):
        return [replace_values(child, counts) for child in value]
    if isinstance(value, str) and value in REPLACEMENTS:
        counts[value] += 1
        return REPLACEMENTS[value]
    return value


def main() -> None:
    query = urllib.parse.urlencode(
        {
            "asset_key": ASSET_KEY,
            "asset_stage": "production",
            "include_hidden": "true",
        }
    )
    assets = request_json(f"{BASE_URL}/assets?{query}")["data"]
    source = next(
        asset
        for asset in assets
        if asset["asset_type"] == ASSET_TYPE and asset["status"] == "active"
    )
    counts = {text: 0 for text in REPLACEMENTS}
    content = replace_values(copy.deepcopy(source["content_json"]), counts)
    unexpected = {text: count for text, count in counts.items() if count != 2}
    if unexpected:
        raise RuntimeError(f"each activity option should occur twice: {unexpected}")

    metadata = dict(source.get("metadata_json") or {})
    metadata.update(
        {
            "asset_stage": "candidate",
            "base_production_asset_id": source["id"],
            "base_production_version_no": source["version_no"],
            "change_reason": "积分和多重福利activity_content改成明确机制，避免模型补写未提供的具体福利",
            "explicit_activity_content_replacements": REPLACEMENTS,
            "changed_activity_content_option_count": len(REPLACEMENTS),
            "changed_occurrence_count": sum(counts.values()),
        }
    )
    candidate = request_json(
        f"{BASE_URL}/assets/candidates",
        payload={
            "asset_type": source["asset_type"],
            "asset_key": source["asset_key"],
            "display_name": "a2礼遇UGC分享贴业务规则-积分与多重福利机制明确化",
            "source_name": f"candidate:asset_registry:{source['id']}:v{source['version_no']}",
            "source_uri": f"asset_registry://{source['id']}",
            "source_hash": source.get("source_hash"),
            "content_json": content,
            "metadata_json": metadata,
            "created_by": "codex-a2-reiyu-v56",
        },
    )["data"]
    print(
        json.dumps(
            {
                "source_asset_id": source["id"],
                "source_version": source["version_no"],
                "candidate_asset_id": candidate["id"],
                "candidate_version": candidate["version_no"],
                "changed_activity_content_option_count": len(REPLACEMENTS),
                "changed_occurrence_count": sum(counts.values()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
