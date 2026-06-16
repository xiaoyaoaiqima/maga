"""Build unified content generation inputs from business rules and keyword assets."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expert_config import ExpertConfig
from app.models.maga_assets import AssetRegistry
from app.services.system_prompt_keyword_service import (
    CONTENT_GENERATION_KEYWORDS_ASSET_TYPE,
    DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
    fallback_system_prompt_keyword_content,
    normalize_system_prompt_keyword_content,
)

CONTENT_GENERATE_CAPABILITY = "content.generate"
SYSTEM_KEYWORD_ASSET_TYPE = CONTENT_GENERATION_KEYWORDS_ASSET_TYPE
DEFAULT_COMMENT_EXPERT_CONFIG_CODE = "comment_generator_v1"
DEFAULT_ARTICLE_EXPERT_CONFIG_CODE = "article_generator_v1"
GENERATION_REQUIREMENT_CATEGORY_CODES = {
    "generation_requirement",
    "comment_generation_requirement",
    "article_generation_requirement",
}
KEYWORD_CORPUS_RENDER_PRIORITY = {
    "perturbation_rule": 10,
    "persona": 20,
    "comment_writing_instruction": 30,
    "writing_instruction": 30,
    "comment_speaking_style": 35,
    "writing_method": 40,
    "comment_format_control": 50,
    "article_format_control": 50,
}


@dataclass(frozen=True)
class UnifiedGenerationSnapshot:
    input_snapshot: dict[str, Any]
    asset_refs: dict[str, Any]


class UnifiedContentGenerationService:
    """Compile one executable generation prompt from a business rule package.

    The operator-facing input remains only the uploaded business rule package.
    MAGA then selects one sub-keyword from each enabled keyword category and renders
    the expert prompt template into a stateless executor payload.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_snapshot(
        self,
        *,
        content_type: str,
        business_rule: dict[str, Any],
        item_no: int,
        output_fields: list[str],
        expert_config_code: str | None = None,
        keyword_asset_key: str | None = None,
        keyword_content_override: dict[str, Any] | None = None,
        model_config: dict[str, Any] | None = None,
    ) -> UnifiedGenerationSnapshot:
        resolved_keyword_asset_key = _resolve_keyword_asset_key(keyword_asset_key, business_rule)
        keyword_asset = (
            None
            if keyword_content_override is not None
            else await self._latest_keyword_asset(resolved_keyword_asset_key)
        )
        keyword_content = normalize_system_prompt_keyword_content(
            keyword_content_override
            if keyword_content_override is not None
            else keyword_asset.content_json
            if keyword_asset
            else fallback_system_prompt_keyword_content()
        )
        selected_keywords = _select_keyword_bundle(
            keyword_content,
            content_type=content_type,
            item_no=item_no,
            keyword_selection=_keyword_selection_from_rule(business_rule),
        )
        expert = await self._expert_snapshot(
            expert_config_code or _default_expert_code(content_type),
            content_type=content_type,
            model_config=model_config,
        )
        variables = _template_variables(
            content_type=content_type,
            output_fields=output_fields,
            business_rule=business_rule,
            selected_keywords=selected_keywords,
        )
        rendered_prompt = _render_template(expert["prompt_template"], variables)
        input_snapshot = {
            "schema_version": "1",
            "capability": CONTENT_GENERATE_CAPABILITY,
            "content_type": content_type,
            "output_fields": output_fields,
            "business_rule": business_rule,
            "selected_keywords": selected_keywords,
            "keyword_asset": _keyword_asset_ref(
                keyword_asset,
                resolved_keyword_asset_key,
                inline=keyword_content_override is not None,
            ),
            "expert": expert,
            "model_config": expert["model_config"],
            "template_variables": variables,
            "rendered_prompt": rendered_prompt,
        }
        return UnifiedGenerationSnapshot(
            input_snapshot=input_snapshot,
            asset_refs={
                "business_rule": _business_rule_ref(business_rule),
                "keyword_asset": _keyword_asset_ref(
                    keyword_asset,
                    resolved_keyword_asset_key,
                    inline=keyword_content_override is not None,
                ),
                "expert_config": {
                    "expert_config_code": expert["expert_config_code"],
                    "source": expert["source"],
                },
            },
        )

    async def _latest_keyword_asset(self, asset_key: str) -> AssetRegistry | None:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type == SYSTEM_KEYWORD_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
                AssetRegistry.asset_stage == "production",
            )
            .order_by(AssetRegistry.version_no.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _expert_snapshot(
        self,
        expert_config_code: str,
        *,
        content_type: str,
        model_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(ExpertConfig)
            .where(
                ExpertConfig.expert_config_code == expert_config_code,
                ExpertConfig.enabled == 1,
                ExpertConfig.is_deleted == 0,
            )
            .limit(1)
        )
        expert = result.scalar_one_or_none()
        if expert:
            config = _normalize_model_config(
                {
                    **(expert.model_config or {}),
                    **({"model_code": expert.model_code} if expert.model_code else {}),
                    **(model_config or {}),
                }
            )
            return {
                "expert_config_code": expert.expert_config_code,
                "expert_config_name": expert.expert_config_name,
                "expert_type": expert.expert_type,
                "prompt_template": expert.prompt_template or _fallback_prompt_template(content_type),
                "model_config": config,
                "source": "expert_config",
            }
        return _fallback_expert_snapshot(expert_config_code, content_type=content_type, model_config=model_config)


def _select_keyword_bundle(
    content_json: dict[str, Any],
    *,
    content_type: str,
    item_no: int,
    keyword_selection: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    categories = _categories_from_content(content_json)
    selected: list[dict[str, Any]] = []
    base = max(1, item_no) - 1
    for offset, category in enumerate(categories):
        if category.get("enabled") is False:
            continue
        applicable_content_types = category.get("applicable_content_types")
        if isinstance(applicable_content_types, list) and applicable_content_types:
            if content_type not in {str(item) for item in applicable_content_types}:
                continue
        sub_keywords = category.get("sub_keywords") or category.get("items") or []
        sub_keywords = [item for item in sub_keywords if isinstance(item, dict)]
        sub_keywords = [item for item in sub_keywords if item.get("enabled") is not False]
        sub_keywords = _filter_sub_keywords_by_selection(category, sub_keywords, keyword_selection)
        if not sub_keywords:
            continue
        item = _select_sub_keyword(category, sub_keywords, index=(base + offset))
        corpus = item.get("corpus") or item.get("语料") or item.get("rules") or []
        if isinstance(corpus, str):
            corpus = [corpus]
        selected.append(
            {
                "category_code": category.get("category_code") or category.get("code") or category.get("category_name"),
                "category_name": category.get("category_name") or category.get("name") or category.get("category_code"),
                "keyword_code": item.get("keyword_code") or item.get("code") or item.get("子关键词") or item.get("keyword_name"),
                "keyword_name": item.get("keyword_name") or item.get("name") or item.get("子关键词") or item.get("keyword_code"),
                "corpus": [str(value).strip() for value in corpus if str(value).strip()],
            }
        )
    return selected


def _keyword_selection_from_rule(rule: dict[str, Any]) -> dict[str, Any]:
    value = rule.get("keyword_selection") if isinstance(rule, dict) else None
    return dict(value) if isinstance(value, dict) else {}


def _filter_sub_keywords_by_selection(
    category: dict[str, Any],
    sub_keywords: list[dict[str, Any]],
    keyword_selection: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    allowed_codes = _allowed_keyword_codes_for_category(category, keyword_selection)
    filtered = sub_keywords
    if allowed_codes is not None:
        filtered = [
            item
            for item in filtered
            if str(item.get("keyword_code") or item.get("code") or item.get("子关键词") or "").strip() in allowed_codes
        ]
    return filtered


def _allowed_keyword_codes_for_category(
    category: dict[str, Any],
    keyword_selection: dict[str, Any] | None,
) -> set[str] | None:
    if not keyword_selection:
        return None
    category_keys = [
        category.get("category_code"),
        category.get("code"),
        category.get("category_name"),
        category.get("name"),
    ]
    for key in category_keys:
        normalized_key = str(key or "").strip()
        if not normalized_key or normalized_key not in keyword_selection:
            continue
        value = keyword_selection[normalized_key]
        if isinstance(value, dict):
            value = value.get("include") or value.get("codes") or value.get("keyword_codes")
        if isinstance(value, str):
            value = re.split(r"[,，\s]+", value)
        if isinstance(value, list):
            allowed = {str(item).strip() for item in value if str(item).strip()}
            return allowed or set()
    return None


def _resolve_keyword_asset_key(explicit_key: str | None, business_rule: dict[str, Any]) -> str:
    for value in (
        explicit_key,
        business_rule.get("keyword_asset_key") if isinstance(business_rule, dict) else None,
        business_rule.get("system_keyword_asset_key") if isinstance(business_rule, dict) else None,
    ):
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return DEFAULT_SYSTEM_KEYWORD_ASSET_KEY


def _select_sub_keyword(category: dict[str, Any], sub_keywords: list[dict[str, Any]], *, index: int) -> dict[str, Any]:
    # 固定选择用于 Demo/活动需要稳定命中某个子关键词的场景；未配置时继续沿用自动轮换。
    if category.get("selection_mode") == "fixed" and category.get("selected_keyword_code"):
        selected_keyword_code = str(category.get("selected_keyword_code"))
        for item in sub_keywords:
            keyword_code = item.get("keyword_code") or item.get("code") or item.get("子关键词")
            if str(keyword_code) == selected_keyword_code:
                return item
    return sub_keywords[index % len(sub_keywords)]


def _categories_from_content(content_json: dict[str, Any]) -> list[dict[str, Any]]:
    raw_categories = content_json.get("categories") if isinstance(content_json, dict) else None
    if isinstance(raw_categories, dict):
        categories = [
            {
                **value,
                "category_code": value.get("category_code") or key,
                "category_name": value.get("category_name") or value.get("name") or key,
            }
            for key, value in raw_categories.items()
            if isinstance(value, dict)
        ]
    elif isinstance(raw_categories, list):
        categories = [item for item in raw_categories if isinstance(item, dict)]
    else:
        categories = []
    return sorted(categories, key=lambda item: (item.get("sort_order") or 0, item.get("category_code") or ""))


def _template_variables(
    *,
    content_type: str,
    output_fields: list[str],
    business_rule: dict[str, Any],
    selected_keywords: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "content_type": content_type,
        "content_type_label": "评论" if content_type == "comment" else "文章",
        "output_fields": "、".join(output_fields),
        "business_rule": _business_rule_text(business_rule),
        "keyword_corpus": _keyword_corpus_text(selected_keywords),
        "selected_keywords_json": json.dumps(selected_keywords, ensure_ascii=False, indent=2),
        "generation_requirements": _generation_requirements(
            content_type,
            output_fields,
            business_rule,
            selected_keywords,
        ),
    }


def _business_rule_text(rule: dict[str, Any]) -> str:
    lines: list[str] = []
    if rule.get("product_topic"):
        lines.append(f"- 主题：{rule.get('product_topic')}")
    if rule.get("target_audience"):
        lines.append(f"- 目标人群：{rule.get('target_audience')}")
    if rule.get("persona_target"):
        lines.append(f"- 人设要求：{rule.get('persona_target')}")
    if rule.get("style"):
        lines.append(f"- 风格：{rule.get('style')}")
    rule_name = (
        rule.get("business_rule")
        or rule.get("comment_" + "angle")
        or rule.get("article_rule")
        or rule.get("topic")
    )
    if rule_name:
        lines.append(f"- 业务规则：{rule_name}")
    if rule.get("baby_stage") or rule.get("use_duration"):
        parts = []
        if rule.get("baby_stage"):
            parts.append(f"月龄={rule.get('baby_stage')}")
        if rule.get("use_duration"):
            parts.append(f"使用时间={rule.get('use_duration')}")
        if rule.get("topic"):
            parts.append(f"主题={rule.get('topic')}")
        lines.append(f"- 体验拆解：{'，'.join(parts)}")
    if rule.get("corpus"):
        lines.append(f"- 业务语料：\n{rule.get('corpus')}")
    for label, key in [
        ("痛点资料", "painpoint_ref"),
        ("卖点资料", "selling_point_ref"),
        ("写作结构参考", "writing_pattern_ref"),
    ]:
        ref = rule.get(key)
        if isinstance(ref, dict) and isinstance(ref.get("snapshot"), dict):
            lines.append(f"- {label}：\n{json.dumps(ref['snapshot'], ensure_ascii=False, indent=2)}")
    reference_refs = rule.get("reference_example_refs") or []
    reference_examples = [
        ref.get("snapshot")
        for ref in reference_refs
        if isinstance(ref, dict) and isinstance(ref.get("snapshot"), dict)
    ]
    if reference_examples:
        lines.append("- 参考例文：\n" + json.dumps(reference_examples[:3], ensure_ascii=False, indent=2))
    compliance_refs = rule.get("compliance_rule_refs") or []
    compliance_rules = [
        ref.get("snapshot")
        for ref in compliance_refs
        if isinstance(ref, dict) and isinstance(ref.get("snapshot"), dict)
    ]
    if compliance_rules:
        lines.append("- 合规约束：\n" + json.dumps(compliance_rules, ensure_ascii=False, indent=2))
    if isinstance(rule.get("diversity_slot"), dict):
        lines.append("- 多样性槽位：\n" + json.dumps(rule["diversity_slot"], ensure_ascii=False, indent=2))
    if isinstance(rule.get("brief_constraints"), dict):
        lines.append("- 格式/篇幅约束：\n" + json.dumps(rule["brief_constraints"], ensure_ascii=False, indent=2))
    if rule.get("render_reference_examples") is not False:
        examples = [str(item).strip() for item in rule.get("examples") or [] if str(item).strip()]
        supplements = [str(item).strip() for item in rule.get("supplements") or [] if str(item).strip()]
        prompt_examples = examples + supplements
        if prompt_examples:
            # 重要逻辑：示例只作为表达颗粒参考，避免把真人语料当范文复刻。
            lines.append(
                "- 示例使用边界：只学习语气、场景颗粒和生活细节；只借一个观察点，"
                "不复刻原句、结构和事实主张，也不要沿用示例的叙述顺序或固定句式骨架。"
            )
            lines.append("- 示例：\n" + "\n".join(f"  - {item}" for item in prompt_examples))
    if not lines:
        lines.append(json.dumps(rule, ensure_ascii=False, indent=2))
    return "\n".join(lines)


def _keyword_corpus_text(selected_keywords: list[dict[str, Any]]) -> str:
    parts = []
    for item in _ordered_keyword_corpus_items(selected_keywords):
        # 生成要求要放在 prompt 顶部独立生效，不再在系统关键词语料区重复出现。
        if str(item.get("category_code") or "").strip() in GENERATION_REQUIREMENT_CATEGORY_CODES:
            continue
        corpus = item.get("corpus") or []
        corpus_text = "\n".join(f"  - {line}" for line in corpus)
        parts.append(f"- {item.get('category_name')} / {item.get('keyword_name')}：\n{corpus_text}")
    return "\n".join(parts)


def _ordered_keyword_corpus_items(selected_keywords: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = list(enumerate(selected_keywords))
    return [
        item
        for _, item in sorted(
            indexed,
            key=lambda pair: (
                KEYWORD_CORPUS_RENDER_PRIORITY.get(str(pair[1].get("category_code") or "").strip(), 100),
                pair[0],
            ),
        )
    ]


def _generation_requirements(
    content_type: str,
    output_fields: list[str],
    business_rule: dict[str, Any],
    selected_keywords: list[dict[str, Any]],
) -> str:
    parts = _selected_generation_requirements(selected_keywords)
    configured = str(business_rule.get("generation_requirements") or "").strip()
    if configured:
        parts.append(configured)
    if parts:
        return "\n".join(parts)
    if content_type == "comment" or output_fields == ["comment"]:
        return (
            "生成一条小红书母婴社区真实用户评论，口语化，有活人感。"
            "只输出评论正文，不要标题、编号、解释。"
        )
    return (
        "输出 JSON 对象，字段包含 title 和 body；正文保持小红书自然表达；"
        "业务规则优先，系统提示词关键词语料用于表达身份、生成指令、多样性和写法控制。"
    )


def _selected_generation_requirements(selected_keywords: list[dict[str, Any]]) -> list[str]:
    requirements: list[str] = []
    for item in selected_keywords:
        if str(item.get("category_code") or "").strip() not in GENERATION_REQUIREMENT_CATEGORY_CODES:
            continue
        for line in item.get("corpus") or []:
            text = str(line or "").strip()
            if text:
                requirements.append(text)
    return requirements


_TEMPLATE_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


def _render_template(template: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = variables.get(key, "")
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    return _TEMPLATE_PATTERN.sub(replace, template).strip()


def _default_expert_code(content_type: str) -> str:
    return DEFAULT_COMMENT_EXPERT_CONFIG_CODE if content_type == "comment" else DEFAULT_ARTICLE_EXPERT_CONFIG_CODE


def _fallback_expert_snapshot(
    expert_config_code: str,
    *,
    content_type: str,
    model_config: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "expert_config_code": expert_config_code,
        "expert_config_name": "默认评论生成 Expert" if content_type == "comment" else "默认文章生成 Expert",
        "expert_type": "GENERATION",
        "prompt_template": _fallback_prompt_template(content_type),
        "model_config": _normalize_model_config(model_config or {}),
        "source": "fallback",
    }


def _fallback_prompt_template(content_type: str) -> str:
    if content_type == "comment":
        return (
            "【生成要求】\n{{ generation_requirements }}\n\n"
            "【系统关键词语料】\n{{ keyword_corpus }}\n\n"
            "【业务规则】\n{{ business_rule }}"
        )
    return (
        "你是小红书母婴内容生成 expert。\n"
        "请根据业务规则和系统内置关键词语料，生成一篇自然种草内容。\n\n"
        "【业务规则】\n{{ business_rule }}\n\n"
        "【系统关键词语料】\n{{ keyword_corpus }}\n\n"
        "【生成要求】\n{{ generation_requirements }}"
    )


def _normalize_model_config(value: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key in (
        "provider",
        "provider_code",
        "model_code",
        "ge_model",
        "ae_model",
        "temperature",
        "max_tokens",
        "timeout",
        "max_retries",
        "system_prompt",
    ):
        item = value.get(key)
        if item is not None and item != "":
            normalized[key] = item
    if "provider" in normalized and "provider_code" not in normalized:
        normalized["provider_code"] = normalized.pop("provider")
    return normalized


def _business_rule_ref(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_type": rule.get("rule_type"),
        "asset_key": rule.get("asset_key"),
        "rule_asset_id": rule.get("rule_asset_id"),
        "rule_asset_version": rule.get("rule_asset_version"),
        "rule_id": rule.get("rule_id"),
    }


def _keyword_asset_ref(asset: AssetRegistry | None, asset_key: str, *, inline: bool = False) -> dict[str, Any]:
    if inline:
        return {
            "asset_type": SYSTEM_KEYWORD_ASSET_TYPE,
            "asset_key": asset_key,
            "source": "inline_preview",
        }
    if asset:
        return {
            "asset_type": asset.asset_type,
            "asset_key": asset.asset_key,
            "asset_id": asset.id,
            "version_no": asset.version_no,
            "source": "asset_registry",
        }
    return {
        "asset_type": SYSTEM_KEYWORD_ASSET_TYPE,
        "asset_key": asset_key,
        "source": "fallback",
    }
