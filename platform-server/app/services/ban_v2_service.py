"""
Ban V2 Service - 带后验证的违禁词检测服务

与 CriticService 的区别：
1. 解析新的输出格式：{score, reason, problem_context_list}
2. 对 problem_context_list 中的词进行后验证（带归一化匹配）
3. 如果都是幻觉，自动纠正为通过

注意：prompt 由 orchestrator 拼接后传入，这里不写死 prompt
"""
import json
import re
import time
import traceback
import unicodedata
from typing import Any, Dict, List, Tuple

from loguru import logger

from app.services.llm_factory import LLMFactory
from app.utils.model_config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    build_llm_config,
    normalize_model_config,
)


def _build_success_response(message: str, result: dict) -> dict:
    """构建成功响应"""
    resp = {
        "success": True,
        "message": message,
        "score": result.get("score", 0),
        "passed": result.get("passed", False),
        "reason": result.get("reason", ""),
        "problem_context_list": result.get("problem_context_list", []),
    }
    # 透传后验证信息
    if "post_validation" in result:
        resp["post_validation"] = result["post_validation"]
    # 透传模型信息
    if "usage" in result:
        resp["usage"] = result["usage"]
    if "model_code" in result:
        resp["model_code"] = result["model_code"]
    if "provider_code" in result:
        resp["provider_code"] = result["provider_code"]
    return resp


def _build_failure_response(message: str, reason: str) -> dict:
    """构建失败响应"""
    return {
        "success": False,
        "message": message,
        "score": 0,
        "passed": False,
        "reason": reason,
        "problem_context_list": [],
    }


def _normalize_text(text: str) -> str:
    """
    归一化文本，消除干扰因素
    
    处理：
    1. Unicode 归一化（全角 → 半角）
    2. 去除所有空白字符（空格、换行、制表符）
    3. 转小写（主要针对英文）
    """
    if not text:
        return ""
    
    # NFKC 归一化：全角转半角，兼容字符统一
    text = unicodedata.normalize('NFKC', text)
    
    # 去除所有空白字符
    text = re.sub(r'\s+', '', text)
    
    # 转小写
    text = text.lower()
    
    return text


def _word_exists_in_content(word: str, content: str) -> Tuple[bool, str]:
    """
    检查词是否存在于内容中（支持多种匹配策略）
    
    匹配策略优先级：
    1. 精确匹配（最可靠）
    2. 归一化匹配（处理空格/全角等干扰）
    
    Returns:
        (是否存在, 匹配方式)
    """
    word = str(word).strip()
    if not word:
        return False, "empty"
    
    # 策略1：精确匹配
    if word in content:
        return True, "exact"
    
    # 策略2：归一化匹配（去除空格、换行、全角等干扰）
    norm_word = _normalize_text(word)
    norm_content = _normalize_text(content)
    
    if norm_word and norm_word in norm_content:
        logger.info(f"[BanV2] 归一化匹配成功: 「{word}」→ 归一化后存在于文本中")
        return True, "normalized"
    
    return False, "not_found"


def _post_validate(content: str, problem_context_list: List[str]) -> Dict[str, Any]:
    """
    后验证：检查 LLM 报告的违禁词是否真实存在于原文中
    
    这是核心的幻觉检测逻辑！
    
    使用多级匹配策略：
    1. 精确匹配 - 原文中有完全一致的词
    2. 归一化匹配 - 消除空格/换行/全角等干扰后匹配
    
    Args:
        content: 原始文本内容
        problem_context_list: LLM 声称检测到的违禁词列表
        
    Returns:
        验证结果字典
    """
    if not problem_context_list:
        return {
            "validated": False,
            "has_hallucination": False,
            "hallucinated_words": [],
            "valid_words": [],
        }
    
    valid_words = []
    hallucinated_words = []
    match_details = []  # 记录匹配详情，方便调试
    
    for word in problem_context_list:
        word = str(word).strip()
        if not word:
            continue
        
        # 核心验证：多策略匹配
        exists, match_type = _word_exists_in_content(word, content)
        
        if exists:
            valid_words.append(word)
            match_details.append({"word": word, "match_type": match_type})
        else:
            # ⚠️ 幻觉！LLM 声称有这个词，但实际不存在
            logger.warning(f"[BanV2] 🔴 LLM 幻觉检测！声称包含词「{word}」但文本中不存在（已尝试归一化匹配）")
            hallucinated_words.append(word)
            match_details.append({"word": word, "match_type": "hallucination"})
    
    has_hallucination = len(hallucinated_words) > 0
    all_hallucinations = has_hallucination and len(valid_words) == 0
    
    return {
        "validated": True,
        "has_hallucination": has_hallucination,
        "all_hallucinations": all_hallucinations,
        "hallucinated_words": hallucinated_words,
        "valid_words": valid_words,
        "validated_count": len(valid_words),
        "hallucination_count": len(hallucinated_words),
        "total_claimed": len(problem_context_list),
        "match_details": match_details,  # 新增：匹配详情
    }


def _parse_ban_v2_response(response: str) -> Tuple[int, str, List[str]]:
    """
    解析 Ban V2 响应格式
    
    期望格式：
    {
        "score": 0 或 1,
        "reason": "违规类别" 或 null,
        "problem_context_list": ["违禁词1", "违禁词2"] 或 []
    }
    
    Returns:
        (score, reason, problem_context_list)
    """
    # 清理 markdown 代码块
    clean_response = re.sub(r'^```(?:json)?\s*', '', response.strip())
    clean_response = re.sub(r'```\s*$', '', clean_response)
    
    # 尝试解析 JSON
    json_match = re.search(r'\{[^{}]*\}', clean_response, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group())
            score = result.get("score", 0)
            reason = result.get("reason") or ""
            problem_list = result.get("problem_context_list", [])
            
            # 确保 problem_context_list 是列表
            if not isinstance(problem_list, list):
                problem_list = [problem_list] if problem_list else []
            
            # 清洗列表项
            problem_list = [str(item).strip() for item in problem_list if item]
            
            logger.info(f"[BanV2] 解析结果: score={score}, reason={reason}, problems={problem_list}")
            return score, reason, problem_list
        except json.JSONDecodeError as e:
            logger.warning(f"[BanV2] JSON 解析失败: {e}")
    
    # 回退：尝试正则提取
    score_match = re.search(r'"score"\s*:\s*(\d+)', response)
    if score_match:
        score = int(score_match.group(1))
        
        # 提取 reason
        reason_match = re.search(r'"reason"\s*:\s*"([^"]*)"', response)
        reason = reason_match.group(1) if reason_match else ""
        
        # 提取 problem_context_list
        problems_match = re.search(r'"problem_context_list"\s*:\s*\[(.*?)\]', response, re.DOTALL)
        problem_list = []
        if problems_match:
            items = re.findall(r'"([^"]+)"', problems_match.group(1))
            problem_list = [item.strip() for item in items if item.strip()]
        
        return score, reason, problem_list
    
    # 完全无法解析，返回默认值
    logger.warning(f"[BanV2] 无法解析响应，使用默认值。响应前200字: {response[:200]}")
    return 0, response[:200], []


async def run_ban_v2(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行 Ban V2 检测（带后验证）
    
    与 CriticService.run_critic 的区别：
    1. 解析新格式 {score, reason, problem_context_list}
    2. 对 problem_context_list 进行后验证
    3. 如果全是幻觉，自动纠正为通过
    
    Args:
        request_data: 请求数据（格式与 CriticReq 兼容）
            {
                "content": "待审核内容",
                "prompt": "由 orchestrator 拼接好的 prompt（包含 $content$ 占位符）",
                "model_code": "deepseek-v4-flash",
                "model_config": {"temperature": 0, "max_tokens": 2000}
            }
    
    Returns:
        统一的审核结果格式
    """
    start_time = time.time()
    
    content = (request_data.get("content") or "").strip()
    if not content:
        return _build_failure_response("content 不能为空", "content 不能为空")
    
    try:
        # 提取参数
        prompt = request_data.get("prompt", "")
        model_code = request_data.get("model_code", "")
        model_config = normalize_model_config(request_data.get("model_config", {}))
        
        if not prompt or not prompt.strip():
            return _build_failure_response("prompt 不能为空", "BanV2 需要 orchestrator 提供 prompt")
        
        # 替换 $content$ 占位符
        user_prompt = prompt.replace("$content$", content)
        
        # 构建 LLM 配置
        llm_config = build_llm_config(model_code, model_config)
        temperature = llm_config.get("temperature", DEFAULT_TEMPERATURE)
        max_tokens = llm_config.get("max_tokens", DEFAULT_MAX_TOKENS)
        model = llm_config.get("model", model_code)
        
        # 兜底 API 配置
        import os
        if not llm_config.get("api_key"):
            llm_config["api_key"] = (
                os.getenv("OPENAI_API_KEY")
                or os.getenv("AIHUBMIX_API_KEY")
                or LLMFactory.DEFAULT_FALLBACK_API_KEY
            )
        if not llm_config.get("base_url"):
            llm_config["base_url"] = LLMFactory.DEFAULT_FALLBACK_BASE_URL
            llm_config["endpoint"] = LLMFactory.DEFAULT_FALLBACK_BASE_URL
        
        if not llm_config.get("api_key"):
            return _build_failure_response("API Key 未配置", "无法调用模型")
        
        # 调用 LLM
        logger.info(f"[BanV2] 调用模型: {model}, temperature={temperature}, max_tokens={max_tokens}")
        response_data = await LLMFactory.call_llm(
            config=llm_config,
            system_prompt="",  # 不使用 system prompt
            user_prompt=user_prompt,
            return_full_response=True
        )
        
        # 提取响应
        if isinstance(response_data, dict):
            response = response_data.get("content", "")
            llm_usage = response_data.get("usage")
            model_code_used = response_data.get("model_code")
            provider_code_used = response_data.get("provider_code")
        else:
            response = response_data
            llm_usage = None
            model_code_used = model
            provider_code_used = llm_config.get("provider") or os.getenv("LLM_PROVIDER", "openai")
        
        logger.info(f"[BanV2] 模型响应 (len={len(response)}): {response[:500]}")
        
        # 解析响应
        score, reason, problem_context_list = _parse_ban_v2_response(response)
        
        # 后验证：检查 problem_context_list 中的词是否真的存在
        post_validation = _post_validate(content, problem_context_list)
        
        # 如果检测到违规（score=0）但全是幻觉，自动纠正
        if score == 0 and post_validation.get("all_hallucinations"):
            logger.warning(
                f"[BanV2] ⚠️ 自动纠正：所有违规均为幻觉，改判为通过。"
                f"幻觉词={post_validation['hallucinated_words']}"
            )
            score = 1
            reason = None
            problem_context_list = []
            post_validation["auto_corrected"] = True
            post_validation["warning"] = "LLM 检测到幻觉，已自动纠正为通过"
        elif post_validation.get("has_hallucination"):
            # 部分幻觉：只保留有效词
            logger.warning(
                f"[BanV2] ⚠️ 部分幻觉：有效词={post_validation['valid_words']}, "
                f"幻觉词={post_validation['hallucinated_words']}"
            )
            problem_context_list = post_validation["valid_words"]
        
        # 计算 passed
        passed = score == 1
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        result = {
            "score": score,
            "passed": passed,
            "reason": reason,
            "problem_context_list": problem_context_list,
            "post_validation": post_validation,
            "duration_ms": duration_ms,
        }
        
        # 注入模型信息
        if llm_usage:
            result["usage"] = llm_usage
        result["model_code"] = model_code_used
        result["provider_code"] = provider_code_used
        
        logger.info(
            f"[BanV2] 检测完成: passed={passed}, score={score}, "
            f"problems={problem_context_list}, has_hallucination={post_validation.get('has_hallucination')}, "
            f"duration_ms={duration_ms}"
        )
        
        return _build_success_response("CriticBanV2 完成", result)
        
    except Exception as e:
        logger.error(f"[BanV2] 检测失败: {str(e)}")
        logger.error(f"错误堆栈:\n{traceback.format_exc()}")
        return _build_failure_response(f"CriticBanV2 失败: {str(e)}", f"审核失败: {str(e)}")
