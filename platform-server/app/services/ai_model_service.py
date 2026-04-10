"""
AI 模型调用服务
底层 LLM 调用实现
"""
import json
import aiohttp
import asyncio
from typing import Any, Dict, List, Optional

from app.utils.llm_parse import parse_function_calls
from loguru import logger


class AIModelService:
    """AI 模型调用服务类"""
    
    @staticmethod
    async def call_ai_model_with_prompt(
        system_prompt: str,
        user_prompt: str,
        ai_model: str,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: int = 1500,
        functions: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        使用自定义 prompt 调用 AI 模型
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            ai_model: AI 模型名称
            temperature: 温度参数，控制输出的随机性，默认 0.7
            api_key: API Key（可选，如果不提供则使用默认配置）
            base_url: API Base URL（可选，如果不提供则使用默认配置）
            max_tokens: 最大 token 数，默认 1500
            
        Returns:
            str: AI 模型返回的文本
        """
        try:
            if not api_key:
                raise ValueError("API Key 未配置，请在上游提供或设置环境变量")
            if not base_url:
                raise ValueError("Base URL 未配置，请在上游提供或设置环境变量")
            
            # gpt-5 系列不支持 max_tokens，需改用 max_completion_tokens
            use_max_completion = ai_model.startswith("gpt-5")

            payload = {
                "model": ai_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
            }

            if use_max_completion:
                payload["max_completion_tokens"] = max_tokens
                logger.debug(
                    "Using max_completion_tokens for model %s, value=%s",
                    ai_model,
                    max_tokens,
                )
            else:
                # 仅设置一个 max_tokens，避免与 max_completion_tokens 冲突
                payload["max_tokens"] = max_tokens
            
            # 如果提供了 functions，添加到 payload（OpenAI 新协议使用 tools）
            if functions:
                payload["tools"] = functions
                payload["tool_choice"] = "auto"  # 让模型决定是否调用 function
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            logger.debug(f"调用 AI 模型: {ai_model}, URL: {base_url}")
            
            # aiohttp.ClientSession 会自动使用当前事件循环
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    base_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=200)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if 'choices' in result and len(result['choices']) > 0:
                            choice = result['choices'][0]
                            message = choice.get('message', {})
                            finish_reason = choice.get('finish_reason', 'unknown')
                            
                            function_calls_json = parse_function_calls(message)
                            if function_calls_json is not None:
                                return function_calls_json
                            
                            content = message.get('content', '').strip()
                            
                            # 详细记录响应状态，便于调试
                            if not content:
                                logger.warning(
                                    f"[AIModelService] 模型返回空 content, "
                                    f"finish_reason: {finish_reason}, "
                                    f"message keys: {list(message.keys())}, "
                                    f"usage: {result.get('usage', 'N/A')}"
                                )
                            else:
                                logger.debug(f"AI 模型响应成功，长度: {len(content)} 字符, finish_reason: {finish_reason}")
                            
                            return content
                        else:
                            logger.error(f"AI 模型返回格式异常: {result}")
                            raise ValueError("AI 模型返回格式异常")
                    else:
                        error_text = await response.text()
                        logger.error(f"AI 模型调用失败: {response.status} - {error_text}")
                        raise RuntimeError(f"AI 模型调用失败: {response.status} - {error_text}")
                        
        except asyncio.TimeoutError as timeout_error:
            raise TimeoutError("AI 模型调用超时") from timeout_error
        except (ValueError, RuntimeError):
            # 重新抛出特定异常
            raise
        except Exception as e:
            logger.error(f"AI 模型调用异常: {str(e)}")
            raise RuntimeError(f"AI 模型调用失败: {str(e)}") from e

