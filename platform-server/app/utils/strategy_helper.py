"""
策略服务调用封装 - 用于调用 keyword-corpus 服务获取策略组合
"""

from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.logger import get_logger
from app.utils.dapr_http import invoke_method

logger = get_logger()

# Dapr 调用 keyword-corpus 服务
KEYWORD_CORPUS_APP_ID = "raap-service-keyword-corpus"


def _extract_node_ids_from_pool(pool_value: Any) -> List[str]:
    """
    从 node_pools 的值中提取节点ID列表

    支持三种格式:
    - 字符串格式: "node_id1"  (string, 兼容旧数据)
    - 旧格式: ["node_id1", "node_id2"]  (list)
    - 新格式 v3: {"node_ids": ["node_id1", "node_id2"], "select_mode": "random"}  (dict)

    Returns:
        节点ID列表
    """
    if pool_value is None:
        return []

    # 字符串格式: 单个节点ID（兼容旧数据）
    if isinstance(pool_value, str):
        return [pool_value]

    # 新格式 v3: dict with node_ids
    if isinstance(pool_value, dict):
        node_ids = pool_value.get("node_ids", [])
        return [str(nid) for nid in node_ids] if node_ids else []

    # 旧格式: list of node IDs
    if isinstance(pool_value, list):
        return [str(nid) for nid in pool_value]

    return []


def _extract_node_id(node: Any) -> Optional[str]:
    """
    从 combo.nodes 中的节点值提取节点ID

    支持两种格式:
    - dict 格式: {"id": "xxx", "name": "yyy", "label": "zzz"}
    - string 格式: "node_id" (defined_combinations 的简化格式)

    Args:
        node: 节点值，可能是 dict 或 string

    Returns:
        节点ID字符串，如果无法提取则返回 None
    """
    if node is None:
        return None
    if isinstance(node, dict):
        return node.get("id")
    if isinstance(node, str):
        return node
    return None


async def fetch_strategy_combinations(
    strategy_id: int,
    count: Optional[int] = None,
    tenant_code: str = "default",
    overrides: Optional[Dict[str, List[str]]] = None,
    include_corpus: bool = True,
) -> List[Dict[str, Any]]:
    """
    通过 Dapr 调用 keyword-corpus 服务获取策略组合

    Args:
        strategy_id: ContentStrategy ID
        count: 需要生成的组合数量，None 表示获取全部
        tenant_code: 租户编码
        overrides: 覆盖配置 {dimension_type: [node_ids]}
        include_corpus: 是否包含语料内容

    Returns:
        组合列表，每个组合格式: {
            "id": "combo_xxx",
            "name": "组合名称",
            "nodes": {
                "persona": {"id": "...", "name": "...", "label": "...", "corpus": [...]},
                "scenario": {"id": "...", "name": "...", "label": "...", "corpus": [...]}
            }
        }
    """
    # 如果 count 为 None，使用 /combinations 端点获取全部
    if count is None:
        return await _fetch_all_combinations(strategy_id, tenant_code, include_corpus)

    # 否则使用 /generate 端点按需生成
    return await _fetch_generated_combinations(
        strategy_id, count, tenant_code, overrides
    )


async def _fetch_all_combinations(
    strategy_id: int,
    tenant_code: str = "default",
    include_corpus: bool = True,
) -> List[Dict[str, Any]]:
    """获取策略的所有组合（使用 /combinations 端点）"""

    method_name = f"api/v1/content-strategies/{strategy_id}/combinations"

    result = await invoke_method(
        app_id=KEYWORD_CORPUS_APP_ID,
        method_name=method_name,
        params={"include_corpus": include_corpus},
        method="GET",
    )

    combinations = result.get("combinations", [])
    logger.info(f"成功获取 {len(combinations)} 个策略组合 (strategy_id={strategy_id})")
    return combinations


async def _fetch_generated_combinations(
    strategy_id: int,
    count: int,
    tenant_code: str = "default",
    overrides: Optional[Dict[str, List[str]]] = None,
) -> List[Dict[str, Any]]:
    """生成指定数量的组合（使用 /generate 端点）"""

    method_name = f"api/v1/content-strategies/{strategy_id}/generate"

    payload = {
        "count": count,
        "overrides": overrides,
    }

    result = await invoke_method(
        app_id=KEYWORD_CORPUS_APP_ID,
        method_name=method_name,
        payload=payload,
        params={"tenant_code": tenant_code},
    )

    combinations = result.get("combinations", [])
    logger.info(f"成功生成 {len(combinations)} 个策略组合 (strategy_id={strategy_id})")
    return combinations


def build_expert_param_config_from_combo(
    combo: Dict[str, Any],
    variable_share_mapping: Dict[str, List[Dict[str, str]]],
    expert_config_code_list: List[str],
    expert_plugin_config_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    根据策略组合和变量共享映射，为每个 Expert 生成 plugin_config_snapshot

    Args:
        combo: 策略组合，格式: {
            "nodes": {
                "persona": {"id": "xxx", "name": "旺玥", "label": "人设"},
                "keyword": {"id": "yyy", "name": "DHA", "label": "卖点"}
            }
        }
        variable_share_mapping: 变量共享映射，格式: {
            "persona": [
                {"expert_code": "content_generator_v1", "variable": "人设"},
                {"expert_code": "critic_quality", "variable": "目标人设"}
            ],
            "keyword": [
                {"expert_code": "content_generator_v1", "variable": "必带词"},
                {"expert_code": "critic_ban", "variable": "安全词"}
            ]
        }
        expert_config_code_list: Expert 配置编码列表
        expert_plugin_config_map: Expert 插件配置映射（可选），格式: {
            "expert_config_code": [
                {"plugin_code": "xxx", "variable_mapping": {"变量名": []}},
                {"plugin_code": "yyy", "strategy_id": 123, "variable_mappings": [...]}
            ]
        }
            如果提供，将自动处理插件的 strategy_id 绑定模式

    Returns:
        expert_param_config: {
            "content_generator_v1": [
                {"plugin_code": "default", "variable_mapping": {"人设": "旺玥", "必带词": "DHA"}}
            ],
            "critic_ban": [
                {"plugin_code": "default", "variable_mapping": {"安全词": "DHA"}}
            ]
        }
        注意：variable_mapping 中直接存储 node.name，而不是 node:id
    """
    nodes = combo.get("nodes", {})
    expert_param_config: Dict[str, List[Dict[str, Any]]] = {}

    # 构建反向索引：expert_code -> [(dimension, variable), ...]
    # 用于后续的智能匹配
    expert_to_dimensions: Dict[str, List[Dict[str, str]]] = {}
    for dimension, mappings in variable_share_mapping.items():
        for mapping in mappings:
            expert_code = mapping.get("expert_code")
            if expert_code:
                if expert_code not in expert_to_dimensions:
                    expert_to_dimensions[expert_code] = []
                expert_to_dimensions[expert_code].append({
                    "dimension": dimension,
                    "variable": mapping.get("variable"),
                })

    for expert_code in expert_config_code_list:
        # 获取该 Expert 的 plugin_config（如果提供了）
        plugin_config_list = (
            expert_plugin_config_map.get(expert_code, [])
            if expert_plugin_config_map
            else []
        )

        # 构建 per-plugin 的 variable_mapping
        # 格式: {plugin_code: {variable_name: node:id}}
        plugin_mappings: Dict[str, Dict[str, str]] = {}

        # 遍历每个 plugin_config，根据其配置类型处理
        for plugin_item in plugin_config_list:
            plugin_code = plugin_item.get("plugin_code", "")
            if not plugin_code:
                continue

            variable_mapping: Dict[str, str] = {}

            # 1. 检查是否有 plugin 级别的 strategy_id 绑定（最高优先级）
            # 这来自 Plugin 表的 strategy_id 和 variable_mappings 字段
            plugin_strategy_id = plugin_item.get("strategy_id")
            plugin_variable_mappings = plugin_item.get("variable_mappings", [])

            if plugin_strategy_id and plugin_variable_mappings:
                # Plugin 绑定了策略，自动映射 variable_mappings 中的变量
                logger.info(
                    f"[StrategyHelper] 使用插件策略绑定: expert={expert_code}, "
                    f"plugin={plugin_code}, strategy_id={plugin_strategy_id}, "
                    f"mappings={[m.get('variable_name') for m in plugin_variable_mappings]}"
                )
                logger.info(f"[StrategyHelper] combo.nodes keys={list(nodes.keys())}")
                for mapping in plugin_variable_mappings:
                    var_name = mapping.get("variable_name")
                    label = mapping.get("label")
                    if var_name and label:
                        # 根据 label 从 combo.nodes 中获取节点
                        node = nodes.get(label)
                        node_id = _extract_node_id(node)
                        logger.info(
                            f"[StrategyHelper] 查找节点: label={label}, node_id={node_id}"
                        )

                        if node_id:
                            variable_mapping[var_name] = f"node:{node_id}"
                            logger.info(
                                f"[StrategyHelper] 插件策略映射: expert={expert_code}, "
                                f"plugin={plugin_code}, label={label} -> var={var_name}, node_id={node_id}"
                            )
                        else:
                            logger.warning(
                                f"[StrategyHelper] 插件策略映射失败: expert={expert_code}, "
                                f"plugin={plugin_code}, label={label} -> var={var_name}, "
                                f"reason=节点不存在或无效, combo.nodes keys={list(nodes.keys())}"
                            )

            # 2. 如果 plugin strategy 绑定没有产生映射，检查该 plugin 的 variable_mapping
            # 这是 expert_config.plugin_config 中配置的
            if not variable_mapping:
                configured_vars = plugin_item.get("variable_mapping", {})
                # 检查 variable_mapping 中是否有显式配置的值（非空数组）
                # 如果是空数组，说明用户希望使用策略自动映射
                has_explicit_config = False
                for var_name, var_value in configured_vars.items():
                    if var_value and not (
                        isinstance(var_value, list) and len(var_value) == 0
                    ):
                        has_explicit_config = True
                        break

                if has_explicit_config:
                    # 有显式配置，使用配置的值（处理 context_name 格式）
                    for var_name, var_value in configured_vars.items():
                        if var_value and isinstance(var_value, str):
                            variable_mapping[var_name] = var_value

            # 2.5. 回退逻辑：如果 plugin strategy 绑定没有产生映射，且 variable_mapping 是空数组
            # 尝试根据 Plugin.variable_mappings 中的 label 去 combo.nodes 中查找
            if not variable_mapping and plugin_variable_mappings:
                logger.info(
                    f"[StrategyHelper] 策略绑定未产生映射，尝试 label 回退匹配: expert={expert_code}, "
                    f"plugin={plugin_code}, strategy_id={plugin_strategy_id}, combo.nodes keys={list(nodes.keys())}"
                )
                for mapping in plugin_variable_mappings:
                    var_name = mapping.get("variable_name")
                    label = mapping.get("label")
                    if var_name and label:
                        node = nodes.get(label)
                        node_id = _extract_node_id(node)
                        if node_id:
                            variable_mapping[var_name] = f"node:{node_id}"
                            logger.info(
                                f"[StrategyHelper] Label回退匹配成功: expert={expert_code}, "
                                f"plugin={plugin_code}, label={label} -> var={var_name}, node_id={node_id}"
                            )
                        else:
                            logger.debug(
                                f"[StrategyHelper] Label回退匹配失败: expert={expert_code}, "
                                f"plugin={plugin_code}, label={label} 未在 combo.nodes 中找到"
                            )

            # 2.6. Plugin 级别的智能匹配：如果前面的步骤都没有产生映射，且是关键词类专家
            # 尝试根据变量名匹配策略维度（解决 Plugin 策略绑定失败时的兜底问题）
            if not variable_mapping:
                expert_lower = expert_code.lower()
                is_keyword_expert = any(
                    keyword in expert_lower
                    for keyword in [
                        "keyword",
                        "filter",
                        "ban",
                        "违禁",
                        "语法",
                        "错别字",
                        "critic",
                    ]
                )

                if is_keyword_expert:
                    # 收集该 plugin 需要匹配的变量名
                    target_variable_names: set[str] = set()
                    if plugin_variable_mappings:
                        for mapping in plugin_variable_mappings:
                            var_name = mapping.get("variable_name")
                            if var_name:
                                target_variable_names.add(var_name)

                    # 如果 Plugin 没有定义变量名，尝试从 variable_mapping 配置中获取
                    if not target_variable_names:
                        configured_vars = plugin_item.get("variable_mapping", {})
                        for var_name in configured_vars.keys():
                            if var_name:
                                target_variable_names.add(var_name)

                    # 遍历策略维度，尝试匹配变量名
                    for dimension, node in nodes.items():
                        node_id = _extract_node_id(node)
                        if not node_id:
                            continue

                        dim_lower = dimension.lower()

                        # 通用维度列表（不自动匹配）
                        generic_dimensions = {
                            "人设",
                            "场景",
                            "卖点",
                            "品牌",
                            "产品",
                            "渠道",
                            "目标人群",
                        }

                        # 如果维度名不是通用维度，则进行智能匹配
                        if dimension not in generic_dimensions:
                            # 检查维度名是否包含"词"、"关键词"、"违禁"等关键词
                            if any(
                                keyword in dim_lower
                                for keyword in [
                                    "词",
                                    "关键词",
                                    "违禁",
                                    "ban",
                                    "keyword",
                                    "语法",
                                    "错别字",
                                ]
                            ):
                                # 尝试匹配变量名
                                matched_var_name = None

                                if target_variable_names:
                                    # 尝试精确匹配或模糊匹配变量名
                                    for var_name in target_variable_names:
                                        var_lower = var_name.lower()
                                        # 精确匹配或包含匹配
                                        if (
                                            var_lower == dim_lower
                                            or var_lower in dim_lower
                                            or dim_lower in var_lower
                                        ):
                                            matched_var_name = var_name
                                            break
                                else:
                                    # 如果没有定义变量名，使用维度名作为变量名
                                    matched_var_name = dimension

                                if matched_var_name:
                                    variable_mapping[matched_var_name] = (
                                        f"node:{node_id}"
                                    )
                                    logger.info(
                                        f"[StrategyHelper] Plugin智能匹配: expert={expert_code}, "
                                        f"plugin={plugin_code}, 维度={dimension} -> 变量={matched_var_name}, node_id={node_id}"
                                    )
                                    break  # 找到一个匹配就停止

            if variable_mapping:
                plugin_mappings[plugin_code] = variable_mapping

        # 3. 使用 variable_share_mapping 逻辑（兜底或补充）
        # 无论 plugin_mappings 是否有值，都尝试用 variable_share_mapping 补充未映射的变量
        if expert_code in expert_to_dimensions:
            for mapping in expert_to_dimensions[expert_code]:
                dimension = mapping["dimension"]
                variable = mapping["variable"]

                # 检查这个变量是否已经被映射了
                already_mapped = False
                for existing_mapping in plugin_mappings.values():
                    if variable in existing_mapping:
                        already_mapped = True
                        break

                # 如果变量还没被映射，使用 variable_share_mapping
                if not already_mapped:
                    node = nodes.get(dimension)
                    node_id = _extract_node_id(node)
                    if node_id and variable:
                        # 找到或创建 "default" plugin 的映射
                        if "default" not in plugin_mappings:
                            plugin_mappings["default"] = {}
                        plugin_mappings["default"][variable] = f"node:{node_id}"
                        logger.info(
                            f"[StrategyHelper] variable_share_mapping补充: expert={expert_code}, "
                            f"dimension={dimension} -> variable={variable}, node_id={node_id}"
                        )

        # 4. 智能匹配：对于没有任何映射的专家，尝试根据变量名精确匹配策略维度
        # 约定：专家的插件变量名与策略维度名一致时自动匹配
        if not plugin_mappings:
            variable_mapping: Dict[str, str] = {}
            for dimension, node in nodes.items():
                node_id = _extract_node_id(node)
                if not node_id:
                    continue
                # 直接用维度名作为变量名进行匹配，存储 node:id 格式
                variable_mapping[dimension] = f"node:{node_id}"
                logger.info(
                    f"[StrategyHelper] 智能匹配: expert={expert_code}, "
                    f"维度={dimension} -> 变量={dimension}, node_id={node_id}"
                )

            if variable_mapping:
                plugin_mappings["default"] = variable_mapping

        # 只有存在变量映射时才添加配置
        if plugin_mappings:
            # 将 plugin_mappings 转换为需要的格式
            # 格式: [{"plugin_code": "xxx", "variable_mapping": {...}}, ...]
            expert_param_config[expert_code] = [
                {
                    "plugin_code": plugin_code,
                    "variable_mapping": var_mapping,
                }
                for plugin_code, var_mapping in plugin_mappings.items()
            ]

    return expert_param_config


def extract_strategy_combo_summary(combo: Dict[str, Any]) -> Dict[str, Any]:
    """
    提取策略组合的摘要信息（用于存储到 plan_item.strategy_combo）

    Args:
        combo: 完整的组合数据

    Returns:
        简化的组合信息: {
            "persona": {"id": "xxx", "name": "旺玥", "label": "人设"},
            "scenario": {"id": "yyy", "name": "换季期", "label": "场景"}
        }
    """
    nodes = combo.get("nodes", {})
    summary: Dict[str, Any] = {}

    for dimension, node in nodes.items():
        if isinstance(node, dict):
            summary[dimension] = {
                "id": node.get("id"),
                "name": node.get("name"),
                "label": node.get("label"),
            }
        elif isinstance(node, str):
            # 兼容 string 格式（defined_combinations 简化格式）
            summary[dimension] = {
                "id": node,
                "name": None,
                "label": None,
            }

    return summary


async def fetch_merged_strategy_combinations(
    strategy_selections: List[Dict[str, Any]],
    tenant_code: str = "default",
    include_corpus: bool = True,
    sample_mode: str = "first",
    primary_strategy_id: Optional[int] = None,
    target_count: Optional[int] = None,
) -> Dict[str, Any]:
    """
    通过 Dapr 调用 keyword-corpus 服务获取多策略合并组合

    Args:
        strategy_selections: 策略选择列表，格式: [
            {"strategy_id": "1", "selected_combo_ids": ["combo_0", "combo_1"]},
            {"strategy_id": "2", "selected_combo_ids": None}  # None 表示使用全部组合
        ]
        tenant_code: 租户编码
        include_corpus: 是否包含语料内容
        sample_mode: 采样模式（first/primary_strategy/random）
        primary_strategy_id: 主策略ID（sample_mode=primary_strategy 时必填）
        target_count: 目标组合数量（默认由后端决定）

    Returns:
        合并结果: {
            "merged_dimensions": ["人设", "场景", "卖点"],
            "dimension_conflicts": [],
            "source_strategies": [...],
            "total_count": 6,
            "merged_combinations": [
                {
                    "id": "merged_s1c0_s2c0",
                    "name": "卖点必带 + 过敏体质 + 季节天气",
                    "source_combos": [...],
                    "merged_nodes": {...}
                },
                ...
            ]
        }
    """

    payload = {
        "strategy_selections": strategy_selections,
        "include_corpus": include_corpus,
        "sample_mode": sample_mode,
    }

    # 只有在 sample_mode 为 primary_strategy 时才传递 primary_strategy_id
    if sample_mode == "primary_strategy" and primary_strategy_id:
        payload["primary_strategy_id"] = primary_strategy_id

    # 传递目标组合数量（确保后端按需生成，而不是返回默认200个）
    if target_count is not None:
        payload["target_count"] = target_count

    result = await invoke_method(
        app_id=KEYWORD_CORPUS_APP_ID,
        method_name="api/v1/content-strategies/merge-combinations",
        payload=payload,
    )

    total_count = result.get("total_count", 0)
    logger.info(f"成功获取 {total_count} 个合并组合")
    return result


async def fetch_strategy_detail(
    strategy_id: int, tenant_code: str = "default"
) -> Optional[Dict[str, Any]]:
    """
    获取策略详情

    Args:
        strategy_id: 策略 ID
        tenant_code: 租户编码

    Returns:
        策略详情，包含 id, name, node_pools 等字段
    """

    method_name = f"api/v1/content-strategies/{strategy_id}"

    try:
        result = await invoke_method(
            app_id=KEYWORD_CORPUS_APP_ID,
            method_name=method_name,
            params={"tenant_code": tenant_code},
            timeout=5.0,
            method="GET",
        )
        # 添加日志：打印原始返回数据
        logger.info(f"[fetch_strategy_detail] strategy_id={strategy_id}, result keys={list(result.keys()) if isinstance(result, dict) else type(result)}, name={result.get('name') if isinstance(result, dict) else 'N/A'}")
        return result
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 404:
            logger.info(
                f"策略不存在或已删除，忽略查询: strategy_id={strategy_id}, tenant_code={tenant_code}"
            )
            return None
        logger.warning(
            f"获取策略详情失败: strategy_id={strategy_id}, tenant_code={tenant_code}, status={e.response.status_code if e.response else 'unknown'}"
        )
        return None
    except Exception as e:
        logger.debug(f"获取策略详情失败: strategy_id={strategy_id}, error={e}")
        return None


async def fetch_strategy_node_pool_details(
    strategy_id: int,
    node_pools: Dict[str, Any],
    tenant_code: str = "default",
) -> Dict[str, List[Dict[str, Any]]]:
    """
    获取策略节点池详情（含语料预览）

    Args:
        strategy_id: 策略 ID
        node_pools: 节点池配置
            - 旧格式: {label: [node_id1, node_id2, ...]}
            - 新格式 v3: {label: {"node_ids": [...], "select_mode": "..."}}
        tenant_code: 租户编码

    Returns:
        节点详情 {label: [{id, name, corpus_count, corpus_preview}, ...]}
    """
    if not node_pools:
        return {}

    # 收集所有节点 ID（支持新旧两种格式）
    all_node_ids = []
    for pool_value in node_pools.values():
        all_node_ids.extend(_extract_node_ids_from_pool(pool_value))

    if not all_node_ids:
        return {}

    # 批量获取节点详情
    try:
        from app.utils.job_test_helper import _fetch_corpus_from_tree

        node_map = await _fetch_corpus_from_tree(all_node_ids, tenant_code=tenant_code)
    except Exception as e:
        logger.warning(f"获取节点详情失败: {e}")
        return {}

    # 按 label 组织结果（支持新旧两种格式）
    result: Dict[str, List[Dict[str, Any]]] = {}
    for label, pool_value in node_pools.items():
        node_ids = _extract_node_ids_from_pool(pool_value)
        # 获取 select_mode（默认 multiple，即节点分开使用）
        select_mode = 'multiple'
        if isinstance(pool_value, dict):
            select_mode = pool_value.get('select_mode', 'multiple')
        nodes = []
        for node_id in node_ids:
            node_data = node_map.get(str(node_id), {})
            corpus_list = node_data.get("corpus", [])

            # 生成语料预览
            preview = None
            if corpus_list:
                first_corpus = corpus_list[0]
                if isinstance(first_corpus, dict) and "fields" in first_corpus:
                    fields = first_corpus.get("fields", {})
                    preview_parts = []
                    for k, v in fields.items():
                        v_str = str(v)
                        if len(v_str) > 30:
                            preview_parts.append(f"{k}: {v_str[:30]}...")
                        else:
                            preview_parts.append(f"{k}: {v_str}")
                    preview = " | ".join(preview_parts)
                elif isinstance(first_corpus, dict) and "text" in first_corpus:
                    preview = first_corpus.get("text", "")[:150]
                else:
                    preview = str(first_corpus)[:150]

            nodes.append({
                "id": str(node_id),
                "name": node_data.get("name", f"节点{node_id}"),
                "corpus_count": len(corpus_list),
                "corpus_preview": preview,
            })
        result[label] = {
            "nodes": nodes,
            "select_mode": select_mode,
        }

    return result
