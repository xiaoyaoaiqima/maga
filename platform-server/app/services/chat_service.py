"""Realtime chat service."""
import json
import re
from typing import Optional

from sqlalchemy import and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.llm_model_route import LLMModelRoute
from app.models.llm_provider_config import LLMProviderConfig
from app.schemas.chat import ChatAction, ChatMessageRequest, ChatMessageResponse
from app.services.business_rule_chat_knowledge import (
    build_business_rule_context_block,
    build_business_rule_system_prompt,
    is_business_rule_context,
)
from app.services.llm_factory import LLMFactory
from app.utils.model_config import DEFAULT_MODEL, normalize_default_model


DEFAULT_CHAT_SYSTEM_PROMPT = (
    "你是 MAGA 控制台的实时助手。请基于用户问题给出简洁、可执行的中文回答；"
    "涉及业务数据或系统状态时，不要编造不存在的事实。"
)


class ChatService:
    """Handle current-session realtime chat requests."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def send_message(
        self,
        request: ChatMessageRequest,
        tenant_id: Optional[int] = None,
    ) -> ChatMessageResponse:
        agent = await self._get_realtime_chat_agent(tenant_id=tenant_id)
        if not agent:
            raise ValueError("未配置实时聊天 Agent")

        config = await self._build_llm_config(agent)
        system_prompt = build_business_rule_system_prompt(
            self._get_system_prompt(agent),
            request.context,
            request.message,
        )
        user_prompt = self._build_user_prompt(request)

        reply = await LLMFactory.call_llm(
            config=config,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context={
                "trace_id": "maga_realtime_chat",
                "expert_config_code": agent.agent_code,
            },
        )

        reply_text, actions = self._parse_model_response(str(reply or "").strip(), request)
        return ChatMessageResponse(
            agent_code=agent.agent_code,
            agent_name=agent.agent_name,
            reply=reply_text,
            actions=actions,
        )

    async def _get_realtime_chat_agent(self, tenant_id: Optional[int]) -> Optional[Agent]:
        conditions = [
            Agent.agent_type == "REALTIME_CHAT",
            Agent.enabled == 1,
            Agent.is_deleted == 0,
        ]
        if tenant_id is not None:
            conditions.append(or_(Agent.tenant_id == tenant_id, Agent.tenant_id.is_(None)))

        stmt = select(Agent).where(and_(*conditions))
        if tenant_id is not None:
            # REALTIME_CHAT 是首版 Chat 的唯一业务入口；同租户 Agent 优先，全局 Agent 作为兜底。
            stmt = stmt.order_by(
                case(
                    (Agent.tenant_id == tenant_id, 0),
                    (Agent.tenant_id.is_(None), 1),
                    else_=2,
                ),
                Agent.create_time.desc(),
            )
        else:
            stmt = stmt.order_by(Agent.create_time.desc())

        result = await self.db.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def _build_llm_config(self, agent: Agent) -> dict:
        default_config = dict(agent.default_config or {})
        model = agent.default_model_code or default_config.get("model") or DEFAULT_MODEL
        config = {
            **default_config,
            "model": normalize_default_model(model),
            "temperature": default_config.get("temperature", 0.7),
            "max_tokens": default_config.get("max_tokens", 1500),
        }
        route = await self._get_model_route(config["model"])
        if route is None:
            return config

        provider = await self._get_provider(route.provider_code)
        if provider is None:
            return config

        # Chat 不把 URL/API Key 存到 Agent；每次发送时从模型路由和 Provider 表拿瞬时连接配置。
        config["provider"] = provider.provider_code
        config["provider_code"] = provider.provider_code
        config["base_url"] = provider.base_url
        config["api_key"] = provider.api_key
        config["model"] = normalize_default_model(route.provider_model or route.model_code)
        config["route_model_code"] = route.model_code
        if provider.default_params:
            for key in ("temperature", "max_tokens", "top_p"):
                if key not in default_config and provider.default_params.get(key) is not None:
                    config[key] = provider.default_params[key]
        if route.timeout_seconds and "timeout" not in config:
            config["timeout"] = route.timeout_seconds
        return config

    async def _get_model_route(self, model_code: str) -> Optional[LLMModelRoute]:
        result = await self.db.execute(
            select(LLMModelRoute)
            .where(
                LLMModelRoute.model_code == model_code,
                LLMModelRoute.enabled == 1,
                LLMModelRoute.is_deleted == 0,
            )
            .order_by(LLMModelRoute.priority.desc(), LLMModelRoute.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_provider(self, provider_code: str) -> Optional[LLMProviderConfig]:
        result = await self.db.execute(
            select(LLMProviderConfig)
            .where(
                LLMProviderConfig.provider_code == provider_code,
                LLMProviderConfig.enabled == 1,
                LLMProviderConfig.is_deleted == 0,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _get_system_prompt(self, agent: Agent) -> str:
        default_config = agent.default_config or {}
        prompt = str(default_config.get("system_prompt") or "").strip()
        return prompt or DEFAULT_CHAT_SYSTEM_PROMPT

    def _build_user_prompt(self, request: ChatMessageRequest) -> str:
        lines: list[str] = []
        context_block = build_business_rule_context_block(request.context)
        if context_block:
            lines.append(context_block)

        if request.history:
            lines.append("以下是当前前端会话内的聊天上下文，刷新页面后不会保留：")
            for item in request.history[-12:]:
                role_label = "用户" if item.role == "user" else "助手"
                lines.append(f"{role_label}: {item.content}")
        lines.append(f"用户: {request.message}")
        # 首版不持久化聊天历史，只把前端内存中的最近上下文带给模型。
        return "\n".join(lines)

    def _parse_model_response(
        self,
        raw_reply: str,
        request: ChatMessageRequest,
    ) -> tuple[str, list[ChatAction]]:
        if not raw_reply:
            return "模型没有返回内容。", []

        parsed = _json_loads(raw_reply)
        if isinstance(parsed, dict):
            reply = str(parsed.get("reply") or parsed.get("message") or raw_reply).strip()
            return reply, self._sanitize_actions(parsed.get("actions"), request)

        actions: list[ChatAction] = []
        reply = raw_reply
        for match in _JSON_BLOCK_RE.finditer(raw_reply):
            block_payload = _json_loads(match.group("json"))
            if not isinstance(block_payload, dict) or "actions" not in block_payload:
                continue
            actions.extend(self._sanitize_actions(block_payload.get("actions"), request))
            reply = reply.replace(match.group(0), "").strip()

        return reply or "已生成草稿建议。", actions

    def _sanitize_actions(self, actions: object, request: ChatMessageRequest) -> list[ChatAction]:
        if not is_business_rule_context(request.context) or not isinstance(actions, list):
            return []

        safe_actions: list[ChatAction] = []
        seen_action_types: set[str] = set()
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_type = str(action.get("type") or "")
            if action_type in seen_action_types:
                continue
            payload = action.get("payload")
            if not isinstance(payload, dict):
                continue
            if action_type == "fill_business_rule_draft":
                draft_corpus = str(payload.get("draft_corpus") or payload.get("content") or "").strip()
                if not draft_corpus:
                    continue
                # 重要逻辑：Chat 只能填入页面草稿，不能绕过现有保存、试跑、发布按钮。
                safe_actions.append(
                    ChatAction(
                        type="fill_business_rule_draft",
                        label=str(action.get("label") or "填入规则语料"),
                        payload={
                            "draft_corpus": draft_corpus,
                            "rule_id": request.context.rule_id,
                            "source_row_no": request.context.source_row_no,
                        },
                    )
                )
                seen_action_types.add(action_type)
                continue
            if action_type == "fill_business_rule_examples":
                examples = _action_examples(payload)
                if not examples:
                    continue
                safe_actions.append(
                    ChatAction(
                        type="fill_business_rule_examples",
                        label=str(action.get("label") or "填入示例"),
                        payload={
                            "examples": examples,
                            "rule_id": request.context.rule_id,
                            "source_row_no": request.context.source_row_no,
                        },
                    )
                )
                seen_action_types.add(action_type)
        return safe_actions[:2]


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(?P<json>.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _json_loads(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _action_examples(payload: dict) -> list[str]:
    raw_examples = payload.get("examples")
    if isinstance(raw_examples, list):
        return [str(item or "").strip() for item in raw_examples if str(item or "").strip()][:50]
    text = str(payload.get("examples_text") or payload.get("content") or "").strip()
    if not text:
        return []
    examples: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"^[\s\-*•\d.、．]+", "", raw_line).strip()
        if line:
            examples.append(line)
    return examples[:50]
