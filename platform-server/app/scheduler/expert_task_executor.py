"""
Expert Task 执行器 - 处理定时任务的实际执行逻辑
"""
import asyncio
import hashlib
import json
import uuid
import time
import random
from typing import Dict, Any, Optional, List

from sqlalchemy import select, update, or_, and_, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory as AsyncSessionLocal
from app.core.config import settings
from app.core.logger import get_logger
from app.models.expert_task import ExpertTask
from app.models.job import Job
from app.models.sub_job import SubJob
from app.models.content import Content
from app.models.tenant import Tenant
from app.services.expert_config_service import ExpertConfigService
from app.services.sub_job_service import SubJobService
from app.utils.expert_caller import ExpertCaller, TraceData
from app.utils.job_test_helper import JobTestHelper
from app.schemas.sub_job import SubJobCreate
from app.schemas.content import ContentCreate
from app.schemas.expert_business_result import ExpertBusinessResultCreate
from app.services.critic_score_service import CriticScoreService

logger = get_logger()

_PLAN_ITEMS_CACHE_TTL_SECONDS = 60
_PLAN_ITEMS_CACHE_MAX_SIZE = 128
_plan_items_cache: Dict[str, tuple[float, List[Dict[str, Any]]]] = {}
_generation_subtask_semaphore = asyncio.Semaphore(max(1, settings.JOB_MAX_ACTIVE_GENERATION_SUBTASKS))
_critic_subtask_semaphore = asyncio.Semaphore(max(1, settings.JOB_MAX_ACTIVE_CRITIC_SUBTASKS))


def _build_plan_items_cache_key(
        job_id: str,
        job_generation_plan: Optional[Dict[str, Any]],
        tenant_code: str,
        expert_config_code_list: Optional[List[str]],
) -> Optional[str]:
    if not isinstance(job_generation_plan, dict):
        return None

    cache_payload = {
        "job_id": job_id,
        "tenant_code": tenant_code,
        "expert_config_code_list": expert_config_code_list or [],
        "job_generation_plan": job_generation_plan,
    }
    serialized = json.dumps(
        cache_payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha1(serialized.encode("utf-8")).hexdigest()
    return f"{job_id}:{digest}"


def _prune_plan_items_cache(now_monotonic: float) -> None:
    expired_keys = [
        key for key, (cached_at, _) in _plan_items_cache.items()
        if now_monotonic - cached_at >= _PLAN_ITEMS_CACHE_TTL_SECONDS
    ]
    for key in expired_keys:
        _plan_items_cache.pop(key, None)

    if len(_plan_items_cache) <= _PLAN_ITEMS_CACHE_MAX_SIZE:
        return

    sorted_items = sorted(_plan_items_cache.items(), key=lambda item: item[1][0])
    overflow = len(_plan_items_cache) - _PLAN_ITEMS_CACHE_MAX_SIZE
    for key, _ in sorted_items[:overflow]:
        _plan_items_cache.pop(key, None)


async def _get_expanded_plan_items(
        db: AsyncSession,
        job_id: str,
        job_generation_plan: Optional[Dict[str, Any]],
        tenant_code: str,
        expert_config_code_list: Optional[List[str]],
) -> List[Dict[str, Any]]:
    cache_key = _build_plan_items_cache_key(
        job_id=job_id,
        job_generation_plan=job_generation_plan,
        tenant_code=tenant_code,
        expert_config_code_list=expert_config_code_list,
    )
    now_monotonic = time.monotonic()

    if cache_key:
        cached = _plan_items_cache.get(cache_key)
        if cached and now_monotonic - cached[0] < _PLAN_ITEMS_CACHE_TTL_SECONDS:
            return cached[1]

    plan_items_expanded = await JobTestHelper.expand_job_generation_plan_async(
        job_generation_plan,
        tenant_code=tenant_code,
        db=db,
        expert_config_code_list=expert_config_code_list,
    )

    if cache_key:
        _plan_items_cache[cache_key] = (now_monotonic, plan_items_expanded)
        _prune_plan_items_cache(now_monotonic)

    return plan_items_expanded


def _get_plan_item_by_index(
        plan_items_expanded: List[Dict[str, Any]],
        plan_index: Optional[int],
) -> Optional[Dict[str, Any]]:
    if plan_index is None:
        return None
    if plan_index < 0 or plan_index >= len(plan_items_expanded):
        return None
    plan_item = plan_items_expanded[plan_index]
    return plan_item if isinstance(plan_item, dict) else None


async def _remove_scheduled_jobs_for_job(job_id: str) -> None:
    """从调度器移除 job 相关的所有任务"""
    try:
        from app.scheduler import get_scheduler_manager
        scheduler_manager = get_scheduler_manager()

        # 查询该 job 的所有 expert_tasks
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ExpertTask.id).where(
                    ExpertTask.job_id == job_id,
                    ExpertTask.is_deleted == 0
                )
            )
            task_ids = result.scalars().all()

        for task_id in task_ids:
            scheduler_job_id = f"expert_task_{task_id}"
            try:
                scheduler_manager.remove_job(scheduler_job_id)
                logger.info(f"[ExpertTaskExecutor] Removed scheduled job: {scheduler_job_id}")
            except Exception as e:
                logger.debug(
                    f"[ExpertTaskExecutor] Scheduled job not found or already removed: {scheduler_job_id}, {e}")
    except Exception as e:
        logger.warning(f"[ExpertTaskExecutor] Failed to remove scheduled jobs for job {job_id}: {e}")


def _merge_plugin_config_snapshot(
        base_snapshot: List[Dict[str, Any]],
        override_snapshot: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    合并 plugin_config_snapshot：
    - base_snapshot：随机生成的完整快照
    - override_snapshot：job_generation_plan 中用户指定的变量（可为部分变量）

    合并规则：
    - 按 plugin_code 合并 variable_mapping（override 覆盖 base）
    - 保持 base_snapshot 的 plugin 顺序，override 中新增的 plugin 追加到末尾
    """
    base_map: Dict[str, Dict[str, str]] = {}
    base_order: List[str] = []

    for item in base_snapshot or []:
        if not isinstance(item, dict):
            continue
        plugin_code = item.get("plugin_code")
        if not isinstance(plugin_code, str) or not plugin_code:
            continue
        mapping = item.get("variable_mapping") or {}
        if not isinstance(mapping, dict):
            mapping = {}
        base_map[plugin_code] = {k: v for k, v in mapping.items() if isinstance(k, str) and isinstance(v, str)}
        base_order.append(plugin_code)

    for item in override_snapshot or []:
        if not isinstance(item, dict):
            continue
        plugin_code = item.get("plugin_code")
        if not isinstance(plugin_code, str) or not plugin_code:
            continue
        mapping = item.get("variable_mapping") or {}
        if not isinstance(mapping, dict):
            continue
        if plugin_code not in base_map:
            base_map[plugin_code] = {}
        for k, v in mapping.items():
            if isinstance(k, str) and isinstance(v, str) and v:
                base_map[plugin_code][k] = v

    result: List[Dict[str, Any]] = []
    seen = set()
    for plugin_code in base_order:
        seen.add(plugin_code)
        merged = base_map.get(plugin_code) or {}
        if merged:
            result.append({"plugin_code": plugin_code, "variable_mapping": merged})

    for plugin_code, merged in base_map.items():
        if plugin_code in seen:
            continue
        if merged:
            result.append({"plugin_code": plugin_code, "variable_mapping": merged})

    return result


async def _save_plugin_config_snapshot_to_subjob(
        sub_job_service: "SubJobService",
        sub_job_id: str,
        plugin_config_snapshot: List[Dict[str, Any]],
        *,
        auto_commit: bool = True,
) -> None:
    """
    将 plugin_config_snapshot（List 格式）保存到 SubJob.plugin_snapshots（Dict 格式）
    
    格式转换:
    - 输入: [{"plugin_code": "xxx", "variable_mapping": {"变量": "值"}}]
    - 输出: {"plugin_code": {"变量": "值"}}
    
    用于保证同一 SubJob 中不同 Expert 使用相同的变量快照
    """
    if not plugin_config_snapshot:
        return

    # 转换格式: List -> Dict
    snapshots_dict: Dict[str, Dict[str, Any]] = {}
    for item in plugin_config_snapshot:
        if not isinstance(item, dict):
            continue
        plugin_code = item.get("plugin_code")
        variable_mapping = item.get("variable_mapping")
        if plugin_code and variable_mapping:
            snapshots_dict[plugin_code] = variable_mapping

    if snapshots_dict:
        await sub_job_service.update_plugin_snapshots(
            sub_job_id,
            snapshots_dict,
            auto_commit=auto_commit,
        )
        logger.debug(f"[Snapshot] 保存快照到 SubJob: sub_job_id={sub_job_id}, plugins={list(snapshots_dict.keys())}")


def _load_plugin_config_snapshot_from_subjob(
        plugin_snapshots: Optional[Dict[str, Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """
    将 SubJob.plugin_snapshots（Dict 格式）转换回 plugin_config_snapshot（List 格式）

    格式转换:
    - 输入: {"plugin_code": {"变量": "值"}}
    - 输出: [{"plugin_code": "xxx", "variable_mapping": {"变量": "值"}}]
    """
    if not plugin_snapshots:
        return []

    result: List[Dict[str, Any]] = []
    for plugin_code, variable_mapping in plugin_snapshots.items():
        if plugin_code and variable_mapping:
            result.append({
                "plugin_code": plugin_code,
                "variable_mapping": variable_mapping,
            })

    return result


def _normalize_candidate_list(v: Any) -> List[str]:
    if isinstance(v, str):
        return [v] if v else []
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str) and x]
    return []


def _get_variable_intersection_candidates(
        plugin_config: Optional[List[Dict[str, Any]]],
        variable_name: str,
) -> List[str]:
    """
    从 expert_config.plugin_config 中抽取某个变量在“跨多个 plugin 的交集候选值”。
    - 若该变量仅出现在一个 plugin：候选值为该 plugin 的候选集合
    - 若出现在多个 plugin：候选值为所有出现位置候选集合的交集
    """
    if not plugin_config or not isinstance(plugin_config, list):
        return []

    sets: List[set] = []
    for plugin_item in plugin_config:
        if not isinstance(plugin_item, dict):
            continue
        mapping = plugin_item.get("variable_mapping") or {}
        if not isinstance(mapping, dict):
            continue
        if variable_name not in mapping:
            continue
        opts = _normalize_candidate_list(mapping.get(variable_name))
        if not opts:
            continue
        sets.append(set(opts))

    if not sets:
        return []
    intersection = sets[0]
    for s in sets[1:]:
        intersection = intersection.intersection(s)
    return list(intersection)


def _set_variable_in_snapshot(
        snapshot: List[Dict[str, Any]],
        variable_name: str,
        context_name: str,
) -> None:
    for plugin_item in snapshot:
        if not isinstance(plugin_item, dict):
            continue
        mapping = plugin_item.get("variable_mapping")
        if not isinstance(mapping, dict):
            continue
        if variable_name in mapping:
            mapping[variable_name] = context_name


def _get_variable_from_snapshot(
        snapshot: List[Dict[str, Any]],
        variable_name: str,
) -> Optional[str]:
    for plugin_item in snapshot:
        if not isinstance(plugin_item, dict):
            continue
        mapping = plugin_item.get("variable_mapping")
        if not isinstance(mapping, dict):
            continue
        v = mapping.get(variable_name)
        if isinstance(v, str) and v:
            return v
    return None


def _apply_rule_conditions_to_snapshot(
        *,
        plugin_config: Optional[List[Dict[str, Any]]],
        snapshot: List[Dict[str, Any]],
        conditions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    将 plan_item.condition.and 的简单条件应用到 snapshot 上：
    - '='：强制指定该变量为指定 context_name（仅当该值在交集候选中）
    - '≠'：避免指定 context_name；若随机命中则从（交集候选-该值）重抽
    """
    if not snapshot or not conditions:
        return snapshot

    equals: Dict[str, str] = {}
    not_equals: Dict[str, str] = {}

    for c in conditions:
        if not isinstance(c, dict):
            continue
        var_name = c.get("field")
        op = c.get("op")
        val = c.get("value")
        if not (isinstance(var_name, str) and var_name):
            continue
        if not (isinstance(op, str) and op in ("=", "≠")):
            continue
        if not (isinstance(val, str) and val):
            continue
        if op == "=":
            equals[var_name] = val
        else:
            not_equals[var_name] = val

    # '=' 优先
    for var_name, val in equals.items():
        candidates = _get_variable_intersection_candidates(plugin_config, var_name)
        if candidates and val not in candidates:
            logger.warning(
                f"[GENERATION Task] rule condition value not in intersection: var={var_name}, value={val}"
            )
            continue
        _set_variable_in_snapshot(snapshot, var_name, val)

    # '≠'：若命中则重抽
    for var_name, forbidden in not_equals.items():
        if var_name in equals:
            # 若同时配置了 '=' 与 '≠'，以 '=' 为准
            continue
        cur = _get_variable_from_snapshot(snapshot, var_name)
        if cur != forbidden:
            continue
        candidates = _get_variable_intersection_candidates(plugin_config, var_name)
        if not candidates:
            continue
        allowed = [x for x in candidates if x != forbidden]
        if not allowed:
            logger.warning(
                f"[GENERATION Task] rule condition makes intersection empty: var={var_name}, forbidden={forbidden}"
            )
            continue
        new_val = random.choice(allowed)
        _set_variable_in_snapshot(snapshot, var_name, new_val)

    return snapshot


async def get_tenant_code_by_id(db: AsyncSession, tenant_id: Optional[int]) -> Optional[str]:
    """根据 tenant_id 获取 tenant_code"""
    if not tenant_id:
        return None
    result = await db.execute(
        select(Tenant.tenant_code).where(Tenant.id == tenant_id, Tenant.is_deleted == 0)
    )
    row = result.scalar_one_or_none()
    return row if row else None


class ExpertTaskExecutor:
    """Expert Task 执行器"""

    # 任务状态常量
    STATUS_PENDING = 0  # 待执行
    STATUS_RUNNING = 1  # 执行中
    STATUS_PAUSED = 2  # 暂停
    STATUS_COMPLETED = 3  # 完成
    STATUS_STOPPED = 4  # 已停止（不再调度）

    @staticmethod
    async def execute_expert_task(expert_task_id: int) -> None:
        """
        执行 expert_task 的入口方法 (由调度器调用)

        Args:
            expert_task_id: expert_task 的技术主键 id
        """
        logger.info(f"[ExpertTaskExecutor] Starting execution for expert_task_id: {expert_task_id}")

        async with AsyncSessionLocal() as db:
            try:
                # 1. 获取 expert_task
                result = await db.execute(
                    select(ExpertTask).where(
                        ExpertTask.id == expert_task_id,
                        ExpertTask.is_deleted == 0
                    )
                )
                expert_task = result.scalar_one_or_none()

                if not expert_task:
                    logger.error(f"[ExpertTaskExecutor] ExpertTask not found: {expert_task_id}")
                    return

                # 2. 使用原子更新确保同一个任务不会被重复执行
                # 注意：不同的任务（不同的 expert_task_id）可以并发执行，这里只防止同一个任务重复执行
                # 先尝试原子性地将状态从 PENDING 更新为 RUNNING
                update_result = await db.execute(
                    update(ExpertTask)
                    .where(
                        ExpertTask.id == expert_task_id,  # 只针对当前任务
                        ExpertTask.status == ExpertTaskExecutor.STATUS_PENDING,
                        ExpertTask.is_deleted == 0
                    )
                    .values(status=ExpertTaskExecutor.STATUS_RUNNING)
                )
                await db.commit()

                # 检查是否有行被更新（如果没有，说明该任务已经在执行中或状态不是 PENDING）
                if update_result.rowcount == 0:
                    logger.info(
                        f"[ExpertTaskExecutor] ExpertTask {expert_task_id} is not PENDING, checking if stuck RUNNING"
                    )

                    # ✅ 新增：检查是否是卡死的 RUNNING 任务（超过30分钟）
                    stuck_task_result = await db.execute(
                        select(ExpertTask).where(
                            ExpertTask.id == expert_task_id,
                            ExpertTask.status == ExpertTaskExecutor.STATUS_RUNNING,
                            ExpertTask.is_deleted == 0
                        )
                    )
                    stuck_task = stuck_task_result.scalar_one_or_none()

                    if stuck_task:
                        # 检查 update_time 时间戳（如果有的话）
                        time_since_update = None
                        if getattr(stuck_task, "update_time", None):
                            from datetime import datetime, timedelta
                            time_since_update = datetime.now() - stuck_task.update_time

                        # 如果超过30分钟没有更新，强制重置为 PENDING
                        STUCK_THRESHOLD_MINUTES = 30
                        if time_since_update and time_since_update > timedelta(minutes=STUCK_THRESHOLD_MINUTES):
                            logger.warning(
                                f"[ExpertTaskExecutor] ExpertTask {expert_task_id} stuck in RUNNING for "
                                f"{time_since_update.total_seconds() / 60:.1f} minutes, resetting to PENDING"
                            )
                            await db.execute(
                                update(ExpertTask)
                                .where(ExpertTask.id == expert_task_id)
                                .values(status=ExpertTaskExecutor.STATUS_PENDING)
                            )
                            await db.commit()

                            # 再次尝试获取执行权
                            update_result = await db.execute(
                                update(ExpertTask)
                                .where(
                                    ExpertTask.id == expert_task_id,
                                    ExpertTask.status == ExpertTaskExecutor.STATUS_PENDING,
                                    ExpertTask.is_deleted == 0
                                )
                                .values(status=ExpertTaskExecutor.STATUS_RUNNING)
                            )
                            await db.commit()

                            if update_result.rowcount == 0:
                                logger.error(f"[ExpertTaskExecutor] Failed to acquire task after reset, skipping")
                                return
                            else:
                                logger.info(f"[ExpertTaskExecutor] Successfully acquired stuck task after reset")
                        else:
                            logger.info(
                                f"[ExpertTaskExecutor] ExpertTask {expert_task_id} is RUNNING but not stuck "
                                f"({time_since_update.total_seconds() / 60 if time_since_update else 'unknown'} minutes), skipping"
                            )
                            return
                    else:
                        # 任务不是 RUNNING 状态，可能是 COMPLETED 或其他状态
                        logger.info(f"[ExpertTaskExecutor] ExpertTask {expert_task_id} not in RUNNING state, skipping")
                        return

                logger.info(f"[ExpertTaskExecutor] Updated status to RUNNING: {expert_task_id}")

                # 重新获取 expert_task（状态已更新为 RUNNING）
                result = await db.execute(
                    select(ExpertTask).where(
                        ExpertTask.id == expert_task_id,
                        ExpertTask.is_deleted == 0
                    )
                )
                expert_task = result.scalar_one_or_none()

                if not expert_task:
                    logger.error(f"[ExpertTaskExecutor] ExpertTask not found after update: {expert_task_id}")
                    return

                # 3. 获取 Job 信息
                job_result = await db.execute(
                    select(Job).where(
                        Job.job_id == expert_task.job_id,
                        Job.is_deleted == 0
                    )
                )
                job = job_result.scalar_one_or_none()

                if not job:
                    logger.error(f"[ExpertTaskExecutor] Job not found: {expert_task.job_id}")
                    # 回滚状态
                    await db.execute(
                        update(ExpertTask)
                        .where(ExpertTask.id == expert_task_id)
                        .values(status=ExpertTaskExecutor.STATUS_PENDING)
                    )
                    await db.commit()
                    return

                if not job.enabled:
                    logger.info(f"[ExpertTaskExecutor] Job is disabled: {expert_task.job_id}")
                    # 回滚状态
                    await db.execute(
                        update(ExpertTask)
                        .where(ExpertTask.id == expert_task_id)
                        .values(status=ExpertTaskExecutor.STATUS_PENDING)
                    )
                    await db.commit()
                    return

                # 【关键修复】检查 Job 是否已完成
                if job.status == 'COMPLETED':
                    logger.info(
                        f"[ExpertTaskExecutor] ✅ Job already COMPLETED: {expert_task.job_id}, "
                        f"stopping expert_task"
                    )
                    expert_task.status = ExpertTaskExecutor.STATUS_STOPPED
                    await db.commit()
                    return

                # 【关键修复】检查已完成+有效的文章数（双重保护）
                if job.article_count and job.article_count > 0:
                    from sqlalchemy import func
                    # ✅ 只统计 status='COMPLETED' 且 content.is_valid=1 的 sub_job
                    # 完成但无效的文章（is_valid=0）不计入完成数量
                    completed_count_result = await db.execute(
                        select(func.count(SubJob.id))
                        .join(Content, SubJob.content_id == Content.content_id)
                        .where(
                            SubJob.job_id == expert_task.job_id,
                            SubJob.status == 'COMPLETED',
                            SubJob.is_deleted == 0,
                            Content.is_valid == 1  # 只统计有效文章
                        )
                    )
                    completed_articles = completed_count_result.scalar() or 0

                    if completed_articles >= job.article_count:
                        logger.warning(
                            f"[ExpertTaskExecutor] ✅ Target reached: {completed_articles}/"
                            f"{job.article_count}, marking job COMPLETED and stopping"
                        )
                        # 从调度器移除任务
                        await _remove_scheduled_jobs_for_job(expert_task.job_id)
                        # 标记 Job 为 COMPLETED
                        await db.execute(
                            update(Job)
                            .where(Job.job_id == expert_task.job_id)
                            .values(status='COMPLETED')
                        )
                        # 停止 expert_task
                        expert_task.status = ExpertTaskExecutor.STATUS_STOPPED
                        await db.commit()
                        return

                # 4. 获取 ExpertConfig 信息
                expert_config_service = ExpertConfigService(db)
                expert_config = await expert_config_service.get_by_code(expert_task.expert_config_code)

                if not expert_config:
                    logger.error(f"[ExpertTaskExecutor] ExpertConfig not found: {expert_task.expert_config_code}")
                    # 回滚状态
                    await db.execute(
                        update(ExpertTask)
                        .where(ExpertTask.id == expert_task_id)
                        .values(status=ExpertTaskExecutor.STATUS_PENDING)
                    )
                    await db.commit()
                    return

                if not expert_config.enabled:
                    logger.info(f"[ExpertTaskExecutor] ExpertConfig is disabled: {expert_task.expert_config_code}")
                    # 回滚状态
                    await db.execute(
                        update(ExpertTask)
                        .where(ExpertTask.id == expert_task_id)
                        .values(status=ExpertTaskExecutor.STATUS_PENDING)
                    )
                    await db.commit()
                    return

                # 6. 根据 expert_type 执行不同的逻辑
                expert_type = expert_config.expert_type.upper()

                # ✅ 添加整体超时保护（10分钟）
                # 防止任务因内部hang导致永久占用资源
                task_timeout = 600  # 10分钟超时

                if expert_type == "GENERATION":
                    try:
                        await asyncio.wait_for(
                            ExpertTaskExecutor._execute_generation_task(
                                db, expert_task, job, expert_config
                            ),
                            timeout=task_timeout
                        )
                    except asyncio.TimeoutError:
                        logger.error(
                            f"[ExpertTaskExecutor] GENERATION task {expert_task_id} timeout after {task_timeout}s")
                        # 状态会在 _execute_generation_task 的 finally 块中重置
                else:
                    # CRITIC 或其他类型
                    try:
                        await asyncio.wait_for(
                            ExpertTaskExecutor._execute_critic_task(
                                db, expert_task, job, expert_config
                            ),
                            timeout=task_timeout
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"[ExpertTaskExecutor] CRITIC task {expert_task_id} timeout after {task_timeout}s")
                        # 状态会在 _execute_critic_task 的 finally 块中重置

            except Exception as e:
                logger.error(f"[ExpertTaskExecutor] Error executing task {expert_task_id}: {e}")
                # 尝试更新状态为待执行（允许重试）
                try:
                    result = await db.execute(
                        select(ExpertTask).where(ExpertTask.id == expert_task_id)
                    )
                    task = result.scalar_one_or_none()
                    if task:
                        task.status = ExpertTaskExecutor.STATUS_PENDING
                        await db.commit()
                except Exception as rollback_error:
                    logger.error(f"[ExpertTaskExecutor] Failed to rollback status: {rollback_error}")

    @staticmethod
    async def _execute_generation_task(
            db: AsyncSession,
            expert_task: ExpertTask,
            job: Job,
            expert_config: Any
    ) -> None:
        """
        执行 GENERATION 类型任务

        逻辑：创建多个线程调用 ExpertCaller.call_expert，
        生成对应的 sub_job、content、expert_business_result 记录，
        直到生成的文章数等于 job.article_count
        """
        job_id = expert_task.job_id
        expert_config_code = expert_task.expert_config_code
        article_count = job.article_count or 1
        # 这里提前取出简单字段，避免并发任务里跨 Session 引用 ORM 对象
        tenant_id = job.tenant_id
        activity_id = job.activity_id
        agent_code = job.agent_code

        # 获取 tenant_code（优先从 expert_config，否则从 job.tenant_id 查询）
        tenant_code = expert_config.tenant_code
        if not tenant_code and tenant_id:
            tenant_code = await get_tenant_code_by_id(db, tenant_id)

        logger.info(
            f"[GENERATION Task] Starting for job_id={job_id}, "
            f"expert_config_code={expert_config_code}, target_articles={article_count}"
        )

        sub_job_service = SubJobService(db)

        # ---------------- 槽位管理（Slot Management） ----------------
        # 1. 展开计划（得到总槽位列表）
        # 使用异步版本以支持 strategy_v3 格式动态展开
        plan_items_expanded: List[Dict[str, Any]] = await _get_expanded_plan_items(
            db=db,
            job_id=job_id,
            job_generation_plan=getattr(job, "job_generation_plan", None),
            tenant_code=tenant_code or "default",
            expert_config_code_list=job.expert_config_code_list,
        )
        total_slots = len(plan_items_expanded) if plan_items_expanded else article_count
        logger.debug(
            f"[GENERATION Task DEBUG] plan_items_expanded count={len(plan_items_expanded)}, first item type={plan_items_expanded[0].get('type') if plan_items_expanded else 'N/A'}")

        # 2. 先检测并清理卡住的 RUNNING sub_job（超过 30 分钟），再查询槽位占用情况
        from datetime import datetime, timedelta
        stuck_timeout_minutes = 30
        stuck_cutoff_time = datetime.now() - timedelta(minutes=stuck_timeout_minutes)

        stuck_sub_jobs_result = await db.execute(
            select(SubJob.sub_job_id, SubJob.plan_index, SubJob.create_time)
            .where(
                SubJob.job_id == job_id,
                SubJob.status == "RUNNING",
                SubJob.is_deleted == 0,
                SubJob.create_time < stuck_cutoff_time  # 创建时间早于 30 分钟前
            )
        )
        stuck_sub_jobs = stuck_sub_jobs_result.all()

        if stuck_sub_jobs:
            logger.warning(
                f"[GENERATION Task] Found {len(stuck_sub_jobs)} stuck RUNNING sub_jobs (timeout > {stuck_timeout_minutes} min), "
                f"marking them as FAILED"
            )

            for sub_job_id, plan_index, create_time in stuck_sub_jobs:
                try:
                    # 标记为 FAILED
                    await db.execute(
                        update(SubJob)
                        .where(
                            SubJob.sub_job_id == sub_job_id,
                            SubJob.job_id == job_id
                        )
                        .values(
                            status="FAILED",
                            error_message=f"自动恢复：RUNNING 状态超过 {stuck_timeout_minutes} 分钟未更新",
                            update_time=datetime.now()
                        )
                    )

                    logger.info(f"[GENERATION Task] Recovered stuck sub_job: {sub_job_id}, plan_index={plan_index}")
                except Exception as e:
                    logger.error(f"[GENERATION Task] Failed to recover stuck sub_job {sub_job_id}: {e}")

            await db.commit()
            logger.info(f"[GENERATION Task] Recovered {len(stuck_sub_jobs)} stuck sub_jobs for job_id={job_id}")

        # 3. 扫描槽位占用情况（直接从数据库查询，保证数据一致性）
        # 占用条件：status=RUNNING 或 (status=COMPLETED 且 content.is_valid=1)
        occupied_query = await db.execute(
            select(distinct(SubJob.plan_index))
            .join(Content, SubJob.content_id == Content.content_id)
            .where(
                SubJob.job_id == job_id,
                SubJob.is_deleted == 0,
                SubJob.plan_index.isnot(None),
                or_(
                    SubJob.status == "RUNNING",
                    and_(
                        SubJob.status == "COMPLETED",
                        Content.is_valid == 1
                    )
                )
            )
        )
        occupied_indexes: Set[int] = {row[0] for row in occupied_query.all() if row[0] is not None}
        logger.info(f"[GENERATION Task] Queried occupied slots from DB: job_id={job_id}, count={len(occupied_indexes)}")

        # 3. 【关键修复】检查已完成+有效的文章数 + 运行中的文章数（防止超量生成）
        # 【关键修复】等待所有 RUNNING 的 sub_job 完成后再判断是否需要创建
        # 统计已完成且有效的文章数
        completed_and_valid_result = await db.execute(
            select(func.count(SubJob.id))
            .join(Content, SubJob.content_id == Content.content_id)
            .where(
                SubJob.job_id == job_id,
                SubJob.status == 'COMPLETED',
                SubJob.is_deleted == 0,
                Content.is_valid == 1  # 已完成且有效
            )
        )
        completed_and_valid_articles = completed_and_valid_result.scalar() or 0

        # 统计运行中的文章（status='RUNNING' 且 is_valid=NULL，表示正在审核）
        running_result = await db.execute(
            select(func.count(SubJob.id))
            .join(Content, SubJob.content_id == Content.content_id)
            .where(
                SubJob.job_id == job_id,
                SubJob.status == 'RUNNING',
                SubJob.is_deleted == 0,
                Content.is_valid.is_(None)  # 只统计正在审核的
            )
        )
        running_articles = running_result.scalar() or 0

        # 【停止条件】已完成有效的文章数 >= 目标数
        if completed_and_valid_articles >= article_count:
            logger.warning(
                f"[GENERATION Task] ✅ Target reached: {completed_and_valid_articles}/{article_count} valid articles, "
                f"marking job COMPLETED and stopping expert_task"
            )
            # 从调度器移除任务
            await _remove_scheduled_jobs_for_job(job_id)
            # 标记 Job 为 COMPLETED
            await db.execute(
                update(Job)
                .where(Job.job_id == job_id)
                .values(status='COMPLETED')
            )
            # 停止 expert_task（不再调度）
            expert_task.status = ExpertTaskExecutor.STATUS_STOPPED
            await db.commit()
            return

        # 【创建前置条件】计算需要创建的数量
        # 公式：needed = 目标数量 N - 已完成且有效的文章数 - 运行中的文章数
        # 注意：running_articles 最终可能变成有效，所以需要减去
        needed_count = article_count - completed_and_valid_articles - running_articles

        # 【关键】只有在 needed_count <= 5 时才需要等待 RUNNING 完成
        # 原因：如果需要创建的数量很多（>5），即使 RUNNING 全变成有效，也不会超量
        # 如果需要创建的数量很少（<=5），则需要等待 RUNNING 完成后才能精确控制
        if needed_count <= 5 and running_articles > 0:
            logger.info(
                f"[GENERATION Task] ⏸️ Need {needed_count} articles (<=5), but {running_articles} still running. "
                f"Waiting for completion to avoid over-generation, marking task PENDING"
            )
            expert_task.status = ExpertTaskExecutor.STATUS_PENDING
            await db.commit()
            return

        # 【关键】计算需要创建的数量
        # 公式：min((目标数量 N - 已完成且有效的文章数 - 运行中的文章数), 5)
        # 5 是最大并发数量
        batch_size = min(needed_count, max(1, settings.JOB_GENERATION_BATCH_SIZE))

        logger.info(
            f"[GENERATION Task] Progress: {completed_and_valid_articles}/{article_count} valid+completed, "
            f"need to create: {needed_count}, batch_size: {batch_size}"
        )

        # 找出未完成的槽位
        pending_indexes = [i for i in range(total_slots) if i not in occupied_indexes]

        # 【关键修复】限制创建数量为 batch_size
        if len(pending_indexes) > batch_size:
            logger.info(
                f"[GENERATION Task] Limiting creation: {len(pending_indexes)} available slots -> {batch_size} articles"
            )
            pending_indexes = pending_indexes[:batch_size]

        logger.info(
            f"[GENERATION Task] Slot status: job_id={job_id}, total={total_slots}, "
            f"occupied={len(occupied_indexes)}, pending={len(pending_indexes)}, "
            f"completed_valid={completed_and_valid_articles}, running={running_articles}, target={article_count}"
        )

        if not pending_indexes:
            # 所有槽位都已占用
            if running_articles > 0:
                # 还有正在运行的文章，等待完成
                logger.info(
                    f"[GENERATION Task] All slots filled, {running_articles} still running, marking task PENDING")
                expert_task.status = ExpertTaskExecutor.STATUS_PENDING
                await db.commit()
                return
            else:
                # 所有槽位都已满且没有运行中的文章 → job 结束
                # 查询已完成（包括无效）的总数
                total_completed_result = await db.execute(
                    select(func.count(SubJob.id))
                    .where(
                        SubJob.job_id == job_id,
                        SubJob.status == 'COMPLETED',
                        SubJob.is_deleted == 0
                    )
                )
                total_completed = total_completed_result.scalar() or 0
                invalid_count = total_completed - completed_and_valid_articles

                logger.warning(
                    f"[GENERATION Task] ✅ All slots filled and no running articles. "
                    f"Valid: {completed_and_valid_articles}, Invalid: {invalid_count}, "
                    f"Total: {total_completed}, Target: {article_count}. "
                    f"Marking job COMPLETED and stopping expert_task"
                )

                # 从调度器移除任务
                await _remove_scheduled_jobs_for_job(job_id)

                # 标记 Job 为 COMPLETED
                await db.execute(
                    update(Job)
                    .where(Job.job_id == job_id)
                    .values(status='COMPLETED')
                )
                # 停止 expert_task（不再调度）
                expert_task.status = ExpertTaskExecutor.STATUS_STOPPED
                await db.commit()
                return

        # 生成文章的任务函数
        async def generate_one_article(plan_index: int) -> bool:
            """生成单篇文章"""
            async with _generation_subtask_semaphore:
                sub_job_id = f"gen-{uuid.uuid4().hex[:16]}"
                content_id = f"content-{uuid.uuid4().hex[:16]}"
                trace_id = f"trace-{uuid.uuid4().hex[:8]}"

                try:
                    logger.info(f"[GENERATION Task] Generating article for slot {plan_index}: sub_job_id={sub_job_id}")

                    async with AsyncSessionLocal() as task_db:
                        task_sub_job_service = SubJobService(task_db)
                        task_expert_config_service = ExpertConfigService(task_db)
                        task_expert_config = await task_expert_config_service.get_by_code(expert_config_code)
                        if not task_expert_config:
                            logger.error("[GENERATION Task] ExpertConfig not found in task session")
                            return False

                        await task_sub_job_service.create_sub_job_with_options(
                            SubJobCreate(
                                job_id=job_id,
                                sub_job_id=sub_job_id,
                                content_id=content_id,
                                expert_list=job.expert_config_code_list or [expert_config_code],
                                expert_complete_list=[],
                                status="RUNNING",
                                plan_index=plan_index,
                            ),
                            auto_commit=False,
                        )

                        plan_item: Optional[Dict[str, Any]] = None
                        plan_snapshot: Optional[List[Dict[str, Any]]] = None
                        if 0 <= plan_index < len(plan_items_expanded):
                            plan_item = plan_items_expanded[plan_index]
                            plan_snapshot = JobTestHelper.get_plan_item_snapshot_for_expert(
                                plan_item, expert_config_code
                            )

                        if plan_item and plan_item.get("type") in ("strategy", "strategy_v3"):
                            base_snapshot = await JobTestHelper.build_plugin_config_snapshot(
                                task_db,
                                expert_config_code,
                                task_expert_config.plugin_config,
                            )
                            epc = plan_item.get("expert_param_config", {})
                            strategy_snapshot = epc.get(expert_config_code)
                            if isinstance(strategy_snapshot, list) and strategy_snapshot:
                                plugin_config_snapshot = _merge_plugin_config_snapshot(
                                    base_snapshot=base_snapshot or [],
                                    override_snapshot=strategy_snapshot,
                                )
                            else:
                                plugin_config_snapshot = base_snapshot or []
                        else:
                            base_snapshot = await JobTestHelper.build_plugin_config_snapshot(
                                task_db,
                                expert_config_code,
                                task_expert_config.plugin_config,
                            )
                            plugin_config_snapshot: List[Dict[str, Any]] = base_snapshot
                            if base_snapshot and plan_item and isinstance(plan_item, dict) and plan_item.get("type") == "rule":
                                cond = plan_item.get("condition") or {}
                                if isinstance(cond, dict):
                                    and_list = cond.get("and") or []
                                    if isinstance(and_list, list) and and_list:
                                        plugin_config_snapshot = _apply_rule_conditions_to_snapshot(
                                            plugin_config=task_expert_config.plugin_config,
                                            snapshot=plugin_config_snapshot,
                                            conditions=[x for x in and_list if isinstance(x, dict)],
                                        )
                            if isinstance(plan_snapshot, list) and plan_snapshot:
                                plugin_config_snapshot = _merge_plugin_config_snapshot(
                                    base_snapshot=base_snapshot or [],
                                    override_snapshot=plan_snapshot,
                                )

                        if task_expert_config.prompt_template:
                            prompt = await JobTestHelper.render_prompt_with_snapshot_and_context(
                                task_db,
                                task_expert_config.prompt_template,
                                plugin_config_snapshot,
                                tenant_code=tenant_code or "default",
                            )
                        else:
                            prompt = ""

                        trace_data = TraceData(
                            job_id=job_id,
                            sub_job_id=sub_job_id,
                            content_id=content_id,
                            trace_id=trace_id,
                        )

                        payload = ExpertCaller.build_expert_payload(
                            job_id=job_id,
                            sub_job_id=sub_job_id,
                            content_id=content_id,
                            expert_task_id=expert_task.id,
                            expert_config_code=expert_config_code,
                            prompt=prompt,
                            content="",
                            model_code=task_expert_config.model_code,
                            model_config=task_expert_config.model_config,
                            plugin_config_snapshot=plugin_config_snapshot,
                            tenant_code=tenant_code,
                        )

                        try:
                            call_result = await ExpertCaller.call_expert(
                                expert_app=task_expert_config.expert_app,
                                expert_service=task_expert_config.expert_service,
                                expert_func=task_expert_config.expert_func,
                                payload=payload,
                                timeout=300,
                                trace_data=trace_data,
                                expert_config_code=expert_config_code,
                                expert_type=task_expert_config.expert_type,
                            )
                        except Exception as call_error:
                            logger.error(f"[GENERATION Task] Expert call failed for article {plan_index}: {call_error}")
                            await task_sub_job_service.create_business_result(
                                ExpertBusinessResultCreate(
                                    job_id=job_id,
                                    sub_job_id=sub_job_id,
                                    content_id=content_id,
                                    expert_task_id=expert_task.id,
                                    expert_config_code=expert_config_code,
                                    expert_config_name=task_expert_config.expert_config_name,
                                    business_type="GENERATION",
                                    plugin_config_snapshot=plugin_config_snapshot,
                                    prompt=prompt,
                                    business_result={"error": str(call_error)},
                                    status="FAILED",
                                    error_message=str(call_error),
                                ),
                                auto_commit=False,
                            )
                            await task_sub_job_service.complete_sub_job(
                                sub_job_id,
                                "FAILED",
                                auto_commit=False,
                            )
                            await task_db.commit()
                            return False

                        if isinstance(call_result, dict) and "response" in call_result:
                            response_data = call_result.get("response", {})
                            trace_info = call_result.get("trace_info", {})
                        else:
                            response_data = call_result
                            trace_info = {}

                        generated_content = ""
                        title = ""
                        if isinstance(response_data, dict):
                            generated_content = (
                                response_data.get("generatedContent")
                                or response_data.get("generated_content")
                                or response_data.get("content", "")
                            )
                            title = response_data.get("title", "")

                        ok = True
                        error_message: Optional[str] = None
                        if not isinstance(response_data, dict):
                            ok = False
                            error_message = "Expert 返回格式异常（非 JSON 对象）"
                            response_data = {"result": response_data}
                        else:
                            if response_data.get("success") is False:
                                ok = False
                                error_message = (
                                    response_data.get("error")
                                    or response_data.get("message")
                                    or "Expert 返回 success=false"
                                )
                            elif response_data.get("error"):
                                ok = False
                                error_message = str(response_data.get("error"))
                            elif not (isinstance(generated_content, str) and generated_content.strip()):
                                ok = False
                                error_message = response_data.get("message") or "Expert 未返回有效的 title/content"

                        if trace_info:
                            try:
                                from app.services.job_service import JobService

                                job_service = JobService(task_db)
                                result_summary = None
                                if isinstance(response_data, dict):
                                    content_preview = (
                                        response_data.get("generatedContent")
                                        or response_data.get("generated_content")
                                        or response_data.get("content", "")
                                    )
                                    result_summary = {
                                        "title": title,
                                        "generated_content_preview": content_preview[:500] if content_preview else "",
                                        "content_id": content_id,
                                        "success": ok,
                                        "score": response_data.get("score"),
                                    }
                                trace_info["status"] = "success" if ok else "failed"
                                if error_message:
                                    trace_info["error_message"] = error_message
                                await job_service._save_trace(
                                    trace_info=trace_info,
                                    plugin_config_snapshot=plugin_config_snapshot,
                                    rendered_prompt=prompt,
                                    result_summary=result_summary,
                                )
                            except Exception as trace_e:
                                logger.error(f"[GENERATION Task] Failed to save trace: {trace_e}")

                        if ok:
                            strategy_combo = plan_item.get("strategy_combo") if plan_item else None
                            context_list = await ExpertTaskExecutor._extract_context_list(
                                plugin_config_snapshot,
                                strategy_combo,
                                tenant_code,
                            )
                            await task_sub_job_service.create_content_with_options(
                                ContentCreate(
                                    job_id=job_id,
                                    sub_job_id=sub_job_id,
                                    content_id=content_id,
                                    tenant_id=tenant_id,
                                    activity_id=activity_id,
                                    agent_code=agent_code,
                                    prompt=prompt,
                                    context_list=context_list,
                                    title=title,
                                    content=generated_content,
                                    is_valid=None,
                                    plan_index=plan_index,
                                    is_test_case=0,
                                ),
                                auto_commit=False,
                            )

                        await task_sub_job_service.create_business_result(
                            ExpertBusinessResultCreate(
                                job_id=job_id,
                                sub_job_id=sub_job_id,
                                content_id=content_id,
                                expert_task_id=expert_task.id,
                                expert_config_code=expert_config_code,
                                expert_config_name=task_expert_config.expert_config_name,
                                model_code=task_expert_config.model_code,
                                business_type="GENERATION",
                                plugin_config_snapshot=plugin_config_snapshot,
                                prompt=prompt,
                                business_result=response_data if isinstance(response_data, dict) else {"result": response_data},
                                status="SUCCESS" if ok else "FAILED",
                                error_message=error_message,
                                plan_index=plan_index,
                            ),
                            auto_commit=False,
                        )

                        if ok:
                            if plugin_config_snapshot:
                                await _save_plugin_config_snapshot_to_subjob(
                                    task_sub_job_service,
                                    sub_job_id,
                                    plugin_config_snapshot,
                                    auto_commit=False,
                                )
                            await task_sub_job_service.add_expert_complete(
                                sub_job_id,
                                expert_config_code,
                                auto_commit=False,
                            )
                            await ExpertTaskExecutor._check_and_complete_sub_job(
                                task_db,
                                sub_job_id,
                                auto_commit=False,
                            )
                            await task_db.commit()
                            logger.info(
                                f"[GENERATION Task] Successfully generated article for slot {plan_index}: content_id={content_id}"
                            )
                            return True

                        await task_sub_job_service.complete_sub_job(
                            sub_job_id,
                            "FAILED",
                            auto_commit=False,
                        )
                        await task_db.commit()
                        logger.error(
                            f"[GENERATION Task] Expert response invalid for slot {plan_index}: "
                            f"content_id={content_id}, error={error_message}"
                        )
                        return False

                except Exception as e:
                    error_message = str(e)
                    logger.error(f"[GENERATION Task] Error generating article {plan_index}: {error_message}")
                    try:
                        async with AsyncSessionLocal() as error_db:
                            error_sub_job_service = SubJobService(error_db)
                            await error_sub_job_service.create_business_result(
                                ExpertBusinessResultCreate(
                                    job_id=job_id,
                                    sub_job_id=sub_job_id,
                                    content_id=content_id,
                                    expert_task_id=expert_task.id,
                                    expert_config_code=expert_config_code,
                                    expert_config_name=expert_config.expert_config_name if expert_config else expert_config_code,
                                    business_type="GENERATION",
                                    plugin_config_snapshot=[],
                                    prompt="",
                                    business_result={"error": error_message},
                                    status="FAILED",
                                    error_message=error_message,
                                    plan_index=plan_index,
                                ),
                                auto_commit=False,
                            )
                            await error_sub_job_service.complete_sub_job(
                                sub_job_id,
                                "FAILED",
                                auto_commit=False,
                            )
                            await error_db.commit()
                            logger.info(
                                f"[GENERATION Task] Marked sub_job {sub_job_id} as FAILED with error: {error_message}"
                            )
                    except Exception as update_error:
                        logger.error(f"[GENERATION Task] Failed to update sub_job status: {update_error}")
                    return False

        # 并发执行生成任务（pending_indexes 已经被限制为 batch_size）
        # 使用 try-finally 确保无论异常与否都重置状态
        try:
            tasks = [generate_one_article(idx) for idx in pending_indexes]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            success_count = sum(1 for r in results if r is True)
            logger.info(f"[GENERATION Task] Batch completed: {success_count}/{len(tasks)} successful")
        finally:
            # ✅ 关键修复：确保无论异常与否都重置状态为 PENDING
            try:
                expert_task.status = ExpertTaskExecutor.STATUS_PENDING
                await db.commit()
                logger.info(f"[GENERATION Task] Reset status to PENDING for next run")
            except Exception as reset_error:
                logger.error(f"[GENERATION Task] Failed to reset status: {reset_error}")
                # 尝试使用新的 session 重置
                try:
                    async with AsyncSessionLocal() as reset_db:
                        await reset_db.execute(
                            update(ExpertTask)
                            .where(ExpertTask.id == expert_task.id)
                            .values(status=ExpertTaskExecutor.STATUS_PENDING)
                        )
                        await reset_db.commit()
                        logger.info(f"[GENERATION Task] Successfully reset status using new session")
                except Exception as final_error:
                    logger.error(f"[GENERATION Task] Critical: failed to reset status with new session: {final_error}")

    @staticmethod
    async def _execute_critic_task(
            db: AsyncSession,
            expert_task: ExpertTask,
            job: Job,
            expert_config: Any
    ) -> None:
        """
        执行 CRITIC 或其他类型任务

        逻辑：获取 job_id 下 expert_complete_list 中没有当前 expert_config_code 的 sub_job，
        处理这些 sub_job，更新 expert_complete_list，如果 score=0 则设置 content.is_valid=0
        """
        job_id = expert_task.job_id
        expert_config_code = expert_task.expert_config_code

        # 获取 tenant_code（优先从 expert_config，否则从 job.tenant_id 查询）
        tenant_code = expert_config.tenant_code if hasattr(expert_config, 'tenant_code') else None
        if not tenant_code and job.tenant_id:
            tenant_code = await get_tenant_code_by_id(db, job.tenant_id)

        logger.info(
            f"[CRITIC Task] Starting for job_id={job_id}, expert_config_code={expert_config_code}, tenant_code={tenant_code}"
        )

        sub_job_service = SubJobService(db)
        plan_items_expanded = await _get_expanded_plan_items(
            db=db,
            job_id=job_id,
            job_generation_plan=getattr(job, "job_generation_plan", None),
            tenant_code=tenant_code or "default",
            expert_config_code_list=job.expert_config_code_list,
        )

        # 查找需要处理的 sub_job（expert_complete_list 中没有当前 expert_config_code）
        # 使用 JSON 查询可能因数据库而异，这里使用简单方法
        all_sub_jobs_result = await db.execute(
            select(SubJob).where(
                SubJob.job_id == job_id,
                SubJob.status == "RUNNING",  # 只处理运行中
                SubJob.is_deleted == 0
            )
        )
        all_sub_jobs = all_sub_jobs_result.scalars().all()

        # 过滤出需要处理的 sub_job：
        # 1. 当前 expert 在 expert_list 中
        # 2. 当前 expert 不在 expert_complete_list 中
        # 3. expert_list 中当前 expert 之前的专家都已在 expert_complete_list 中 (确保顺序执行)
        pending_sub_jobs = []
        for sj in all_sub_jobs:
            expert_list = sj.expert_list or []
            complete_list = sj.expert_complete_list or []

            if expert_config_code in expert_list and expert_config_code not in complete_list:
                try:
                    idx = expert_list.index(expert_config_code)
                    # 检查当前专家之前的所有专家是否都已完成
                    if all(e in complete_list for e in expert_list[:idx]):
                        pending_sub_jobs.append(sj)
                except ValueError:
                    pass

        if not pending_sub_jobs:
            logger.info(f"[CRITIC Task] No pending sub_jobs to process")
            expert_task.status = ExpertTaskExecutor.STATUS_PENDING
            await db.commit()
            return

        logger.info(f"[CRITIC Task] Found {len(pending_sub_jobs)} sub_jobs to process")

        async def process_one_sub_job(sub_job: SubJob) -> bool:
            """处理单个 sub_job"""
            async with _critic_subtask_semaphore:
                try:
                    sub_job_id = sub_job.sub_job_id
                    content_id = sub_job.content_id
                    logger.debug(f"[CRITIC Task] Processing sub_job: {sub_job_id}")

                    async with AsyncSessionLocal() as task_db:
                        task_sub_job_service = SubJobService(task_db)
                        task_expert_config_service = ExpertConfigService(task_db)
                        task_expert_config = await task_expert_config_service.get_by_code(expert_config_code)
                        if not task_expert_config:
                            logger.error("[CRITIC Task] ExpertConfig not found")
                            return False

                        content = await task_sub_job_service.get_content_by_content_id(content_id)
                        if not content:
                            logger.error(f"[CRITIC Task] Content not found: {content_id}")
                            return False

                        plugin_config_snapshot: List[Dict[str, Any]] = []
                        plan_index = sub_job.plan_index
                        cached_snapshot = _load_plugin_config_snapshot_from_subjob(sub_job.plugin_snapshots)
                        if cached_snapshot:
                            if task_expert_config.plugin_config:
                                current_expert_snapshot = await JobTestHelper.build_plugin_config_snapshot(
                                    task_db,
                                    expert_config_code,
                                    task_expert_config.plugin_config,
                                )
                                plugin_config_snapshot = _merge_plugin_config_snapshot(
                                    base_snapshot=current_expert_snapshot,
                                    override_snapshot=cached_snapshot,
                                )
                            else:
                                plugin_config_snapshot = cached_snapshot

                            plan_item = _get_plan_item_by_index(plan_items_expanded, plan_index)
                            if plan_item and plan_item.get("type") in ("strategy", "strategy_v3"):
                                epc = plan_item.get("expert_param_config", {})
                                strategy_snapshot = epc.get(expert_config_code)
                                if isinstance(strategy_snapshot, list) and strategy_snapshot:
                                    plugin_config_snapshot = _merge_plugin_config_snapshot(
                                        base_snapshot=plugin_config_snapshot,
                                        override_snapshot=strategy_snapshot,
                                    )
                        else:
                            base_snapshot: List[Dict[str, Any]] = []
                            if task_expert_config.plugin_config:
                                base_snapshot = await JobTestHelper.build_plugin_config_snapshot(
                                    task_db,
                                    expert_config_code,
                                    task_expert_config.plugin_config,
                                )
                            plan_item = _get_plan_item_by_index(plan_items_expanded, plan_index)
                            if plan_item and plan_item.get("type") in ("strategy", "strategy_v3"):
                                epc = plan_item.get("expert_param_config", {})
                                strategy_snapshot = epc.get(expert_config_code)
                                if isinstance(strategy_snapshot, list) and strategy_snapshot:
                                    plugin_config_snapshot = _merge_plugin_config_snapshot(
                                        base_snapshot=base_snapshot or [],
                                        override_snapshot=strategy_snapshot,
                                    )
                            if not plugin_config_snapshot:
                                plugin_config_snapshot = base_snapshot
                            if plugin_config_snapshot:
                                await _save_plugin_config_snapshot_to_subjob(
                                    task_sub_job_service,
                                    sub_job_id,
                                    plugin_config_snapshot,
                                    auto_commit=False,
                                )

                        if task_expert_config.prompt_template:
                            prompt = await JobTestHelper.render_prompt_with_snapshot_and_context(
                                task_db,
                                task_expert_config.prompt_template,
                                plugin_config_snapshot,
                                tenant_code=tenant_code or "default",
                            )
                        else:
                            prompt = ""

                        trace_data = TraceData(
                            job_id=job_id,
                            sub_job_id=sub_job_id,
                            content_id=content_id,
                            trace_id=f"trace-{uuid.uuid4().hex[:8]}",
                        )

                        payload = ExpertCaller.build_expert_payload(
                            job_id=job_id,
                            sub_job_id=sub_job_id,
                            content_id=content_id,
                            expert_task_id=expert_task.id,
                            expert_config_code=expert_config_code,
                            prompt=prompt,
                            content=content.content or "",
                            model_code=task_expert_config.model_code,
                            model_config=task_expert_config.model_config,
                            plugin_config_snapshot=plugin_config_snapshot,
                            tenant_code=tenant_code,
                        )

                        try:
                            call_result = await ExpertCaller.call_expert(
                                expert_app=task_expert_config.expert_app,
                                expert_service=task_expert_config.expert_service,
                                expert_func=task_expert_config.expert_func,
                                payload=payload,
                                timeout=300,
                                trace_data=trace_data,
                                expert_config_code=expert_config_code,
                                expert_type=task_expert_config.expert_type,
                            )
                        except Exception as call_error:
                            logger.error(f"[CRITIC Task] Expert call failed for sub_job {sub_job_id}: {call_error}")
                            await task_sub_job_service.create_business_result(
                                ExpertBusinessResultCreate(
                                    job_id=job_id,
                                    sub_job_id=sub_job_id,
                                    content_id=content_id,
                                    expert_task_id=expert_task.id,
                                    expert_config_code=expert_config_code,
                                    expert_config_name=task_expert_config.expert_config_name,
                                    business_type=task_expert_config.expert_type.upper(),
                                    plugin_config_snapshot=plugin_config_snapshot,
                                    prompt=prompt,
                                    business_result={"error": str(call_error)},
                                    status="FAILED",
                                    error_message=str(call_error),
                                    plan_index=sub_job.plan_index,
                                ),
                                auto_commit=False,
                            )
                            await task_db.commit()
                            return False

                        if isinstance(call_result, dict) and "response" in call_result:
                            response_data = call_result.get("response", {})
                            trace_info = call_result.get("trace_info", {})
                        else:
                            response_data = call_result
                            trace_info = {}

                        ok = True
                        error_message: Optional[str] = None
                        if not isinstance(response_data, dict):
                            ok = False
                            error_message = "Expert 返回格式异常（非 JSON 对象）"
                            response_data = {"result": response_data}
                        else:
                            if response_data.get("success") is False:
                                ok = False
                                error_message = (
                                    response_data.get("error")
                                    or response_data.get("message")
                                    or "Expert 返回 success=false"
                                )
                            elif response_data.get("error"):
                                ok = False
                                error_message = str(response_data.get("error"))

                        if trace_info:
                            try:
                                from app.services.job_service import JobService

                                job_service = JobService(task_db)
                                result_summary = None
                                if isinstance(response_data, dict):
                                    result_summary = {
                                        "content_id": content_id,
                                        "success": ok,
                                        "score": response_data.get("score"),
                                        "reason": response_data.get("reason"),
                                        "message": response_data.get("message"),
                                    }
                                trace_info["status"] = "success" if ok else "failed"
                                if error_message:
                                    trace_info["error_message"] = error_message
                                await job_service._save_trace(
                                    trace_info=trace_info,
                                    plugin_config_snapshot=plugin_config_snapshot,
                                    rendered_prompt=prompt,
                                    result_summary=result_summary,
                                )
                            except Exception as trace_e:
                                logger.error(f"[CRITIC Task] Failed to save trace: {trace_e}")

                        await task_sub_job_service.create_business_result(
                            ExpertBusinessResultCreate(
                                job_id=job_id,
                                sub_job_id=sub_job_id,
                                content_id=content_id,
                                expert_task_id=expert_task.id,
                                expert_config_code=expert_config_code,
                                expert_config_name=task_expert_config.expert_config_name,
                                model_code=task_expert_config.model_code,
                                business_type=task_expert_config.expert_type.upper(),
                                plugin_config_snapshot=plugin_config_snapshot,
                                prompt=prompt,
                                business_result=response_data if isinstance(response_data, dict) else {"result": response_data},
                                status="SUCCESS" if ok else "FAILED",
                                error_message=error_message,
                                plan_index=sub_job.plan_index,
                            ),
                            auto_commit=False,
                        )

                        if not ok:
                            await task_db.commit()
                            logger.error(
                                f"[CRITIC Task] Expert response invalid for sub_job {sub_job_id}: {error_message}"
                            )
                            return False

                        business_type = task_expert_config.expert_type.upper()
                        if business_type in ("CRITIC", "BAN") and isinstance(response_data, dict):
                            try:
                                critic_score = response_data.get("score")
                                if critic_score is not None:
                                    job_result = await task_db.execute(
                                        select(Job).where(Job.job_id == job_id)
                                    )
                                    job_for_tenant = job_result.scalar_one_or_none()
                                    critic_score_service = CriticScoreService(task_db)
                                    from app.services.critic_score_service import BAN_EXPERT_FUNCS

                                    expert_func = task_expert_config.expert_func
                                    score_int = int(critic_score)
                                    passed_from_api = response_data.get("passed")
                                    if passed_from_api is not None:
                                        passed = bool(passed_from_api)
                                    else:
                                        passed = score_int == 1 if expert_func in BAN_EXPERT_FUNCS else score_int >= 60
                                    await critic_score_service.create_score_record(
                                        job_id=job_id,
                                        sub_job_id=sub_job_id,
                                        content_id=content_id,
                                        expert_config_code=expert_config_code,
                                        expert_func=expert_func,
                                        score=score_int,
                                        passed=passed,
                                        reason=response_data.get("reason"),
                                        highlights=response_data.get("highlights"),
                                        problem_tags=response_data.get("problem_tags"),
                                        problem_snippets=response_data.get("problem_snippets"),
                                        expert_task_id=expert_task.id,
                                        model_code=task_expert_config.model_code,
                                        trace_id=trace_data.trace_id if trace_data else None,
                                        source_type="job",
                                        tenant_id=job_for_tenant.tenant_id if job_for_tenant else None,
                                        activity_id=job_for_tenant.activity_id if job_for_tenant else None,
                                        auto_commit=False,
                                    )
                            except Exception as score_record_err:
                                logger.warning(f"[CRITIC Task] Failed to save critic_score_record: {score_record_err}")

                        if isinstance(response_data, dict):
                            score = response_data.get("score")
                            should_check = False
                            if job.zero_score_invalid_expert_codes is None:
                                should_check = True
                            else:
                                should_check = expert_config_code in job.zero_score_invalid_expert_codes
                            if should_check and score is not None:
                                try:
                                    score_int = int(score)
                                except Exception:
                                    score_int = None
                                if score_int == 0:
                                    await task_sub_job_service.set_content_valid(
                                        content_id,
                                        0,
                                        auto_commit=False,
                                    )
                                    sj_result = await task_db.execute(
                                        select(SubJob).where(SubJob.sub_job_id == sub_job_id)
                                    )
                                    sj_in_db = sj_result.scalar_one_or_none()
                                    if sj_in_db:
                                        complete_list = list(sub_job.expert_complete_list or [])
                                        if expert_config_code not in complete_list:
                                            complete_list.append(expert_config_code)
                                        await task_db.execute(
                                            update(SubJob)
                                            .where(SubJob.sub_job_id == sub_job_id)
                                            .values(
                                                status="COMPLETED",
                                                expert_complete_list=complete_list,
                                            )
                                        )
                                    await task_db.commit()
                                    return True

                        await task_sub_job_service.add_expert_complete(
                            sub_job_id,
                            expert_config_code,
                            auto_commit=False,
                        )
                        await ExpertTaskExecutor._check_and_complete_sub_job(
                            task_db,
                            sub_job_id,
                            auto_commit=False,
                        )
                        await task_db.commit()
                        logger.info(f"[CRITIC Task] Successfully processed sub_job: {sub_job_id}")
                        return True

                except Exception as e:
                    logger.error(f"[CRITIC Task] Error processing sub_job: {e}")
                    return False

        # 并发处理 sub_jobs（最多5个并发）
        # 使用 try-finally 确保无论异常与否都重置状态
        batch_size = max(1, settings.JOB_CRITIC_BATCH_SIZE)
        try:
            for i in range(0, len(pending_sub_jobs), batch_size):
                batch = pending_sub_jobs[i:i + batch_size]
                tasks = [process_one_sub_job(sj) for sj in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                success_count = sum(1 for r in results if r is True)
                logger.info(
                    f"[CRITIC Task] Batch {i // batch_size + 1} completed: {success_count}/{len(batch)} successful")
        finally:
            # ✅ 关键修复：确保无论异常与否都重置状态为 PENDING
            # 防止批处理异常导致 ExpertTask 永久停留在 RUNNING 状态
            try:
                expert_task.status = ExpertTaskExecutor.STATUS_PENDING
                await db.commit()
                logger.info(f"[CRITIC Task] Reset status to PENDING for next run")
            except Exception as reset_error:
                logger.error(f"[CRITIC Task] Failed to reset status: {reset_error}")
                # 尝试使用新的 session 重置
                try:
                    async with AsyncSessionLocal() as reset_db:
                        await reset_db.execute(
                            update(ExpertTask)
                            .where(ExpertTask.id == expert_task.id)
                            .values(status=ExpertTaskExecutor.STATUS_PENDING)
                        )
                        await reset_db.commit()
                        logger.info(f"[CRITIC Task] Successfully reset status using new session")
                except Exception as final_error:
                    logger.error(f"[CRITIC Task] Critical: failed to reset status with new session: {final_error}")

    @staticmethod
    async def _check_and_complete_sub_job(
        db: AsyncSession,
        sub_job_id: str,
        *,
        auto_commit: bool = True,
    ) -> None:
        """检查并完成 sub_job"""
        from sqlalchemy.exc import SQLAlchemyError
        import asyncio

        result = await db.execute(
            select(SubJob).where(SubJob.sub_job_id == sub_job_id)
        )
        sub_job = result.scalar_one_or_none()

        if sub_job:
            expert_list = set(sub_job.expert_list or [])
            expert_complete_list = set(sub_job.expert_complete_list or [])

            if expert_list == expert_complete_list:
                sub_job.status = "COMPLETED"

                # ❌ BUG: 不应该释放槽位！plan_index 槽位代表"生成的第几篇文章"，一旦被占用应该永久占用
                # 释放槽位会导致同一 plan_index 被重复执行，造成文章分布不均
                # 参考: https://github.com/anthropics/claude-code/issues/xxx
                # try:
                #     from app.services.slot_status_cache_service import SlotStatusCacheService
                #     job_id = sub_job.job_id
                #     plan_index = sub_job.plan_index
                #     await SlotStatusCacheService.mark_slot_released(job_id, plan_index)
                #     logger.info(f"[ExpertTaskExecutor] Released slot {plan_index} for job_id={job_id}")
                # except Exception as slot_error:
                #     logger.warning(f"[ExpertTaskExecutor] Failed to release slot: {slot_error}")

                # 所有专家执行完毕，且未被中途标记为无效 (is_valid=0)，则正式启用该文章

                # ✅ 增强：添加异常处理
                try:
                    await db.execute(
                        update(Content)
                        .where(Content.content_id == sub_job.content_id, Content.is_valid.is_(None))
                        .values(is_valid=1)
                    )
                    if auto_commit:
                        await asyncio.wait_for(db.commit(), timeout=10.0)
                    else:
                        await asyncio.wait_for(db.flush(), timeout=10.0)
                    logger.info(f"[ExpertTaskExecutor] Sub_job and Content completed successfully: {sub_job_id}")
                except asyncio.TimeoutError:
                    logger.error(f"[ExpertTaskExecutor] Timeout completing sub_job {sub_job_id}")
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                except SQLAlchemyError as e:
                    logger.error(f"[ExpertTaskExecutor] Database error completing sub_job {sub_job_id}: {e}")
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                except SQLAlchemyError as e:
                    logger.error(f"[ExpertTaskExecutor] Database error completing sub_job {sub_job_id}: {e}")
                    try:
                        await db.rollback()
                    except Exception:
                        pass

    @staticmethod
    async def _fetch_node_names(
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
        from app.core.config import settings

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

    @staticmethod
    async def _extract_context_list(
            plugin_config_snapshot: Optional[List[Dict[str, Any]]],
            strategy_combo: Optional[Dict[str, Any]] = None,
            tenant_code: str = "default"
    ) -> Dict[str, str]:
        """
        从 plugin_config_snapshot 中提取结构化的 context_list

        Args:
            plugin_config_snapshot: 插件配置快照
            strategy_combo: 策略组合，格式: {
                "persona": {"id": "xxx", "name": "旺玥", "label": "人设"},
                "scenario": {"id": "yyy", "name": "换季期", "label": "场景"}
            }
            tenant_code: 租户编码

        Returns:
            结构化的变量映射字典，如: {"写者": "生活美学家", "目的": "好物分享"}
            - key: 变量名 (variable_name)
            - value: 选中的上下文名（节点名称，而非 node ID）
        """
        if not plugin_config_snapshot:
            return {}

        # 构建 node_id -> name 的映射（从 strategy_combo 中提取）
        # 支持两种格式：{id, name} 和 {node_id, node_name}
        node_id_to_name: Dict[str, str] = {}
        need_fetch_ids: List[str] = []

        if strategy_combo:
            for node_info in strategy_combo.values():
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
            fetched_names = await ExpertTaskExecutor._fetch_node_names(
                list(set(need_fetch_ids)),  # 去重
                tenant_code
            )
            node_id_to_name.update(fetched_names)

        # 构建 context_mapping
        context_mapping: Dict[str, str] = {}
        for plugin_item in plugin_config_snapshot:
            variable_mapping = plugin_item.get("variable_mapping", {})
            for var_name, context_names in variable_mapping.items():
                # 取第一个值（如果是数组）
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
                    # 直接存储的是 node.name，直接使用
                    context_mapping[var_name] = context_value

        return context_mapping


# 全局变量：保存主事件循环的引用
_main_event_loop = None


def set_main_event_loop(loop):
    """设置主事件循环引用（在应用启动时调用）"""
    global _main_event_loop
    _main_event_loop = loop
    logger.info(f"[Scheduler] Main event loop set: {loop}")


def execute_expert_task_sync(expert_task_id: int) -> None:
    """
    Expert Task 执行入口（同步 Wrapper）

    这是一个同步函数，用于包装异步函数 execute_expert_task。
    APScheduler 的线程池执行器会调用此函数。
    使用 run_coroutine_threadsafe 将任务提交到主事件循环执行，
    避免创建新的事件循环导致数据库连接绑定问题。
    """
    logger.info(f"[Scheduler] Triggered task execution for expert_task_id: {expert_task_id}")

    global _main_event_loop

    if _main_event_loop is None:
        logger.error(f"[Scheduler] Main event loop not set, cannot execute task {expert_task_id}")
        return

    try:
        # 将协程提交到主事件循环执行
        future = asyncio.run_coroutine_threadsafe(
            ExpertTaskExecutor.execute_expert_task(expert_task_id),
            _main_event_loop
        )
        # 等待任务完成（设置超时避免无限等待）
        future.result(timeout=3600)  # 1小时超时
    except Exception as e:
        logger.error(f"[Scheduler] Error executing task {expert_task_id}: {e}", exc_info=True)
