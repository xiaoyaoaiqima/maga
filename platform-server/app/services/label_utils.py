"""
标签工具函数：处理新旧标签格式的转换和兼容
"""
from __future__ import annotations

from typing import Any


def get_labels(properties: dict | None) -> dict[str, list[str]]:
    """
    从 properties 中获取 labels，支持新旧格式兼容

    旧格式：
    {"brands": ["A"], "products": ["B"], "tags": ["C"]}

    新格式：
    {"labels": {"brand": ["A"], "product": ["B"], "tag": ["C"]}}

    Args:
        properties: 节点的 properties 字段

    Returns:
        标签字典，格式为 {"label_type": ["value1", "value2"]}
    """
    if not properties:
        return {}

    # 新格式：直接返回 labels
    if "labels" in properties:
        return properties["labels"] or {}

    # 旧格式：转换 brands/products/tags 为 labels
    labels: dict[str, list[str]] = {}

    if brands := properties.get("brands"):
        labels["brand"] = brands if isinstance(brands, list) else [brands]

    if products := properties.get("products"):
        labels["product"] = products if isinstance(products, list) else [products]

    if tags := properties.get("tags"):
        labels["tag"] = tags if isinstance(tags, list) else [tags]

    return labels


def set_labels(
    properties: dict | None,
    labels: dict[str, list[str] | str],
) -> dict:
    """
    设置 properties 中的 labels（新格式）

    Args:
        properties: 原始 properties
        labels: 要设置的标签字典

    Returns:
        更新后的 properties
    """
    if properties is None:
        properties = {}

    # 确保所有值都是数组
    normalized_labels: dict[str, list[str]] = {}
    for key, value in labels.items():
        if isinstance(value, list):
            normalized_labels[key] = value
        else:
            normalized_labels[key] = [value]

    properties["labels"] = normalized_labels

    # 清除旧格式的字段（迁移后可移除）
    properties.pop("brands", None)
    properties.pop("products", None)
    properties.pop("tags", None)

    return properties


def get_label_values(
    properties: dict | None,
    label_type: str,
) -> list[str]:
    """
    获取指定类型的标签值

    Args:
        properties: 节点的 properties 字段
        label_type: 标签类型，如 "brand", "product", "tag"

    Returns:
        标签值列表
    """
    labels = get_labels(properties)
    return labels.get(label_type, [])


def has_label(
    properties: dict | None,
    label_type: str,
    value: str,
) -> bool:
    """
    检查节点是否包含指定的标签

    Args:
        properties: 节点的 properties 字段
        label_type: 标签类型
        value: 标签值

    Returns:
        是否包含该标签
    """
    labels = get_label_values(properties, label_type)
    return value in labels


def match_filters(
    properties: dict | None,
    filters: dict[str, str | list[str]],
) -> bool:
    """
    检查节点是否匹配所有筛选条件

    Args:
        properties: 节点的 properties 字段
        filters: 筛选条件，格式为 {"label_type": "value"} 或 {"label_type": ["value1", "value2"]}

    Returns:
        是否匹配所有条件
    """
    labels = get_labels(properties)

    for label_type, filter_value in filters.items():
        node_values = labels.get(label_type, [])

        # 如果节点没有任何该类型的标签，跳过检查（视为全局）
        if not node_values:
            continue

        # 检查是否匹配
        if isinstance(filter_value, list):
            # 多值匹配：任一匹配即可
            if not any(v in node_values for v in filter_value):
                return False
        else:
            # 单值匹配
            if filter_value not in node_values:
                return False

    return True


def is_global_node(properties: dict | None) -> bool:
    """
    判断是否为全局节点（没有绑定任何品牌/产品的节点）

    Args:
        properties: 节点的 properties 字段

    Returns:
        是否为全局节点
    """
    labels = get_labels(properties)
    # 检查是否有任何绑定标签
    brand_values = labels.get("brand", [])
    product_values = labels.get("product", [])
    return not (brand_values or product_values)


def convert_old_to_new(properties: dict | None) -> dict:
    """
    将旧格式的 properties 转换为新格式

    Args:
        properties: 旧格式的 properties

    Returns:
        新格式的 properties
    """
    if not properties:
        return {"labels": {}}

    labels = get_labels(properties)
    result = properties.copy()

    # 添加新格式
    result["labels"] = labels

    # 移除旧格式（可选，迁移期保留）
    # result.pop("brands", None)
    # result.pop("products", None)
    # result.pop("tags", None)

    return result
