"""
TraceService - 追踪记录服务

提供追踪数据的存储、查询和统计功能
"""
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Tuple
import uuid

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expert_call_trace import ExpertCallTrace
from app.models.ab_experiment import ABExperiment
from app.models.trace_daily_stats import TraceDailyStats
from app.models.llm_model_route import LLMModelRoute
from app.models.job import Job
from app.models.job_business_context import JobBusinessContext
from decimal import Decimal
from app.constants.model_pricing import get_model_price_reference
from app.schemas.trace import (
    TraceSpanCreate,
    TraceListQuery,
    TraceStatsQuery,
    ReportTraceSpanRequest,
    ABExperimentCreate,
    ABExperimentUpdate,
    GenerationContextResponse,
    BusinessBackground,
    GenerationDetail,
    ExpertResultSummary,
)
from app.models.expert_business_result import ExpertBusinessResult
from app.models.expert_config import ExpertConfig

logger = logging.getLogger(__name__)


# 模型路由价格缓存 (key: f"{model_code}:{provider_code}", value: {input: Decimal, output: Decimal, currency: str, expiry: datetime})
# 简单缓存以减少数据库查询压力
_PRICE_CACHE = {}
_CACHE_TTL_SECONDS = 300  # 缓存 5 分钟


class TraceService:
    """追踪记录服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ Trace Span 操作 ============

    async def _get_model_route_price_info(self, model_code: str, provider_code: str) -> Optional[dict]:
        """获取模型路由价格信息（带内存缓存）"""
        if not model_code or not provider_code:
            return None
            
        cache_key = f"{model_code}:{provider_code}"
        now = datetime.now()
        
        # 1. 检查缓存
        if cache_key in _PRICE_CACHE:
            entry = _PRICE_CACHE[cache_key]
            if now < entry["expiry"]:
                return entry["data"]
        
        # 2. 查询数据库
        stmt = select(LLMModelRoute).where(
            LLMModelRoute.model_code == model_code,
            LLMModelRoute.provider_code == provider_code,
            LLMModelRoute.is_deleted == 0
        )
        result = await self.db.execute(stmt)
        route = result.scalar_one_or_none()
        
        if route:
            price_info = {
                "input": route.cost_per_1k_input,
                "output": route.cost_per_1k_output,
                "currency": route.currency or "USD"
            }
            # 更新缓存
            _PRICE_CACHE[cache_key] = {
                "data": price_info,
                "expiry": now + timedelta(seconds=_CACHE_TTL_SECONDS)
            }
            return price_info
            
        return None

    async def _calculate_and_set_trace_cost(self, trace: ExpertCallTrace):
        """
        统一计算并设置追踪记录的费用
        """
        # 基础校验：必须有模型和提供商信息，且有 token 使用
        if not trace.model_code or not trace.provider_code:
            if not trace.currency: trace.currency = "USD"
            return

        if trace.input_tokens <= 0 and trace.output_tokens <= 0:
            if not trace.currency: trace.currency = "USD"
            return

        try:
            # 优先从数据库/缓存获取路由配置（含价格和币种）
            route_info = await self._get_model_route_price_info(trace.model_code, trace.provider_code)
            
            input_cost = Decimal("0")
            output_cost = Decimal("0")
            currency = "USD"
            found_price = False

            if route_info:
                # 检查是否有价格配置
                if route_info.get("input") is not None or route_info.get("output") is not None:
                    cost_per_1k_input = route_info.get("input")
                    cost_per_1k_output = route_info.get("output")
                    currency = route_info.get("currency") or "USD"
                    
                    # 计算输入成本
                    if cost_per_1k_input and trace.input_tokens > 0:
                        input_cost = (Decimal(str(trace.input_tokens)) / Decimal("1000")) * cost_per_1k_input
                    
                    # 计算输出成本
                    if cost_per_1k_output and trace.output_tokens > 0:
                        output_cost = (Decimal(str(trace.output_tokens)) / Decimal("1000")) * cost_per_1k_output
                    
                    found_price = True

            # 如果数据库没有价格，尝试从静态参考库兜底
            if not found_price:
                ref_price = get_model_price_reference(trace.model_code)
                if ref_price:
                    input_cost = (Decimal(str(trace.input_tokens)) / Decimal("1000")) * ref_price["input"]
                    output_cost = (Decimal(str(trace.output_tokens)) / Decimal("1000")) * ref_price["output"]
                    currency = "USD"  # 参考库目前默认都是 USD
                    found_price = True
                    logger.info(f"[TraceService] Using Fallback Price for {trace.model_code}: {ref_price}")

            if found_price:
                trace.input_cost = input_cost
                trace.output_cost = output_cost
                trace.total_cost = input_cost + output_cost
                trace.currency = currency
                
                logger.info(
                    f"[TraceService] Calculated cost: total={trace.total_cost} {trace.currency} "
                    f"(in={input_cost}, out={output_cost}) for span={trace.span_id}"
                )
            else:
                logger.warning(f"[TraceService] No Price found (DB or Ref) for {trace.provider_code}/{trace.model_code}")
                if not trace.currency: trace.currency = "USD"
                
        except Exception as e:
            logger.error(f"[TraceService] Cost Calc Failed for span={trace.span_id}: {e}", exc_info=True)
            if not trace.currency: trace.currency = "USD"

    async def create_trace_span(self, data: TraceSpanCreate) -> ExpertCallTrace:
        """
        创建追踪 Span 记录
        """
        # 解析时间戳
        start_time = datetime.fromtimestamp(data.start_time_ms / 1000)
        end_time = datetime.fromtimestamp(data.end_time_ms / 1000) if data.end_time_ms else None
        
        # 解析结果摘要
        result_summary = None
        if data.result_summary_json:
            try:
                result_summary = json.loads(data.result_summary_json)
            except json.JSONDecodeError:
                result_summary = {"raw": data.result_summary_json}

        # 创建追踪实例
        trace = ExpertCallTrace(
            job_id=data.job_id,
            sub_job_id=data.sub_job_id,
            content_id=data.content_id,
            trace_id=data.trace_id,
            span_id=data.span_id,
            parent_span_id=data.parent_span_id,
            stage=data.stage,
            expert_config_code=data.expert_config_code,
            expert_type=data.expert_type,
            service_app=data.service_app,
            service_method=data.service_method,
            status=data.status,
            error_type=data.error_type,
            error_message=data.error_message,
            start_time=start_time,
            end_time=end_time,
            duration_ms=data.duration_ms,
            model_code=data.model_code,
            model_provider=data.provider_code,
            provider_code=data.provider_code,
            input_tokens=data.input_tokens,
            output_tokens=data.output_tokens,
            total_tokens=data.total_tokens,
            # 初始成本设为上报值，后续统一计算覆盖
            input_cost=Decimal(str(data.input_cost or 0.0)),
            output_cost=Decimal(str(data.output_cost or 0.0)),
            total_cost=Decimal(str(data.total_cost or 0.0)),
            experiment_id=data.experiment_id,
            experiment_group=data.experiment_group,
            experiment_variant=data.experiment_variant,
            result_summary=result_summary,
            source_log_id=data.source_log_id,
            source_log_table=data.source_log_table,
        )

        # 统一计算费用（中心化逻辑）
        await self._calculate_and_set_trace_cost(trace)
        
        self.db.add(trace)
        await self.db.commit()
        await self.db.refresh(trace)
        return trace

    async def aggregate_daily_stats(self, target_date: Optional[date] = None) -> int:
        """
        聚合每日统计数据 (ETL)
        将 expert_call_trace 的明细数据聚合到 trace_daily_stats
        
        Args:
            target_date: 指定聚合日期，默认为今天
        """
        if not target_date:
            target_date = datetime.now().date()
            
        logger.info(f"开始聚合每日统计: {target_date}")
        
        # 聚合 SQL：按日期、Provider、模型、阶段分组
        # 使用原生 SQL 以获得最佳性能和兼容性 (ON DUPLICATE KEY UPDATE)
        sql = """
        INSERT INTO trace_daily_stats (
            stat_date, stage, expert_config_code, provider_code, currency,
            total_count, success_count, failed_count, timeout_count,
            avg_duration_ms, total_input_tokens, total_output_tokens, total_cost,
            created_at, updated_at
        )
        SELECT 
            DATE(start_time) as stat_date,
            stage,
            expert_config_code,
            provider_code,
            COALESCE(currency, 'USD') as currency,
            COUNT(*) as total_count,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count,
            SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) as timeout_count,
            AVG(duration_ms) as avg_duration_ms,
            SUM(input_tokens) as total_input_tokens,
            SUM(output_tokens) as total_output_tokens,
            SUM(total_cost) as total_cost,
            NOW(), NOW()
        FROM expert_call_trace
        WHERE start_time >= :start_dt AND start_time < :end_dt
        GROUP BY DATE(start_time), stage, expert_config_code, provider_code, currency
        ON DUPLICATE KEY UPDATE
            total_count = VALUES(total_count),
            success_count = VALUES(success_count),
            failed_count = VALUES(failed_count),
            timeout_count = VALUES(timeout_count),
            avg_duration_ms = VALUES(avg_duration_ms),
            total_input_tokens = VALUES(total_input_tokens),
            total_output_tokens = VALUES(total_output_tokens),
            total_cost = VALUES(total_cost),
            updated_at = NOW();
        """
        
        from sqlalchemy import text
        
        try:
            # 聚合指定日期全天数据
            start_dt = datetime.combine(target_date, datetime.min.time())
            end_dt = datetime.combine(target_date + timedelta(days=1), datetime.min.time())
            
            result = await self.db.execute(
                text(sql), 
                {"start_dt": start_dt, "end_dt": end_dt}
            )
            await self.db.commit()
            
            rows = result.rowcount
            logger.info(f"聚合每日统计完成: {target_date}, 更新/插入 {rows} 条记录")
            return rows
        except Exception as e:
            await self.db.rollback()
            logger.error(f"聚合每日统计失败: {e}")
            raise e

    # ============ Admin Backfill ============

    async def recalc_trace_cost_batch(
        self,
        *,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        batch_size: int,
        last_id: int,
        dry_run: bool,
        only_if_price_found: bool = True,
    ) -> dict:
        """
        管理：按 DB 的 llm_model_route 定价回算 expert_call_trace 成本（分批游标）

        设计原则：
        - 仅使用 DB 定价（不使用静态参考价兜底），避免口径污染
        - 分批小事务，降低数据库压力
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if last_id < 0:
            raise ValueError("last_id must be >= 0")

        conditions = [ExpertCallTrace.id > last_id]
        if start_time is not None:
            conditions.append(ExpertCallTrace.start_time >= start_time)
        if end_time is not None:
            conditions.append(ExpertCallTrace.start_time < end_time)

        stmt = (
            select(ExpertCallTrace)
            .where(and_(*conditions))
            .order_by(ExpertCallTrace.id.asc())
            .limit(batch_size)
        )
        result = await self.db.execute(stmt)
        traces = list(result.scalars().all())

        processed = len(traces)
        if processed == 0:
            return {
                "processed": 0,
                "updated": 0,
                "missing_price": 0,
                "next_last_id": None,
                "old_total_cost_sum": "0",
                "new_total_cost_sum": "0",
                "delta_total_cost_sum": "0",
                "missing_price_top": {},
            }

        # 注意：commit/rollback 之后 ORM 对象可能被 expire，避免在事务结束后再访问 traces[*].xxx
        last_seen_id = traces[-1].id
        next_last_id = last_seen_id if processed == batch_size else None

        updated = 0
        missing_price = 0
        missing_counter: dict[str, int] = {}

        old_total_sum = Decimal("0")
        new_total_sum = Decimal("0")

        for t in traces:
            # 不具备计算条件（缺 model/provider 或 token 都为 0）直接跳过
            if not t.model_code or not t.provider_code:
                missing_price += 1
                key = f"{t.provider_code or 'unknown'}|{t.model_code or 'unknown'}"
                missing_counter[key] = missing_counter.get(key, 0) + 1
                continue
            if (t.input_tokens or 0) <= 0 and (t.output_tokens or 0) <= 0:
                continue

            route_info = await self._get_model_route_price_info(t.model_code, t.provider_code)
            if not route_info:
                missing_price += 1
                key = f"{t.provider_code}|{t.model_code}"
                missing_counter[key] = missing_counter.get(key, 0) + 1
                continue

            cost_per_1k_input = route_info.get("input")
            cost_per_1k_output = route_info.get("output")
            currency = route_info.get("currency") or "USD"

            # DB 中该路由没配置任何价格
            if cost_per_1k_input is None and cost_per_1k_output is None:
                missing_price += 1
                key = f"{t.provider_code}|{t.model_code}"
                missing_counter[key] = missing_counter.get(key, 0) + 1
                continue

            input_cost = Decimal("0")
            output_cost = Decimal("0")
            if cost_per_1k_input is not None and (t.input_tokens or 0) > 0:
                input_cost = (Decimal(str(t.input_tokens)) / Decimal("1000")) * cost_per_1k_input
            if cost_per_1k_output is not None and (t.output_tokens or 0) > 0:
                output_cost = (Decimal(str(t.output_tokens)) / Decimal("1000")) * cost_per_1k_output

            new_total = input_cost + output_cost
            old_total = t.total_cost if t.total_cost is not None else Decimal("0")

            if only_if_price_found:
                # 这里已经保证命中 DB 价格；若未来扩展更多规则，可继续在此处判断是否允许覆盖
                pass

            old_total_sum += old_total
            new_total_sum += new_total

            if not dry_run:
                t.input_cost = input_cost
                t.output_cost = output_cost
                t.total_cost = new_total
                t.currency = currency
                updated += 1
            else:
                # dry-run 仍统计“本应更新”的数量
                updated += 1

        # 仅返回 top N，避免响应过大
        missing_price_top = dict(
            sorted(missing_counter.items(), key=lambda kv: kv[1], reverse=True)[:20]
        )

        if dry_run:
            await self.db.rollback()
        else:
            await self.db.commit()

        return {
            "processed": processed,
            "updated": updated,
            "missing_price": missing_price,
            "next_last_id": next_last_id,
            "old_total_cost_sum": str(old_total_sum),
            "new_total_cost_sum": str(new_total_sum),
            "delta_total_cost_sum": str(new_total_sum - old_total_sum),
            "missing_price_top": missing_price_top,
        }

    async def rebuild_trace_daily_stats(self, *, start_date: date, end_date: date) -> dict:
        """
        管理：按日期范围重建 trace_daily_stats（逐日聚合）
        """
        if end_date < start_date:
            raise ValueError("end_date must be >= start_date")

        total_rows = 0
        days = 0
        d = start_date
        while d <= end_date:
            rows = await self.aggregate_daily_stats(target_date=d)
            total_rows += int(rows or 0)
            days += 1
            d = d + timedelta(days=1)

        return {
            "start_date": start_date,
            "end_date": end_date,
            "days": days,
            "total_rows_affected": total_rows,
        }

    async def create_from_report(self, data: ReportTraceSpanRequest) -> ExpertCallTrace:
        """
        从追踪上报请求创建追踪记录（历史兼容：旧回调协议，当前统一走 HTTP）
        """
        # 解析时间戳
        start_time = datetime.fromtimestamp(data.start_time_ms / 1000) if data.start_time_ms else datetime.now()
        end_time = datetime.fromtimestamp(data.end_time_ms / 1000) if data.end_time_ms else None
        
        # 解析结果摘要
        result_summary = None
        if data.result_summary_json:
            try:
                result_summary = json.loads(data.result_summary_json)
            except json.JSONDecodeError:
                result_summary = {"raw": data.result_summary_json}

        trace = ExpertCallTrace(
            job_id=data.job_id,
            sub_job_id=data.sub_job_id,
            content_id=data.content_id,
            trace_id=data.trace_id,
            span_id=data.span_id,
            parent_span_id=data.parent_span_id,
            stage=data.stage,
            expert_config_code=data.expert_config_code,
            service_app=data.service_app or "unknown",
            service_method=data.service_method or "unknown",
            status=data.status,
            error_type=data.error_type,
            error_message=data.error_message,
            start_time=start_time,
            end_time=end_time,
            duration_ms=data.duration_ms,
            model_code=data.model_code,
            input_tokens=data.input_tokens,
            output_tokens=data.output_tokens,
            total_tokens=data.total_tokens,
            provider_code=data.provider_code,
            input_cost=Decimal(str(data.input_cost or 0.0)),
            output_cost=Decimal(str(data.output_cost or 0.0)),
            total_cost=Decimal(str(data.total_cost or 0.0)),
            experiment_id=data.experiment_id,
            experiment_group=data.experiment_group,
            experiment_variant=data.experiment_variant,
            result_summary=result_summary,
            source_log_id=data.source_log_id,
            source_log_table=data.source_log_table,
        )
        
        # 统一计算费用（中心化逻辑）
        await self._calculate_and_set_trace_cost(trace)
        
        self.db.add(trace)
        await self.db.commit()
        await self.db.refresh(trace)
        return trace

    async def get_trace_by_id(self, trace_id: int) -> Optional[ExpertCallTrace]:
        """根据 ID 获取追踪记录"""
        stmt = select(ExpertCallTrace).where(ExpertCallTrace.id == trace_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_trace_by_trace_id(self, trace_id: str) -> Optional[ExpertCallTrace]:
        """
        根据 trace_id 获取追踪记录（优先返回根 Span）
        
        策略：
        1. 优先查找 parent_span_id 为空的记录（Root Span）
        2. 如果找不到，回退到按开始时间排序取第一条
        """
        # 1. 尝试查找根 Span (parent_span_id IS NULL)
        stmt_root = select(ExpertCallTrace).where(
            ExpertCallTrace.trace_id == trace_id,
            ExpertCallTrace.parent_span_id.is_(None)
        ).limit(1)
        result_root = await self.db.execute(stmt_root)
        root_trace = result_root.scalar_one_or_none()
        
        if root_trace:
            return root_trace
            
        # 2. 回退策略：按开始时间排序
        stmt = select(ExpertCallTrace).where(
            ExpertCallTrace.trace_id == trace_id
        ).order_by(ExpertCallTrace.start_time.asc()).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_spans_by_trace_id(self, trace_id: str) -> List[ExpertCallTrace]:
        """获取同一 trace_id 下的所有 span"""
        stmt = select(ExpertCallTrace).where(
            ExpertCallTrace.trace_id == trace_id
        ).order_by(ExpertCallTrace.start_time.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_spans_by_content_id(self, content_id: str) -> List[ExpertCallTrace]:
        """
        获取同一 content_id 下的所有 span（完整生产链路）
        
        包含：GE 生成 → AG 治理 → RLHF 审核 全流程
        """
        stmt = select(ExpertCallTrace).where(
            ExpertCallTrace.content_id == content_id
        ).order_by(ExpertCallTrace.start_time.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_full_trace_spans(
        self, 
        trace_id: str, 
        content_id: Optional[str] = None
    ) -> List[ExpertCallTrace]:
        """
        获取完整的生产链路 span
        
        优先通过 content_id 查询（包含所有阶段），
        如果没有 content_id，则回退到 trace_id 查询
        """
        if content_id:
            spans = await self.get_spans_by_content_id(content_id)
            if spans:
                return spans
        
        # 回退到 trace_id 查询
        return await self.get_spans_by_trace_id(trace_id)

    async def list_traces(
        self,
        query: TraceListQuery
    ) -> Tuple[List[ExpertCallTrace], int]:
        """
        查询追踪列表
        """
        # 构建查询条件
        conditions = []
        if query.job_id:
            conditions.append(ExpertCallTrace.job_id == query.job_id)
        if query.sub_job_id:
            conditions.append(ExpertCallTrace.sub_job_id == query.sub_job_id)
        if query.content_id:
            conditions.append(ExpertCallTrace.content_id == query.content_id)
        if query.trace_id:
            conditions.append(ExpertCallTrace.trace_id == query.trace_id)
        if query.stage:
            conditions.append(ExpertCallTrace.stage == query.stage)
        if query.status:
            conditions.append(ExpertCallTrace.status == query.status)
        if query.expert_config_code:
            conditions.append(ExpertCallTrace.expert_config_code == query.expert_config_code)
        if query.experiment_id:
            conditions.append(ExpertCallTrace.experiment_id == query.experiment_id)
        if query.start_date:
            conditions.append(ExpertCallTrace.created_at >= datetime.combine(query.start_date, datetime.min.time()))
        if query.end_date:
            conditions.append(ExpertCallTrace.created_at < datetime.combine(query.end_date + timedelta(days=1), datetime.min.time()))

        # 查询总数
        count_stmt = select(func.count()).select_from(ExpertCallTrace)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        # 查询列表
        stmt = select(ExpertCallTrace)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.order_by(ExpertCallTrace.created_at.desc())
        stmt = stmt.offset((query.page - 1) * query.page_size).limit(query.page_size)
        
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        
        return items, total

    async def get_trace_stats(self, query: TraceStatsQuery) -> dict:
        """
        获取追踪统计
        """
        # 基础条件
        conditions = [
            ExpertCallTrace.created_at >= datetime.combine(query.start_date, datetime.min.time()),
            ExpertCallTrace.created_at < datetime.combine(query.end_date + timedelta(days=1), datetime.min.time()),
        ]
        if query.stage:
            conditions.append(ExpertCallTrace.stage == query.stage)
        if query.expert_config_code:
            conditions.append(ExpertCallTrace.expert_config_code == query.expert_config_code)
        if query.experiment_id:
            conditions.append(ExpertCallTrace.experiment_id == query.experiment_id)

        # 根据分组维度构建查询
        if query.group_by == "date":
            group_column = func.date(ExpertCallTrace.created_at)
        elif query.group_by == "stage":
            group_column = ExpertCallTrace.stage
        elif query.group_by == "expert":
            group_column = ExpertCallTrace.expert_config_code
        elif query.group_by == "experiment":
            group_column = ExpertCallTrace.experiment_group
        else:
            group_column = func.date(ExpertCallTrace.created_at)

        # 分组统计
        stmt = select(
            group_column.label("dimension"),
            func.count().label("total_count"),
            func.sum(func.if_(ExpertCallTrace.status == "success", 1, 0)).label("success_count"),
            func.sum(func.if_(ExpertCallTrace.status == "failed", 1, 0)).label("failed_count"),
            func.sum(func.if_(ExpertCallTrace.status == "timeout", 1, 0)).label("timeout_count"),
            func.avg(ExpertCallTrace.duration_ms).label("avg_duration_ms"),
            func.sum(ExpertCallTrace.total_tokens).label("total_tokens"),
        ).where(and_(*conditions)).group_by(group_column).order_by(group_column)

        result = await self.db.execute(stmt)
        rows = result.all()

        items = []
        summary_total = 0
        summary_success = 0
        summary_failed = 0
        summary_timeout = 0
        summary_tokens = 0
        summary_duration_sum = 0
        summary_duration_count = 0

        for row in rows:
            total = row.total_count or 0
            success = row.success_count or 0
            failed = row.failed_count or 0
            timeout = row.timeout_count or 0
            success_rate = round(success / total * 100, 2) if total > 0 else 0

            items.append({
                "dimension": str(row.dimension) if row.dimension else "unknown",
                "total_count": total,
                "success_count": success,
                "failed_count": failed,
                "timeout_count": timeout,
                "success_rate": success_rate,
                "avg_duration_ms": round(row.avg_duration_ms, 2) if row.avg_duration_ms else None,
                "total_tokens": row.total_tokens or 0,
            })

            summary_total += total
            summary_success += success
            summary_failed += failed
            summary_timeout += timeout
            summary_tokens += row.total_tokens or 0
            if row.avg_duration_ms:
                summary_duration_sum += row.avg_duration_ms * total
                summary_duration_count += total

        summary = {
            "dimension": "summary",
            "total_count": summary_total,
            "success_count": summary_success,
            "failed_count": summary_failed,
            "timeout_count": summary_timeout,
            "success_rate": round(summary_success / summary_total * 100, 2) if summary_total > 0 else 0,
            "avg_duration_ms": round(summary_duration_sum / summary_duration_count, 2) if summary_duration_count > 0 else None,
            "total_tokens": summary_tokens,
        }

        return {
            "start_date": query.start_date,
            "end_date": query.end_date,
            "group_by": query.group_by,
            "items": items,
            "summary": summary,
        }

    # ============ A/B Experiment 操作 ============

    async def create_experiment(self, data: ABExperimentCreate, created_by: Optional[str] = None) -> ABExperiment:
        """创建 A/B 实验"""
        experiment_id = f"exp-{uuid.uuid4().hex[:12]}"
        
        experiment = ABExperiment(
            experiment_id=experiment_id,
            experiment_name=data.experiment_name,
            description=data.description,
            target_type=data.target_type,
            target_code=data.target_code,
            groups=[g.model_dump() for g in data.groups],
            traffic_ratio=data.traffic_ratio,
            metrics_config=data.metrics_config,
            status="draft",
            created_by=created_by,
        )
        
        self.db.add(experiment)
        await self.db.commit()
        await self.db.refresh(experiment)
        return experiment

    async def get_experiment(self, experiment_id: str) -> Optional[ABExperiment]:
        """获取实验详情"""
        stmt = select(ABExperiment).where(
            ABExperiment.experiment_id == experiment_id,
            ABExperiment.is_deleted == 0,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_experiment(
        self,
        experiment_id: str,
        data: ABExperimentUpdate
    ) -> Optional[ABExperiment]:
        """更新实验"""
        experiment = await self.get_experiment(experiment_id)
        if not experiment:
            return None
        
        if data.experiment_name is not None:
            experiment.experiment_name = data.experiment_name
        if data.description is not None:
            experiment.description = data.description
        if data.groups is not None:
            experiment.groups = [g.model_dump() for g in data.groups]
        if data.traffic_ratio is not None:
            experiment.traffic_ratio = data.traffic_ratio
        if data.metrics_config is not None:
            experiment.metrics_config = data.metrics_config
        
        await self.db.commit()
        await self.db.refresh(experiment)
        return experiment

    async def start_experiment(self, experiment_id: str) -> Optional[ABExperiment]:
        """启动实验"""
        experiment = await self.get_experiment(experiment_id)
        if not experiment:
            return None
        
        experiment.status = "running"
        experiment.start_time = datetime.now()
        
        await self.db.commit()
        await self.db.refresh(experiment)
        return experiment

    async def stop_experiment(self, experiment_id: str) -> Optional[ABExperiment]:
        """停止实验"""
        experiment = await self.get_experiment(experiment_id)
        if not experiment:
            return None
        
        experiment.status = "completed"
        experiment.end_time = datetime.now()
        
        await self.db.commit()
        await self.db.refresh(experiment)
        return experiment

    async def list_experiments(
        self,
        status: Optional[str] = None,
        target_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ABExperiment], int]:
        """列出实验"""
        conditions = [ABExperiment.is_deleted == 0]
        if status:
            conditions.append(ABExperiment.status == status)
        if target_type:
            conditions.append(ABExperiment.target_type == target_type)

        # 总数
        count_stmt = select(func.count()).select_from(ABExperiment).where(and_(*conditions))
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        # 列表
        stmt = select(ABExperiment).where(and_(*conditions))
        stmt = stmt.order_by(ABExperiment.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        
        return items, total

    async def get_active_experiment(
        self,
        target_type: str,
        target_code: Optional[str] = None
    ) -> Optional[ABExperiment]:
        """获取目标的活跃实验"""
        conditions = [
            ABExperiment.is_deleted == 0,
            ABExperiment.status == "running",
            ABExperiment.target_type == target_type,
        ]
        if target_code:
            conditions.append(
                or_(
                    ABExperiment.target_code == target_code,
                    ABExperiment.target_code.is_(None),
                )
            )

        stmt = select(ABExperiment).where(and_(*conditions)).order_by(ABExperiment.created_at.desc())
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ============ Daily Stats 操作 ============

    async def get_daily_stats(
        self,
        start_date: date,
        end_date: date,
        stage: Optional[str] = None,
        expert_config_code: Optional[str] = None,
    ) -> List[TraceDailyStats]:
        """获取每日统计"""
        conditions = [
            TraceDailyStats.stat_date >= start_date,
            TraceDailyStats.stat_date <= end_date,
        ]
        if stage:
            conditions.append(TraceDailyStats.stage == stage)
        if expert_config_code:
            conditions.append(TraceDailyStats.expert_config_code == expert_config_code)

        stmt = select(TraceDailyStats).where(and_(*conditions))
        stmt = stmt.order_by(TraceDailyStats.stat_date.asc())
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ============ 溯源背景数据聚合 ============

    async def get_generation_context(self, content_id: str) -> Optional[GenerationContextResponse]:
        """
        聚合文章生成的背景信息
        """
        # 1. 查询所有相关的 trace spans
        spans = await self.get_spans_by_content_id(content_id)
        if not spans:
            return None

        # 获取 job_id
        job_id = spans[0].job_id

        # 2. 查询 Job 基础信息
        job_stmt = select(Job).where(Job.job_id == job_id)
        job_res = await self.db.execute(job_stmt)
        job = job_res.scalar_one_or_none()
        if not job:
            return None

        # 3. 查询业务上下文
        context_stmt = select(JobBusinessContext).where(JobBusinessContext.job_id == job_id)
        context_res = await self.db.execute(context_stmt)
        context = context_res.scalar_one_or_none()

        # 4. 提取生成阶段的详情 (stage='generation' 或 'ge_generation')
        # 根据模型定义，stage 可能是 ge_generation 或 generation，这里做兼容
        gen_trace = next((s for s in spans if s.stage in ('generation', 'ge_generation')), None)
        
        gen_detail = None
        if gen_trace:
            gen_detail = GenerationDetail(
                expert_config_code=gen_trace.expert_config_code,
                model_code=gen_trace.model_code,
                rendered_prompt=gen_trace.rendered_prompt,
                result_summary=gen_trace.result_summary,
                input_tokens=gen_trace.input_tokens,
                output_tokens=gen_trace.output_tokens,
                total_tokens=gen_trace.total_tokens,
                duration_ms=gen_trace.duration_ms or 0,
                total_cost=float(gen_trace.total_cost or 0.0)
            )

        # 5. 组装背景信息
        background = BusinessBackground(
            job_name=job.job_name,
            job_description=job.description,
            agent_code=job.agent_code,
            tenant_id=job.tenant_id,
            activity_id=job.activity_id,
            platform_code=context.platform_code if context else None,
            brand_id=context.brand_id if context else None,
            campaign_id=context.campaign_id if context else None,
            extra_context=context.extra_context if context else None
        )

        # 6. 查询 Expert 业务执行结果
        expert_results_stmt = (
            select(ExpertBusinessResult)
            .where(
                ExpertBusinessResult.content_id == content_id,
                ExpertBusinessResult.is_deleted == 0
            )
            .order_by(ExpertBusinessResult.create_time.asc())
        )
        expert_results_res = await self.db.execute(expert_results_stmt)
        expert_results = expert_results_res.scalars().all()

        # 获取所有 expert_config_code 对应的 expert_func 和 expert_type
        config_codes = list(set(r.expert_config_code for r in expert_results))
        expert_config_map: dict[str, tuple[str | None, str | None]] = {}
        if config_codes:
            config_result = await self.db.execute(
                select(ExpertConfig.expert_config_code, ExpertConfig.expert_func, ExpertConfig.expert_type)
                .where(ExpertConfig.expert_config_code.in_(config_codes))
            )
            for row in config_result:
                expert_config_map[row.expert_config_code] = (row.expert_func, row.expert_type)

        expert_result_summaries = [
            ExpertResultSummary(
                id=r.id,
                expert_config_code=r.expert_config_code,
                expert_config_name=r.expert_config_name,
                expert_func=expert_config_map.get(r.expert_config_code, (None, None))[0],
                expert_type=expert_config_map.get(r.expert_config_code, (None, None))[1],
                model_code=r.model_code,
                business_type=r.business_type,
                plugin_config_snapshot=r.plugin_config_snapshot,
                prompt=r.prompt,
                business_result=r.business_result,
                status=r.status,
                error_message=r.error_message,
                create_time=r.create_time
            )
            for r in expert_results
        ]

        from app.schemas.trace import TraceSpanResponse

        return GenerationContextResponse(
            content_id=content_id,
            job_id=job_id,
            background=background,
            generation=gen_detail,
            spans=[TraceSpanResponse.model_validate(s) for s in spans],
            expert_results=expert_result_summaries
        )

