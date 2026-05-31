"""Versioned system prompt keyword assets for unified generation."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maga_assets import AssetRegistry

CONTENT_GENERATION_KEYWORDS_ASSET_TYPE = "content_generation_keywords"
DEFAULT_SYSTEM_KEYWORD_ASSET_KEY = "default_content_generation_keywords"
SYSTEM_PROMPT_KEYWORD_SCHEMA_VERSION = "2"


class SystemPromptKeywordService:
    """Manage extensible system prompt keyword assets in asset_registry."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_latest_asset(self, asset_key: str = DEFAULT_SYSTEM_KEYWORD_ASSET_KEY) -> AssetRegistry | None:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type == CONTENT_GENERATION_KEYWORDS_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
                AssetRegistry.asset_stage == "production",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save_keywords(
        self,
        *,
        asset_key: str,
        display_name: str | None,
        content_json: dict[str, Any],
        created_by: str,
    ) -> AssetRegistry:
        normalized = normalize_system_prompt_keyword_content(content_json, strict=True)
        await self.db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == CONTENT_GENERATION_KEYWORDS_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        asset = AssetRegistry(
            asset_type=CONTENT_GENERATION_KEYWORDS_ASSET_TYPE,
            asset_key=asset_key,
            display_name=display_name or "系统提示词关键词",
            version_no=await self._next_asset_version(asset_key),
            status="active",
            asset_stage="production",
            source_name="system_prompt_keywords_manager",
            source_hash=_content_hash(normalized),
            content_json=normalized,
            metadata_json=_keyword_asset_metadata(normalized),
            created_by=created_by,
        )
        self.db.add(asset)
        await self.db.flush()
        return asset

    async def _next_asset_version(self, asset_key: str) -> int:
        result = await self.db.execute(
            select(AssetRegistry.version_no)
            .where(
                AssetRegistry.asset_type == CONTENT_GENERATION_KEYWORDS_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
            )
            .order_by(AssetRegistry.version_no.desc())
            .limit(1)
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1


def normalize_system_prompt_keyword_content(content_json: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    """Normalize old/new keyword asset shapes into the extensible v2 schema."""

    raw_categories = content_json.get("categories") if isinstance(content_json, dict) else None
    categories = _normalize_categories(raw_categories, strict=strict)
    if strict and not categories:
        raise ValueError("至少需要一个关键词类别")

    return {
        "schema_version": SYSTEM_PROMPT_KEYWORD_SCHEMA_VERSION,
        "asset_type": CONTENT_GENERATION_KEYWORDS_ASSET_TYPE,
        "selection_policy": _normalize_selection_policy(content_json.get("selection_policy")),
        "categories": categories,
    }


def fallback_system_prompt_keyword_content() -> dict[str, Any]:
    return normalize_system_prompt_keyword_content(
        {
            "schema_version": SYSTEM_PROMPT_KEYWORD_SCHEMA_VERSION,
            "selection_policy": {"default_mode": "one_per_enabled_category"},
            "categories": [
                {
                    "category_code": "persona",
                    "category_name": "人设",
                    "description": "默认表达身份，不是类别上限。",
                    "sort_order": 10,
                    "sub_keywords": [
                        {
                            "keyword_code": "experienced_mom",
                            "keyword_name": "经验型妈妈",
                            "corpus": ["像有带娃经验的妈妈在评论区交流，语气自然，不端着讲课。"],
                        },
                        {
                            "keyword_code": "careful_observer",
                            "keyword_name": "细节观察型妈妈",
                            "corpus": ["表达时多写具体观察和真实顾虑，少下结论，保留一点继续观望的感觉。"],
                        },
                        {
                            "keyword_code": "rational_comparer",
                            "keyword_name": "理性比较型妈妈",
                            "corpus": ["用克制的比较口吻表达，关注选择依据，不做绝对化推荐。"],
                        },
                    ],
                },
                {
                    "category_code": "writing_instruction",
                    "category_name": "生文指令",
                    "description": "默认生成约束，不是类别上限。",
                    "sort_order": 20,
                    "sub_keywords": [
                        {
                            "keyword_code": "natural_comment",
                            "keyword_name": "自然评论区表达",
                            "corpus": ["语言像顺手评论，短句优先，不写成广告口播或完整科普段落。"],
                        },
                        {
                            "keyword_code": "specific_question",
                            "keyword_name": "带着具体问题来",
                            "corpus": ["把泛泛的兴趣落到一个具体问题上，让内容更像真实妈妈在交流。"],
                        },
                        {
                            "keyword_code": "light_experience",
                            "keyword_name": "轻经验分享",
                            "corpus": ["可以用轻量经验感表达，但不要虚构强亲历或承诺效果。"],
                        },
                    ],
                },
                {
                    "category_code": "perturbation_rule",
                    "category_name": "扰动规则",
                    "description": "默认多样性控制，不是类别上限。",
                    "sort_order": 30,
                    "sub_keywords": [
                        {
                            "keyword_code": "opening_shift",
                            "keyword_name": "开头扰动",
                            "corpus": ["不要总用同一种开头，可从共鸣、追问、观察、轻提醒里选一种自然切入。"],
                        },
                        {
                            "keyword_code": "length_shift",
                            "keyword_name": "长短扰动",
                            "corpus": ["同批内容长短要有变化，本条优先控制在一到两句话。"],
                        },
                        {
                            "keyword_code": "stance_shift",
                            "keyword_name": "态度扰动",
                            "corpus": ["态度可以是想了解、轻共鸣、谨慎观望或补充经验，不要每条都像强推荐。"],
                        },
                    ],
                },
                {
                    "category_code": "writing_method",
                    "category_name": "写作手法",
                    "description": "默认表达技法，不是类别上限。",
                    "sort_order": 40,
                    "sub_keywords": [
                        {
                            "keyword_code": "scene_detail",
                            "keyword_name": "场景细节法",
                            "corpus": ["用一个带娃场景或选择奶粉时的小细节承接业务规则。"],
                        },
                        {
                            "keyword_code": "question_hook",
                            "keyword_name": "问题钩子法",
                            "corpus": ["用真实问题引出互动，让评论更像妈妈之间互相确认。"],
                        },
                        {
                            "keyword_code": "plain_explain",
                            "keyword_name": "白话解释法",
                            "corpus": ["把复杂点说得更白话，但不扩写成硬科普。"],
                        },
                    ],
                },
            ],
        }
    )


def _normalize_selection_policy(value: Any) -> dict[str, Any]:
    policy = value if isinstance(value, dict) else {}
    return {
        "default_mode": str(policy.get("default_mode") or "one_per_enabled_category"),
    }


def _normalize_categories(raw_categories: Any, *, strict: bool) -> list[dict[str, Any]]:
    if isinstance(raw_categories, dict):
        iterable = [
            {
                **value,
                "category_code": value.get("category_code") or key,
                "category_name": value.get("category_name") or value.get("name") or key,
            }
            for key, value in raw_categories.items()
            if isinstance(value, dict)
        ]
    elif isinstance(raw_categories, list):
        iterable = [item for item in raw_categories if isinstance(item, dict)]
    else:
        iterable = []

    categories: list[dict[str, Any]] = []
    for index, item in enumerate(iterable):
        code = _clean_text(item.get("category_code") or item.get("code") or item.get("category_name") or item.get("name"))
        name = _clean_text(item.get("category_name") or item.get("name") or code)
        if strict and (not code or not name):
            raise ValueError("关键词类别需要 category_code 和 category_name")
        if not code or not name:
            continue

        sub_keywords = _normalize_sub_keywords(item.get("sub_keywords") or item.get("items") or [], strict=strict)
        enabled = _as_bool(item.get("enabled"), default=True)
        if strict and enabled and not any(_as_bool(sub.get("enabled"), default=True) for sub in sub_keywords):
            raise ValueError(f"关键词类别「{name}」至少需要一个启用的子关键词")

        categories.append(
            {
                "category_code": code,
                "category_name": name,
                "description": _clean_text(item.get("description")),
                "enabled": enabled,
                "required": _as_bool(item.get("required"), default=False),
                "sort_order": _as_int(item.get("sort_order"), default=(index + 1) * 10),
                "selection_mode": _clean_text(item.get("selection_mode")) or "one",
                "applicable_content_types": _normalize_content_types(item.get("applicable_content_types")),
                "sub_keywords": sub_keywords,
            }
        )

    return sorted(categories, key=lambda item: (item.get("sort_order", 0), item.get("category_code", "")))


def _normalize_sub_keywords(raw_sub_keywords: Any, *, strict: bool) -> list[dict[str, Any]]:
    if not isinstance(raw_sub_keywords, list):
        if strict:
            raise ValueError("sub_keywords 必须是数组")
        return []

    sub_keywords: list[dict[str, Any]] = []
    for item in raw_sub_keywords:
        if not isinstance(item, dict):
            continue
        code = _clean_text(item.get("keyword_code") or item.get("code") or item.get("子关键词") or item.get("keyword_name"))
        name = _clean_text(item.get("keyword_name") or item.get("name") or item.get("子关键词") or code)
        corpus = _normalize_corpus(item.get("corpus") or item.get("语料") or item.get("rules") or [])
        if strict and (not code or not name):
            raise ValueError("子关键词需要 keyword_code 和 keyword_name")
        if strict and _as_bool(item.get("enabled"), default=True) and not corpus:
            raise ValueError(f"子关键词「{name or code}」至少需要一条语料")
        if not code or not name:
            continue
        sub_keywords.append(
            {
                "keyword_code": code,
                "keyword_name": name,
                "enabled": _as_bool(item.get("enabled"), default=True),
                "weight": _as_int(item.get("weight"), default=1),
                "corpus": corpus,
            }
        )
    return sub_keywords


def _normalize_content_types(value: Any) -> list[str]:
    if not isinstance(value, list):
        return ["article", "comment"]
    content_types = [_clean_text(item) for item in value]
    return [item for item in content_types if item] or ["article", "comment"]


def _normalize_corpus(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [_clean_text(item) for item in values if _clean_text(item)]


def _keyword_asset_metadata(content_json: dict[str, Any]) -> dict[str, Any]:
    categories = content_json.get("categories") or []
    sub_keywords = [
        sub
        for category in categories
        for sub in category.get("sub_keywords", [])
        if isinstance(sub, dict)
    ]
    return {
        "schema_version": content_json.get("schema_version"),
        "category_count": len(categories),
        "enabled_category_count": sum(1 for item in categories if _as_bool(item.get("enabled"), default=True)),
        "sub_keyword_count": len(sub_keywords),
        "corpus_count": sum(len(item.get("corpus") or []) for item in sub_keywords),
    }


def _content_hash(content_json: dict[str, Any]) -> str:
    payload = json.dumps(content_json, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", "否", "关闭"}
    return bool(value)


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
