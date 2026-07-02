import time
import logging
import os
from typing import Dict, Any

from app.schemas.content_generation import TaskGenerateRequest, TaskGenerateResponse

logger = logging.getLogger(__name__)

class ContentGenerationService:
    """
    Content Generation Service (HTTP implementation)
    """

    def __init__(self):
        logger.info("ContentGenerationService initialized")

    def _clean_markdown_formatting(self, text: str) -> str:
        """
        清理 Markdown 格式字符（如 *、_）
        保留正常文本内容
        """
        import re
        # 移除所有 * 字符
        cleaned = re.sub(r'\*+', '', text)
        return cleaned.strip()

    def _calculate_title_length(self, title: str) -> int:
        """
        计算标题的加权长度
        
        规则：
        - 中文字符：1 个字符
        - emoji：2 个字符
        - 其他符号/字母/数字：1 个字符
        
        返回加权长度
        """
        import regex  # 使用 regex 库支持 Unicode 属性
        
        length = 0
        # 使用 regex 库的 grapheme 迭代器来正确处理 emoji（包括组合 emoji）
        for char in regex.findall(r'\X', title):
            # 检查是否是 emoji（包括组合 emoji 如 👨‍👩‍👧‍👦）
            if regex.match(r'\p{Emoji}', char) and not regex.match(r'[0-9#*]', char):
                length += 2
            else:
                # 中文字符、符号、字母、数字都算 1
                length += 1
        
        return length

    def _parse_task_output(self, content: str) -> tuple:
        """
        解析任务生成的输出
        
        支持多种格式（按优先级）:
        1. JSON 格式: {"标题": "xxx", "正文": "xxx"} 或 {"title": "xxx", "content": "xxx"}
        2. 纯文本格式: 标题：xxx\n\n正文：xxx
        3. 兜底：第一行作为标题，其余作为正文
        """
        import re
        import json
        
        title = ""
        body = ""
        # logger.info(f"🔍 解析任务输出: {content}")

        # 1. 优先尝试 JSON 解析
        try:
            # 尝试提取 JSON 块（支持被 markdown 代码块包裹）
            json_patterns = [
                r'```json\s*(\{[\s\S]*?\})\s*```',  # ```json {...} ```
                r'```\s*(\{[\s\S]*?\})\s*```',       # ``` {...} ```
                r'(\{[^{}]*"[^"]*"[^{}]*:[^{}]*\})', # 简单 JSON 对象
                r'(\{[\s\S]*?"(?:标题|title)"[\s\S]*?"(?:正文|content|body)"[\s\S]*?\})', # 复杂 JSON
            ]
            
            for pattern in json_patterns:
                json_match = re.search(pattern, content, re.IGNORECASE)
                if json_match:
                    json_str = json_match.group(1)
                    parsed = json.loads(json_str)
                    
                    # 提取标题
                    title = str(
                        parsed.get("标题") or 
                        parsed.get("title") or 
                        parsed.get("Title") or 
                        ""
                    ).strip()
                    
                    # 提取正文
                    body = str(
                        parsed.get("正文") or 
                        parsed.get("content") or 
                        parsed.get("Content") or 
                        parsed.get("body") or 
                        parsed.get("Body") or 
                        ""
                    ).strip()
                    
                    if title or body:
                        logger.info(f"✅ JSON 解析成功: 标题={len(title)}字符, 正文={len(body)}字符")
                        return title, body
                        
        except (json.JSONDecodeError, AttributeError) as e:
            logger.debug(f"JSON 解析失败，尝试正则匹配: {e}")
        
        # 2. 正则匹配纯文本格式
        # 尝试提取标题（支持 Markdown 加粗格式）
        title_patterns = [
            r'[*_]*标题[*_]*[：:]\s*([^\n]+)',
            r'[*_]*Title[*_]*[：:]\s*([^\n]+)',
            r'[*_]*title[*_]*[：:]\s*([^\n]+)',
        ]
        
        for pattern in title_patterns:
            title_match = re.search(pattern, content, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip().strip('*_"\'')
                break
        
        # 尝试提取正文（支持 Markdown 加粗格式）
        content_patterns = [
            r'[*_]*正文[*_]*[：:]\s*(.+)',
            r'[*_]*Content[*_]*[：:]\s*(.+)',
            r'[*_]*content[*_]*[：:]\s*(.+)',
            r'[*_]*Body[*_]*[：:]\s*(.+)',
            r'[*_]*body[*_]*[：:]\s*(.+)',
        ]
        
        for pattern in content_patterns:
            body_match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if body_match:
                body = body_match.group(1).strip().strip('*_')
                break
        
        # 3. 如果正则匹配到标题但没匹配到正文，尝试按段落分割
        if title and not body:
            # 移除已匹配的标题部分，剩余内容作为正文
            remaining = re.sub(r'[*_]*(?:标题|Title|title)[*_]*[：:][^\n]*\n*', '', content, flags=re.IGNORECASE)
            remaining = remaining.strip()
            if remaining:
                body = remaining
                logger.info(f"标题已匹配，使用剩余内容作为正文: {len(body)}字符")
        
        # 4. 如果都没有匹配到，尝试按段落分割
        if not title and not body:
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            if len(paragraphs) >= 2:
                title = paragraphs[0].strip('*_#').strip()
                body = '\n\n'.join(paragraphs[1:])
                logger.info("使用段落分割方式解析")
            else:
                # 最终兜底：全部作为正文
                body = content.strip()
                logger.warning("使用兜底方案：全部作为正文")
        
        # 清理 Markdown 格式字符
        title = self._clean_markdown_formatting(title)
        body = self._clean_markdown_formatting(body)
        
        return title, body

    async def GenerateByTask(self, request_dict: Dict[str, Any], context=None) -> TaskGenerateResponse:
        """
        基于编排器任务的内容生成
        """
        start_time = time.time()
        llm_start_time = 0
        llm_end_time = 0
        
        # Parse request using Pydantic
        try:
            request = TaskGenerateRequest(**request_dict)
        except Exception as e:
             logger.error(f"Invalid request format: {e}")
             return TaskGenerateResponse(
                 success=False,
                 message=f"Invalid request format: {e}",
                 job_id=request_dict.get("job_id", ""),
                 sub_job_id=request_dict.get("sub_job_id", ""),
                 content_id=request_dict.get("content_id", ""),
                 expert_task_id=request_dict.get("expert_task_id", 0),
                 error=str(e)
             )

        # Log request
        logger.info(
            f"📥 收到任务生成请求: job_id={request.job_id}, "
            f"expert_task_id={request.expert_task_id}, "
            f"model={request.model_code}"
        )
        
        try:
            # Get model config
            temperature = request.model_cfg.temperature
            max_tokens = request.model_cfg.max_tokens
            
            # Select provider
            from app.core.config import settings as app_settings
            model_code = request.model_code or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
            
            # 自动路由策略：
            # 1. 如果请求指定了 model_code，则 provider 设为 None，交由 SDK 根据路由表自动选择（推荐）
            # 2. 如果使用默认配置，则尝试使用默认 provider
            provider = None
            if not request.model_code:
                provider = getattr(app_settings, "LLM_PROVIDER", None)
            
            logger.info(f"🤖 使用模型: provider={provider or 'auto-routing'}, model={model_code}, temp={temperature}")
            
            # Build prompt
            prompt = request.prompt
            if not prompt:
                return TaskGenerateResponse(
                    success=False,
                    message="提示词不能为空",
                    job_id=request.job_id,
                    sub_job_id=request.sub_job_id,
                    content_id=request.content_id,
                    expert_task_id=request.expert_task_id,
                    error="prompt is required",
                )
            
            if request.content:
                prompt = f"{prompt}\n\n原始内容：\n{request.content}"
            
            prompt += """\n\n请严格按照以下格式输出：\n\n标题：[标题内容]\n\n正文：[正文内容]"""
            
            # Invoke LLM
            from langchain_core.messages import HumanMessage
            from raap_llm_sdk.langchain_llm import LangChainLLM
            from raap_llm_sdk import LLMCallContext
            from app.utils.llm_factory import get_llm_client
            from raap_trace_sdk import get_current_context, get_current_span_id
            
            # 获取当前 Trace Context 或使用请求中的信息
            current_trace_ctx = get_current_context()
            trace_id = current_trace_ctx.trace_id if current_trace_ctx else ""
            span_id = get_current_span_id()  # 获取当前 Span ID
            
            llm_context = LLMCallContext(
                job_id=request.job_id,
                sub_job_id=request.sub_job_id,
                content_id=request.content_id,
                trace_id=trace_id,
                expert_config_code=request.expert_config_code,
            )
            
            llm = LangChainLLM(
                client=get_llm_client(),  # 使用统一配置的 client (已禁用内部 trace)
                model_code=model_code,
                provider_code=provider,
                default_params={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            llm_start_time = time.time()
            ai_msg = await llm.ainvoke(
                [HumanMessage(content=prompt)],
                context=llm_context
            )
            llm_end_time = time.time()
            llm_time = llm_end_time - llm_start_time
            
            usage_meta = (ai_msg.response_metadata or {}).get("usage") or {}
            input_tokens = usage_meta.get("input_tokens", 0) or 0
            output_tokens = usage_meta.get("output_tokens", 0) or 0
            total_tokens = usage_meta.get("total_tokens", 0) or 0
            
            # 获取 cost 信息
            cost_meta = (ai_msg.response_metadata or {}).get("cost") or {}
            input_cost = cost_meta.get("input_cost", 0.0) or 0.0
            output_cost = cost_meta.get("output_cost", 0.0) or 0.0
            total_cost = cost_meta.get("total_cost", 0.0) or 0.0
            
            # 获取实际使用的 provider (从 SDK 返回的 metadata 中提取)
            actual_provider = (ai_msg.response_metadata or {}).get("provider_code") or provider
            
            # Parse output
            generated_content = ai_msg.content
            title, content = self._parse_task_output(generated_content)
            
            execution_time = time.time() - start_time
            
            # 检查标题长度是否超过限制
            if title:
                title_length = self._calculate_title_length(title)
                if title_length > 20:
                    logger.warning(
                        f"⚠️ 标题长度超限: job_id={request.job_id}, "
                        f"title='{title[:50]}...', 加权长度={title_length} > 20，舍弃该结果"
                    )
                    return TaskGenerateResponse(
                        success=False,
                        message=f"标题长度超限（{title_length} > 20），已舍弃",
                        job_id=request.job_id,
                        sub_job_id=request.sub_job_id,
                        content_id=request.content_id,
                        expert_task_id=request.expert_task_id,
                        error=f"标题长度超限: {title_length} > 20",
                        execution_time=execution_time,
                        llm_time=llm_time,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        total_tokens=total_tokens,
                        input_cost=input_cost,
                        output_cost=output_cost,
                        total_cost=total_cost,
                        model_used=model_code,
                        provider=actual_provider,
                    )
            
            if title or content:
                logger.info(
                    f"✅ 任务生成成功: job_id={request.job_id}, "
                    f"title={title[:30] if title else '无'}..., "
                    f"耗时={execution_time:.1f}s (LLM={llm_time:.1f}s)"
                )
                return TaskGenerateResponse(
                    success=True,
                    message="生成成功",
                    job_id=request.job_id,
                    sub_job_id=request.sub_job_id,
                    content_id=request.content_id,
                    expert_task_id=request.expert_task_id,
                    title=title or "",
                    generated_content=content or "",
                    execution_time=execution_time,
                    llm_time=llm_time,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    input_cost=input_cost,
                    output_cost=output_cost,
                    total_cost=total_cost,
                    model_used=model_code,
                    provider=actual_provider,
                )
            else:
                logger.error(f"❌ 任务生成失败: 无法解析输出")
                return TaskGenerateResponse(
                    success=False,
                    message="无法解析输出内容",
                    job_id=request.job_id,
                    sub_job_id=request.sub_job_id,
                    content_id=request.content_id,
                    expert_task_id=request.expert_task_id,
                    error="无法解析输出内容",
                    execution_time=execution_time,
                    llm_time=llm_time,
                    model_used=model_code,
                    provider=actual_provider if 'actual_provider' in locals() else provider,
                )
                
        except Exception as e:
            execution_time = time.time() - start_time
            llm_time = (llm_end_time - llm_start_time) if llm_end_time > 0 else 0
            logger.error(f"❌ 任务生成异常: {e}", exc_info=True)
            
            return TaskGenerateResponse(
                success=False,
                message=f"生成失败: {str(e)}",
                job_id=request.job_id,
                sub_job_id=request.sub_job_id,
                content_id=request.content_id,
                expert_task_id=request.expert_task_id,
                error=str(e),
                execution_time=execution_time,
                llm_time=llm_time,
                provider=(provider if 'provider' in locals() and provider else ""),
            )
