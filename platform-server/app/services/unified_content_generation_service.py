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

CONTENT_GENERATE_CAPABILITY = "content.generate"
SYSTEM_KEYWORD_ASSET_TYPE = "content_generation_keywords"
DEFAULT_SYSTEM_KEYWORD_ASSET_KEY = "default_content_generation_keywords"
DEFAULT_COMMENT_EXPERT_CONFIG_CODE = "comment_generator_v1"
DEFAULT_ARTICLE_EXPERT_CONFIG_CODE = "article_generator_v1"

KEYWORD_CATEGORIES = [
    ("persona", "人设"),
    ("writing_instruction", "生文指令"),
    ("perturbation_rule", "扰动规则"),
    ("writing_method", "写作手法"),
]


@dataclass(frozen=True)
class UnifiedGenerationSnapshot:
    input_snapshot: dict[str, Any]
    asset_refs: dict[str, Any]


class UnifiedContentGenerationService:
    """Compile one executable generation prompt from a business rule package.

    The operator-facing input remains only the uploaded business rule package.
    MAGA then selects one sub-keyword from each built-in category and renders
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
        keyword_asset_key: str = DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
        model_config: dict[str, Any] | None = None,
    ) -> UnifiedGenerationSnapshot:
        keyword_asset = await self._latest_keyword_asset(keyword_asset_key)
        keyword_content = keyword_asset.content_json if keyword_asset else _fallback_keyword_asset_content()
        selected_keywords = _select_keyword_bundle(keyword_content, item_no=item_no)
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
            "keyword_asset": _keyword_asset_ref(keyword_asset, keyword_asset_key),
            "expert": expert,
            "model_config": expert["model_config"],
            "template_variables": variables,
            "rendered_prompt": rendered_prompt,
        }
        return UnifiedGenerationSnapshot(
            input_snapshot=input_snapshot,
            asset_refs={
                "business_rule": _business_rule_ref(business_rule),
                "keyword_asset": _keyword_asset_ref(keyword_asset, keyword_asset_key),
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


def _select_keyword_bundle(content_json: dict[str, Any], *, item_no: int) -> list[dict[str, Any]]:
    categories = _categories_from_content(content_json)
    selected: list[dict[str, Any]] = []
    base = max(1, item_no) - 1
    for offset, (category_code, category_name) in enumerate(KEYWORD_CATEGORIES):
        category = categories.get(category_code) or categories.get(category_name) or {}
        sub_keywords = category.get("sub_keywords") or category.get("items") or []
        sub_keywords = [item for item in sub_keywords if isinstance(item, dict)]
        if not sub_keywords:
            continue
        item = sub_keywords[(base + offset) % len(sub_keywords)]
        corpus = item.get("corpus") or item.get("语料") or item.get("rules") or []
        if isinstance(corpus, str):
            corpus = [corpus]
        selected.append(
            {
                "category_code": category_code,
                "category_name": category.get("category_name") or category.get("name") or category_name,
                "keyword_code": item.get("keyword_code") or item.get("code") or item.get("子关键词") or item.get("keyword_name"),
                "keyword_name": item.get("keyword_name") or item.get("name") or item.get("子关键词") or item.get("keyword_code"),
                "corpus": [str(value).strip() for value in corpus if str(value).strip()],
            }
        )
    return selected


def _categories_from_content(content_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_categories = content_json.get("categories") if isinstance(content_json, dict) else None
    if isinstance(raw_categories, dict):
        return {str(key): value for key, value in raw_categories.items() if isinstance(value, dict)}
    if isinstance(raw_categories, list):
        return {
            str(item.get("category_code") or item.get("category_name") or item.get("name")): item
            for item in raw_categories
            if isinstance(item, dict)
        }
    return {}


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
        "generation_requirements": _generation_requirements(content_type, output_fields),
    }


def _business_rule_text(rule: dict[str, Any]) -> str:
    lines: list[str] = []
    if rule.get("rule_type"):
        lines.append(f"- 规则类型：{rule.get('rule_type')}")
    if rule.get("comment_angle"):
        lines.append(f"- 评论切角：{rule.get('comment_angle')}")
    if rule.get("product_experience"):
        lines.append(f"- 产品使用体验：{rule.get('product_experience')}")
    if rule.get("corpus"):
        lines.append(f"- 业务语料：\n{rule.get('corpus')}")
    examples = [str(item).strip() for item in rule.get("examples") or [] if str(item).strip()]
    supplements = [str(item).strip() for item in rule.get("supplements") or [] if str(item).strip()]
    if examples:
        lines.append("- 参考示例：\n" + "\n".join(f"  - {item}" for item in examples[:8]))
    if supplements:
        lines.append("- 补充参考：\n" + "\n".join(f"  - {item}" for item in supplements[:6]))
    if not lines:
        lines.append(json.dumps(rule, ensure_ascii=False, indent=2))
    return "\n".join(lines)


def _keyword_corpus_text(selected_keywords: list[dict[str, Any]]) -> str:
    parts = []
    for item in selected_keywords:
        corpus = item.get("corpus") or []
        corpus_text = "\n".join(f"  - {line}" for line in corpus)
        parts.append(f"- {item.get('category_name')} / {item.get('keyword_name')}：\n{corpus_text}")
    return "\n".join(parts)


def _generation_requirements(content_type: str, output_fields: list[str]) -> str:
    if content_type == "comment" or output_fields == ["comment"]:
        return (
            "只输出一条自然评论正文；像真实评论区，不要标题、编号、解释；"
            "可以借鉴示例的语义方向，但不要照搬原句；不承诺解决所有问题，不做医疗化诊断。"
        )
    return (
        "输出 JSON 对象，字段包含 title 和 body；正文保持小红书自然表达；"
        "业务规则优先，四类关键词语料用于人设、指令、扰动和写法控制。"
    )


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
            "你是小红书母婴评论生成 expert。\n"
            "请根据业务规则和系统内置关键词语料，生成一条自然评论。\n\n"
            "【业务规则】\n{{ business_rule }}\n\n"
            "【本次自动选中的系统关键词语料】\n{{ keyword_corpus }}\n\n"
            "【生成要求】\n{{ generation_requirements }}"
        )
    return (
        "你是小红书母婴内容生成 expert。\n"
        "请根据业务规则和系统内置关键词语料，生成一篇自然种草内容。\n\n"
        "【业务规则】\n{{ business_rule }}\n\n"
        "【本次自动选中的系统关键词语料】\n{{ keyword_corpus }}\n\n"
        "【生成要求】\n{{ generation_requirements }}"
    )


def _normalize_model_config(value: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key in ("provider", "provider_code", "model_code", "temperature", "max_tokens", "system_prompt"):
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


def _keyword_asset_ref(asset: AssetRegistry | None, asset_key: str) -> dict[str, Any]:
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


def _fallback_keyword_asset_content() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "asset_type": SYSTEM_KEYWORD_ASSET_TYPE,
        "categories": [
            {
                "category_code": "persona",
                "category_name": "人设",
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
