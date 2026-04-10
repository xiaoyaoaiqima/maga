"""
LangChain 适配层：将 raap_llm_sdk 暴露为 LangChain ChatModel。
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

from .client import LLMClient


def _normalize_messages(messages: List[BaseMessage]) -> List[Dict[str, str]]:
    """将 LangChain Message 转为 OpenAI 兼容 role/content。"""
    normalized: List[Dict[str, str]] = []
    for msg in messages:
        role = getattr(msg, "type", None) or getattr(msg, "role", None) or "user"
        content = getattr(msg, "content", "") or ""
        if role == "human":
            role = "user"
        elif role == "ai":
            role = "assistant"
        elif role == "system":
            role = "system"
        elif role == "tool":
            role = "tool"
        normalized.append({"role": role, "content": content})
    return normalized


class LangChainLLM(BaseChatModel):
    """基于 raap_llm_sdk 的 LangChain ChatModel 适配器。"""

    client: LLMClient = Field(default_factory=LLMClient)
    model_code: Optional[str] = None
    provider_code: Optional[str] = None
    default_params: Dict[str, Any] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "raap_llm_sdk"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "model_code": self.model_code,
            "provider_code": self.provider_code,
            **self.default_params,
        }

    # ================= sync 调用 =================
    def _call(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """同步调用不建议在已运行事件循环中使用。"""
        try:
            return asyncio.run(self._acall(messages, stop=stop, **kwargs)).content
        except RuntimeError:
            raise RuntimeError("当前事件循环已运行，请使用 .ainvoke/.astream 进行异步调用")

    async def _acall(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AIMessage:
        params = {**self.default_params, **kwargs}
        if stop is not None:
            params["stop"] = stop

        response = await self.client.invoke(
            messages=_normalize_messages(messages),
            model_code=params.pop("model_code", self.model_code),
            provider_code=params.pop("provider_code", self.provider_code),
            stream=False,
            **params,
        )

        return AIMessage(
            content=response.content,
            response_metadata={
                "model_code": response.model_code,
                "provider_code": response.provider_code,
                "provider_model": response.provider_model,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "cost": {
                    "input_cost": float(response.cost.input_cost),
                    "output_cost": float(response.cost.output_cost),
                    "total_cost": float(response.cost.total_cost),
                },
                "raw_response": response.raw_response,
            },
        )

    # ================= LangChain 生成接口 =================
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        ai_msg = await self._acall(messages, stop=stop, **kwargs)
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            ai_msg = self._call(messages, stop=stop, **kwargs)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=ai_msg))])
        except RuntimeError:
            # 当同步不可用时，提示使用异步
            raise

    # ================= 流式接口 =================
    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        params = {**self.default_params, **kwargs}
        if stop is not None:
            params["stop"] = stop

        response = await self.client.invoke(
            messages=_normalize_messages(messages),
            model_code=params.pop("model_code", self.model_code),
            provider_code=params.pop("provider_code", self.provider_code),
            stream=True,
            **params,
        )

        chunks = (response.raw_response or {}).get("chunks") or []
        for chunk in chunks:
            choice = (chunk.get("choices") or [{}])[0] or {}
            delta = choice.get("delta") or {}
            content_piece = delta.get("content") or ""
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=content_piece,
                    response_metadata={"raw_chunk": chunk},
                )
            )
