"""Versioned system prompt keyword assets for unified generation."""
from __future__ import annotations

import hashlib
import json
import csv
import io
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maga_assets import AssetImportRun, AssetRegistry

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

    async def list_versions(
        self,
        asset_key: str = DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
        *,
        limit: int = 20,
    ) -> list[AssetRegistry]:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type == CONTENT_GENERATION_KEYWORDS_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.asset_stage == "production",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_version(self, *, asset_key: str, version_no: int) -> AssetRegistry | None:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type == CONTENT_GENERATION_KEYWORDS_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.version_no == version_no,
                AssetRegistry.asset_stage == "production",
            )
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

    async def rollback_to_version(
        self,
        *,
        asset_key: str,
        version_no: int,
        created_by: str,
    ) -> AssetRegistry:
        source_asset = await self.get_version(asset_key=asset_key, version_no=version_no)
        if source_asset is None:
            raise ValueError("要回滚的系统提示词关键词版本不存在")
        content_json = normalize_system_prompt_keyword_content(source_asset.content_json or {}, strict=True)
        asset = await self.save_keywords(
            asset_key=asset_key,
            display_name=source_asset.display_name or "系统提示词关键词",
            content_json=content_json,
            created_by=created_by,
        )
        asset.source_name = "system_prompt_keywords_rollback"
        asset.source_uri = f"asset_registry://{source_asset.id}"
        asset.metadata_json = {
            **(asset.metadata_json or {}),
            "rollback_from_asset_id": source_asset.id,
            "rollback_from_version_no": source_asset.version_no,
        }
        await self.db.flush()
        return asset

    async def import_keywords(
        self,
        file_content: bytes,
        *,
        source_name: str,
        asset_key: str = DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
        display_name: str | None = None,
        created_by: str = "maga-operator",
    ) -> tuple[AssetRegistry, AssetImportRun]:
        rows = _read_keyword_rows(file_content, source_name=source_name)
        content_json = keyword_rows_to_content(rows)
        asset = await self.save_keywords(
            asset_key=asset_key,
            display_name=display_name or "系统提示词关键词",
            content_json=content_json,
            created_by=created_by,
        )
        source_hash = hashlib.sha256(file_content).hexdigest()
        asset.source_name = source_name
        asset.source_uri = f"upload://{source_name}"
        asset.source_hash = source_hash

        metadata = _keyword_asset_metadata(asset.content_json)
        run = AssetImportRun(
            source_name=source_name,
            source_uri=f"upload://{source_name}",
            source_hash=source_hash,
            status="succeeded",
            imported_assets=1,
            summary_json={
                "asset_type": CONTENT_GENERATION_KEYWORDS_ASSET_TYPE,
                "asset_key": asset.asset_key,
                **metadata,
            },
            created_by=created_by,
        )
        self.db.add(run)
        await self.db.flush()
        return asset, run

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
    categories = _split_legacy_writing_instruction_categories(
        _normalize_categories(raw_categories, strict=strict)
    )
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
                    "description": "文章生成约束，不是类别上限。",
                    "sort_order": 20,
                    "applicable_content_types": ["article"],
                    "sub_keywords": [
                        {
                            "keyword_code": "natural_article",
                            "keyword_name": "自然成文表达",
                            "corpus": ["像真实妈妈写一段完整分享，表达自然，不写成广告口播或硬科普。"],
                        },
                        {
                            "keyword_code": "specific_expansion",
                            "keyword_name": "具体问题展开",
                            "corpus": ["围绕一个具体带娃问题展开，不泛泛罗列卖点，也不把话说得太满。"],
                        },
                        {
                            "keyword_code": "light_article_experience",
                            "keyword_name": "轻经验分享",
                            "corpus": ["可以有轻量经验感和选择过程，但不要虚构强亲历或承诺效果。"],
                        },
                    ],
                },
                {
                    "category_code": "comment_writing_instruction",
                    "category_name": "生评论指令",
                    "description": "评论生成约束，不是类别上限。",
                    "sort_order": 25,
                    "applicable_content_types": ["comment"],
                    "sub_keywords": [
                        {
                            "keyword_code": "natural_comment",
                            "keyword_name": "自然评论区表达",
                            "corpus": ["语言像顺手评论，短句优先，不写成广告口播或完整科普段落。"],
                        },
                        {
                            "keyword_code": "specific_comment_question",
                            "keyword_name": "带着具体问题来",
                            "corpus": ["把泛泛的兴趣落到一个具体问题上，让内容更像真实妈妈在评论区交流。"],
                        },
                        {
                            "keyword_code": "light_comment_experience",
                            "keyword_name": "轻经验互动",
                            "corpus": ["可以带一点轻量经验感或观望感，但不要虚构强亲历或承诺效果。"],
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
                {
                    "category_code": "article_format_control",
                    "category_name": "帖子格式控制",
                    "description": "控制帖子篇幅、emoji 和段落排版，不是评论规则。",
                    "sort_order": 50,
                    "applicable_content_types": ["article"],
                    "sub_keywords": [
                        {
                            "keyword_code": "article_compact_clean",
                            "keyword_name": "短帖干净",
                            "corpus": [
                                "文章控制在150到250字，分2到3个短段，段落之间空行，不用emoji。"
                            ],
                        },
                        {
                            "keyword_code": "article_light_emoji",
                            "keyword_name": "帖子少量表情",
                            "corpus": [
                                "文章控制在180到300字，分2到4段，可用1到2个emoji并自然分散。"
                            ],
                        },
                        {
                            "keyword_code": "article_clear_layout",
                            "keyword_name": "帖子分段清楚",
                            "corpus": [
                                "文章控制在250到400字，分3到5段，避免超过100字的长段，emoji最多3个且不能连续出现。"
                            ],
                        },
                    ],
                },
                {
                    "category_code": "comment_format_control",
                    "category_name": "评论格式控制",
                    "description": "控制评论篇幅和 emoji，不使用帖子段落规则。",
                    "sort_order": 55,
                    "applicable_content_types": ["comment"],
                    "sub_keywords": [
                        {
                            "keyword_code": "comment_short_clean",
                            "keyword_name": "0-5字",
                            "corpus": [
                                "评论控制在0到5字，极短回应，不用emoji，不分段。"
                            ],
                        },
                        {
                            "keyword_code": "comment_light_emoji",
                            "keyword_name": "6-15字",
                            "corpus": [
                                "评论控制在6到15字，尽量一句话，可不用emoji，不写成完整科普。"
                            ],
                        },
                        {
                            "keyword_code": "comment_two_sentence",
                            "keyword_name": "15-25字",
                            "corpus": [
                                "评论控制在15到25字，最多两句话，少用或不用emoji，保留真实互动感。"
                            ],
                        },
                    ],
                },
            ],
        }
    )


def keyword_rows_to_content(rows: list[dict[str, str]]) -> dict[str, Any]:
    categories_by_code: dict[str, dict[str, Any]] = {}
    keyword_lookup: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        category_code = _clean_text(_row_value(row, "类别Code", "类别编码", "category_code", "category code"))
        category_name = _clean_text(_row_value(row, "类别名称", "category_name", "category"))
        keyword_code = _clean_text(_row_value(row, "子关键词Code", "子关键词编码", "keyword_code", "keyword code"))
        keyword_name = _clean_text(_row_value(row, "子关键词名称", "keyword_name", "keyword"))
        corpus = _clean_text(_row_value(row, "语料", "corpus", "prompt", "提示词"))
        if not category_code:
            category_code = category_name
        if not category_name:
            category_name = category_code
        if not keyword_code:
            keyword_code = keyword_name
        if not keyword_name:
            keyword_name = keyword_code
        if not category_code or not keyword_code or not corpus:
            continue

        category = categories_by_code.setdefault(
            category_code,
            {
                "category_code": category_code,
                "category_name": category_name,
                "description": _clean_text(_row_value(row, "类别说明", "说明", "description")),
                "enabled": _as_bool(_row_value(row, "类别启用", "category_enabled", "enabled"), default=True),
                "required": _as_bool(_row_value(row, "必选", "required"), default=False),
                "sort_order": _as_int(_row_value(row, "类别顺序", "顺序", "sort_order"), default=(len(categories_by_code) + 1) * 10),
                "selection_mode": _clean_text(_row_value(row, "选择模式", "selection_mode")) or "one",
                "selected_keyword_code": _clean_text(_row_value(row, "固定子关键词Code", "固定子关键词", "selected_keyword_code")),
                "applicable_content_types": _content_types_from_text(
                    _row_value(row, "适用内容", "适用内容类型", "applicable_content_types")
                ),
                "sub_keywords": [],
            },
        )
        if category_name:
            category["category_name"] = category_name

        lookup_key = (category_code, keyword_code)
        keyword = keyword_lookup.get(lookup_key)
        if keyword is None:
            keyword = {
                "keyword_code": keyword_code,
                "keyword_name": keyword_name,
                "enabled": _as_bool(_row_value(row, "子关键词启用", "keyword_enabled"), default=True),
                "weight": _as_int(_row_value(row, "权重", "weight"), default=1),
                "corpus": [],
            }
            keyword_lookup[lookup_key] = keyword
            category["sub_keywords"].append(keyword)
        if keyword_name:
            keyword["keyword_name"] = keyword_name
        if corpus not in keyword["corpus"]:
            keyword["corpus"].append(corpus)

    content = normalize_system_prompt_keyword_content(
        {
            "schema_version": SYSTEM_PROMPT_KEYWORD_SCHEMA_VERSION,
            "selection_policy": {"default_mode": "one_per_enabled_category"},
            "categories": list(categories_by_code.values()),
        },
        strict=True,
    )
    if not content["categories"]:
        raise ValueError("系统提示词关键词导入文件为空")
    return content


def export_keywords_csv(content_json: dict[str, Any]) -> str:
    content = normalize_system_prompt_keyword_content(content_json)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "类别Code",
            "类别名称",
            "类别说明",
            "类别启用",
            "必选",
            "类别顺序",
            "选择模式",
            "固定子关键词Code",
            "适用内容",
            "子关键词Code",
            "子关键词名称",
            "子关键词启用",
            "权重",
            "语料",
        ],
    )
    writer.writeheader()
    for category in content.get("categories") or []:
        for keyword in category.get("sub_keywords") or []:
            corpus_items = keyword.get("corpus") or [""]
            for corpus in corpus_items:
                writer.writerow(
                    {
                        "类别Code": category.get("category_code"),
                        "类别名称": category.get("category_name"),
                        "类别说明": category.get("description"),
                        "类别启用": "是" if _as_bool(category.get("enabled"), default=True) else "否",
                        "必选": "是" if _as_bool(category.get("required"), default=False) else "否",
                        "类别顺序": category.get("sort_order"),
                        "选择模式": category.get("selection_mode") or "one",
                        "固定子关键词Code": category.get("selected_keyword_code") or "",
                        "适用内容": ",".join(category.get("applicable_content_types") or []),
                        "子关键词Code": keyword.get("keyword_code"),
                        "子关键词名称": keyword.get("keyword_name"),
                        "子关键词启用": "是" if _as_bool(keyword.get("enabled"), default=True) else "否",
                        "权重": keyword.get("weight") or 1,
                        "语料": corpus,
                    }
                )
    return output.getvalue()


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
        selection_mode = _clean_text(item.get("selection_mode")) or "one"
        selected_keyword_code = _clean_text(item.get("selected_keyword_code"))
        if strict and enabled and selection_mode == "fixed":
            if not selected_keyword_code:
                raise ValueError(f"关键词类别「{name}」固定选择时必须指定子关键词")
            enabled_codes = {
                sub.get("keyword_code")
                for sub in sub_keywords
                if _as_bool(sub.get("enabled"), default=True)
            }
            if selected_keyword_code not in enabled_codes:
                raise ValueError(f"关键词类别「{name}」固定选择的子关键词不存在或未启用")

        categories.append(
            {
                "category_code": code,
                "category_name": name,
                "description": _clean_text(item.get("description")),
                "enabled": enabled,
                "required": _as_bool(item.get("required"), default=False),
                "sort_order": _as_int(item.get("sort_order"), default=(index + 1) * 10),
                "selection_mode": selection_mode,
                "selected_keyword_code": selected_keyword_code,
                "applicable_content_types": _normalize_content_types(item.get("applicable_content_types")),
                "sub_keywords": sub_keywords,
            }
        )

    return sorted(categories, key=lambda item: (item.get("sort_order", 0), item.get("category_code", "")))


def _split_legacy_writing_instruction_categories(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    has_comment_instruction = any(
        item.get("category_code") == "comment_writing_instruction"
        or item.get("category_name") == "生评论指令"
        for item in categories
    )
    if has_comment_instruction:
        return categories

    split_categories: list[dict[str, Any]] = []
    for category in categories:
        content_types = set(category.get("applicable_content_types") or [])
        should_split = (
            category.get("category_code") == "writing_instruction"
            and {"article", "comment"}.issubset(content_types)
        )
        if not should_split:
            split_categories.append(category)
            continue

        article_category = {
            **category,
            "description": category.get("description") or "文章生成约束，不是类别上限。",
            "applicable_content_types": ["article"],
        }
        comment_category = {
            **category,
            "category_code": "comment_writing_instruction",
            "category_name": "生评论指令",
            "description": "评论生成约束，不是类别上限。",
            "sort_order": _as_int(category.get("sort_order"), default=20) + 5,
            "applicable_content_types": ["comment"],
        }
        split_categories.extend([article_category, comment_category])

    return sorted(split_categories, key=lambda item: (item.get("sort_order", 0), item.get("category_code", "")))


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


def _read_keyword_rows(file_content: bytes, *, source_name: str) -> list[dict[str, str]]:
    lower_name = source_name.lower()
    if lower_name.endswith(".xlsx"):
        return _read_xlsx_rows(file_content)
    if lower_name.endswith(".csv"):
        return _read_csv_rows(file_content)
    raise ValueError("only .csv and .xlsx files are supported")


def _read_csv_rows(file_content: bytes) -> list[dict[str, str]]:
    text = file_content.decode("utf-8-sig")
    content = "".join(line for line in text.splitlines(True) if not line.startswith("#"))
    return [
        {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
        for row in csv.DictReader(io.StringIO(content))
        if any(str(value or "").strip() for value in row.values())
    ]


def _read_xlsx_rows(file_content: bytes) -> list[dict[str, str]]:
    wb = load_workbook(io.BytesIO(file_content), data_only=True)
    ws = wb.active
    headers = [str(cell.value or "").strip() for cell in ws[1]]
    rows: list[dict[str, str]] = []
    for raw in ws.iter_rows(min_row=2, values_only=True):
        row = {header: str(value or "").strip() for header, value in zip(headers, raw) if header}
        if any(row.values()):
            rows.append(row)
    return rows


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


def _row_value(row: dict[str, str], *keys: str) -> str:
    lowered = {key.lower().replace("_", "").replace(" ", ""): value for key, value in row.items()}
    for key in keys:
        if key in row:
            return row[key]
        normalized_key = key.lower().replace("_", "").replace(" ", "")
        if normalized_key in lowered:
            return lowered[normalized_key]
    return ""


def _content_types_from_text(value: Any) -> list[str]:
    text = _clean_text(value)
    if not text:
        return ["article", "comment"]
    mapping = {"文章": "article", "生文": "article", "评论": "comment"}
    parts = [part.strip() for part in text.replace("，", ",").replace("、", ",").split(",") if part.strip()]
    content_types = [mapping.get(part, part) for part in parts]
    return content_types or ["article", "comment"]


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", "否", "关闭", "停用"}
    return bool(value)


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
