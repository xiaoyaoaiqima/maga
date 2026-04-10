"""
ExpertTask service - Business logic for expert_task operations
"""
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expert_task import ExpertTask
from app.schemas.expert_task import ExpertTaskCreate, ExpertTaskUpdate


class ExpertTaskService:
    """ExpertTask service"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get(self, expert_task_id: int) -> Optional[ExpertTask]:
        """Get expert_task by ID"""
        result = await self.db.execute(
            select(ExpertTask).where(
                ExpertTask.id == expert_task_id,
                ExpertTask.is_deleted == 0
            )
        )
        return result.scalar_one_or_none()
    
    async def get_by_job_id(self, job_id: str) -> List[ExpertTask]:
        """Get expert_tasks by job_id"""
        result = await self.db.execute(
            select(ExpertTask).where(
                ExpertTask.job_id == job_id,
                ExpertTask.is_deleted == 0
            )
        )
        return list(result.scalars().all())
    
    async def list(
        self,
        job_id: Optional[str] = None,
        expert_config_code: Optional[str] = None,
        status: Optional[int] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[ExpertTask]:
        """List expert_tasks with optional filters"""
        query = select(ExpertTask).where(ExpertTask.is_deleted == 0)
        
        if job_id:
            query = query.where(ExpertTask.job_id == job_id)
        if expert_config_code:
            query = query.where(ExpertTask.expert_config_code == expert_config_code)
        if status is not None:
            query = query.where(ExpertTask.status == status)
        
        result = await self.db.execute(query.offset(skip).limit(limit))
        return list(result.scalars().all())
    
    async def create(self, expert_task_in: ExpertTaskCreate) -> ExpertTask:
        """Create expert_task"""
        expert_task = ExpertTask(**expert_task_in.model_dump())
        self.db.add(expert_task)
        await self.db.commit()
        await self.db.refresh(expert_task)
        return expert_task
    
    async def update(
        self,
        expert_task_id: int,
        expert_task_in: ExpertTaskUpdate
    ) -> Optional[ExpertTask]:
        """Update expert_task"""
        expert_task = await self.get(expert_task_id)
        if not expert_task:
            return None
        
        update_data = expert_task_in.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(expert_task, field, value)
        
        await self.db.commit()
        await self.db.refresh(expert_task)
        return expert_task
    
    async def delete(self, expert_task_id: int) -> bool:
        """Soft delete expert_task"""
        expert_task = await self.get(expert_task_id)
        if not expert_task:
            return False
        
        expert_task.is_deleted = 1
        await self.db.commit()
        return True

