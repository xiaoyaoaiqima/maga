"""Bootstrap helpers for the MAGA content-agent execution boundary."""
from __future__ import annotations

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.content_agent_defaults import (
    DEFAULT_EXECUTOR_CODE,
    LEGACY_XHS_WRITER_DISPLAY_NAME,
    LEGACY_XHS_WRITER_EXECUTOR_CODE,
    MAGA_WORKER_DISPLAY_NAME,
    MAGA_WORKER_INVOKE_URL,
    MAGA_WORKER_PROFILE_NAME,
    MAGA_WORKER_SUPPORTED_CAPABILITY_SPECS,
    XHS_CAPABILITY_SPECS,
)
from app.models.content_agent import ExecutorRegistry


async def seed_default_content_agent_executors(
    conn: AsyncConnection,
    *,
    maga_worker_invoke_url: str = MAGA_WORKER_INVOKE_URL,
    xhs_writer_invoke_url: str | None = None,
    executor_token: str | None = "test-token",
    overwrite: bool = True,
) -> None:
    """Create or update the default MAGA executor registry rows.

    `overwrite=False` is used during app startup so existing production executor
    routing is not silently changed by a process restart. Explicit init/seed
    commands use `overwrite=True` to let operators point MAGA at a real worker.
    """
    legacy_invoke_url = xhs_writer_invoke_url or maga_worker_invoke_url
    config_json = {"executor_token": executor_token} if executor_token else None
    rows = [
        {
            "executor_code": DEFAULT_EXECUTOR_CODE,
            "display_name": MAGA_WORKER_DISPLAY_NAME,
            "executor_type": "hermes_profile",
            "profile_name": MAGA_WORKER_PROFILE_NAME,
            "protocol_version": "0.1",
            "invoke_url": maga_worker_invoke_url,
            "supported_capabilities_json": MAGA_WORKER_SUPPORTED_CAPABILITY_SPECS,
            "config_json": config_json,
            "enabled": 1,
        },
        {
            "executor_code": LEGACY_XHS_WRITER_EXECUTOR_CODE,
            "display_name": LEGACY_XHS_WRITER_DISPLAY_NAME,
            "executor_type": "hermes_profile",
            "profile_name": MAGA_WORKER_PROFILE_NAME,
            "protocol_version": "0.1",
            "invoke_url": legacy_invoke_url,
            "supported_capabilities_json": XHS_CAPABILITY_SPECS,
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
