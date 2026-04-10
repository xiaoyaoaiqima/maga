"""
Job service - Business logic for job operations
"""
import asyncio
import time
import uuid
import json
import httpx
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.orm import defer
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.job import Job
from app.models.expert_config import ExpertConfig
from app.models.expert_task import ExpertTask
from app.models.expert_call_trace import ExpertCallTrace
from app.models.rlhf_feedback import RLHFFeedback
from app.models.agent import Agent
from app.models.tenant import Tenant
from app.models.activity import Activity
from app.schemas.job import JobCreate, JobUpdate, ExpertTaskConfig
from app.schemas.expert_task import ExpertTaskCreate
from app.schemas.sub_job import SubJobCreate
from app.schemas.content import ContentCreate, ContentUpdate
from app.schemas.expert_business_result import ExpertBusinessResultCreate
from app.services.expert_config_service import ExpertConfigService
from app.services.sub_job_service import SubJobService
from app.services.trace_service import TraceService
from app.core.config import settings
from app.utils.job_test_helper import JobTestHelper
from app.utils.expert_caller import ExpertCaller, TraceData
from app.scheduler import get_scheduler_manager
from app.scheduler.expert_task_executor import execute_expert_task_sync
from app.schemas.message import MessagePublishRequest
from app.services.message_service import MessageService


class JobService:
    """Job service"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        result = await self.db.execute(
            select(Job).where(Job.job_id == job_id, Job.is_deleted == 0)
        )
        return result.scalar_one_or_none()
    
    async def list(
        self,
        status: Optional[str] = None,
        enabled: Optional[bool] = None,
        tenant_id: Optional[int] = None,
        agent_code: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Job]:
        """List jobs with optional filters"""
        query = select(Job).options(defer(Job.job_generation_plan)).where(Job.is_deleted == 0)
        
        if status:
            query = query.where(Job.status == status)
        if enabled is not None:
            query = query.where(Job.enabled == enabled)
        if tenant_id is not None:
            query = query.where(Job.tenant_id == tenant_id)
        if agent_code:
            query = query.where(Job.agent_code == agent_code)
        
        result = await self.db.execute(query.offset(skip).limit(limit))
        jobs = list(result.scalars().all())

        # Enrich with names
        tenant_ids = {j.tenant_id for j in jobs if j.tenant_id}
        activity_ids = {j.activity_id for j in jobs if j.activity_id}
        agent_codes = {j.agent_code for j in jobs if j.agent_code}
        
        tenants = {}
        activities = {}
        agents = {}
        
        if tenant_ids:
            res = await self.db.execute(select(Tenant.id, Tenant.tenant_name).where(Tenant.id.in_(tenant_ids)))
            tenants = {r.id: r.tenant_name for r in res.all()}
            
        if activity_ids:
            res = await self.db.execute(select(Activity.id, Activity.activity_name).where(Activity.id.in_(activity_ids)))
            activities = {r.id: r.activity_name for r in res.all()}
            
        if agent_codes:
            res = await self.db.execute(select(Agent.agent_code, Agent.agent_name).where(Agent.agent_code.in_(agent_codes)))
            agents = {r.agent_code: r.agent_name for r in res.all()}
            
        for job in jobs:
            if job.tenant_id:
                setattr(job, "tenant_name", tenants.get(job.tenant_id))
            if job.activity_id:
                setattr(job, "activity_name", activities.get(job.activity_id))
            if job.agent_code:
                setattr(job, "agent_name", agents.get(job.agent_code))
        
        return jobs
    
    async def create(self, job_in: JobCreate, created_by: Optional[str] = None) -> Job:
        """Create job"""
        # 排除 Job 模型不存在的字段（这些是 Response 用的关联字段）
        job_data = job_in.model_dump(exclude={"tenant_name", "activity_name", "agent_name"})
        
        # 如果指定了 agent_code，验证 Agent 存在
        if job_in.agent_code:
            agent_result = await self.db.execute(
                select(Agent).where(
                    Agent.agent_code == job_in.agent_code,
                    Agent.is_deleted == 0
                )
            )
            agent = agent_result.scalar_one_or_none()
            if not agent:
                raise ValueError(f"Agent with code {job_in.agent_code} not found")
            if not agent.enabled:
                raise ValueError(f"Agent with code {job_in.agent_code} is not enabled")

            # 创建 Job 时强制从 Agent 继承编排与 0 分规则（避免 Job 侧再配置 Expert 编排）
            job_data["expert_config_code_list"] = agent.expert_config_code_list or []
            job_data["zero_score_invalid_expert_codes"] = agent.zero_score_invalid_expert_codes
        else:
            # 未绑定 Agent 时，必须显式提供 expert_config_code_list
            if not job_data.get("expert_config_code_list"):
                raise ValueError("未指定 agent_code 时，expert_config_code_list 不能为空")
        
        # 如果指定了 tenant_id，验证租户存在
        if job_in.tenant_id:
            tenant_result = await self.db.execute(
                select(Tenant).where(
                    Tenant.id == job_in.tenant_id,
                    Tenant.is_deleted == 0
                )
            )
            tenant = tenant_result.scalar_one_or_none()
            if not tenant:
                raise ValueError(f"Tenant with id {job_in.tenant_id} not found")
        
        # 如果指定了 activity_id，验证活动存在
        if job_in.activity_id:
            activity_result = await self.db.execute(
                select(Activity).where(
                    Activity.id == job_in.activity_id,
                    Activity.is_deleted == 0
                )
            )
            activity = activity_result.scalar_one_or_none()
            if not activity:
                raise ValueError(f"Activity with id {job_in.activity_id} not found")

        # 验证 job_generation_plan
        job_generation_plan = job_data.get("job_generation_plan")
        if job_generation_plan:
            plan_mode = job_generation_plan.get("mode")
            # strategy_v3 模式必须有 strategy_selections
            if plan_mode == "strategy_v3":
                strategy_selections = job_generation_plan.get("strategy_selections")
                if not strategy_selections or len(strategy_selections) == 0:
                    raise ValueError("strategy_v3 模式必须指定 strategy_selections")

                # ⭐ 强制使用轻量级格式：移除所有冗余字段，只保留配置
                # 执行时会通过 fetch_merged_strategy_combinations 动态生成 plan_items
                lightweight_plan = {
                    "mode": "strategy_v3",
                    "strategy_selections": strategy_selections,
                    "sample_mode": job_generation_plan.get("sample_mode", "first"),
                    "primary_strategy_id": job_generation_plan.get("primary_strategy_id"),
                    "target_count": job_generation_plan.get("target_count") or job_generation_plan.get("total_count"),
                    "variable_share_mapping": job_generation_plan.get("variable_share_mapping", {}),
                }
                # 替换为轻量级格式
                job_data["job_generation_plan"] = lightweight_plan

                logger.info(
                    f"[JobService.create] strategy_v3 模式强制使用轻量级格式，"
                    f"移除了 plan_items/merged_allocations 等冗余字段"
                )

        # Validate expert_config_code_list & zero_score_invalid_expert_codes
        expert_config_service = ExpertConfigService(self.db)
        expert_config_code_list = job_data.get("expert_config_code_list", [])
        for expert_config_code in expert_config_code_list:
            expert_config = await expert_config_service.get_by_code(expert_config_code)
            if not expert_config:
                raise ValueError(f"ExpertConfig with code {expert_config_code} not found")
            if not expert_config.enabled:
                raise ValueError(f"ExpertConfig with code {expert_config_code} is not enabled")

        # zero_score_invalid_expert_codes: None=兼容旧逻辑；[]/list=新逻辑
        zero_score_invalid_expert_codes = job_data.get("zero_score_invalid_expert_codes", None)
        if zero_score_invalid_expert_codes is not None:
            # 必须是 expert_config_code_list 的子集
            for code in zero_score_invalid_expert_codes:
                if code not in expert_config_code_list:
                    raise ValueError(
                        f"zero_score_invalid_expert_codes 中包含未在 expert_config_code_list 内的 expert: {code}"
                    )
                expert_config = await expert_config_service.get_by_code(code)
                if not expert_config:
                    raise ValueError(f"ExpertConfig with code {code} not found")
                if expert_config.expert_type.upper() == "GENERATION":
                    raise ValueError(
                        f"zero_score_invalid_expert_codes 不允许包含 GENERATION expert: {code}"
                    )
        
        # Generate job_id
        job_id = f"job-{uuid.uuid4().hex[:16]}"
        
        job = Job(
            job_id=job_id,
            **job_data
        )
        if created_by:
            job.created_by = created_by
            job.updated_by = created_by
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job


    async def copy(self, source_job_id: str, new_job_name: Optional[str], created_by: Optional[str] = None) -> Job:
        """
        Copy an existing job (including job_generation_plan)
        
        This method queries the source job WITH job_generation_plan (unlike list),
        then creates a new job with the same configuration but a different name.
        
        Args:
            source_job_id: Source job ID to copy from
            new_job_name: New job name (optional, will auto-generate if None)
            created_by: User who created the copy
            
        Returns:
            The newly created job
        """
        # Query source job WITH job_generation_plan (no defer)
        result = await self.db.execute(
            select(Job).where(Job.job_id == source_job_id, Job.is_deleted == 0)
        )
        source_job = result.scalar_one_or_none()

        if not source_job:
            raise ValueError(f"Source job {source_job_id} not found")

        # Auto-generate name if not provided
        if not new_job_name:
            import time
            import re

            # 清理旧的 _copy_ 时间戳后缀，避免重复追加
            # 例如：A_copy_123_copy_456 -> A
            base_name = re.sub(r'_copy_\d+', '', source_job.job_name)

            timestamp = str(int(time.time() * 1000))
            new_job_name = f"{base_name}_copy_{timestamp}"

        # Prepare job data (exclude auto-generated and response-only fields)
        job_data = {
            "job_name": new_job_name,
            "tenant_id": source_job.tenant_id,
            "activity_id": source_job.activity_id,
            "agent_code": source_job.agent_code,
            "description": source_job.description,
            "expert_config_code_list": source_job.expert_config_code_list or [],
            "zero_score_invalid_expert_codes": source_job.zero_score_invalid_expert_codes,
            # ⭐ CRITICAL: Copy job_generation_plan from source (this is the whole point!)
            "job_generation_plan": source_job.job_generation_plan,
            "article_count": source_job.article_count,
            "remark": source_job.remark,
            "status": "NOT_DEPLOYED",  # Reset status for new job
            "enabled": True,
        }
        
        # Generate new job_id
        new_job_id = f"job-{uuid.uuid4().hex[:16]}"
        
        # Create new job
        new_job = Job(job_id=new_job_id, **job_data)
        if created_by:
            new_job.created_by = created_by
            new_job.updated_by = created_by
        
        self.db.add(new_job)
        await self.db.commit()
        await self.db.refresh(new_job)
        
        logger.info(
            f"[JobService.copy] Copied job: {source_job_id} -> {new_job_id}, "
            f"has_generation_plan={bool(source_job.job_generation_plan)}"
        )
        
        return new_job
    
    async def update(
        self,
        job_id: str,
        job_in: JobUpdate,
        updated_by: Optional[str] = None,
    ) -> Optional[Job]:
        """Update job"""
        job = await self.get(job_id)
        if not job:
            return None

        old_status = job.status
        
        expert_config_service = ExpertConfigService(self.db)
        # If expert_config_code_list is being updated, validate it
        if job_in.expert_config_code_list is not None:
            for expert_config_code in job_in.expert_config_code_list:
                expert_config = await expert_config_service.get_by_code(expert_config_code)
                if not expert_config:
                    raise ValueError(f"ExpertConfig with code {expert_config_code} not found")
                if not expert_config.enabled:
                    raise ValueError(f"ExpertConfig with code {expert_config_code} is not enabled")
        
        # Validate merged zero_score_invalid_expert_codes against merged expert list
        merged_expert_list = (
            job_in.expert_config_code_list
            if job_in.expert_config_code_list is not None
            else (job.expert_config_code_list or [])
        )
        merged_zero_score_list = (
            job_in.zero_score_invalid_expert_codes
        )
        if merged_zero_score_list is not None:
            for code in merged_zero_score_list:
                if code not in merged_expert_list:
                    raise ValueError(
                        f"zero_score_invalid_expert_codes 中包含未在 expert_config_code_list 内的 expert: {code}"
                    )
                expert_config = await expert_config_service.get_by_code(code)
                if not expert_config:
                    raise ValueError(f"ExpertConfig with code {code} not found")
                if expert_config.expert_type.upper() == "GENERATION":
                    raise ValueError(
                        f"zero_score_invalid_expert_codes 不允许包含 GENERATION expert: {code}"
                    )
        
        update_data = job_in.model_dump(exclude_unset=True)

        # ⭐ 处理 job_generation_plan 更新
        if "job_generation_plan" in update_data and update_data["job_generation_plan"] is not None:
            new_plan = update_data["job_generation_plan"]
            old_plan = job.job_generation_plan

            # strategy_v3 模式：强制使用轻量级格式，移除 plan_items
            # 执行时会通过 fetch_merged_strategy_combinations 动态生成
            if new_plan.get("mode") == "strategy_v3":
                strategy_selections = new_plan.get("strategy_selections")
                lightweight_plan = {
                    "mode": "strategy_v3",
                    "strategy_selections": strategy_selections,
                    "sample_mode": new_plan.get("sample_mode", "first"),
                    "primary_strategy_id": new_plan.get("primary_strategy_id"),
                    "target_count": new_plan.get("target_count") or new_plan.get("total_count"),
                    "variable_share_mapping": new_plan.get("variable_share_mapping", {}),
                }
                update_data["job_generation_plan"] = lightweight_plan
                logger.info(
                    f"[JobService.update] strategy_v3 模式强制使用轻量级格式，"
                    f"移除了 plan_items/merged_allocations 等冗余字段"
                )
            else:
                # 其他模式：如果新 plan 中没有 plan_items，但旧 plan 中有，则保留旧的 plan_items
                if (
                    not new_plan.get("plan_items")
                    and old_plan
                    and old_plan.get("plan_items")
                ):
                    logger.info(
                        f"[JobService.update] 保留原有的 plan_items，job_id={job_id}, "
                        f"plan_items_count={len(old_plan.get('plan_items', []))}"
                    )
                    new_plan["plan_items"] = old_plan["plan_items"]
                    update_data["job_generation_plan"] = new_plan
        
        for field, value in update_data.items():
            setattr(job, field, value)

        if updated_by:
            job.updated_by = updated_by

        # Job 完成通知：仅在状态从非 COMPLETED 变为 COMPLETED 时触发一次
        new_status = job.status
        if old_status != "COMPLETED" and new_status == "COMPLETED":
            await self._notify_job_completed(job=job, operator_user_id=updated_by)
        
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def _notify_job_completed(self, *, job: Job, operator_user_id: Optional[str]) -> None:
        """
        Job 完成时发送站内消息

        目标接收人：
        - 优先 job.created_by（若已设置为 sys_user.id）
        - 否则 fallback 到 operator_user_id（谁把状态改成 COMPLETED）
        """
        receiver_user_id = job.created_by or operator_user_id
        if not receiver_user_id:
            logger.warning(
                f"[消息] Job completed but no receiver user_id: job_id={job.job_id}"
            )
            return

        link = f"/job/detail/{job.job_id}"
        title = f"任务已完成：{job.job_name}"
        content = f"Job 已完成：{job.job_name}\njob_id={job.job_id}\n点击查看详情。"

        service = MessageService(self.db)
        await service.publish_system_message(
            publisher_user_id=operator_user_id or "system",
            publisher_name=None,
            data=MessagePublishRequest(
                title=title,
                content=content,
                link=link,
                message_type="job",
                target_user_ids=[receiver_user_id],
            ),
        )
    
    async def deploy(
        self,
        job_id: str,
        task_configs: List[ExpertTaskConfig]
    ) -> List[ExpertTask]:
        """Deploy job - Create expert_tasks for each expert_config_code with custom configs"""
        job = await self.get(job_id)
        if not job:
            raise ValueError(f"Job with id {job_id} not found")
        
        if job.status != "NOT_DEPLOYED":
            raise ValueError(f"Job {job_id} is already deployed or in other status")
        
        # 验证 task_configs 是否包含所有必需的 expert_config_code
        config_codes = {cfg.expert_config_code for cfg in task_configs}
        job_codes = set(job.expert_config_code_list)
        if config_codes != job_codes:
            missing = job_codes - config_codes
            extra = config_codes - job_codes
            error_msg = []
            if missing:
                error_msg.append(f"缺少配置: {', '.join(missing)}")
            if extra:
                error_msg.append(f"多余的配置: {', '.join(extra)}")
            raise ValueError(f"任务配置不匹配: {'; '.join(error_msg)}")
        
        # 构建 expert_config_code -> config 的映射
        config_map = {cfg.expert_config_code: cfg for cfg in task_configs}
        
        expert_config_service = ExpertConfigService(self.db)
        expert_tasks: List[ExpertTask] = []
        registered_scheduler_job_ids: List[str] = []

        # 统一通过 APScheduler 注册 cron 任务：保证“数据库状态”和“调度器任务”一致（原子化）
        scheduler_manager = get_scheduler_manager()
        try:
            scheduler_manager.start()
        except Exception as e:
            logger.warning(f"[Deploy] Scheduler start skipped/failed: {e}")

        try:
            # 1) 创建 expert_task（不提交事务）
            for expert_config_code in job.expert_config_code_list:
                expert_config = await expert_config_service.get_by_code(expert_config_code)
                if not expert_config:
                    raise ValueError(f"ExpertConfig with code {expert_config_code} not found")

                existing_task_result = await self.db.execute(
                    select(ExpertTask).where(
                        ExpertTask.job_id == job_id,
                        ExpertTask.expert_config_code == expert_config_code,
                        ExpertTask.is_deleted == 0,
                    )
                )
                existing_task_one = existing_task_result.scalar_one_or_none()
                if existing_task_one:
                    expert_tasks.append(existing_task_one)
                    continue

                task_config = config_map[expert_config_code]
                expert_task = ExpertTask(
                    job_id=job_id,
                    expert_config_code=expert_config_code,
                    cron_expression=task_config.cron_expression,
                    misfire_policy=task_config.misfire_policy,
                    concurrent=task_config.concurrent,
                    status=0,
                )
                self.db.add(expert_task)
                expert_tasks.append(expert_task)

            # 2) 标记 job 已部署（先写入事务，注册调度成功后再 commit）
            job.status = "DEPLOYED"

            # Flush：拿到自增 ID（不提交事务）
            await self.db.flush()

            # 3) 注册调度任务（任意一个失败都视为部署失败）
            for task in expert_tasks:
                expert_config = await expert_config_service.get_by_code(task.expert_config_code)
                executor = (
                    "generation"
                    if expert_config and expert_config.expert_type.upper() == "GENERATION"
                    else "critic"
                )

                job_id_for_scheduler = f"expert_task_{task.id}"
                try:
                    scheduler_manager.add_cron_job(
                        func=execute_expert_task_sync,
                        job_id=job_id_for_scheduler,
                        cron_expression=task.cron_expression,
                        args=(task.id,),
                        executor=executor,
                        replace_existing=True,
                    )
                    registered_scheduler_job_ids.append(job_id_for_scheduler)
                    logger.info(f"[Deploy] Registered scheduled job: {job_id_for_scheduler}")
                except Exception as e:
                    raise ValueError(
                        f"注册调度任务失败：expert_task_id={task.id}, "
                        f"expert_config_code={task.expert_config_code}, "
                        f"cron='{task.cron_expression}', error={str(e)}"
                    ) from e

            await self.db.commit()

        except Exception:
            await self.db.rollback()
            for jid in registered_scheduler_job_ids:
                try:
                    scheduler_manager.remove_job(jid)
                except Exception:
                    pass
            raise

        for task in expert_tasks:
            await self.db.refresh(task)

        return expert_tasks
    
    async def pause(self, job_id: str) -> Optional[Job]:
        """Pause job - Pause all associated expert_tasks in scheduler and update status"""
        job = await self.get(job_id)
        if not job:
            raise ValueError(f"Job with id {job_id} not found")
        
        # 获取所有活跃的 expert_tasks
        tasks = await self.get_tasks(job_id)
        scheduler_manager = get_scheduler_manager()
        
        for task in tasks:
            if task.status in (0, 1):  # 待执行或运行中，都需要暂停
                task.status = 2  # 已暂停
                scheduler_job_id = f"expert_task_{task.id}"
                try:
                    scheduler_manager.pause_job(scheduler_job_id)
                    logger.info(f"[Job Pause] Paused scheduled job: {scheduler_job_id}")
                except Exception as e:
                    logger.warning(f"[Job Pause] Failed to pause scheduler job {scheduler_job_id}: {e}")

        job.status = "PAUSED"
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def resume(self, job_id: str) -> Optional[Job]:
        """Resume job - Resume all paused expert_tasks in scheduler and update status"""
        job = await self.get(job_id)
        if not job:
            raise ValueError(f"Job with id {job_id} not found")
        
        tasks = await self.get_tasks(job_id)
        scheduler_manager = get_scheduler_manager()
        
        for task in tasks:
            if task.status == 2:  # 只有暂停的才需要恢复
                task.status = 1  # 运行中
                scheduler_job_id = f"expert_task_{task.id}"
                try:
                    scheduler_manager.resume_job(scheduler_job_id)
                    logger.info(f"[Job Resume] Resumed scheduled job: {scheduler_job_id}")
                except Exception as e:
                    logger.warning(f"[Job Resume] Failed to resume scheduler job {scheduler_job_id}: {e}")

        job.status = "DEPLOYED"  # 或者根据需要设为 RUNNING
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def complete(self, job_id: str) -> Optional[Job]:
        """Complete job - Stop all associate expert_tasks and update status to COMPLETED"""
        job = await self.get(job_id)
        if not job:
            raise ValueError(f"Job with id {job_id} not found")

        # 保存旧状态用于通知判断
        old_status = job.status

        tasks = await self.get_tasks(job_id)
        scheduler_manager = get_scheduler_manager()

        for task in tasks:
            task.status = 3  # 已完成
            scheduler_job_id = f"expert_task_{task.id}"
            try:
                scheduler_manager.remove_job(scheduler_job_id)
                logger.info(f"[Job Complete] Removed scheduled job: {scheduler_job_id}")
            except Exception as e:
                logger.warning(f"[Job Complete] Failed to remove scheduler job {scheduler_job_id}: {e}")

        job.status = "COMPLETED"
        await self.db.commit()
        await self.db.refresh(job)

        # Job 完成通知：状态从非 COMPLETED 变为 COMPLETED 时触发
        if old_status != "COMPLETED":
            await self._notify_job_completed(job=job, operator_user_id=job.updated_by)

        return job

    async def delete(self, job_id: str) -> bool:
        """Soft delete job"""
        job = await self.get(job_id)
        if not job:
            return False
        
        job.is_deleted = 1
        await self.db.commit()
        return True
    
    async def test(
        self,
        job_id: str,
        experts_plugin_config_snapshot: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        count: int = 1
    ) -> Dict[str, Any]:
        """
        Test job - Execute all experts in the job with optional plugin config snapshot
        
        Args:
            job_id: Job ID
            experts_plugin_config_snapshot: Optional plugin config snapshot
            count: Number of executions (default: 1)
        
        Returns:
            Test results dict of the LAST execution.
        """
        logger.info(f"[Job Test] Starting test for job_id: {job_id}, count: {count}")
        
        import asyncio
        from app.core.database import async_session_factory
        
        semaphore = asyncio.Semaphore(5)
        
        async def _run_test_with_session():
            async with semaphore:
                # 每个并发任务必须使用独立的数据库会话，避免 AsyncSession 并发竞争
                async with async_session_factory() as session:
                    service = JobService(session)
                    return await service._execute_single_test(
                        job_id=job_id,
                        experts_plugin_config_snapshot=experts_plugin_config_snapshot
                    )

        # 创建所有并发任务
        tasks = [_run_test_with_session() for _ in range(count)]
        
        # 并发执行，信号量限制为 5
        results_list = await asyncio.gather(*tasks)
        
        # 返回最后一次执行的结果（兼容原有接口期望）
        return results_list[-1] if results_list else {}

    async def _execute_single_test(
        self,
        job_id: str,
        experts_plugin_config_snapshot: Optional[Dict[str, List[Dict[str, Any]]]] = None
    ) -> Dict[str, Any]:
        """
        Execute a single test run for a job.
        """
        job = await self.get(job_id)
        if not job:
            logger.error(f"[Job Test] Job not found: {job_id}")
            raise ValueError(f"Job with id {job_id} not found")
        
        expert_config_service = ExpertConfigService(self.db)
        sub_job_service = SubJobService(self.db)
        results: Dict[str, Any] = {}
        
        # Generate test IDs
        test_sub_job_id = f"test-sub-{uuid.uuid4().hex[:16]}"
        test_content_id = f"test-content-{uuid.uuid4().hex[:16]}"
        test_trace_id = f"trace-{uuid.uuid4().hex[:8]}"
        
        # 1. 创建 sub_job 记录
        await sub_job_service.create_sub_job(SubJobCreate(
            job_id=job_id,
            sub_job_id=test_sub_job_id,
            content_id=test_content_id,
            expert_list=job.expert_config_code_list,
            expert_complete_list=[],
            status="RUNNING"
        ))
        
        # 创建追踪数据上下文
        trace_data = TraceData(
            job_id=job_id,
            sub_job_id=test_sub_job_id,
            content_id=test_content_id,
            trace_id=test_trace_id,
        )
        
        content_for_next = ""
        score_by_expert: Dict[str, int] = {}
        content_invalid = False  # 标记内容是否被判定无效
        
        # 去重 expert_config_code_list，避免同一个 expert 重复执行
        seen_expert_codes: set[str] = set()
        unique_expert_list: list[str] = []
        for code in job.expert_config_code_list:
            if code not in seen_expert_codes:
                seen_expert_codes.add(code)
                unique_expert_list.append(code)
        
        for idx, expert_config_code in enumerate(unique_expert_list, 1):
            expert_config = await expert_config_service.get_by_code(expert_config_code)
            if not expert_config or not expert_config.enabled:
                continue
            
            plugin_config_snapshot = []
            prompt = ""
            render_time_ms = 0
            try:
                business_type = expert_config.expert_type.upper()

                # Build plugin_config_snapshot: support partial override + random fill
                base_snapshot = None
                if experts_plugin_config_snapshot and expert_config_code in experts_plugin_config_snapshot:
                    base_snapshot = experts_plugin_config_snapshot[expert_config_code]
                
                if expert_config.plugin_config:
                    # 使用更新后的 build_plugin_config_snapshot (支持 base_snapshot 合并)
                    plugin_config_snapshot = await JobTestHelper.build_plugin_config_snapshot(
                        self.db,
                        expert_config_code,
                        expert_config.plugin_config,
                        base_snapshot=base_snapshot
                    )
                else:
                    plugin_config_snapshot = base_snapshot or []
                
                # Render prompt_template with plugin_config_snapshot
                render_start_time = time.time()
                if expert_config.prompt_template:
                    prompt = await JobTestHelper.render_prompt_with_snapshot_and_context(
                        self.db,
                        expert_config.prompt_template,
                        plugin_config_snapshot
                    )
                render_time_ms = int((time.time() - render_start_time) * 1000)
                
                # Build payload
                payload = ExpertCaller.build_expert_payload(
                    job_id=job_id,
                    sub_job_id=test_sub_job_id,
                    content_id=test_content_id,
                    expert_task_id=0,
                    expert_config_code=expert_config_code,
                    prompt=prompt,
                    content=content_for_next,
                    model_code=expert_config.model_code,
                    model_config=expert_config.model_config,
                    plugin_config_snapshot=plugin_config_snapshot
                )
                
                # Call expert service
                call_result = await ExpertCaller.call_expert(
                    expert_app=expert_config.expert_app,
                    expert_service=expert_config.expert_service,
                    expert_func=expert_config.expert_func,
                    payload=payload,
                    timeout=300,
                    trace_data=trace_data,
                    expert_config_code=expert_config_code,
                    expert_type=expert_config.expert_type,
                )
                
                # 解析返回结果
                if isinstance(call_result, dict) and "trace_info" in call_result:
                    response_data = call_result.get("response", {})
                    trace_info = call_result.get("trace_info", {})
                    trace_info["render_time_ms"] = render_time_ms
                    
                    # 构建结果摘要
                    result_summary = None
                    if isinstance(response_data, dict):
                        content_preview = (
                            response_data.get("generatedContent", "")
                            or response_data.get("generated_content")
                            or response_data.get("content", "")
                            or response_data.get("reason", "")
                            or response_data.get("message", "")
                        )
                        if not content_preview and "score" in response_data:
                            score = response_data.get("score")
                            reason = response_data.get("reason", "")
                            content_preview = f"评分: {score}, 原因: {reason}"
                        
                        result_summary = {
                            "title": response_data.get("title"),
                            "generated_content_preview": content_preview[:500] if content_preview else "",
                            "content_id": response_data.get("contentId") or response_data.get("content_id"),
                            "success": response_data.get("success", True),
                            "score": response_data.get("score"),
                        }
                    
                    # 记录追踪到数据库
                    await self._save_trace(
                        trace_info,
                        plugin_config_snapshot,
                        rendered_prompt=prompt,
                        result_summary=result_summary
                    )
                else:
                    response_data = call_result

                # 统一失败判定
                ok = True
                error_message = None
                if not isinstance(response_data, dict):
                    ok = False
                    error_message = "Expert 返回格式异常（非 JSON 对象）"
                    response_data = {"result": response_data}
                else:
                    if response_data.get("success") is False:
                        ok = False
                        error_message = response_data.get("error") or response_data.get("message") or "Expert 返回 success=false"
                    elif response_data.get("error"):
                        ok = False
                        error_message = str(response_data.get("error"))
                    
                    if ok and business_type == "GENERATION":
                        generated = response_data.get("generatedContent") or response_data.get("generated_content") or response_data.get("content") or ""
                        if not (isinstance(generated, str) and generated.strip()):
                            ok = False
                            error_message = response_data.get("message") or "GENERATION 未返回有效的 title/content"
                
                results[expert_config_code] = response_data

                # 创建 expert_business_result 记录
                await sub_job_service.create_business_result(ExpertBusinessResultCreate(
                    job_id=job_id,
                    sub_job_id=test_sub_job_id,
                    content_id=test_content_id,
                    expert_task_id=None,
                    expert_config_code=expert_config_code,
                    expert_config_name=expert_config.expert_config_name,
                    model_code=expert_config.model_code,
                    business_type=business_type,
                    plugin_config_snapshot=plugin_config_snapshot,
                    prompt=prompt,
                    business_result=response_data if isinstance(response_data, dict) else {"result": response_data},
                    status="SUCCESS" if ok else "FAILED",
                    error_message=error_message
                ))

                if not ok:
                    await sub_job_service.complete_sub_job(test_sub_job_id, "FAILED")
                    return results

                # 更新 sub_job 的 expert_complete_list
                await sub_job_service.add_expert_complete(test_sub_job_id, expert_config_code)

                if business_type == "GENERATION" and isinstance(response_data, dict):
                    generated = response_data.get("generatedContent") or response_data.get("generated_content") or response_data.get("content")
                    title = response_data.get("title", "")
                    if generated:
                        content_for_next = generated
                        if response_data.get("content_id"):
                            trace_data.content_id = response_data.get("content_id")
                    
                    context_list = await self._extract_context_list(plugin_config_snapshot, tenant_code=job.tenant_id)
                    await sub_job_service.create_content(ContentCreate(
                        job_id=job_id,
                        sub_job_id=test_sub_job_id,
                        content_id=test_content_id,
                        tenant_id=job.tenant_id,
                        activity_id=job.activity_id,
                        agent_code=job.agent_code,
                        prompt=prompt,
                        context_list=context_list,
                        title=title,
                        content=generated or "",
                        is_valid=None,
                        is_test_case=1
                    ))
                
                if business_type in ("CRITIC", "BAN") and isinstance(response_data, dict):
                    score = response_data.get("score")
                    if score is not None:
                        try:
                            score_int = int(score)
                            score_by_expert[expert_config_code] = score_int
                            
                            # 提前判无效逻辑 (与调度器保持一致)
                            should_check = False
                            if job.zero_score_invalid_expert_codes is None:
                                should_check = True
                            else:
                                should_check = expert_config_code in job.zero_score_invalid_expert_codes
                            
                            if should_check and score_int == 0:
                                await sub_job_service.set_content_valid(test_content_id, 0)
                                logger.info(f"[Job Test] Score 0 detected for expert {expert_config_code}, setting content invalid and stopping")
                                content_invalid = True  # 标记无效，退出循环
                        except Exception as score_parse_err:
                            logger.warning(f"[Job Test] Failed to parse score: {score_parse_err}")
                
                # 如果内容被判定无效，立即停止后续 expert 执行
                if content_invalid:
                    break
                        
            except Exception as e:
                error_info = {"error": str(e), "error_type": type(e).__name__}
                results[expert_config_code] = error_info
                business_type = (getattr(expert_config, "expert_type", None) or "UNKNOWN").upper()
                await sub_job_service.create_business_result(ExpertBusinessResultCreate(
                    job_id=job_id,
                    sub_job_id=test_sub_job_id,
                    content_id=test_content_id,
                    expert_task_id=None,
                    expert_config_code=expert_config_code,
                    expert_config_name=expert_config.expert_config_name,
                    model_code=expert_config.model_code,
                    business_type=business_type,
                    plugin_config_snapshot=plugin_config_snapshot,
                    prompt=prompt,
                    business_result=error_info,
                    status="FAILED",
                    error_message=str(e)
                ))
                await sub_job_service.complete_sub_job(test_sub_job_id, "FAILED")
                return results
        
        await sub_job_service.complete_sub_job(test_sub_job_id, "COMPLETED")
        
        # 最后一次检查：如果还没被标记为 0，且所有专家都跑完了，则置为 1
        content_after = await sub_job_service.get_content_by_content_id(test_content_id)
        if content_after and content_after.is_valid is None:
            targets = job.zero_score_invalid_expert_codes
            target_scores = [score_by_expert[c] for c in (targets if targets is not None else score_by_expert.keys()) if c in score_by_expert]
            if not any(s == 0 for s in target_scores):
                await sub_job_service.set_content_valid(test_content_id, 1)
            else:
                await sub_job_service.set_content_valid(test_content_id, 0)
            
        return results

    async def _fetch_node_names(
        self,
        node_ids: List[str],
        tenant_code: str = "default"
    ) -> Dict[str, str]:
        """
        批量获取节点名称（通过 Dapr 调用 keyword-corpus 服务）

        Args:
            node_ids: 节点 ID 列表
            tenant_code: 租户编码

        Returns:
            节点 ID 到名称的映射
        """
        if not node_ids:
            return {}

        import httpx

        KEYWORD_CORPUS_APP_ID = "raap-service-keyword-corpus"

        # 通过 Dapr 调用
        dapr_url = (
            f"http://localhost:{settings.DAPR_HTTP_PORT}"
            f"/v1.0/invoke/{KEYWORD_CORPUS_APP_ID}/method/api/v1/categories/keywords/batch-get"
        )

        node_ids_int = []
        for nid in node_ids:
            try:
                node_ids_int.append(int(nid))
            except (ValueError, TypeError):
                logger.warning(f"[_fetch_node_names] Invalid node_id: {nid}")

        if not node_ids_int:
            return {}

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    dapr_url,
                    json={"node_ids": node_ids_int, "include_children": False},
                    params={"tenant_code": tenant_code},
                )

                if resp.status_code == 200:
                    result = resp.json()
                    data = result.get("data", {})
                    # 提取 node_id -> name 映射
                    node_id_to_name = {}
                    for nid_str, node_info in data.items():
                        if isinstance(node_info, dict):
                            node_id_to_name[nid_str] = node_info.get("name", nid_str)
                    logger.info(f"[_fetch_node_names] Fetched {len(node_id_to_name)} node names")
                    return node_id_to_name
                else:
                    logger.warning(f"[_fetch_node_names] API failed: status={resp.status_code}")
        except Exception as e:
            logger.warning(f"[_fetch_node_names] Failed to fetch node names: {e}")

        return {}

    async def _extract_context_list(
        self,
        plugin_config_snapshot: Optional[List[Dict[str, Any]]],
        strategy_combo: Optional[Dict[str, Any]] = None,
        tenant_code: str = "default"
    ) -> Dict[str, str]:
        """
        从 plugin_config_snapshot 中提取结构化的 context_list

        Args:
            plugin_config_snapshot: Plugin 配置快照，格式:
                [
                    {
                        "plugin_code": "xxx",
                        "variable_mapping": {
                            "写者": ["生活美学家", "通勤战士"],
                            "目的": ["好物分享"]
                        }
                    }
                ]
            strategy_combo: 策略组合，格式: {
                "persona": {"id": "xxx", "name": "旺玥", "label": "人设"},
                "scenario": {"id": "yyy", "name": "换季期", "label": "场景"}
            }
            tenant_code: 租户编码

        Returns:
            结构化的变量映射字典，如: {"写者": "生活美学家", "目的": "好物分享"}
            - key: 变量名 (variable_name)
            - value: 选中的上下文名（节点名称，而非 node ID）
            - 如果同一变量名在多个插件中出现，后面的会覆盖前面的
            - 如果变量值是数组，取第一个元素
        """
        if not plugin_config_snapshot:
            return {}

        # 构建 node_id -> name 的映射（从 strategy_combo 中提取）
        # 支持两种格式：{id, name} 和 {node_id, node_name}
        node_id_to_name: Dict[str, str] = {}
        need_fetch_ids: List[str] = []

        if strategy_combo:
            for dimension, node_info in strategy_combo.items():
                if isinstance(node_info, dict):
                    # 兼容两种格式：{id, name} 或 {node_id, node_name}
                    node_id = node_info.get("id") or node_info.get("node_id")
                    node_name = node_info.get("name") or node_info.get("node_name")
                    if node_id:
                        if node_name:
                            node_id_to_name[str(node_id)] = node_name
                        else:
                            # 只有 ID 没有 name，记录需要查询
                            need_fetch_ids.append(str(node_id))

        # 从 plugin_config_snapshot 中提取 node:id，收集需要查询的 ID
        if not need_fetch_ids:
            for plugin_item in plugin_config_snapshot:
                variable_mapping = plugin_item.get("variable_mapping", {})
                for var_name, context_names in variable_mapping.items():
                    if isinstance(context_names, list) and len(context_names) > 0:
                        context_value = context_names[0]
                    elif isinstance(context_names, str) and context_names:
                        context_value = context_names
                    else:
                        continue

                    if isinstance(context_value, str) and context_value.startswith("node:"):
                        node_id = context_value[5:]
                        if node_id not in node_id_to_name:
                            need_fetch_ids.append(node_id)

        # 批量查询缺失的节点名称
        if need_fetch_ids:
            fetched_names = await self._fetch_node_names(
                list(set(need_fetch_ids)),  # 去重
                tenant_code
            )
            node_id_to_name.update(fetched_names)

        # 构建 context_mapping
        context_mapping: Dict[str, str] = {}
        for plugin_item in plugin_config_snapshot:
            variable_mapping = plugin_item.get("variable_mapping", {})
            for var_name, context_names in variable_mapping.items():
                # 取第一个值（实际执行时应该只选了一个）
                if isinstance(context_names, list) and len(context_names) > 0:
                    context_value = context_names[0]
                elif isinstance(context_names, str) and context_names:
                    context_value = context_names
                else:
                    continue

                # 如果是 node:xxx 格式，尝试从 node_id_to_name 获取名称
                if isinstance(context_value, str) and context_value.startswith("node:"):
                    node_id = context_value[5:]  # 去掉 "node:" 前缀
                    if node_id in node_id_to_name:
                        context_mapping[var_name] = node_id_to_name[node_id]
                    else:
                        # 找不到名称，保留 node:xxx 格式（前端会转换）
                        context_mapping[var_name] = context_value
                else:
                    # 新格式：直接存储的是 node.name，直接使用
                    context_mapping[var_name] = context_value

        return context_mapping

    async def _save_trace(
        self,
        trace_info: Dict[str, Any],
        plugin_config_snapshot: Optional[List[Dict[str, Any]]] = None,
        rendered_prompt: Optional[str] = None,
        result_summary: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        保存追踪记录到数据库
        
        Args:
            trace_info: 追踪信息字典
            plugin_config_snapshot: Plugin 配置快照，格式: [{plugin_code, variable_mapping}]
            rendered_prompt: 渲染后的 Prompt
            result_summary: 结果摘要
        """
        try:
            trace = ExpertCallTrace(
                job_id=trace_info.get("job_id", ""),
                sub_job_id=trace_info.get("sub_job_id", ""),
                content_id=trace_info.get("content_id"),
                trace_id=trace_info.get("trace_id", ""),
                span_id=trace_info.get("span_id", ""),
                parent_span_id=trace_info.get("parent_span_id"),
                stage=trace_info.get("stage", "expert_call"),
                expert_config_code=trace_info.get("expert_config_code"),
                expert_type=trace_info.get("expert_type"),
                service_app=trace_info.get("service_app", ""),
                service_method=trace_info.get("service_method", ""),
                status=trace_info.get("status", "success"),
                error_type=trace_info.get("error_type"),
                error_message=trace_info.get("error_message"),
                start_time=trace_info.get("start_time", datetime.now()),
                end_time=trace_info.get("end_time"),
                duration_ms=trace_info.get("duration_ms"),
                # 细粒度时间指标
                queue_time_ms=trace_info.get("queue_time_ms"),
                model_time_ms=trace_info.get("model_time_ms"),
                render_time_ms=trace_info.get("render_time_ms"),
                # 模型和 Token 信息
                model_code=trace_info.get("model_code"),
                model_provider=trace_info.get("model_provider") or trace_info.get("provider_code"),
                provider_code=trace_info.get("provider_code") or trace_info.get("model_provider"),
                input_tokens=trace_info.get("input_tokens", 0),
                output_tokens=trace_info.get("output_tokens", 0),
                total_tokens=trace_info.get("total_tokens", 0),
                experiment_id=trace_info.get("experiment_id"),
                experiment_group=trace_info.get("experiment_group"),
                plugin_config_snapshot=plugin_config_snapshot,
                rendered_prompt=rendered_prompt,
                result_summary=result_summary,
                caller_service="raap-service-orchestrator",
            )

            # 统一计算费用
            trace_service = TraceService(self.db)
            await trace_service._calculate_and_set_trace_cost(trace)

            self.db.add(trace)
            await self.db.commit()
            logger.debug(f"[Job Test] Trace saved: span_id={trace_info.get('span_id')}")
            
            # 如果是 GE 生成成功，自动创建 RLHF 待审核记录
            await self._maybe_create_rlhf_feedback(trace_info, result_summary)
        except Exception as e:
            logger.error(f"[Job Test] Failed to save trace: {e}")
            # 不抛出异常，追踪记录失败不应影响主流程

    async def _maybe_create_rlhf_feedback(
        self,
        trace_info: Dict[str, Any],
        result_summary: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        如果符合条件，自动创建 RLHF 待审核记录
        
        触发条件：
        - stage = 'ge_generation' 且 status = 'success'
        - 有 content_id
        
        Args:
            trace_info: 追踪信息字典
            result_summary: 结果摘要
        """
        try:
            stage = trace_info.get("stage", "")
            status = trace_info.get("status", "")
            content_id = trace_info.get("content_id") or (result_summary or {}).get("content_id")
            
            # 只有 GE 生成成功才创建 RLHF 记录
            if stage != "ge_generation" or status != "success":
                return
            
            if not content_id:
                logger.debug("[RLHF] No content_id, skip RLHF feedback creation")
                return
            
            # 检查是否已存在
            existing = await self.db.execute(
                select(RLHFFeedback).where(
                    RLHFFeedback.content_id == content_id,
                    RLHFFeedback.is_deleted == 0
                )
            )
            if existing.scalar_one_or_none():
                logger.debug(f"[RLHF] Feedback already exists for content_id={content_id}")
                return
            
            # 提取内容信息
            title = None
            content = None
            if result_summary:
                title = result_summary.get("title")
                content = result_summary.get("generated_content_preview", "")
            
            # 创建 RLHF 反馈记录
            feedback = RLHFFeedback(
                job_id=trace_info.get("job_id", ""),
                sub_job_id=trace_info.get("sub_job_id", ""),
                content_id=content_id,
                trace_id=trace_info.get("trace_id"),
                title=title,
                content=content,
                ge_expert_code=trace_info.get("expert_config_code"),
                model_code=trace_info.get("model_code"),
                review_status="PENDING",
                created_by="system",
            )
            
            self.db.add(feedback)
            await self.db.commit()
            logger.info(f"[RLHF] Created feedback for content_id={content_id}, job_id={trace_info.get('job_id')}")
            
        except Exception as e:
            logger.error(f"[RLHF] Failed to create feedback: {e}")
            # 不抛出异常，RLHF 创建失败不应影响主流程
    
    async def get_tasks(self, job_id: str) -> List[ExpertTask]:
        """
        获取 Job 关联的所有 ExpertTask
        
        Args:
            job_id: Job ID
            
        Returns:
            ExpertTask 列表
        """
        job = await self.get(job_id)
        if not job:
            raise ValueError(f"Job with id {job_id} not found")
        
        result = await self.db.execute(
            select(ExpertTask)
            .where(ExpertTask.job_id == job_id, ExpertTask.is_deleted == 0)
            .order_by(ExpertTask.id.asc())
        )
        return list(result.scalars().all())
    
    async def get_executions(
        self,
        job_id: str,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        expert_config_code: Optional[str] = None,
    ) -> tuple[List[ExpertCallTrace], int]:
        """
        获取 Job 的执行历史
        
        Args:
            job_id: Job ID
            page: 页码
            page_size: 每页数量
            status: 状态筛选
            expert_config_code: ExpertConfig 编码筛选
            
        Returns:
            (执行记录列表, 总数)
        """
        job = await self.get(job_id)
        if not job:
            raise ValueError(f"Job with id {job_id} not found")
        
        # 构建查询
        query = select(ExpertCallTrace).where(ExpertCallTrace.job_id == job_id)
        count_query = select(func.count()).select_from(ExpertCallTrace).where(
            ExpertCallTrace.job_id == job_id
        )
        
        if status:
            query = query.where(ExpertCallTrace.status == status)
            count_query = count_query.where(ExpertCallTrace.status == status)
        
        if expert_config_code:
            query = query.where(ExpertCallTrace.expert_config_code == expert_config_code)
            count_query = count_query.where(ExpertCallTrace.expert_config_code == expert_config_code)
        
        # 获取总数
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 分页查询
        offset = (page - 1) * page_size
        query = query.order_by(ExpertCallTrace.created_at.desc()).offset(offset).limit(page_size)
        
        result = await self.db.execute(query)
        items = list(result.scalars().all())
        
        return items, total
    
    async def export_results(
        self,
        job_id: str,
        format: str = "json",
        include_details: bool = False,
    ) -> Dict[str, Any]:
        """
        导出 Job 的执行结果
        
        Args:
            job_id: Job ID
            format: 导出格式 (json/csv)
            include_details: 是否包含详细信息（rendered_prompt, plugin_config_snapshot）
            
        Returns:
            导出数据
        """
        job = await self.get(job_id)
        if not job:
            raise ValueError(f"Job with id {job_id} not found")
        
        # 获取执行记录
        query = select(ExpertCallTrace).where(
            ExpertCallTrace.job_id == job_id
        ).order_by(ExpertCallTrace.created_at.desc())
        
        result = await self.db.execute(query)
        traces = list(result.scalars().all())
        
        # 统计数据
        total_count = len(traces)
        success_count = sum(1 for t in traces if t.status == "success")
        failed_count = sum(1 for t in traces if t.status == "failed")
        timeout_count = sum(1 for t in traces if t.status == "timeout")
        
        total_tokens = sum(t.total_tokens or 0 for t in traces)
        total_input_tokens = sum(t.input_tokens or 0 for t in traces)
        total_output_tokens = sum(t.output_tokens or 0 for t in traces)
        
        avg_duration = (
            sum(t.duration_ms or 0 for t in traces) / total_count
            if total_count > 0 else 0
        )
        
        # 构建导出数据
        export_data = {
            "job_id": job_id,
            "job_name": job.job_name,
            "export_time": datetime.now().isoformat(),
            "summary": {
                "total_executions": total_count,
                "success_count": success_count,
                "failed_count": failed_count,
                "timeout_count": timeout_count,
                "success_rate": round(success_count / total_count * 100, 2) if total_count > 0 else 0,
                "total_tokens": total_tokens,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "avg_duration_ms": round(avg_duration, 2),
            },
            "executions": [],
        }
        
        # 构建执行记录
        for trace in traces:
            execution = {
                "id": trace.id,
                "sub_job_id": trace.sub_job_id,
                "content_id": trace.content_id,
                "trace_id": trace.trace_id,
                "span_id": trace.span_id,
                "stage": trace.stage,
                "expert_config_code": trace.expert_config_code,
                "expert_type": trace.expert_type,
                "status": trace.status,
                "error_type": trace.error_type,
                "error_message": trace.error_message,
                "start_time": trace.start_time.isoformat() if trace.start_time else None,
                "end_time": trace.end_time.isoformat() if trace.end_time else None,
                "duration_ms": trace.duration_ms,
                "model_code": trace.model_code,
                "input_tokens": trace.input_tokens,
                "output_tokens": trace.output_tokens,
                "total_tokens": trace.total_tokens,
                "result_summary": trace.result_summary,
            }
            
            if include_details:
                execution["rendered_prompt"] = trace.rendered_prompt
                execution["plugin_config_snapshot"] = trace.plugin_config_snapshot
            
            export_data["executions"].append(execution)
        
        return export_data
