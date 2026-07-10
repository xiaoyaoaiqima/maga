"""Bootstrap helpers for the MAGA content-agent execution boundary."""
from __future__ import annotations

from datetime import datetime, timezone

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
from app.models.maga_assets import AssetRegistry
from app.services.business_forbidden_term_service import (
    A2_SENTIMENT_COMMENT_ASSET_KEY,
    A2_SENTIMENT_COMMENT_SEED_TERMS,
    BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
    BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION,
)


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


async def seed_a2_sentiment_comment_forbidden_terms(conn: AsyncConnection) -> None:
    """Seed the A2 comment-scoped business forbidden terms asset."""
    existing = (
        await conn.execute(
            select(AssetRegistry.content_json)
            .where(
                AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                AssetRegistry.asset_key == A2_SENTIMENT_COMMENT_ASSET_KEY,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    existing_entries = _business_forbidden_seed_entries(existing or {})
    existing_by_term = {entry.get("term"): entry for entry in existing_entries}
    seed_terms_by_term = {entry["term"]: entry for entry in A2_SENTIMENT_COMMENT_SEED_TERMS}
    if all(
        (existing_by_term.get(term) or {}).get("reason") == seed_entry["reason"]
        and (existing_by_term.get(term) or {}).get("enabled") is not False
        for term, seed_entry in seed_terms_by_term.items()
    ):
        return

    now = datetime.now(timezone.utc).isoformat()
    next_entries = [
        (
            {
                **entry,
                **seed_terms_by_term[entry["term"]],
                "created_at": entry.get("created_at") or now,
                "updated_at": now,
                "updated_by": "system",
            }
            if entry.get("term") in seed_terms_by_term
            else entry
        )
        for entry in existing_entries
    ]
    existing_terms = {entry.get("term") for entry in next_entries}
    added_seed_entries = [
        {
            **seed_entry,
            "created_at": now,
        }
        for seed_entry in A2_SENTIMENT_COMMENT_SEED_TERMS
        if seed_entry["term"] not in existing_terms
    ]
    if added_seed_entries:
        next_entries = [
            *next_entries,
            *added_seed_entries,
        ]
    updated_term_count = sum(
        1
        for term, seed_entry in seed_terms_by_term.items()
        if term in existing_by_term
        and (
            existing_by_term[term].get("reason") != seed_entry["reason"]
            or existing_by_term[term].get("enabled") is False
        )
    )
    added_term_count = len(added_seed_entries)
    if existing is not None:
        await conn.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                AssetRegistry.asset_key == A2_SENTIMENT_COMMENT_ASSET_KEY,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
    current_version = await conn.scalar(
        select(func.max(AssetRegistry.version_no)).where(
            AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
            AssetRegistry.asset_key == A2_SENTIMENT_COMMENT_ASSET_KEY,
        )
    )
    await conn.execute(
        insert(AssetRegistry).values(
            asset_type=BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
            asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
            display_name="A2舆情改善评论业务违禁词",
            version_no=int(current_version or 0) + 1,
            status="active",
            asset_stage="production",
            source_name="bootstrap_seed",
            content_json={
                "schema_version": BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION,
                "asset_type": BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                "terms": next_entries,
            },
            metadata_json={
                "schema_version": BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION,
                "term_count": len([entry for entry in next_entries if entry.get("enabled") is not False]),
                "added_term_count": added_term_count,
                "updated_term_count": updated_term_count,
            },
            created_by="system",
        )
    )


def _business_forbidden_seed_entries(content_json: dict | None) -> list[dict]:
    raw_terms = (content_json or {}).get("terms")
    if not isinstance(raw_terms, list):
        raw_terms = (content_json or {}).get("items")
    entries: list[dict] = []
    for item in raw_terms or []:
        if isinstance(item, str):
            entries.append({"term": item, "enabled": True})
        elif isinstance(item, dict):
            entries.append(item)
    return entries
