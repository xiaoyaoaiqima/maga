"""
Activity service - 活动服务
"""
from typing import Optional, List, Tuple

from sqlalchemy import select, and_, or_, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.activity import Activity
from app.models.activity_question import ActivityQuestion
from app.models.activity_question_option import ActivityQuestionOption
from app.models.agent import Agent
from app.models.tenant import Tenant
from app.schemas.activity import (
    ActivityCreate,
    ActivityUpdate,
    ActivityResponse,
    ActivityFilters,
    ActivitySimpleItem,
    ActivityStatusUpdate,
    ActivityQuestionCreate,
    ActivityQuestionResponse,
    ActivityQuestionsUpdate,
)
from app.core.logger import logger


class ActivityService:
    """活动服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_activity(self, data: ActivityCreate, created_by: Optional[str] = None) -> ActivityResponse:
        """
        创建活动
        
        Args:
            data: 活动创建数据
            created_by: 创建人
        
        Returns:
            创建的活动
        
        Raises:
            ValueError: 活动编码在同租户下已存在 / 租户不存在
        """
        # 检查租户是否存在
        tenant_stmt = select(Tenant).where(
            and_(
                Tenant.id == data.tenant_id,
                Tenant.is_deleted == 0
            )
        )
        tenant_result = await self.db.execute(tenant_stmt)
        tenant = tenant_result.scalar_one_or_none()
        
        if not tenant:
            raise ValueError(f"租户 ID '{data.tenant_id}' 不存在")
        
        # 检查同租户下活动编码是否已存在
        stmt = select(Activity).where(
            and_(
                Activity.tenant_id == data.tenant_id,
                Activity.activity_code == data.activity_code,
                Activity.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise ValueError(f"活动编码 '{data.activity_code}' 在该租户下已存在")

        # 校验 Agent 列表（可选）
        agent_code_list = getattr(data, "agent_code_list", None) or []
        if agent_code_list:
            await self._validate_agent_codes(agent_code_list, data.tenant_id)
        
        # 创建活动
        activity = Activity(
            activity_code=data.activity_code,
            activity_name=data.activity_name,
            tenant_id=data.tenant_id,
            agent_code_list=agent_code_list if agent_code_list else None,
            channel=data.channel,
            target_audience=data.target_audience,
            budget=data.budget,
            config_json=data.config_json,
            start_time=data.start_time,
            end_time=data.end_time,
            status=data.status,
            remark=data.remark,
            created_by=created_by,
            updated_by=created_by,
        )
        self.db.add(activity)
        await self.db.flush()  # 获取 activity.id
        
        # 创建问题和选项
        questions_data = getattr(data, "questions", None) or []
        if questions_data:
            await self._create_questions(activity.id, questions_data, created_by)
        
        await self.db.commit()
        await self.db.refresh(activity)
        
        logger.info(f"创建活动成功: {activity.activity_code}")
        
        # 构建响应（包含租户名称和问题列表）
        response = await self._build_activity_response(activity, tenant.tenant_name, tenant.tenant_code)
        return response
    
    async def _validate_agent_codes(self, agent_codes: List[str], tenant_id: int) -> None:
        """校验 Agent 编码列表"""
        for agent_code in agent_codes:
            agent_stmt = select(Agent).where(
                and_(
                    Agent.agent_code == agent_code,
                    Agent.is_deleted == 0,
                )
            )
            agent_result = await self.db.execute(agent_stmt)
            agent = agent_result.scalar_one_or_none()
            if not agent:
                raise ValueError(f"Agent 编码 '{agent_code}' 不存在")
            if not agent.enabled:
                raise ValueError(f"Agent 编码 '{agent_code}' 未启用")
            if agent.tenant_id is not None and agent.tenant_id != tenant_id:
                raise ValueError(f"Agent '{agent_code}' 所属租户与活动所属租户不一致（仅允许全局共享或同租户 Agent）")
    
    async def _create_questions(
        self, 
        activity_id: int, 
        questions_data: List[ActivityQuestionCreate],
        created_by: Optional[str] = None
    ) -> List[ActivityQuestion]:
        """创建问题和选项"""
        questions = []
        for idx, q_data in enumerate(questions_data):
            question = ActivityQuestion(
                activity_id=activity_id,
                question_text=q_data.question_text,
                min_select=q_data.min_select,
                max_select=q_data.max_select,
                sort_order=q_data.sort_order if q_data.sort_order else idx,
                created_by=created_by,
                updated_by=created_by,
            )
            self.db.add(question)
            await self.db.flush()
            
            # 创建选项
            for opt_idx, opt_data in enumerate(q_data.options or []):
                option = ActivityQuestionOption(
                    question_id=question.id,
                    display_label=opt_data.display_label,
                    aigc_tag=opt_data.aigc_tag,
                    weight=opt_data.weight,
                    sort_order=opt_data.sort_order if opt_data.sort_order else opt_idx,
                    created_by=created_by,
                    updated_by=created_by,
                )
                self.db.add(option)
            
            questions.append(question)
        
        return questions
    
    async def _build_activity_response(
        self, 
        activity: Activity, 
        tenant_name: Optional[str] = None,
        tenant_code: Optional[str] = None
    ) -> ActivityResponse:
        """构建活动响应（包含问题列表）"""
        # 查询问题和选项
        questions_stmt = (
            select(ActivityQuestion)
            .options(selectinload(ActivityQuestion.options))
            .where(
                and_(
                    ActivityQuestion.activity_id == activity.id,
                    ActivityQuestion.is_deleted == 0
                )
            )
            .order_by(ActivityQuestion.sort_order)
        )
        questions_result = await self.db.execute(questions_stmt)
        questions = questions_result.scalars().all()
        
        # 构建问题响应
        question_responses = []
        for q in questions:
            # 过滤已删除的选项并排序
            options = sorted(
                [opt for opt in q.options if opt.is_deleted == 0],
                key=lambda x: x.sort_order
            )
            q_response = ActivityQuestionResponse(
                id=q.id,
                activity_id=q.activity_id,
                question_text=q.question_text,
                min_select=q.min_select,
                max_select=q.max_select,
                sort_order=q.sort_order,
                enabled=q.enabled,
                options=[{
                    "id": opt.id,
                    "question_id": opt.question_id,
                    "display_label": opt.display_label,
                    "aigc_tag": opt.aigc_tag,
                    "weight": opt.weight,
                    "sort_order": opt.sort_order,
                    "enabled": opt.enabled,
                } for opt in options]
            )
            question_responses.append(q_response)
        
        # 构建活动响应
        response = ActivityResponse(
            id=activity.id,
            activity_code=activity.activity_code,
            activity_name=activity.activity_name,
            tenant_id=activity.tenant_id,
            agent_code_list=activity.agent_code_list,
            channel=activity.channel,
            target_audience=activity.target_audience,
            budget=activity.budget,
            config_json=activity.config_json,
            start_time=activity.start_time,
            end_time=activity.end_time,
            status=activity.status,
            remark=activity.remark,
            enabled=activity.enabled,
            created_by=activity.created_by,
            updated_by=activity.updated_by,
            create_time=activity.create_time,
            update_time=activity.update_time,
            tenant_name=tenant_name,
            tenant_code=tenant_code,
            questions=question_responses,
        )
        return response
    
    async def get_activity(self, activity_id: int) -> Optional[ActivityResponse]:
        """
        获取活动详情
        
        Args:
            activity_id: 活动ID
        
        Returns:
            活动详情，不存在返回 None
        """
        stmt = select(Activity, Tenant.tenant_name, Tenant.tenant_code).join(
            Tenant, Activity.tenant_id == Tenant.id, isouter=True
        ).where(
            and_(
                Activity.id == activity_id,
                Activity.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        row = result.one_or_none()
        
        if not row:
            return None
        
        activity, tenant_name, tenant_code = row
        return await self._build_activity_response(activity, tenant_name, tenant_code)
    
    async def list_activities(self, filters: ActivityFilters) -> Tuple[int, List[ActivityResponse]]:
        """
        获取活动列表
        
        Args:
            filters: 查询过滤条件
        
        Returns:
            (总数, 活动列表)
        """
        # 构建查询条件
        conditions = [Activity.is_deleted == 0]
        
        if filters.tenant_id:
            conditions.append(Activity.tenant_id == filters.tenant_id)
        if filters.activity_code:
            conditions.append(Activity.activity_code.like(f"%{filters.activity_code}%"))
        if filters.activity_name:
            conditions.append(Activity.activity_name.like(f"%{filters.activity_name}%"))
        if filters.channel:
            conditions.append(Activity.channel == filters.channel)
        if filters.status:
            conditions.append(Activity.status == filters.status)
        
        # 查询总数
        count_stmt = select(func.count()).select_from(Activity).where(and_(*conditions))
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # 查询列表（包含租户名称和编码）
        stmt = (
            select(Activity, Tenant.tenant_name, Tenant.tenant_code)
            .join(Tenant, Activity.tenant_id == Tenant.id, isouter=True)
            .where(and_(*conditions))
            .order_by(Activity.create_time.desc())
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        
        items = []
        for activity, tenant_name, tenant_code in rows:
            response = await self._build_activity_response(activity, tenant_name, tenant_code)
            items.append(response)
        
        return total, items
    
    async def update_activity(
        self, 
        activity_id: int, 
        data: ActivityUpdate,
        updated_by: Optional[str] = None
    ) -> Optional[ActivityResponse]:
        """
        更新活动
        
        Args:
            activity_id: 活动ID
            data: 更新数据
            updated_by: 更新人
        
        Returns:
            更新后的活动，不存在返回 None
        """
        stmt = select(Activity).where(
            and_(
                Activity.id == activity_id,
                Activity.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        activity = result.scalar_one_or_none()
        
        if not activity:
            return None

        # 预计算更新后的 tenant_id / agent_code_list，用于校验
        new_tenant_id = data.tenant_id if data.tenant_id is not None else activity.tenant_id
        new_agent_code_list = data.agent_code_list if data.agent_code_list is not None else activity.agent_code_list

        # 检查租户是否存在（如果更新了租户）
        if data.tenant_id is not None and data.tenant_id != activity.tenant_id:
            tenant_stmt = select(Tenant).where(
                and_(
                    Tenant.id == data.tenant_id,
                    Tenant.is_deleted == 0
                )
            )
            tenant_result = await self.db.execute(tenant_stmt)
            tenant = tenant_result.scalar_one_or_none()

            if not tenant:
                raise ValueError(f"租户 ID '{data.tenant_id}' 不存在")

        # 校验 Agent 列表
        if new_agent_code_list:
            await self._validate_agent_codes(new_agent_code_list, new_tenant_id)
        
        # 更新字段（排除 questions）
        update_data = data.model_dump(exclude_unset=True, exclude={"questions"})
        for key, value in update_data.items():
            setattr(activity, key, value)
        
        activity.updated_by = updated_by
        
        # 更新问题（如果提供）
        if data.questions is not None:
            await self._update_questions(activity_id, data.questions, updated_by)
        
        await self.db.commit()
        await self.db.refresh(activity)
        
        logger.info(f"更新活动成功: {activity.activity_code}")
        
        # 获取租户名称和编码
        tenant_stmt = select(Tenant.tenant_name, Tenant.tenant_code).where(Tenant.id == activity.tenant_id)
        tenant_result = await self.db.execute(tenant_stmt)
        tenant_data = tenant_result.first()
        
        tenant_name = tenant_data.tenant_name if tenant_data else None
        tenant_code = tenant_data.tenant_code if tenant_data else None
        
        return await self._build_activity_response(activity, tenant_name, tenant_code)
    
    async def _update_questions(
        self,
        activity_id: int,
        questions_data: List,
        updated_by: Optional[str] = None
    ) -> None:
        """更新问题（全量替换策略）"""
        # 软删除旧问题和选项
        old_questions_stmt = select(ActivityQuestion).where(
            and_(
                ActivityQuestion.activity_id == activity_id,
                ActivityQuestion.is_deleted == 0
            )
        )
        old_questions_result = await self.db.execute(old_questions_stmt)
        old_questions = old_questions_result.scalars().all()
        
        for old_q in old_questions:
            old_q.is_deleted = 1
            old_q.updated_by = updated_by
            # 软删除选项
            for opt in old_q.options:
                opt.is_deleted = 1
                opt.updated_by = updated_by
        
        # 创建新问题
        await self._create_questions(activity_id, questions_data, updated_by)
    
    async def update_status(
        self,
        activity_id: int,
        data: ActivityStatusUpdate,
        updated_by: Optional[str] = None
    ) -> Optional[ActivityResponse]:
        """
        更新活动状态
        
        Args:
            activity_id: 活动ID
            data: 状态数据
            updated_by: 更新人
        
        Returns:
            更新后的活动
        """
        stmt = select(Activity).where(
            and_(
                Activity.id == activity_id,
                Activity.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        activity = result.scalar_one_or_none()
        
        if not activity:
            return None
        
        activity.status = data.status
        activity.updated_by = updated_by
        
        await self.db.commit()
        await self.db.refresh(activity)
        
        logger.info(f"更新活动状态成功: {activity.activity_code} -> {data.status}")
        
        # 获取租户名称
        tenant_stmt = select(Tenant.tenant_name, Tenant.tenant_code).where(Tenant.id == activity.tenant_id)
        tenant_result = await self.db.execute(tenant_stmt)
        tenant_data = tenant_result.first()
        
        tenant_name = tenant_data.tenant_name if tenant_data else None
        tenant_code = tenant_data.tenant_code if tenant_data else None
        
        return await self._build_activity_response(activity, tenant_name, tenant_code)
    
    async def delete_activity(self, activity_id: int, deleted_by: Optional[str] = None) -> bool:
        """
        删除活动（软删除）
        
        Args:
            activity_id: 活动ID
            deleted_by: 删除人
        
        Returns:
            是否删除成功
        """
        stmt = select(Activity).where(
            and_(
                Activity.id == activity_id,
                Activity.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        activity = result.scalar_one_or_none()
        
        if not activity:
            return False
        
        activity.is_deleted = 1
        activity.updated_by = deleted_by
        
        # 软删除关联的问题和选项
        questions_stmt = select(ActivityQuestion).where(
            and_(
                ActivityQuestion.activity_id == activity_id,
                ActivityQuestion.is_deleted == 0
            )
        )
        questions_result = await self.db.execute(questions_stmt)
        questions = questions_result.scalars().all()
        
        for q in questions:
            q.is_deleted = 1
            q.updated_by = deleted_by
            for opt in q.options:
                opt.is_deleted = 1
                opt.updated_by = deleted_by
        
        await self.db.commit()
        
        logger.info(f"删除活动成功: {activity.activity_code}")
        return True
    
    async def list_simple(self, tenant_id: Optional[int] = None) -> List[ActivitySimpleItem]:
        """
        获取简单活动列表（用于下拉框）
        
        Args:
            tenant_id: 可选，按租户过滤
        
        Returns:
            简单活动列表
        """
        conditions = [
            Activity.is_deleted == 0,
            Activity.enabled == 1,
        ]
        
        if tenant_id:
            conditions.append(Activity.tenant_id == tenant_id)
        
        stmt = (
            select(Activity)
            .where(and_(*conditions))
            .order_by(Activity.activity_name)
        )
        result = await self.db.execute(stmt)
        activities = result.scalars().all()
        
        return [ActivitySimpleItem.model_validate(a) for a in activities]
    
    # ============== 问题单独操作接口 ==============
    
    async def update_activity_questions(
        self,
        activity_id: int,
        data: ActivityQuestionsUpdate,
        updated_by: Optional[str] = None
    ) -> Optional[List[ActivityQuestionResponse]]:
        """
        更新活动问题（全量替换）
        
        Args:
            activity_id: 活动ID
            data: 问题数据
            updated_by: 更新人
        
        Returns:
            更新后的问题列表，活动不存在返回 None
        """
        # 检查活动是否存在
        stmt = select(Activity).where(
            and_(
                Activity.id == activity_id,
                Activity.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        activity = result.scalar_one_or_none()
        
        if not activity:
            return None
        
        # 更新问题
        await self._update_questions(activity_id, data.questions, updated_by)
        
        activity.updated_by = updated_by
        await self.db.commit()
        
        logger.info(f"更新活动问题成功: {activity.activity_code}")
        
        # 返回更新后的问题列表
        response = await self._build_activity_response(activity)
        return response.questions
    
    async def get_activity_questions(self, activity_id: int) -> Optional[List[ActivityQuestionResponse]]:
        """
        获取活动问题列表
        
        Args:
            activity_id: 活动ID
        
        Returns:
            问题列表，活动不存在返回 None
        """
        # 检查活动是否存在
        stmt = select(Activity).where(
            and_(
                Activity.id == activity_id,
                Activity.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        activity = result.scalar_one_or_none()
        
        if not activity:
            return None
        
        response = await self._build_activity_response(activity)
        return response.questions
