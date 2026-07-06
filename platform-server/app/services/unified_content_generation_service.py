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
        selected_prompt_slots = (
            _select_comment_prompt_slots(business_rule)
            if content_type == "comment"
            else []
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
            rendered_prompt = _comment_prompt_text(
                business_rule,
                selected_prompt_slots=selected_prompt_slots,
                output_format=comment_output_format,
            )
        else:
            rendered_prompt = _render_template(expert["prompt_template"], variables)
        input_snapshot = {
            "schema_version": "1",
            "capability": CONTENT_GENERATE_CAPABILITY,
            "content_type": content_type,
            "output_fields": output_fields,
            "business_rule": business_rule,
            "selected_keywords": selected_keywords,
            "selected_prompt_slots": selected_prompt_slots,
            "output_format": comment_output_format,
            "output_format_mode": comment_output_format.get("mode"),
            "expansion_count": comment_output_format.get("count"),
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
        "business_rule": _business_rule_text(business_rule, content_type=content_type),
        "keyword_corpus": _keyword_corpus_text(selected_keywords, content_type=content_type),
        "selected_keywords_json": json.dumps(selected_keywords, ensure_ascii=False, indent=2),
        "generation_requirements": _generation_requirements(
            content_type,
            output_fields,
            business_rule,
            selected_keywords,
        ),
    }


def _business_rule_text(rule: dict[str, Any], *, content_type: str | None = None) -> str:
    if content_type == "comment":
        return _comment_rule_text(rule)

    lines: list[str] = []
    if content_type == "article" and str(rule.get("corpus") or "").strip():
        # 文章业务规则由运营直接写成可读的写作规则；prompt 里不再重复渲染
        # rule name / corpus label，避免工程字段污染生成。
        lines.append(str(rule.get("corpus") or "").strip())
    else:
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
    if rule.get("render_reference_examples") is not False:
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


def _comment_prompt_text(
    rule: dict[str, Any],
    *,
    selected_prompt_slots: list[dict[str, Any]] | None = None,
    output_format: dict[str, Any] | None = None,
) -> str:
    product_name = _comment_product_name(rule)
    major = str(rule.get("business_rule") or "").split("-", 1)[0].strip()
    context = _comment_context_line(rule, product_name)
    focus = _comment_focus_line(rule)
    notes = _comment_prompt_notes(rule)
    examples = _comment_prompt_examples(rule)
    output_format = output_format or _comment_output_format_config(rule)
    generation_lines: list[str] = []
    configured = str(rule.get("generation_requirements") or "").strip()
    if configured:
        generation_lines.append(configured)
    generation_lines.extend(_comment_generation_lines(output_format))

    if major == "有货":
        lines = [context]
    else:
        lines = [
            f"你是一位妈妈，在小红书母婴评论区回复别人关于{product_name}的帖子。",
            "",
            context,
        ]
    if focus:
        lines.extend(["", focus])
    for slot in selected_prompt_slots or []:
        rendered_slot = _render_comment_prompt_slot(slot)
        if rendered_slot:
            lines.extend(["", rendered_slot])
    if notes:
        lines.extend(["", "注意：", *[f"- {note}" for note in notes]])
    if examples:
        lines.extend(["", "以下参考示例仅供参考，不照抄、不固定句式：", *[f"- {item}" for item in examples]])
    lines.extend(["", "【生成要求】", *generation_lines])
    return "\n".join(line for line in lines if line is not None).strip()


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
    raw_slots = rule.get("prompt_slots") or rule.get("comment_prompt_slots")
    slots = _normalize_comment_prompt_slots(raw_slots)
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
        return f"你看到有人在聊{product_name}会员权益、集罐或积分活动，想把自己看到的权益信息顺手说一下。"
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
    notes = [
        "评论内容不用很丰富，简单表达含义和情绪即可。",
    ]
    if major != "有货":
        notes.append("不要写成品牌公告、客服回复、科普说明或广告口播。")
    if _is_a2_sentiment_comment_rule(rule):
        notes.append("不要说缺货、断粮等消极词。")
        notes.append("不要直接说其他奶粉品牌名，如需提到对比或转奶对象，用其他品牌、别的牌子、其他奶粉、之前的奶粉这类泛化说法。")
    if major == "有货":
        notes.append("字数在10到20字之间。")
    else:
        notes.append("字数不要超过80字，具体长短参考示例。")
    return notes


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


def _keyword_corpus_text(selected_keywords: list[dict[str, Any]], *, content_type: str | None = None) -> str:
    parts = []
    for item in _ordered_keyword_corpus_items(selected_keywords):
        # 生成要求要放在 prompt 顶部独立生效，不再在系统关键词语料区重复出现。
        category_code = str(item.get("category_code") or "").strip()
        if category_code in GENERATION_REQUIREMENT_CATEGORY_CODES:
            continue
        # 重要逻辑：文章业务规则已经承载篇幅和排版边界，避免再把格式控制
        # 作为一段系统关键词塞进 prompt，造成重复约束和工程味。
        if content_type == "article" and category_code == "article_format_control":
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
    parts = []
    mouth_phrase_requirement = _mouth_phrase_budget_requirement(business_rule)
    if mouth_phrase_requirement:
        parts.append(mouth_phrase_requirement)
    content_path_requirement = _content_path_control_requirement(content_type, business_rule)
    if content_path_requirement:
        parts.append(content_path_requirement)
    article_title_requirement = _article_title_generation_requirement(content_type, output_fields)
    if article_title_requirement:
        parts.append(article_title_requirement)
    parts.extend(_selected_generation_requirements(selected_keywords))
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
        "输出 JSON 对象，字段包含 title 和 body；标题单独写，正文按业务规则控制篇幅和表达。"
        "参考系统关键词调整语气，但具体内容只跟随业务规则。"
    )


def _article_title_generation_requirement(content_type: str, output_fields: list[str]) -> str | None:
    if content_type != "article" and output_fields != ["title", "body"]:
        return None
    return (
        "标题要像真人随手起的小红书标题，不要总结正文卖点，不要写成栏目名、攻略名、导购标题或品牌 slogan；"
        "标题里不要堆专业成分词、数字配方、功效判断或“第几个原因/实录/观察/好在哪”这类总结话术；"
        "可以从正文里挑一个自然短句、生活细节、真实疑问或轻微吐槽来做标题，短一点也可以。"
        "正文按业务规则控制篇幅和表达。"
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
    if allowed_terms:
        parts.append("本篇如果自然顺口，可以偶尔使用：" + "、".join(allowed_terms) + "；不用为了使用而使用。")
    if avoid_terms:
        parts.append(
            "除上面列出的可用口癖外，本篇不要使用其他批量高频口头禅；"
            "可换成具体动作、具体观察，或直接不写总结口头禅。"
        )
    return "".join(parts)


def _content_path_control_requirement(content_type: str, business_rule: dict[str, Any]) -> str | None:
    if content_type != "article":
        return None
    control = business_rule.get("content_path_control") if isinstance(business_rule, dict) else None
    if isinstance(control, str):
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
        "【生成要求】\n{{ generation_requirements }}\n\n"
        "【业务规则】\n{{ business_rule }}\n\n"
        "【系统关键词语料】\n{{ keyword_corpus }}"
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
