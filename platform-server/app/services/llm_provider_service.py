import re
import httpx
import os
import json
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func, update, delete, and_, or_

from app.core.logger import logger
from app.models.llm_provider_config import LLMProviderConfig
from app.models.llm_model_route import LLMModelRoute
from app.models.llm_circuit_breaker import LLMCircuitBreaker
from app.schemas.llm_provider import (
    LLMProviderConfigCreate, LLMProviderConfigUpdate, 
    LLMModelRouteCreate, LLMModelRouteUpdate
)
from app.constants.model_pricing import get_model_price_reference

# ==================== LLM Provider Service ====================

class LLMProviderService:
    """LLM 提供商配置服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self, 
        skip: int = 0, 
        limit: int = 100,
        enabled: Optional[bool] = None,
        provider_type: Optional[str] = None
    ) -> Tuple[List[LLMProviderConfig], int]:
        """获取 Provider 列表"""
        stmt = select(LLMProviderConfig).where(LLMProviderConfig.is_deleted == 0)
        
        if enabled is not None:
            stmt = stmt.where(LLMProviderConfig.enabled == (1 if enabled else 0))
        if provider_type:
            stmt = stmt.where(LLMProviderConfig.provider_type == provider_type)
            
        stmt = stmt.order_by(LLMProviderConfig.priority.desc()).offset(skip).limit(limit)
        
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        
        # Count
        count_stmt = select(func.count()).select_from(LLMProviderConfig).where(LLMProviderConfig.is_deleted == 0)
        if enabled is not None:
            count_stmt = count_stmt.where(LLMProviderConfig.enabled == (1 if enabled else 0))
        if provider_type:
            count_stmt = count_stmt.where(LLMProviderConfig.provider_type == provider_type)
            
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        return items, total

    async def get_by_code(self, code: str) -> Optional[LLMProviderConfig]:
        """根据编码获取 Provider"""
        result = await self.db.execute(
            select(LLMProviderConfig).where(
                LLMProviderConfig.provider_code == code,
                LLMProviderConfig.is_deleted == 0
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: LLMProviderConfigCreate) -> LLMProviderConfig:
        """创建 Provider"""
        # 检查重复
        existing = await self.get_by_code(data.provider_code)
        if existing:
            raise ValueError(f"Provider code '{data.provider_code}' already exists")
            
        db_obj = LLMProviderConfig(**data.model_dump())
        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj

    async def update(self, code: str, data: LLMProviderConfigUpdate) -> Optional[LLMProviderConfig]:
        """更新 Provider"""
        db_obj = await self.get_by_code(code)
        if not db_obj:
            return None
            
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
            
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj

    async def delete(self, code: str) -> bool:
        """删除 Provider (软删除)"""
        db_obj = await self.get_by_code(code)
        if not db_obj:
            return False
            
        db_obj.is_deleted = int(datetime.now().timestamp())
        await self.db.commit()
        return True

    async def get_with_decrypted_key(self, code: str) -> Optional[Dict[str, Any]]:
        """获取包含解密后 API Key 的配置 (仅内部使用)"""
        db_obj = await self.get_by_code(code)
        if not db_obj:
            return None
            
        config = {
            "provider_code": db_obj.provider_code,
            "provider_name": db_obj.provider_name,
            "provider_type": db_obj.provider_type,
            "base_url": db_obj.base_url,
            "api_key": db_obj.api_key,  # 目前暂未实现加密，直接返回
            "default_model": db_obj.default_model,
            "available_models": db_obj.available_models,
            "default_params": db_obj.default_params,
            "timeout": db_obj.timeout,
            "priority": db_obj.priority,
        }
        return config


# ==================== LLM Model Route Service ====================

class LLMModelRouteService:
    """模型路由服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        model_code: Optional[str] = None,
        provider_code: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Tuple[List[LLMModelRoute], int]:
        """获取路由列表"""
        stmt = select(LLMModelRoute).where(LLMModelRoute.is_deleted == 0)
        
        if model_code:
            stmt = stmt.where(LLMModelRoute.model_code == model_code)
        if provider_code:
            stmt = stmt.where(LLMModelRoute.provider_code == provider_code)
        if enabled is not None:
            stmt = stmt.where(LLMModelRoute.enabled == (1 if enabled else 0))
            
        stmt = stmt.order_by(LLMModelRoute.priority.desc()).offset(skip).limit(limit)
        
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        
        # Count
        count_stmt = select(func.count()).select_from(LLMModelRoute).where(LLMModelRoute.is_deleted == 0)
        if model_code:
            count_stmt = count_stmt.where(LLMModelRoute.model_code == model_code)
        if provider_code:
            count_stmt = count_stmt.where(LLMModelRoute.provider_code == provider_code)
        if enabled is not None:
            count_stmt = count_stmt.where(LLMModelRoute.enabled == (1 if enabled else 0))
            
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        return items, total

    async def list_available_models(self) -> List[Dict[str, Any]]:
        """获取所有可用模型（聚合视图）"""
        result = await self.db.execute(
            select(
                LLMModelRoute.model_code,
                LLMModelRoute.model_name,
                func.max(LLMModelRoute.max_context_length).label("max_context_length"),
                func.max(LLMModelRoute.cost_per_1k_input).label("cost_per_1k_input"),
                func.max(LLMModelRoute.cost_per_1k_output).label("cost_per_1k_output"),
                func.max(LLMModelRoute.currency).label("currency"),
            )
            .where(
                LLMModelRoute.enabled == 1,
                LLMModelRoute.is_deleted == 0
            )
            .group_by(LLMModelRoute.model_code, LLMModelRoute.model_name)
        )
        
        models = []
        for row in result:
            # 获取该模型的所有 provider
            providers_result = await self.db.execute(
                select(LLMModelRoute.provider_code)
                .where(
                    LLMModelRoute.model_code == row.model_code,
                    LLMModelRoute.enabled == 1,
                    LLMModelRoute.is_deleted == 0
                )
            )
            providers = [p[0] for p in providers_result]
            
            models.append({
                "model_code": row.model_code,
                "model_name": row.model_name,
                "providers": providers,
                "max_context_length": row.max_context_length,
                "cost_per_1k_input": float(row.cost_per_1k_input) if row.cost_per_1k_input is not None else None,
                "cost_per_1k_output": float(row.cost_per_1k_output) if row.cost_per_1k_output is not None else None,
                "currency": row.currency,
            })
        
        return models

    async def create(self, data: LLMModelRouteCreate) -> LLMModelRoute:
        """创建路由"""
        db_obj = LLMModelRoute(**data.model_dump())
        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj

    async def update(self, route_id: int, data: LLMModelRouteUpdate) -> Optional[LLMModelRoute]:
        """更新路由"""
        result = await self.db.execute(
            select(LLMModelRoute).where(LLMModelRoute.id == route_id)
        )
        db_obj = result.scalar_one_or_none()
        if not db_obj:
            return None
            
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
            
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj

    async def delete(self, route_id: int) -> bool:
        """删除路由"""
        result = await self.db.execute(
            select(LLMModelRoute).where(LLMModelRoute.id == route_id)
        )
        db_obj = result.scalar_one_or_none()
        if not db_obj:
            return False
            
        db_obj.is_deleted = int(datetime.now().timestamp())
        await self.db.commit()
        return True

    async def sync_aliyun_prices(self) -> Dict[str, Any]:
        """
        从阿里云百炼定价页面 API 自动同步模型价格
        """
        try:
            pricing_map = await self.get_aliyun_pricing_map()
            if not pricing_map:
                return {"success": False, "message": "未能从 API 获取到内容"}

            # 1. 首先将所有 aliyun provider 的币种统一设置为 CNY
            await self.db.execute(
                text("UPDATE llm_model_route SET currency = 'CNY' WHERE provider_code = 'aliyun' AND is_deleted = 0")
            )

            total_updated = 0
            updated_models = []

            for model_name, (input_p, output_p) in pricing_map.items():
                result = await self.db.execute(
                    text("""
                        UPDATE llm_model_route 
                        SET cost_per_1k_input = :input_p, 
                            cost_per_1k_output = :output_p,
                            currency = 'CNY'
                        WHERE provider_code = 'aliyun' 
                          AND (provider_model = :model OR provider_model LIKE :model_prefix)
                          AND is_deleted = 0
                    """),
                    {
                        "input_p": input_p,
                        "output_p": output_p,
                        "model": model_name,
                        "model_prefix": f"{model_name}%"
                    }
                )
                
                if result.rowcount > 0:
                    total_updated += result.rowcount
                    updated_models.append(model_name)

            await self.db.commit()
            return {
                "success": True, 
                "total_updated": total_updated,
                "updated_models": list(set(updated_models))
            }

        except Exception as e:
            logger.error(f"[AliyunSync] 同步失败: {str(e)}")
            return {"success": False, "message": str(e)}

    async def get_aliyun_pricing_map(self) -> Dict[str, Tuple[Decimal, Decimal]]:
        """
        从阿里云官网爬取并解析模型价格映射表
        返回格式: { "model_name": (input_price, output_price) }
        """
        url = "https://help.aliyun.com/help/json/document_detail.json?alias=%2Fmodel-studio%2Fmodel-pricing"
        pricing_map = {}
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            
            content = data.get("data", {}).get("content", "")
            if not content:
                return {}

            # 提取 <tr> 内容
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", content, re.DOTALL)
            
            last_model_id = ""
            
            for row in rows:
                # 过滤掉非推理计费相关的行
                if any(k in row for k in ["训练", "调优", "部署", "按时"]):
                    continue

                # 提取单元格文本
                cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
                texts = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
                texts = [t for t in texts if t]
                if not texts:
                    continue
                
                # 1. 识别模型名/ID
                model_id = ""
                # 优先寻找括号内的英文 ID
                for t in texts:
                    id_match = re.search(r"\(([a-z0-9\-\.\_]+)\)", t)
                    if id_match:
                        model_id = id_match.group(1)
                        break
                
                if not model_id:
                    for t in texts:
                        t_lower = t.lower()
                        # 排除掉表头
                        if "模型名称" in t:
                            break
                        if any(k in t_lower for k in ["qwen", "deepseek", "vl-", "llama", "qwq", "qvq", "gui-"]):
                            # 取第一段非中文字符串作为 ID 备选
                            parts = re.split(r"[\u4e00-\u9fa5\s]+", t)
                            candidates = [p for p in parts if p and not p.startswith("(")]
                        if candidates:
                            model_id = candidates[0].strip("() ")
                            # 进一步清理 ID：去掉 Batch 等后缀，确保与 API 返回的 model_id 一致
                            model_id = re.sub(r"Batch$", "", model_id, flags=re.IGNORECASE)
                        break

                # 关键修复：处理 rowspan 导致的 model_id 缺失
                if not model_id:
                    model_id = last_model_id
                else:
                    last_model_id = model_id
                
                if not model_id:
                    continue
                
                # 2. 识别价格
                # 阿里云百炼定价页面表头已明确单位为“每千 Token”，因此直接提取数值即可
                prices = []
                for t in texts:
                    if "元" in t:
                        # 清理文本：去掉干扰性的单位数字
                        clean_t = t.replace(",", "")
                        # 去掉 1000, 1000000 等，但保留小数点
                        clean_t = re.sub(r"\b(1000|1000000|100000)\b", "", clean_t)
                        
                        # 提取数值，增加对科学计数法的支持 (如 8E-7)
                        nums = re.findall(r"(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", clean_t)
                        if nums:
                            prices.extend(nums)
                
                if len(prices) >= 2:
                    try:
                        input_p = Decimal(prices[0]).quantize(Decimal("0.0000001"), rounding=ROUND_HALF_UP)
                        output_p = Decimal(prices[1]).quantize(Decimal("0.0000001"), rounding=ROUND_HALF_UP)
                        
                        # 价格合理性检查：单价通常不会超过 1 元/k tokens (除了极个别极昂贵模型)
                        if input_p > 10:
                            continue

                        # 策略：保留第一个抓取到的非零价格（通常是基础档位）
                        # 移除自动添加 -latest 后缀的逻辑，因为 sync_models 已经有更灵活的后缀匹配逻辑
                        if model_id not in pricing_map or (pricing_map[model_id][0] == 0 and input_p > 0):
                            pricing_map[model_id] = (input_p, output_p)
                    except Exception:
                        pass
            
            return pricing_map
        except Exception as e:
            logger.error(f"[AliyunPricing] 抓取失败: {e}")
            return {}


# ==================== LLM Circuit Breaker Service ====================

class LLMCircuitBreakerService:
    """熔断状态服务"""
    
    FAILURE_THRESHOLD = 3
    RECOVERY_TIMEOUT = 60
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_status(self, provider_code: str) -> Optional[LLMCircuitBreaker]:
        """获取熔断状态"""
        result = await self.db.execute(
            select(LLMCircuitBreaker).where(
                LLMCircuitBreaker.provider_code == provider_code
            )
        )
        return result.scalar_one_or_none()
    
    async def list_all(self) -> List[LLMCircuitBreaker]:
        """获取所有熔断状态"""
        result = await self.db.execute(select(LLMCircuitBreaker))
        return list(result.scalars().all())
    
    async def is_open(self, provider_code: str) -> bool:
        """检查是否熔断中"""
        status = await self.get_status(provider_code)
        if not status:
            return False
        
        if status.state == "open":
            if status.open_until and datetime.now() > status.open_until:
                await self._set_state(provider_code, "half_open")
                return False
            return True
        
        return False
    
    async def record_success(self, provider_code: str):
        """记录成功"""
        status = await self.get_status(provider_code)
        
        if not status:
            status = LLMCircuitBreaker(
                provider_code=provider_code,
                state="closed",
                failure_count=0,
                success_count=1,
            )
            self.db.add(status)
            await self.db.commit()
            return
        
        if status.state == "half_open":
            status.state = "closed"
            status.failure_count = 0
            status.success_count = status.success_count + 1
        elif status.state == "closed":
            status.failure_count = 0
            status.success_count = status.success_count + 1
        
        await self.db.commit()
    
    async def record_failure(self, provider_code: str, reason: str):
        """记录失败"""
        status = await self.get_status(provider_code)
        
        if not status:
            status = LLMCircuitBreaker(
                provider_code=provider_code,
                state="closed",
                failure_count=1,
                success_count=0,
                last_failure_time=datetime.now(),
                last_failure_reason=reason[:256] if reason else None,
            )
            self.db.add(status)
            await self.db.commit()
            return
        
        status.failure_count += 1
        status.last_failure_time = datetime.now()
        status.last_failure_reason = reason[:256] if reason else None
        
        if status.state == "half_open":
            status.state = "open"
            status.open_until = datetime.now() + timedelta(seconds=self.RECOVERY_TIMEOUT)
        elif status.failure_count >= self.FAILURE_THRESHOLD:
            status.state = "open"
            status.open_until = datetime.now() + timedelta(seconds=self.RECOVERY_TIMEOUT)
        
        await self.db.commit()
    
    async def reset(self, provider_code: str) -> bool:
        """重置熔断状态"""
        status = await self.get_status(provider_code)
        if not status:
            return False
        
        status.state = "closed"
        status.failure_count = 0
        status.success_count = 0
        status.open_until = None
        
        await self.db.commit()
        return True
    
    async def force_open(self, provider_code: str, reason: str = "Manual intervention") -> bool:
        """强制熔断"""
        status = await self.get_status(provider_code)
        
        if not status:
            status = LLMCircuitBreaker(
                provider_code=provider_code,
                state="open",
                failure_count=0,
                success_count=0,
                last_failure_reason=reason,
                open_until=datetime.now() + timedelta(days=365),
            )
            self.db.add(status)
        else:
            status.state = "open"
            status.last_failure_reason = reason
            status.open_until = datetime.now() + timedelta(days=365)
        
        await self.db.commit()
        return True

    async def update_state(
        self,
        provider_code: str,
        state: str,
        failure_count: int = 0,
        last_failure_reason: str = None,
    ):
        """更新熔断状态"""
        status = await self.get_status(provider_code)
        
        if not status:
            status = LLMCircuitBreaker(
                provider_code=provider_code,
                state=state,
                failure_count=failure_count,
                success_count=0,
                last_failure_reason=last_failure_reason[:256] if last_failure_reason else None,
                last_failure_time=datetime.now() if state != "closed" else None,
            )
            self.db.add(status)
        else:
            status.state = state
            status.failure_count = failure_count
            if last_failure_reason:
                status.last_failure_reason = last_failure_reason[:256]
                status.last_failure_time = datetime.now()
            
            if state == "open":
                status.open_until = datetime.now() + timedelta(seconds=self.RECOVERY_TIMEOUT)
            elif state == "closed":
                status.open_until = None
        
        await self.db.commit()

    async def _set_state(self, provider_code: str, state: str):
        """设置状态内部方法"""
        status = await self.get_status(provider_code)
        if status:
            status.state = state
            if state == "half_open":
                status.success_count = 0
            await self.db.commit()
