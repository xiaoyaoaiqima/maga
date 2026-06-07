from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field
from loguru import logger

from app.services.critic_dapr_service import (
    run_critic_http,
    run_critic_tencent_http,
    run_ai_content_detector_http,
)
from app.services.rlhf_expert_service import RLHFExpertService
from app.services.ban_v2_service import run_ban_v2
from app.services.document_parse_service import DocumentParseReq, DocumentParseService

router = APIRouter(tags=["dapr-http-invoke"])


class ModelCfg(BaseModel):
    temperature: float = 0.7
    max_tokens: int = 2000


class RLHFTagSummarizeReq(BaseModel):
    annotations: List[Dict[str, Any]]
    comment: Optional[str] = None
    model_code: str = "deepseek-v4-flash"


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
    model_code: str = "deepseek-v4-flash"


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
    model_code: str = "deepseek-v4-flash"
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
    使用配置的 deepseek-v4-flash 模型进行 AI 内容检测评分

    特点：
    - 使用本地 Ollama 服务，无需 API key
    - 模型：deepseek-v4-flash
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
        "model_code": "deepseek-v4-flash",
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
