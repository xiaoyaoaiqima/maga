"""
批量创建服务 - 优化第一次启动时的数据库写入性能

使用批量插入代替单条插入，减少数据库往返次数。
"""
from typing import List, Dict, Any
from logging import getLogger
from datetime import datetime

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sub_job import SubJob
from app.models.content import Content
from app.models.expert_business_result import ExpertBusinessResult

logger = getLogger(__name__)


class BatchCreateService:
    """批量创建服务"""
    
    @staticmethod
    async def batch_create_sub_jobs(
        db: AsyncSession,
        job_id: str,
        plan_indexes: List[int],
        expert_config_code: str,
        expert_list: List[str],
    ) -> List[Dict[str, Any]]:
        """
        批量创建 SubJob 记录
        
        Args:
            db: 数据库会话
            job_id: Job ID
            plan_indexes: 槽位索引列表
            expert_config_code: Expert 配置代码
            expert_list: Expert 列表
        
        Returns:
            创建的 SubJob 列表（包含 sub_job_id、content_id 等）
        """
        import uuid
        
        now = datetime.now()
        sub_jobs_data = []
        
        # 准备批量数据
        for plan_index in plan_indexes:
            sub_job_id = f"gen-{uuid.uuid4().hex[:16]}"
            content_id = f"content-{uuid.uuid4().hex[:16]}"
            
            sub_jobs_data.append({
                "job_id": job_id,
                "sub_job_id": sub_job_id,
                "content_id": content_id,
                "expert_list": expert_list,
                "expert_complete_list": [],
                "status": "RUNNING",
                "plan_index": plan_index,
                "is_deleted": 0,
                "create_time": now,
                "update_time": now,
            })
        
        # 批量插入
        try:
            await db.execute(insert(SubJob), sub_jobs_data)
            await db.commit()
            
            logger.info(f"[BatchCreate] Created {len(sub_jobs_data)} SubJobs for job_id={job_id}")
            return sub_jobs_data
            
        except Exception as e:
            await db.rollback()
            logger.error(f"[BatchCreate] Failed to batch create SubJobs: {e}")
            raise
    
    @staticmethod
    async def batch_create_contents(
        db: AsyncSession,
        contents_data: List[Dict[str, Any]],
    ) -> None:
        """
        批量创建 Content 记录
        
        Args:
            db: 数据库会话
            contents_data: Content 数据列表
        """
        if not contents_data:
            return
        
        try:
            await db.execute(insert(Content), contents_data)
            await db.commit()
            
            logger.info(f"[BatchCreate] Created {len(contents_data)} Contents")
            
        except Exception as e:
            await db.rollback()
            logger.error(f"[BatchCreate] Failed to batch create Contents: {e}")
            raise
    
    @staticmethod
    async def batch_create_business_results(
        db: AsyncSession,
        results_data: List[Dict[str, Any]],
    ) -> None:
        """
        批量创建 ExpertBusinessResult 记录
        
        Args:
            db: 数据库会话
            results_data: ExpertBusinessResult 数据列表
        """
        if not results_data:
            return
        
        try:
            await db.execute(insert(ExpertBusinessResult), results_data)
            await db.commit()
            
            logger.info(f"[BatchCreate] Created {len(results_data)} ExpertBusinessResults")
            
        except Exception as e:
            await db.rollback()
            logger.error(f"[BatchCreate] Failed to batch create ExpertBusinessResults: {e}")
            raise
