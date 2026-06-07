"""Preflight checks for the unified content generation flow."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_agent import ExecutorRegistry
from app.models.expert_config import ExpertConfig
from app.models.llm_model_route import LLMModelRoute
from app.models.maga_assets import AssetRegistry
from app.schemas.content_batch_report import (
    ContentGenerationPreflightCheck,
    ContentGenerationPreflightResponse,
)
from app.services.business_forbidden_term_service import BusinessForbiddenTermService
from app.services.comment_angle_rule_service import COMMENT_ANGLE_RULE_ASSET_TYPE
from app.services.content_generation_expert_service import (
    CONTENT_REWRITE_CAPABILITY,
    DEFAULT_REWRITE_EXPERT_CONFIG_CODE,
)
from app.services.forbidden_term_review_service import STATIC_FORBIDDEN_TERMS
from app.services.product_experience_rule_service import PRODUCT_EXPERIENCE_RULE_ASSET_TYPE
from app.services.system_prompt_keyword_service import (
    DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
    SystemPromptKeywordService,
    fallback_system_prompt_keyword_content,
    normalize_system_prompt_keyword_content,
)
from app.services.unified_content_generation_service import (
    CONTENT_GENERATE_CAPABILITY,
    DEFAULT_ARTICLE_EXPERT_CONFIG_CODE,
    DEFAULT_COMMENT_EXPERT_CONFIG_CODE,
    _select_keyword_bundle,
)


@dataclass(frozen=True)
class _RuleAssetContext:
    asset: AssetRegistry | None
    asset_key: str
    asset_type: str | None
    content_type: str | None
    usable_rule_count: int = 0
    keyword_asset_key: str = DEFAULT_SYSTEM_KEYWORD_ASSET_KEY


class ContentGenerationPreflightService:
    """Validate generation dependencies before operators start an expensive batch."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check(
        self,
        *,
        asset_key: str,
        asset_type: str | None,
        executor_code: str,
    ) -> ContentGenerationPreflightResponse:
        checks: list[ContentGenerationPreflightCheck] = []
        context = await self._check_rule_package(
            asset_key=asset_key,
            asset_type=asset_type,
            checks=checks,
        )
        content_type = context.content_type or "article"

        await self._check_system_keywords(
            content_type=content_type,
            keyword_asset_key=context.keyword_asset_key,
            checks=checks,
        )
        await self._check_experts_and_routes(content_type=content_type, checks=checks)
        await self._check_executor(executor_code=executor_code, checks=checks)
        await self._check_audit_flow(asset_key=asset_key, checks=checks)

        blocking_codes = [item.code for item in checks if item.status == "fail"]
        warning_codes = [item.code for item in checks if item.status == "warning"]
        return ContentGenerationPreflightResponse(
            passed=not blocking_codes,
            status="blocked" if blocking_codes else "warning" if warning_codes else "ready",
            asset_key=asset_key,
            asset_type=context.asset_type or asset_type,
            content_type=context.content_type,
            executor_code=executor_code,
            checks=checks,
            blocking_codes=blocking_codes,
            warning_codes=warning_codes,
        )

    async def _check_rule_package(
        self,
        *,
        asset_key: str,
        asset_type: str | None,
        checks: list[ContentGenerationPreflightCheck],
    ) -> _RuleAssetContext:
        resolved_type = asset_type or await self._infer_rule_asset_type(asset_key)
        content_type = _content_type_for_asset_type(resolved_type)
        if resolved_type not in {COMMENT_ANGLE_RULE_ASSET_TYPE, PRODUCT_EXPERIENCE_RULE_ASSET_TYPE}:
            checks.append(
                _fail(
                    "rule_package",
                    "业务规则包",
                    "当前规则包类型暂不支持统一生文。",
                    {"asset_key": asset_key, "asset_type": resolved_type},
                )
            )
            return _RuleAssetContext(None, asset_key, resolved_type, content_type)

        asset = await self._latest_asset(resolved_type, asset_key)
        if asset is None:
            checks.append(
                _fail(
                    "rule_package",
                    "业务规则包",
                    "没有找到可用的生产态业务规则包。",
                    {"asset_key": asset_key, "asset_type": resolved_type},
                )
            )
            return _RuleAssetContext(None, asset_key, resolved_type, content_type)

        usable_count = _usable_rule_count(asset)
        keyword_asset_key = _resolve_keyword_asset_key(None, asset)
        if usable_count <= 0:
            checks.append(
                _fail(
                    "rule_package",
                    "业务规则包",
                    "规则包里没有可用于生成的规则行。",
                    {
                        "asset_id": asset.id,
                        "asset_key": asset.asset_key,
                        "asset_type": asset.asset_type,
                        "version_no": asset.version_no,
                        "keyword_asset_key": keyword_asset_key,
                    },
                )
            )
        else:
            checks.append(
                _pass(
                    "rule_package",
                    "业务规则包",
                    f"已找到 {usable_count} 条可生成规则。",
                    {
                        "asset_id": asset.id,
                        "asset_key": asset.asset_key,
                        "asset_type": asset.asset_type,
                        "version_no": asset.version_no,
                        "usable_rule_count": usable_count,
                        "keyword_asset_key": keyword_asset_key,
                    },
                )
            )
        return _RuleAssetContext(asset, asset_key, resolved_type, content_type, usable_count, keyword_asset_key)

    async def _check_system_keywords(
        self,
        *,
        content_type: str,
        keyword_asset_key: str,
        checks: list[ContentGenerationPreflightCheck],
    ) -> None:
        service = SystemPromptKeywordService(self.db)
        asset = await service.get_latest_asset(keyword_asset_key)
        content = normalize_system_prompt_keyword_content(
            asset.content_json if asset else fallback_system_prompt_keyword_content()
        )
        selected = _select_keyword_bundle(content, content_type=content_type, item_no=1)
        enabled_category_count = _enabled_category_count(content, content_type=content_type)
        detail = {
            "asset_key": keyword_asset_key,
            "source": "asset_registry" if asset else "fallback",
            "version_no": asset.version_no if asset else None,
            "enabled_category_count": enabled_category_count,
            "selected_keyword_count": len(selected),
        }
        if not selected:
            checks.append(
                _fail(
                    "system_keywords",
                    "系统提示词关键词",
                    "没有可用于当前内容类型的启用关键词语料。",
                    detail,
                )
            )
        elif asset is None:
            checks.append(
                _warning(
                    "system_keywords",
                    "系统提示词关键词",
                    "未保存正式关键词资产，本次会使用系统内置种子。",
                    detail,
                )
            )
        else:
            checks.append(
                _pass(
                    "system_keywords",
                    "系统提示词关键词",
                    f"可自动选择 {len(selected)} 类关键词。",
                    detail,
                )
            )

    async def _check_experts_and_routes(
        self,
        *,
        content_type: str,
        checks: list[ContentGenerationPreflightCheck],
    ) -> None:
        generation_code = (
            DEFAULT_COMMENT_EXPERT_CONFIG_CODE
            if content_type == "comment"
            else DEFAULT_ARTICLE_EXPERT_CONFIG_CODE
        )
        generation_ok = await self._check_one_expert(
            expert_config_code=generation_code,
            check_code="generation_expert",
            label="生成 Expert",
            checks=checks,
        )
        rewrite_ok = await self._check_one_expert(
            expert_config_code=DEFAULT_REWRITE_EXPERT_CONFIG_CODE,
            check_code="rewrite_expert",
            label="审核改写 Expert",
            checks=checks,
        )
        if generation_ok and rewrite_ok:
            checks.append(
                _pass(
                    "audit_rewrite_path",
                    "审核改写链路",
                    "生成后会进入 MAGA 违禁词审核，并在命中时调用 content.rewrite。",
                    {
                        "rewrite_capability": CONTENT_REWRITE_CAPABILITY,
                        "rewrite_expert_config_code": DEFAULT_REWRITE_EXPERT_CONFIG_CODE,
                    },
                )
            )

    async def _check_one_expert(
        self,
        *,
        expert_config_code: str,
        check_code: str,
        label: str,
        checks: list[ContentGenerationPreflightCheck],
    ) -> bool:
        expert = await self._get_expert(expert_config_code)
        if expert is None:
            checks.append(
                _fail(
                    check_code,
                    label,
                    "未找到正式 Expert 配置。",
                    {"expert_config_code": expert_config_code},
                )
            )
            return False
        model_config = expert.model_config or {}
        provider_code = str(model_config.get("provider_code") or model_config.get("provider") or "").strip()
        model_code = str(expert.model_code or model_config.get("model_code") or "").strip()
        detail = {
            "expert_config_code": expert.expert_config_code,
            "expert_config_name": expert.expert_config_name,
            "provider_code": provider_code,
            "model_code": model_code,
        }
        if not expert.enabled:
            checks.append(_fail(check_code, label, "Expert 已停用。", detail))
            return False
        if not (expert.prompt_template or "").strip():
            checks.append(_fail(check_code, label, "Expert 缺少 Prompt 模板。", detail))
            return False
        if not provider_code or not model_code:
            checks.append(_fail(check_code, label, "Expert 未绑定 Provider 或模型。", detail))
            return False

        route = await self._get_model_route(provider_code=provider_code, model_code=model_code)
        if route is None:
            checks.append(
                _fail(
                    f"{check_code}_model_route",
                    f"{label}模型路由",
                    "Provider 和模型没有匹配的启用路由。",
                    detail,
                )
            )
            return False
        checks.append(
            _pass(
                check_code,
                label,
                f"已绑定 {provider_code}/{model_code}。",
                {
                    **detail,
                    "route_id": route.id,
                    "provider_model": route.provider_model,
                    "route_priority": route.priority,
                },
            )
        )
        return True

    async def _check_executor(
        self,
        *,
        executor_code: str,
        checks: list[ContentGenerationPreflightCheck],
    ) -> None:
        result = await self.db.execute(
            select(ExecutorRegistry).where(ExecutorRegistry.executor_code == executor_code).limit(1)
        )
        executor = result.scalar_one_or_none()
        if executor is None:
            checks.append(
                _fail(
                    "worker_executor",
                    "Worker 执行器",
                    "没有找到执行器注册信息。",
                    {"executor_code": executor_code},
                )
            )
            return
        capability_names = _capability_names(executor.supported_capabilities_json or executor.capabilities or [])
        missing = [
            capability
            for capability in (CONTENT_GENERATE_CAPABILITY, CONTENT_REWRITE_CAPABILITY)
            if capability not in capability_names
        ]
        detail = {
            "executor_code": executor.executor_code,
            "invoke_url": executor.invoke_url,
            "capabilities": sorted(capability_names),
        }
        if executor.enabled != 1:
            checks.append(_fail("worker_executor", "Worker 执行器", "执行器已停用。", detail))
        elif missing:
            checks.append(
                _fail(
                    "worker_capabilities",
                    "Worker 能力",
                    f"执行器缺少能力：{', '.join(missing)}。",
                    {**detail, "missing_capabilities": missing},
                )
            )
        else:
            checks.append(
                _pass(
                    "worker_capabilities",
                    "Worker 能力",
                    "执行器支持 content.generate 和 content.rewrite。",
                    detail,
                )
            )

    async def _check_audit_flow(
        self,
        *,
        asset_key: str,
        checks: list[ContentGenerationPreflightCheck],
    ) -> None:
        business_terms = await BusinessForbiddenTermService(self.db).list_terms(asset_key=asset_key)
        detail = {
            "static_forbidden_term_count": len(STATIC_FORBIDDEN_TERMS),
            "business_forbidden_term_count": len(business_terms),
        }
        if not STATIC_FORBIDDEN_TERMS:
            checks.append(_fail("forbidden_audit", "违禁词审核", "系统违禁词为空。", detail))
        else:
            message = (
                f"系统违禁词 {len(STATIC_FORBIDDEN_TERMS)} 个，"
                f"业务违禁词 {len(business_terms)} 个。"
            )
            checks.append(_pass("forbidden_audit", "违禁词审核", message, detail))
            if not business_terms:
                checks.append(
                    _warning(
                        "business_forbidden_terms",
                        "业务违禁词",
                        "当前规则包还没有业务违禁词反馈，后续可在评价反馈中补充。",
                        detail,
                    )
                )

    async def _infer_rule_asset_type(self, asset_key: str) -> str | None:
        for asset_type in (COMMENT_ANGLE_RULE_ASSET_TYPE, PRODUCT_EXPERIENCE_RULE_ASSET_TYPE):
            if await self._latest_asset(asset_type, asset_key):
                return asset_type
        return None

    async def _latest_asset(self, asset_type: str, asset_key: str) -> AssetRegistry | None:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type == asset_type,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
                AssetRegistry.asset_stage == "production",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_expert(self, expert_config_code: str) -> ExpertConfig | None:
        result = await self.db.execute(
            select(ExpertConfig)
            .where(
                ExpertConfig.expert_config_code == expert_config_code,
                ExpertConfig.is_deleted == 0,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_model_route(self, *, provider_code: str, model_code: str) -> LLMModelRoute | None:
        result = await self.db.execute(
            select(LLMModelRoute)
            .where(
                LLMModelRoute.provider_code == provider_code,
                LLMModelRoute.model_code == model_code,
                LLMModelRoute.enabled == 1,
                LLMModelRoute.is_deleted == 0,
            )
            .order_by(LLMModelRoute.priority.desc(), LLMModelRoute.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()


def _content_type_for_asset_type(asset_type: str | None) -> str | None:
    if asset_type == COMMENT_ANGLE_RULE_ASSET_TYPE:
        return "comment"
    if asset_type == PRODUCT_EXPERIENCE_RULE_ASSET_TYPE:
        return "article"
    return None


def _usable_rule_count(asset: AssetRegistry) -> int:
    items = (asset.content_json or {}).get("items")
    if asset.asset_type == COMMENT_ANGLE_RULE_ASSET_TYPE:
        return sum(
            1
            for item in items or []
            if isinstance(item, dict) and item.get("comment_angle") and item.get("corpus")
        )
    if asset.asset_type == PRODUCT_EXPERIENCE_RULE_ASSET_TYPE:
        return sum(
            1
            for item in items or []
            if isinstance(item, dict) and item.get("product_experience") and item.get("corpus")
        )
    return 0


def _enabled_category_count(content: dict[str, Any], *, content_type: str) -> int:
    count = 0
    for category in content.get("categories") or []:
        if not isinstance(category, dict) or category.get("enabled") is False:
            continue
        applicable = category.get("applicable_content_types")
        if isinstance(applicable, list) and applicable and content_type not in {str(item) for item in applicable}:
            continue
        sub_keywords = [
            item
            for item in category.get("sub_keywords") or []
            if isinstance(item, dict) and item.get("enabled") is not False
        ]
        if sub_keywords:
            count += 1
    return count


def _resolve_keyword_asset_key(explicit_key: str | None, asset: AssetRegistry | None) -> str:
    normalized = _normalize_keyword_asset_key(explicit_key)
    if normalized:
        return normalized
    for source in ((asset.content_json or {}) if asset else {}, (asset.metadata_json or {}) if asset else {}):
        normalized = _normalize_keyword_asset_key(source.get("keyword_asset_key"))
        if normalized:
            return normalized
    return DEFAULT_SYSTEM_KEYWORD_ASSET_KEY


def _normalize_keyword_asset_key(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _capability_names(raw_capabilities: list[Any]) -> set[str]:
    names: set[str] = set()
    for item in raw_capabilities:
        if isinstance(item, str):
            names.add(item)
        elif isinstance(item, dict) and item.get("capability"):
            names.add(str(item["capability"]))
    return names


def _pass(
    code: str,
    label: str,
    message: str,
    detail: dict[str, Any] | None = None,
) -> ContentGenerationPreflightCheck:
    return ContentGenerationPreflightCheck(
        code=code,
        label=label,
        status="pass",
        message=message,
        detail=detail or {},
    )


def _warning(
    code: str,
    label: str,
    message: str,
    detail: dict[str, Any] | None = None,
) -> ContentGenerationPreflightCheck:
    return ContentGenerationPreflightCheck(
        code=code,
        label=label,
        status="warning",
        message=message,
        detail=detail or {},
    )


def _fail(
    code: str,
    label: str,
    message: str,
    detail: dict[str, Any] | None = None,
) -> ContentGenerationPreflightCheck:
    return ContentGenerationPreflightCheck(
        code=code,
        label=label,
        status="fail",
        message=message,
        detail=detail or {},
    )
