"""
语料模板服务
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.corpus_template import CorpusTemplate
from app.models.graph import GraphNode
from app.schemas.corpus_template import (
    CorpusTemplateCreate,
    CorpusTemplateItem,
    CorpusTemplateUpdate,
)

logger = logging.getLogger(__name__)


class CorpusTemplateService:
    """语料模板服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_list(
        self,
        category_type: Optional[str] = None,
        tenant_code: Optional[str] = None,
    ) -> list[CorpusTemplateItem]:
        """获取模板列表（包含节点使用统计）"""
        conditions = [CorpusTemplate.is_deleted == 0]

        if category_type:
            conditions.append(CorpusTemplate.category_type == category_type)

        # 精确筛选：如果指定了租户，只返回该租户的模板（不再混入 default）
        if tenant_code:
            conditions.append(CorpusTemplate.tenant_code == tenant_code)

        stmt = (
            select(CorpusTemplate)
            .where(and_(*conditions))
            .order_by(CorpusTemplate.category_type, CorpusTemplate.code)
        )

        result = await self.db.execute(stmt)
        templates = result.scalars().all()

        # 一次性统计所有模板的节点使用数量
        node_counts = await self._count_nodes_for_templates(templates)

        return [self._to_item(t, node_counts.get(t.code, 0)) for t in templates]

    async def get_distinct_category_types(
        self,
        tenant_code: Optional[str] = None,
    ) -> list[str]:
        """获取所有不重复的分类类型（从 nodes 表的 label 字段获取）"""
        conditions = [GraphNode.is_deleted == 0, GraphNode.is_active == 1]

        if tenant_code:
            conditions.append(GraphNode.tenant_code == tenant_code)

        stmt = (
            select(GraphNode.label)
            .where(and_(*conditions))
            .distinct()
            .order_by(GraphNode.label)
        )

        result = await self.db.execute(stmt)
        category_types = result.scalars().all()

        return list(category_types)

    async def get_by_code(self, code: str) -> Optional[CorpusTemplateItem]:
        """根据编码获取模板"""
        stmt = select(CorpusTemplate).where(
            and_(
                CorpusTemplate.code == code,
                CorpusTemplate.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        template = result.scalar_one_or_none()
        
        if not template:
            return None
        
        return self._to_item(template)

    async def get_by_category_type(
        self,
        category_type: str,
        tenant_code: str = "default",
    ) -> Optional[CorpusTemplateItem]:
        """根据分类类型获取模板（优先返回租户专属模板，同类型多模板时返回最新创建的）"""
        # 优先查找租户专属模板
        if tenant_code and tenant_code != "default":
            stmt = (
                select(CorpusTemplate)
                .where(
                    and_(
                        CorpusTemplate.category_type == category_type,
                        CorpusTemplate.tenant_code == tenant_code,
                        CorpusTemplate.is_deleted == 0,
                    )
                )
                .order_by(CorpusTemplate.id.desc())
                .limit(1)
            )
            result = await self.db.execute(stmt)
            template = result.scalars().first()
            if template:
                return self._to_item(template)
        
        # 回退到 default 模板（同类型多模板时返回最新创建的）
        stmt = (
            select(CorpusTemplate)
            .where(
                and_(
                    CorpusTemplate.category_type == category_type,
                    CorpusTemplate.tenant_code == "default",
                    CorpusTemplate.is_deleted == 0,
                )
            )
            .order_by(CorpusTemplate.id.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        template = result.scalars().first()
        
        if not template:
            return None
        
        return self._to_item(template)

    async def create(self, data: CorpusTemplateCreate) -> CorpusTemplateItem:
        """创建模板"""
        # 如果未提供 code，自动生成（参考 Job 的 ID 生成逻辑）
        template_code = data.code
        if not template_code or not template_code.strip():
            template_code = f"template-{uuid.uuid4().hex[:16]}"
            logger.info(f"自动生成模板编码: {template_code}")

        # 在每个字段中添加 order 字段，用于解决 MySQL JSON 列不保证顺序的问题
        fields_with_order = []
        for idx, field in enumerate(data.fields):
            field_dict = field.model_dump()
            field_dict["order"] = idx
            fields_with_order.append(field_dict)

        template = CorpusTemplate(
            code=template_code,
            name=data.name,
            category_type=data.category_type,
            fields=fields_with_order,
            description=data.description,
            tenant_code=data.tenant_code,
        )

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        logger.info(f"创建语料模板: {template_code}")
        return self._to_item(template)

    async def update(self, code: str, data: CorpusTemplateUpdate) -> Optional[CorpusTemplateItem]:
        """更新模板"""
        stmt = select(CorpusTemplate).where(
            and_(
                CorpusTemplate.code == code,
                CorpusTemplate.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        template = result.scalar_one_or_none()

        if not template:
            return None

        if data.name is not None:
            template.name = data.name
        if data.fields is not None:
            # 在每个字段中添加 order 字段
            fields_with_order = []
            for idx, field in enumerate(data.fields):
                field_dict = field.model_dump()
                field_dict["order"] = idx
                fields_with_order.append(field_dict)
            template.fields = fields_with_order
        if data.description is not None:
            template.description = data.description

        await self.db.commit()
        await self.db.refresh(template)

        logger.info(f"更新语料模板: {code}")
        return self._to_item(template)

    async def delete(self, code: str) -> bool:
        """
        删除模板（软删除）

        Raises:
            ValueError: 如果模板被节点使用（node_count > 0）
        """
        stmt = select(CorpusTemplate).where(
            and_(
                CorpusTemplate.code == code,
                CorpusTemplate.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        template = result.scalar_one_or_none()

        if not template:
            return False

        # 检查模板是否被节点使用
        node_count = await self._count_nodes_for_template(template)
        if node_count > 0:
            raise ValueError(
                f"无法删除模板 '{template.name}' ({code})："
                f"该模板被 {node_count} 个节点使用，请先移除使用该模板的所有节点后再删除"
            )

        template.is_deleted = 1
        await self.db.commit()

        logger.info(f"删除语料模板: {code}")
        return True

    async def _count_nodes_for_templates(
        self,
        templates: list[CorpusTemplate],
    ) -> dict[str, int]:
        """
        统计每个模板被多少节点使用

        实现：
        1. 遍历所有模板的 corpus（JSON 数组）
        2. 统计每个 template_code 出现的次数
        3. 返回 {template_code: count} 字典

        注意：
        - corpus 格式：[{"template_code": "xxx", "fields": {...}}, ...]
        - 只统计未删除的节点 (is_deleted=0)
        """
        if not templates:
            return {}

        template_codes = [t.code for t in templates]

        # 统计结果字典
        node_counts: dict[str, int] = {code: 0 for code in template_codes}

        # 查询所有未删除的节点
        stmt = select(GraphNode).where(
            and_(
                GraphNode.is_deleted == 0,
                GraphNode.corpus.is_not(None),
                GraphNode.corpus != "null",
                GraphNode.corpus != "",
            )
        )
        result = await self.db.execute(stmt)
        nodes = result.scalars().all()

        # 遍历所有节点的 corpus，统计模板使用次数
        for node in nodes:
            if not node.corpus:
                continue

            try:
                corpus_list = json.loads(node.corpus) if isinstance(node.corpus, str) else node.corpus

                if not isinstance(corpus_list, list):
                    continue

                # 统计该节点中每个模板的出现次数（一个节点可能有多条同模板的语料）
                for corpus_item in corpus_list:
                    if isinstance(corpus_item, dict):
                        template_code = corpus_item.get("template_code")
                        if template_code in template_codes:
                            node_counts[template_code] = node_counts.get(template_code, 0) + 1
            except (json.JSONDecodeError, TypeError):
                # corpus 格式错误，跳过
                logger.warning(f"节点 {node.id} 的 corpus 格式错误: {node.corpus[:100] if node.corpus else 'None'}")
                continue

        return node_counts

    async def _count_nodes_for_template(
        self,
        template: CorpusTemplate,
    ) -> int:
        """
        统计单个模板被多少节点使用

        Args:
            template: 要统计的模板

        Returns:
            使用该模板的节点数量
        """
        node_counts = await self._count_nodes_for_templates([template])
        return node_counts.get(template.code, 0)

    def _to_item(
        self,
        template: CorpusTemplate,
        node_count: int = 0,
    ) -> CorpusTemplateItem:
        """转换为响应项"""
        return CorpusTemplateItem(
            id=template.id,
            code=template.code,
            name=template.name,
            category_type=template.category_type,
            fields=template.fields,
            description=template.description,
            tenant_code=template.tenant_code,
            create_time=template.create_time,
            update_time=template.update_time,
            node_count=node_count,
        )
