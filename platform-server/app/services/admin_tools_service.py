"""
Admin tools task service & runner

提供：
- 任务 CRUD（DB 持久化）
- 异步执行器：提交后后台执行并持续更新进度/结果
"""

from __future__ import annotations

import asyncio
import traceback
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, Any

from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.admin_tool_task import AdminToolTask
from app.services.trace_service import TraceService
from app.constants.model_pricing import get_model_price_reference


class AdminToolTaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_task(self, *, task_type: str, params: Optional[dict], created_by: Optional[str]) -> AdminToolTask:
        task = AdminToolTask(
            task_type=task_type,
            status="pending",
            progress=0,
            message="queued",
            params=params or None,
            created_by=created_by,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_task(self, task_id: int) -> Optional[AdminToolTask]:
        r = await self.db.execute(select(AdminToolTask).where(AdminToolTask.id == task_id))
        return r.scalar_one_or_none()

    async def list_tasks(
        self,
        *,
        status: Optional[str],
        task_type: Optional[str],
        created_by: Optional[str],
        page: int,
        page_size: int,
    ) -> tuple[list[AdminToolTask], int]:
        conditions = []
        if status:
            conditions.append(AdminToolTask.status == status)
        if task_type:
            conditions.append(AdminToolTask.task_type == task_type)
        if created_by:
            conditions.append(AdminToolTask.created_by == created_by)

        count_stmt = select(func.count()).select_from(AdminToolTask)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = select(AdminToolTask)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.order_by(AdminToolTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, total

    async def _update_task(
        self,
        task_id: int,
        *,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[dict] = None,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ) -> None:
        def _serialize(obj):
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_serialize(x) for x in obj]
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return str(obj)
            return obj

        task = await self.get_task(task_id)
        if not task:
            return
        if status is not None:
            task.status = status
        if progress is not None:
            task.progress = max(0, min(100, int(progress)))
        if message is not None:
            task.message = message
        if result is not None:
            task.result = _serialize(result)
        if error_message is not None:
            task.error_message = error_message
        if started_at is not None:
            task.started_at = started_at
        if finished_at is not None:
            task.finished_at = finished_at
        await self.db.commit()


class AdminToolTaskRunner:
    """
    后台执行器（进程内异步）

    - 使用独立 DB session
    - 执行过程中持续更新 admin_tool_task 表（进度/结果）
    """

    _semaphore = asyncio.Semaphore(1)  # 默认同一实例只跑 1 个管理任务，避免压垮 DB

    @classmethod
    def enqueue(cls, task_id: int) -> None:
        # fire-and-forget
        asyncio.create_task(cls._run(task_id))

    @classmethod
    async def _run(cls, task_id: int) -> None:
        async with cls._semaphore:
            async with async_session_factory() as db:
                svc = AdminToolTaskService(db)
                task = await svc.get_task(task_id)
                if not task:
                    return

                # 防止重复执行
                if task.status not in ("pending",):
                    return

                await svc._update_task(
                    task_id,
                    status="running",
                    progress=1,
                    message="running",
                    started_at=datetime.now(),
                )

                try:
                    params = task.params or {}
                    if task.task_type == "pricing_audit":
                        result = await cls._task_pricing_audit(params)
                    elif task.task_type == "trace_field_repair":
                        result = await cls._task_trace_field_repair(params)
                    elif task.task_type == "route_upsert_from_usage":
                        result = await cls._task_route_upsert_from_usage(params)
                    elif task.task_type == "cost_backfill":
                        result = await cls._task_cost_backfill(params)
                    elif task.task_type == "rebuild_daily_stats":
                        result = await cls._task_rebuild_daily_stats(params)
                    elif task.task_type == "verify_report":
                        result = await cls._task_verify_report(params)
                    else:
                        raise ValueError(f"Unknown task_type: {task.task_type}")

                    await svc._update_task(
                        task_id,
                        status="success",
                        progress=100,
                        message="success",
                        result=result,
                        finished_at=datetime.now(),
                    )
                except Exception as e:
                    await svc._update_task(
                        task_id,
                        status="failed",
                        progress=100,
                        message="failed",
                        error_message=f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=20)}",
                        finished_at=datetime.now(),
                    )

    # ---------------- task implementations ----------------

    @staticmethod
    async def _task_pricing_audit(params: dict) -> dict:
        """
        定价覆盖盘点（使用范围内历史用过的 provider+model 是否有路由/价格）
        """
        # 可选时间范围：start_date/end_date（YYYY-MM-DD）
        start_date = params.get("start_date")
        end_date = params.get("end_date")

        where_date = ""
        sql_params: dict[str, Any] = {}
        if start_date:
            where_date += " AND t.start_time >= :start_dt "
            sql_params["start_dt"] = f"{start_date} 00:00:00"
        if end_date:
            where_date += " AND t.start_time < :end_dt "
            # end_date inclusive -> +1 day
            ed = date.fromisoformat(end_date) + timedelta(days=1)
            sql_params["end_dt"] = f"{ed.isoformat()} 00:00:00"

        sql = f"""
WITH used AS (
  SELECT DISTINCT provider_code, model_code
  FROM expert_call_trace t
  WHERE t.provider_code IS NOT NULL AND t.provider_code <> ''
    AND t.model_code IS NOT NULL AND t.model_code <> ''
    {where_date}
),
route_agg AS (
  SELECT
    provider_code,
    model_code,
    MAX(CASE WHEN cost_per_1k_input IS NOT NULL OR cost_per_1k_output IS NOT NULL THEN 1 ELSE 0 END) AS has_any_price
  FROM llm_model_route
  WHERE is_deleted = 0
  GROUP BY provider_code, model_code
)
SELECT
  COUNT(*) AS used_distinct,
  SUM(CASE WHEN r.provider_code IS NULL THEN 1 ELSE 0 END) AS missing_route_distinct,
  SUM(CASE WHEN r.provider_code IS NOT NULL AND r.has_any_price = 0 THEN 1 ELSE 0 END) AS no_price_distinct,
  SUM(CASE WHEN r.provider_code IS NOT NULL AND r.has_any_price = 1 THEN 1 ELSE 0 END) AS has_price_distinct
FROM used u
LEFT JOIN route_agg r
  ON r.provider_code = u.provider_code AND r.model_code = u.model_code;
"""

        sql_missing_route_top = f"""
WITH route_agg AS (
  SELECT provider_code, model_code
  FROM llm_model_route
  WHERE is_deleted = 0
  GROUP BY provider_code, model_code
)
SELECT
  t.provider_code,
  t.model_code,
  COUNT(*) AS trace_count,
  MIN(t.start_time) AS first_seen_time,
  MAX(t.start_time) AS last_seen_time
FROM expert_call_trace t
LEFT JOIN route_agg r
  ON r.provider_code = t.provider_code AND r.model_code = t.model_code
WHERE t.provider_code IS NOT NULL AND t.provider_code <> ''
  AND t.model_code IS NOT NULL AND t.model_code <> ''
  {where_date}
  AND r.provider_code IS NULL
GROUP BY t.provider_code, t.model_code
ORDER BY trace_count DESC
LIMIT 200;
"""

        async with async_session_factory() as db:
            summary = (await db.execute(text(sql), sql_params)).mappings().one()
            missing_route_top = (await db.execute(text(sql_missing_route_top), sql_params)).mappings().all()

        return {
            "filters": {"start_date": start_date, "end_date": end_date},
            "summary": {k: (int(v) if v is not None else 0) for k, v in dict(summary).items()},
            "missing_route_top": [dict(r) for r in missing_route_top],
        }

    @staticmethod
    async def _task_trace_field_repair(params: dict) -> dict:
        default_provider = params.get("default_provider_code")
        default_model = params.get("default_model_code")
        if not default_provider and not default_model:
            raise ValueError("default_provider_code / default_model_code 至少提供一个")

        sqls = []
        if default_model:
            sqls.append(
                (
                    "model_code",
                    text(
                        "UPDATE expert_call_trace SET model_code=:v WHERE model_code IS NULL OR model_code='';"
                    ),
                    {"v": default_model},
                )
            )
        if default_provider:
            sqls.append(
                (
                    "provider_code",
                    text(
                        "UPDATE expert_call_trace SET provider_code=:v WHERE provider_code IS NULL OR provider_code='';"
                    ),
                    {"v": default_provider},
                )
            )

        counts: dict[str, int] = {}
        async with async_session_factory() as db:
            for name, stmt, p in sqls:
                r = await db.execute(stmt, p)
                counts[f"updated_{name}"] = int(r.rowcount or 0)
            await db.commit()

            verify = (await db.execute(
                text(
                    "SELECT "
                    "SUM(CASE WHEN provider_code IS NULL OR provider_code='' THEN 1 ELSE 0 END) AS missing_provider, "
                    "SUM(CASE WHEN model_code IS NULL OR model_code='' THEN 1 ELSE 0 END) AS missing_model "
                    "FROM expert_call_trace;"
                )
            )).mappings().one()

        return {"updated": counts, "missing_after": {k: int(v or 0) for k, v in dict(verify).items()}}

    @staticmethod
    async def _task_route_upsert_from_usage(params: dict) -> dict:
        """
        从历史用量补齐缺失路由（可选补价）
        params:
          - fill_price: bool (default true)
          - limit: int (default 200)
        """
        fill_price = bool(params.get("fill_price", True))
        limit = int(params.get("limit", 200))

        sql_missing = f"""
WITH route_agg AS (
  SELECT provider_code, model_code
  FROM llm_model_route
  WHERE is_deleted = 0
  GROUP BY provider_code, model_code
)
SELECT
  t.provider_code,
  t.model_code,
  COUNT(*) AS trace_count
FROM expert_call_trace t
LEFT JOIN route_agg r
  ON r.provider_code = t.provider_code AND r.model_code = t.model_code
WHERE t.provider_code IS NOT NULL AND t.provider_code <> ''
  AND t.model_code IS NOT NULL AND t.model_code <> ''
  AND r.provider_code IS NULL
GROUP BY t.provider_code, t.model_code
ORDER BY trace_count DESC
LIMIT {limit};
"""

        upsert_sql = text(
            """
INSERT INTO llm_model_route (
  model_code, model_name,
  provider_code, provider_model,
  priority, enabled,
  cost_per_1k_input, cost_per_1k_output,
  currency,
  is_deleted,
  create_time, update_time
)
VALUES (
  :model_code, :model_name,
  :provider_code, :provider_model,
  :priority, :enabled,
  :cost_in, :cost_out,
  :currency,
  0,
  NOW(), NOW()
)
ON DUPLICATE KEY UPDATE
  enabled = 1,
  cost_per_1k_input = COALESCE(llm_model_route.cost_per_1k_input, VALUES(cost_per_1k_input)),
  cost_per_1k_output = COALESCE(llm_model_route.cost_per_1k_output, VALUES(cost_per_1k_output)),
  currency = COALESCE(llm_model_route.currency, VALUES(currency)),
  update_time = NOW();
"""
        )

        def derive_price(model_code: str):
            if not fill_price:
                return None, None, "USD"
            ref = get_model_price_reference(model_code)
            if ref:
                return ref["input"], ref["output"], "USD"
            if model_code.startswith("aliyun-"):
                ref2 = get_model_price_reference(model_code.removeprefix("aliyun-"))
                if ref2:
                    return ref2["input"], ref2["output"], "USD"
            return None, None, "USD"

        applied: list[dict] = []
        async with async_session_factory() as db:
            missing = (await db.execute(text(sql_missing))).mappings().all()
            for row in missing:
                provider_code = row["provider_code"]
                model_code = row["model_code"]
                cost_in, cost_out, currency = derive_price(model_code)
                r = await db.execute(
                    upsert_sql,
                    {
                        "model_code": model_code,
                        "model_name": model_code,
                        "provider_code": provider_code,
                        "provider_model": model_code,
                        "priority": 50,
                        "enabled": 1,
                        "cost_in": cost_in,
                        "cost_out": cost_out,
                        "currency": currency,
                    },
                )
                applied.append(
                    {
                        "provider_code": provider_code,
                        "model_code": model_code,
                        "trace_count": int(row["trace_count"] or 0),
                        "cost_in": str(cost_in) if cost_in is not None else None,
                        "cost_out": str(cost_out) if cost_out is not None else None,
                        "currency": currency,
                        "rowcount": int(r.rowcount or 0),
                    }
                )
            await db.commit()

        return {"missing_count": len(applied), "applied": applied, "fill_price": fill_price}

    @staticmethod
    async def _task_cost_backfill(params: dict) -> dict:
        """
        成本回算（分批）
        params:
          - batch_size (default 2000)
          - start_time/end_time (optional ISO datetime)
        """
        batch_size = int(params.get("batch_size", 2000))
        start_time = params.get("start_time")
        end_time = params.get("end_time")

        # 允许传 ISO 字符串
        def parse_dt(v):
            if not v:
                return None
            return datetime.fromisoformat(v)

        st = parse_dt(start_time)
        et = parse_dt(end_time)

        last_id = 0
        total_processed = 0
        total_updated = 0
        total_missing = 0
        total_old = Decimal("0")
        total_new = Decimal("0")

        async with async_session_factory() as db:
            svc = TraceService(db)
            while True:
                r = await svc.recalc_trace_cost_batch(
                    start_time=st,
                    end_time=et,
                    batch_size=batch_size,
                    last_id=last_id,
                    dry_run=False,
                    only_if_price_found=True,
                )
                processed = int(r.get("processed") or 0)
                updated = int(r.get("updated") or 0)
                missing = int(r.get("missing_price") or 0)
                next_last = r.get("next_last_id")

                total_processed += processed
                total_updated += updated
                total_missing += missing
                total_old += Decimal(str(r.get("old_total_cost_sum") or "0"))
                total_new += Decimal(str(r.get("new_total_cost_sum") or "0"))

                if not next_last or processed == 0:
                    break
                last_id = int(next_last)

        return {
            "filters": {"start_time": start_time, "end_time": end_time, "batch_size": batch_size},
            "total_processed": total_processed,
            "total_updated": total_updated,
            "total_missing": total_missing,
            "old_total": str(total_old),
            "new_total": str(total_new),
            "delta_total": str(total_new - total_old),
        }

    @staticmethod
    async def _task_rebuild_daily_stats(params: dict) -> dict:
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        if not start_date or not end_date:
            raise ValueError("start_date/end_date required")
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)

        async with async_session_factory() as db:
            svc = TraceService(db)
            res = await svc.rebuild_trace_daily_stats(start_date=sd, end_date=ed)
        # res contains date objects; stringify
        return {**res, "start_date": start_date, "end_date": end_date}

    @staticmethod
    async def _task_verify_report(params: dict) -> dict:
        sql1 = text(
            """
SELECT
  COUNT(*) AS traces,
  SUM(COALESCE(total_cost,0)) AS total_cost_sum,
  SUM(COALESCE(input_cost,0)) AS input_cost_sum,
  SUM(COALESCE(output_cost,0)) AS output_cost_sum,
  SUM(CASE WHEN total_cost IS NULL THEN 1 ELSE 0 END) AS total_cost_null
FROM expert_call_trace;
"""
        )
        sql2 = text(
            """
SELECT
  COUNT(*) AS daily_rows,
  SUM(COALESCE(total_cost,0)) AS daily_total_cost_sum
FROM trace_daily_stats;
"""
        )
        async with async_session_factory() as db:
            a = (await db.execute(sql1)).mappings().one()
            b = (await db.execute(sql2)).mappings().one()
        return {
            "expert_call_trace": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in dict(a).items()},
            "trace_daily_stats": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in dict(b).items()},
        }


