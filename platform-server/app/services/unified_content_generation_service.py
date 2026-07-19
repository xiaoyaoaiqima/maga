"""Build unified content generation inputs from business rules and keyword assets."""
from __future__ import annotations

import json
import re
import secrets
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
    "article_speaking_style": 35,
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
        layered_article = content_type == "article" and _uses_layered_article_prompt(business_rule)
        rule_corpus_article = content_type == "article" and _uses_rule_corpus_as_prompt(business_rule)
        comment_prompt_bundle = content_type == "comment" and _uses_comment_prompt_bundle(business_rule)
        if layered_article or rule_corpus_article or comment_prompt_bundle:
            resolved_keyword_asset_key = ""
            keyword_asset = None
            selected_keywords: list[dict[str, Any]] = []
        else:
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
        business_rule, selected_keywords, slot_coherence = _apply_article_slot_coherence(
            content_type=content_type,
            business_rule=business_rule,
            selected_keywords=selected_keywords,
        )
        selected_prompt_slots = (
            _select_comment_prompt_slots(business_rule)
            if content_type == "comment"
            and (not comment_prompt_bundle or _uses_explicit_bundle_prompt_slots(business_rule))
            else []
        )
        selected_comment_tone = (
            None
            if comment_prompt_bundle
            else _select_comment_tone(business_rule, item_no=item_no)
            if content_type == "comment"
            else None
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
        comment_output_format = (
            _comment_output_format_config(business_rule)
            if content_type == "comment"
            else {}
        )
        if content_type == "comment":
            if comment_prompt_bundle:
                rendered_prompt = _comment_prompt_bundle_text(
                    business_rule,
                    output_format=comment_output_format,
                    selected_prompt_slots=selected_prompt_slots,
                )
            else:
                rendered_prompt = _comment_prompt_text(
                    business_rule,
                    selected_prompt_slots=selected_prompt_slots,
                    comment_tone=selected_comment_tone,
                    output_format=comment_output_format,
                    selected_keywords=selected_keywords,
                )
            rendered_prompt = _normalize_comment_prompt_labels(rendered_prompt)
        else:
            if _uses_royal_compact_prompt(business_rule):
                rendered_prompt = _royal_compact_article_prompt(
                    business_rule,
                    selected_keywords=selected_keywords,
                    output_format=str(variables.get("output_format_requirement") or ""),
                )
            elif _uses_layered_article_prompt(business_rule):
                rendered_prompt = _layered_article_prompt(
                    business_rule,
                    selected_keywords=selected_keywords,
                    output_format=str(variables.get("output_format_requirement") or ""),
                )
            elif _uses_rule_corpus_as_prompt(business_rule):
                rendered_prompt = _rule_corpus_as_prompt_article_prompt(
                    variables,
                    selected_keywords=selected_keywords,
                )
            else:
                rendered_prompt = _render_template(expert["prompt_template"], variables)
                rendered_prompt = _normalize_expression_corpus_labels(rendered_prompt)
                rendered_prompt = _append_final_output_format(
                    rendered_prompt,
                    str(variables.get("output_format_requirement") or ""),
                )
        keyword_asset_ref = (
            None
            if layered_article or rule_corpus_article or comment_prompt_bundle
            else _keyword_asset_ref(
                keyword_asset,
                resolved_keyword_asset_key,
                inline=keyword_content_override is not None,
            )
        )
        input_snapshot = {
            "schema_version": "1",
            "capability": CONTENT_GENERATE_CAPABILITY,
            "content_type": content_type,
            "output_fields": output_fields,
            "business_rule": business_rule,
            "selected_keywords": selected_keywords,
            "selected_prompt_slots": selected_prompt_slots,
            "comment_tone": selected_comment_tone,
            "output_format": comment_output_format,
            "output_format_mode": comment_output_format.get("mode"),
            "expansion_count": comment_output_format.get("count"),
            "slot_coherence": slot_coherence,
            "keyword_asset": keyword_asset_ref,
            "expert": expert,
            "model_config": expert["model_config"],
            "template_variables": variables,
            "rendered_prompt": rendered_prompt,
        }
        return UnifiedGenerationSnapshot(
            input_snapshot=input_snapshot,
            asset_refs={
                "business_rule": _business_rule_ref(business_rule),
                "keyword_asset": keyword_asset_ref,
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


_PURCHASE_DECISION_CLOSURE_RE = re.compile(
    r"[，,；;。]?"
    r"(?:这点|这个|这样|所以)?[^，,。！？；;\n]{0,12}"
    r"(?:挺)?愿意继续(?:买|用)"
    r"|[，,；;。]?"
    r"(?:这点|这个|这样|所以)?[^，,。！？；;\n]{0,12}"
    r"(?:还会|继续|愿意)(?:回购|复购)"
)


def _apply_article_slot_coherence(
    *,
    content_type: str,
    business_rule: dict[str, Any],
    selected_keywords: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Repair proven slot conflicts before rendering the generation prompt."""

    if content_type != "article" or not isinstance(business_rule, dict) or not _is_wangyue_article_rule(business_rule):
        return business_rule, selected_keywords, {"actions": []}

    patched_rule = dict(business_rule)
    patched_keywords = [dict(item) for item in selected_keywords]
    actions: list[dict[str, Any]] = []

    ending_keyword = next(
        (
            item
            for item in patched_keywords
            if str(item.get("category_code") or "") == "article_real_ending_texture"
        ),
        None,
    )
    has_life_action_ending = False
    if ending_keyword:
        ending_code = str(ending_keyword.get("keyword_code") or "")
        ending_text = " ".join(str(line or "") for line in ending_keyword.get("corpus") or [])
        has_life_action_ending = (
            ending_code
            in {
                "ending_child_small_reaction_v332",
                "ending_action_unfinished_v332",
                "ending_return_current_scene_v332",
            }
            or any(marker in ending_text for marker in ("孩子", "小反应", "小动作", "生活现场", "动作"))
        )

    source_text = " ".join(
        str(patched_rule.get(key) or "")
        for key in (
            "selling_description",
            "selling_kernel",
            "story_spine",
        )
    )
    if not has_life_action_ending or not _PURCHASE_DECISION_CLOSURE_RE.search(source_text):
        return patched_rule, patched_keywords, {"actions": actions}

    for key in ("selling_description", "selling_kernel"):
        before = str(patched_rule.get(key) or "")
        after = _strip_purchase_decision_closure(before)
        if after != before:
            patched_rule[key] = after
            actions.append(
                {
                    "action": "strip_purchase_decision_closure",
                    "field": key,
                    "before": before,
                    "after": after,
                    "reason": "purchase-decision closure conflicts with life-action ending",
                }
            )
    if actions:
        patched_rule["slot_coherence_note"] = (
            "已在生文前移除购买决策收口，避免产品总结后再硬接生活动作尾巴；"
            "产品好处和生活现场仍保留。"
        )
    return patched_rule, patched_keywords, {"actions": actions}


def _strip_purchase_decision_closure(text: str) -> str:
    cleaned = _PURCHASE_DECISION_CLOSURE_RE.sub("", str(text or ""))
    cleaned = re.sub(r"[，,；;。]\s*([。；;，,])", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.strip("，,；; ")
    return cleaned


def _template_variables(
    *,
    content_type: str,
    output_fields: list[str],
    business_rule: dict[str, Any],
    selected_keywords: list[dict[str, Any]],
) -> dict[str, Any]:
    multi_output_group = business_rule.get("multi_output_group")
    slot_rotation_no = business_rule.get("item_no")
    if isinstance(multi_output_group, dict):
        if multi_output_group.get("group_no") is not None:
            slot_rotation_no = multi_output_group.get("group_no")
        else:
            try:
                item_no = max(1, int(business_rule.get("item_no") or 1))
                requested_count = max(1, int(multi_output_group.get("requested_count") or 1))
                slot_rotation_no = ((item_no - 1) // requested_count) + 1
            except (TypeError, ValueError):
                pass
    return {
        "item_no": business_rule.get("item_no"),
        "slot_rotation_no": slot_rotation_no,
        "content_type": content_type,
        "content_type_label": "评论" if content_type == "comment" else "文章",
        "output_fields": "、".join(output_fields),
        "business_rule": _business_rule_text(business_rule, content_type=content_type),
        "selling_painpoint_group": business_rule.get("selling_painpoint_group"),
        "selling_painpoint_expression": business_rule.get("selling_painpoint_expression"),
        "keyword_corpus": ""
        if content_type == "comment"
        else _keyword_corpus_text(
            selected_keywords,
            content_type=content_type,
            output_fields=output_fields,
            business_rule=business_rule,
        ),
        "selected_keywords_json": json.dumps(selected_keywords, ensure_ascii=False, indent=2),
        "generation_requirements": _generation_requirements(
            content_type,
            output_fields,
            business_rule,
            selected_keywords,
        ),
        "output_format_requirement": _article_output_format_requirement(content_type, output_fields, business_rule) or "",
    }


def _business_rule_text(rule: dict[str, Any], *, content_type: str | None = None) -> str:
    if content_type == "comment":
        return _comment_rule_text(rule)

    lines: list[str] = []
    if content_type == "article":
        if _uses_rule_corpus_as_prompt(rule):
            corpus_text = str(rule.get("corpus") or "").strip()
            return _sanitize_wangyue_business_rule_text(corpus_text) if corpus_text else ""
        # 文章业务规则由运营直接写成可读的写作规则；prompt 里不再重复渲染
        # rule name / corpus label，避免工程字段污染生成。
        context_line = _article_structured_context_line(rule)
        if context_line:
            lines.append(context_line)
        story_spine_line = _article_story_spine_context_line(rule)
        if story_spine_line:
            lines.append(story_spine_line)
        selling_surface_line = _article_selling_surface_context_line(rule)
        if selling_surface_line:
            lines.append(selling_surface_line)
        corpus_text = str(rule.get("corpus") or "").strip()
        if _is_wangyue_article_rule(rule):
            corpus_text = _sanitize_wangyue_business_rule_text(corpus_text)
        if corpus_text:
            lines.append(corpus_text)
    if not lines:
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
    title_reference_examples = [
        str(item).strip()
        for item in rule.get("title_reference_examples") or []
        if str(item).strip()
    ]
    if content_type == "article" and title_reference_examples:
        lines.append(
            "- 真人标题参考：以下标题来自真实小红书帖子，只借标题形式，不照搬标题、品牌事实、年龄、时长或具体结论；"
            "生成标题不得与任一真实标题样本完全一致；"
            "标题可以是产品名短标题、选奶问题、真实反馈、纠结记录、开罐记录，也可以很短。"
            "不要写空泛模板标题，例如“旺玥真实体验分享”“旺玥喝了一阵”“喝旺玥的日常”；"
            "不要写作文观点句或广告 slogan。"
        )
        lines.append("- 真实标题样本：\n" + "\n".join(f"  - {item}" for item in title_reference_examples))
    exclude_example_terms = _content_path_exclude_example_terms(rule)
    real_user_examples = [
        item
        for item in rule.get("real_user_examples") or []
        if isinstance(item, dict) and str(item.get("text") or "").strip()
        and not _example_matches_excluded_terms(item, exclude_example_terms)
    ]
    if real_user_examples:
        route_examples = [item for item in real_user_examples if item.get("example_layer") == "route"]
        detail_examples = [item for item in real_user_examples if item.get("example_layer") == "detail"]
        title_shape_examples = [item for item in real_user_examples if item.get("example_layer") == "title_shape"]
        opening_examples = [item for item in real_user_examples if item.get("example_layer") == "opening_texture"]
        texture_examples = [item for item in real_user_examples if item.get("example_layer") == "texture"]
        ending_examples = [item for item in real_user_examples if item.get("example_layer") == "ending"]
        note_examples = [
            item
            for item in real_user_examples
            if item.get("source_type") == "note"
            and item.get("example_layer") not in {"route", "detail", "title_shape", "opening_texture", "texture", "ending"}
        ]
        comment_examples = [item for item in real_user_examples if item.get("source_type") == "comment"]
        opening_ending_examples = [*opening_examples, *ending_examples]
        if route_examples or detail_examples or title_shape_examples or opening_examples or texture_examples or ending_examples:
            lines.append(
                "- 真人素材使用边界：业务规则优先。以下素材都是低权重参考，可以完全不用；"
                "内容入口只借切入启发，标题只借形态，不借产品词、年龄、功效承诺或测评栏目感，口气只借毛边；"
                "不要照搬事实、顺序、因果链，也不要把多个素材拼成一篇。"
            )
        else:
            lines.append(
                "- 全量真人原句池使用边界：以下内容是本次检索抽到的真人原句纹理，只借生活入口、语气和句子毛边；"
                "不要照抄原句、标题、品牌事实、数字、功效结论或评论问法。帖子正文优先参考帖子原句，"
                "评论原句只能提供口气和真实短句感，不能写成评论区回复。"
            )
        if route_examples:
            lines.append(
                "- 低权重内容入口（可不用，只借切入方式）：\n"
                + "\n".join(f"  - {_real_user_example_text(item)}" for item in route_examples)
            )
        if title_shape_examples:
            lines.append("- 可借标题形态：\n" + "\n".join(f"  - {_real_user_example_text(item)}" for item in title_shape_examples))
        if detail_examples:
            lines.append("- 可借生活细节颗粒：\n" + "\n".join(f"  - {_real_user_example_text(item)}" for item in detail_examples))
        if opening_ending_examples:
            lines.append("- 可借开头/收尾：\n" + "\n".join(f"  - {_real_user_example_text(item)}" for item in opening_ending_examples))
        if texture_examples:
            lines.append("- 可借说话口气：\n" + "\n".join(f"  - {_real_user_example_text(item)}" for item in texture_examples))
        if note_examples:
            lines.append("- 本次抽到的帖子原句纹理：\n" + "\n".join(f"  - {_real_user_example_text(item)}" for item in note_examples))
        if comment_examples:
            lines.append("- 本次抽到的评论短句纹理：\n" + "\n".join(f"  - {_real_user_example_text(item)}" for item in comment_examples))
    if content_type == "article" and _is_wangyue_article_rule(rule):
        expression_paths = [
            str(item).strip()
            for item in rule.get("expression_reference_paths") or []
            if str(item).strip()
        ]
        expression_phrases = [
            str(item).strip()
            for item in rule.get("expression_reference_phrases") or []
            if str(item).strip()
        ]
        if expression_paths or expression_phrases:
            if expression_paths:
                lines.append(
                    "- 本篇节奏（可不用；学意思和节奏，正文要换说法、换位置，不直接复用原句）：\n"
                    + "\n".join(f"  - {item}" for item in expression_paths)
                )
            if expression_phrases:
                lines.append(
                    "- 本篇短句口气（可不用；只当语气方向，正文要换词或不用）：\n"
                    + "\n".join(f"  - {item}" for item in expression_phrases)
                )
    has_wangyue_expression_reference = (
        content_type == "article"
        and _is_wangyue_article_rule(rule)
        and (rule.get("expression_reference_paths") or rule.get("expression_reference_phrases"))
    )
    if not has_wangyue_expression_reference and rule.get("render_reference_examples") is not False:
        examples = [
            str(item).strip()
            for item in rule.get("examples") or []
            if str(item).strip() and not _text_matches_excluded_terms(str(item), exclude_example_terms)
        ]
        supplements = [
            str(item).strip()
            for item in rule.get("supplements") or []
            if str(item).strip() and not _text_matches_excluded_terms(str(item), exclude_example_terms)
        ]
        prompt_examples = examples + supplements
        if prompt_examples:
            if content_type == "article" and _is_wangyue_article_rule(rule):
                lines.append("- 表达参考：以下内容可以不用；只借说话方式，不照搬事实和句式。")
                label = "参考内容" if any(len(item) > 50 for item in prompt_examples) else "参考短句"
                lines.append(f"- {label}：\n" + "\n".join(f"  - {item}" for item in prompt_examples))
            else:
                # 重要逻辑：规则内示例只给短句毛边，不再决定正文路线。
                lines.append(
                    "- 规则内示例边界：以下示例是低权重短句纹理，可以完全不用；"
                    "只借语气毛边，不借事实、顺序、因果链或固定句式骨架。"
                )
                lines.append("- 规则内短句纹理（弱参考，可不用）：\n" + "\n".join(f"  - {item}" for item in prompt_examples))
    if not lines:
        lines.append(json.dumps(rule, ensure_ascii=False, indent=2))
    return "\n".join(lines)


def _comment_rule_text(rule: dict[str, Any]) -> str:
    lines: list[str] = []
    corpus_text = str(rule.get("corpus") or "").strip()
    if corpus_text:
        lines.append(corpus_text)
    elif rule.get("business_rule"):
        lines.append(str(rule.get("business_rule") or "").strip())

    exclude_example_terms = _content_path_exclude_example_terms(rule)
    examples = [
        str(item).strip()
        for item in rule.get("examples") or []
        if str(item).strip() and not _text_matches_excluded_terms(str(item), exclude_example_terms)
    ]
    supplements = [
        str(item).strip()
        for item in rule.get("supplements") or []
        if str(item).strip() and not _text_matches_excluded_terms(str(item), exclude_example_terms)
    ]
    prompt_examples = examples + supplements
    if prompt_examples:
        lines.append(
            "参考示例只学习真人语气和评论形态，不照抄、不固定句式：\n"
            + "\n".join(f"- {item}" for item in prompt_examples)
        )
    if not lines:
        return json.dumps(rule, ensure_ascii=False, indent=2)
    return "\n".join(lines)


def _comment_keyword_prompt_layers(selected_keywords: list[dict[str, Any]]) -> dict[str, list[str]]:
    layers = {
        "instruction": [],
        "speaking_style": [],
        "format": [],
    }
    category_to_layer = {
        "comment_generation_requirement": "instruction",
        "comment_writing_instruction": "instruction",
        "comment_speaking_style": "speaking_style",
        "comment_format_control": "format",
    }
    for item in selected_keywords:
        layer = category_to_layer.get(str(item.get("category_code") or "").strip())
        if not layer:
            continue
        for raw_line in item.get("corpus") or []:
            line = str(raw_line or "").strip()
            if line and line not in layers[layer]:
                layers[layer].append(line)
    return layers


def _comment_prompt_text(
    rule: dict[str, Any],
    *,
    selected_prompt_slots: list[dict[str, Any]] | None = None,
    comment_tone: dict[str, str] | None = None,
    output_format: dict[str, Any] | None = None,
    selected_keywords: list[dict[str, Any]] | None = None,
) -> str:
    if _uses_comment_prompt_bundle(rule):
        return _comment_prompt_bundle_text(
            rule,
            output_format=output_format or _comment_output_format_config(rule),
            selected_prompt_slots=selected_prompt_slots,
        )
    product_name = _comment_product_name(rule)
    major = str(rule.get("business_rule") or "").split("-", 1)[0].strip()
    context = _comment_context_line(rule, product_name)
    focus = _comment_focus_line(rule)
    content_direction = str(rule.get("content_direction") or rule.get("corpus") or "").strip()
    activity_material = _comment_activity_material_lines(rule)
    notes = _comment_prompt_notes(rule)
    if comment_tone:
        notes = [
            *notes,
            "语气槽只控制说法，不提供事实；不要因此新增购买经历、喂养方式、宝宝状态或使用结果。",
        ]
    examples = _comment_prompt_examples(rule)
    output_format = output_format or _comment_output_format_config(rule)
    generation_lines: list[str] = []
    configured = str(rule.get("generation_requirements") or "").strip()
    if configured:
        generation_lines.append(configured)
    generation_lines.extend(_comment_generation_lines(output_format))
    keyword_layers = _comment_keyword_prompt_layers(selected_keywords or [])

    if _is_a2_sentiment_comment_rule(rule):
        lines = []
    elif major == "有货":
        lines = [context]
    else:
        lines = [
            f"你是一位妈妈，在小红书母婴评论区回复别人关于{product_name}的帖子。",
            "",
            context,
        ]
    if keyword_layers["instruction"]:
        lines.extend(["", "生文指令：", *[f"- {line}" for line in keyword_layers["instruction"]]])
    if keyword_layers["speaking_style"]:
        lines.extend(["", "说话方式：", *[f"- {line}" for line in keyword_layers["speaking_style"]]])
    if _is_a2_sentiment_comment_rule(rule) and content_direction:
        lines.extend(["", "内容方向：", content_direction])
    elif rule.get("content_direction") and content_direction:
        lines.extend(["", "内容方向：", content_direction])
    elif focus:
        lines.extend(["", focus])
    if activity_material:
        lines.extend(["", "本篇素材：", *[f"- {line}" for line in activity_material]])
    if comment_tone:
        tone_label = str(comment_tone.get("tone_label") or "本条语气").strip()
        tone_prompt = str(comment_tone.get("prompt") or "").strip()
        if tone_prompt:
            lines.extend(["", "本条语气槽：", f"{tone_label}：{tone_prompt}"])
    for slot in selected_prompt_slots or []:
        rendered_slot = _render_comment_prompt_slot(slot)
        if rendered_slot:
            lines.extend(["", rendered_slot])
    if keyword_layers["format"]:
        lines.extend(["", "写法：", *[f"- {line}" for line in keyword_layers["format"]]])
    if notes:
        lines.extend(["", "注意：", *[f"- {note}" for note in notes]])
    if examples:
        lines.extend(["", "以下参考示例仅供参考，不照抄、不固定句式：", *[f"- {item}" for item in examples]])
    if _is_a2_sentiment_comment_rule(rule):
        lines.extend(["", *generation_lines])
    else:
        lines.extend(["", "【生成要求】", *generation_lines])
    return "\n".join(line for line in lines if line is not None).strip()


def _uses_comment_prompt_bundle(rule: dict[str, Any]) -> bool:
    return (
        str(rule.get("prompt_mode") or "").strip() == "comment_prompt_bundle"
        and isinstance(rule.get("comment_prompt_bundle"), dict)
    )


def _uses_explicit_bundle_prompt_slots(rule: dict[str, Any]) -> bool:
    return (
        _uses_comment_prompt_bundle(rule)
        and str(rule.get("bundle_prompt_slots_source") or "").strip() == "batch_override"
        and isinstance(rule.get("prompt_slots"), dict)
    )


def _comment_prompt_bundle_text(
    rule: dict[str, Any],
    *,
    output_format: dict[str, Any],
    selected_prompt_slots: list[dict[str, Any]] | None = None,
) -> str:
    bundle = rule.get("comment_prompt_bundle") if isinstance(rule.get("comment_prompt_bundle"), dict) else {}
    generation_instruction = str(bundle.get("generation_instruction") or "").strip()
    content_direction = str(bundle.get("content_direction") or "").strip()
    activity_material = _comment_bundle_lines(bundle.get("activity_material"))
    writing_requirements = _comment_bundle_lines(bundle.get("writing_requirements"))
    notes = _comment_bundle_lines(bundle.get("notes"))
    lines: list[str] = []
    if generation_instruction:
        lines.extend(["生文指令：", f"- {generation_instruction}"])
    if content_direction:
        lines.extend(["", "内容方向：", content_direction])
    for slot in selected_prompt_slots or []:
        rendered_slot = _render_comment_prompt_slot(slot)
        if rendered_slot:
            lines.extend(["", rendered_slot])
    if activity_material:
        lines.extend(["", "内容素材：", *[f"- {item}" for item in activity_material]])
    if writing_requirements:
        lines.extend(["", "写法：", *[f"- {item}" for item in writing_requirements]])
    if notes:
        lines.extend(["", "生成要求：", *[f"- {item}" for item in notes]])
    lines.extend(["", *_comment_generation_lines(output_format)])
    return "\n".join(lines).strip()


def _comment_bundle_lines(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items: list[Any] = re.split(r"\|\||[\n\r]+", value)
    elif isinstance(value, list):
        raw_items = value
    else:
        return []
    lines: list[str] = []
    for raw_item in raw_items:
        line = re.sub(r"^\s*[-*•]\s*", "", str(raw_item or "")).strip()
        if line and line not in lines:
            lines.append(line)
    return lines


def _comment_activity_material_lines(rule: dict[str, Any]) -> list[str]:
    raw_material = rule.get("activity_material") or rule.get("activity_materials") or []
    if isinstance(raw_material, str):
        raw_items: list[Any] = raw_material.splitlines()
    elif isinstance(raw_material, list):
        raw_items = raw_material
    else:
        return []
    lines: list[str] = []
    for raw_item in raw_items:
        line = re.sub(r"^\s*[-*•]\s*", "", str(raw_item or "")).strip()
        if line and line not in lines:
            lines.append(line)
    return lines


def _comment_generation_lines(output_format: dict[str, Any]) -> list[str]:
    mode = str(output_format.get("mode") or "plain_comment").strip()
    count = _positive_int(output_format.get("count"), default=1)
    if mode == "json_string_array":
        return [
            f"生成 {count} 条评论。",
            "只输出 JSON 字符串数组，不要标题、编号、解释。",
        ]
    if mode == "json_object_array":
        return [
            f"生成 {count} 条评论。",
            '只输出 JSON 对象数组，每个对象包含 "comment" 字段，不要标题、编号、解释。',
        ]
    return ["只输出评论正文，不要标题、编号、解释。"]


def _comment_output_format_config(rule: dict[str, Any]) -> dict[str, Any]:
    raw_config = rule.get("output_format") if isinstance(rule.get("output_format"), dict) else {}
    raw_mode = (
        rule.get("output_format_mode")
        or raw_config.get("mode")
        or raw_config.get("output_format_mode")
        or "plain_comment"
    )
    mode = str(raw_mode or "plain_comment").strip()
    if mode not in {"plain_comment", "json_string_array", "json_object_array"}:
        mode = "plain_comment"
    count = _positive_int(
        rule.get("expansion_count")
        or raw_config.get("count")
        or raw_config.get("expansion_count")
        or 1,
        default=1,
    )
    if mode == "plain_comment":
        count = 1
    return {"mode": mode, "count": count}


def _positive_int(value: Any, *, default: int = 1, minimum: int = 1, maximum: int = 100) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _select_comment_prompt_slots(rule: dict[str, Any]) -> list[dict[str, Any]]:
    slots = _normalize_comment_prompt_slots(
        rule.get("prompt_slots") or rule.get("comment_prompt_slots")
    )
    slots.extend(_normalize_comment_prompt_slots(rule.get("variation_slots")))
    selected: list[dict[str, Any]] = []
    for slot in slots:
        entries = slot["entries"]
        index = _random_choice_index(len(entries))
        selected.append(
            {
                "slot_name": slot["slot_name"],
                "text": entries[index],
                "selected_index": index,
                "candidate_count": len(entries),
            }
        )
    return selected


def _select_comment_tone(rule: dict[str, Any], *, item_no: int) -> dict[str, str] | None:
    raw_options = rule.get("comment_tone_options") or rule.get("comment_persona_options")
    if not isinstance(raw_options, list):
        return None
    options = [
        {
            "tone_code": str(item.get("tone_code") or item.get("persona_code") or "").strip(),
            "tone_label": str(item.get("tone_label") or item.get("persona_label") or "").strip(),
            "prompt": str(item.get("prompt") or "").strip(),
        }
        for item in raw_options
        if isinstance(item, dict) and str(item.get("prompt") or "").strip()
    ]
    if not options:
        return None
    return options[(max(1, int(item_no)) - 1) % len(options)]


def _normalize_comment_prompt_slots(raw_slots: Any) -> list[dict[str, Any]]:
    if not raw_slots:
        return []
    normalized: list[dict[str, Any]] = []
    if isinstance(raw_slots, dict):
        iterator = raw_slots.items()
        for slot_name, raw_entries in iterator:
            entries = _comment_prompt_slot_entries(str(slot_name), raw_entries)
            if entries:
                normalized.append({"slot_name": str(slot_name).strip(), "entries": entries})
        return normalized
    if isinstance(raw_slots, list):
        for item in raw_slots:
            if not isinstance(item, dict):
                continue
            slot_name = str(item.get("slot_name") or item.get("name") or item.get("槽位") or "").strip()
            raw_entries = (
                item.get("entries")
                or item.get("options")
                or item.get("corpus")
                or item.get("items")
                or item.get("语料")
            )
            entries = _comment_prompt_slot_entries(slot_name, raw_entries)
            if slot_name and entries:
                normalized.append({"slot_name": slot_name, "entries": entries})
    return normalized


def _comment_prompt_slot_entries(slot_name: str, raw_entries: Any) -> list[str]:
    if isinstance(raw_entries, str):
        entries = [line.strip() for line in re.split(r"[\n\r]+", raw_entries) if line.strip()]
    elif isinstance(raw_entries, list):
        entries = [str(item).strip() for item in raw_entries if str(item).strip()]
    else:
        entries = []
    if _is_comment_style_slot(slot_name):
        invalid = [entry for entry in entries if _comment_style_text_has_business_terms(entry)]
        if invalid:
            raise ValueError(
                "说话风格槽位不能包含业务元素: "
                + "；".join(invalid[:3])
            )
    return entries


def _is_comment_style_slot(slot_name: str) -> bool:
    normalized = str(slot_name or "").strip().lower()
    return normalized in {"说话风格", "说话方式", "comment_style", "speaking_style", "comment_speaking_style"}


def _comment_style_text_has_business_terms(text: str) -> bool:
    business_terms = [
        "a2",
        "A2",
        "至初",
        "源悦",
        "爱他美",
        "美素",
        "皇家",
        "批批检",
        "每批",
        "检测",
        "质检",
        "扫码",
        "扫罐",
        "报告",
        "蜡毒",
        "蜡样",
        "溯源码",
        "罐底",
        "转奶",
        "换奶",
        "会员",
        "集罐",
        "积分",
        "换礼",
        "老客",
        "导购",
        "山姆",
        "到货",
        "有货",
    ]
    return any(term in str(text or "") for term in business_terms)


def _random_choice_index(count: int) -> int:
    if count <= 0:
        raise ValueError("count must be positive")
    return secrets.randbelow(count)


def _render_comment_prompt_slot(slot: dict[str, Any]) -> str:
    slot_name = str(slot.get("slot_name") or "").strip()
    text = str(slot.get("text") or "").strip()
    if not slot_name or not text:
        return ""
    if slot_name == "本条活动事实":
        return text
    if text.startswith(f"{slot_name}：") or text.startswith(f"{slot_name}:"):
        return text
    return f"{slot_name}：{text}"


def _comment_product_name(rule: dict[str, Any]) -> str:
    text = " ".join(
        str(rule.get(key) or "")
        for key in ("asset_key", "quality_guard_profile_key", "business_rule", "corpus", "generation_requirements")
    )
    if any(marker in text for marker in ("源悦", "飞鹤")):
        return "源悦奶粉"
    if any(marker in text for marker in ("a2", "A2", "至初")) or "a2_sentiment" in text:
        return "a2奶粉"
    return "这款奶粉"


def _comment_context_line(rule: dict[str, Any], product_name: str) -> str:
    major = str(rule.get("business_rule") or "").split("-", 1)[0].strip()
    if _is_a2_sentiment_comment_rule(rule):
        return str(rule.get("scenario_post_context") or "").strip()
    if major == "有货":
        return (
            f"你是一位妈妈，之前一直买{product_name}，但前段时间{product_name}没货了，一直没买到，"
            "今天突然发现有货了，然后你买了，买完之后你想去小红书上跟别人分享这个信息。"
            f"于是你要在一个说{product_name}缺货了，没货了的帖子下面写一条评论。"
        )
    if major == "批批检":
        return f"你看到有人在聊{product_name}的检测报告或扫码信息，想把自己能看到的报告信息顺手补一句。"
    if major == "转奶":
        return f"你看到有人在聊转奶或换奶，想结合自己对{product_name}的选择回一条自然评论。"
    if major == "会员权益":
        return f"你看到有人在聊{product_name}会员权益活动，想把自己看到的信息顺手说一下。"
    return f"你看到有人在聊{product_name}，想结合自己的真实想法回一条自然评论。"


def _comment_focus_line(rule: dict[str, Any]) -> str:
    major = str(rule.get("business_rule") or "").split("-", 1)[0].strip()
    corpus = str(rule.get("corpus") or "").strip()
    if not corpus:
        return ""
    if major == "有货":
        return ""
    if major == "批批检":
        return "可以围绕自己扫码、看报告入口、看到检测报告或报告信息来写。"
    if major == "转奶":
        return "可以围绕转奶折腾、怕不适应、喝熟悉款这些真实顾虑来写。"
    if major == "会员权益":
        return "可以围绕会员权益、集罐、积分、换礼或老客活动这些信息来写。"
    return f"可以围绕这个意思来写：{corpus}"


def _comment_prompt_notes(rule: dict[str, Any]) -> list[str]:
    major = str(rule.get("business_rule") or "").split("-", 1)[0].strip()
    is_a2_comment = _is_a2_sentiment_comment_rule(rule)
    notes = [] if is_a2_comment else ["评论内容不用很丰富，简单表达含义和情绪即可。"]
    if major != "有货":
        notes.append("不要写成品牌公告、客服回复、科普说明或广告口播。")
    if is_a2_comment:
        notes.append("不要说缺货、断粮等消极词。")
        if _a2_comment_needs_competitor_generalization_note(rule):
            notes.append("不要直接说其他奶粉品牌名，如需提到对比或转奶对象，用其他品牌、别的牌子、其他奶粉、之前的奶粉这类泛化说法。")
        if major == "会员权益":
            notes.append("具体活动事实只按“本条要写的事”中明确内容说；参考示例只学表达，不把礼品、门槛、领取或中奖结果扩成新事实。")
    if major == "有货" and not is_a2_comment:
        notes.append("字数在10到20字之间。")
    else:
        notes.append("字数不要超过80字。" if is_a2_comment else "字数不要超过80字，具体长短参考示例。")
    return notes


def _a2_comment_needs_competitor_generalization_note(rule: dict[str, Any]) -> bool:
    if not _is_a2_sentiment_comment_rule(rule):
        return False
    source = "\n".join(
        [
            str(rule.get("business_rule") or ""),
            str(rule.get("scenario_guard_keyword") or ""),
            *[str(item) for item in rule.get("examples") or []],
        ]
    )
    markers = (
        "转奶",
        "转回",
        "其他品牌",
        "其他奶粉",
        "别的牌子",
        "爱他美",
        "达能",
        "美素",
        "皇美",
        "皇家",
    )
    return any(marker in source for marker in markers) or bool(re.search(r"换奶(?!粉)", source))


def _comment_prompt_examples(rule: dict[str, Any]) -> list[str]:
    exclude_example_terms = _content_path_exclude_example_terms(rule)
    examples = [
        str(item).strip()
        for item in rule.get("examples") or []
        if str(item).strip() and not _text_matches_excluded_terms(str(item), exclude_example_terms)
    ]
    supplements = [
        str(item).strip()
        for item in rule.get("supplements") or []
        if str(item).strip() and not _text_matches_excluded_terms(str(item), exclude_example_terms)
    ]
    prompt_examples = examples + supplements
    if _is_a2_sentiment_comment_rule(rule):
        prompt_examples = [_generalize_a2_comment_competitor_terms(item) for item in prompt_examples]
    major = str(rule.get("business_rule") or "").split("-", 1)[0].strip()
    corpus = str(rule.get("corpus") or "")
    if major == "有货" and any(marker in corpus for marker in ("导购", "门店", "山姆", "线上")):
        picked: list[str] = []
        for marker in ("山姆", "线上", "导购"):
            match = next((item for item in prompt_examples if marker in item and item not in picked), "")
            if match:
                picked.append(match)
        if len(picked) >= 3:
            return picked[:3]
    return prompt_examples[:6]


def _is_a2_sentiment_comment_rule(rule: dict[str, Any]) -> bool:
    text = " ".join(str(rule.get(key) or "") for key in ("asset_key", "quality_guard_profile_key", "business_rule", "corpus"))
    return "a2_sentiment" in text or "a2" in text or "A2" in text or "至初" in text


def _generalize_a2_comment_competitor_terms(text: str) -> str:
    value = str(text or "")
    competitor_terms = (
        "超启能恩",
        "皇家美素",
        "美赞臣",
        "星飞帆",
        "爱他美",
        "君乐宝",
        "贝因美",
        "合生元",
        "诺优能",
        "达能",
        "雀巢",
        "美素",
        "皇美",
        "飞鹤",
        "惠氏",
        "启赋",
        "雅培",
    )
    for term in competitor_terms:
        value = re.sub(rf"(之前|原来|以前)(?:喝|吃)?{re.escape(term)}", "之前的奶粉", value)
        value = re.sub(rf"(一直|本来)(?:喝|吃)?{re.escape(term)}", r"\1喝之前的奶粉", value)
        value = value.replace(term, "其他品牌")
    while re.search(r"(其他品牌)(?:和|跟|、|，|,|/)(?:其他品牌)(?:也)?", value):
        value = re.sub(r"(其他品牌)(?:和|跟|、|，|,|/)(?:其他品牌)(?:也)?", "其他品牌", value)
    value = value.replace("其他品牌其他品牌", "其他品牌")
    value = value.replace("喝其他品牌", "喝其他奶粉")
    value = value.replace("换其他品牌", "换别的牌子")
    value = value.replace("转其他品牌", "转别的牌子")
    return value.strip()


def _article_structured_context_line(rule: dict[str, Any]) -> str | None:
    def clean(value: Any) -> str:
        return str(value or "").strip().rstrip("。；;，, ")

    is_wangyue = _is_wangyue_article_rule(rule)
    product_name = clean(rule.get("product_name"))
    product_appearance_mode = clean(rule.get("product_appearance_mode"))
    product_role = clean(rule.get("product_role"))
    rows: list[tuple[str, str]] = []
    if product_name:
        rows.append(("产品名", product_name))
    fields: list[tuple[str, str]] = [
        ("痛点", "painpoint"),
        ("正向证据", "positive_evidence"),
    ]
    for label, key in fields:
        value = clean(rule.get(key))
        if value:
            rows.append((label, value))
    product_relation_note = ""
    if product_appearance_mode and not is_wangyue:
        rows.append(("产品入场关系", product_appearance_mode))
        product_relation_note = "\n- 使用方式：这是产品在文中的关系，不是正文句子；可以换成同义生活说法，不照抄。"
    elif product_role and not is_wangyue:
        rows.append(("产品入场关系", product_role))
        product_relation_note = "\n- 使用方式：这是产品在文中的关系，不是正文句子；可以换成同义生活说法，不照抄。"
    if not rows:
        return None
    return "本篇信息：\n" + "\n".join(f"- {label}：{value}" for label, value in rows) + product_relation_note


def _article_story_spine_context_line(rule: dict[str, Any]) -> str | None:
    story_spine = str(rule.get("story_spine") or "").strip().rstrip("。；;，, ")
    if not story_spine:
        return None
    text = f"叙事主线：\n- {story_spine}。"
    if _is_wangyue_article_rule(rule):
        text += "\n- 使用方式：正文事件只从这条主线出；产品、卖点和正向反馈都挂在这条线上，不额外拼第二个入口或第二个收尾现场。"
    return text


def _article_selling_surface_context_line(rule: dict[str, Any]) -> str | None:
    def clean(value: Any) -> str:
        return str(value or "").strip().rstrip("。；;，, ")

    is_wangyue = _is_wangyue_article_rule(rule)
    selling_description = _drop_product_relation_prefix(
        clean(rule.get("selling_description")),
        clean(rule.get("product_appearance_mode")) or clean(rule.get("product_role")),
    )
    rows: list[tuple[str, str]] = []
    fields: list[tuple[str, str]] = [
        ("表达口吻", "selling_point_surface"),
        ("成分承接", "ingredient_surface"),
        ("好处表达", "benefit_surface"),
        ("表达机制", "expression_mechanism"),
    ]
    for label, key in fields:
        value = clean(rule.get(key))
        if value:
            rows.append((label, value))
    if is_wangyue:
        return _wangyue_product_narrative_context_line(
            clean(rule.get("product_appearance_mode")) or clean(rule.get("product_role")),
            selling_description,
        )
    if selling_description and not rows:
        text = f"产品价值任务：\n- {selling_description}"
        if not is_wangyue:
            text += "\n- 使用方式：这是本篇要传达的产品价值，不是正文句子；根据生活入口换成妈妈自己的说法，不照抄其中连续短语。"
        return text
    if selling_description:
        rows.insert(0, ("产品价值任务", selling_description))
    if not rows:
        return None
    text = "表达边界：\n" + "\n".join(f"- {label}：{value}" for label, value in rows)
    if not is_wangyue:
        text += "\n- 使用方式：这是本篇要传达的产品价值，不是正文句子；根据生活入口换成妈妈自己的说法，不照抄其中连续短语，不堆成分清单，也不要把好处写成夸张承诺。"
    return text


def _wangyue_product_narrative_context_line(relation: str, selling_description: str) -> str | None:
    relation_text = str(relation or "").strip().rstrip("。；;，, ")
    value_text = str(selling_description or "").strip().rstrip("。；;，, ")
    if not relation_text and not value_text:
        return None
    if relation_text and value_text:
        return (
            "产品叙事推进：\n"
            f"- 主线内产品信息：{relation_text}；{value_text}。\n"
            "- 使用方式：这是语义任务，不是正文句子；先顺着叙事主线写发帖由头，"
            "再让产品信息解释这条主线里的一个判断或观察，换成妈妈自己的说法，"
            "不照抄连续短语，也不要拆成产品进入、成分和反馈的并列清单。"
        )
    if relation_text:
        return (
            "产品叙事推进：\n"
            f"- 产品进入含义：{relation_text}。\n"
            "- 使用方式：这是语义任务，不是正文句子；换成妈妈自己的说法，不要硬塞产品名。"
        )
    return (
        "产品叙事推进：\n"
        f"- 产品价值含义：{value_text}。\n"
        "- 使用方式：这是语义任务，不是正文句子；旺玥出现时顺手承接，不另起一段补卖点清单。"
    )


def _drop_product_relation_prefix(selling_description: str, relation: str) -> str:
    description = str(selling_description or "").strip()
    relation_text = str(relation or "").strip().rstrip("。；;，, ")
    if not description or not relation_text:
        return description
    for separator in ("；", ";", "，", ",", "。"):
        prefix = relation_text + separator
        if description.startswith(prefix):
            return description[len(prefix):].strip()
    if description == relation_text:
        return ""
    semantic_trimmed = _drop_semantic_product_entry_prefix(description, relation_text)
    if semantic_trimmed != description:
        return semantic_trimmed
    return description


def _drop_semantic_product_entry_prefix(description: str, relation_text: str) -> str:
    if "旺玥" not in description or "旺玥" not in relation_text:
        return description
    for separator in ("；", ";", "。", "，", ","):
        if separator not in description:
            continue
        prefix, rest = description.split(separator, 1)
        prefix = prefix.strip()
        rest = rest.strip()
        if rest and _is_wangyue_entry_only_clause(prefix):
            return rest
    return description


def _is_wangyue_entry_only_clause(text: str) -> bool:
    normalized = re.sub(r"\s+", "", str(text or ""))
    if "旺玥" not in normalized:
        return False
    value_terms = (
        "钙铁锌",
        "DHA",
        "燕窝酸",
        "乳铁蛋白",
        "HMO",
        "营养",
        "状态",
        "出勤",
        "精神",
        "保护力",
        "精力",
        "接受",
        "愿意",
        "清淡",
        "奶香",
        "跑跳",
        "长个",
        "体格",
        "配得",
        "看中",
        "支持",
    )
    if any(term in normalized for term in value_terms):
        return False
    entry_patterns = (
        r"选了旺玥",
        r"选择了旺玥",
        r"选.*旺玥",
        r"买了旺玥",
        r"买.*旺玥",
        r"补了旺玥",
        r"补.*旺玥",
        r"定了旺玥",
        r"家里.*喝.*旺玥",
        r"现在.*喝.*旺玥",
        r"会说.*旺玥",
        r"提.*旺玥",
        r"聊.*旺玥",
        r"留.*旺玥",
    )
    return any(re.search(pattern, normalized) for pattern in entry_patterns)


def _real_user_example_text(item: dict[str, Any]) -> str:
    text = str(item.get("prompt_text") or item.get("text") or "").strip()
    title = str(item.get("title") or "").strip()
    tags = item.get("tags") if isinstance(item.get("tags"), list) else []
    risk_tags = item.get("risk_tags") if isinstance(item.get("risk_tags"), list) else []
    prefix = f"{title}：{text}" if title and title not in text else text
    meta_parts = []
    if tags:
        meta_parts.append("标签=" + "、".join(str(tag) for tag in tags[:4]))
    if risk_tags:
        meta_parts.append("风险提示=" + "、".join(str(tag) for tag in risk_tags[:3]))
    return prefix + (f"（{'；'.join(meta_parts)}）" if meta_parts else "")


def _content_path_exclude_example_terms(rule: dict[str, Any]) -> list[str]:
    control = rule.get("content_path_control") if isinstance(rule, dict) else None
    if not isinstance(control, dict):
        return []
    return _string_list(control.get("exclude_example_terms"))


def _example_matches_excluded_terms(item: dict[str, Any], terms: list[str]) -> bool:
    text = " ".join(
        str(value or "")
        for value in (
            item.get("prompt_text"),
            item.get("text"),
            item.get("title"),
        )
    )
    return _text_matches_excluded_terms(text, terms)


def _text_matches_excluded_terms(text: str, terms: list[str]) -> bool:
    if not terms:
        return False
    normalized = str(text or "").lower()
    return any(term.lower() in normalized for term in terms if term)


def _keyword_corpus_text(
    selected_keywords: list[dict[str, Any]],
    *,
    content_type: str | None = None,
    output_fields: list[str] | None = None,
    business_rule: dict[str, Any] | None = None,
) -> str:
    parts = []
    is_wangyue_article = content_type == "article" and isinstance(business_rule, dict) and _is_wangyue_article_rule(business_rule)
    for item in _ordered_keyword_corpus_items(selected_keywords):
        # 生成要求要放在 prompt 顶部独立生效，不再在表达扩散语料区重复出现。
        category_code = str(item.get("category_code") or "").strip()
        if category_code in GENERATION_REQUIREMENT_CATEGORY_CODES:
            continue
        if is_wangyue_article and _is_wangyue_excluded_expression_keyword(item):
            continue
        # 重要逻辑：文章业务规则已经承载篇幅和排版边界，避免再把格式控制
        # 作为一段表达扩散语料塞进 prompt，造成重复约束和工程味。
        if content_type == "article" and category_code == "article_format_control":
            continue
        corpus = item.get("corpus") or []
        corpus_text = "\n".join(
            f"  - {_sanitize_wangyue_prompt_layer_text(str(line)) if is_wangyue_article else line}"
            for line in corpus
        )
        item_boundary = _wangyue_expression_item_mainline_boundary(item, business_rule if isinstance(business_rule, dict) else {})
        if item_boundary:
            corpus_text = (corpus_text + "\n" if corpus_text else "") + f"  - 使用边界：{item_boundary}"
        if content_type == "comment":
            parts.append(corpus_text)
        else:
            parts.append(f"- {item.get('category_name')} / {item.get('keyword_name')}：\n{corpus_text}")
    if content_type == "comment":
        boundary = (
            "参考表达边界：以下只用于调语气、节奏和生活毛边；"
            "具体信息只按本条要求和参考示例已经给出的范围，不新增事实。"
            "不要照搬语料，也不要把语料扩成新的事实、固定结构、现实季节或疾病大环境。"
        )
    elif isinstance(business_rule, dict) and _uses_rule_corpus_as_prompt(business_rule):
        boundary = "表达扩散语料使用边界：以下只用于同批发散和语气变化；正文事实只按“这篇要写的事”。"
    else:
        boundary = (
            "表达扩散语料使用边界：以下只用于调语气、节奏、生活毛边和标题松散感；"
            "产品事实、成分、正向反馈、产品动作和正文事件只按业务规则里的本篇信息和叙事主线。"
            "不要照搬语料，也不要把语料扩成新的事实、第二个生活入口、第二个收尾现场、固定结构、现实季节或疾病大环境。"
        )
    expression_guidance = _article_low_priority_expression_guidance(
        content_type,
        output_fields or [],
        business_rule if isinstance(business_rule, dict) else {},
    )
    if expression_guidance:
        parts.insert(0, expression_guidance)
    if not parts:
        return ""
    return boundary + "\n" + "\n".join(parts)


def _is_wangyue_excluded_expression_keyword(item: dict[str, Any]) -> bool:
    category_code = str(item.get("category_code") or "").strip()
    if category_code == "article_speaking_style":
        return True
    return False


def _wangyue_expression_item_mainline_boundary(item: dict[str, Any], business_rule: dict[str, Any]) -> str | None:
    if not isinstance(business_rule, dict) or not _is_wangyue_article_rule(business_rule):
        return None
    if not str(business_rule.get("story_spine") or "").strip():
        return None
    category_code = str(item.get("category_code") or "").strip()
    category_name = str(item.get("category_name") or "").strip()
    keyword_name = str(item.get("keyword_name") or "").strip()
    label_text = f"{category_code} {category_name} {keyword_name}"
    if "ending" in category_code or "结尾" in label_text or "收尾" in label_text:
        return "只借收尾方式；结尾回到叙事主线已有现场，不新增第二个结尾。"
    if category_code in {"persona", "writing_method"} or any(
        marker in label_text for marker in ("生活", "身份", "场景", "入口", "家务", "对话")
    ):
        return "只借生活感和说话角度；正文事件仍从叙事主线出，不新增第二个入口。"
    return None


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


def _article_low_priority_expression_guidance(
    content_type: str | None,
    output_fields: list[str],
    business_rule: dict[str, Any],
) -> str | None:
    if content_type != "article" or output_fields != ["title", "body"] or not isinstance(business_rule, dict):
        return None
    if _uses_rule_corpus_as_prompt(business_rule):
        return None
    lines: list[str] = []
    structure_hint = _structure_slot_soft_guidance(business_rule)
    if structure_hint:
        lines.append(structure_hint)
    title_hint = _title_shape_soft_guidance(business_rule)
    if title_hint:
        lines.append(title_hint)
    scene_hint = _scene_motive_soft_guidance(business_rule)
    if scene_hint:
        lines.append(scene_hint)
    ending_hint = _ending_mode_soft_guidance(business_rule)
    if ending_hint:
        lines.append(ending_hint)
    if not lines:
        return None
    return "- 低权重表达扰动 / 主链路不变：\n" + "\n".join(f"  - {line}" for line in lines)


def _structure_slot_soft_guidance(business_rule: dict[str, Any]) -> str | None:
    slot = str(business_rule.get("structure_slot") or "").strip()
    if not slot:
        return None
    slot_hints = {
        "观察关系": "结构关系可偏观察现场，产品按业务规则自然进入。",
        "对话关系": "结构关系可像别人问起后顺口说自家情况。",
        "日常混乱": "结构关系可保留生活阻力，产品只是其中一个安排。",
        "物件关系": "结构关系可从家庭动作或物件关系里自然带出产品。",
        "现场短帖": "结构关系可像一段现场短帖，句子允许轻微跳跃。",
        "先反馈后补产品": "结构关系可生活观察在前、产品在后作为背景或原因之一。",
        "别人问起式": "结构关系可有别人问起或顺口聊到的关系，用自家情况回应。",
        "乱糟糟日常": "结构关系可保留生活里不完整的小混乱，产品只承担一个安排。",
        "物件动作带出": "结构关系可用家庭内动作或东西被处理的关系带出产品。",
        "生活现场短帖": "结构关系可像一段现场短帖，句子允许轻微跳跃。",
    }
    return slot_hints.get(slot, "结构关系只作低权重参考，不要复述结构名。")


def _title_shape_soft_guidance(business_rule: dict[str, Any]) -> str | None:
    mode = str(business_rule.get("title_shape_mode") or "").strip()
    if not mode:
        return None
    emoji_mode = str(business_rule.get("title_emoji_mode") or "").strip() if isinstance(business_rule, dict) else ""
    allows_title_emoji = emoji_mode == "TITLE_EMOJI_LIGHT" or (
        not emoji_mode
        and "无emoji" not in mode.lower()
        and "不加emoji" not in mode.lower()
        and ("emoji" in mode.lower() or any(char in mode for char in "😂🥲🙃🤏🙂🤣"))
    )
    emoji_hint = "标题可不用 emoji；适合时最多加 1 个普通生活口气 emoji。" if allows_title_emoji else "标题不加 emoji。"
    internal_hints = {
        "TITLE_SCENE_FRAGMENT": "标题形态可从正文生活现场截一个能单独看懂的短片段，别写成栏目名。",
        "TITLE_REPLY_CONTEXT": "标题形态可像顺手记下被人问起这件事，也可以直接截正文里的场景、产品或状态；别写成选品思路标题。",
        "TITLE_PROBLEM_FRAGMENT": "标题形态可抓一个真实小困扰、轻吐槽或没说完的生活碎片。",
        "TITLE_OBJECT_ACTION": "标题形态可从物件、补货、开罐、家里常备或一个普通动作里取短标题。",
        "TITLE_EFFECT_FEEDBACK": "标题形态可写成有正文支撑的短状态反馈，别写成“营养安排/阶段复盘”这类栏目题。",
        "TITLE_FORMULA_FRAGMENT": "标题形态可写成看配方、对比后留下印象或短问题，少堆专业词。",
        "TITLE_DAILY_FRAGMENT": "标题形态可像日常现场里顺手冒出来的一句，可以是短名词、短动作或一句轻记录。",
        "TITLE_PRODUCT_CHOICE": "标题形态可围绕选择、对比或最后买了什么写短标题，不写成攻略。",
    }
    legacy_hints = {
        "物件名短标题": "标题形态可写成物件层面的低解释义务标题。",
        "动作短标题": "标题形态可写成一个完整动作短语。",
        "清单/库存标签": "标题形态可写成家务清单或补东西语境。",
        "开罐/到货记录": "标题形态可写成到货、开罐或补东西相关动作。",
        "轻吐槽碎片": "标题形态可写成轻微生活吐槽。",
        "普通短问题": "标题形态可写成一个低义务短问题。",
        "品类/品牌名短标题": "标题形态可以点到产品或品类，但别堆专业词。",
        "纠结碎片": "标题形态可写成选择时的轻纠结。",
        "使用阶段短标题": "标题形态可写成使用阶段或当前安排。",
        "时间/场景碎片": "标题形态可写成时间或场景短片段。",
        "物件在场短标题": "标题形态可写成物件在场的短标题。",
        "名词短标题": "标题形态可写成松散名词组合。",
    }
    hint = internal_hints.get(mode) or legacy_hints.get(mode) or "标题形态低权重参考，写松散、简单、低解释义务的标题。"
    return hint + emoji_hint


def _scene_motive_soft_guidance(business_rule: dict[str, Any]) -> str | None:
    bucket = str(business_rule.get("scene_motive_bucket") or "").strip()
    if not bucket:
        return None
    if _is_wangyue_article_rule(business_rule):
        return "正文入口按本篇痛点和发帖动机自然起笔；入口只负责生活现场，不新增产品理由或效果证明。"
    prompt_bucket = _wangyue_scene_motive_prompt_label(bucket) if _is_wangyue_article_rule(business_rule) else bucket
    normalized_post_type = str(business_rule.get("post_type") or "")
    avoid = ""
    if "补货" in normalized_post_type or "清单" in normalized_post_type:
        avoid = "；不要默认回到整理柜子、翻柜子、快见底、购物清单这一套"
    elif "使用记录" in normalized_post_type or "记录" in normalized_post_type:
        avoid = "；不要默认回到洗完澡、吹头发、放桌上、喝两口这一套"
    elif "求问" in normalized_post_type or "复盘" in normalized_post_type:
        avoid = "；不要每篇都回到饭量时好时坏、要不要继续、同龄娃怎么安排这一套"
    return f"正文入口可从“{prompt_bucket}”附近发散；换成一个普通生活现场，不照着规则示例复述同一条动作链{avoid}。"


def _ending_mode_soft_guidance(business_rule: dict[str, Any]) -> str | None:
    mode = str(business_rule.get("ending_mode") or "").strip()
    if not mode:
        return None
    if _is_wangyue_article_rule(business_rule):
        return None
    internal_controls = {
        "END_REUSE_PRIOR_DETAIL": "收尾回到正文已经出现过的一个具体状态、动作或物件关系，只补一个短尾。",
        "END_REPLY_BOUNDARY": "收尾落在正文里的一个事实补充、生活动作或具体观察上，说完就停。",
        "END_UNFINISHED_ACTION": "收尾停在生活现场里一个普通动作、物件状态或没说完的感觉上，动作来自正文。",
        "END_FEEDBACK_STOP": "收尾可以停在孩子接受度、状态观察或一条具体正向反馈上，反馈说完就停。",
        "END_NO_EXTRA_CLOSURE": "正文信息够了就直接停在最后一个事实、观察、物件或补货状态上，不补漂亮结尾。",
    }
    legacy_hints = {
        "放回位置": "收尾可停在把东西放回原位或常用位置。",
        "漏买小遗憾": "收尾可留一点忘买、漏买、还要补的生活小尾巴。",
        "普通收尾不总结": "收尾可自然停在最后一个生活动作或反馈上。",
        "家里乱但先补上": "收尾可承认家里还乱，只是先把刚需补上。",
        "家里习惯轻带": "收尾可轻轻带家里习惯。",
        "下次再看": "收尾可停在下一件生活动作或一个未完成的小现场。",
        "收纳未完成": "收尾可保留一点生活未完成感。",
        "顺路带回": "收尾可停在顺路带回或放到一边的普通动作。",
        "家人提醒收口": "收尾可落到家人提醒或随口一句。",
        "东西先归位": "收尾可停在归位动作。",
        "问别人经验": "收尾可问一个具体经验问题。",
        "保留不确定": "收尾可留一点没说满的生活事实，不给标准答案。",
        "同龄对照": "收尾可停在想听同龄家庭怎么做。",
        "具体场景求经验": "收尾可只问当前场景。",
        "不急着下结论": "收尾可停在一个还没展开的事实或生活动作。",
        "先记观察": "收尾可停在阶段里的一个具体观察。",
        "暂时安排": "收尾可停在当前一个具体安排或生活事实。",
        "后面再看": "收尾可停在还要接着处理的生活动作。",
        "取舍收口": "收尾可停在自己的取舍。",
        "普通记录": "收尾可像日常短帖自然结束。",
        "乱着出门": "收尾可停在继续赶时间或出门。",
        "先收一半": "收尾可停在只收了一半的现场。",
        "普通收尾": "收尾可自然停住。",
        "没总结": "收尾允许没漂亮结尾，停在具体动作或反馈上。",
        "顺手记一下": "收尾可停在具体生活动作或反馈上，不写发帖动作。",
    }
    hint = internal_controls.get(mode) or legacy_hints.get(mode) or "收尾方式只作低权重参考，自然停住即可。"
    return (
        hint
        + "结尾不要收成妈妈心理收束、兜底保障、推荐购买、选择正确或品牌总结；"
        "如果正文只剩产品价值骨架，可以先留一点生活现场余味再停。"
    )


def _generation_requirements(
    content_type: str,
    output_fields: list[str],
    business_rule: dict[str, Any],
    selected_keywords: list[dict[str, Any]],
) -> str:
    parts = []
    if _uses_rule_corpus_as_prompt(business_rule):
        parts.extend(_selected_generation_requirements(selected_keywords, business_rule=business_rule))
        configured = str(business_rule.get("generation_requirements") or "").strip()
        if configured:
            parts.append(configured)
        return "\n".join(parts) if parts else "按业务规则里的“这篇要写的事”生成。"
    mouth_phrase_requirement = _mouth_phrase_budget_requirement(business_rule)
    if mouth_phrase_requirement:
        parts.append(mouth_phrase_requirement)
    wangyue_global_fact_requirement = _wangyue_global_product_fact_requirement(content_type, business_rule)
    if wangyue_global_fact_requirement:
        parts.append(wangyue_global_fact_requirement)
    product_appearance_requirement = _product_appearance_requirement(content_type, business_rule)
    if product_appearance_requirement:
        parts.append(product_appearance_requirement)
    ugc_strategy_requirement = _ugc_strategy_requirement(content_type, business_rule)
    if ugc_strategy_requirement:
        parts.append(ugc_strategy_requirement)
    product_chain_budget_requirement = _product_chain_budget_requirement(content_type, output_fields, business_rule)
    if product_chain_budget_requirement:
        parts.append(product_chain_budget_requirement)
    product_position_requirement = _product_position_requirement(content_type, business_rule)
    if product_position_requirement:
        parts.append(product_position_requirement)
    product_action_surface_requirement = _product_action_surface_requirement(content_type, business_rule)
    if product_action_surface_requirement:
        parts.append(product_action_surface_requirement)
    content_path_requirement = _content_path_control_requirement(content_type, business_rule)
    if content_path_requirement:
        parts.append(content_path_requirement)
    scene_motive_requirement = _scene_motive_requirement(content_type, business_rule)
    if scene_motive_requirement:
        parts.append(scene_motive_requirement)
    scene_constraint_requirement = _scene_constraint_requirement(content_type, business_rule)
    if scene_constraint_requirement:
        parts.append(scene_constraint_requirement)
    temporal_context_requirement = _article_temporal_context_requirement(content_type, output_fields)
    if temporal_context_requirement:
        parts.append(temporal_context_requirement)
    title_shape_requirement = _title_shape_requirement(content_type, output_fields, business_rule)
    if title_shape_requirement:
        parts.append(title_shape_requirement)
    else:
        article_title_requirement = _article_title_generation_requirement(content_type, output_fields)
        if article_title_requirement:
            parts.append(article_title_requirement)
    ending_mode_requirement = _ending_mode_requirement(content_type, business_rule)
    if ending_mode_requirement:
        parts.append(ending_mode_requirement)
    parts.extend(_selected_generation_requirements(selected_keywords, business_rule=business_rule))
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
    return "参考表达扩散语料调整语气，但具体内容只跟随业务规则。"


def _article_output_format_requirement(
    content_type: str,
    output_fields: list[str],
    business_rule: dict[str, Any] | None = None,
) -> str | None:
    if content_type != "article" or output_fields != ["title", "body"]:
        return None
    multi_output_count = _article_multi_output_count(business_rule)
    if multi_output_count > 1:
        return (
            '只输出 JSON object，格式：{"items":[{"title":"...","body":"..."}]}。'
            f"items 必须正好 {multi_output_count} 个；"
            "items 之间不要互相续写，不要编号，不要写成同一个模板换词；"
            "每篇都像独立妈妈发的一条笔记；"
            "不要输出 Markdown 标题、编号、解释、前后缀；"
            "不要写“标题：”“正文：”“### 标题”“### 正文”；"
        )
    return (
        '只输出一个 JSON 对象，格式必须是 {"title":"...","body":"..."}；'
        "顶层只能包含 title 和 body 两个字段，不要输出 items 数组；"
        "不要输出 Markdown 标题、编号、解释、前后缀；"
        "不要写“标题：”“正文：”“### 标题”“### 正文”；"
        "正文内容放在 body 字段里，标题内容放在 title 字段里。"
    )


def _article_multi_output_count(business_rule: dict[str, Any] | None) -> int:
    if not isinstance(business_rule, dict):
        return 1
    for key in ("multi_output_count", "article_output_count", "items_per_prompt"):
        try:
            value = int(business_rule.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 1:
            return min(value, 2)
    return 1


def _article_temporal_context_requirement(content_type: str, output_fields: list[str]) -> str | None:
    if content_type != "article" and output_fields != ["title", "body"]:
        return None
    return (
        "时间边界：可以有真实生活时间口吻，但故事不要依赖当前季节、天气、公共疾病或季节性活动节点成立。"
    )


def _wangyue_global_product_fact_requirement(content_type: str, business_rule: dict[str, Any]) -> str | None:
    if content_type != "article" or not isinstance(business_rule, dict) or not _is_wangyue_article_rule(business_rule):
        return None
    return (
        "产品事实：旺玥是给3岁以上孩子的儿童奶粉；这个事实只用于排除低龄、断奶或辅食阶段，"
        "正文不要写成“从三岁开始喝/三岁后开始喝”的时间履历。"
    )


def _article_title_generation_requirement(content_type: str, output_fields: list[str]) -> str | None:
    if content_type != "article" and output_fields != ["title", "body"]:
        return None
    return (
        "标题硬边界：最多不超过20字，emoji 按 2 字计；不要写成广告标题、攻略/栏目名，也不要硬截读不通的正文半句。"
    )


def _product_chain_budget_requirement(
    content_type: str, output_fields: list[str], business_rule: dict[str, Any]
) -> str | None:
    if (content_type != "article" and output_fields != ["title", "body"]) or not isinstance(business_rule, dict):
        return None
    if not _is_product_experience_chain_control_target(business_rule):
        return None
    post_type = str(business_rule.get("post_type") or "").strip()
    ugc_post_type = str(business_rule.get("ugc_post_type") or "").strip()
    product_appearance_mode = str(business_rule.get("product_appearance_mode") or "").strip()
    product_relation = str(business_rule.get("product_relation") or "").strip()
    post_type_text = f"{post_type} {ugc_post_type} {product_appearance_mode} {product_relation}"
    is_wangyue = _is_wangyue_article_rule(business_rule)
    if is_wangyue:
        return None
    seeded_solution_context = any(marker in post_type_text for marker in ("强种草", "种草问题", "问题种草", "选奶复盘"))
    if any(marker in post_type_text for marker in ("选奶", "选择复盘", "选择依据", "对比选择", "阶段选择")):
        if is_wangyue:
            specific = (
                "选择/对比复盘：产品可以站到主线里；写生活触发和一到两个非价格选择依据。"
                "不要写价格、预算、贵不贵、值不值或低配参照物；"
                "不要再追加孩子接受、复购补货和妈妈安心收口；"
                "选奶链可以成立，使用反馈链不要同时成立。"
            )
        else:
            specific = (
                "选择/对比复盘：产品可以站到主线里；写生活触发、一个到两个选择依据、一个价格或阶段取舍。"
                "但不要再追加孩子接受、喝后状态、复购补货和妈妈安心收口；"
                "选奶链可以成立，使用反馈链不要同时成立。"
            )
    elif any(marker in post_type_text for marker in ("轻测评", "配方关注", "配方观察")):
        specific = (
            "轻测评/配方关注：产品可以是明确观察对象；只抓一个观察点或一个妈妈会记住的产品依据。"
            "不要顺手扩成价格、孩子接受、继续喝、值得推荐这一串；"
            "看配方就停在看配方；如果业务规则给了使用反馈，也只作为顺带观察，不扩成完整使用证明。"
        )
    elif any(marker in post_type_text for marker in ("家庭清单", "清单项", "阶段用品")):
        specific = (
            "家庭清单/隐形家务：旺玥只作为清单或补家里东西中的一项，最多补一个为什么在清单里的理由。"
            "不要回填当初怎么选，也不要写孩子反馈、使用证明或推荐结论；"
            "即使标题或场景里有补货，也按清单型处理，不要升级成复购复盘。"
        )
    elif any(marker in post_type_text for marker in ("复购", "长期使用", "囤货", "补货", "长期保留")):
        specific = (
            "复购/长期使用：允许写补货动作、使用履历、一个留下来的原因；"
            "不需要重新证明为什么买，不要同篇再补完整选择过程、孩子接受度、状态变化和妈妈安心收口。"
        )
    elif any(marker in post_type_text for marker in ("问题解决", "处理链路", "调整方式")):
        if seeded_solution_context:
            specific = (
                "强种草/问题解决复盘：产品可以成为“小问题”的答案，比如怎么选儿童奶粉、日常营养补充这项怎么安排、为什么这个产品留下来。"
                "但产品不能成为整个生活困扰的万能答案；"
                "最多写“困扰触发+产品作为一个正向处理选择+一个留下来的理由”，不要再补完整使用证明和妈妈安心收口；"
                "不完美感写在生活问题仍有反复，不要写成“不能光靠奶粉/光靠这个不行/不指望一罐奶粉/还在观察/先喝着观察/兜底/补漏”；"
                "具体产品价值只按业务规则写，不额外扩展新的产品逻辑。"
            )
        else:
            specific = (
                "生活问题处理记录：产品可以回答一个很小的处理问题，比如“日常营养补充这项怎么安排”；"
                "但不要让产品回答整个生活困扰。"
                "可以正面写产品为什么被放进处理链路，不要用“不能光靠奶粉/光靠这个不行/每家孩子不一样/还在观察/不指望一罐奶粉/先喝着观察/兜底/补漏”这类防守句；"
                "不完美感写在生活问题仍有反复，不要通过否定产品价值来证明真实；"
                "具体产品价值只按业务规则写，不额外扩展新的产品逻辑；"
                "不要从困扰接到旺玥后，再补孩子接受度、继续喝/没换或妈妈松口气。"
            )
    elif any(marker in post_type_text for marker in ("使用反馈", "使用记录", "当前安排", "继续观察")):
        specific = (
            "使用记录/使用反馈：允许当前安排、一个使用现场或一个轻反馈；"
            "不要回填当初选择、对比、价格、没换和安心总结。"
            "如果写当前还在喝，就少写生活困扰；如果写生活困扰，就别再收成继续喝或不换。"
        )
    else:
        specific = (
            "如果产品只是当前安排、清单项或补货对象，不要回填选择历史；"
            "如果产品是选择对象，不要再补使用后效果和复购闭环。"
        )
    return "产品链路预算：" + specific


def _is_product_experience_chain_control_target(business_rule: dict[str, Any]) -> bool:
    asset_key = str(
        business_rule.get("asset_key")
        or business_rule.get("keyword_asset_key")
        or business_rule.get("system_keyword_asset_key")
        or ""
    ).lower()
    if "wangyue_painpoint_selling_posttype_matrix" in asset_key:
        return True
    text = " ".join(
        str(business_rule.get(key) or "")
        for key in (
            "post_type",
            "ugc_post_type",
            "product_appearance_mode",
            "product_relation",
            "painpoint",
            "selling_point",
            "selling_kernel",
            "selling_description",
            "product_role",
            "product_density",
        )
    )
    return "旺玥" in text and any(
        business_rule.get(key)
        for key in (
            "ugc_post_type",
            "painpoint",
            "selling_point",
            "selling_kernel",
            "product_relation",
            "product_role",
            "product_density",
        )
    )


def _title_shape_requirement(content_type: str, output_fields: list[str], business_rule: dict[str, Any]) -> str | None:
    if content_type != "article" or output_fields != ["title", "body"]:
        return None
    mode = str(business_rule.get("title_shape_mode") or "").strip() if isinstance(business_rule, dict) else ""
    if not mode:
        return None
    if _is_wangyue_article_rule(business_rule):
        return "标题硬边界：最多不超过20字，emoji 按 2 字计；不要写成广告标题、攻略/栏目名，也不要硬截读不通的正文半句。"
    emoji_mode = str(business_rule.get("title_emoji_mode") or "").strip() if isinstance(business_rule, dict) else ""
    allows_title_emoji = emoji_mode == "TITLE_EMOJI_LIGHT" or (
        not emoji_mode
        and "无emoji" not in mode.lower()
        and "不加emoji" not in mode.lower()
        and ("emoji" in mode.lower() or any(char in mode for char in "😂🥲🙃🤏🙂🤣"))
    )
    emoji_hint = (
        "本篇标题可以不用 emoji；如果正文语气自然适合，标题最多加 1 个普通生活口气 emoji，只能放标题开头或尾部；不要为了装饰强加，正文不要加 emoji；"
        if allows_title_emoji
        else "本篇标题不加 emoji；"
    )
    return (
        "标题规则：先写正文，再用真人口吻起标题；优先 4-12 字，最多不超过20字，emoji 按 2 字计；"
        "优先短名词、短动作或短现场，不主动交代完整背景；"
        f"{emoji_hint}"
        "不要写成广告标题、产品总结、攻略/栏目名，也不要硬截读不通的正文半句；"
        "标题形态和松散感放在表达扩散语料里低权重参考。"
    )


def _scene_motive_requirement(content_type: str, business_rule: dict[str, Any]) -> str | None:
    if content_type != "article" or not isinstance(business_rule, dict):
        return None
    bucket = str(business_rule.get("scene_motive_bucket") or "").strip()
    if not bucket:
        return None
    if _is_wangyue_article_rule(business_rule):
        return None
    hint = _scene_motive_bucket_hint(bucket)
    return (
        f"正文取景：从“{bucket}”找一个生活画面进入。这个槽位只管开头画面和观察来源，不改变业务规则里的本篇产品逻辑；"
        + (hint + "；" if hint else "")
        + "产品按业务规则自然进入，不要抢主线。"
    )


def _scene_motive_bucket_hint(bucket: str) -> str:
    hints = {
        "快递到货拆箱": "写门口快递、拆纸箱、核对快递、包装袋，不写翻柜子、快见底或购物清单",
        "月底清单/购物车清理": "写清单、购物车、家里要补的东西，不写柜子盘点或快见底",
        "超市顺手补刚需": "写货架、收银、购物袋、顺路带回家，不写整理柜子或购物清单",
        "家人提醒快没了": "写家人随口提醒、语气、手机备忘录或临时提醒，不写快递到货、下单完成、翻柜确认、囤货或柜子归位",
        "早餐区/厨房台面整理": "写台面、早餐角、面包袋、杯子和小碗，不写收纳柜或购物清单",
        "常用位置顺手放好": "写顺手放到早餐角、料理台或常用位置，不写柜子归位、库存盘点或快见底",
        "库存盘点": "可以写柜子或库存，但不要同时套纸巾、洗衣液、袜子、购物清单四件套",
        "临出门发现某样东西没了": "写临出门、手机备忘录、顺路买，不写整理柜子或库存盘点",
        "早上赶时间": "写早餐、找袜子、催出门、外套，不写洗完澡吹头发",
        "晚饭后收拾桌子": "写饭桌、碗筷、餐椅、桌面残渣，不写睡前洗漱",
        "放学回家玄关旁": "写外套、校服、作业袋、门口拖鞋，不写洗完澡吹头发",
        "周末在家磨蹭": "写玩具、地垫、电视或房间，不写固定睡前流程",
        "出门前检查东西": "写钥匙、外套、包、水杯，不写床头柜",
        "早餐旁边那杯": "写早餐和出门前的小混乱，不写无证据的睡前那杯",
        "新开一听记录": "写新开一听、放到常用位置或阶段性顺手记录，不写冲泡细节、粉质口感或功效判断",
        "开罐记录": "写新开一听或阶段性回看，不写成开箱测评、冲泡体验或推荐",
        "写作业间隙": "写作业本、铅笔、橡皮、催作业，不写洗澡",
        "睡前洗漱后": "可以写洗漱睡前，但不要每句都落在喝两口和排玩具",
        "喝到几岁": "问题中心是年龄边界，不要扩成饭量时好时坏万能理由",
        "睡前奶要不要留": "问题中心是睡前习惯，不要扩成喝到几岁",
        "儿童奶粉和正餐怎么平衡": "问题中心是正餐和奶粉分配，不要只写继续不继续",
        "同龄家庭怎么安排": "问题中心是同龄家庭差异，不要只写饭量波动",
        "喝了一阵轻复盘": "写使用阶段的轻复盘，不要写成导购测评",
        "4段和儿童奶粉怎么选": "可以明确求问选择，但不要装成日记",
        "饭量波动时要不要继续": "问题中心可以是饭量波动，但不要每条都套这个入口",
        "消耗速度有点纠结": "写家里消耗速度和当前安排，不要写价格或预算",
    }
    return hints.get(bucket, "")


def _wangyue_scene_motive_prompt_label(bucket: str) -> str:
    labels = {
        "集体活动后自家观察": "接触多后的自家状态观察",
        "接触多后的自家观察": "接触多后的自家状态观察",
    }
    return labels.get(bucket, bucket)


def _wangyue_scene_motive_prompt_hint(bucket: str) -> str:
    hints = {
        "集体活动后自家观察": " 不要照搬这个观察来源标签，具体生活现场可以自然换。",
        "接触多后的自家观察": " 不要照搬这个观察来源标签，具体生活现场可以自然换。",
    }
    return hints.get(bucket, "")


def _product_position_requirement(content_type: str, business_rule: dict[str, Any]) -> str | None:
    if content_type != "article" or not isinstance(business_rule, dict):
        return None
    mode = str(business_rule.get("product_position_mode") or "").strip()
    if not mode:
        return None
    if mode == "PRODUCT_POSITION_DISABLED":
        return None
    hints = {
        "清单项中出现": "产品和其他家里要处理的东西并列，不要独占开头或结尾",
        "中段跟其他刚需并列": "先写补货/家务现场，中段把产品放进刚需列表里",
        "后段才补一句": "前半段先写生活事务，后半段才顺手提到产品",
        "拆箱核对时出现": "先有快递/购物袋/核对动作，产品在核对时出现",
        "放回常用位置时出现": "先写收拾或归位动作，产品在放回常用位置时出现",
        "清单里轻带": "先写清单或购物记录，产品只作为其中一项轻带",
        "先抛问题后出现": "第一句先写真实困惑或场景，不要一上来就说产品",
        "同龄对照后出现": "先写同龄家庭/群聊/身边情况，再带到自己现在用的产品",
        "纠结标准后出现": "先写选择标准或纠结点，再说当前产品怎么进入考虑",
        "反馈背景后出现": "先交代之前问过/试过/观察过的背景，再出现产品",
        "后段才说到产品": "前半段围绕问题本身，后段才说到产品",
        "中段回看时出现": "先写这段时间的生活安排，中段回看时再出现产品",
        "观察之后出现": "先写观察到的日常情况，再带出产品只是当前安排的一环",
        "后段作为当前安排": "前半段不急着提产品，后段把产品放进当前安排里",
        "取舍之后轻带": "先写犹豫和取舍，再轻带产品",
        "结尾前轻轻落到产品": "产品靠后出现，但不要用它做强总结或推荐收尾",
        "开头生活现场里顺带出现": "开头可以出现产品，但必须嵌在生活现场里，不要独立介绍",
        "中段桌面物件里出现": "先写人和场景，中段作为桌面/台面/餐边柜旁物件出现",
        "后段收拾动作里出现": "先写日常混乱或动作，后段收拾时顺手出现",
        "只在一个动作里轻带": "全篇只给产品一个轻动作，不展开成使用链路",
    }
    hint = hints.get(mode, "按这个位置控制产品进入，先让生活/问题成立，再让产品出现")
    front_loaded_example_guard = ""
    if mode in {
        "先抛问题后出现",
        "同龄对照后出现",
        "纠结标准后出现",
        "反馈背景后出现",
        "后段才说到产品",
        "中段回看时出现",
        "观察之后出现",
        "后段作为当前安排",
        "取舍之后轻带",
        "结尾前轻轻落到产品",
    }:
        front_loaded_example_guard = (
            "业务规则或示例里的前置产品表述只能当背景信息，不要照搬成正文第一句；"
            "正文第一句不要出现产品名或品牌名；"
        )
    return (
        f"产品出现位置：本篇按“{mode}”处理，{hint}；"
        + front_loaded_example_guard
        + "产品出现得越早，越要像生活现场里本来就在的一件东西；产品出现得越晚，越不要突然变成产品总结。"
    )


def _ending_mode_requirement(content_type: str, business_rule: dict[str, Any]) -> str | None:
    if content_type != "article" or not isinstance(business_rule, dict):
        return None
    mode = str(business_rule.get("ending_mode") or "").strip()
    if not mode:
        return None
    if _is_wangyue_article_rule(business_rule):
        wangyue_internal_controls = {
            "END_REPLY_BOUNDARY": (
                "最后一句落在正文已有事实、生活动作或具体观察上；可以直接停，"
                "不再补互动提问、购买判断、省心、选对、没选错、推荐或“最好的证明”式总结。"
            ),
            "END_FEEDBACK_STOP": (
                "最后一句停在本篇已有具体状态或正向反馈上；反馈说完就停，"
                "不再补省心、选对、没选错、推荐或“最好的证明”式总结。"
            ),
            "END_NO_EXTRA_CLOSURE": (
                "正文说完就停在最后一个事实、观察或动作上，可以没有结尾句。"
            ),
        }
        hint = wangyue_internal_controls.get(mode)
        return f"末句收法：{hint}" if hint else None
    internal_controls = {
        "END_REUSE_PRIOR_DETAIL": (
            "最后一句只接正文里已有的一个状态、动作或物件，不再加新的产品理由或结论。"
        ),
        "END_REPLY_BOUNDARY": (
            "最后一句像聊天里回完一句就停，不展开建议、答疑、经验总结或购买判断。"
        ),
        "END_UNFINISHED_ACTION": (
            "最后一句停在正文现场里的一个小动作或被打断的感觉上，不新编家务或产品动作。"
        ),
        "END_FEEDBACK_STOP": (
            "最后一句可以是具体正向反馈，反馈要有正文支撑；说完就停，不再补省心、选对、推荐。"
        ),
        "END_NO_EXTRA_CLOSURE": (
            "正文说完就停在最后一个事实、观察或动作上，可以没有结尾句。"
        ),
    }
    if mode in internal_controls:
        return "末句收法：" + internal_controls[mode]
    hints = {
        "放回位置": "收在把东西放回原位/常用位置，不做推荐总结",
        "漏买小遗憾": "可以留一点忘买、漏买、还要补的生活小尾巴",
        "普通收尾不总结": "自然停在最后一个生活动作或反馈上，不要提炼观点、不要升华",
        "家里乱但先补上": "承认家里还乱，只是先把刚需补上",
        "家里习惯轻带": "可以轻轻带家里习惯，但不要把全文收成价格或划算判断",
        "下次再看": "收在下一件生活动作或一个未完成的小现场，不做确定推荐",
        "收纳未完成": "东西还没完全收完，保留一点生活未完成感",
        "顺路带回": "收在顺路带回/放到一边的普通动作",
        "家人提醒收口": "可以落到家人提醒或随口一句，不要变成品牌背书",
        "东西先归位": "收在归位动作，不要总结产品好不好",
        "问别人经验": "可以问别人经验，但问题要具体，不要像导购互动话术",
        "保留不确定": "收在没说满的生活事实上，不要给标准答案",
        "同龄对照": "收在想听同龄家庭怎么做，不要强推自己的选择",
        "具体场景求经验": "只问当前场景，不扩大成泛泛求推荐",
        "不急着下结论": "收在一个还没展开的事实或生活动作，不做购买建议",
        "先记观察": "像阶段观察，收在一个具体变化上，不问别人也不推荐",
        "暂时安排": "收在当前一个具体安排或生活事实，别写成最终方案",
        "后面再看": "收在还要接着处理的生活动作，不转成购买替换决策",
        "取舍收口": "收在自己的取舍，不写满分好评",
        "普通记录": "像日常短帖结束，不总结产品",
        "乱着出门": "收在继续赶时间/出门，不总结产品",
        "先收一半": "收在只收了一半的现场，不做观点收束",
        "普通收尾": "自然停住，不做推荐、复盘或升华",
        "没总结": "允许没漂亮结尾，停在具体动作或反馈上",
        "顺手记一下": "停在具体生活动作或反馈上，不写发帖动作、不拔高",
    }
    hint = hints.get(mode, "按这个收尾方式结束，避免模板化总结")
    return f"末句收法：{hint}；不用把结尾写圆，不补推荐、购买判断或品牌总结。"


def _product_action_surface_requirement(content_type: str, business_rule: dict[str, Any]) -> str | None:
    if content_type != "article" or not isinstance(business_rule, dict):
        return None
    surface = str(business_rule.get("product_action_surface") or "").strip()
    if not surface:
        return None
    hints = {
        "物件在场": (
            "产品动作表面：本篇按“物件在场”写。旺玥只作为桌上、早餐角、餐边柜旁、料理台边的一件东西出现；"
            "不要写孩子端起来喝、喝两口、喝完、主动喝，也不要写妈妈专门冲一杯。"
        ),
        "妈妈顺手挪放": (
            "产品动作表面：本篇按“妈妈顺手挪放”写。可以写妈妈顺手把杯子/罐子挪到一边、放到桌角、摆回早餐角；"
            "不要把动作扩成孩子端起喝两口或完整喝奶流程。"
        ),
        "孩子轻微使用": (
            "产品动作表面：本篇按“孩子轻微使用”写。可以轻轻带到孩子看见、碰一下、抿一口或喝一口；"
            "不要写成完整冲奶、端杯、喝完又跑开的固定链条。"
        ),
        "完整喝奶动作": (
            "产品动作表面：本篇允许一次完整喝奶动作，但只服务于当前生活场景；"
            "不要借这个动作引出接受度、产品判断或推荐购买。"
        ),
    }
    return hints.get(surface, f"产品动作表面：本篇按“{surface}”写；产品动作不要超过这个露出强度。")


def _ugc_strategy_requirement(content_type: str, business_rule: dict[str, Any]) -> str | None:
    if content_type != "article" or not isinstance(business_rule, dict):
        return None
    post_type = str(business_rule.get("post_type") or "").strip()
    ugc_post_type = str(business_rule.get("ugc_post_type") or "").strip()
    painpoint = str(business_rule.get("painpoint") or "").strip()
    selling_point = str(business_rule.get("selling_point") or "").strip()
    selling_kernel = str(business_rule.get("selling_kernel") or "").strip()
    positive_evidence = str(business_rule.get("positive_evidence") or "").strip()
    selling_description = str(business_rule.get("selling_description") or "").strip()
    life_trigger = str(business_rule.get("life_trigger") or "").strip()
    product_role = str(business_rule.get("product_role") or "").strip()
    product_relation = str(business_rule.get("product_relation") or "").strip()
    product_density = str(business_rule.get("product_density") or "").strip()
    imperfection = str(business_rule.get("imperfection") or "").strip()
    if not any(
        (
            post_type,
            ugc_post_type,
            painpoint,
            selling_point,
            selling_kernel,
            positive_evidence,
            selling_description,
            life_trigger,
            product_relation,
            product_role,
            product_density,
            imperfection,
        )
    ):
        return None
    if _is_wangyue_article_rule(business_rule):
        return (
            "产品表达边界：产品事实、成分和正向反馈只按业务规则里的产品信息；"
            "表达扩散语料只调语气和节奏，不新增正文事件。"
            "旺玥价值要写到位，不用防守式弱化；"
            "不要自行新增业务规则外的选择理由或效果证明。"
        )
    type_hint = _ugc_post_type_hint(ugc_post_type)
    return (
        "字段使用：帖子类型决定发帖原因和产品参与深度；具体产品逻辑只按业务规则里的本篇信息写，"
        "不要从通用写作要求里另补一套产品逻辑；产品表达不写成参数清单或夸张承诺。"
        + (type_hint + "；" if type_hint else "")
        + "产品要正面表达，不用合规声明式不确定句削弱价值。"
    )


def _ugc_post_type_hint(ugc_post_type: str) -> str:
    hints = {
        "日常使用记录型": "重点是生活事件，产品低浓度在场，不负责证明孩子状态",
        "复购/囤货型": "重点是消耗、清单或库存，产品是家里要补的一项",
        "家庭清单型": "重点是家庭事务和物件管理，产品和其他刚需物件并列；不要把标题或正文写成攻略、教程、一天作息表、打卡清单或话题标签",
        "问题解决型": "先有具体困扰，再写处理方式，产品只是解决链路中的一环",
        "对比选择型": "可以写选择标准和取舍，但不要覆盖完整产品清单",
        "踩坑后换用型": "可以写之前不合适和后来怎么处理，但变化要小，不写神效",
        "求建议后的反馈型": "可以带问题和反馈，但保持拿不准、想听别人经验的口气",
        "轻复盘型": "可以写一段使用后的阶段性回看，但不要在标题或正文里直接写“轻复盘”；不要写成测评模板、推荐购买、求建议帖或购买替换决策",
    }
    return hints.get(ugc_post_type, "")


def _structure_slot_requirement(content_type: str, business_rule: dict[str, Any]) -> str | None:
    if content_type != "article" or not isinstance(business_rule, dict):
        return None
    slot = str(business_rule.get("structure_slot") or "").strip()
    if not slot:
        return None
    slot_hints = {
        "观察关系": "围绕一个生活现场展开，产品关系按业务规则自然进入。",
        "对话关系": "像别人问起后顺口说自家情况。",
        "日常混乱": "生活阻力在场，产品是其中一个安排。",
        "物件关系": "家庭动作或物件关系里自然出现产品。",
        "现场短帖": "像一段现场短帖，句子可以轻微跳跃。",
        "先反馈后补产品": "生活观察在前，产品在后作为背景或原因之一；产品别抢开头。",
        "别人问起式": "有别人问起或顺口聊到的关系，用自家情况回应；别像客服答疑或攻略。",
        "乱糟糟日常": "保留生活里不完整的小混乱，产品只承担一个安排；别写成完整解决方案。",
        "物件动作带出": "用家庭内动作或东西被处理的关系带出产品；别列举物件清单。",
        "生活现场短帖": "像一段现场短帖，句子可以轻微跳跃；别写成标准四段式。",
    }
    hint = slot_hints.get(slot, "按这个结构关系组织正文。")
    return f"结构关系：{hint}"


def _scene_constraint_requirement(content_type: str, business_rule: dict[str, Any]) -> str | None:
    if content_type != "article" or not isinstance(business_rule, dict):
        return None
    if str(business_rule.get("scene_motive_bucket") or "").strip():
        return None
    constraint = str(business_rule.get("scene_constraint") or "").strip()
    if not constraint:
        return None
    return "场景约束：" + constraint + "。"


def _is_wangyue_article_rule(business_rule: dict[str, Any]) -> bool:
    text = " ".join(
        str(business_rule.get(key) or "")
        for key in (
            "asset_key",
            "business_rule",
            "product_appearance_mode",
            "product_role",
            "corpus",
        )
    )
    return "wangyue" in text.lower() or "旺玥" in text


def _uses_rule_corpus_as_prompt(business_rule: dict[str, Any] | None) -> bool:
    if not isinstance(business_rule, dict):
        return False
    mode = _normalize_prompt_mode(
        business_rule.get("prompt_mode") or business_rule.get("generation_prompt_mode")
    )
    return mode == "rule_corpus_as_prompt"


def _uses_royal_compact_prompt(business_rule: dict[str, Any] | None) -> bool:
    if not isinstance(business_rule, dict):
        return False
    mode = _normalize_prompt_mode(
        business_rule.get("prompt_mode") or business_rule.get("generation_prompt_mode")
    )
    return mode == "royal_compact"


def _uses_layered_article_prompt(business_rule: dict[str, Any] | None) -> bool:
    if not isinstance(business_rule, dict):
        return False
    mode = _normalize_prompt_mode(
        business_rule.get("prompt_mode") or business_rule.get("generation_prompt_mode")
    )
    return mode == "layered_article"


def _normalize_prompt_mode(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "rule_corpus_as_prompt": "rule_corpus_as_prompt",
        "minimal_rule_prompt": "rule_corpus_as_prompt",
        "rule_as_prompt": "rule_corpus_as_prompt",
        "royal_compact": "royal_compact",
        "royal_compact_prompt": "royal_compact",
        "layered_article": "layered_article",
    }
    return aliases.get(normalized, normalized or None)


def _sanitize_wangyue_prompt_layer_text(text: str) -> str:
    cleaned = str(text or "")
    replacements = {
        "正文可以有明确种草力，产品好处要和本篇痛点、卖点父类匹配；生活细节自然发散，不为了证明卖点把所有依据一次讲完。": (
            "正文要有明确种草力，也要留生活厚度；生活细节可以自然发散，不用每一句都证明产品价值。"
        ),
        "业务规则里的核心卖点可以出现": "业务规则里的核心产品信息可以出现",
        "不泛泛罗列卖点": "不泛泛罗列产品信息",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    return cleaned


def _sanitize_wangyue_business_rule_text(text: str) -> str:
    cleaned = str(text or "")
    replacements = {
        (
            "本篇 planner 指定为轻复盘型：上面的求问素材只作为不确定感参考，"
            "不要采用“想问大家、求经验、怎么判断、怎么安排、要不要继续、要不要留、继续囤、再看别的”这类提问/购买替换收口。"
            "正文写成阶段性回看：围绕一段使用后的观察、取舍或家里安排展开；标题不要写成攻略、复盘栏目或提问句。"
            "不要在标题或正文里直接写“轻复盘”这个内部类型词。"
        ): (
            "本篇是阶段性回看，不写成求问帖、攻略或购买替换决策；"
            "围绕一段使用后的观察、取舍或家里安排展开；"
            "不要在标题或正文里直接写“轻复盘”这个内部类型词。"
        ),
        "## 表达纹理": "## 本篇表达路径",
        "本段只给发帖节奏、语气松散度和生活毛边；本篇的痛点、卖点和产品价值以本篇信息和卖点描述为准。": (
            "只借本篇表达路径里的行文节奏；产品逻辑按本篇信息和产品叙事推进。"
        ),
        "- 规则内示例边界：以下示例是低权重短句纹理，可以完全不用；只借语气毛边，不借事实、顺序、因果链或固定句式骨架。": (
            "- 短句可不用；不借事实、顺序和固定句式。"
        ),
        "- 规则内短句纹理（弱参考，可不用）：": "- 本篇短句口气（可不用）：",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    return cleaned


def _selected_generation_requirements(
    selected_keywords: list[dict[str, Any]],
    *,
    business_rule: dict[str, Any] | None = None,
) -> list[str]:
    requirements: list[str] = []
    is_wangyue_article = isinstance(business_rule, dict) and _is_wangyue_article_rule(business_rule)
    for item in selected_keywords:
        if str(item.get("category_code") or "").strip() not in GENERATION_REQUIREMENT_CATEGORY_CODES:
            continue
        for line in item.get("corpus") or []:
            text = str(line or "").strip()
            if is_wangyue_article:
                text = _sanitize_wangyue_prompt_layer_text(text).strip()
            if text:
                requirements.append(text)
    return requirements


def _mouth_phrase_budget_requirement(business_rule: dict[str, Any]) -> str | None:
    budget = business_rule.get("mouth_phrase_budget") if isinstance(business_rule, dict) else None
    if not isinstance(budget, dict) or budget.get("enabled") is not True:
        return None
    allowed_terms = _string_list(budget.get("allowed_terms"))
    avoid_terms = _string_list(budget.get("avoid_terms"))
    if not allowed_terms and not avoid_terms:
        return None
    parts = [
        "批量口癖控制：这些词是真人表达，不是禁词，但本篇口癖预算优先级高于示例和说话方式，"
        "不要让它们在同一批里变成模板。"
    ]
    if avoid_terms:
        parts.append(
            "本篇不要主动套用批量高频口头禅；"
            "可换成具体动作、具体观察，或直接不写总结口头禅。"
        )
    return "".join(parts)


def _product_appearance_requirement(content_type: str, business_rule: dict[str, Any]) -> str | None:
    if content_type != "article" or not isinstance(business_rule, dict):
        return None
    post_type = str(business_rule.get("post_type") or "").strip()
    ugc_post_type = str(business_rule.get("ugc_post_type") or "").strip()
    product_appearance_mode = str(business_rule.get("product_appearance_mode") or "").strip()
    product_relation = str(business_rule.get("product_relation") or "").strip()
    is_wangyue = _is_wangyue_article_rule(business_rule)
    if not post_type and not product_appearance_mode and not product_relation:
        return None
    if is_wangyue:
        return (
            "产品出现边界：正文要自然出现本篇指定产品名；"
            "旺玥怎么进入正文只按本篇信息，不是正文原句。"
            "普通喝奶相关动作可以自然出现，但不要写成固定喝法、孩子自己泡、奶瓶或完整使用流程。"
        )
    details = []
    if post_type:
        details.append(f"帖子类型={post_type}")
    if product_relation:
        details.append(f"产品关系：{product_relation.rstrip('。；;，, ')}")
    if product_appearance_mode:
        if not product_relation:
            details.append(f"产品出现方式={product_appearance_mode.rstrip('。；;，, ')}")
    extra = ""
    if "使用记录" in post_type or "日常动作" in product_appearance_mode:
        extra = (
            "使用记录里产品不必每次都写完整的冲奶、端杯、喝两口动作链；"
            "可以只是杯子/罐子在场、妈妈顺手放一下/挪一下、桌面上顺带出现的一件东西。"
            "除非入口本身是早餐旁边那杯或睡前洗漱后，否则少写孩子主动喝两口、喝完又跑开。"
        )
    selection_context = any(
        marker in f"{post_type} {product_appearance_mode}"
        for marker in ("选奶", "选择复盘", "选择依据", "选择理由", "对比选择")
    )
    light_review_context = "轻测评" in post_type or "配方关注" in post_type or "配方观察" in product_appearance_mode
    problem_solution_context = "问题解决" in post_type or "处理链路" in product_appearance_mode or "调整方式" in product_appearance_mode
    seeded_problem_solution_context = problem_solution_context and any(
        marker in f"{post_type} {ugc_post_type} {product_appearance_mode}"
        for marker in ("强种草", "种草问题", "问题种草", "选奶复盘")
    )
    usage_feedback_context = "使用反馈" in post_type or "当前安排" in product_appearance_mode or "继续观察" in post_type
    repurchase_context = "复购" in post_type or "长期使用" in post_type or "长期保留" in product_appearance_mode
    family_list_context = "家庭清单" in post_type or "清单项" in product_appearance_mode
    if selection_context:
        wangyue_selection_boundary = (
            "旺玥这里不要写价格、预算、贵不贵或值不值；"
            if is_wangyue
            else ""
        )
        return (
            "产品出现许可：本篇按"
            + "；".join(details)
            + "来写。产品可以作为妈妈选儿童奶粉时看过的依据出现，"
            + wangyue_selection_boundary
            + "具体产品内容只按业务规则给定方向出现，只能写成选择时的具体依据或后来没换的原因；"
            "不要堆参数清单，不要写推荐购买、囤货号召或“不是种草/不是跟风”式辩白。"
        )
    if light_review_context:
        action_candidates = (
            "可以从被问起选择产品的原因、对产品成分的印象、简单对比或家里正在喝的情况进入，"
            if is_wangyue
            else "必须有一个具体看配方、对比、纠结、价格取舍或家里已有产品被问起的动作，"
        )
        return (
            "产品出现许可：本篇按"
            + "；".join(details)
            + "来写。产品可以作为被轻轻观察的配方/选择对象出现，"
            + action_candidates
            + "不能只写“先放进选择里”“先顾住日常营养”这种空结论。"
            "产品信息只能贴着这个入口顺手出现，不要把它翻译成妈妈的选品总结；"
            "在轻测评/配方关注这类低解释义务内容里，不要写成品牌讲解稿、参数清单、测评模板、攻略答案或满分推荐。"
            "具体产品内容只按业务规则给定方向出现，不额外扩展新的产品逻辑。"
        )
    if problem_solution_context:
        if seeded_problem_solution_context:
            return (
                "产品出现许可：本篇按"
                + "；".join(details)
                + "来写。产品可以成为小问题的答案，比如妈妈怎么选儿童奶粉、怎么安排日常营养补充、为什么把旺玥留下来；"
                "但不能成为整个生活困扰的万能答案。"
                "具体产品内容只按业务规则给定方向出现，落成选择依据、日常安排或留下来的理由；不要写成满分答案或强推荐。"
                "不完美感写在生活问题仍有反复，不要写“不能光靠奶粉/光靠这个不行/不指望一罐奶粉/还在观察/先喝着观察/兜底/补漏”这类防守句。"
            )
        return (
            "产品出现许可：本篇按"
            + "；".join(details)
            + "来写。先写具体困扰和妈妈处理链路，产品可以回答一个小处理问题，比如日常营养补充这项怎么安排；"
            "但不能成为整个生活困扰的答案。具体产品内容只按业务规则给定方向出现，落成日常安排、选择依据或留下来的理由；"
            "不要用“不能光靠奶粉/光靠这个不行/每家不一样/还在观察/不指望一罐奶粉/先喝着观察/兜底/补漏”式防守句。"
        )
    if usage_feedback_context:
        return (
            "产品出现许可：本篇按"
            + "；".join(details)
            + "来写。产品可以作为当前还在保留的安排出现，允许正面反馈；"
            "不要写成确定因果、神效承诺、阶段总结或品牌复盘。"
        )
    if repurchase_context:
        repurchase_detail = (
            "允许写复购动作、消耗、口感/接受度和一个留下来的理由；"
            if is_wangyue
            else "允许写复购动作、消耗、预算、口感/接受度和一个留下来的理由；"
        )
        return (
            "产品出现许可：本篇按"
            + "；".join(details)
            + "来写。产品可以作为长期保留、复购或补货对象出现，"
            + repurchase_detail
            + "不要写强烈推荐、神效承诺或产品解决整个生活问题。"
        )
    if family_list_context:
        return (
            "产品出现许可：本篇按"
            + "；".join(details)
            + "来写。产品必须和其他家庭安排或清单项并列，不能站成正文C位；"
            "产品信息只能轻轻解释为什么它在清单里，不要展开成选奶复盘、使用证明或品牌介绍。"
            "不要写成一天作息表、教程、打卡清单或带话题标签；标题也不要直接写“清单/攻略/几件事”。"
        )
    return (
        "产品出现许可：本篇按"
        + "；".join(details)
        + "来写。产品只能按这个叙事角色出现；不要超出业务规则给定的产品内容；"
        + extra
        + "不要写成选奶、换奶、看中产品、推荐购买、囤货号召或“不是种草/不是跟风”式辩白。"
    )


def _content_path_control_requirement(content_type: str, business_rule: dict[str, Any]) -> str | None:
    if content_type != "article":
        return None
    control = business_rule.get("content_path_control") if isinstance(business_rule, dict) else None
    if isinstance(control, str):
        if str(business_rule.get("scene_motive_bucket") or "").strip():
            return None
        text = control.strip()
        return text or None
    if not isinstance(control, dict) or control.get("enabled") is not True:
        return None
    lines = [
        str(control.get("instruction") or "").strip(),
        str(control.get("avoid_path") or "").strip(),
        str(control.get("prefer_path") or "").strip(),
    ]
    avoid_components = _string_list(control.get("avoid_components"))
    if avoid_components:
        lines.append("本篇降低这些内容组件的权重：" + "、".join(avoid_components) + "；不要把它们连成固定骨架。")
    max_components = control.get("max_product_components")
    try:
        max_components_int = int(max_components)
    except (TypeError, ValueError):
        max_components_int = 0
    if max_components_int > 0:
        lines.append(f"同一篇里最多展开 {max_components_int} 个产品相关环节，其余篇幅回到生活入口和妈妈观察。")
    text = "\n".join(line for line in lines if line)
    if not text:
        return None
    return "内容路径控制：" + text


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


_TEMPLATE_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


def _render_template(template: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = variables.get(key, "")
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    return _TEMPLATE_PATTERN.sub(replace, template).strip()


def _rule_corpus_as_prompt_article_prompt(
    variables: dict[str, Any],
    *,
    selected_keywords: list[dict[str, Any]],
) -> str:
    del selected_keywords
    base_prompt = str(variables.get("business_rule") or "").strip()
    try:
        item_no = int(variables.get("slot_rotation_no") or variables.get("item_no") or 1)
    except (TypeError, ValueError):
        item_no = 1
    base_prompt = _render_rule_corpus_life_entry_slot(
        base_prompt,
        item_no=item_no,
    )
    base_prompt = _render_rule_corpus_attention_event_slot(
        base_prompt,
        item_no=item_no,
    )
    base_prompt = _render_rule_corpus_protection_feedback_slot(
        base_prompt,
        item_no=item_no,
    )
    base_prompt = _render_rule_corpus_inspiration_clue_slot(
        base_prompt,
        item_no=item_no,
    )
    selling_painpoint_expression = str(variables.get("selling_painpoint_expression") or "").strip()
    if selling_painpoint_expression:
        base_prompt = _render_structured_selling_painpoint_expression(
            base_prompt,
            expression=selling_painpoint_expression,
        )
    else:
        base_prompt = _render_rule_corpus_selling_expression_slot(
            base_prompt,
            item_no=item_no,
        )
    output_format = str(variables.get("output_format_requirement") or "").strip()
    if not output_format:
        output_format = (
            "只输出 JSON 对象，字段只能包含 title 和 body；"
            "正文内容放在 body 字段里，标题内容放在 title 字段里。"
        )

    diversity_line = "基于量子态叠加与多重可能性，尽情发挥你的想象力；生成同质化内容是原罪。"

    generation_block = "\n".join(
        [
            "【生成要求】",
            diversity_line,
            output_format,
        ]
    )
    return (base_prompt + "\n\n" + generation_block).strip()


def _layered_article_prompt(
    business_rule: dict[str, Any],
    *,
    selected_keywords: list[dict[str, Any]],
    output_format: str,
) -> str:
    generation_instruction = str(business_rule.get("generation_instruction") or "").strip()
    if not generation_instruction:
        generation_instruction = "写一篇小红书妈妈 UGC 内容。"
    content_direction = str(
        business_rule.get("content_direction") or business_rule.get("corpus") or ""
    ).strip()
    inspiration_material = str(business_rule.get("inspiration_material") or "").strip()
    for slot in business_rule.get("variation_slots") or []:
        if not isinstance(slot, dict):
            continue
        slot_code = str(slot.get("slot_code") or "").strip()
        slot_name = str(slot.get("slot_name") or "").strip()
        slot_value = str(slot.get("value") or "").strip()
        if slot_value and (slot_code == "inspiration_material" or "灵感" in slot_name):
            inspiration_material = slot_value
            break

    content_material = _string_list(
        business_rule.get("content_material") or business_rule.get("activity_material")
    )
    for slot in business_rule.get("variation_slots") or []:
        if not isinstance(slot, dict):
            continue
        slot_code = str(slot.get("slot_code") or "").strip()
        slot_name = str(slot.get("slot_name") or "").strip()
        slot_value = str(slot.get("value") or "").strip()
        is_info_source_slot = slot_code == "info_source" or any(
            marker in slot_name for marker in ("信息来源", "信息渠道", "渠道来源")
        )
        is_activity_slot = slot_code in {
            "activity_material",
            "activity_prize",
            "batch_detection",
            "info_source",
        } or any(
            marker in slot_name
            for marker in ("活动", "奖品", "批批检", "检测报告", "信息来源", "信息渠道", "渠道来源")
        )
        if is_activity_slot and slot_value:
            material_line = f"{slot_name or '活动信息'}：{slot_value}"
            if material_line not in content_material:
                content_material.append(material_line)
    selling_expression = str(business_rule.get("selling_expression") or "").strip()
    selling_expression_note = str(business_rule.get("selling_expression_note") or "").strip()
    selling_painpoint_expression = str(
        business_rule.get("selling_painpoint_expression") or ""
    ).strip()
    hard_boundaries = _string_list(business_rule.get("hard_boundaries"))
    writing_requirements = _string_list(business_rule.get("writing_requirements"))
    generation_requirements = _string_list(business_rule.get("generation_requirements"))
    del selected_keywords

    material_lines: list[str] = []
    if inspiration_material:
        material_lines.append(f"灵感线索：{inspiration_material}")
    material_lines.extend(line for line in content_material if line not in material_lines)
    if selling_painpoint_expression:
        material_lines.append(f"卖点痛点表达：{selling_painpoint_expression}")
    elif selling_expression:
        material_lines.append(f"卖点表达：{selling_expression}")
        if selling_expression_note:
            material_lines.append(f"卖点表达边界：{selling_expression_note}")

    lines = ["生文指令：", generation_instruction]
    lines.extend(["", "内容方向：", content_direction or "按本篇业务规则自然展开。"])
    if material_lines:
        lines.extend(["", "本篇素材：", *[f"- {line}" for line in material_lines]])

    if writing_requirements:
        lines.extend(["", "写法：", *[f"- {line}" for line in writing_requirements]])

    examples = _string_list(business_rule.get("examples"))
    if examples:
        lines.extend(
            [
                "",
                "参考示例（低权重，只借真人表达，不照抄事实和句式）：",
                *[f"- {line}" for line in examples],
            ]
        )
    final_requirements = [*generation_requirements, *hard_boundaries]
    if output_format:
        final_requirements.append(output_format)
    if final_requirements:
        lines.extend(["", "生成要求：", *[f"- {line}" for line in final_requirements]])
    return "\n".join(lines).strip()


_LIFE_ENTRY_SLOT_SECTION = re.compile(
    r"\n*【生活入口槽位】\s*\n(?P<options>(?:\s*-\s*[^\n]+\n?)+)"
)


def _render_rule_corpus_life_entry_slot(corpus: str, *, item_no: int) -> str:
    match = _LIFE_ENTRY_SLOT_SECTION.search(corpus)
    if match is None:
        return corpus

    options = [
        line.strip()[1:].strip()
        for line in match.group("options").splitlines()
        if line.strip().startswith("-") and line.strip()[1:].strip()
    ]
    if not options:
        return corpus

    selected = options[(max(1, item_no) - 1) % len(options)]
    replacement = f"\n\n本篇抽中的生活入口：\n- {selected}\n"
    rendered = corpus[: match.start()] + replacement + corpus[match.end() :]
    return rendered.replace("【生活入口】", selected).strip()


_ATTENTION_EVENT_SLOT_SECTION = re.compile(
    r"\n*【孩子专注事件槽位】\s*\n(?P<options>(?:\s*-\s*[^\n]+\n?)+)"
)


def _render_rule_corpus_attention_event_slot(corpus: str, *, item_no: int) -> str:
    match = _ATTENTION_EVENT_SLOT_SECTION.search(corpus)
    if match is None:
        return corpus

    options = [
        line.strip()[1:].strip()
        for line in match.group("options").splitlines()
        if line.strip().startswith("-") and line.strip()[1:].strip()
    ]
    if not options:
        return corpus

    selected = options[(max(1, item_no) - 1) % len(options)]
    replacement = f"\n\n本篇抽中的孩子专注事件：\n- {selected}\n"
    rendered = corpus[: match.start()] + replacement + corpus[match.end() :]
    return rendered.replace("【孩子专注事件】", selected).strip()


_PROTECTION_FEEDBACK_SLOT_SECTION = re.compile(
    r"\n*【保护力日常反馈槽位】\s*\n(?P<options>(?:\s*-\s*[^\n]+\n?)+)"
)


def _render_rule_corpus_protection_feedback_slot(corpus: str, *, item_no: int) -> str:
    match = _PROTECTION_FEEDBACK_SLOT_SECTION.search(corpus)
    if match is None:
        return corpus

    options = [
        line.strip()[1:].strip()
        for line in match.group("options").splitlines()
        if line.strip().startswith("-") and line.strip()[1:].strip()
    ]
    if not options:
        return corpus

    selected = options[(max(1, item_no) - 1) % len(options)]
    replacement = f"\n\n本篇抽中的保护力日常反馈：\n- {selected}\n"
    rendered = corpus[: match.start()] + replacement + corpus[match.end() :]
    return rendered.replace("【保护力日常反馈】", selected).strip()


_INSPIRATION_CLUE_SLOT_SECTION = re.compile(
    r"\n*【本篇灵感线索(?:槽位)?】\s*\n(?P<options>(?:\s*-\s*[^\n]+\n?)+)"
)
_NO_INSPIRATION_CLUE = "不使用灵感线索"


def _render_rule_corpus_inspiration_clue_slot(corpus: str, *, item_no: int) -> str:
    match = _INSPIRATION_CLUE_SLOT_SECTION.search(corpus)
    if match is None:
        return corpus

    options = [
        line.strip()[1:].strip()
        for line in match.group("options").splitlines()
        if line.strip().startswith("-") and line.strip()[1:].strip()
    ]
    if not options:
        return corpus

    selected = options[(max(1, item_no) - 1) % len(options)]
    rendered = (corpus[: match.start()] + corpus[match.end() :]).strip()
    rendered = rendered.replace("本篇灵感线索", "本篇素材中的灵感线索")
    if selected == _NO_INSPIRATION_CLUE:
        return rendered
    return _append_rule_corpus_material(rendered, label="灵感线索", value=selected)


_SELLING_EXPRESSION_SLOT_SECTION = re.compile(
    r"\n*【卖点表达(?:槽位)?】[ \t]*\n"
    r"(?P<options>(?:[ \t]*-[ \t]*卖点表达：[^\n]+(?:\n[ \t]+注意：[^\n]+)?(?:\n|$))+)"
)
_SELLING_EXPRESSION_SLOT_ENTRY = re.compile(
    r"^[ \t]*-[ \t]*卖点表达：(?P<selling>[^\n]+)"
    r"(?:\n[ \t]+注意：(?P<note>[^\n]+))?",
    re.MULTILINE,
)


def _render_structured_selling_painpoint_expression(corpus: str, *, expression: str) -> str:
    normalized_expression = str(expression or "").strip()
    if not normalized_expression:
        return corpus
    return _append_rule_corpus_material(
        corpus,
        label="卖点痛点表达",
        value=normalized_expression,
    )


def _append_rule_corpus_material(corpus: str, *, label: str, value: str) -> str:
    normalized_value = str(value or "").strip()
    if not normalized_value:
        return corpus
    material_line = f"- {label}：{normalized_value}"
    if material_line in corpus:
        return corpus
    boundary_match = re.search(r"\n*事实与合规边界：", corpus)
    if boundary_match is None:
        if "本篇素材：" in corpus:
            return (corpus.rstrip() + "\n" + material_line).strip()
        return (corpus.rstrip() + "\n\n本篇素材：\n" + material_line).strip()
    before = corpus[: boundary_match.start()].rstrip()
    after = corpus[boundary_match.start() :].lstrip()
    if "本篇素材：" in before:
        return f"{before}\n{material_line}\n\n{after}".strip()
    return f"{before}\n\n本篇素材：\n{material_line}\n\n{after}".strip()


def _render_rule_corpus_selling_expression_slot(corpus: str, *, item_no: int) -> str:
    match = _SELLING_EXPRESSION_SLOT_SECTION.search(corpus)
    if match is None:
        return corpus

    options = [
        (entry.group("selling").strip(), str(entry.group("note") or "").strip())
        for entry in _SELLING_EXPRESSION_SLOT_ENTRY.finditer(match.group("options"))
    ]
    if not options:
        return corpus

    selling, note = options[(max(1, item_no) - 1) % len(options)]
    rendered = (corpus[: match.start()] + corpus[match.end() :]).strip()
    rendered = _append_rule_corpus_material(rendered, label="卖点表达", value=selling)
    if note:
        rendered = _append_rule_corpus_material(rendered, label="卖点表达边界", value=note)
    return rendered


def _royal_compact_article_prompt(
    business_rule: dict[str, Any],
    *,
    selected_keywords: list[dict[str, Any]],
    output_format: str,
) -> str:
    task_instruction, generation_instruction, corpus = _split_royal_prompt_opening(
        str(business_rule.get("corpus") or "")
    )
    speaking_style = ""
    variation_slots = [
        item
        for item in business_rule.get("variation_slots") or []
        if isinstance(item, dict) and str(item.get("value") or "").strip()
    ]
    diversity_line = "同批内容只在措辞和节奏上发散，不新增业务规则之外的场景或产品事实。"
    for item in selected_keywords:
        category_code = str(item.get("category_code") or "").strip()
        lines = [str(line or "").strip() for line in item.get("corpus") or [] if str(line or "").strip()]
        if category_code == "article_speaking_style" and lines and not speaking_style:
            speaking_style = lines[0]

    lines = [
        task_instruction,
    ]
    if generation_instruction:
        lines.extend(["", "生文指令：", generation_instruction])
    lines.extend(["", "这篇要写的事：", corpus])
    if variation_slots:
        lines.extend(
            [
                "",
                "本篇已抽中的变化条件：",
                *[
                    f"- {str(item.get('slot_name') or '变化条件').strip()}：{str(item.get('value') or '').strip()}"
                    for item in variation_slots
                ],
            ]
        )
    lines.extend(
        [
            "",
            "写法：",
            "- 只围绕上面的一个生活入口写，不叠加表达语料里的其他场景、人设故事、补货动作或第二条主线。",
            "- 皇家美素佳儿是生活现场里的当前口粮；产品名出现一次，业务规则指定的核心卖点要写出来，只展开一个选择理由和一个自家反馈，不补第二套好处。",
            "- 标题从正文自然提炼，不超过20字；正文80-160字，可以有1-3个自然小段。",
            "- 不写具体年龄和段数，不自行新增业务规则未指定的专业成分；不写季节疾病、医疗诊断、孩子自己操作奶具或喝完马上安静、睡着等即时结果。",
            "- 情绪变化按业务规则自然写出来，可以从担心、犹豫写到松下来或庆幸；情绪必须由选择前后的具体事情推动，不单独喊安心、值得或选对了。",
            (
                "- 是否推荐、是否使用emoji、是否分段，按本篇生文指令执行；"
                "除此之外不额外补购买判断、品牌总结或漂亮结尾。"
                if generation_instruction
                else "- 说清这件事就停，不额外补推荐、购买判断、品牌总结或漂亮结尾。"
            ),
        ]
    )
    if speaking_style:
        lines.append(f"- 说话感觉：{speaking_style}")
    lines.append(f"- 发散边界：{diversity_line}")

    cleaned_output_format = str(output_format or "").strip()
    if cleaned_output_format:
        lines.extend(["", "输出格式：", cleaned_output_format])
    return "\n".join(lines).strip()


def _split_royal_prompt_opening(corpus: str) -> tuple[str, str, str]:
    default_task = "任务：写一篇小红书妈妈UGC生活记录，正文自然提到一次皇家美素佳儿。"
    lines = str(corpus or "").strip().splitlines()
    if not lines:
        return default_task, "", ""
    if lines[0].strip() == "## 生文指令":
        instruction_index = next(
            (index for index in range(1, len(lines)) if lines[index].strip()),
            None,
        )
        if instruction_index is not None:
            return (
                "任务：按本篇生文指令写一篇小红书妈妈UGC内容，正文自然提到皇家美素佳儿。",
                lines[instruction_index].strip(),
                "\n".join(lines[instruction_index + 1 :]).strip(),
            )
    if lines[0].strip().startswith("任务："):
        return lines[0].strip(), "", "\n".join(lines[1:]).strip()
    return default_task, "", str(corpus or "").strip()


def _append_final_output_format(prompt: str, output_format: str) -> str:
    output_format = str(output_format or "").strip()
    if not output_format:
        return prompt.strip()
    cleaned = prompt.strip()
    if output_format in cleaned:
        cleaned = cleaned.replace(output_format, "").strip()
    return cleaned + "\n\n【输出格式】\n" + output_format


def _normalize_expression_corpus_labels(prompt: str) -> str:
    return (
        str(prompt or "")
        .replace("【本次自动选中的系统关键词语料】", "【本次自动选中的表达扩散语料】")
        .replace("【系统关键词语料】", "【表达扩散语料】")
        .replace("根据生成要求、业务规则和系统关键词语料生成内容", "根据生成要求、业务规则和表达扩散语料生成内容")
    )


def _normalize_comment_prompt_labels(prompt: str) -> str:
    normalized = (
        str(prompt or "")
        .replace("【业务规则】", "【本条要求】")
        .replace("【本次自动选中的表达扩散语料】", "【参考表达】")
        .replace("【表达扩散语料】", "【参考表达】")
        .replace("根据生成要求、业务规则和表达扩散语料生成内容", "根据生成要求、本条要求和表达扩散语料生成内容")
        .replace("系统内置关键词语料", "表达扩散语料")
        .replace("先看业务规则里的参考示例", "先看本条要求里的参考示例")
        .replace("不要复述规则", "不要复述要求")
        .replace("表达扩散语料", "参考表达")
        .replace("业务规则", "本条要求")
    )
    normalized = normalized.replace("请根据本条要求和参考表达，生成一条自然评论。", "请根据本条要求，生成一条自然评论。")
    normalized = normalized.replace("根据生成要求、本条要求和参考表达生成内容", "根据生成要求和本条要求生成内容")
    normalized = re.sub(r"\n{0,2}【参考表达】\s*(?=\n【[^】]+】)", "\n\n", normalized)
    return normalized.strip()


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
            "【本条要求】\n{{ business_rule }}"
        )
    return (
        "你是小红书母婴内容生成 expert。\n"
        "根据生成要求、业务规则和表达扩散语料生成内容。\n\n"
        "【生成要求】\n{{ generation_requirements }}\n\n"
        "【业务规则】\n{{ business_rule }}\n\n"
        "【表达扩散语料】\n{{ keyword_corpus }}"
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
