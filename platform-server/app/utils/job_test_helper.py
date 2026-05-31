"""
Job test helper utility - Helper functions for job testing
"""
import asyncio
import random
import re
from typing import Dict, Any, Optional, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.expert_config_service import ExpertConfigService
from app.services.plugin_service import PluginService
from app.services.plugin_context_service import PluginContextService
from app.core.logger import get_logger

logger = get_logger()


def _corpus_to_text(corpus_item: Dict[str, Any]) -> str:
    """
    将语料项转换为文本（兼容新旧格式）

    Args:
        corpus_item: 语料项

    Returns:
        语料文本
    """
    # 结构化语料（新格式）
    if "template_code" in corpus_item and "fields" in corpus_item:
        fields = corpus_item.get("fields", {})
        if isinstance(fields, dict):
            # 优先使用 field_keys 顺序。
            field_keys = corpus_item.get("field_keys")
            logger.info(f"[_corpus_to_text] template_code={corpus_item.get('template_code')}, field_keys={field_keys}, fields_keys={list(fields.keys())}")
            if field_keys and isinstance(field_keys, list):
                return "\n".join([
                    f"{k}: {fields.get(k, '')}" for k in field_keys if k in fields and fields.get(k)
                ])
            # 降级：使用 dict.items() 顺序（不保证）
            return "\n".join([
                f"{k}: {v}" for k, v in fields.items() if v
            ])
        return ""

    # 旧格式语料
    if "text" in corpus_item:
        return corpus_item.get("text", "")

    # 直接返回字符串（兼容最老的格式）
    if isinstance(corpus_item, str):
        return corpus_item

    return str(corpus_item)


async def _fetch_corpus_from_tree(node_ids: List[str], tenant_code: str = "default") -> Dict[str, Dict[str, Any]]:
    """旧 keyword_tree 语料源已下线，保留空返回避免历史调试链路启动失败。"""
    if node_ids:
        logger.warning(f"旧 keyword_tree 语料源已下线，忽略 node_ids={node_ids[:3]}")
    return {}


class JobTestHelper:
    """Helper functions for job testing"""
    
    @staticmethod
    async def build_plugin_config_snapshot(
        db: AsyncSession,
        expert_config_code: str,
        plugin_config: List[Dict[str, Any]],
        base_snapshot: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Build plugin_config_snapshot by selecting context_name from plugin_config.
        
        Args:
            db: Database session
            expert_config_code: Expert config code
            plugin_config: Plugin configuration array
            base_snapshot: Optional base snapshot to override/fill values. 
                          If a variable exists in base_snapshot, it will be used.
                          Otherwise, it will be randomly selected.
        """
        if not plugin_config:
            return []
        
        context_service = PluginContextService(db)
        
        # Step 0: Extract already selected values from base_snapshot
        selected_values: Dict[str, str] = {}
        if base_snapshot:
            for item in base_snapshot:
                mapping = item.get("variable_mapping", {})
                for var_name, ctx_name in mapping.items():
                    if isinstance(ctx_name, str) and ctx_name:
                        selected_values[var_name] = ctx_name

        # Step 1: Collect all variable_name occurrences and their available values across all plugins
        # Key: variable_name, Value: list of sets (each set is available values from one plugin)
        variable_occurrences: Dict[str, List[set]] = {}
        
        for plugin_item in plugin_config:
            variables = plugin_item.get("variable_mapping", {})
            
            for variable_name, context_value in variables.items():
                # Normalize to list
                if isinstance(context_value, str):
                    context_list = [context_value]
                elif isinstance(context_value, list):
                    context_list = context_value
                else:
                    continue
                
                if not context_list:
                    continue
                
                if variable_name not in variable_occurrences:
                    variable_occurrences[variable_name] = []
                variable_occurrences[variable_name].append(set(context_list))
        
        # Step 2: For each variable_name, compute intersection and select one value
        for variable_name, value_sets in variable_occurrences.items():
            # If already selected in base_snapshot, keep it (but verify it's valid if possible)
            if variable_name in selected_values:
                continue

            # Compute intersection of all sets for this variable_name
            if len(value_sets) == 1:
                available_values = value_sets[0]
            else:
                available_values = value_sets[0].intersection(*value_sets[1:])
            
            if not available_values:
                # If intersection is empty, this is a configuration error
                raise ValueError(
                    f"No common values found for variable '{variable_name}' across plugins "
                    f"in expert_config {expert_config_code}. "
                    f"Each plugin's available values: {[list(s) for s in value_sets]}"
                )
            
            # Randomly select one value from the intersection
            selected_context_name = random.choice(list(available_values))
            
            # Verify the context_name exists
            plugin_context = await context_service.get_by_context_name(selected_context_name)
            if not plugin_context:
                raise ValueError(
                    f"PluginContext with context_name '{selected_context_name}' not found "
                    f"for expert_config {expert_config_code}, variable '{variable_name}'"
                )
            
            selected_values[variable_name] = selected_context_name
        
        # Step 3: Build snapshot using pre-selected values
        snapshot: List[Dict[str, Any]] = []
        
        for plugin_item in plugin_config:
            plugin_code = plugin_item.get("plugin_code")
            variables = plugin_item.get("variable_mapping", {})
            
            if not plugin_code:
                continue
            
            plugin_snapshot: Dict[str, str] = {}
            
            for variable_name, context_value in variables.items():
                # Use the pre-selected value for this variable_name
                if variable_name in selected_values:
                    plugin_snapshot[variable_name] = selected_values[variable_name]
            
            if plugin_snapshot:
                snapshot.append({
                    "plugin_code": plugin_code,
                    "variable_mapping": plugin_snapshot
                })
        
        return snapshot
    
    @staticmethod
    async def render_prompt_with_snapshot_and_context(
        db: AsyncSession,
        prompt_template: str,
        plugin_config_snapshot: List[Dict[str, Any]],
        tenant_code: str = "default"
    ) -> str:
        """
        Render prompt_template with plugin_config_snapshot, using actual context content

        支持两种 source 模式：
        1. 旧模式（plugin_context）：variable_mapping = {"变量名": "context_name"}
        2. 新模式（keyword_tree）：variable_mapping = {"变量名": {"source": "keyword_tree", ...}}

        Args:
            db: Database session
            prompt_template: Prompt template string with {{variable_name}} placeholders
            plugin_config_snapshot: Plugin config snapshot array
            tenant_code: 租户编码

        Returns:
            Rendered prompt string with actual context content
        """
        if not prompt_template:
            return ""

        if not plugin_config_snapshot:
            return prompt_template

        # 调试日志：打印传入的参数
        logger.debug(
            f"[render_prompt DEBUG] input plugin_count={len(plugin_config_snapshot)}"
        )

        context_service = PluginContextService(db)

        # Flatten plugin_config_snapshot and fetch actual context content
        variables: Dict[str, str] = {}

        # 收集需要从 keyword_tree 获取的 node_ids
        keyword_tree_vars: Dict[str, Dict[str, Any]] = {}
        node_value_vars: Dict[str, str] = {}  # 存储 node:{node_id} 格式的变量

        for plugin_item in plugin_config_snapshot:
            plugin_vars = plugin_item.get("variable_mapping", {})
            for variable_name, context_value in plugin_vars.items():
                # 空数组或空列表：表示未配置，跳过此变量（替换为空字符串）
                # 这样可以避免未配置的变量保留占位符干扰 prompt 渲染
                if context_value is None or (isinstance(context_value, list) and len(context_value) == 0):
                    logger.warning(
                        f"[render_prompt] 变量 {variable_name} 的值为空（未配置），"
                        f"将替换为空字符串以避免干扰 prompt"
                    )
                    variables[variable_name] = ""
                    continue
                # 新模式：keyword_tree source（对象格式）
                if isinstance(context_value, dict) and context_value.get("source") == "keyword_tree":
                    keyword_tree_vars[variable_name] = context_value
                # 新模式：node:{node_id} 格式（前端选择后的值）
                # 前端可能传递 node:id 或 node:id:corpus_index 格式
                elif isinstance(context_value, str) and context_value.startswith("node:"):
                    node_id = context_value[5:]  # 去掉 "node:" 前缀
                    node_value_vars[variable_name] = node_id
                # 旧模式：context_name 字符串
                elif isinstance(context_value, str):
                    plugin_context = await context_service.get_by_context_name(context_value)
                    if plugin_context:
                        variables[variable_name] = plugin_context.context or context_value
                    else:
                        variables[variable_name] = context_value

        # 处理 node:{node_id} 格式的变量（支持单选和多选模式）
        # 多选模式：node_id 可能是逗号分隔的多个 ID，如 "17670796844942514,17670880893908053"
        # 单选模式可能带 corpus_index：node:id:corpus_index，如 "176829457457100002:1"
        logger.debug(
            f"[render_prompt DEBUG] node_value_var_names={list(node_value_vars.keys())}"
        )
        if node_value_vars:
            # 拆分逗号分隔的多选 ID，收集所有需要查询的 node_ids（去掉 corpus_index 后缀）
            all_node_ids: List[str] = []
            for node_id_str in node_value_vars.values():
                if "," in node_id_str:
                    # 多选模式：拆分逗号分隔的 ID
                    for single_id in node_id_str.split(","):
                        single_id = single_id.strip()
                        if single_id:
                            # 去掉 corpus_index 后缀（如果存在）
                            pure_id = single_id.split(":")[0]
                            all_node_ids.append(pure_id)
                else:
                    # 单选模式
                    if node_id_str:
                        # 去掉 corpus_index 后缀（如果存在）
                        pure_id = node_id_str.split(":")[0]
                        all_node_ids.append(pure_id)
            
            corpus_map = await _fetch_corpus_from_tree(all_node_ids, tenant_code=tenant_code)
            logger.debug(f"[render_prompt DEBUG] corpus_map keys={list(corpus_map.keys())}")

            for var_name, node_id_str in node_value_vars.items():
                # 检查是否是多选模式
                if "," in node_id_str:
                    # 多选模式：合并多个节点的语料
                    merged_corpus: List[Any] = []
                    merged_names: List[str] = []
                    for single_id in node_id_str.split(","):
                        single_id = single_id.strip()
                        if not single_id:
                            continue
                        node_data = corpus_map.get(single_id, {})
                        corpus_list = node_data.get("corpus", [])
                        if corpus_list:
                            merged_corpus.extend(corpus_list)
                        if node_data.get("name"):
                            merged_names.append(node_data["name"])
                    
                    logger.debug(f"[render_prompt DEBUG] var={var_name}, multi_node_ids={node_id_str}, merged_corpus_count={len(merged_corpus)}, merged_names={merged_names}")
                    
                    if merged_corpus:
                        # 多选模式：把所有语料都合并使用（如违禁词列表需要全部包含）
                        merged_texts = [_corpus_to_text(c) for c in merged_corpus]
                        variables[var_name] = "\n".join(merged_texts)
                    else:
                        # corpus 为空时，记录警告
                        # node name 应该由 _extract_context_list 填入 content.context_list
                        logger.debug(f"[render_prompt DEBUG] var={var_name}, multi_node_ids={node_id_str} has no corpus, skipping variable fill")
                else:
                    # 单选模式：支持 node:id:corpus_index 格式
                    # 解析出纯 node_id 和 corpus_index（如果有）
                    parts = node_id_str.split(":")
                    pure_node_id = parts[0]
                    corpus_index = int(parts[1]) if len(parts) > 1 else None

                    node_data = corpus_map.get(pure_node_id, {})
                    corpus_list = node_data.get("corpus", [])
                    logger.debug(f"[render_prompt DEBUG] var={var_name}, node_id={pure_node_id}, corpus_index={corpus_index}, has_corpus={bool(corpus_list)}, corpus_count={len(corpus_list)}")

                    if corpus_list:
                        # 如果指定了 corpus_index，使用指定的索引；否则随机选择
                        if corpus_index is not None and 0 <= corpus_index < len(corpus_list):
                            selected_corpus = corpus_list[corpus_index]
                            logger.debug(f"[render_prompt DEBUG] using specified corpus_index={corpus_index}")
                        else:
                            selected_corpus = random.choice(corpus_list)
                            logger.debug(f"[render_prompt DEBUG] using random choice")
                        variables[var_name] = _corpus_to_text(selected_corpus)
                    else:
                        # corpus 为空时，记录警告但不使用 name/description 填入变量
                        # node name 应该由 _extract_context_list 填入 content.context_list
                        logger.debug(f"[render_prompt DEBUG] var={var_name}, node_id={pure_node_id} has no corpus, skipping variable fill")

        # 处理 keyword_tree source 的变量（原始配置格式，用于后台任务）
        if keyword_tree_vars:
            # 收集所有需要查询的 node_ids
            all_node_ids_list: List[str] = []
            for var_config in keyword_tree_vars.values():
                node_ids = var_config.get("selected_node_ids", [])
                all_node_ids_list.extend([str(nid) for nid in node_ids])

            # 批量获取语料
            if all_node_ids_list:
                corpus_map = await _fetch_corpus_from_tree(all_node_ids_list, tenant_code=tenant_code)

                # 为每个变量选择一个 keyword
                for var_name, var_config in keyword_tree_vars.items():
                    node_ids = [str(nid) for nid in var_config.get("selected_node_ids", [])]
                    strategy = var_config.get("strategy", "random")

                    if not node_ids:
                        continue

                    # 根据策略选择节点
                    if strategy == "random":
                        selected_node_id = random.choice(node_ids)
                    else:
                        selected_node_id = node_ids[0]

                    # 获取节点的语料
                    node_data = corpus_map.get(selected_node_id, {})
                    corpus_list = node_data.get("corpus", [])

                    if corpus_list:
                        # 随机选择一个语料
                        selected_corpus = random.choice(corpus_list)
                        # 将语料转换为文本（兼容新旧格式）
                        variables[var_name] = _corpus_to_text(selected_corpus)
                    else:
                        # corpus 为空时，记录警告但不使用 name/description 填入变量
                        # node name 应该由 _extract_context_list 填入 content.context_list
                        logger.warning(f"变量 {var_name} 的节点 {selected_node_id} 没有可用的语料，跳过变量填充")

        # Render template with variables
        result = prompt_template
        logger.info(f"[render_prompt] variables to replace: {list(variables.keys())}")

        # Replace all {{variable_name}} with actual values
        for var_name, var_value in variables.items():
            # Match {{variable_name}} or {{ variable_name }}
            pattern = r'\{\{\s*' + re.escape(var_name) + r'\s*\}\}'
            result = re.sub(pattern, str(var_value), result)

        logger.info(f"[render_prompt] result first 300 chars: {result[:300]}")
        return result

    @staticmethod
    async def render_prompt_with_segments(
        db: AsyncSession,
        plugin_config: List[Dict[str, Any]],
        plugin_config_snapshot: List[Dict[str, Any]],
        tenant_code: str = "default"
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Render prompt and return segments for each plugin

        支持两种 source 模式：
        1. 旧模式（plugin_context）：variable_mapping = {"变量名": "context_name"}
        2. 新模式（keyword_tree）：variable_mapping = {"变量名": {"source": "keyword_tree", ...}}

        Args:
            db: Database session
            plugin_config: Plugin configuration array
            plugin_config_snapshot: Plugin config snapshot array
            tenant_code: 租户编码

        Returns:
            Tuple of (rendered_prompt, plugin_segments)
            plugin_segments format: [{"plugin_code": "xxx", "plugin_name": "xxx", "content": "xxx"}]
        """
        if not plugin_config or not plugin_config_snapshot:
            return "", []

        plugin_service = PluginService(db)
        context_service = PluginContextService(db)

        # Build variable values map from snapshot
        variables: Dict[str, str] = {}

        # 收集需要从 keyword_tree 获取的 node_ids
        keyword_tree_vars: Dict[str, Dict[str, Any]] = {}
        node_value_vars: Dict[str, str] = {}  # 存储 node:{node_id} 格式的变量

        for plugin_item in plugin_config_snapshot:
            plugin_vars = plugin_item.get("variable_mapping", {})
            for variable_name, context_value in plugin_vars.items():
                # 新模式：keyword_tree source（对象格式）
                if isinstance(context_value, dict) and context_value.get("source") == "keyword_tree":
                    keyword_tree_vars[variable_name] = context_value
                # 新模式：node:{node_id} 格式（前端选择后的值）
                # 前端可能传递 node:id 或 node:id:corpus_index 格式
                elif isinstance(context_value, str) and context_value.startswith("node:"):
                    node_id = context_value[5:]  # 去掉 "node:" 前缀
                    node_value_vars[variable_name] = node_id
                # 旧模式：context_name 字符串
                elif isinstance(context_value, str):
                    plugin_context = await context_service.get_by_context_name(context_value)
                    if plugin_context:
                        variables[variable_name] = plugin_context.context or context_value
                    else:
                        variables[variable_name] = context_value

        # 处理 node:{node_id} 或 node:{node_id}:{corpus_index} 格式的变量
        # 多选模式：node_id 可能是逗号分隔的多个 ID，如 "17670796844942514,17670880893908053"
        # 指定语料索引：node_id:corpus_index，如 "17670796844942514:0" 表示第0条语料
        if node_value_vars:
            # 拆分逗号分隔的多选 ID，收集所有需要查询的 node_ids
            all_node_ids: List[str] = []
            # 存储 node_id 到 corpus_index 的映射（如果指定了索引）
            corpus_index_map: Dict[str, int] = {}

            for node_id_str in node_value_vars.values():
                if "," in node_id_str:
                    for single_id in node_id_str.split(","):
                        single_id = single_id.strip()
                        if single_id:
                            # 检查是否指定了语料索引
                            if ":" in single_id:
                                parts = single_id.split(":")
                                all_node_ids.append(parts[0])
                                # 暂时忽略多选模式下的 corpus_index
                            else:
                                all_node_ids.append(single_id)
                else:
                    if node_id_str:
                        # 检查是否指定了语料索引
                        if ":" in node_id_str:
                            parts = node_id_str.split(":")
                            all_node_ids.append(parts[0])
                            try:
                                corpus_index_map[node_id_str] = int(parts[1])
                            except ValueError:
                                pass
                        else:
                            all_node_ids.append(node_id_str)

            corpus_map = await _fetch_corpus_from_tree(all_node_ids, tenant_code=tenant_code)

            for var_name, node_id_str in node_value_vars.items():
                # 检查是否是多选模式
                if "," in node_id_str:
                    # 多选模式：合并多个节点的语料
                    merged_corpus: List[Any] = []
                    merged_names: List[str] = []
                    for single_id in node_id_str.split(","):
                        single_id = single_id.strip()
                        if not single_id:
                            continue
                        # 提取纯 node_id（去掉 corpus_index 部分）
                        pure_node_id = single_id.split(":")[0]
                        node_data = corpus_map.get(pure_node_id, {})
                        corpus_list = node_data.get("corpus", [])
                        if corpus_list:
                            merged_corpus.extend(corpus_list)
                        if node_data.get("name"):
                            merged_names.append(node_data["name"])

                    if merged_corpus:
                        # 多选模式：把所有语料都合并使用（如违禁词列表需要全部包含）
                        merged_texts = [_corpus_to_text(c) for c in merged_corpus]
                        variables[var_name] = "\n".join(merged_texts)
                    else:
                        # corpus 为空时，记录警告
                        # node name 应该由 _extract_context_list 填入 content.context_list
                        logger.debug(f"[render_prompt DEBUG] var={var_name}, multi_node_ids={node_id_str} has no corpus, skipping variable fill")
                else:
                    # 单选模式
                    # 提取纯 node_id（去掉 corpus_index 部分）
                    pure_node_id = node_id_str.split(":")[0]
                    node_data = corpus_map.get(pure_node_id, {})
                    corpus_list = node_data.get("corpus", [])

                    if corpus_list:
                        # 检查是否指定了语料索引
                        if node_id_str in corpus_index_map:
                            corpus_index = corpus_index_map[node_id_str]
                            # -1 表示随机选择
                            if corpus_index == -1:
                                selected_corpus = random.choice(corpus_list)
                            # 确保索引在有效范围内
                            elif 0 <= corpus_index < len(corpus_list):
                                selected_corpus = corpus_list[corpus_index]
                            else:
                                # 索引越界，使用最后一条
                                selected_corpus = corpus_list[-1]
                        else:
                            # 未指定索引，随机选择
                            selected_corpus = random.choice(corpus_list)
                        variables[var_name] = _corpus_to_text(selected_corpus)
                    else:
                        # corpus 为空时，记录警告但不使用 name/description 填入变量
                        # node name 应该由 _extract_context_list 填入 content.context_list
                        logger.debug(f"[render_prompt DEBUG] var={var_name}, node_id={pure_node_id} has no corpus, skipping variable fill")

        # 处理 keyword_tree source 的变量（原始配置格式，用于后台任务）
        if keyword_tree_vars:
            all_node_ids_for_tree: List[str] = []
            for var_config in keyword_tree_vars.values():
                node_ids = var_config.get("selected_node_ids", [])
                all_node_ids_for_tree.extend([str(nid) for nid in node_ids])

            if all_node_ids_for_tree:
                corpus_map = await _fetch_corpus_from_tree(all_node_ids_for_tree, tenant_code=tenant_code)

                for var_name, var_config in keyword_tree_vars.items():
                    node_ids = [str(nid) for nid in var_config.get("selected_node_ids", [])]
                    strategy = var_config.get("strategy", "random")

                    if not node_ids:
                        continue

                    if strategy == "random":
                        selected_node_id = random.choice(node_ids)
                    else:
                        selected_node_id = node_ids[0]

                    node_data = corpus_map.get(selected_node_id, {})
                    corpus_list = node_data.get("corpus", [])

                    if corpus_list:
                        selected_corpus = random.choice(corpus_list)
                        # 将语料转换为文本（兼容新旧格式）
                        variables[var_name] = _corpus_to_text(selected_corpus)
                    else:
                        # corpus 为空时，记录警告但不使用 name/description 填入变量
                        # node name 应该由 _extract_context_list 填入 content.context_list
                        logger.debug(f"[render_prompt DEBUG] var={var_name}, node_id={selected_node_id} has no corpus, skipping variable fill")

        # Render each plugin's context_template separately
        segments: List[Dict[str, Any]] = []
        full_prompt_parts: List[str] = []

        for plugin_item in plugin_config:
            plugin_code = plugin_item.get("plugin_code")
            if not plugin_code:
                continue

            # Get plugin info
            plugin = await plugin_service.get_by_code(plugin_code)
            if not plugin:
                continue

            plugin_name = plugin.plugin_name or plugin_code
            context_template = plugin.context_template or ""

            # Render this plugin's context_template
            rendered_content = context_template
            for var_name, var_value in variables.items():
                pattern = r'\{\{\s*' + re.escape(var_name) + r'\s*\}\}'
                rendered_content = re.sub(pattern, str(var_value), rendered_content)

            if rendered_content.strip():
                segments.append({
                    "plugin_code": plugin_code,
                    "plugin_name": plugin_name,
                    "content": rendered_content
                })
                full_prompt_parts.append(rendered_content)

        full_prompt = "\n".join(full_prompt_parts)
        return full_prompt, segments

    @staticmethod
    def expand_job_generation_plan(job_generation_plan: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将 job_generation_plan.plan_items 按 count 展开为"每篇文章对应一个 plan_item"的列表。

        说明：
        - 支持两种格式：
          1. 未展开格式：plan_items[*].count 为非负整数，按 count 重复
          2. 已展开格式：plan_items 中每个 item 对应一篇文章（没有 count 字段）
        - 保持 plan_items 原始顺序
        """
        if not isinstance(job_generation_plan, dict):
            return []
        plan_items = job_generation_plan.get("plan_items")
        if not isinstance(plan_items, list):
            return []

        # 检查是否是已展开格式（没有 count 字段或 count 全为 1）
        is_expanded = True
        for item in plan_items:
            if not isinstance(item, dict):
                continue
            count = item.get("count")
            # 如果有任何 item 的 count > 1，说明是未展开格式
            if isinstance(count, int) and count > 1:
                is_expanded = False
                break
        
        # 如果已展开，直接返回
        if is_expanded:
            return [item for item in plan_items if isinstance(item, dict)]
        
        # 如果未展开，按 count 展开
        expanded: List[Dict[str, Any]] = []
        for item in plan_items:
            if not isinstance(item, dict):
                continue
            count = item.get("count")
            if not isinstance(count, int) or count <= 0:
                continue
            expanded.extend([item] * count)
        return expanded

    @staticmethod
    async def expand_job_generation_plan_async(
        job_generation_plan: Optional[Dict[str, Any]],
        tenant_code: str = "default",
        db: Optional[AsyncSession] = None,
        expert_config_code_list: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        异步版本的 expand_job_generation_plan，支持 strategy_v3 格式动态展开。

        说明：
        - 如果已有 plan_items，直接使用（与同步版本一致）
        - 如果是 strategy_v3 模式，会查询 ExpertConfig 和 Plugin 表获取 plugin strategy_id 绑定
        - expert_config_code_list：从 job.expert_config_code_list 传入，用于轻量级配置模式

        Args:
            job_generation_plan: Job 执行计划
            tenant_code: 租户代码
            db: 数据库会话
            expert_config_code_list: Expert 配置代码列表（用于轻量级配置）
        """
        if not isinstance(job_generation_plan, dict):
            return []

        # 如果已有 plan_items，使用同步逻辑
        plan_items = job_generation_plan.get("plan_items")
        if isinstance(plan_items, list) and plan_items:
            return JobTestHelper.expand_job_generation_plan(job_generation_plan)

        # 检查是否是 strategy_v3 模式
        mode = job_generation_plan.get("mode")
        if mode == "strategy_v3":
            return await JobTestHelper._expand_strategy_v3_plan(
                job_generation_plan, tenant_code, db, expert_config_code_list
            )

        logger.warning(f"[expand_job_generation_plan_async] 未知的 mode: {mode}，返回空列表")
        return []

    @staticmethod
    async def _expand_strategy_v3_plan(
        job_generation_plan: Dict[str, Any],
        tenant_code: str = "default",
        db: Optional[AsyncSession] = None,
        expert_config_code_list: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        展开 strategy_v3 模式的 plan（多策略维度合并）。

        说明：
        - 旧策略系统已下线，调用兼容层时会给出明确错误
        - 如果有 merged_allocations（旧格式），根据 allocations 生成 plan_items
        - 如果没有 merged_allocations（轻量级格式），根据 target_count 和返回的组合生成 plan_items
        - 查询 ExpertConfig 和 Plugin 表获取 plugin strategy_id 绑定（支持插件策略自动映射）

        Args:
            job_generation_plan: Job 执行计划
            tenant_code: 租户代码
            db: 数据库会话
            expert_config_code_list: Expert 配置代码列表（从 job.expert_config_code_list 传入）
        """
        strategy_selections = job_generation_plan.get("strategy_selections", [])
        merged_allocations = job_generation_plan.get("merged_allocations", {})
        variable_share_mapping = job_generation_plan.get("variable_share_mapping", {})

        # 优先使用传入的 expert_config_code_list，否则从 plan 中读取（向后兼容）
        if expert_config_code_list is None:
            expert_config_code_list = job_generation_plan.get("expert_config_code_list", [])

        # 轻量级配置的新参数
        sample_mode = job_generation_plan.get("sample_mode", "first")
        primary_strategy_id = job_generation_plan.get("primary_strategy_id")
        target_count = job_generation_plan.get("target_count")

        if not strategy_selections:
            return []

        # 查询 ExpertConfig 和 Plugin 表，构建 expert_plugin_config_map（支持 plugin strategy_id 绑定模式）
        expert_plugin_config_map: Dict[str, List[Dict[str, Any]]] = {}
        if db and expert_config_code_list:
            try:
                from app.models.expert_config import ExpertConfig
                from app.models.plugin import Plugin
                from sqlalchemy import select, and_

                # 查询 ExpertConfig
                stmt = select(ExpertConfig).where(
                    and_(
                        ExpertConfig.expert_config_code.in_(expert_config_code_list),
                        ExpertConfig.is_deleted == 0
                    )
                )
                result = await db.execute(stmt)
                expert_configs = result.scalars().all()

                # 收集所有需要查询的 plugin_code
                all_plugin_codes: set[str] = set()
                for ec in expert_configs:
                    if ec.plugin_config:
                        for plugin_item in ec.plugin_config:
                            plugin_code = plugin_item.get("plugin_code")
                            if plugin_code:
                                all_plugin_codes.add(plugin_code)

                # 批量查询 Plugin 表获取 strategy_id 和 variable_mappings
                plugin_map: Dict[str, Plugin] = {}
                if all_plugin_codes:
                    plugin_stmt = select(Plugin).where(
                        and_(
                            Plugin.plugin_code.in_(list(all_plugin_codes)),
                            Plugin.is_deleted == 0,
                        )
                    )
                    plugin_result = await db.execute(plugin_stmt)
                    for plugin in plugin_result.scalars().all():
                        plugin_map[plugin.plugin_code] = plugin

                # 合并 ExpertConfig.plugin_config 和 Plugin.strategy_id/variable_mappings
                for ec in expert_configs:
                    if ec.plugin_config:
                        enhanced_plugin_config = []
                        for plugin_item in ec.plugin_config:
                            plugin_code = plugin_item.get("plugin_code")
                            if not plugin_code:
                                continue

                            # 复制原始配置
                            enhanced_item = dict(plugin_item)

                            # 从 Plugin 表补充 strategy_id 和 variable_mappings
                            plugin = plugin_map.get(plugin_code)
                            if plugin:
                                if plugin.strategy_id:
                                    enhanced_item["strategy_id"] = plugin.strategy_id
                                if plugin.variable_mappings:
                                    enhanced_item["variable_mappings"] = plugin.variable_mappings

                            enhanced_plugin_config.append(enhanced_item)

                        expert_plugin_config_map[ec.expert_config_code] = enhanced_plugin_config

                logger.debug(f"[expand_strategy_v3] 查询 ExpertConfig/Plugin 成功，expert_plugin_config_map keys={list(expert_plugin_config_map.keys())}")
            except Exception as e:
                logger.warning(f"[expand_strategy_v3] 查询 ExpertConfig/Plugin 失败: {e}")

        from app.utils.strategy_helper import (
            fetch_merged_strategy_combinations,
            build_expert_param_config_from_combo,
        )

        # ⭐ 使用轻量级配置中的参数（向后兼容旧格式）
        # sample_mode, primary_strategy_id, target_count 已在函数开头提取

        logger.debug(
            f"[expand_strategy_v3] 使用采样模式: sample_mode={sample_mode}, "
            f"primary_strategy_id={primary_strategy_id}, target_count={target_count}"
        )

        try:
            merge_result = await fetch_merged_strategy_combinations(
                strategy_selections=strategy_selections,
                tenant_code=tenant_code,
                include_corpus=False,  # 不返回语料内容，减少响应体积
                sample_mode=sample_mode,
                primary_strategy_id=primary_strategy_id,
                target_count=target_count,
            )
        except Exception as e:
            logger.error(f"[expand_strategy_v3] 获取合并组合失败: {e}")
            return []

        merged_combinations = merge_result.get("merged_combinations", [])
        if not merged_combinations:
            logger.warning("[expand_strategy_v3] 未获取到合并组合")
            return []

        # 构建 combo_id -> combo 映射
        combo_map = {c.get("id"): c for c in merged_combinations}

        # ⭐ 轻量级配置模式：没有 merged_allocations
        # 直接使用 fetch_merged_strategy_combinations 返回的组合，每个组合生成 1 篇
        if not merged_allocations:
            # API 已经根据 target_count 返回了正确数量的组合
            merged_allocations = {c["id"]: 1 for c in merged_combinations}
            logger.debug(
                f"[expand_strategy_v3] 轻量级配置模式：使用 API 返回的 {len(merged_combinations)} 个组合"
            )
        else:
            # 旧格式：验证 merged_allocations 中的 combo_id 是否有效
            # 如果所有 combo_id 都无效（可能是策略被修改导致 ID 变化），则回退到默认值
            valid_combos_exist = any(combo_id in combo_map for combo_id in merged_allocations.keys())
            if not valid_combos_exist and merged_combinations:
                logger.warning(
                    f"[expand_strategy_v3] merged_allocations 中的所有 combo_id 都无效，"
                    f"回退到默认值（每个组合生成 1 篇）。"
                    f"无效 IDs: {list(merged_allocations.keys())[:5]}...（显示前5个）"
                )
                merged_allocations = {c["id"]: 1 for c in merged_combinations}

        expanded: List[Dict[str, Any]] = []
        plan_idx = 0

        for combo_id, count in merged_allocations.items():
            if not isinstance(count, int) or count <= 0:
                continue

            combo = combo_map.get(combo_id)
            if not combo:
                logger.warning(f"[expand_strategy_v3] 合并组合 {combo_id} 不存在")
                continue

            # 获取合并后的节点
            merged_nodes = combo.get("merged_nodes", {})

            # 为每个分配的篇数生成一个 plan_item
            for _ in range(count):
                # 构建 expert_param_config
                # merged_nodes 格式和 combo.nodes 格式一致
                fake_combo = {"nodes": merged_nodes}
                expert_param_config = build_expert_param_config_from_combo(
                    combo=fake_combo,
                    variable_share_mapping=variable_share_mapping,
                    expert_config_code_list=expert_config_code_list,
                    expert_plugin_config_map=expert_plugin_config_map,  # 传入 plugin 配置映射
                )

                # 提取策略组合摘要
                strategy_combo = {}
                for dim, node_info in merged_nodes.items():
                    if isinstance(node_info, dict):
                        strategy_combo[dim] = {
                            "id": node_info.get("id"),
                            "name": node_info.get("name"),
                            "label": node_info.get("label"),
                        }

                expanded.append({
                    "type": "strategy_v3",
                    "index": plan_idx,
                    "merged_combo_id": combo_id,
                    "name": combo.get("name", f"合并组合 {combo_id}"),
                    "source_combos": combo.get("source_combos", []),
                    "strategy_combo": strategy_combo,
                    "expert_param_config": expert_param_config,
                })
                logger.debug(
                    f"[expand_strategy_v3] plan_item[{plan_idx}] expert_count={len(expert_param_config)}"
                )
                plan_idx += 1

        logger.debug(f"[expand_strategy_v3] 动态展开 {len(expanded)} 个 plan_items")
        return expanded

    @staticmethod
    def get_plan_item_snapshot_for_expert(
        plan_item: Optional[Dict[str, Any]],
        expert_config_code: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        从 plan_item 中提取某个 expert 的 plugin_config_snapshot。

        约定：
        - plan_item.expert_param_config 可以是：
          - dict: {expert_config_code: [{plugin_code, variable_mapping:{var: context_name}}]}
          - list: 直接是某个 expert 的 snapshot（兼容只配置 GENERATION 的场景）
        """
        if not isinstance(plan_item, dict):
            return None

        epc = plan_item.get("expert_param_config")
        if isinstance(epc, list):
            return epc
        if isinstance(epc, dict):
            v = epc.get(expert_config_code)
            if isinstance(v, list):
                return v
        return None
