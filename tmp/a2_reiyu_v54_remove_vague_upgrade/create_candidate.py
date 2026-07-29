from __future__ import annotations

import copy
import json
import urllib.parse
import urllib.request


BASE_URL = "http://127.0.0.1:5100/api/v1"
ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
ASSET_TYPE = "article_business_rule_set"
TARGET = "这次升级会员体系确实比以前用心了"


def request_json(url: str, *, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers)) as response:
        return json.load(response)


def remove_target(value: object) -> int:
    removed = 0
    if isinstance(value, dict):
        for child in value.values():
            removed += remove_target(child)
    elif isinstance(value, list):
        before = len(value)
        value[:] = [item for item in value if item != TARGET]
        removed += before - len(value)
        for child in value:
            removed += remove_target(child)
    return removed


def main() -> None:
    query = urllib.parse.urlencode(
        {
            "asset_key": ASSET_KEY,
            "asset_stage": "production",
            "include_hidden": "true",
        }
    )
    assets = request_json(f"{BASE_URL}/assets?{query}")["data"]
    source = next(asset for asset in assets if asset["asset_type"] == ASSET_TYPE)
    content = copy.deepcopy(source["content_json"])
    removed_count = remove_target(content)
    if removed_count != 2:
        raise RuntimeError(f"expected 2 removals, got {removed_count}")

    metadata = dict(source.get("metadata_json") or {})
    metadata.update(
        {
            "asset_stage": "candidate",
            "base_production_asset_id": source["id"],
            "base_production_version_no": source["version_no"],
            "change_reason": "删除缺少具体活动事实的升级更用心语料，避免模型自行补活动机制和奖品",
            "removed_activity_content_option": TARGET,
            "removed_occurrence_count": removed_count,
        }
    )
    candidate = request_json(
        f"{BASE_URL}/assets/candidates",
        payload={
            "asset_type": source["asset_type"],
            "asset_key": source["asset_key"],
            "display_name": "a2礼遇UGC分享贴业务规则-删除升级更用心空泛语料",
            "source_name": f"candidate:asset_registry:{source['id']}:v{source['version_no']}",
            "source_uri": f"asset_registry://{source['id']}",
            "source_hash": source.get("source_hash"),
            "content_json": content,
            "metadata_json": metadata,
            "created_by": "codex-a2-reiyu-v54",
        },
    )["data"]
    print(
        json.dumps(
            {
                "source_asset_id": source["id"],
                "source_version": source["version_no"],
                "candidate_asset_id": candidate["id"],
                "candidate_version": candidate["version_no"],
                "removed_occurrence_count": removed_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
