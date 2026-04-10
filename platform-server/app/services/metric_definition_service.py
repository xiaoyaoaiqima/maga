from typing import List, Optional, Dict, Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.metrics import RAAP_METRIC_QUERIES, METRIC_FIELD_DEFINITIONS
from app.models.metric_definition import MetricDefinition
from app.schemas.metric_definition import MetricDefinitionCreate, MetricDefinitionUpdate


class MetricDefinitionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_key(self, metric_key: str) -> Optional[MetricDefinition]:
        """根据 Key 获取指标定义"""
        stmt = select(MetricDefinition).where(MetricDefinition.metric_key == metric_key)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self) -> List[MetricDefinition]:
        """获取所有指标定义"""
        stmt = select(MetricDefinition).order_by(MetricDefinition.display_order, MetricDefinition.id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def create(self, schema: MetricDefinitionCreate) -> MetricDefinition:
        """创建指标定义"""
        db_obj = MetricDefinition(**schema.model_dump())
        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj

    async def update(self, metric_key: str, schema: MetricDefinitionUpdate) -> Optional[MetricDefinition]:
        """更新指标定义"""
        db_obj = await self.get_by_key(metric_key)
        if not db_obj:
            return None

        update_data = schema.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj

    async def delete(self, metric_key: str) -> bool:
        """删除指标定义"""
        db_obj = await self.get_by_key(metric_key)
        if not db_obj:
            return False
        
        await self.db.delete(db_obj)
        await self.db.commit()
        return True

    async def sync_from_codebase(self) -> Dict[str, int]:
        """
        从代码库同步指标定义到数据库
        策略：如果数据库不存在该 key，则创建；如果存在，则跳过（保留用户编辑的内容）
        """
        stats = {"created": 0, "skipped": 0}
        
        # 预定义分类映射
        def get_category(key: str) -> str:
            if key.startswith("rlhf_"): return "RLHF"
            if key.startswith("ge_"): return "Generation"
            if key.startswith("ag_"): return "AG"
            if key.startswith("dashboard") or key.startswith("daily"): return "Dashboard"
            return "Cost"

        # 1. 同步查询级指标 (Query Metrics)
        for key, value in RAAP_METRIC_QUERIES.items():
            existing = await self.get_by_key(key)
            if existing:
                stats["skipped"] += 1
                continue
            
            # 创建新定义
            new_def = MetricDefinition(
                metric_key=key,
                metric_name=value["name"],
                description=value["description"],
                category=get_category(key),
                display_order=0
            )
            self.db.add(new_def)
            stats["created"] += 1

        # 2. 同步字段级指标 (Field Metrics)
        for key, value in METRIC_FIELD_DEFINITIONS.items():
            existing = await self.get_by_key(key)
            if existing:
                stats["skipped"] += 1
                continue
            
            # 创建新定义
            new_def = MetricDefinition(
                metric_key=key,
                metric_name=value["name"],
                description=value["description"],
                category=value.get("category", get_category(key)),
                unit=value.get("unit"),
                display_order=0
            )
            self.db.add(new_def)
            stats["created"] += 1
        
        if stats["created"] > 0:
            await self.db.commit()
            
        return stats
    
    async def get_all_definitions_map(self) -> Dict[str, Dict[str, Any]]:
        """获取所有指标定义，返回字典格式 {key: {name, description, category}}"""
        definitions = await self.get_all()
        result = {}
        
        # 先放入数据库中的定义
        for d in definitions:
            result[d.metric_key] = {
                "name": d.metric_name,
                "description": d.description,
                "category": d.category
            }
            
        # 再补充代码中存在但数据库中没有的
        for key, value in RAAP_METRIC_QUERIES.items():
            if key not in result:
                result[key] = {
                    "name": value["name"],
                    "description": value["description"],
                    "category": "Unknown"
                }

        for key, value in METRIC_FIELD_DEFINITIONS.items():
            if key not in result:
                result[key] = {
                    "name": value["name"],
                    "description": value["description"],
                    "category": value.get("category", "Unknown")
                }
                
        return result

