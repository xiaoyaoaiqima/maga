"""
CalibrationTaskService - 校准任务服务
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calibration_task import CalibrationTask
from app.models.calibration_record import CalibrationRecord
from app.schemas.calibration_task import CalibrationTaskCreate, CalibrationTaskUpdate


class CalibrationTaskService:
    """校准任务服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_task(
        self,
        payload: CalibrationTaskCreate,
        creator_id: str,
        creator_name: Optional[str],
        assignee_id: Optional[str],
        assignee_name: Optional[str],
    ) -> CalibrationTask:
        task_name = payload.task_name or f"校准任务-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        task = CalibrationTask(
            task_code=payload.task_code,
            task_name=task_name,
            status="PENDING",
            assignee_id=assignee_id,
            assignee_name=assignee_name,
            due_time=payload.due_time,
            remark=payload.remark,
            created_by=creator_id,
            created_name=creator_name,
        )
        self.db.add(task)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def update_task(
        self,
        task_id: int,
        payload: CalibrationTaskUpdate,
    ) -> Optional[CalibrationTask]:
        result = await self.db.execute(
            select(CalibrationTask).where(CalibrationTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            return None

        updates = payload.model_dump(exclude_unset=True)
        status = updates.get("status")
        if status == "IN_PROGRESS" and not updates.get("start_time") and not task.start_time:
            updates["start_time"] = datetime.now()
        if status == "DONE" and not updates.get("finish_time") and not task.finish_time:
            updates["finish_time"] = datetime.now()
        for field, value in updates.items():
            setattr(task, field, value)

        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def list_tasks(
        self,
        assignee_id: Optional[str] = None,
        status: Optional[str] = None,
        expert_config_code: Optional[str] = None,
        skip: int = 0,
        limit: int = 1000,
    ) -> List[CalibrationTask]:
        stmt = select(CalibrationTask)
        if assignee_id:
            stmt = stmt.where(CalibrationTask.assignee_id == assignee_id)
        if status:
            stmt = stmt.where(CalibrationTask.status == status)
        if expert_config_code:
            # Subquery to find task IDs that have records for this expert
            record_subq = select(CalibrationRecord.calibration_task_id).where(
                CalibrationRecord.expert_config_code == expert_config_code
            ).distinct().subquery()
            stmt = stmt.where(CalibrationTask.id.in_(record_subq))

        stmt = stmt.order_by(desc(CalibrationTask.create_time)).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
