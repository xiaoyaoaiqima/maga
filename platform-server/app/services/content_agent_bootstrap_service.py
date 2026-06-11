"""Bootstrap helpers for the MAGA content-agent execution boundary."""
from __future__ import annotations

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.content_agent_defaults import (
    DEFAULT_EXECUTOR_CODE,
    MAGA_WORKER_DISPLAY_NAME,
    MAGA_WORKER_INVOKE_URL,
    MAGA_WORKER_PROFILE_NAME,
    MAGA_WORKER_SUPPORTED_CAPABILITY_SPECS,
)
from app.models.content_agent import ExecutorRegistry
from app.models.agent import Agent


async def seed_default_content_agent_executors(
    conn: AsyncConnection,
    *,
    maga_worker_invoke_url: str = MAGA_WORKER_INVOKE_URL,
    executor_token: str | None = "test-token",
    overwrite: bool = True,
) -> None:
    """Create or update the default MAGA executor registry rows.

    `overwrite=False` is used during app startup so existing production executor
    routing is not silently changed by a process restart. Explicit init/seed
    commands use `overwrite=True` to let operators point MAGA at a real worker.
    """
    config_json = {"executor_token": executor_token} if executor_token else None
    rows = [
        {
            "executor_code": DEFAULT_EXECUTOR_CODE,
            "display_name": MAGA_WORKER_DISPLAY_NAME,
            "executor_type": "direct_llm",
            "profile_name": MAGA_WORKER_PROFILE_NAME,
            "protocol_version": "0.1",
            "invoke_url": maga_worker_invoke_url,
            "supported_capabilities_json": MAGA_WORKER_SUPPORTED_CAPABILITY_SPECS,
            "config_json": config_json,
            "enabled": 1,
        },
    ]

    for values in rows:
        executor_code = values["executor_code"]
        existing_id = await conn.scalar(
            select(ExecutorRegistry.id).where(ExecutorRegistry.executor_code == executor_code)
        )
        if existing_id is None:
            await conn.execute(insert(ExecutorRegistry).values(**values))
        elif overwrite:
            await conn.execute(
                update(ExecutorRegistry)
                .where(ExecutorRegistry.id == existing_id)
                .values(**values)
            )


DEFAULT_REALTIME_CHAT_AGENT_CODE = "maga_realtime_chat_agent"
DEFAULT_REALTIME_CHAT_AGENT_NAME = "MAGA 实时聊天 Agent"
DEFAULT_REALTIME_CHAT_MODEL_CODE = "deepseek-v4-flash"
DEFAULT_REALTIME_CHAT_SYSTEM_PROMPT = (
    "你是 MAGA 控制台的实时助手。请用简洁、可执行的中文回答用户问题。"
    "当问题涉及页面操作、业务规则、批次复盘或模型配置时，优先给出下一步动作；"
    "不知道真实数据时要明确说明，不要编造。"
)


async def seed_default_realtime_chat_agent(
    conn: AsyncConnection,
    *,
    overwrite: bool = False,
) -> None:
    """Create the default REALTIME_CHAT Agent used by the global Chat panel.

    这里只写 Agent 元数据和默认模型编码，不写 API Key / base_url；真实模型
    Provider 仍走统一 LLM Provider 配置或环境变量，避免把密钥混进 Agent 配置。
    """
    existing_id = await conn.scalar(
        select(Agent.id).where(Agent.agent_code == DEFAULT_REALTIME_CHAT_AGENT_CODE)
    )
    values = {
        "agent_code": DEFAULT_REALTIME_CHAT_AGENT_CODE,
        "agent_name": DEFAULT_REALTIME_CHAT_AGENT_NAME,
        "agent_type": "REALTIME_CHAT",
        "expert_config_code_list": [],
        "zero_score_invalid_expert_codes": [],
        "default_model_code": DEFAULT_REALTIME_CHAT_MODEL_CODE,
        "default_config": {
            "system_prompt": DEFAULT_REALTIME_CHAT_SYSTEM_PROMPT,
            "temperature": 0.7,
            "max_tokens": 1500,
        },
        "description": "MAGA 控制台右侧 Chat 面板默认实时助手",
        "tenant_id": None,
        "publish_status": "PUBLISHED",
        "enabled": 1,
        "is_deleted": 0,
        "created_by": "system",
        "updated_by": "system",
    }

    if existing_id is None:
        insert_values = dict(values)
        if conn.dialect.name == "sqlite":
            max_id = await conn.scalar(select(func.max(Agent.id)))
            insert_values["id"] = int(max_id or 0) + 1
        await conn.execute(insert(Agent).values(**insert_values))
    elif overwrite:
        await conn.execute(
            update(Agent)
            .where(Agent.id == existing_id)
            .values(**values)
        )
