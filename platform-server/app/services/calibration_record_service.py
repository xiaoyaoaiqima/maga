"""
CalibrationRecordService - 校准工作台记录服务
"""
from typing import List, Optional

from sqlalchemy import select, desc, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calibration_record import CalibrationRecord
from app.schemas.calibration_record import CalibrationRecordCreate


class CalibrationRecordService:
    """校准工作台记录服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_records(
        self,
        records: List[CalibrationRecordCreate],
        reviewer_id: str,
        reviewer_name: Optional[str],
    ) -> List[CalibrationRecord]:
        if not records:
            return []

        key_fields = (
            CalibrationRecord.calibration_task_id,
            CalibrationRecord.reviewer_id,
            CalibrationRecord.expert_config_code,
            CalibrationRecord.content_id,
        )
        key_values = {
            (
                item.calibration_task_id,
                reviewer_id,
                item.expert_config_code,
                item.content_id,
            )
            for item in records
        }

        existing_map = {}
        if key_values:
            stmt = select(CalibrationRecord).where(tuple_(*key_fields).in_(list(key_values)))
            result = await self.db.execute(stmt)
            for record in result.scalars().all():
                key = (
                    record.calibration_task_id,
                    record.reviewer_id,
                    record.expert_config_code,
                    record.content_id,
                )
                existing_map[key] = record

        entities: List[CalibrationRecord] = []
        for item in records:
            key = (
                item.calibration_task_id,
                reviewer_id,
                item.expert_config_code,
                item.content_id,
            )
            record = existing_map.get(key)
            if record:
                record.content_row_id = item.content_row_id
                record.job_id = item.job_id
                record.sub_job_id = item.sub_job_id
                record.expert_func = item.expert_func
                record.expert_type = item.expert_type
                record.human_score_value = item.human_score_value
                record.human_passed = item.human_passed
                record.remark = item.remark
                record.reviewer_name = reviewer_name
            else:
                record = CalibrationRecord(
                    calibration_task_id=item.calibration_task_id,
                    content_row_id=item.content_row_id,
                    content_id=item.content_id,
                    job_id=item.job_id,
                    sub_job_id=item.sub_job_id,
                    expert_config_code=item.expert_config_code,
                    expert_func=item.expert_func,
                    expert_type=item.expert_type,
                    human_score_value=item.human_score_value,
                    human_passed=item.human_passed,
                    remark=item.remark,
                    reviewer_id=reviewer_id,
                    reviewer_name=reviewer_name,
                )
                self.db.add(record)
                existing_map[key] = record
            entities.append(record)

        await self.db.flush()
        await self.db.commit()
        refreshed_ids = set()
        for entity in entities:
            entity_id = id(entity)
            if entity_id not in refreshed_ids:
                await self.db.refresh(entity)
                refreshed_ids.add(entity_id)
        return list({id(item): item for item in entities}.values())

    async def list_records(
        self,
        calibration_task_id: Optional[int] = None,
        content_ids: Optional[List[str]] = None,
        expert_config_codes: Optional[List[str]] = None,
        reviewer_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 1000,
    ) -> List[CalibrationRecord]:
        from app.models.critic_score_record import CriticScoreRecord
        from sqlalchemy import func

        # 1. 查询 calibration_record（人工评分记录）
        stmt = select(CalibrationRecord)

        if calibration_task_id:
            stmt = stmt.where(CalibrationRecord.calibration_task_id == calibration_task_id)
        if content_ids:
            stmt = stmt.where(CalibrationRecord.content_id.in_(content_ids))
        if expert_config_codes:
            stmt = stmt.where(CalibrationRecord.expert_config_code.in_(expert_config_codes))
        if reviewer_id:
            stmt = stmt.where(CalibrationRecord.reviewer_id == reviewer_id)

        stmt = stmt.order_by(desc(CalibrationRecord.create_time)).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        records = list(result.scalars().all())

        # 2. 如果没有记录，直接返回
        if not records:
            return []

        # 3. 收集所有 content_id 和 expert_config_code（用于关联 AI 评分）
        content_id_set = {r.content_id for r in records}
        expert_code_set = {r.expert_config_code for r in records}

        # 4. 子查询：获取每个 (content_id, expert_config_code) 组合的最大 version
        max_version_subq = (
            select(
                CriticScoreRecord.content_id,
                CriticScoreRecord.expert_config_code,
                func.max(CriticScoreRecord.version).label('max_version'),
            )
            .where(
                CriticScoreRecord.content_id.in_(list(content_id_set)),
                CriticScoreRecord.expert_config_code.in_(list(expert_code_set)),
                CriticScoreRecord.source_type == 'job',
            )
            .group_by(CriticScoreRecord.content_id, CriticScoreRecord.expert_config_code)
            .subquery()
        )

        # 5. 主查询：关联获取最新版本的 AI 评分记录
        critic_stmt = (
            select(
                CriticScoreRecord.content_id,
                CriticScoreRecord.expert_config_code,
                CriticScoreRecord.score,
                CriticScoreRecord.passed,
                CriticScoreRecord.version,
            )
            .join(
                max_version_subq,
                (CriticScoreRecord.content_id == max_version_subq.c.content_id)
                & (CriticScoreRecord.expert_config_code == max_version_subq.c.expert_config_code)
                & (CriticScoreRecord.version == max_version_subq.c.max_version),
            )
        )

        critic_result = await self.db.execute(critic_stmt)

        # 6. 构建映射表：{(content_id, expert_config_code): (score, passed, version)}
        critic_map = {}
        for row in critic_result.all():
            key = (row.content_id, row.expert_config_code)
            # passed 字段：1=通过, 0=不通过, 转换为 bool
            critic_map[key] = (row.score, row.passed == 1, row.version)

        # 7. 将 AI 评分附加到 CalibrationRecord 对象（使用 setattr 动态添加）
        for record in records:
            key = (record.content_id, record.expert_config_code)
            if key in critic_map:
                ai_score, ai_passed, ai_version = critic_map[key]
                setattr(record, 'ai_score', ai_score)
                setattr(record, 'ai_passed', ai_passed)
                setattr(record, 'ai_score_version', ai_version)
            else:
                # 没有对应的 AI 评分记录
                setattr(record, 'ai_score', None)
                setattr(record, 'ai_passed', None)
                setattr(record, 'ai_score_version', None)

        return records
