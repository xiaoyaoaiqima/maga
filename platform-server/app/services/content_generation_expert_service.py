"""Content-generation flow Expert config service.

This layer keeps the new content flow away from the old RAAP Expert/Agent
workbench: an Expert here means one prompt template plus model parameters for
one execution capability.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expert_config import ExpertConfig
from app.schemas.content_generation_expert import (
    ContentGenerationExpertResponse,
    ContentGenerationExpertUpsertRequest,
)
from app.schemas.expert_config import ExpertConfigCreate, ExpertConfigUpdate
from app.services.expert_config_service import ExpertConfigService
from app.services.unified_content_generation_service import (
    CONTENT_GENERATE_CAPABILITY,
    DEFAULT_ARTICLE_EXPERT_CONFIG_CODE,
    DEFAULT_COMMENT_EXPERT_CONFIG_CODE,
    _fallback_prompt_template,
    _normalize_model_config,
)

CONTENT_REWRITE_CAPABILITY = "content.rewrite"
DEFAULT_REWRITE_EXPERT_CONFIG_CODE = "content_rewrite_v1"


@dataclass(frozen=True)
class ContentFlowExpertSpec:
    code: str
    name: str
    expert_type: str
    stage: str
    capability: str
    content_type: str
    description: str
    prompt_template: str
    model_config: dict[str, Any]
    variables: tuple[str, ...]


CONTENT_FLOW_EXPERT_SPECS: tuple[ContentFlowExpertSpec, ...] = (
    ContentFlowExpertSpec(
        code=DEFAULT_ARTICLE_EXPERT_CONFIG_CODE,
        name="文章生成 Expert",
        expert_type="GENERATION",
        stage="生文",
        capability=CONTENT_GENERATE_CAPABILITY,
        content_type="article",
        description="帖子内容生成；接收业务规则包和系统提示词关键词。",
        prompt_template=_fallback_prompt_template("article"),
        model_config={"temperature": 0.8, "max_tokens": 2048},
        variables=("business_rule", "keyword_corpus", "generation_requirements", "selected_keywords_json"),
    ),
    ContentFlowExpertSpec(
        code=DEFAULT_COMMENT_EXPERT_CONFIG_CODE,
        name="评论生成 Expert",
        expert_type="GENERATION",
        stage="生评论",
        capability=CONTENT_GENERATE_CAPABILITY,
        content_type="comment",
        description="评论业务规则生成；接收业务规则（业务规则）和系统提示词关键词。",
        prompt_template=_fallback_prompt_template("comment"),
        model_config={"temperature": 0.85, "max_tokens": 512},
        variables=("business_rule", "keyword_corpus", "generation_requirements", "selected_keywords_json"),
    ),
    ContentFlowExpertSpec(
        code=DEFAULT_REWRITE_EXPERT_CONFIG_CODE,
        name="审核改写 Expert",
        expert_type="REWRITE",
        stage="改写",
        capability=CONTENT_REWRITE_CAPABILITY,
        content_type="article,comment",
        description="违禁词或相似度命中后的自然改写；审核闸口仍由 MAGA 确定性控制。",
        prompt_template=(
            "你是中文内容审核后的自然改写 Expert。\n"
            "只根据审核结果改写必要位置，保留原意、语气、业务规则和已选关键词方向。\n\n"
            "rewrite 的首要任务是删除、压缩或替换问题内容，不是扩写、润色或制造多样化；只有删除后语义断裂时，才补极短连接。\n\n"
            "如果改写来源是运营反馈，反馈意图优先于词级保守替换；可以重写被反馈影响的一整句，避免机械同义改写。\n\n"
            "【内容类型】\n{{ content_type_label }}\n\n"
            "【原内容】\n{{ previous_content }}\n\n"
            "【必须删除或自然替换的违禁词】\n{{ forbidden_hits }}\n\n"
            "【指定替换映射】\n{{ forbidden_replacements }}\n\n"
            "【业务规则】\n{{ business_rule }}\n\n"
            "【本次自动选中的系统关键词语料】\n{{ selected_keywords_json }}\n\n"
            "【改写指令】\n{{ rewrite_instructions }}\n\n"
            "【输出要求】\n{{ output_requirements }}"
        ),
        model_config={"temperature": 0.35, "max_tokens": 1200},
        variables=(
            "content_type_label",
            "previous_content",
            "forbidden_hits",
            "forbidden_replacements",
            "business_rule",
            "selected_keywords_json",
            "rewrite_instructions",
            "output_requirements",
        ),
    ),
)

_SPEC_BY_CODE = {item.code: item for item in CONTENT_FLOW_EXPERT_SPECS}
_TEMPLATE_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


class ContentGenerationExpertService:
    """Read and persist Expert configs that are actually used by content flow."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.expert_config_service = ExpertConfigService(db)

    async def list_flow_experts(self) -> list[ContentGenerationExpertResponse]:
        return [await self.get_flow_expert(spec.code) for spec in CONTENT_FLOW_EXPERT_SPECS]

    async def get_flow_expert(self, expert_config_code: str) -> ContentGenerationExpertResponse:
        spec = self._require_spec(expert_config_code)
        expert = await self._get_enabled_or_disabled_by_code(spec.code)
        if expert is None:
            return self._fallback_response(spec)
        return self._response_from_model(spec, expert)

    async def get_expert_snapshot(self, expert_config_code: str) -> dict[str, Any]:
        expert = await self.get_flow_expert(expert_config_code)
        return {
            "expert_config_code": expert.expert_config_code,
            "expert_config_name": expert.expert_config_name,
            "expert_type": expert.expert_type,
            "prompt_template": expert.prompt_template,
            "model_config": expert.model_config_data,
            "source": expert.source,
        }

    async def upsert_flow_expert(
        self,
        expert_config_code: str,
        request: ContentGenerationExpertUpsertRequest,
    ) -> ContentGenerationExpertResponse:
        spec = self._require_spec(expert_config_code)
        existing = await self._get_enabled_or_disabled_by_code(spec.code)
        payload = {
            "expert_config_name": request.expert_config_name.strip() or spec.name,
            "expert_type": spec.expert_type,
            "expert_app": "maga-worker",
            "expert_service": "content-generation-flow",
            "expert_func": spec.capability,
            "expert_func_name": spec.stage,
            "description": request.description,
            "model_code": request.model_code,
            "model_config": _normalize_model_config(request.model_config_data or {}),
            "prompt_template": request.prompt_template.strip() or spec.prompt_template,
            "enabled": request.enabled,
            "updated_by": request.updated_by,
        }
        if existing is None:
            create_payload = ExpertConfigCreate(
                expert_config_code=spec.code,
                tenant_code=None,
                created_by=request.updated_by,
                **payload,
            )
            expert = await self.expert_config_service.create(create_payload)
        else:
            update_payload = ExpertConfigUpdate(**payload)
            expert = await self.expert_config_service.update(existing.id, update_payload)
            if expert is None:
                raise ValueError(f"ExpertConfig not found: {spec.code}")
        return self._response_from_model(spec, expert)

    async def build_rewrite_snapshot(
        self,
        *,
        content_type: str,
        previous_content: dict[str, Any],
        business_rule: dict[str, Any],
        selected_keywords: list[Any],
        forbidden_hits: list[str],
        forbidden_replacements: dict[str, str] | None = None,
        rewrite_instructions: list[str],
        output_fields: list[str],
    ) -> dict[str, Any]:
        expert = await self.get_expert_snapshot(DEFAULT_REWRITE_EXPERT_CONFIG_CODE)
        variables = rewrite_template_variables(
            content_type=content_type,
            previous_content=previous_content,
            business_rule=business_rule,
            selected_keywords=selected_keywords,
            forbidden_hits=forbidden_hits,
            forbidden_replacements=forbidden_replacements,
            rewrite_instructions=rewrite_instructions,
            output_fields=output_fields,
        )
        return {
            "expert": expert,
            "model_config": expert["model_config"],
            "template_variables": variables,
            "rendered_prompt": render_template(expert["prompt_template"], variables),
        }

    async def preview_prompt(
        self,
        *,
        expert_config_code: str,
        content_type: str | None,
        previous_content: dict[str, Any],
        business_rule: dict[str, Any],
        selected_keywords: list[dict[str, Any]],
        forbidden_hits: list[str],
    ) -> dict[str, Any]:
        spec = self._require_spec(expert_config_code)
        expert = await self.get_expert_snapshot(expert_config_code)
        if spec.capability == CONTENT_REWRITE_CAPABILITY:
            variables = rewrite_template_variables(
                content_type=content_type or "article",
                previous_content=previous_content or {"title": "原标题", "body": "原正文命中了需要改写的表达。"},
                business_rule=business_rule,
                selected_keywords=selected_keywords,
                forbidden_hits=forbidden_hits or ["示例违禁词"],
                forbidden_replacements={},
                rewrite_instructions=["只处理命中词和相关句子", "不要解释改写过程"],
                output_fields=["comment"] if content_type == "comment" else ["title", "body"],
            )
        else:
            variables = {
                "business_rule": json.dumps(business_rule or {"示例业务规则": "这里展示业务规则包内容"}, ensure_ascii=False, indent=2),
                "keyword_corpus": "\n".join(
                    f"- {item.get('category_name') or item.get('category_code')} / {item.get('keyword_name') or item.get('keyword_code')}"
                    for item in selected_keywords or []
                ) or "- 人设 / 真实妈妈：\n  - 像有真实带娃经验的妈妈表达",
                "generation_requirements": "按当前内容类型输出结果，不解释过程。",
                "selected_keywords_json": json.dumps(selected_keywords or [], ensure_ascii=False, indent=2),
            }
        return {
            "expert_config_code": expert_config_code,
            "rendered_prompt": render_template(expert["prompt_template"], variables),
            "model_config": expert["model_config"],
        }

    async def _get_enabled_or_disabled_by_code(self, expert_config_code: str) -> ExpertConfig | None:
        result = await self.db.execute(
            select(ExpertConfig)
            .where(
                ExpertConfig.expert_config_code == expert_config_code,
                ExpertConfig.is_deleted == 0,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _fallback_response(self, spec: ContentFlowExpertSpec) -> ContentGenerationExpertResponse:
        return ContentGenerationExpertResponse(
            id=None,
            expert_config_code=spec.code,
            expert_config_name=spec.name,
            expert_type=spec.expert_type,
            stage=spec.stage,
            capability=spec.capability,
            content_type=spec.content_type,
            description=spec.description,
            model_code=None,
            model_config=_normalize_model_config(spec.model_config),
            prompt_template=spec.prompt_template,
            enabled=True,
            source="fallback",
            variables=list(spec.variables),
            update_time=None,
        )

    def _response_from_model(self, spec: ContentFlowExpertSpec, expert: ExpertConfig) -> ContentGenerationExpertResponse:
        model_config = _normalize_model_config(
            {
                **spec.model_config,
                **(expert.model_config or {}),
                **({"model_code": expert.model_code} if expert.model_code else {}),
            }
        )
        return ContentGenerationExpertResponse(
            id=expert.id,
            expert_config_code=expert.expert_config_code,
            expert_config_name=expert.expert_config_name,
            expert_type=expert.expert_type or spec.expert_type,
            stage=spec.stage,
            capability=spec.capability,
            content_type=spec.content_type,
            description=expert.description or spec.description,
            model_code=expert.model_code,
            model_config=model_config,
            prompt_template=expert.prompt_template or spec.prompt_template,
            enabled=bool(expert.enabled),
            source="expert_config",
            variables=list(spec.variables),
            update_time=expert.update_time.strftime("%Y-%m-%d %H:%M:%S") if expert.update_time else None,
        )

    def _require_spec(self, expert_config_code: str) -> ContentFlowExpertSpec:
        spec = _SPEC_BY_CODE.get(expert_config_code)
        if spec is None:
            raise ValueError(f"unsupported content generation expert: {expert_config_code}")
        return spec


def rewrite_template_variables(
    *,
    content_type: str,
    previous_content: dict[str, Any],
    business_rule: dict[str, Any],
    selected_keywords: list[Any],
    forbidden_hits: list[str],
    forbidden_replacements: dict[str, str] | None = None,
    rewrite_instructions: list[str],
    output_fields: list[str],
) -> dict[str, Any]:
    is_comment = content_type == "comment" or output_fields == ["comment"]
    return {
        "content_type": content_type,
        "content_type_label": "评论" if is_comment else "文章",
        "previous_content": json.dumps(previous_content, ensure_ascii=False, indent=2),
        "business_rule": json.dumps(business_rule or {}, ensure_ascii=False, indent=2),
        "selected_keywords_json": json.dumps(selected_keywords or [], ensure_ascii=False, indent=2),
        "forbidden_hits": "、".join(forbidden_hits) if forbidden_hits else "无",
        "forbidden_replacements": (
            "\n".join(f"- {term} -> {replacement}" for term, replacement in (forbidden_replacements or {}).items())
            or "无"
        ),
        "rewrite_instructions": "\n".join(f"- {item}" for item in rewrite_instructions if str(item).strip()),
        "output_requirements": (
            "只输出改写后的评论正文，不要标题、编号、解释。"
            if is_comment
            else '只输出 JSON，格式为 {"title": "...", "body": "..."}，不要解释。'
        ),
    }


def render_template(template: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = variables.get(key, "")
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    return _TEMPLATE_PATTERN.sub(replace, template or "",).strip()
