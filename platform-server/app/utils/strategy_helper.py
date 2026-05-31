"""Compatibility stubs for the removed keyword strategy system."""
from __future__ import annotations

from typing import Any


REMOVED_STRATEGY_MESSAGE = "旧关键词策略系统已下线，请使用业务规则包和系统提示词关键词链路。"


async def fetch_strategy_combinations(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    raise RuntimeError(REMOVED_STRATEGY_MESSAGE)


async def fetch_merged_strategy_combinations(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise RuntimeError(REMOVED_STRATEGY_MESSAGE)


async def fetch_strategy_detail(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise RuntimeError(REMOVED_STRATEGY_MESSAGE)


async def fetch_strategy_node_pool_details(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise RuntimeError(REMOVED_STRATEGY_MESSAGE)


def build_expert_param_config_from_combo(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise RuntimeError(REMOVED_STRATEGY_MESSAGE)


def extract_strategy_combo_summary(combo: dict[str, Any]) -> dict[str, Any]:
    return {}
