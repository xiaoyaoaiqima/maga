"""
SubJob, Content, ExpertBusinessResult 服务

v2 重构：
- 新增 update_plugin_snapshots 方法
- 新增 get_plugin_snapshot 方法
"""
from typing import Optional, List, Dict, Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.sub_job import SubJob
from app.models.content import Content
from app.models.expert_business_result import ExpertBusinessResult
from app.schemas.sub_job import SubJobCreate, SubJobUpdate
from app.schemas.content import ContentCreate, ContentUpdate
from app.schemas.expert_business_result import ExpertBusinessResultCreate


class SubJobService:
    """SubJob 服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ==================== SubJob 操作 ====================
    
    async def create_sub_job(self, data: SubJobCreate) -> SubJob:
        """创建 SubJob"""
        return await self.create_sub_job_with_options(data, auto_commit=True)

    async def create_sub_job_with_options(
        self,
        data: SubJobCreate,
        *,
        auto_commit: bool = True,
    ) -> SubJob:
        """创建 SubJob，可选择是否立即提交事务。"""
        from datetime import datetime
        
        sub_job_dict = data.model_dump()
        # 显式设置创建时间和更新时间，避免依赖数据库默认值
        if 'create_time' not in sub_job_dict or sub_job_dict['create_time'] is None:
            sub_job_dict['create_time'] = datetime.now()
        if 'update_time' not in sub_job_dict or sub_job_dict['update_time'] is None:
            sub_job_dict['update_time'] = datetime.now()
        
        sub_job = SubJob(**sub_job_dict)
        self.db.add(sub_job)
        if auto_commit:
            await self.db.commit()
            await self.db.refresh(sub_job)
        else:
            await self.db.flush()
        return sub_job
    
    async def get_sub_job(
        self, 
        job_id: str, 
        sub_job_id: str, 
        content_id: str
    ) -> Optional[SubJob]:
        """根据 job_id, sub_job_id, content_id 获取 SubJob"""
        result = await self.db.execute(
            select(SubJob).where(
                SubJob.job_id == job_id,
                SubJob.sub_job_id == sub_job_id,
                SubJob.content_id == content_id
            )
        )
        return result.scalar_one_or_none()
    
    async def get_sub_job_by_sub_job_id(self, sub_job_id: str) -> Optional[SubJob]:
        """根据 sub_job_id 获取 SubJob"""
        result = await self.db.execute(
            select(SubJob).where(SubJob.sub_job_id == sub_job_id)
        )
        return result.scalar_one_or_none()
    
    async def update_sub_job(
        self,
        sub_job_id: str,
        data: SubJobUpdate
    ) -> Optional[SubJob]:
        """更新 SubJob"""
        sub_job = await self.get_sub_job_by_sub_job_id(sub_job_id)
        if not sub_job:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(sub_job, field, value)
        
        await self.db.commit()
        await self.db.refresh(sub_job)
        return sub_job
    
    async def add_expert_complete(
        self,
        sub_job_id: str,
        expert_config_code: str,
        *,
        auto_commit: bool = True,
    ) -> Optional[SubJob]:
        """添加已完成的 expert_config_code 到列表"""
        from app.core.logger import logger
        from sqlalchemy.exc import SQLAlchemyError
        import asyncio
        
        sub_job = await self.get_sub_job_by_sub_job_id(sub_job_id)
        if not sub_job:
            return None
        
        # 获取现有列表并创建新列表
        complete_list = list(sub_job.expert_complete_list or [])
        if expert_config_code not in complete_list:
            complete_list.append(expert_config_code)
        
        # 赋值新列表
        sub_job.expert_complete_list = complete_list
        # 显式标记 JSON 字段已修改，确保 SQLAlchemy 检测到变化
        flag_modified(sub_job, "expert_complete_list")
        
        # ✅ 增强：添加异常处理和超时保护
        try:
            # 使用 asyncio.wait_for 防止 commit/refresh hang
            if auto_commit:
                await asyncio.wait_for(self.db.commit(), timeout=10.0)
                await asyncio.wait_for(self.db.refresh(sub_job), timeout=5.0)
            else:
                await asyncio.wait_for(self.db.flush(), timeout=10.0)
            return sub_job
        except asyncio.TimeoutError:
            logger.error(f"[SubJobService] add_expert_complete timeout for sub_job={sub_job_id}, expert={expert_config_code}")
            # 超时时尝试回滚
            try:
                await self.db.rollback()
            except Exception:
                pass
            # 返回未刷新的对象（总比hang好）
            return sub_job
        except SQLAlchemyError as e:
            logger.error(f"[SubJobService] Database error in add_expert_complete: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            raise  # 重新抛出让上层处理
        except Exception as e:
            logger.error(f"[SubJobService] Unexpected error in add_expert_complete: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            raise
    
    async def complete_sub_job(
        self,
        sub_job_id: str,
        status: str = "COMPLETED",
        *,
        auto_commit: bool = True,
    ) -> Optional[SubJob]:
        """完成 SubJob"""
        sub_job = await self.get_sub_job_by_sub_job_id(sub_job_id)
        if not sub_job:
            return None
        
        sub_job.status = status
        if auto_commit:
            await self.db.commit()
            await self.db.refresh(sub_job)
        else:
            await self.db.flush()

        # ❌ BUG: 不应该释放槽位！plan_index 槽位代表"生成的第几篇文章"，一旦被占用应该永久占用
        # 释放槽位会导致同一 plan_index 被重复执行，造成文章分布不均
        # if status in ("COMPLETED", "FAILED"):
        #     try:
        #         from app.services.slot_status_cache_service import SlotStatusCacheService
        #         job_id = sub_job.job_id
        #         plan_index = sub_job.plan_index
        #         await SlotStatusCacheService.mark_slot_released(job_id, plan_index)
        #         logger.info(f"[SubJobService] Released slot {plan_index} for job_id={job_id} (status={status})")
        #     except Exception as e:
        #         logger.warning(f"[SubJobService] Failed to release slot: {e}")

        return sub_job
    
    # ========== v2 新增：插件快照管理 ==========
    
    async def update_plugin_snapshots(
        self,
        sub_job_id: str,
        plugin_snapshots: Dict[str, Any],
        *,
        auto_commit: bool = True,
    ) -> Optional[SubJob]:
        """
        更新 SubJob 的插件快照
        
        Args:
            sub_job_id: SubJob ID
            plugin_snapshots: 插件快照，格式: {plugin_code: {变量名: {...}}}
        
        Returns:
            更新后的 SubJob
        """
        sub_job = await self.get_sub_job_by_sub_job_id(sub_job_id)
        if not sub_job:
            return None
        
        sub_job.plugin_snapshots = plugin_snapshots
        flag_modified(sub_job, "plugin_snapshots")
        
        if auto_commit:
            await self.db.commit()
            await self.db.refresh(sub_job)
        else:
            await self.db.flush()
        return sub_job
    
    async def set_plugin_snapshot(
        self,
        sub_job_id: str,
        plugin_code: str,
        snapshot: Dict[str, Any],
    ) -> Optional[SubJob]:
        """
        设置单个插件的快照
        
        Args:
            sub_job_id: SubJob ID
            plugin_code: 插件编码
            snapshot: 插件快照
        
        Returns:
            更新后的 SubJob
        """
        sub_job = await self.get_sub_job_by_sub_job_id(sub_job_id)
        if not sub_job:
            return None
        
        if sub_job.plugin_snapshots is None:
            sub_job.plugin_snapshots = {}
        
        sub_job.plugin_snapshots[plugin_code] = snapshot
        flag_modified(sub_job, "plugin_snapshots")
        
        await self.db.commit()
        await self.db.refresh(sub_job)
        return sub_job
    
    async def get_plugin_snapshot(
        self,
        sub_job_id: str,
        plugin_code: str,
    ) -> Optional[Dict[str, Any]]:
        """
        获取单个插件的快照
        
        Args:
            sub_job_id: SubJob ID
            plugin_code: 插件编码
        
        Returns:
            插件快照，不存在则返回 None
        """
        sub_job = await self.get_sub_job_by_sub_job_id(sub_job_id)
        if not sub_job or not sub_job.plugin_snapshots:
            return None
        
        return sub_job.plugin_snapshots.get(plugin_code)
    
    # ==================== Content 操作 ====================
    
    async def create_content(self, data: ContentCreate) -> Content:
        """创建 Content"""
        return await self.create_content_with_options(data, auto_commit=True)

    async def create_content_with_options(
        self,
        data: ContentCreate,
        *,
        auto_commit: bool = True,
    ) -> Content:
        """创建 Content，可选择是否立即提交事务。"""
        from datetime import datetime
        
        content_dict = data.model_dump()
        # 显式设置创建时间和更新时间，避免依赖数据库默认值
        if 'create_time' not in content_dict or content_dict['create_time'] is None:
            content_dict['create_time'] = datetime.now()
        if 'update_time' not in content_dict or content_dict['update_time'] is None:
            content_dict['update_time'] = datetime.now()
        
        content = Content(**content_dict)
        self.db.add(content)
        if auto_commit:
            await self.db.commit()
            await self.db.refresh(content)
        else:
            await self.db.flush()
        return content
    
    async def get_content(
        self,
        job_id: str,
        sub_job_id: str,
        content_id: str
    ) -> Optional[Content]:
        """根据 job_id, sub_job_id, content_id 获取 Content"""
        result = await self.db.execute(
            select(Content).where(
                Content.job_id == job_id,
                Content.sub_job_id == sub_job_id,
                Content.content_id == content_id
            )
        )
        return result.scalar_one_or_none()
    
    async def get_content_by_content_id(self, content_id: str) -> Optional[Content]:
        """根据 content_id 获取 Content"""
        result = await self.db.execute(
            select(Content).where(Content.content_id == content_id)
        )
        return result.scalar_one_or_none()
    
    async def update_content(
        self,
        content_id: str,
        data: ContentUpdate
    ) -> Optional[Content]:
        """更新 Content"""
        content = await self.get_content_by_content_id(content_id)
        if not content:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(content, field, value)
        
        await self.db.commit()
        await self.db.refresh(content)
        return content
    
    async def set_content_valid(
        self,
        content_id: str,
        is_valid: int,
        *,
        auto_commit: bool = True,
    ) -> Optional[Content]:
        """设置 Content 是否有效"""
        content = await self.get_content_by_content_id(content_id)
        if not content:
            return None
        
        content.is_valid = is_valid
        if auto_commit:
            await self.db.commit()
            await self.db.refresh(content)
        else:
            await self.db.flush()
        return content
    
    # ==================== ExpertBusinessResult 操作 ====================
    
    async def create_business_result(
        self,
        data: ExpertBusinessResultCreate,
        *,
        auto_commit: bool = True,
    ) -> ExpertBusinessResult:
        """创建 ExpertBusinessResult"""
        from datetime import datetime
        
        result_dict = data.model_dump()
        # 显式设置创建时间和更新时间，避免依赖数据库默认值
        if 'create_time' not in result_dict or result_dict['create_time'] is None:
            result_dict['create_time'] = datetime.now()
        if 'update_time' not in result_dict or result_dict['update_time'] is None:
            result_dict['update_time'] = datetime.now()
        
        result = ExpertBusinessResult(**result_dict)
        self.db.add(result)
        if auto_commit:
            await self.db.commit()
            await self.db.refresh(result)
        else:
            await self.db.flush()
        return result
    
    async def get_business_results(
        self,
        job_id: str,
        sub_job_id: str,
        content_id: str
    ) -> List[ExpertBusinessResult]:
        """根据 job_id, sub_job_id, content_id 获取所有 ExpertBusinessResult"""
        result = await self.db.execute(
            select(ExpertBusinessResult).where(
                ExpertBusinessResult.job_id == job_id,
                ExpertBusinessResult.sub_job_id == sub_job_id,
                ExpertBusinessResult.content_id == content_id
            ).order_by(ExpertBusinessResult.id.asc())
        )
        return list(result.scalars().all())
    
    async def get_critic_results(
        self,
        job_id: str,
        sub_job_id: str,
        content_id: str
    ) -> List[ExpertBusinessResult]:
        """获取所有 CRITIC 类型的结果"""
        result = await self.db.execute(
            select(ExpertBusinessResult).where(
                ExpertBusinessResult.job_id == job_id,
                ExpertBusinessResult.sub_job_id == sub_job_id,
                ExpertBusinessResult.content_id == content_id,
                ExpertBusinessResult.business_type == "CRITIC"
            ).order_by(ExpertBusinessResult.id.asc())
        )
        return list(result.scalars().all())
