"""
Review Service - 审核服务
"""
import json
import os
import re
from typing import Any, Dict

from app.core.config import get_settings
from app.services.llm_factory import LLMFactory
from app.utils.model_config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    build_llm_config,
    normalize_model_config,
)
from app.utils.tencent_verify import verify_text_content
from loguru import logger


class CriticService:
    """审核服务"""

    @staticmethod
    def _format_user_friendly_error(error_type: str, error_text: str, model: str) -> str:
        """
        将技术错误转换为用户友好的错误信息

        Args:
            error_type: 异常类型名（如 "RemoteProtocolError"）
            error_text: 异常的详细信息
            model: 使用的模型名称

        Returns:
            用户友好的中文错误描述
        """
        # 网络连接类错误
        if error_type in ["RemoteProtocolError", "ConnectError", "ConnectTimeout"]:
            return f"模型服务（{model}）连接失败，请检查网络或稍后重试"

        # 超时类错误
        if error_type in ["TimeoutError", "ReadTimeout", "AsyncTimeoutError"]:
            return f"模型服务（{model}）响应超时，请稍后重试"

        # 认证/权限类错误
        if error_type in ["AuthenticationError", "PermissionDenied"]:
            return f"模型服务（{model}）认证失败，请检查 API 密钥配置"

        # 速率限制类错误
        if error_type in ["RateLimitError"]:
            return f"模型服务（{model}）调用频率超限，请稍后重试"

        # 服务端错误（5xx）
        if "50" in error_text or "Server" in error_type:
            return f"模型服务（{model}）暂时不可用，请稍后重试"

        # 其他错误，返回通用提示
        return f"模型服务（{model}）调用失败：{error_text}"

    @staticmethod
    def _log_response_excerpt(response: str, prefix: str = "[CriticService] 模型原始响应") -> None:
        """
        调试用：打印模型返回的前 500 字符，避免日志过长。
        """
        if response is None:
            logger.info(f"{prefix}: <empty>")
            return
        excerpt = response[:500]
        logger.info(f"{prefix} (len={len(response)}): {excerpt}")
    
    def _extract_reason_from_response(self, response: str) -> str:
        """
        从模型响应中提取 reason 字段，处理各种边界情况：
        - markdown 代码块包裹
        - 嵌入的引号（中英文）
        - 响应截断
        - 多行内容
        
        Args:
            response: 模型的原始响应文本
            
        Returns:
            提取到的 reason 字符串，如果提取失败则返回响应前200字符
        """
        if not response:
            return ""
        
        # 清理 markdown 代码块标记
        clean_response = re.sub(r'^```(?:json)?\s*', '', response.strip())
        clean_response = re.sub(r'```\s*$', '', clean_response)
        
        # 策略1: 匹配完整的 JSON reason 字段（带转义引号支持）
        reason_match = re.search(r'"reason"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[,}\]]', clean_response)
        if reason_match:
            reason = reason_match.group(1).strip()
            if reason:
                logger.info("[CriticService] reason 提取策略1成功")
                return reason
        
        # 策略2: 匹配到下一个 JSON 字段（如 problem_context_list）
        reason_match = re.search(r'"reason"\s*:\s*"(.*?)"\s*,\s*"(?:problem|suggestions|message)', clean_response, re.DOTALL)
        if reason_match:
            reason = reason_match.group(1).strip()
            if reason:
                logger.info("[CriticService] reason 提取策略2成功")
                return reason
        
        # 策略3: 匹配到 JSON 对象结束（处理 reason 是最后一个字段的情况）
        reason_match = re.search(r'"reason"\s*:\s*"(.*?)"\s*}', clean_response, re.DOTALL)
        if reason_match:
            reason = reason_match.group(1).strip()
            if reason:
                logger.info("[CriticService] reason 提取策略3成功")
                return reason
        
        # 策略4: 捕获 reason 到 problem_context_list 之间的内容（或到响应结束）
        # 使用贪婪匹配以获取尽可能多的内容（处理截断情况）
        reason_match = re.search(r'"reason"\s*:\s*"(.+?)(?:"\s*,\s*"problem_context_list"|"\s*[,}\]]|$)', clean_response, re.DOTALL)
        if reason_match:
            reason = reason_match.group(1).strip()
            # 清理可能的尾部 JSON 语法字符和引号
            reason = re.sub(r'["\s,}\]]+$', '', reason)
            if reason:
                logger.info(f"[CriticService] reason 提取策略4成功，长度: {len(reason)}")
                return reason
        
        # 策略5: 最宽松匹配 - 捕获 "reason": " 之后的所有内容直到响应结束（处理严重截断）
        reason_match = re.search(r'"reason"\s*:\s*"(.+)', clean_response, re.DOTALL)
        if reason_match:
            reason = reason_match.group(1).strip()
            # 清理可能的尾部 JSON 语法字符、引号、换行等
            reason = re.sub(r'["\s,}\]]+$', '', reason)
            # 如果 reason 以不完整的引号结尾，去掉它
            reason = reason.rstrip('"')
            if reason:
                logger.info(f"[CriticService] reason 提取策略5成功（截断响应），长度: {len(reason)}")
                return reason
                
        # 兜底: 返回响应前200字符
        fallback = response[:200] if len(response) > 200 else response
        logger.warning("[CriticService] reason 提取失败，使用响应前200字符作为兜底")
        return fallback
    
    def _get_default_prompt(self) -> str:
        """
        获取默认的评分 prompt
        
        Returns:
            默认 prompt 字符串，包含 $content$ 占位符
        """
        return """请评估以下内容的质量，并以 JSON 格式输出评分结果。

评分标准：
1. 内容质量（语言流畅度、叙事完整性、可读性）
2. 营销价值（痛点匹配度、卖点清晰度）
3. 品牌契合度（品牌语调一致性、合规语义）

输出格式：
{
  "score": 85,
  "reason": "评分理由或改进建议"
}

评分范围：0-100，分数越高表示质量越好。

下面是待审核的文本：$content$"""

    async def critic_tencent(
        self,
        request_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        使用腾讯风控对内容进行审核（BAN 类型专家）。
        
        Args:
            request_data: dict，包含 content 和可选 biztype:
                {
                    "content": "待审核文本",
                    "biztype": "article_review"  # 可选，默认环境变量
                }
        
        Returns:
            dict: BAN 类型标准输出格式
                - score: 0 或 1（0=不通过，1=通过）
                - passed: bool（是否通过审核）
                - reason: str（审核理由）
                - suggestion: str（腾讯审核建议：Pass/Review/Block）
                - request_id: str
        """
        content = request_data.get("content", "")
        biztype = request_data.get("biztype")
        
        if not content:
            logger.warning("[CriticService] 腾讯风控 content 为空")
            return {
                "score": 0,
                "passed": False,
                "reason": "content 不能为空",
                "suggestion": "None",
                "request_id": "",
            }
        
        result = verify_text_content(content, biztype=biztype)
        raw = result.get("raw") or {}
        detail_results = raw.get("DetailResults") or []
        request_id = result.get("request_id", "")
        
        severity_order = {"Block": 2, "Review": 1, "Pass": 0}
        top_suggestion = result.get("suggestion", "Pass")
        top_label = raw.get("Label")
        top_sub_label = raw.get("SubLabel")
        all_keywords = []  # 收集所有命中的关键词
        all_hit_details = []  # 收集所有命中的违禁详情
        
        for item in detail_results:
            sug = item.get("Suggestion", "Pass")
            label = item.get("Label")
            sub_label = item.get("SubLabel")
            keywords = item.get("Keywords") or []
            lib_results = item.get("LibResults") or []
            score_detail = item.get("Score")
            
            # 收集违禁详情（Block 或 Review 都收集）
            if sug in ("Block", "Review"):
                # 收集所有命中的关键词
                all_keywords.extend(keywords)
                
                hit_info = {
                    "suggestion": sug,
                    "label": label,
                    "sub_label": sub_label,
                    "keywords": keywords,
                    "score": score_detail,
                }
                # 提取自定义库命中信息（通常包含具体违禁词）
                if lib_results:
                    lib_keywords = []
                    for lib in lib_results:
                        lib_kw = lib.get("Keywords") or []
                        lib_keywords.extend(lib_kw)
                        all_keywords.extend(lib_kw)  # 也加入总关键词列表
                    hit_info["lib_keywords"] = lib_keywords
                all_hit_details.append(hit_info)
            
            # 更新最严重的标签（使用 >= 确保能获取到 label 和 sub_label）
            if severity_order.get(sug, 0) >= severity_order.get(top_suggestion, 0):
                top_suggestion = sug
                if label:
                    top_label = label
                if sub_label:
                    top_sub_label = sub_label
        
        # 去重关键词列表
        all_keywords = list(dict.fromkeys(all_keywords))
        
        # BAN 类型专家：只返回 0/1（通过/不通过）
        # Pass = 通过审核（score=1, passed=True）
        # Review/Block = 不通过审核（score=0, passed=False）
        passed = top_suggestion == "Pass"
        score = 1 if passed else 0
        
        parts = [f"Tencent suggestion: {top_suggestion}"]
        if top_label:
            parts.append(f"label: {top_label}")
        if top_sub_label:
            parts.append(f"sub_label: {top_sub_label}")
        if all_keywords:
            parts.append(f"keywords: {all_keywords}")
        if request_id:
            parts.append(f"request_id: {request_id}")
        reason = ", ".join(parts)
        
        # 日志输出：包含违禁详情
        if top_suggestion in ("Block", "Review"):
            logger.warning(
                "[CriticService] 腾讯风控检测到违规内容 | suggestion={} | label={} | sub_label={} | keywords={} | request_id={} | 违禁详情={}",
                top_suggestion, top_label, top_sub_label, all_keywords, request_id, all_hit_details
            )
        else:
            logger.info(f"[CriticService] 腾讯风控完成 suggestion={top_suggestion}, request_id={request_id}")
        return {
            "score": score,
            "passed": passed,
            "reason": reason,
            "suggestion": top_suggestion,
            "request_id": request_id,
        }

    async def CriticGrace(
        self,
        request_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        CriticGrace：兼容既定的 service_method 命名。

        - 对内统一走 run_critic
        - 不改变请求参数结构
        """
        return await self.run_critic(request_data=request_data)
    
    async def run_critic(
        self,
        request_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        使用自定义 prompt 和 content 直接调用模型进行评分
        支持 Orchestrator 服务调用格式
        
        Args:
            request_data: Orchestrator 服务请求数据，格式：
                {
                    "job_id": "job-xxx",
                    "sub_job_id": "sub-xxx",
                    "content_id": "content-xxx",
                    "content": "content",
                    "expert_task_id": 123,
                    "expert_config_code": "finance_daily_gen_v1",
                    "prompt": "prompt text",
                    "model_code": "deepseek-v4-flash",
                    "model_config": {
                        "temperature": 0.7,
                        "max_tokens": 2048
                    }
                }
                如果 prompt 为空，使用默认 prompt
                如果 model_code 为空，使用环境变量 DEEPSEEK_MODEL 或默认值 "deepseek-v4-flash"
                如果 model_config 为空，使用默认值 temperature=0.7, max_tokens=1500
            
        Returns:
            评分结果字典，格式: {"score": int, "reason": str,"problem_context_list": list}
        """
        def _format_error(e: Exception) -> str:
            # 兼容：某些异常（例如 CancelledError/Timeout）str(e) 为空，导致日志/返回不直观
            error_message = str(e).strip()
            if error_message:
                return error_message
            return repr(e)

        try:
            # 从 request_data 中提取参数
            prompt = request_data.get("prompt", "")
            content = request_data.get("content", "")
            model_code = request_data.get("model_code", "")
            model_config = normalize_model_config(request_data.get("model_config", {}))
            
            if not content:
                logger.warning("[CriticService] content 为空，跳过 LLM 调用")
                return {"success": False, "score": 0, "reason": "content 不能为空"}
            
            # 如果没有提供 prompt 或为空字符串，使用默认 prompt
            if not prompt or not prompt.strip():
                prompt = self._get_default_prompt()
            
            # 替换 prompt 中的 $content$ 占位符
            user_prompt = prompt.replace("$content$", content)
            
            llm_config = build_llm_config(model_code, model_config)
            temperature = llm_config.get("temperature", DEFAULT_TEMPERATURE)
            max_tokens = llm_config.get("max_tokens", DEFAULT_MAX_TOKENS)
            model = llm_config.get("model", model_code)
            
            # 兜底补齐 key/base_url，避免环境缺失导致阻断
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
                logger.error("[CriticService] 未配置 OPENAI_API_KEY，无法调用模型（兜底失败）")
                return {
                    "success": False,
                    "score": 0,
                    "reason": "OPENAI_API_KEY 未配置，无法调用模型"
                }
            
            # 调用 LLM（不使用 system prompt）
            logger.info(f"[CriticService] 使用自定义 prompt 调用模型: {model}, temperature: {temperature}, max_tokens: {max_tokens}")
            response_data = await LLMFactory.call_llm(
                config=llm_config,
                system_prompt="",  # 不使用 system prompt
                user_prompt=user_prompt,
                return_full_response=True
            )
            
            # 提取文本内容进行解析
            if isinstance(response_data, dict):
                response = response_data.get("content", "")
                llm_usage = response_data.get("usage")
                model_code_used = response_data.get("model_code")
                provider_code_used = response_data.get("provider_code")
            else:
                response = response_data
                llm_usage = None
                model_code_used = model
                # 从配置或环境变量获取 provider，避免返回 "unknown" 导致后续查询失败
                provider_code_used = llm_config.get("provider") or os.getenv("LLM_PROVIDER", "openai")

            # 调试：记录模型原始响应片段
            self._log_response_excerpt(response)
            
            # 解析响应，提取 score / reason / problem_context_list
            result = self._parse_review_response(response)
            
            # 注入模型和 Token 信息以便透传给 Orchestrator
            if llm_usage:
                result["usage"] = llm_usage
            result["model_code"] = model_code_used
            result["provider_code"] = provider_code_used
            
            logger.info(
                "[CriticService] 解析结果: score={}, reason={}, problem_context_list={}, model={}, provider={}",
                result.get("score"),
                result.get("reason"),
                result.get("problem_context_list"),
                model_code_used,
                provider_code_used
            )
            
            return result
            
        except Exception as e:
            # 生产环境 JSON 日志要把"错误类型 + 关键信息"打出来，否则 str(e) 为空时不可读
            import os
            timeout_s = float(os.getenv("LLM_HTTP_TIMEOUT", "30"))
            error_text = _format_error(e)
            logger.bind(
                error_type=type(e).__name__,
                error_message=error_text,
                model=model,
                model_code=model_code,
                base_url=llm_config.get("base_url") or llm_config.get("endpoint"),
                llm_http_timeout_s=timeout_s,
            ).opt(exception=True).error("使用自定义 prompt 评分失败")

            # 将技术错误转换为用户友好的错误信息
            error_type = type(e).__name__
            user_friendly_reason = self._format_user_friendly_error(error_type, error_text, model)

            return {
                "success": False,  # 模型调用失败
                "score": 0,
                "reason": user_friendly_reason,
                "problem_context_list": [],
            }
    
    def _parse_review_response(self, response: str) -> Dict[str, Any]:
        """
        解析模型响应，提取 score / reason / problem_context_list
        
        Args:
            response: 模型返回的原始文本
            
        Returns:
            解析后的结果字典: {"score": int, "reason": str, "problem_context_list": list}
        """
        def _clean_problem_context_list(raw_value: Any) -> list:
            """
            清洗 problem_context_list:
            - 确保返回 list[str]
            - 去掉中英文引号和首尾空白
            """
            if raw_value is None:
                return []
            items = raw_value if isinstance(raw_value, list) else [raw_value]
            cleaned = []
            for item in items:
                if item is None:
                    continue
                text = str(item).strip()
                # 去掉首尾可能的引号符号
                text = text.strip('\"\'“”‘’')
                if text:
                    cleaned.append(text)
            return cleaned

        try:
            # 尝试提取 JSON 格式的结果
            # 匹配 JSON 对象，可能包含 score 和 reason 字段
            json_pattern = r'\{[^{}]*"score"[^{}]*\}'
            json_match = re.search(json_pattern, response, re.DOTALL)
            
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    score = result.get("score", 0)
                    reason = result.get("reason") 
                    problem_context_list = _clean_problem_context_list(
                        result.get("problem_context_list")
                    )
                    
                    # 确保 score 是整数且在 0-100 范围内
                    score = max(0, min(100, int(score)))
                    
                    logger.info("[CriticService] ✅ 成功解析评分: {}, problems: {}", score, problem_context_list)
                    return {
                        "score": score,
                        "reason": reason,
                        "problem_context_list": problem_context_list,
                    }
                except json.JSONDecodeError:
                    logger.warning("[CriticService] ⚠️ JSON 解析失败，尝试其他方式")
            
            # 尝试直接提取 score 数字
            score_match = re.search(r'"score"\s*:\s*(\d+)', response)
            if score_match:
                score = max(0, min(100, int(score_match.group(1))))
                
                # 提取 reason - 使用多种策略处理各种情况
                reason = self._extract_reason_from_response(response)
                problem_context_list: list[Any] = []
                
                logger.info(
                    "[CriticService] ✅ 通过正则提取评分: {}, reason (len={}): {}, problem_context_list: {}",
                    score,
                    len(reason) if reason else 0,
                    reason,
                    problem_context_list,
                )
                return {
                    "score": score,
                    "reason": reason,
                    "problem_context_list": problem_context_list,
                }
            
            # 如果都失败了，尝试提取任何数字作为 score
            number_match = re.search(r'\b(\d{1,3})\b', response)
            if number_match:
                score = max(0, min(100, int(number_match.group(1))))
                logger.warning(
                    "[CriticService] ⚠️ 未找到明确的 score 字段，使用提取的数字: {}, problems: []",
                    score,
                )
                return {
                    "score": score,
                    "reason": response[:200] if len(response) > 200 else response,  # 使用响应前200字符作为 reason
                    "problem_context_list": [],
                }
            
            # 如果完全无法解析，返回默认值
            logger.warning("[CriticService] ⚠️ 无法解析响应，使用默认值, problems: []")
            return {
                "score": 60,
                "reason": response[:200] if len(response) > 200 else response,
                "problem_context_list": [],
            }
            
        except Exception as e:
            logger.error(f"[CriticService] 解析响应失败: {str(e)}, problems: []")
            return {
                "score": 60,
                "reason": f"解析失败: {str(e)}",
                "problem_context_list": [],
            }
    
    async def run_ai_content_detector(
        self,
        request_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        使用配置的 deepseek-v4-flash 模型进行 AI 内容检测评分
        
        Args:
            request_data: Orchestrator 服务请求数据，格式：
                {
                    "job_id": "job-xxx",
                    "sub_job_id": "sub-xxx",
                    "content_id": "content-xxx",
                    "content": "content",
                    "expert_task_id": 123,
                    "expert_config_code": "finance_daily_gen_v1",
                    "prompt": "prompt text",
                    "model_config": {
                        "temperature": 0.7,
                        "max_tokens": 2048
                    }
                }
                如果 prompt 为空，使用默认 prompt
                如果 model_config 为空，使用默认值 temperature=0.7, max_tokens=1500
            
        Returns:
            评分结果字典，格式: {"score": int, "reason": str, "problem_context_list": list}
        """
        def _format_error(e: Exception) -> str:
            error_message = str(e).strip()
            if error_message:
                return error_message
            return repr(e)

        try:
            # 从 request_data 中提取参数
            prompt = request_data.get("prompt", "")
            content = request_data.get("content", "")
            model_config = normalize_model_config(request_data.get("model_config", {}))
            
            if not content:
                logger.warning("[CriticService] content 为空，跳过 LLM 调用")
                return {"success": False, "score": 0, "reason": "content 不能为空"}
            
            # 如果没有提供 prompt 或为空字符串，使用默认 prompt
            if not prompt or not prompt.strip():
                prompt = self._get_default_prompt()
            
            # 替换 prompt 中的 $content$ 占位符
            user_prompt = prompt.replace("$content$", content)
            
            # Ollama 配置
            temperature = model_config.get("temperature", DEFAULT_TEMPERATURE)
            max_tokens = model_config.get("max_tokens", DEFAULT_MAX_TOKENS)
            model = request_data.get("model_code") or "deepseek-v4-flash"
            
            # Ollama 默认地址和配置（优先使用环境变量，其次使用配置文件）
            settings = get_settings()
            ollama_base_url = os.getenv("OLLAMA_BASE_URL") or settings.OLLAMA_BASE_URL
            
            # 在 K8s 环境中，如果使用 localhost 且未配置环境变量，尝试使用 host.docker.internal
            # 这适用于 Docker Desktop 的 K8s 环境，可以访问宿主机服务
            if settings.POD_NAME and "localhost" in ollama_base_url and not os.getenv("OLLAMA_BASE_URL"):
                # Docker Desktop 的 K8s 可以使用 host.docker.internal 访问宿主机
                ollama_base_url = ollama_base_url.replace("localhost", "host.docker.internal")
                logger.info(
                    f"[CriticService] 检测到 K8s 环境（POD_NAME={settings.POD_NAME}），"
                    f"自动使用 host.docker.internal 访问本地 Ollama: {ollama_base_url}"
                )
            
            # 记录使用的 Ollama 地址（首次调用时）
            if not hasattr(self, "_ollama_url_logged"):
                logger.info(f"[CriticService] AI 内容检测使用 Ollama 地址: {ollama_base_url}")
                self._ollama_url_logged = True
            
            # 直接调用 Ollama API（Ollama 不需要 API key）
            import httpx
            timeout_s = float(os.getenv("LLM_HTTP_TIMEOUT", "30"))
            
            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            # 调用 LLM（不使用 system prompt）
            logger.info(f"[CriticService] 使用 Ollama AI 内容检测模型: {model}, temperature: {temperature}, max_tokens: {max_tokens}")
            
            try:
                async with httpx.AsyncClient(timeout=timeout_s) as client:
                    resp = await client.post(ollama_base_url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
            except httpx.TimeoutException as e:
                raise TimeoutError(f"Ollama HTTP 调用超时 (timeout={timeout_s}s)") from e
            
            # 提取响应内容
            response = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            
            # 提取 usage 信息
            usage_data = data.get("usage", {})
            llm_usage = {
                "input_tokens": usage_data.get("prompt_tokens", 0),
                "output_tokens": usage_data.get("completion_tokens", 0),
                "total_tokens": usage_data.get("total_tokens", 0),
            }
            model_code_used = model
            provider_code_used = "ollama"

            # 调试：记录模型原始响应片段
            self._log_response_excerpt(response)
            
            # 解析响应，提取 score / reason / problem_context_list
            result = self._parse_review_response(response)
            
            # 注入模型和 Token 信息以便透传给 Orchestrator
            if llm_usage:
                result["usage"] = llm_usage
            result["model_code"] = model_code_used
            result["provider_code"] = provider_code_used
            
            logger.info(
                "[CriticService] AI 内容检测解析结果: score={}, reason={}, problem_context_list={}, model={}, provider={}",
                result.get("score"),
                result.get("reason"),
                result.get("problem_context_list"),
                model_code_used,
                provider_code_used
            )
            
            return result
            
        except Exception as e:
            timeout_s = float(os.getenv("LLM_HTTP_TIMEOUT", "30"))
            error_text = _format_error(e)
            
            # 获取 base_url
            settings = get_settings()
            base_url = os.getenv("OLLAMA_BASE_URL") or settings.OLLAMA_BASE_URL
            
            # 如果是连接错误，提供更详细的提示
            error_type = type(e).__name__
            if error_type in ["ConnectError", "ConnectTimeout"]:
                # 检查是否是 localhost（在 K8s 环境中通常无法连接）
                is_localhost = "localhost" in base_url or "127.0.0.1" in base_url
                if is_localhost:
                    error_text = (
                        f"{error_text}。当前配置使用 localhost 地址（{base_url}），"
                        f"在 Kubernetes 环境中无法连接到 Ollama 服务。"
                        f"请在 Helm values.yaml 中配置 OLLAMA_BASE_URL 环境变量，"
                        f"指向正确的 Ollama 服务地址，例如："
                        f"http://ollama-service:11434/v1/chat/completions"
                    )
                else:
                    error_text = (
                        f"{error_text}。请检查 Ollama 服务是否运行，"
                        f"以及 OLLAMA_BASE_URL 配置是否正确（当前: {base_url}）。"
                        f"确保 Ollama 服务在 Kubernetes 集群中可访问。"
                    )
            
            logger.bind(
                error_type=error_type,
                error_message=error_text,
                model=model,
                base_url=base_url,
                llm_http_timeout_s=timeout_s,
            ).opt(exception=True).error("使用 Ollama AI 内容检测失败")

            # 将技术错误转换为用户友好的错误信息
            user_friendly_reason = self._format_user_friendly_error(error_type, error_text, model)

            return {
                "success": False,  # 模型调用失败
                "score": 0,
                "reason": user_friendly_reason,
                "problem_context_list": [],
            }
