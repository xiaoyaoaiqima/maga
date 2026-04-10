from typing import Any, Dict, List, Optional
import asyncio
import httpx
import time
from fastapi import APIRouter
from pydantic import BaseModel, Field
from loguru import logger

from app.core.config import settings
from app.services.critic_dapr_service import (
    run_critic_http,
    run_critic_tencent_http,
    run_ai_content_detector_http,
)
from app.services.keyword_filter_service import get_keyword_filter_service
from app.services.rlhf_expert_service import RLHFExpertService
from app.services.ban_v2_service import run_ban_v2
from app.services.document_parse_service import DocumentParseReq, DocumentParseService

router = APIRouter(tags=["dapr-http-invoke"])


# ==================== keyword-corpus 服务调用 ====================


class _CorpusCache:
    """语料内存缓存"""

    def __init__(self, ttl: int = 300):
        """
        Args:
            ttl: 缓存过期时间（秒），默认 5 分钟
        """
        self._cache: Dict[
            str, tuple[str, float]
        ] = {}  # {(label, tenant_code): (result, expire_time)}
        self._lock = asyncio.Lock()
        self._ttl = ttl

    async def get(self, label: str, tenant_code: str) -> str | None:
        """获取缓存"""
        key = f"ag:{label}:{tenant_code}"
        result, expire_time = self._cache.get(key, ("", 0))
        if time.time() < expire_time:
            logger.debug(f"[_CorpusCache] 命中缓存: {key}")
            return result
        return None

    async def set(self, label: str, tenant_code: str, value: str) -> None:
        """设置缓存"""
        key = f"ag:{label}:{tenant_code}"
        expire_time = time.time() + self._ttl
        self._cache[key] = (value, expire_time)
        logger.info(f"[_CorpusCache] 更新缓存: {key}, TTL={self._ttl}s")

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()


# 全局缓存实例（5分钟 TTL）
_corpus_cache = _CorpusCache(ttl=300)


def _has_unfilled_placeholder(prompt: str) -> bool:
    """
    检测提示词是否包含未填充的占位符

    未填充的占位符格式：
    - {{变量名}} - Orchestrator 层变量
    - $变量名$ - AG 层变量

    Args:
        prompt: 提示词内容

    Returns:
        True 表示有未填充的占位符（无效提示词）
    """
    if not prompt:
        return False

    import re

    # 检测 {{xxx}} 或 $xxx$ 格式的占位符
    pattern = r"\{\{[^}]+\}\}|\$[^$]+\$"
    matches = re.findall(pattern, prompt)

    if matches:
        logger.info(f"[_has_unfilled_placeholder] 检测到未填充占位符: {matches}")
        return True
    return False


async def _fetch_nodes_by_label(
    label: str, tenant_code: str = "default", bypass_cache: bool = False
) -> str:
    """
    从 keyword-corpus 服务获取指定 label 下所有节点的语料（带 5 分钟内存缓存）

    Args:
        label: 节点标签，如 "平台合规"、"品牌合规"
        tenant_code: 租户编码
        bypass_cache: 是否绕过缓存强制从 DB 加载

    Returns:
        逗号分隔的语料字符串，如 "词1,词2,词3"
    """
    # 先检查缓存（除非绕过缓存）
    if not bypass_cache:
        cached = await _corpus_cache.get(label, tenant_code)
        if cached is not None:
            return cached

    try:
        # 通过 Dapr sidecar 调用 keyword-corpus 服务
        url = (
            f"http://localhost:{settings.DAPR_HTTP_PORT}"
            f"/v1.0/invoke/raap-service-keyword-corpus/method/api/v1/categories/by-label/{label}"
        )

        params = {"tenant_code": tenant_code, "page_size": 500}

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        if data.get("code") != 0:
            logger.warning(
                f"[_fetch_nodes_by_label] API 返回错误: {data.get('message')}"
            )
            return ""

        # 打印原始数据结构（用于调试）
        items = data.get("data", {}).get("items", [])
        logger.info(f"[_fetch_nodes_by_label] 原始返回数据: items数量={len(items)}")
        if items:
            logger.info(f"[_fetch_nodes_by_label] 第一个item示例: {items[0]}")
            # 打印第一个 item 的 keywords 字段详情
            first_keywords = items[0].get("keywords", [])
            logger.info(
                f"[_fetch_nodes_by_label] 第一个item的keywords字段: {first_keywords}"
            )

        # 提取语料：从 keywords.fields 中提取
        keywords = []
        for idx, item in enumerate(items):
            # 从 keywords 字段提取
            item_keywords = item.get("keywords", [])
            logger.info(
                f"[_fetch_nodes_by_label] item[{idx}] name={item.get('name')}, keywords={item_keywords}"
            )

            for kw_idx, kw in enumerate(item_keywords):
                logger.info(f"[_fetch_nodes_by_label]   kw[{kw_idx}]={kw}")
                fields = kw.get("fields", {})
                logger.info(f"[_fetch_nodes_by_label]   fields={fields}")
                if isinstance(fields, dict):
                    for label_name, corpus_text in fields.items():
                        logger.info(
                            f"[_fetch_nodes_by_label]     label={label_name}, corpus_text={corpus_text}, type={type(corpus_text)}"
                        )
                        if corpus_text and str(corpus_text).strip():
                            keywords.append(str(corpus_text).strip())

            logger.info(
                f"[_fetch_nodes_by_label] item[{idx}] 提取后keywords数={len(keywords)}"
            )

        result = ",".join(keywords) if keywords else ""
        logger.info(
            f"[_fetch_nodes_by_label] label={label}, 获取到 {len(keywords)} 条语料"
        )
        # 打印分割后的语料（用于调试）
        logger.info(f"[_fetch_nodes_by_label] 分割后的语料: {result}")

        # 更新缓存
        await _corpus_cache.set(label, tenant_code, result)

        return result

    except httpx.HTTPStatusError as e:
        logger.warning(f"[_fetch_nodes_by_label] HTTP 错误: {e}")
        return ""
    except Exception as e:
        logger.warning(f"[_fetch_nodes_by_label] 获取语料失败: {e}")
        return ""


class ModelCfg(BaseModel):
    temperature: float = 0.7
    max_tokens: int = 2000


class RLHFTagSummarizeReq(BaseModel):
    annotations: List[Dict[str, Any]]
    comment: Optional[str] = None
    model_code: str = "gpt-4o"


class RLHFCommentSummarizeReq(BaseModel):
    """AI 总结意见请求

    支持两种总结模式：
    1. 划词评论模式：基于 annotations 生成意见
    2. 精修内容模式：对比 original_content 和 refined_content 生成意见
    3. 两者都有时，结合两种模式生成综合意见
    """

    content: str = ""  # 原文内容（兼容旧参数）
    annotations: Optional[List[Dict[str, Any]]] = None  # 划词评论列表
    original_content: Optional[str] = None  # 原文内容（用于精修对比）
    refined_content: Optional[str] = None  # 精修后内容
    model_code: str = "gpt-4o"


class CriticReq(BaseModel):
    job_id: str
    sub_job_id: str
    content_id: str
    content: str
    expert_task_id: int
    expert_config_code: str
    expert_service: str = "critic.CriticService"
    expert_func: str = "CriticIllegal"
    prompt: str
    model_code: str = "gemini-2.5-pro"
    model_cfg: ModelCfg = Field(alias="model_config")
    tenant_code: str = "default"  # 租户编码（用于多租户隔离，如违禁词过滤）


class CriticTencentReq(CriticReq):
    biztype: str | None = None


@router.post("/critic.CriticService/CriticIllegal")
async def http_critic_illegal(req: CriticReq):
    payload = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "content": req.content,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "expert_service": req.expert_service,
        "expert_func": req.expert_func,
        "prompt": req.prompt,
        "model_code": req.model_code,
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
    }
    # 不改请求参数结构：仅在服务端强制对齐 expert_func
    payload["expert_func"] = "CriticIllegal"
    return await run_critic_http(
        request_data=payload, stage="ag_ban", service_method="CriticIllegal"
    )


@router.post("/critic.CriticService/CriticUnreasonable")
async def http_critic_unreasonable(req: CriticReq):
    payload = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "content": req.content,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "expert_service": req.expert_service,
        "expert_func": req.expert_func,
        "prompt": req.prompt,
        "model_code": req.model_code,
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
    }
    payload["expert_func"] = "CriticUnreasonable"
    return await run_critic_http(
        request_data=payload,
        stage="ag_unreasonable",
        service_method="CriticUnreasonable",
    )


@router.post("/critic.CriticService/CriticCounterproductive")
async def http_critic_counterproductive(req: CriticReq):
    payload = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "content": req.content,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "expert_service": req.expert_service,
        "expert_func": req.expert_func,
        "prompt": req.prompt,
        "model_code": req.model_code,
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
    }
    payload["expert_func"] = "CriticCounterproductive"
    return await run_critic_http(
        request_data=payload,
        stage="ag_counterproductive",
        service_method="CriticCounterproductive",
    )


@router.post("/critic.CriticService/CriticGrace")
async def http_critic_grace(req: CriticReq):
    payload = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "content": req.content,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "expert_service": req.expert_service,
        "expert_func": req.expert_func,
        "prompt": req.prompt,
        "model_code": req.model_code,
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
    }
    payload["expert_func"] = "CriticGrace"
    return await run_critic_http(
        request_data=payload,
        stage="ag_grace",
        service_method="CriticGrace",
    )


@router.post("/critic.CriticService/CriticMarket")
async def http_critic_market(req: CriticReq):
    payload = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "content": req.content,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "expert_service": req.expert_service,
        "expert_func": req.expert_func,
        "prompt": req.prompt,
        "model_code": req.model_code,
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
    }
    payload["expert_func"] = "CriticMarket"
    return await run_critic_http(
        request_data=payload,
        stage="ag_market",
        service_method="CriticMarket",
    )


@router.post("/critic.CriticService/CriticBrandAlign")
async def http_critic_brand_align(req: CriticReq):
    payload = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "content": req.content,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "expert_service": req.expert_service,
        "expert_func": req.expert_func,
        "prompt": req.prompt,
        "model_code": req.model_code,
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
    }
    payload["expert_func"] = "CriticBrandAlign"
    return await run_critic_http(
        request_data=payload,
        stage="ag_brand_align",
        service_method="CriticBrandAlign",
    )


@router.post("/critic.CriticService/CriticCreativity")
async def http_critic_creativity(req: CriticReq):
    payload = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "content": req.content,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "expert_service": req.expert_service,
        "expert_func": req.expert_func,
        "prompt": req.prompt,
        "model_code": req.model_code,
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
    }
    payload["expert_func"] = "CriticCreativity"
    return await run_critic_http(
        request_data=payload,
        stage="ag_creativity",
        service_method="CriticCreativity",
    )


@router.post("/critic.CriticService/CriticPersonaAuth")
async def http_critic_persona_auth(req: CriticReq):
    payload = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "content": req.content,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "expert_service": req.expert_service,
        "expert_func": req.expert_func,
        "prompt": req.prompt,
        "model_code": req.model_code,
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
    }
    payload["expert_func"] = "CriticPersonaAuth"
    return await run_critic_http(
        request_data=payload,
        stage="ag_persona_auth",
        service_method="CriticPersonaAuth",
    )


@router.post("/critic.CriticService/CriticContentQuality")
async def http_critic_content_quality(req: CriticReq):
    payload = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "content": req.content,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "expert_service": req.expert_service,
        "expert_func": req.expert_func,
        "prompt": req.prompt,
        "model_code": req.model_code,
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
    }
    payload["expert_func"] = "CriticContentQuality"
    return await run_critic_http(
        request_data=payload,
        stage="ag_content_quality",
        service_method="CriticContentQuality",
    )


@router.post("/critic.CriticService/CriticTencent")
async def http_critic_tencent(req: CriticTencentReq):
    payload = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "content": req.content,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "expert_service": req.expert_service,
        "expert_func": req.expert_func,
        "prompt": req.prompt,
        "model_code": req.model_code,
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
        "biztype": req.biztype,
    }
    payload["expert_func"] = "CriticTencent"
    return await run_critic_tencent_http(
        request_data=payload,
        stage="ag_tencent",
        service_method="CriticTencent",
    )


# ==================== Ban V2 接口（带后验证防幻觉） ====================


@router.post("/critic.CriticService/CriticBanV2")
async def http_critic_ban_v2(req: CriticReq) -> dict:
    """
    Ban V2 - 带后验证的违禁词检测（防幻觉）

    核心特点：
    - 证据驱动的 Prompt：要求 LLM 返回 exact_text + position
    - 后验证机制：验证 LLM 声称的词是否真的在文本中
    - 自动纠正：如果所有违规都是 LLM 幻觉，自动改为通过

    返回格式与 run_critic_http 统一：
    - success: bool
    - message: str
    - score: 1 (通过) / 0 (不通过)
    - passed: bool
    - reason: str
    - post_validation: dict（幻觉检测详情）
    """
    logger.info(
        f"[BanV2] 开始审核: job_id={req.job_id}, tenant_code={req.tenant_code}, "
        f"content_id={req.content_id}, content_len={len(req.content)}"
    )

    request_data = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "content": req.content,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "prompt": req.prompt,
        "model_code": req.model_code,
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
        "tenant_code": req.tenant_code,
    }

    return await run_ban_v2(request_data)


# ==================== 违禁词精确匹配接口（无 AI，纯代码） ====================


@router.post("/critic.CriticService/CriticKeywordFilter")
async def http_critic_keyword_filter(req: CriticReq) -> dict:
    """
    违禁词精确匹配过滤

    核心特点：
    - 基于精确字符串匹配，无 AI 幻觉
    - 速度快、成本低、准确率高
    - 适用于绝对红线词（医疗/母婴/强功效类）
    - 从 prompt 中读取逗号分隔的违禁词列表

    Prompt 格式：
    "检查以下违禁词：赌博,暴力,色情"

    返回格式与 run_critic_http 统一：
    - success: bool
    - message: str
    - score: 1 (合规) / 0 (违规)
    - reason: str
    - problem_tags: List[str]
    - problem_snippets: List[str]
    """
    logger.info(
        f"[KeywordFilter] 开始审核: job_id={req.job_id}, tenant_code={req.tenant_code}, "
        f"content_id={req.content_id}, content_len={len(req.content)}, prompt_len={len(req.prompt or '')}"
    )

    # 参数校验
    content = (req.content or "").strip()
    if not content:
        return {
            "success": False,
            "message": "content 不能为空",
            "score": 0,
            "reason": "content 不能为空",
            "problem_context_list": [],
        }

    service = get_keyword_filter_service()

    # 优先使用 prompt 中的自定义关键词列表
    if req.prompt and req.prompt.strip():
        logger.info(f"[KeywordFilter] 使用 prompt 中的自定义关键词列表")
        logger.info(f"[KeywordFilter] 📋 传入的违禁词列表: {req.prompt}")
        result = service.filter_with_custom_keywords(
            content, keywords_str=req.prompt, tenant_code=req.tenant_code
        )
    else:
        # 兼容旧逻辑：如果没有 prompt，使用 ban_term 表的全局词表
        logger.warning(
            f"[KeywordFilter] prompt 为空，使用 ban_term 表的全局词表（不推荐）"
        )
        result = service.filter(content, tenant_code=req.tenant_code)

    # 详细记录检测结果
    problem_snippets = result.get("problem_snippets", [])
    if problem_snippets:
        logger.warning(
            f"[KeywordFilter] ❌ 检测到不合规内容! "
            f"score={result['score']}, "
            f"违禁词={problem_snippets}, "
            f"reason={result.get('reason', '')}"
        )
    else:
        logger.info(
            f"[KeywordFilter] ✅ 内容合规: score={result['score']}, "
            f"snippets={problem_snippets}"
        )

    # 统一返回格式（与 run_critic_http 一致）
    return {
        "success": True,
        "message": "CriticKeywordFilter 完成",
        "score": result["score"],
        "reason": result["reason"],
        "problem_tags": result.get("problem_tags", []),
        "problem_snippets": result.get("problem_snippets", []),
    }


@router.post("/critic.CriticService/CriticBrandRule")
async def http_critic_brand_rule(req: CriticReq) -> dict:
    """
    品牌规则精确匹配过滤

    核心特点：
    - 基于精确字符串匹配，无 AI 幻觉
    - 速度快、成本低、准确率高
    - 适用于品牌违禁词/品牌规范词检查
    - 从 prompt 中读取逗号分隔的关键词列表

    Prompt 格式：
    "检查以下品牌规则词：竞品名A,竞品名B,违禁表述C"

    兜底逻辑：
    - 如果 prompt 为空，自动从 keyword-corpus 服务的 nodes 表中获取 label=品牌合规 下所有节点的语料

    返回格式与 run_critic_http 统一：
    - success: bool
    - message: str
    - score: 1 (合规) / 0 (违规)
    - reason: str
    - problem_tags: List[str]
    - problem_snippets: List[str]
    """
    logger.info(
        f"[BrandRule] 开始审核: job_id={req.job_id}, tenant_code={req.tenant_code}, "
        f"content_id={req.content_id}, content_len={len(req.content)}, prompt_len={len(req.prompt or '')}"
    )

    # 参数校验
    content = (req.content or "").strip()
    if not content:
        return {
            "success": False,
            "message": "content 不能为空",
            "score": 0,
            "reason": "content 不能为空",
            "problem_context_list": [],
        }

    service = get_keyword_filter_service()

    # 检测 prompt 是否有效（非空且无未填充占位符）
    prompt_is_valid = bool(
        req.prompt and req.prompt.strip() and not _has_unfilled_placeholder(req.prompt)
    )

    # 优先使用 prompt 中的自定义关键词列表
    if prompt_is_valid:
        logger.info("[BrandRule] 使用 prompt 中的自定义关键词列表")
        logger.info(f"[BrandRule] 📋 传入的品牌规则词列表: {req.prompt}")
        result = service.filter_with_custom_keywords(
            content, keywords_str=req.prompt, tenant_code=req.tenant_code
        )
    else:
        # 兜底逻辑：从 keyword-corpus 服务获取 label=品牌合规 的语料
        reason = (
            "为空" if not req.prompt or not req.prompt.strip() else "包含未填充占位符"
        )
        logger.warning(
            f"[BrandRule] prompt {reason}，尝试从 keyword-corpus 获取品牌合规语料"
        )
        keywords_str = await _fetch_nodes_by_label("品牌合规", req.tenant_code)
        if keywords_str:
            logger.info(
                f"[BrandRule] 📋 从 keyword-corpus 获取到语料: {keywords_str[:200]}..."
            )
            result = service.filter_with_custom_keywords(
                content, keywords_str=keywords_str, tenant_code=req.tenant_code
            )
        else:
            # 如果 keyword-corpus 也获取不到，使用 ban_term 表的全局词表
            logger.warning(
                "[BrandRule] keyword-corpus 无语料，使用 ban_term 表的全局词表（不推荐）"
            )
            result = service.filter(content, tenant_code=req.tenant_code)

    # 详细记录检测结果
    problem_snippets = result.get("problem_snippets", [])
    if problem_snippets:
        logger.warning(
            f"[BrandRule] ❌ 检测到不合规内容! "
            f"score={result['score']}, "
            f"违禁词={problem_snippets}, "
            f"reason={result.get('reason', '')}"
        )
    else:
        logger.info(
            f"[BrandRule] ✅ 内容合规: score={result['score']}, "
            f"snippets={problem_snippets}"
        )

    # 统一返回格式（与 run_critic_http 一致）
    return {
        "success": True,
        "message": "CriticBrandRule 完成",
        "score": result["score"],
        "reason": result["reason"],
        "problem_tags": result.get("problem_tags", []),
        "problem_snippets": result.get("problem_snippets", []),
    }


@router.post("/critic.CriticService/CriticPlatformRule")
async def http_critic_platform_rule(req: CriticReq) -> dict:
    """
    平台规则精确匹配过滤

    核心特点：
    - 基于精确字符串匹配，无 AI 幻觉
    - 速度快、成本低、准确率高
    - 适用于平台违禁词/平台规范词检查
    - 从 prompt 中读取逗号分隔的关键词列表

    Prompt 格式：
    "检查以下平台规则词：极限词A,虚假宣传B,违规用语C"

    兜底逻辑：
    - 如果 prompt 为空，自动从 keyword-corpus 服务的 nodes 表中获取 label=平台合规 下所有节点的语料

    返回格式与 run_critic_http 统一：
    - success: bool
    - message: str
    - score: 1 (合规) / 0 (违规)
    - reason: str
    - problem_tags: List[str]
    - problem_snippets: List[str]
    """
    logger.info(
        f"[PlatformRule] 开始审核: job_id={req.job_id}, tenant_code={req.tenant_code}, "
        f"content_id={req.content_id}, content_len={len(req.content)}, prompt_len={len(req.prompt or '')}"
    )

    # 参数校验
    content = (req.content or "").strip()
    if not content:
        return {
            "success": False,
            "message": "content 不能为空",
            "score": 0,
            "reason": "content 不能为空",
            "problem_context_list": [],
        }

    service = get_keyword_filter_service()

    # 检测 prompt 是否有效（非空且无未填充占位符）
    prompt_is_valid = bool(
        req.prompt and req.prompt.strip() and not _has_unfilled_placeholder(req.prompt)
    )

    # 优先使用 prompt 中的自定义关键词列表
    if prompt_is_valid:
        logger.info("[PlatformRule] 使用 prompt 中的自定义关键词列表")
        logger.info(f"[PlatformRule] 📋 传入的平台规则词列表: {req.prompt}")
        result = service.filter_with_custom_keywords(
            content, keywords_str=req.prompt, tenant_code=req.tenant_code
        )
    else:
        # 兜底逻辑：从 keyword-corpus 服务获取 label=平台合规 的语料
        reason = (
            "为空" if not req.prompt or not req.prompt.strip() else "包含未填充占位符"
        )
        logger.warning(
            f"[PlatformRule] prompt {reason}，尝试从 keyword-corpus 获取平台合规语料"
        )
        keywords_str = await _fetch_nodes_by_label("平台合规", req.tenant_code)
        if keywords_str:
            logger.info(
                f"[PlatformRule] 📋 从 keyword-corpus 获取到语料: {keywords_str[:200]}..."
            )
            result = service.filter_with_custom_keywords(
                content, keywords_str=keywords_str, tenant_code=req.tenant_code
            )
        else:
            # 如果 keyword-corpus 也获取不到，使用 ban_term 表的全局词表
            logger.warning(
                "[PlatformRule] keyword-corpus 无语料，使用 ban_term 表的全局词表（不推荐）"
            )
            result = service.filter(content, tenant_code=req.tenant_code)

    # 详细记录检测结果
    problem_snippets = result.get("problem_snippets", [])
    if problem_snippets:
        logger.warning(
            f"[PlatformRule] ❌ 检测到不合规内容! "
            f"score={result['score']}, "
            f"违禁词={problem_snippets}, "
            f"reason={result.get('reason', '')}"
        )
    else:
        logger.info(
            f"[PlatformRule] ✅ 内容合规: score={result['score']}, "
            f"snippets={problem_snippets}"
        )

    # 统一返回格式（与 run_critic_http 一致）
    return {
        "success": True,
        "message": "CriticPlatformRule 完成",
        "score": result["score"],
        "reason": result["reason"],
        "problem_tags": result.get("problem_tags", []),
        "problem_snippets": result.get("problem_snippets", []),
    }


@router.post("/rlhf.RLHFExpertService/SummarizeTags")
async def http_summarize_tags(req: RLHFTagSummarizeReq):
    """AI 总结问题标签接口"""
    try:
        tags = await RLHFExpertService.summarize_tags(
            annotations=req.annotations, comment=req.comment, model_code=req.model_code
        )
        return {"success": True, "tags": tags}
    except Exception as e:
        logger.error(f"SummarizeTags failed: {e}")
        return {"success": False, "message": str(e), "tags": []}


@router.post("/rlhf.RLHFExpertService/SummarizeComment")
async def http_summarize_comment(req: RLHFCommentSummarizeReq):
    """AI 总结意见接口 - 根据原文和划词评论/精修内容生成修改意见

    支持三种模式：
    1. 划词评论模式：基于 annotations 生成意见
    2. 精修内容模式：对比 original_content 和 refined_content 生成意见
    3. 综合模式：两者都有时，结合生成综合意见
    """
    try:
        # 优先使用 original_content，兼容旧参数 content
        original_content = req.original_content or req.content

        comment = await RLHFExpertService.summarize_comment(
            original_content=original_content,
            annotations=req.annotations or [],
            refined_content=req.refined_content,
            model_code=req.model_code,
        )
        return {"success": True, "comment": comment}
    except Exception as e:
        logger.error(f"SummarizeComment failed: {e}")
        return {"success": False, "message": str(e), "comment": ""}


@router.post("/critic.CriticService/CriticAIExtraContentCheck")
async def http_critic_ai_extra_content_check(req: CriticReq):
    """
    AI额外内容检测

    特点：
    - 检测AI生成的额外内容
    - 支持自定义 prompt 和 model_config
    """
    payload = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "content": req.content,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "expert_service": req.expert_service,
        "expert_func": req.expert_func,
        "prompt": req.prompt,
        "model_code": req.model_code,
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
    }
    payload["expert_func"] = "CriticAIExtraContentCheck"
    return await run_critic_http(
        request_data=payload,
        stage="ag_ai_extra_content",
        service_method="CriticAIExtraContentCheck",
    )


@router.post("/critic.CriticService/AiContentDetector")
async def http_ai_content_detector(req: CriticReq):
    """
    使用 Ollama 的 qwen2:7b 模型进行 AI 内容检测评分

    特点：
    - 使用本地 Ollama 服务，无需 API key
    - 模型：qwen2:7b
    - 支持自定义 prompt 和 model_config
    """
    payload = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "content": req.content,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "expert_service": req.expert_service,
        "expert_func": req.expert_func,
        "prompt": req.prompt,
        "model_code": "qwen2:7b",  # 固定使用 qwen2:7b
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
    }
    payload["expert_func"] = "AiContentDetector"
    return await run_ai_content_detector_http(
        request_data=payload,
        stage="ag_ai_content_detector",
        service_method="AiContentDetector",
    )


# ==================== 文档解析接口 ====================


@router.post("/document_parser.DocumentParseService/ParseDocument")
async def http_parse_document(req: DocumentParseReq) -> dict:
    """
    文档解析接口 - 从文档中提取结构化语料数据

    流程：
    1. 从文档提取文本内容（PDF/Word/PPT/Excel）
    2. 根据 template_fields 构建 prompt
    3. 调用 LLM 进行结构化提取
    4. 返回解析结果
    """
    logger.info(
        f"[DocumentParser] 开始解析: job_id={req.job_id}, "
        f"file_type={req.file_type}, category_type={req.category_type}, "
        f"template_fields_count={len(req.template_fields)}"
    )

    result = await DocumentParseService.parse_document(req)

    logger.info(
        f"[DocumentParser] 解析完成: success={result['success']}, "
        f"items_count={len(result.get('items', []))}"
    )

    return result


@router.post("/admin/cache/corpus/clear")
async def clear_corpus_cache():
    """清空语料缓存（用于语料更新后强制刷新）"""
    _corpus_cache.clear()
    logger.info("[Admin] 语料缓存已清空")
    return {"success": True, "message": "语料缓存已清空"}


@router.post("/admin/cache/corpus/warmup")
async def warmup_corpus_cache(tenant_code: str = "default"):
    """预热语料缓存（主动加载常用 label 的语料）"""
    labels = ["平台合规", "品牌合规"]
    results = {}

    for label in labels:
        # 强制绕过缓存，从 DB 加载
        keywords_str = await _fetch_nodes_by_label(
            label, tenant_code, bypass_cache=True
        )
        results[label] = {
            "count": len(keywords_str.split(",")) if keywords_str else 0,
            "preview": keywords_str[:100] if keywords_str else "",
        }

    logger.info(f"[Admin] 语料预热完成: {results}")
    return {"success": True, "data": results}


# ==================== 句子匹配检测接口（无 AI，纯代码） ====================


@router.post("/critic.CriticService/CriticSentenceCheck")
async def http_critic_sentence_check(req: CriticReq) -> dict:
    """
    句子匹配检测

    核心特点：
    - 基于精确字符串匹配，无 AI 幻觉
    - 速度快、成本低、准确率高
    - 从 prompt 中读取逗号分隔的短句列表
    - 检测 content 中是否包含任意一个短句

    Prompt 格式：
    "检查以下短句：短句1,短句2,短句3"

    返回格式与 run_critic_http 统一：
    - success: bool
    - message: str
    - score: 1 (包含任意短句) / 0 (不包含任何短句)
    - reason: str
    - problem_context_list: 空
    """
    logger.info(
        f"[SentenceCheck] 开始检测: job_id={req.job_id}, tenant_code={req.tenant_code}, "
        f"content_id={req.content_id}, content_len={len(req.content)}, prompt_len={len(req.prompt or '')}"
    )

    # 参数校验
    content = (req.content or "").strip()
    if not content:
        return {
            "success": False,
            "message": "content 不能为空",
            "score": 0,
            "reason": "content 不能为空",
            "problem_context_list": [],
        }

    # 解析 prompt 中的短句列表（逗号分隔）
    prompt = (req.prompt or "").strip()
    if not prompt:
        return {
            "success": False,
            "message": "prompt 不能为空",
            "score": 0,
            "reason": "prompt 不能为空，需要提供逗号分隔的短句列表",
            "problem_context_list": [],
        }

    # 按逗号分割短句
    sentences = [s.strip() for s in prompt.split(",") if s.strip()]
    if not sentences:
        return {
            "success": False,
            "message": "未检测到有效短句",
            "score": 0,
            "reason": f"prompt 中未检测到有效短句（按逗号分隔）: {prompt}",
            "problem_context_list": [],
        }

    logger.info(f"[SentenceCheck] 📋 解析到 {len(sentences)} 个短句: {sentences}")

    # 检测 content 中是否包含任意一个短句
    matched_sentences = []
    for sentence in sentences:
        if sentence in content:
            matched_sentences.append(sentence)
            logger.info(f"[SentenceCheck] ✅ 匹配到短句: {sentence}")

    # 根据匹配结果返回
    if matched_sentences:
        logger.warning(
            f"[SentenceCheck] ❌ 检测到包含短句! matched={matched_sentences}"
        )
        return {
            "success": True,
            "message": "CriticSentenceCheck 完成",
            "score": 1,  # 包含至少一个短句
            "reason": f"内容中检测到以下短句: {', '.join(matched_sentences)}",
            "problem_context_list": [],
        }
    else:
        logger.info(f"[SentenceCheck] ✅ 内容中不包含任何短句: sentences={sentences}")
        return {
            "success": True,
            "message": "CriticSentenceCheck 完成",
            "score": 0,  # 不包含任何短句
            "reason": f"内容中不包含任何指定短句: {', '.join(sentences)}",
            "problem_context_list": [],
        }
