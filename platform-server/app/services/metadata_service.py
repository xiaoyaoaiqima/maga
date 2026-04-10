"""
元数据管理服务

管理品牌、产品、标签等元数据配置
使用独立的 node_property_meta 表，与 nodes 表解耦
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from loguru import logger
from sqlalchemy import and_, cast, func, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import (
    cache_delete_pattern,
    cache_get,
    cache_set,
    CACHE_TTL_METADATA,
)
from app.models.graph import GraphNode, NodePropertyMeta
from app.schemas.metadata import (
    BrandWithProducts,
    LabelType,
    LabelTypeOption,
    LabelTypesResponse,
    MetadataItemCreate,
    MetadataItemResponse,
    MetadataItemUpdate,
    MetadataStatsResponse,
    MetadataTreeNode,
    MetadataType,
    SimpleOption,
    TagGroupWithTags,
)
from app.services.category_service import generate_id


class MetadataService:
    """元数据管理服务 - 使用 node_property_meta 表"""

    # 元数据类型对应的 item_type
    ITEM_TYPE_MAPPING = {
        MetadataType.BRAND: "brand",
        MetadataType.PRODUCT: "product",
        MetadataType.TAG_GROUP: "tag_group",
        MetadataType.TAG: "tag",
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== 缓存管理 ====================

    async def _invalidate_metadata_cache(self, tenant_code: str) -> None:
        """清除元数据相关缓存（品牌、标签选项）"""
        await cache_delete_pattern(f"kc:meta:brands:{tenant_code}")
        await cache_delete_pattern(f"kc:meta:tags:{tenant_code}:*")
        logger.debug(f"清除元数据缓存: tenant_code={tenant_code}")

    # ==================== 通用 CRUD ====================

    async def create_item(
        self,
        tenant_code: str,
        data: MetadataItemCreate,
        created_by: str | None = None,
    ) -> MetadataItemResponse:
        """创建元数据项"""
        # 兼容枚举和字符串类型
        if isinstance(data.item_type, MetadataType):
            item_type = self.ITEM_TYPE_MAPPING.get(data.item_type, data.item_type.value)
        else:
            item_type = data.item_type
        
        # 如果没有提供 code，自动生成 UUID
        code = data.code
        if not code:
            code = str(uuid.uuid4())
        
        item = NodePropertyMeta(
            id=generate_id(),
            tenant_code=tenant_code,
            item_type=item_type,
            name=data.name,
            code=code,
            description=data.description,
            parent_id=int(data.parent_id) if data.parent_id else None,
            icon=data.icon,
            color=data.color,
            sort_order=data.sort_order or 0,
            is_active=1,
            is_deleted=0,
            created_by=created_by,
        )
        
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        
        # 清除缓存
        await self._invalidate_metadata_cache(tenant_code)
        
        logger.info(f"创建元数据: type={data.item_type}, name={data.name}, id={item.id}")
        
        return await self._item_to_response(item)

    async def update_item(
        self,
        item_id: int,
        data: MetadataItemUpdate,
        updated_by: str | None = None,
    ) -> MetadataItemResponse | None:
        """更新元数据项"""
        item = await self.db.get(NodePropertyMeta, item_id)
        if not item or item.is_deleted == 1:
            return None
        
        if data.name is not None:
            item.name = data.name
        if data.code is not None:
            item.code = data.code
        if data.description is not None:
            item.description = data.description
        if data.icon is not None:
            item.icon = data.icon
        if data.color is not None:
            item.color = data.color
        if data.sort_order is not None:
            item.sort_order = data.sort_order
        if data.is_active is not None:
            item.is_active = data.is_active
        
        await self.db.commit()
        await self.db.refresh(item)
        
        # 清除缓存
        await self._invalidate_metadata_cache(item.tenant_code)
        
        logger.info(f"更新元数据: id={item_id}, name={item.name}")
        
        return await self._item_to_response(item)

    async def delete_item(self, item_id: int) -> bool:
        """删除元数据项（软删除）"""
        item = await self.db.get(NodePropertyMeta, item_id)
        if not item or item.is_deleted == 1:
            return False
        
        item.is_deleted = 1
        
        # 同时软删除子项
        stmt = select(NodePropertyMeta).where(
            and_(
                NodePropertyMeta.parent_id == item_id,
                NodePropertyMeta.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        children = result.scalars().all()
        for child in children:
            child.is_deleted = 1
        
        await self.db.commit()
        
        # 清除缓存
        await self._invalidate_metadata_cache(item.tenant_code)
        
        logger.info(f"删除元数据: id={item_id}")
        return True

    async def get_item(self, item_id: int) -> MetadataItemResponse | None:
        """获取单个元数据项"""
        item = await self.db.get(NodePropertyMeta, item_id)
        if not item or item.is_deleted == 1:
            return None
        return await self._item_to_response(item)

    async def list_items(
        self,
        tenant_code: str,
        item_type: MetadataType | None = None,
        parent_id: int | None = None,
        include_inactive: bool = False,
    ) -> list[MetadataItemResponse]:
        """列出元数据项"""
        conditions = [
            NodePropertyMeta.tenant_code == tenant_code,
            NodePropertyMeta.is_deleted == 0,
        ]
        
        if item_type:
            type_str = self.ITEM_TYPE_MAPPING.get(item_type, item_type.value)
            conditions.append(NodePropertyMeta.item_type == type_str)
        
        if not include_inactive:
            conditions.append(NodePropertyMeta.is_active == 1)
        
        if parent_id:
            conditions.append(NodePropertyMeta.parent_id == parent_id)
        else:
            # 如果没有指定父级，且是子级类型，则不限制
            # 如果是顶级类型（brand, tag_group），则限制 parent_id 为空
            if item_type in [MetadataType.BRAND, MetadataType.TAG_GROUP]:
                conditions.append(NodePropertyMeta.parent_id == None)
        
        stmt = select(NodePropertyMeta).where(and_(*conditions)).order_by(
            NodePropertyMeta.sort_order,
            NodePropertyMeta.name,
        )
        result = await self.db.execute(stmt)
        items = result.scalars().all()
        
        return [await self._item_to_response(item) for item in items]

    # ==================== 品牌与产品 ====================

    async def get_brands_with_products(
        self,
        tenant_code: str,
    ) -> list[BrandWithProducts]:
        """获取品牌列表及其产品"""
        brands = await self.list_items(tenant_code, MetadataType.BRAND)
        
        result = []
        for brand in brands:
            products = await self.list_items(
                tenant_code, 
                MetadataType.PRODUCT, 
                parent_id=int(brand.id)
            )
            
            total_corpus = brand.corpus_count
            for product in products:
                total_corpus += product.corpus_count
            
            result.append(BrandWithProducts(
                id=brand.id,
                name=brand.name,
                code=brand.code,
                description=brand.description,
                products=products,
                total_corpus_count=total_corpus,
            ))
        
        return result

    async def get_brand_tree(
        self,
        tenant_code: str,
    ) -> list[MetadataTreeNode]:
        """获取品牌-产品树"""
        brands_with_products = await self.get_brands_with_products(tenant_code)
        
        tree = []
        for brand in brands_with_products:
            children = [
                MetadataTreeNode(
                    id=p.id,
                    key=p.id,
                    title=p.name,
                    name=p.name,
                    code=p.code,
                    item_type="product",
                    description=p.description,
                    icon=p.icon,
                    color=p.color,
                    sort_order=p.sort_order,
                    is_active=p.is_active,
                    corpus_count=p.corpus_count,
                    children=[],
                )
                for p in brand.products
            ]
            
            tree.append(MetadataTreeNode(
                id=brand.id,
                key=brand.id,
                title=brand.name,
                name=brand.name,
                code=brand.code,
                item_type="brand",
                description=brand.description,
                corpus_count=brand.total_corpus_count,
                children=children,
            ))
        
        return tree

    async def get_product_options(
        self,
        tenant_code: str,
        brand_id: int | None = None,
    ) -> list[SimpleOption]:
        """获取产品选项（用于下拉选择）"""
        products = await self.list_items(
            tenant_code, 
            MetadataType.PRODUCT,
            parent_id=brand_id,
        )
        
        return [
            SimpleOption(
                value=p.name,
                label=p.name,
                id=p.id,
            )
            for p in products
        ]

    async def get_brand_options(
        self,
        tenant_code: str,
    ) -> list[SimpleOption]:
        """获取品牌选项（用于下拉选择）"""
        # === 缓存检查 ===
        cache_key = f"kc:meta:brands:{tenant_code}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return [SimpleOption(**item) for item in cached]

        brands = await self.list_items(tenant_code, MetadataType.BRAND)
        
        result = [
            SimpleOption(
                value=b.code or b.name,
                label=b.name,
                id=b.id,
            )
            for b in brands
        ]
        
        # === 写入缓存 ===
        await cache_set(cache_key, [r.model_dump() for r in result], CACHE_TTL_METADATA)
        
        return result

    # ==================== 标签管理 ====================

    async def get_tag_groups_with_tags(
        self,
        tenant_code: str,
    ) -> list[TagGroupWithTags]:
        """获取标签组列表及其标签"""
        groups = await self.list_items(tenant_code, MetadataType.TAG_GROUP)
        
        result = []
        for group in groups:
            tags = await self.list_items(
                tenant_code, 
                MetadataType.TAG, 
                parent_id=int(group.id)
            )
            
            result.append(TagGroupWithTags(
                id=group.id,
                name=group.name,
                description=group.description,
                tags=tags,
            ))
        
        return result

    async def get_tag_tree(
        self,
        tenant_code: str,
    ) -> list[MetadataTreeNode]:
        """获取标签组-标签树"""
        groups_with_tags = await self.get_tag_groups_with_tags(tenant_code)
        
        tree = []
        for group in groups_with_tags:
            children = [
                MetadataTreeNode(
                    id=t.id,
                    key=t.id,
                    title=t.name,
                    name=t.name,
                    code=t.code,
                    item_type="tag",
                    description=t.description,
                    icon=t.icon,
                    color=t.color,
                    sort_order=t.sort_order,
                    is_active=t.is_active,
                    corpus_count=t.corpus_count,
                    children=[],
                )
                for t in group.tags
            ]
            
            tree.append(MetadataTreeNode(
                id=group.id,
                key=group.id,
                title=group.name,
                name=group.name,
                item_type="tag_group",
                description=group.description,
                corpus_count=sum(t.corpus_count for t in group.tags),
                children=children,
            ))
        
        return tree

    async def get_tag_options(
        self,
        tenant_code: str,
        group_id: int | None = None,
    ) -> list[SimpleOption]:
        """获取标签选项（用于下拉选择）"""
        # === 缓存检查 ===
        cache_key = f"kc:meta:tags:{tenant_code}:{group_id or 'all'}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return [SimpleOption(**item) for item in cached]

        tags = await self.list_items(
            tenant_code, 
            MetadataType.TAG,
            parent_id=group_id,
        )
        
        result = [
            SimpleOption(
                value=str(t.id),  # 使用 id 作为 value，用于策略 tags 字段存储
                label=t.name,
                id=str(t.id),
            )
            for t in tags
        ]
        
        # === 写入缓存 ===
        await cache_set(cache_key, [r.model_dump() for r in result], CACHE_TTL_METADATA)
        
        return result

    # ==================== 统计 ====================

    async def get_stats(
        self,
        tenant_code: str,
    ) -> MetadataStatsResponse:
        """获取元数据统计"""
        brand_count = await self._count_by_type(tenant_code, "brand")
        product_count = await self._count_by_type(tenant_code, "product")
        tag_group_count = await self._count_by_type(tenant_code, "tag_group")
        tag_count = await self._count_by_type(tenant_code, "tag")

        total_corpus = await self._count_all_corpus(tenant_code)

        return MetadataStatsResponse(
            brand_count=brand_count,
            product_count=product_count,
            tag_group_count=tag_group_count,
            tag_count=tag_count,
            global_corpus_count=total_corpus,  # 全部语料
            brand_corpus_count=0,  # ⚠️ 已废弃，返回 0
            product_corpus_count=0,  # ⚠️ 已废弃，返回 0
        )

    async def _count_by_type(self, tenant_code: str, item_type: str) -> int:
        """统计指定类型的元数据数量"""
        stmt = select(func.count()).select_from(NodePropertyMeta).where(
            and_(
                NodePropertyMeta.tenant_code == tenant_code,
                NodePropertyMeta.item_type == item_type,
                NodePropertyMeta.is_deleted == 0,
                NodePropertyMeta.is_active == 1,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def _count_all_corpus(self, tenant_code: str) -> int:
        """统计全部语料数量（不区分 scope）"""
        stmt = select(func.count()).select_from(GraphNode).where(
            and_(
                GraphNode.tenant_code == tenant_code,
                GraphNode.is_deleted == 0,
                GraphNode.is_active == 1,
                GraphNode.corpus.isnot(None),
                cast(GraphNode.corpus, String) != "[]",
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    # ==================== 辅助方法 ====================

    async def _item_to_response(self, item: NodePropertyMeta) -> MetadataItemResponse:
        """将元数据项转换为响应对象"""
        # 获取父级名称
        parent_name = None
        if item.parent_id:
            parent = await self.db.get(NodePropertyMeta, item.parent_id)
            if parent:
                parent_name = parent.name
        
        # 获取子项数量
        children_count = await self._count_children(item.id)
        
        # 获取关联的语料数量
        corpus_count = await self._count_related_corpus(item)
        
        return MetadataItemResponse(
            id=str(item.id),
            item_type=item.item_type,
            name=item.name,
            code=item.code,
            description=item.description,
            icon=item.icon,
            color=item.color,
            sort_order=item.sort_order or 0,
            parent_id=str(item.parent_id) if item.parent_id else None,
            parent_name=parent_name,
            is_active=item.is_active,
            corpus_count=corpus_count,
            children_count=children_count,
            created_at=item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else None,
            updated_at=item.updated_at.strftime("%Y-%m-%d %H:%M:%S") if item.updated_at else None,
        )

    async def _count_children(self, item_id: int) -> int:
        """统计子项数量"""
        stmt = select(func.count()).select_from(NodePropertyMeta).where(
            and_(
                NodePropertyMeta.parent_id == item_id,
                NodePropertyMeta.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def _count_related_corpus(self, item: NodePropertyMeta) -> int:
        """
        统计关联的语料数量
        - 品牌：统计 properties.brands 包含该品牌名称的语料
        - 产品：统计 properties.brands 包含该产品名称的语料
        - 标签：统计 properties.tags 包含该标签的语料
        """
        if item.item_type == "brand":
            # 查询 properties.brands 包含该品牌名称的节点
            # 使用 cast 将 JSON 转为字符串，然后用 like 匹配
            brand_name = item.name
            stmt = select(func.count()).select_from(GraphNode).where(
                and_(
                    GraphNode.tenant_code == item.tenant_code,
                    cast(GraphNode.properties["brands"], String).like(f"%{brand_name}%"),
                    GraphNode.is_deleted == 0,
                    GraphNode.is_active == 1,
                    GraphNode.corpus.isnot(None),
                    cast(GraphNode.corpus, String) != "[]",
                )
            )
            result = await self.db.execute(stmt)
            return result.scalar() or 0

        elif item.item_type == "product":
            # 查询 properties.brands 包含该产品名称的节点
            product_name = item.name
            stmt = select(func.count()).select_from(GraphNode).where(
                and_(
                    GraphNode.tenant_code == item.tenant_code,
                    cast(GraphNode.properties["brands"], String).like(f"%{product_name}%"),
                    GraphNode.is_deleted == 0,
                    GraphNode.is_active == 1,
                    GraphNode.corpus.isnot(None),
                    cast(GraphNode.corpus, String) != "[]",
                )
            )
            result = await self.db.execute(stmt)
            return result.scalar() or 0

        elif item.item_type == "tag":
            # 查询 properties.tags 包含该标签的节点
            tag_name = item.name
            stmt = select(func.count()).select_from(GraphNode).where(
                and_(
                    GraphNode.tenant_code == item.tenant_code,
                    cast(GraphNode.properties["tags"], String).like(f"%{tag_name}%"),
                    GraphNode.is_deleted == 0,
                    GraphNode.is_active == 1,
                    GraphNode.corpus.isnot(None),
                    cast(GraphNode.corpus, String) != "[]",
                )
            )
            result = await self.db.execute(stmt)
            return result.scalar() or 0

        return 0

    # ==================== 统一标签树 ====================

    async def get_unified_tree(
        self,
        tenant_code: str,
    ) -> list[MetadataTreeNode]:
        """
        获取统一的标签树（支持所有类型，包括自定义类型）

        返回所有类型的分组和标签，不再区分品牌/标签类型
        """
        # 直接获取所有根节点（parent_id 为 None）
        stmt = select(NodePropertyMeta).where(
            and_(
                NodePropertyMeta.tenant_code == tenant_code,
                NodePropertyMeta.is_deleted == 0,
                NodePropertyMeta.is_active == 1,
                NodePropertyMeta.parent_id == None,
            )
        ).order_by(
            NodePropertyMeta.sort_order,
            NodePropertyMeta.name,
        )
        result = await self.db.execute(stmt)
        root_items = result.scalars().all()

        unified_tree = []
        for root_item in root_items:
            # 递归获取子节点
            children = await self._build_tree_children(root_item.id)

            unified_tree.append(MetadataTreeNode(
                id=str(root_item.id),
                key=str(root_item.id),
                title=root_item.name,
                name=root_item.name,
                code=root_item.code,
                item_type=root_item.item_type,
                description=root_item.description,
                icon=root_item.icon,
                color=root_item.color,
                sort_order=root_item.sort_order or 0,
                is_active=root_item.is_active,
                corpus_count=await self._count_related_corpus(root_item),
                children=children,
            ))

        # 按 sort_order 和 name 排序
        unified_tree.sort(key=lambda x: (x.sort_order or 0, x.name))

        logger.info(f"获取统一标签树: tenant_code={tenant_code}, total={len(unified_tree)}")

        return unified_tree

    async def _build_tree_children(self, parent_id: int) -> list[MetadataTreeNode]:
        """递归构建子节点树"""
        stmt = select(NodePropertyMeta).where(
            and_(
                NodePropertyMeta.parent_id == parent_id,
                NodePropertyMeta.is_deleted == 0,
                NodePropertyMeta.is_active == 1,
            )
        ).order_by(
            NodePropertyMeta.sort_order,
            NodePropertyMeta.name,
        )
        result = await self.db.execute(stmt)
        children = result.scalars().all()

        if not children:
            return []

        tree_nodes = []
        for child in children:
            # 递归获取子节点
            grandchildren = await self._build_tree_children(child.id)

            tree_nodes.append(MetadataTreeNode(
                id=str(child.id),
                key=str(child.id),
                title=child.name,
                name=child.name,
                code=child.code,
                item_type=child.item_type,
                description=child.description,
                icon=child.icon,
                color=child.color,
                sort_order=child.sort_order or 0,
                is_active=child.is_active,
                corpus_count=await self._count_related_corpus(child),
                children=grandchildren,
            ))

        return tree_nodes

    # ==================== 统一标签类型 ====================

    async def get_label_types(
        self,
        tenant_code: str,
    ) -> LabelTypesResponse:
        """
        获取所有标签类型（用于统一标签选择器）

        返回格式：
        - 产品标签（product）
        - 各标签组及其标签值（tag_group -> tag）
        """
        label_types: list[LabelType] = []

        # 1. 获取产品标签
        products = await self.list_items(tenant_code, MetadataType.PRODUCT)
        if products:
            label_types.append(LabelType(
                key="product",
                name="产品标签",
                icon="📦",
                color="#10b981",
                multi_select=True,
                options=[
                    LabelTypeOption(value=p.name, label=p.name)
                    for p in products
                ],
            ))

        # 2. 获取标签组及其标签
        tag_groups = await self.list_items(tenant_code, MetadataType.TAG_GROUP)
        for group in tag_groups:
            tags = await self.list_items(
                tenant_code,
                MetadataType.TAG,
                parent_id=int(group.id),
            )

            # 使用 group.code 或 "tag_group_{id}" 作为 key
            group_key = group.code if group.code else f"tag_group_{group.id}"

            label_types.append(LabelType(
                key=group_key,
                name=group.name,
                icon=group.icon or "🏷️",
                color=group.color or "#8b5cf6",
                multi_select=True,
                options=[
                    LabelTypeOption(value=t.name, label=t.name)
                    for t in tags
                ],
            ))

        return LabelTypesResponse(label_types=label_types)
