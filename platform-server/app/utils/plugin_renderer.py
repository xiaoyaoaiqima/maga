"""
Plugin renderer utility - Renders plugins and assembles prompt_template

v2 重构：
- 新增 render_with_snapshot 方法：支持基于策略快照的变量替换
- 新增 render_compatible 方法：自动检测模式并选择渲染方式
- 保留原有方法用于向后兼容
"""
import re
from typing import Dict, Any, Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.plugin import Plugin
from app.models.plugin_context import PluginContext
from app.services.plugin_service import PluginService
from app.services.plugin_context_service import PluginContextService

logger = get_logger()


class PluginRenderer:
    """
    Plugin renderer for assembling prompt_template from plugin_config
    
    v2 重构说明：
    - 支持两种模式：
      1. 旧模式（context_name）：从 plugin_context 表获取变量值
      2. 新模式（strategy）：从 plugin_snapshots 获取变量值
    """
    
    @staticmethod
    async def render_plugins(
        db: AsyncSession,
        plugin_config: List[Dict[str, Any]]
    ) -> str:
        """
        Assemble prompt_template from plugin_config, keeping {{variable_name}} placeholders
        
        This method only assembles the template by concatenating plugin.context_template,
        without replacing variables. Variable replacement happens at runtime.
        
        Args:
            db: Database session
            plugin_config: Plugin configuration array, format:
                [
                    {
                        "plugin_code": "xxx",
                        "variable_mapping": {
                            "variable_name": ["context_name1", "context_name2"]
                        }
                    }
                ]
        
        Returns:
            Assembled prompt_template string with {{variable_name}} placeholders preserved
        """
        if not plugin_config:
            return ""
        
        plugin_service = PluginService(db)
        template_parts: List[str] = []
        
        # Process each plugin item in order
        for plugin_item in plugin_config:
            plugin_code = plugin_item.get("plugin_code")
            if not plugin_code:
                continue
            
            # Get plugin by code
            plugin = await plugin_service.get_by_code(plugin_code)
            if not plugin:
                raise ValueError(f"Plugin with code {plugin_code} not found")
            
            if not plugin.enabled:
                continue  # Skip disabled plugins
            
            if not plugin.context_template:
                continue  # Skip plugins without context_template
            
            # Just use the context_template as-is, keeping {{variable_name}} placeholders
            # Variable replacement will happen at runtime
            template_parts.append(plugin.context_template)
        
        # Join all template parts with newlines
        return "\n\n".join(template_parts)
    
    @staticmethod
    def _render_template(template: str, variables: Dict[str, str]) -> str:
        """
        Render template with variables using {{variable_name}} syntax
        
        Args:
            template: Template string with {{variable_name}} placeholders
            variables: Dictionary of variable names to values
        
        Returns:
            Rendered template string
        """
        if not template:
            return ""
        
        result = template
        
        # Replace all {{variable_name}} with actual values
        for var_name, var_value in variables.items():
            # Match {{variable_name}} or {{ variable_name }}
            pattern = r'\{\{\s*' + re.escape(var_name) + r'\s*\}\}'
            result = re.sub(pattern, str(var_value), result)
        
        return result
    
    # ========== v2 新增方法 ==========
    
    @staticmethod
    async def render_with_snapshot(
        db: AsyncSession,
        plugin: Plugin,
        snapshot: Dict[str, Any],
    ) -> str:
        """
        使用快照渲染插件模板（新模式）
        
        Args:
            db: 数据库会话
            plugin: 插件实例
            snapshot: 插件快照，格式: {"变量名": {"corpus_text": "内容", ...}}
        
        Returns:
            渲染后的模板字符串
        """
        if not plugin.context_template:
            return ""
        
        template = plugin.context_template
        result = template
        
        # 从快照中提取变量值
        for var_name, var_data in snapshot.items():
            if isinstance(var_data, dict):
                # 新模式：从 corpus_text 获取值
                var_value = var_data.get("corpus_text", "")
            elif isinstance(var_data, str):
                # 兼容旧模式：直接使用字符串值
                var_value = var_data
            else:
                var_value = str(var_data)
            
            # 替换变量
            pattern = r'\{\{\s*' + re.escape(var_name) + r'\s*\}\}'
            result = re.sub(pattern, var_value, result)
        
        return result
    
    @staticmethod
    async def render_compatible(
        db: AsyncSession,
        plugin: Plugin,
        snapshot: Optional[Dict[str, Any]] = None,
        plugin_config_snapshot: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        兼容渲染：自动检测模式并选择渲染器
        
        优先使用新模式（snapshot），如果没有则使用旧模式（plugin_config_snapshot）
        
        Args:
            db: 数据库会话
            plugin: 插件实例
            snapshot: 新模式快照（来自 SubJob.plugin_snapshots）
            plugin_config_snapshot: 旧模式快照（来自 ExpertConfig.plugin_config）
        
        Returns:
            渲染后的模板字符串
        """
        if not plugin.context_template:
            return ""
        
        # 优先使用新模式（snapshot）
        if snapshot:
            logger.debug(f"使用新模式渲染插件: {plugin.plugin_code}")
            return await PluginRenderer.render_with_snapshot(db, plugin, snapshot)
        
        # 回退到旧模式（plugin_config_snapshot）
        if plugin_config_snapshot:
            logger.debug(f"使用旧模式渲染插件: {plugin.plugin_code}")
            return await PluginRenderer._render_old_mode(db, plugin, plugin_config_snapshot)
        
        # 无快照，返回原始模板
        return plugin.context_template
    
    @staticmethod
    async def _render_old_mode(
        db: AsyncSession,
        plugin: Plugin,
        plugin_config_snapshot: List[Dict[str, Any]],
    ) -> str:
        """
        旧模式渲染（使用 plugin_context）
        
        Args:
            db: 数据库会话
            plugin: 插件实例
            plugin_config_snapshot: 旧模式快照
        
        Returns:
            渲染后的模板字符串
        """
        template = plugin.context_template
        if not template:
            return ""
        
        result = template
        plugin_context_service = PluginContextService(db)
        
        # 找到当前插件的配置
        for config in plugin_config_snapshot:
            if config.get("plugin_code") != plugin.plugin_code:
                continue
            
            variable_mapping = config.get("variable_mapping", {})
            for var_name, context_name in variable_mapping.items():
                if isinstance(context_name, list) and context_name:
                    context_name = context_name[0]  # 取第一个
                
                # 检查是否是 node:xxx 格式（旧格式，向后兼容）
                if isinstance(context_name, str) and context_name.startswith("node:"):
                    # 旧格式：node:xxx，直接使用（应该已经被转换成 name）
                    var_value = context_name
                else:
                    # 从 plugin_context 表获取
                    context = await plugin_context_service.get_by_context_name(context_name)
                    if context and context.context:
                        var_value = context.context
                    else:
                        var_value = context_name
                
                # 替换变量
                pattern = r'\{\{\s*' + re.escape(var_name) + r'\s*\}\}'
                result = re.sub(pattern, str(var_value), result)
        
        return result
    
    @staticmethod
    def extract_variables_from_template(template: str) -> List[str]:
        """
        从模板中提取变量名
        
        Args:
            template: 模板字符串，包含 {{variable_name}} 占位符
        
        Returns:
            变量名列表
        """
        if not template:
            return []
        
        # 匹配 {{variable_name}} 或 {{ variable_name }}
        pattern = r'\{\{\s*([^}]+?)\s*\}\}'
        matches = re.findall(pattern, template)
        return list(set(matches))

