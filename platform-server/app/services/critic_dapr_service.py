"""
Critic HTTP 调用封装

- 对外：由 FastAPI 路由接收请求（保持既定请求参数不变）
- 对内：统一走 CriticService.run_critic / CriticService.critic_tencent
"""

import time
import traceback
from datetime import datetime

from loguru import logger

from app.services.critic_service import CriticService
from app.utils.model_config import normalize_model_config


def _build_success_response(message: str, result: dict) -> dict:
    resp = {
        "success": True,
        "message": message,
        "score": result.get("score", 0),
        "reason": result.get("reason", ""),
        "problem_context_list": result.get("problem_context_list", []),
    }
    # 透传模型和 Token 信息
    if "usage" in result:
        resp["usage"] = result["usage"]
    if "model_code" in result:
        resp["model_code"] = result["model_code"]
    if "provider_code" in result:
        resp["provider_code"] = result["provider_code"]
    return resp


def _build_failure_response(message: str, reason: str) -> dict:
    return {
        "success": False,
        "message": message,
        "score": 0,
        "reason": reason,
        "problem_context_list": [],
    }


async def run_critic_http(*, request_data: dict, stage: str, service_method: str) -> dict:
    """统一的 HTTP Critic 执行入口。

    内部只做：
    - 校验 + 标准化 model_config
    - 调用 CriticService.run_critic
    - 上报 trace（失败不阻断主流程）
    - 返回统一响应结构
    """

    start_time = time.time()
    start_datetime = datetime.now()

    if not isinstance(request_data, dict):
        return _build_failure_response("仅支持 dict 请求", "request_data 必须为 dict")

    content = (request_data.get("content") or "").strip()
    if not content:
        return _build_failure_response("content 不能为空", "content 不能为空")

    try:
        request_data = dict(request_data)
        request_data["model_config"] = normalize_model_config(
            request_data.get("model_config", {}),
        )

        critic_service = CriticService()
        result = await critic_service.run_critic(request_data)

        # 检查模型调用是否成功（run_critic 在失败时会返回 success: False）
        if not result.get("success", True):
            return _build_failure_response(
                f"{service_method} 失败",
                result.get("reason", "模型调用失败"),
            )

        return _build_success_response(f"{service_method} 完成", result)
    except Exception as e:  # noqa: BLE001
        logger.error(f"{service_method} 失败: {str(e)}")
        logger.error(f"错误堆栈:\n{traceback.format_exc()}")

        return _build_failure_response(
            f"{service_method} 失败: {str(e)}",
            f"审核失败: {str(e)}",
        )


async def run_critic_tencent_http(*, request_data: dict, stage: str, service_method: str) -> dict:
    """Critic Tencent 风控 HTTP 入口。

    - 对外：保持既定请求参数不变（content/biztype 即可，其它字段忽略）
    - 对内：调用 CriticService.critic_tencent
    - 返回：统一 success/message + 结果字段
    """

    start_time = time.time()
    start_datetime = datetime.now()

    if not isinstance(request_data, dict):
        return _build_failure_response("仅支持 dict 请求", "request_data 必须为 dict")

    content = (request_data.get("content") or "").strip()
    if not content:
        return _build_failure_response("content 不能为空", "content 不能为空")

    try:
        critic_service = CriticService()
        result = await critic_service.critic_tencent(request_data)

        return {
            "success": True,
            "message": f"{service_method} 完成",
            "score": result.get("score", 0),
            "passed": result.get("passed", False),  # BAN 类型专家：是否通过审核
            "reason": result.get("reason", ""),
            "suggestion": result.get("suggestion"),
            "request_id": result.get("request_id", ""),
            "problem_context_list": [],
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"{service_method} 失败: {str(e)}")
        logger.error(f"错误堆栈:\n{traceback.format_exc()}")

        return _build_failure_response(
            f"{service_method} 失败: {str(e)}",
            f"审核失败: {str(e)}",
        )


async def run_ai_content_detector_http(*, request_data: dict, stage: str, service_method: str) -> dict:
    """AI 内容检测 HTTP 入口。
    
    使用 Ollama 的 qwen2:7b 模型进行 AI 内容检测评分
    
    - 对外：保持既定请求参数不变
    - 对内：调用 CriticService.run_ai_content_detector
    - 返回：统一 success/message + 结果字段
    """
    
    start_time = time.time()
    start_datetime = datetime.now()
    
    if not isinstance(request_data, dict):
        return _build_failure_response("仅支持 dict 请求", "request_data 必须为 dict")
    
    content = (request_data.get("content") or "").strip()
    if not content:
        return _build_failure_response("content 不能为空", "content 不能为空")
    
    try:
        request_data = dict(request_data)
        request_data["model_config"] = normalize_model_config(
            request_data.get("model_config", {}),
        )
        
        critic_service = CriticService()
        result = await critic_service.run_ai_content_detector(request_data)
        
        # 检查模型调用是否成功
        if not result.get("success", True):
            return _build_failure_response(
                f"{service_method} 失败",
                result.get("reason", "模型调用失败"),
            )
        
        return _build_success_response(f"{service_method} 完成", result)
    except Exception as e:  # noqa: BLE001
        logger.error(f"{service_method} 失败: {str(e)}")
        logger.error(f"错误堆栈:\n{traceback.format_exc()}")
        
        return _build_failure_response(
            f"{service_method} 失败: {str(e)}",
            f"审核失败: {str(e)}",
        )
