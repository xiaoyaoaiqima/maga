"""
Demo Data Service

演示数据配置管理服务
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from app.core.logger import logger


class DemoDataService:
    """
    演示数据配置管理服务

    功能:
    1. 管理演示数据配置（CRUD）
    2. 全局演示模式开关
    3. 静态/动态演示数据生成
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.demo_table = "raap_dashboard_data_cache_demo_config"
        self.GLOBAL_DEMO_KEY = "__global__"

    # ==================== 全局演示模式开关 ====================

    async def is_global_demo_enabled(self) -> bool:
        """
        ✅ Bug#3: 检查全局演示模式是否启用

        Returns:
            True 表示启用，False 表示禁用
        """
        sql = text(f"""
            SELECT global_enabled
            FROM {self.demo_table}
            WHERE demo_key = :global_demo_key
        """)

        result = await self.session.execute(sql, {"global_demo_key": self.GLOBAL_DEMO_KEY})
        row = result.fetchone()

        return row and row["global_enabled"] == 1

    async def set_global_demo_mode(self, enabled: bool) -> None:
        """
        ✅ Bug#3: 设置全局演示模式

        Args:
            enabled: True 启用，False 禁用
        """
        sql = text(f"""
            INSERT INTO {self.demo_table} (
                demo_key, demo_name, demo_enabled, demo_type, global_enabled,
                created_at, updated_at
            ) VALUES (
                :global_demo_key, '全局演示模式配置', 0, 'static', :enabled,
                NOW(), NOW()
            )
            ON DUPLICATE KEY UPDATE
                global_enabled = VALUES(global_enabled),
                updated_at = NOW()
        """)

        await self.session.execute(sql, {
            "global_demo_key": self.GLOBAL_DEMO_KEY,
            "enabled": 1 if enabled else 0,
        })
        await self.session.commit()

        logger.info(f"全局演示模式已: {'启用' if enabled else '禁用'}")

    # ==================== 演示数据配置 CRUD ====================

    async def create_demo_config(
        self,
        demo_key: str,
        demo_name: str,
        demo_type: str,
        static_data: Optional[Any] = None,
        dynamic_rule_type: Optional[str] = None,
        dynamic_rule_config: Optional[Dict] = None,
        valid_from: Optional[datetime] = None,
        valid_until: Optional[datetime] = None,
        demo_enabled: bool = True,
    ) -> Dict:
        """
        创建演示数据配置

        Args:
            demo_key: 演示数据键（唯一标识）
            demo_name: 演示数据名称
            demo_type: 演示类型（static/increment/range/random/function）
            static_data: 静态数据（demo_type=static 时使用）
            dynamic_rule_type: 动态规则类型（demo_type=dynamic 时使用）
            dynamic_rule_config: 动态规则配置
            valid_from: 有效期开始
            valid_until: 有效期结束
            demo_enabled: 是否启用

        Returns:
            创建的配置记录
        """
        sql = text(f"""
            INSERT INTO {self.demo_table} (
                demo_key, demo_name, demo_enabled, demo_type,
                static_data, dynamic_rule_type, dynamic_rule_config,
                valid_from, valid_until,
                created_at, updated_at
            ) VALUES (
                :demo_key, :demo_name, :demo_enabled, :demo_type,
                :static_data, :dynamic_rule_type, :dynamic_rule_config,
                :valid_from, :valid_until,
                NOW(), NOW()
            )
        """)

        await self.session.execute(sql, {
            "demo_key": demo_key,
            "demo_name": demo_name,
            "demo_enabled": 1 if demo_enabled else 0,
            "demo_type": demo_type,
            "static_data": json.dumps(static_data) if static_data else None,
            "dynamic_rule_type": dynamic_rule_type,
            "dynamic_rule_config": json.dumps(dynamic_rule_config) if dynamic_rule_config else None,
            "valid_from": valid_from,
            "valid_until": valid_until,
        })
        await self.session.commit()

        logger.info(f"演示数据配置已创建: {demo_key}")
        return await self.get_demo_config(demo_key)

    async def get_demo_config(self, demo_key: str) -> Optional[Dict]:
        """获取演示数据配置"""
        sql = text(f"""
            SELECT
                id, demo_key, demo_name, demo_enabled, demo_type,
                static_data, dynamic_rule_type, dynamic_rule_config,
                valid_from, valid_until, hit_count, last_hit_at,
                created_at, updated_at
            FROM {self.demo_table}
            WHERE demo_key = :demo_key
        """)

        result = await self.session.execute(sql, {"demo_key": demo_key})
        row = result.fetchone()

        if not row:
            return None

        return {
            "id": row["id"],
            "demo_key": row["demo_key"],
            "demo_name": row["demo_name"],
            "demo_enabled": row["demo_enabled"] == 1,
            "demo_type": row["demo_type"],
            "static_data": row["static_data"],
            "dynamic_rule_type": row["dynamic_rule_type"],
            "dynamic_rule_config": json.loads(row["dynamic_rule_config"]) if row["dynamic_rule_config"] else None,
            "valid_from": row["valid_from"].isoformat() if row["valid_from"] else None,
            "valid_until": row["valid_until"].isoformat() if row["valid_until"] else None,
            "hit_count": row["hit_count"],
            "last_hit_at": row["last_hit_at"].isoformat() if row["last_hit_at"] else None,
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }

    async def list_demo_configs(
        self,
        demo_enabled: Optional[bool] = None,
        demo_type: Optional[str] = None,
    ) -> List[Dict]:
        """
        列出演示数据配置

        Args:
            demo_enabled: 过滤是否启用
            demo_type: 过滤演示类型

        Returns:
            配置列表
        """
        conditions = []
        params = {}

        if demo_enabled is not None:
            conditions.append("demo_enabled = :demo_enabled")
            params["demo_enabled"] = 1 if demo_enabled else 0

        if demo_type:
            conditions.append("demo_type = :demo_type")
            params["demo_type"] = demo_type

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        sql = text(f"""
            SELECT
                id, demo_key, demo_name, demo_enabled, demo_type,
                valid_from, valid_until, hit_count, last_hit_at,
                created_at, updated_at
            FROM {self.demo_table}
            {where_clause}
            ORDER BY created_at DESC
        """)

        result = await self.session.execute(sql, params)
        rows = result.fetchall()

        return [
            {
                "id": row["id"],
                "demo_key": row["demo_key"],
                "demo_name": row["demo_name"],
                "demo_enabled": row["demo_enabled"] == 1,
                "demo_type": row["demo_type"],
                "valid_from": row["valid_from"].isoformat() if row["valid_from"] else None,
                "valid_until": row["valid_until"].isoformat() if row["valid_until"] else None,
                "hit_count": row["hit_count"],
                "last_hit_at": row["last_hit_at"].isoformat() if row["last_hit_at"] else None,
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
            }
            for row in rows
        ]

    async def update_demo_config(
        self,
        demo_key: str,
        **updates,
    ) -> bool:
        """
        更新演示数据配置

        Args:
            demo_key: 演示数据键
            **updates: 要更新的字段

        Returns:
            True 表示成功，False 表示不存在
        """
        if not updates:
            return False

        # 处理 JSON 字段
        if "static_data" in updates and updates["static_data"] is not None:
            updates["static_data"] = json.dumps(updates["static_data"])

        if "dynamic_rule_config" in updates and updates["dynamic_rule_config"] is not None:
            updates["dynamic_rule_config"] = json.dumps(updates["dynamic_rule_config"])

        # 处理布尔字段
        if "demo_enabled" in updates:
            updates["demo_enabled"] = 1 if updates["demo_enabled"] else 0

        # 构建 SET 子句
        set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
        updates["demo_key"] = demo_key
        updates["updated_at"] = datetime.now()

        sql = text(f"""
            UPDATE {self.demo_table}
            SET {set_clause}, updated_at = :updated_at
            WHERE demo_key = :demo_key
        """)

        result = await self.session.execute(sql, updates)
        await self.session.commit()

        updated = result.rowcount > 0
        if updated:
            logger.info(f"演示数据配置已更新: {demo_key}")

        return updated

    async def delete_demo_config(self, demo_key: str) -> bool:
        """
        删除演示数据配置

        Args:
            demo_key: 演示数据键

        Returns:
            True 表示成功，False 表示不存在
        """
        sql = text(f"""
            DELETE FROM {self.demo_table}
            WHERE demo_key = :demo_key
        """)

        result = await self.session.execute(sql, {"demo_key": demo_key})
        await self.session.commit()

        deleted = result.rowcount > 0
        if deleted:
            logger.info(f"演示数据配置已删除: {demo_key}")

        return deleted

    # ==================== 演示数据生成 ====================

    async def get_demo_data(self, demo_key: str) -> Optional[Any]:
        """
        获取演示数据

        Args:
            demo_key: 演示数据键

        Returns:
            演示数据或 None
        """
        # 先检查全局开关
        if not await self.is_global_demo_enabled():
            return None

        # 查询演示配置
        sql = text(f"""
            SELECT
                demo_type, static_data, dynamic_rule_type, dynamic_rule_config
            FROM {self.demo_table}
            WHERE demo_key = :demo_key
                AND demo_enabled = 1
                AND (valid_from IS NULL OR valid_from <= NOW())
                AND (valid_until IS NULL OR valid_until >= NOW())
        """)

        result = await self.session.execute(sql, {"demo_key": demo_key})
        row = result.fetchone()

        if not row:
            return None

        # 更新命中统计
        await self.session.execute(text(f"""
            UPDATE {self.demo_table}
            SET hit_count = hit_count + 1,
                last_hit_at = NOW()
            WHERE demo_key = :demo_key
        """), {"demo_key": demo_key})
        await self.session.commit()

        # 根据类型返回数据
        if row["demo_type"] == "static":
            return row["static_data"]
        elif row["demo_type"] == "dynamic":
            return await self._generate_dynamic_data(row)
        else:
            logger.warning(f"未知的演示类型: {row['demo_type']}")
            return None

    async def _generate_dynamic_data(self, config_row) -> Any:
        """生成动态演示数据"""
        import math

        rule_type = config_row["dynamic_rule_type"]
        rule_config = json.loads(config_row["dynamic_rule_config"]) if config_row["dynamic_rule_config"] else {}

        if rule_type == "increment":
            return await self._generate_increment_data(rule_config)
        elif rule_type == "range":
            return await self._generate_range_data(rule_config)
        elif rule_type == "random":
            return await self._generate_random_data(rule_config)
        elif rule_type == "function":
            return await self._generate_function_data(rule_config)
        else:
            logger.warning(f"未知的动态规则类型: {rule_type}")
            return None

    async def _generate_increment_data(self, config: Dict) -> Any:
        """生成累加数据"""
        from datetime import timedelta

        base_value = config.get("base_value", 0)
        increment = config.get("increment", 0)
        interval = config.get("interval_seconds", 60)
        currencies = config.get("currencies", [])

        now = datetime.now()
        base_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed_seconds = (now - base_time).total_seconds()
        steps = int(elapsed_seconds / interval)

        current_value = base_value + (increment * steps)

        if currencies:
            return [
                {
                    "currency": currency,
                    "total_cost": current_value * (1.0 if currency == "USD" else 7.5)
                }
                for currency in currencies
            ]
        else:
            return {"total_cost": current_value}

    async def _generate_range_data(self, config: Dict) -> Any:
        """生成范围数据"""
        from datetime import timedelta
        import random

        min_val = config.get("min", 0)
        max_val = config.get("max", 1000)
        data_points = config.get("data_points", 10)

        return [
            {
                "value": random.uniform(min_val, max_val),
                "timestamp": (datetime.now() - timedelta(seconds=i * 60)).isoformat()
            }
            for i in range(data_points)
        ]

    async def _generate_random_data(self, config: Dict) -> Any:
        """生成随机数据"""
        import random
        return random.uniform(config.get("min", 0), config.get("max", 1000))

    async def _generate_function_data(self, config: Dict) -> Any:
        """生成函数数据"""
        from datetime import timedelta
        import math

        function_name = config.get("function", "sine_wave")
        data_points = config.get("data_points", 30)

        if function_name == "sine_wave":
            amplitude = config.get("amplitude", 500)
            period = config.get("period", 86400)
            offset = config.get("offset", 1000)

            now = datetime.now()
            base_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elapsed_seconds = (now - base_time).total_seconds()

            data = []
            for i in range(data_points):
                t = elapsed_seconds - (i * (period / data_points))
                value = offset + amplitude * math.sin(2 * math.pi * t / period)
                data.append({
                    "timestamp": (now - timedelta(seconds=i * (period / data_points))).isoformat(),
                    "value": value
                })

            return data
        else:
            logger.warning(f"未知的函数类型: {function_name}")
            return None
