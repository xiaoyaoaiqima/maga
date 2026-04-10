"""
CriticScoreService - Critic 评分记录服务
"""
# pylint: disable=not-callable

from datetime import datetime, date
from typing import Optional, List, Dict, Any, Iterable
from collections import Counter
import re

from sqlalchemy import select, func, and_, desc
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.critic_score_record import CriticScoreRecord


# BAN 类型的 expert_func 列表（合规封禁检查）
BAN_EXPERT_FUNCS = frozenset([
    "CriticIllegal",        # 不合法
    "CriticKeywordFilter",  # 违禁词
    "CriticUnreasonable",   # 不合理
    "CriticCounterproductive",  # 不合目的
    "CriticTencent",        # 腾讯风控
])


_RE_URL = re.compile(r"https?://\S+")
_RE_EN = re.compile(r"[a-zA-Z]{3,}")
_RE_CN_SEQ = re.compile(r"[\u4e00-\u9fff]{2,}")
_RE_SPLIT = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+")

_DEFAULT_STOPWORDS = {
    # 通用虚词
    "这个",
    "那个",
    "然后",
    "但是",
    "因为",
    "所以",
    "因此",
    "并且",
    "以及",
    "同时",
    "还是",
    "比较",
    "更加",
    "可能",
    "需要",
    "建议",
    "应该",
    "可以",
    "部分",
    "整体",
    "非常",
    "较为",
    "一些",
    "很多",
    "不够",
    "不足",
    # 业务常见但信息量低（可按需调整）
    "内容",
    "文章",
    "文本",
    "表达",
    "语言",
    "模型",
    "评分",
    "维度",
}


def _iter_reason_tokens(*, text: str, min_len: int) -> Iterable[str]:
    """
    简易切词：
    - 英文：提取 3+ 字母单词
    - 中文：优先按连续中文串抽取；长串用 2-gram 降噪拆分
    """
    if not text:
        return []

    normalized = _RE_URL.sub(" ", text)
    normalized = normalized.replace("\n", " ").replace("\r", " ").lower()
    normalized = _RE_SPLIT.sub(" ", normalized)

    tokens: List[str] = []
    tokens.extend(_RE_EN.findall(normalized))

    for seq in _RE_CN_SEQ.findall(normalized):
        seq = seq.strip()
        if len(seq) < min_len:
            continue
        if len(seq) <= 4:
            tokens.append(seq)
            continue
        # 长中文串用 2-gram 拆分，提升“词云”可读性
        tokens.extend([seq[i : i + 2] for i in range(0, len(seq) - 1)])

    return tokens


class CriticScoreService:
    """Critic 评分记录服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    @staticmethod
    def _build_expert_type_condition(expert_type: Optional[str]):
        """
        根据 expert_type 构建过滤条件
        
        Args:
            expert_type: BAN / CRITIC / None
            
        Returns:
            SQLAlchemy 条件或 None
        """
        if not expert_type:
            return None
        expert_type_upper = expert_type.upper()
        if expert_type_upper in ("BAN", "CRITIC"):
            return CriticScoreRecord.expert_type == expert_type_upper
        return None
    
    # ==================== 写入操作 ====================
    
    async def create_score_record(
        self,
        job_id: str,
        sub_job_id: str,
        content_id: str,
        expert_config_code: str,
        expert_func: str,
        score: int,
        passed: bool,
        reason: Optional[str] = None,
        highlights: Optional[str] = None,
        problem_context_list: Optional[List[str]] = None,
        problem_tags: Optional[List[str]] = None,
        problem_snippets: Optional[List[str]] = None,
        expert_task_id: Optional[int] = None,
        model_code: Optional[str] = None,
        provider_code: Optional[str] = None,
        duration_ms: Optional[int] = None,
        trace_id: Optional[str] = None,
        # === 来源标识 ===
        source_type: str = "job",
        # === job 场景专属 ===
        tenant_id: Optional[int] = None,
        activity_id: Optional[int] = None,
        # === eval_run 场景专属 ===
        dataset_code: Optional[str] = None,
        run_id: Optional[int] = None,
        test_case_id: Optional[int] = None,
        # === debug 场景专属 ===
        debug_history_id: Optional[int] = None,
        # === 专家类型 ===
        expert_type: Optional[str] = None,
        auto_commit: bool = True,
    ) -> CriticScoreRecord:
        """创建评分记录"""
        # 计算版本号：同一 content_id + expert_func 递增
        version = await self._get_next_version(content_id, expert_func)
        
        # 自动推断 expert_type（如果未提供）
        if not expert_type:
            expert_type = "BAN" if expert_func in BAN_EXPERT_FUNCS else "CRITIC"
        
        record = CriticScoreRecord(
            job_id=job_id,
            sub_job_id=sub_job_id,
            content_id=content_id,
            source_type=source_type,
            # job 场景专属
            tenant_id=tenant_id,
            activity_id=activity_id,
            # eval_run 场景专属
            dataset_code=dataset_code,
            run_id=run_id,
            test_case_id=test_case_id,
            # debug 场景专属
            debug_history_id=debug_history_id,
            # 通用字段
            expert_task_id=expert_task_id,
            expert_config_code=expert_config_code,
            expert_func=expert_func,
            expert_type=expert_type,
            model_code=model_code,
            provider_code=provider_code,
            score=score,
            passed=1 if passed else 0,
            reason=reason,
            highlights=highlights,
            problem_context_list=problem_context_list or [],
            problem_tags=problem_tags or [],
            problem_snippets=problem_snippets or [],
            duration_ms=duration_ms,
            trace_id=trace_id,
            version=version,
        )
        
        self.db.add(record)
        if auto_commit:
            await self.db.commit()
            await self.db.refresh(record)
        else:
            await self.db.flush()
        return record
    
    async def _get_next_version(self, content_id: str, expert_func: str) -> int:
        """获取下一个版本号"""
        stmt = select(func.max(CriticScoreRecord.version)).where(
            and_(
                CriticScoreRecord.content_id == content_id,
                CriticScoreRecord.expert_func == expert_func,
            )
        )
        result = await self.db.execute(stmt)
        max_version = result.scalar()
        return (max_version or 0) + 1
    
    # ==================== 查询操作 ====================
    
    async def get_by_id(self, record_id: int) -> Optional[CriticScoreRecord]:
        """根据 ID 获取记录"""
        stmt = select(CriticScoreRecord).where(CriticScoreRecord.id == record_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_records(
        self,
        job_id: Optional[str] = None,
        content_id: Optional[str] = None,
        source_type: Optional[str] = None,
        # job 场景筛选
        tenant_id: Optional[int] = None,
        activity_id: Optional[int] = None,
        # eval_run 场景筛选
        dataset_code: Optional[str] = None,
        run_id: Optional[int] = None,
        test_case_id: Optional[int] = None,
        # debug 场景筛选
        debug_history_id: Optional[int] = None,
        # 通用筛选
        expert_func: Optional[str] = None,
        model_code: Optional[str] = None,
        score_min: Optional[int] = None,
        score_max: Optional[int] = None,
        passed: Optional[bool] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[CriticScoreRecord]:
        """列表查询评分记录"""
        stmt = select(CriticScoreRecord)
        
        conditions = []
        if job_id:
            conditions.append(CriticScoreRecord.job_id == job_id)
        if content_id:
            conditions.append(CriticScoreRecord.content_id == content_id)
        if source_type:
            conditions.append(CriticScoreRecord.source_type == source_type)
        # job 场景
        if tenant_id is not None:
            conditions.append(CriticScoreRecord.tenant_id == tenant_id)
        if activity_id is not None:
            conditions.append(CriticScoreRecord.activity_id == activity_id)
        # eval_run 场景
        if dataset_code:
            conditions.append(CriticScoreRecord.dataset_code == dataset_code)
        if run_id is not None:
            conditions.append(CriticScoreRecord.run_id == run_id)
        if test_case_id is not None:
            conditions.append(CriticScoreRecord.test_case_id == test_case_id)
        # debug 场景
        if debug_history_id is not None:
            conditions.append(CriticScoreRecord.debug_history_id == debug_history_id)
        # 通用
        if expert_func:
            conditions.append(CriticScoreRecord.expert_func == expert_func)
        if model_code:
            conditions.append(CriticScoreRecord.model_code == model_code)
        if score_min is not None:
            conditions.append(CriticScoreRecord.score >= score_min)
        if score_max is not None:
            conditions.append(CriticScoreRecord.score <= score_max)
        if passed is not None:
            conditions.append(CriticScoreRecord.passed == (1 if passed else 0))
        if start_date:
            conditions.append(CriticScoreRecord.create_time >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            conditions.append(CriticScoreRecord.create_time <= datetime.combine(end_date, datetime.max.time()))
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        stmt = stmt.order_by(desc(CriticScoreRecord.create_time)).offset(skip).limit(limit)
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_content_history(
        self,
        content_id: str,
        expert_func: Optional[str] = None,
    ) -> List[CriticScoreRecord]:
        """获取某内容的历史评分"""
        stmt = select(CriticScoreRecord).where(CriticScoreRecord.content_id == content_id)
        
        if expert_func:
            stmt = stmt.where(CriticScoreRecord.expert_func == expert_func)
        
        stmt = stmt.order_by(desc(CriticScoreRecord.create_time))
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def count_records(
        self,
        job_id: Optional[str] = None,
        content_id: Optional[str] = None,
        source_type: Optional[str] = None,
        # job 场景筛选
        tenant_id: Optional[int] = None,
        activity_id: Optional[int] = None,
        # eval_run 场景筛选
        dataset_code: Optional[str] = None,
        run_id: Optional[int] = None,
        test_case_id: Optional[int] = None,
        # debug 场景筛选
        debug_history_id: Optional[int] = None,
        # 通用筛选
        expert_func: Optional[str] = None,
        model_code: Optional[str] = None,
        passed: Optional[bool] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> int:
        """统计记录数"""
        stmt = select(func.count(CriticScoreRecord.id))
        
        conditions = []
        if job_id:
            conditions.append(CriticScoreRecord.job_id == job_id)
        if content_id:
            conditions.append(CriticScoreRecord.content_id == content_id)
        if source_type:
            conditions.append(CriticScoreRecord.source_type == source_type)
        # job 场景
        if tenant_id is not None:
            conditions.append(CriticScoreRecord.tenant_id == tenant_id)
        if activity_id is not None:
            conditions.append(CriticScoreRecord.activity_id == activity_id)
        # eval_run 场景
        if dataset_code:
            conditions.append(CriticScoreRecord.dataset_code == dataset_code)
        if run_id is not None:
            conditions.append(CriticScoreRecord.run_id == run_id)
        if test_case_id is not None:
            conditions.append(CriticScoreRecord.test_case_id == test_case_id)
        # debug 场景
        if debug_history_id is not None:
            conditions.append(CriticScoreRecord.debug_history_id == debug_history_id)
        # 通用
        if expert_func:
            conditions.append(CriticScoreRecord.expert_func == expert_func)
        if model_code:
            conditions.append(CriticScoreRecord.model_code == model_code)
        if passed is not None:
            conditions.append(CriticScoreRecord.passed == (1 if passed else 0))
        if start_date:
            conditions.append(CriticScoreRecord.create_time >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            conditions.append(CriticScoreRecord.create_time <= datetime.combine(end_date, datetime.max.time()))
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        result = await self.db.execute(stmt)
        return result.scalar() or 0
    
    # ==================== 统计分析 ====================
    
    async def get_summary_stats(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        expert_func: Optional[str] = None,
        model_code: Optional[str] = None,
        source_type: Optional[str] = None,
        # job 场景筛选
        tenant_id: Optional[int] = None,
        activity_id: Optional[int] = None,
        job_id: Optional[str] = None,
        # eval_run 场景筛选
        dataset_code: Optional[str] = None,
        # expert_type 过滤：BAN / CRITIC
        expert_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取汇总统计"""
        conditions = []
        if start_date:
            conditions.append(CriticScoreRecord.create_time >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            conditions.append(CriticScoreRecord.create_time <= datetime.combine(end_date, datetime.max.time()))
        if expert_func:
            conditions.append(CriticScoreRecord.expert_func == expert_func)
        if model_code:
            conditions.append(CriticScoreRecord.model_code == model_code)
        if source_type:
            conditions.append(CriticScoreRecord.source_type == source_type)
        # job 场景
        if tenant_id is not None:
            conditions.append(CriticScoreRecord.tenant_id == tenant_id)
        if activity_id is not None:
            conditions.append(CriticScoreRecord.activity_id == activity_id)
        if job_id:
            conditions.append(CriticScoreRecord.job_id == job_id)
        # eval_run 场景
        if dataset_code:
            conditions.append(CriticScoreRecord.dataset_code == dataset_code)
        # expert_type 过滤
        type_cond = self._build_expert_type_condition(expert_type)
        if type_cond is not None:
            conditions.append(type_cond)
        
        stmt = select(
            func.count(CriticScoreRecord.id).label("total_count"),
            func.sum(CriticScoreRecord.passed).label("passed_count"),
            func.avg(CriticScoreRecord.score).label("avg_score"),
            func.min(CriticScoreRecord.score).label("min_score"),
            func.max(CriticScoreRecord.score).label("max_score"),
            func.avg(CriticScoreRecord.duration_ms).label("avg_duration_ms"),
        )
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        result = await self.db.execute(stmt)
        row = result.one()
        
        total_count = row.total_count or 0
        passed_count = row.passed_count or 0
        
        return {
            "total_count": total_count,
            "passed_count": passed_count,
            "pass_rate": round(passed_count / total_count * 100, 2) if total_count > 0 else 0,
            "avg_score": round(row.avg_score, 2) if row.avg_score else 0,
            "min_score": row.min_score or 0,
            "max_score": row.max_score or 0,
            "avg_duration_ms": round(row.avg_duration_ms, 2) if row.avg_duration_ms else 0,
        }
    
    async def get_trend_data(
        self,
        start_date: date,
        end_date: date,
        expert_func: Optional[str] = None,
        model_code: Optional[str] = None,
        source_type: Optional[str] = None,
        # job 场景筛选
        tenant_id: Optional[int] = None,
        activity_id: Optional[int] = None,
        job_id: Optional[str] = None,
        # eval_run 场景筛选
        dataset_code: Optional[str] = None,
        # expert_type 过滤：BAN / CRITIC
        expert_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """获取趋势数据（按天聚合）"""
        conditions = [
            CriticScoreRecord.create_time >= datetime.combine(start_date, datetime.min.time()),
            CriticScoreRecord.create_time <= datetime.combine(end_date, datetime.max.time()),
        ]
        if expert_func:
            conditions.append(CriticScoreRecord.expert_func == expert_func)
        if model_code:
            conditions.append(CriticScoreRecord.model_code == model_code)
        if source_type:
            conditions.append(CriticScoreRecord.source_type == source_type)
        # job 场景
        if tenant_id is not None:
            conditions.append(CriticScoreRecord.tenant_id == tenant_id)
        if activity_id is not None:
            conditions.append(CriticScoreRecord.activity_id == activity_id)
        if job_id:
            conditions.append(CriticScoreRecord.job_id == job_id)
        # eval_run 场景
        if dataset_code:
            conditions.append(CriticScoreRecord.dataset_code == dataset_code)
        # expert_type 过滤
        type_cond = self._build_expert_type_condition(expert_type)
        if type_cond is not None:
            conditions.append(type_cond)
        
        stmt = select(
            func.date(CriticScoreRecord.create_time).label("stat_date"),
            func.count(CriticScoreRecord.id).label("total_count"),
            func.sum(CriticScoreRecord.passed).label("passed_count"),
            func.avg(CriticScoreRecord.score).label("avg_score"),
        ).where(
            and_(*conditions)
        ).group_by(
            func.date(CriticScoreRecord.create_time)
        ).order_by(
            func.date(CriticScoreRecord.create_time)
        )
        
        result = await self.db.execute(stmt)
        rows = result.all()
        
        return [
            {
                "date": str(row.stat_date),
                "total_count": row.total_count or 0,
                "passed_count": row.passed_count or 0,
                "pass_rate": round((row.passed_count or 0) / row.total_count * 100, 2) if row.total_count else 0,
                "avg_score": round(row.avg_score, 2) if row.avg_score else 0,
            }
            for row in rows
        ]
    
    async def get_model_comparison(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        expert_func: Optional[str] = None,
        source_type: Optional[str] = None,
        # job 场景筛选
        tenant_id: Optional[int] = None,
        activity_id: Optional[int] = None,
        job_id: Optional[str] = None,
        # eval_run 场景筛选
        dataset_code: Optional[str] = None,
        # expert_type 过滤：BAN / CRITIC
        expert_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """获取模型对比数据"""
        conditions = []
        if start_date:
            conditions.append(CriticScoreRecord.create_time >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            conditions.append(CriticScoreRecord.create_time <= datetime.combine(end_date, datetime.max.time()))
        if expert_func:
            conditions.append(CriticScoreRecord.expert_func == expert_func)
        if source_type:
            conditions.append(CriticScoreRecord.source_type == source_type)
        # job 场景
        if tenant_id is not None:
            conditions.append(CriticScoreRecord.tenant_id == tenant_id)
        if activity_id is not None:
            conditions.append(CriticScoreRecord.activity_id == activity_id)
        if job_id:
            conditions.append(CriticScoreRecord.job_id == job_id)
        # eval_run 场景
        if dataset_code:
            conditions.append(CriticScoreRecord.dataset_code == dataset_code)
        # expert_type 过滤
        type_cond = self._build_expert_type_condition(expert_type)
        if type_cond is not None:
            conditions.append(type_cond)
        
        stmt = select(
            CriticScoreRecord.model_code,
            func.count(CriticScoreRecord.id).label("total_count"),
            func.sum(CriticScoreRecord.passed).label("passed_count"),
            func.avg(CriticScoreRecord.score).label("avg_score"),
            func.avg(CriticScoreRecord.duration_ms).label("avg_duration_ms"),
        ).where(
            CriticScoreRecord.model_code.isnot(None)
        )
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        stmt = stmt.group_by(CriticScoreRecord.model_code).order_by(desc(func.count(CriticScoreRecord.id)))
        
        result = await self.db.execute(stmt)
        rows = result.all()
        
        return [
            {
                "model_code": row.model_code,
                "total_count": row.total_count or 0,
                "passed_count": row.passed_count or 0,
                "pass_rate": round((row.passed_count or 0) / row.total_count * 100, 2) if row.total_count else 0,
                "avg_score": round(row.avg_score, 2) if row.avg_score else 0,
                "avg_duration_ms": round(row.avg_duration_ms, 2) if row.avg_duration_ms else 0,
            }
            for row in rows
        ]
    
    async def get_score_distribution(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        expert_func: Optional[str] = None,
        model_code: Optional[str] = None,
        source_type: Optional[str] = None,
        # job 场景筛选
        tenant_id: Optional[int] = None,
        activity_id: Optional[int] = None,
        job_id: Optional[str] = None,
        # eval_run 场景筛选
        dataset_code: Optional[str] = None,
        bucket_size: int = 10,
        # expert_type 过滤：BAN / CRITIC
        expert_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取分数分布（直方图数据）
        
        逻辑：
        - 选了维度（expert_func）：直接按该维度分数分布
        - 没选维度：同一篇文章（content_id）多维度分数取平均后再统计分布
        """
        conditions = []
        if start_date:
            conditions.append(CriticScoreRecord.create_time >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            conditions.append(CriticScoreRecord.create_time <= datetime.combine(end_date, datetime.max.time()))
        if expert_func:
            conditions.append(CriticScoreRecord.expert_func == expert_func)
        if model_code:
            conditions.append(CriticScoreRecord.model_code == model_code)
        if source_type:
            conditions.append(CriticScoreRecord.source_type == source_type)
        # job 场景
        if tenant_id is not None:
            conditions.append(CriticScoreRecord.tenant_id == tenant_id)
        if activity_id is not None:
            conditions.append(CriticScoreRecord.activity_id == activity_id)
        if job_id:
            conditions.append(CriticScoreRecord.job_id == job_id)
        # eval_run 场景
        if dataset_code:
            conditions.append(CriticScoreRecord.dataset_code == dataset_code)
        # expert_type 过滤
        type_cond = self._build_expert_type_condition(expert_type)
        if type_cond is not None:
            conditions.append(type_cond)
        
        if expert_func:
            # 选了维度：直接按分数分桶
            bucket_expr = (CriticScoreRecord.score / bucket_size).cast(sa.Integer) * bucket_size
            
            stmt = select(
                bucket_expr.label("bucket"),
                func.count(CriticScoreRecord.id).label("count"),
            )
            
            if conditions:
                stmt = stmt.where(and_(*conditions))
            
            stmt = stmt.group_by(bucket_expr).order_by(bucket_expr)
            
            result = await self.db.execute(stmt)
            rows = result.all()
        else:
            # 没选维度：先按 content_id 聚合取平均分，再按平均分分桶
            # 子查询：每篇文章的平均分
            subq = (
                select(
                    CriticScoreRecord.content_id,
                    func.avg(CriticScoreRecord.score).label("avg_score"),
                )
            )
            if conditions:
                subq = subq.where(and_(*conditions))
            subq = subq.group_by(CriticScoreRecord.content_id).subquery()
            
            # 主查询：按平均分分桶统计
            bucket_expr = (subq.c.avg_score / bucket_size).cast(sa.Integer) * bucket_size
            stmt = (
                select(
                    bucket_expr.label("bucket"),
                    func.count(subq.c.content_id).label("count"),
                )
                .group_by(bucket_expr)
                .order_by(bucket_expr)
            )
            
            result = await self.db.execute(stmt)
            rows = result.all()
        
        return [
            {
                "range": f"{int(row.bucket)}-{int(row.bucket) + bucket_size - 1}",
                "min": int(row.bucket),
                "max": int(row.bucket) + bucket_size - 1,
                "count": row.count or 0,
            }
            for row in rows
        ]

    async def list_dataset_codes(
        self,
        *,
        source_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """获取 critic_score_record 中出现过的 dataset_code（下拉用）"""
        conditions = [CriticScoreRecord.dataset_code.isnot(None)]
        if source_type:
            conditions.append(CriticScoreRecord.source_type == source_type)

        stmt = (
            select(
                CriticScoreRecord.dataset_code.label("dataset_code"),
                func.count(CriticScoreRecord.id).label("total"),
            )
            .where(and_(*conditions))
            .group_by(CriticScoreRecord.dataset_code)
            .order_by(desc(func.count(CriticScoreRecord.id)))
        )
        rows = (await self.db.execute(stmt)).all()
        return [{"dataset_code": r.dataset_code, "total": int(r.total or 0)} for r in rows]

    async def get_problem_context_top(
        self,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        expert_func: Optional[str] = None,
        model_code: Optional[str] = None,
        source_type: Optional[str] = None,
        # job 场景筛选
        tenant_id: Optional[int] = None,
        activity_id: Optional[int] = None,
        job_id: Optional[str] = None,
        # eval_run 场景筛选
        dataset_code: Optional[str] = None,
        top_n: int = 10,
        sample_limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        """
        热门问题上下文 TopN（先用 Python 聚合，后续可升级为落表/SQL JSON 聚合）
        """
        # 新字段优先：problem_tags；历史数据兼容：problem_context_list
        conditions = [
            sa.or_(
                CriticScoreRecord.problem_tags.isnot(None),
                CriticScoreRecord.problem_context_list.isnot(None),
            )
        ]
        if start_date:
            conditions.append(CriticScoreRecord.create_time >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            conditions.append(CriticScoreRecord.create_time <= datetime.combine(end_date, datetime.max.time()))
        if expert_func:
            conditions.append(CriticScoreRecord.expert_func == expert_func)
        if model_code:
            conditions.append(CriticScoreRecord.model_code == model_code)
        if source_type:
            conditions.append(CriticScoreRecord.source_type == source_type)
        # job 场景
        if tenant_id is not None:
            conditions.append(CriticScoreRecord.tenant_id == tenant_id)
        if activity_id is not None:
            conditions.append(CriticScoreRecord.activity_id == activity_id)
        if job_id:
            conditions.append(CriticScoreRecord.job_id == job_id)
        # eval_run 场景
        if dataset_code:
            conditions.append(CriticScoreRecord.dataset_code == dataset_code)

        stmt = (
            select(CriticScoreRecord.problem_tags, CriticScoreRecord.problem_context_list)
            .where(and_(*conditions))
            .order_by(desc(CriticScoreRecord.create_time))
            .limit(sample_limit)
        )
        rows = (await self.db.execute(stmt)).all()

        counts: Dict[str, int] = {}
        for tags, legacy_list in rows:
            candidate = tags if tags else legacy_list
            if not candidate:
                continue
            if isinstance(candidate, list):
                for item in candidate:
                    key = str(item).strip()
                    if not key:
                        continue
                    counts[key] = counts.get(key, 0) + 1
            else:
                key = str(candidate).strip()
                if key:
                    counts[key] = counts.get(key, 0) + 1

        items = sorted(counts.items(), key=lambda x: x[1], reverse=True)[: max(top_n, 1)]
        return [{"key": k, "count": v} for k, v in items]

    async def get_reason_wordcloud(
        self,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        expert_func: Optional[str] = None,
        model_code: Optional[str] = None,
        source_type: Optional[str] = None,
        # job 场景筛选
        tenant_id: Optional[int] = None,
        activity_id: Optional[int] = None,
        job_id: Optional[str] = None,
        # eval_run 场景筛选
        dataset_code: Optional[str] = None,
        top_n: int = 80,
        sample_limit: int = 5000,
        min_len: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        评分理由词云：从 critic_score_record.reason 抽样，后端切词聚合 TopN。
        """
        conditions = [CriticScoreRecord.reason.isnot(None)]
        if start_date:
            conditions.append(
                CriticScoreRecord.create_time >= datetime.combine(start_date, datetime.min.time())
            )
        if end_date:
            conditions.append(
                CriticScoreRecord.create_time <= datetime.combine(end_date, datetime.max.time())
            )
        if expert_func:
            conditions.append(CriticScoreRecord.expert_func == expert_func)
        if model_code:
            conditions.append(CriticScoreRecord.model_code == model_code)
        if source_type:
            conditions.append(CriticScoreRecord.source_type == source_type)
        # job 场景
        if tenant_id is not None:
            conditions.append(CriticScoreRecord.tenant_id == tenant_id)
        if activity_id is not None:
            conditions.append(CriticScoreRecord.activity_id == activity_id)
        if job_id:
            conditions.append(CriticScoreRecord.job_id == job_id)
        # eval_run 场景
        if dataset_code:
            conditions.append(CriticScoreRecord.dataset_code == dataset_code)

        stmt = (
            select(CriticScoreRecord.reason)
            .where(and_(*conditions))
            .order_by(desc(CriticScoreRecord.create_time))
            .limit(max(int(sample_limit), 1))
        )
        rows = (await self.db.execute(stmt)).all()

        stopwords = _DEFAULT_STOPWORDS
        counter: Counter[str] = Counter()
        for (reason,) in rows:
            if not reason:
                continue
            for token in _iter_reason_tokens(text=str(reason), min_len=max(int(min_len), 1)):
                token = token.strip()
                if len(token) < min_len:
                    continue
                if token in stopwords:
                    continue
                counter[token] += 1

        items = counter.most_common(max(int(top_n), 1))
        return [{"word": w, "count": int(c)} for w, c in items]

    async def get_dimension_score_heatmap(
        self,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        source_type: Optional[str] = None,
        # job 场景筛选
        tenant_id: Optional[int] = None,
        activity_id: Optional[int] = None,
        job_id: Optional[str] = None,
        # eval_run 场景筛选
        dataset_code: Optional[str] = None,
        bucket_size: int = 10,
        # expert_type 过滤：BAN / CRITIC，默认只展示 CRITIC
        expert_type: str | None = "CRITIC",
    ) -> Dict[str, Any]:
        """
        获取维度×分数段的交叉统计（热力图数据）

        说明：
        - 默认只展示 CRITIC 类型（质量评分维度）
        - BAN 类型（合规封禁）在前端单独用卡片展示
        """
        conditions = []
        
        # expert_type 过滤（默认 CRITIC）
        type_cond = self._build_expert_type_condition(expert_type)
        if type_cond is not None:
            conditions.append(type_cond)
        
        if start_date:
            conditions.append(
                CriticScoreRecord.create_time >= datetime.combine(start_date, datetime.min.time())
            )
        if end_date:
            conditions.append(
                CriticScoreRecord.create_time <= datetime.combine(end_date, datetime.max.time())
            )
        if source_type:
            conditions.append(CriticScoreRecord.source_type == source_type)
        # job 场景
        if tenant_id is not None:
            conditions.append(CriticScoreRecord.tenant_id == tenant_id)
        if activity_id is not None:
            conditions.append(CriticScoreRecord.activity_id == activity_id)
        if job_id:
            conditions.append(CriticScoreRecord.job_id == job_id)
        # eval_run 场景
        if dataset_code:
            conditions.append(CriticScoreRecord.dataset_code == dataset_code)

        # 从数据库获取 CRITIC 类型的 expert_func 及其显示名称
        from app.models.expert_config import ExpertConfig
        
        func_name_stmt = (
            select(ExpertConfig.expert_func, ExpertConfig.expert_func_name)
            .where(
                ExpertConfig.is_deleted == 0,
                ExpertConfig.enabled == True,  # noqa: E712
                ExpertConfig.expert_type == "CRITIC",
            )
        )
        func_name_result = await self.db.execute(func_name_stmt)
        func_name_rows = func_name_result.fetchall()
        
        # 构建 expert_func -> expert_func_name 映射
        dimension_labels: Dict[str, str] = {}
        for row in func_name_rows:
            # 如果有 expert_func_name 则使用，否则用 expert_func 本身
            dimension_labels[row.expert_func] = row.expert_func_name or row.expert_func
        
        # 如果没有配置任何 CRITIC 类型，返回空数据
        if not dimension_labels:
            return {
                "dimensions": [],
                "score_ranges": [f"{i}-{i + bucket_size - 1}" for i in range(0, 100, bucket_size)],
                "data": [],
            }
        
        # 只查询数据库中配置的 CRITIC 维度
        conditions.append(CriticScoreRecord.expert_func.in_(list(dimension_labels.keys())))

        # 按分数段分桶
        bucket_expr = (CriticScoreRecord.score / bucket_size).cast(sa.Integer) * bucket_size
        
        stmt = select(
            CriticScoreRecord.expert_func,
            bucket_expr.label("bucket"),
            func.count(CriticScoreRecord.id).label("count"),
        )
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        stmt = stmt.group_by(
            CriticScoreRecord.expert_func,
            bucket_expr,
        ).order_by(
            CriticScoreRecord.expert_func,
            bucket_expr,
        )
        
        rows = (await self.db.execute(stmt)).all()
        
        # 收集所有出现的维度
        dim_set: set[str] = set()
        for row in rows:
            dim_set.add(row.expert_func)
        
        # 按预定义顺序排列维度（按 dimension_labels 的 key 顺序）
        ordered_dims = [
            d for d in dimension_labels.keys() if d in dim_set
        ]
        
        dim_to_idx = {d: i for i, d in enumerate(ordered_dims)}
        
        # 分数段标签
        score_ranges = [f"{i}-{i + bucket_size - 1}" for i in range(0, 100, bucket_size)]
        range_to_idx = {f"{i}-{i + bucket_size - 1}": idx for idx, i in enumerate(range(0, 100, bucket_size))}
        
        # 构建热力图数据
        # ECharts heatmap 数据格式：[x轴索引, y轴索引, 值] = [分数段索引, 维度索引, 数量]
        data: List[List[int]] = []
        for row in rows:
            dim_idx = dim_to_idx.get(row.expert_func)
            if dim_idx is None:
                continue
            bucket_val = int(row.bucket) if row.bucket is not None else 0
            # 确保 bucket 在有效范围内
            if bucket_val < 0:
                bucket_val = 0
            if bucket_val >= 100:
                bucket_val = 90
            range_key = f"{bucket_val}-{bucket_val + bucket_size - 1}"
            range_idx = range_to_idx.get(range_key, 0)
            # 格式：[x轴索引(分数段), y轴索引(维度), 数量]
            data.append([range_idx, dim_idx, row.count or 0])
        
        # 维度显示名称（使用数据库中的 expert_func_name）
        dimensions = [dimension_labels.get(d, d) for d in ordered_dims]
        
        return {
            "dimensions": dimensions,
            "score_ranges": score_ranges,
            "data": data,
        }

    async def get_scatter_data(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        model_code: str | None = None,
        source_type: str | None = None,
        tenant_id: int | None = None,
        activity_id: int | None = None,
        job_id: str | None = None,
        dataset_code: str | None = None,
        limit: int = 2000,
        # expert_type 过滤：BAN / CRITIC，默认只展示 CRITIC
        expert_type: str | None = "CRITIC",
    ) -> List[dict]:
        """
        获取散点图数据（Scatter with Jittering）
        x = 维度，y = 分数，每个点 = 一篇文章
        默认只展示 CRITIC 类型（质量评分维度）
        """
        conditions = []
        
        # expert_type 过滤（默认 CRITIC）
        type_cond = self._build_expert_type_condition(expert_type)
        if type_cond is not None:
            conditions.append(type_cond)
        
        if start_date:
            conditions.append(func.date(CriticScoreRecord.create_time) >= start_date)
        if end_date:
            conditions.append(func.date(CriticScoreRecord.create_time) <= end_date)
        if model_code:
            conditions.append(CriticScoreRecord.model_code == model_code)
        if source_type:
            conditions.append(CriticScoreRecord.source_type == source_type)
        if tenant_id:
            conditions.append(CriticScoreRecord.tenant_id == tenant_id)
        if activity_id:
            conditions.append(CriticScoreRecord.activity_id == activity_id)
        if job_id:
            conditions.append(CriticScoreRecord.job_id == job_id)
        if dataset_code:
            conditions.append(CriticScoreRecord.dataset_code == dataset_code)
        
        # 从数据库获取 CRITIC 类型的 expert_func 及其显示名称
        from app.models.expert_config import ExpertConfig
        
        func_name_stmt = (
            select(ExpertConfig.expert_func, ExpertConfig.expert_func_name)
            .where(
                ExpertConfig.is_deleted == 0,
                ExpertConfig.enabled == True,  # noqa: E712
                ExpertConfig.expert_type == "CRITIC",
            )
        )
        func_name_result = await self.db.execute(func_name_stmt)
        func_name_rows = func_name_result.fetchall()
        
        # 构建 expert_func -> expert_func_name 映射
        dimension_labels: Dict[str, str] = {}
        for row in func_name_rows:
            dimension_labels[row.expert_func] = row.expert_func_name or row.expert_func
        
        # 如果没有配置任何 CRITIC 类型，返回空数据
        if not dimension_labels:
            return []
        
        # 只查询数据库中配置的 CRITIC 维度
        conditions.append(CriticScoreRecord.expert_func.in_(list(dimension_labels.keys())))
        
        stmt = (
            select(
                CriticScoreRecord.expert_func,
                CriticScoreRecord.score,
                CriticScoreRecord.content_id,
            )
            .where(and_(*conditions))
            .order_by(func.random())
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        rows = result.fetchall()
        
        return [
            {
                "dimension": dimension_labels.get(row.expert_func, row.expert_func),
                "score": row.score,
                "content_id": row.content_id,
            }
            for row in rows
        ]

    async def list_expert_config_options(
        self,
        expert_type: str | None = None,
        tenant_code: str | None = None,
    ) -> List[dict]:
        """
        获取 CRITIC/BAN 类型的 expert_config 列表（用于下拉选项）

        Args:
            expert_type: 过滤类型，CRITIC / BAN / None（返回 CRITIC + BAN）
            tenant_code: 租户编码过滤（匹配 tenant_code 或 NULL 表示全局共享）

        Returns:
            expert_config 列表，包含 expert_config_code, expert_config_name, expert_type, expert_func
        """
        from app.models.expert_config import ExpertConfig

        conditions = [
            ExpertConfig.is_deleted == 0,
            ExpertConfig.enabled == True,  # noqa: E712
        ]

        # 默认只返回 CRITIC 和 BAN 类型
        if expert_type:
            conditions.append(ExpertConfig.expert_type == expert_type.upper())
        else:
            conditions.append(ExpertConfig.expert_type.in_(["CRITIC", "BAN"]))

        # 租户过滤：匹配指定租户或全局共享（tenant_code IS NULL）
        if tenant_code:
            conditions.append(
                sa.or_(
                    ExpertConfig.tenant_code == tenant_code,
                    ExpertConfig.tenant_code.is_(None),
                )
            )

        stmt = (
            select(
                ExpertConfig.expert_config_code,
                ExpertConfig.expert_config_name,
                ExpertConfig.expert_type,
                ExpertConfig.expert_func,
                ExpertConfig.expert_func_name,
            )
            .where(and_(*conditions))
            .order_by(ExpertConfig.expert_type, ExpertConfig.expert_config_name)
        )

        result = await self.db.execute(stmt)
        rows = result.fetchall()

        return [
            {
                "expert_config_code": row.expert_config_code,
                "expert_config_name": row.expert_config_name,
                "expert_type": row.expert_type,
                "expert_func": row.expert_func,
                "expert_func_name": row.expert_func_name,
            }
            for row in rows
        ]
