"""
AB测试服务
统一支持 Expert 维度和 Agent/Job 维度的对比实验
采用关联模式：关联已有数据，聚合指标进行对比
"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from sqlalchemy.orm.attributes import flag_modified
from loguru import logger

from app.models.ab_test import ABTest
from app.models.expert_debug_history import ExpertDebugHistory
from app.models.expert_call_trace import ExpertCallTrace
from app.models.content import Content
from app.models.critic_score_record import CriticScoreRecord
from app.schemas.ab_test import (
    ABTestCreateExpert,
    ABTestCreateJob,
    ABTestUpdate,
    ABTestResponse,
    ABTestListResponse,
    ABTestDetailResponse,
    ABTestAnalyzeResponse,
    ABTestMetrics,
    GroupMetricsDetail,
    CriticScoreDetail,
    AddDebugHistoryRequest,
    ABTestExecuteExpert,
    ABTestExecuteResponse,
    ABTestGroup,
    ABTestGroupConfig,
)
from app.services.expert_debug_service import ExpertDebugService
from app.schemas.expert_debug import ExpertDebugRequest


class ABTestService:
    """AB测试服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.debug_service = ExpertDebugService(db)

    # ========== 执行模式（保留原有流程）==========

    async def create_and_execute_expert_test(
        self,
        data: ABTestExecuteExpert,
        created_by: Optional[str] = None,
    ) -> ABTestResponse:
        """
        创建并执行 Expert 维度 AB 测试
        
        1. 创建测试记录，debug_history_ids 初始为空数组
        2. 后台执行测试时，每完成一个 debug 就追加 debug_history_id
        
        Args:
            data: 执行模式创建数据
            created_by: 创建人
            
        Returns:
            创建的测试
        """
        test_id = f"ab-{uuid.uuid4().hex[:12]}"
        
        # 验证流量分配
        total_ratio = sum(data.traffic_allocation.values())
        if total_ratio != 100:
            raise ValueError(f"流量分配比例之和必须为100，当前为{total_ratio}")
        
        # 验证配置组名与流量分配一致
        config_groups = {cfg.group_name for cfg in data.configs}
        allocation_groups = set(data.traffic_allocation.keys())
        if config_groups != allocation_groups:
            raise ValueError(
                f"配置组名与流量分配不匹配: 配置组={config_groups}, 流量分配={allocation_groups}"
            )
        
        # 构建 groups 和 debug_history_ids（初始为空数组）
        groups = []
        debug_history_ids: Dict[str, List[int]] = {}
        
        for cfg in data.configs:
            groups.append({
                "group_name": cfg.group_name,
                "description": cfg.config_name,
                "config_snapshot": {
                    "config_code": cfg.config_code,
                    "config_name": cfg.config_name,
                    "model_code": cfg.model_code,
                    "variables": cfg.variables,
                    "llm_config": cfg.llm_config,
                },
            })
            debug_history_ids[cfg.group_name] = []  # 初始为空
        
        ab_test = ABTest(
            test_id=test_id,
            test_name=data.test_name,
            test_type="EXPERT_CONFIG",
            debug_history_ids=debug_history_ids,
            job_ids=None,
            groups=groups,
            status="pending",
            created_by=created_by,
            remark=data.remark,
        )
        
        self.db.add(ab_test)
        await self.db.commit()
        await self.db.refresh(ab_test)
        
        logger.info(f"[ABTest] 创建执行模式测试: {test_id}, 配置组数: {len(data.configs)}")
        
        return self._to_response(ab_test)

    async def execute_test(
        self,
        test_id: str,
        data: ABTestExecuteExpert,
        username: Optional[str] = None,
    ) -> ABTestExecuteResponse:
        """
        执行 AB 测试（后台执行）
        
        每执行完一个 debug，立即追加 debug_history_id 到对应组
        
        Args:
            test_id: 测试 ID
            data: 执行配置
            username: 执行用户
            
        Returns:
            执行结果
        """
        ab_test = await self._get_test_by_id(test_id)
        if not ab_test:
            raise ValueError(f"测试不存在: {test_id}")
        
        if ab_test.status == "completed":
            raise ValueError(f"测试已完成: {test_id}")
        
        # 更新状态为 running
        ab_test.status = "running"
        ab_test.start_time = datetime.now()
        await self.db.commit()
        
        try:
            # 构建配置组映射
            config_map = {cfg.group_name: cfg for cfg in data.configs}
            
            # 计算各组执行次数
            total_runs = data.execution_count
            group_runs: Dict[str, int] = {}
            allocated = 0
            group_names = list(data.traffic_allocation.keys())
            
            for i, group_name in enumerate(group_names):
                ratio = data.traffic_allocation.get(group_name, 0)
                if i == len(group_names) - 1:
                    group_runs[group_name] = total_runs - allocated
                else:
                    runs = int(total_runs * ratio / 100)
                    group_runs[group_name] = runs
                    allocated += runs
            
            # 执行测试
            completed_count = 0
            success_count = 0
            
            for group_name, runs_count in group_runs.items():
                config = config_map.get(group_name)
                if not config:
                    continue
                
                for i in range(runs_count):
                    try:
                        debug_history_id = await self._execute_single_debug(
                            ab_test=ab_test,
                            group_name=group_name,
                            config=config,
                            test_content=data.test_content,
                        )
                        
                        if debug_history_id:
                            # 追加 debug_history_id 到对应组
                            await self._append_debug_history_id(
                                test_id, group_name, debug_history_id
                            )
                            success_count += 1
                        
                    except Exception as e:
                        logger.error(
                            f"[ABTest] 执行失败: {test_id}, group={group_name}, "
                            f"run={i+1}, error={e}"
                        )
                    
                    completed_count += 1
            
            # 自动分析
            await self.analyze_test(test_id)
            
            logger.info(
                f"[ABTest] 执行完成: {test_id}, 成功: {success_count}/{completed_count}"
            )
            
            return ABTestExecuteResponse(
                test_id=test_id,
                status="completed",
                message="测试执行完成",
                total_runs=completed_count,
                completed_runs=success_count,
            )
            
        except Exception as e:
            ab_test.status = "failed"
            ab_test.end_time = datetime.now()
            ab_test.remark = f"执行失败: {str(e)}"
            await self.db.commit()
            raise

    async def _execute_single_debug(
        self,
        ab_test: ABTest,
        group_name: str,
        config: ABTestGroupConfig,
        test_content: Optional[str],
    ) -> Optional[int]:
        """
        执行单次调试
        
        Returns:
            debug_history_id
        """
        # 构建调试请求
        debug_request = ExpertDebugRequest(
            expert_config_code=config.config_code,
            content=test_content or "",
            plugin_config_snapshot=config.variables,
            model_code=config.model_code,
            model_cfg_override=config.llm_config,
        )
        
        # 执行调试
        debug_response = await self.debug_service.debug(debug_request)
        
        if debug_response and debug_response.id:
            return debug_response.id
        
        return None

    async def _append_debug_history_id(
        self,
        test_id: str,
        group_name: str,
        debug_history_id: int,
    ):
        """
        追加 debug_history_id 到指定组
        """
        ab_test = await self._get_test_by_id(test_id)
        if not ab_test:
            return
        
        current_ids = ab_test.debug_history_ids or {}
        if group_name not in current_ids:
            current_ids[group_name] = []
        
        if debug_history_id not in current_ids[group_name]:
            current_ids[group_name].append(debug_history_id)
        
        ab_test.debug_history_ids = current_ids
        # 显式标记 JSON 字段已修改，否则 SQLAlchemy 检测不到原地修改
        flag_modified(ab_test, "debug_history_ids")
        await self.db.commit()
        
        logger.debug(
            f"[ABTest] 追加 debug_history_id: {test_id}, "
            f"group={group_name}, id={debug_history_id}"
        )

    # ========== 创建测试（关联模式）==========

    async def create_expert_test(
        self,
        data: ABTestCreateExpert,
        created_by: Optional[str] = None,
    ) -> ABTestResponse:
        """
        创建 Expert 维度 AB 测试
        
        Args:
            data: 测试创建数据（包含 debug_history_ids）
            created_by: 创建人
            
        Returns:
            创建的测试
        """
        test_id = f"ab-{uuid.uuid4().hex[:12]}"
        
        # 验证组名一致性
        group_names_from_ids = set(data.debug_history_ids.keys())
        group_names_from_groups = {g.group_name for g in data.groups}
        if group_names_from_ids != group_names_from_groups:
            raise ValueError(
                f"组名不匹配: debug_history_ids={group_names_from_ids}, groups={group_names_from_groups}"
            )
        
        ab_test = ABTest(
            test_id=test_id,
            test_name=data.test_name,
            test_type="EXPERT_CONFIG",
            debug_history_ids=data.debug_history_ids,
            job_ids=None,
            groups=[g.model_dump() for g in data.groups],
            status="pending",
            created_by=created_by,
            remark=data.remark,
        )
        
        self.db.add(ab_test)
        await self.db.commit()
        await self.db.refresh(ab_test)
        
        logger.info(f"[ABTest] 创建 Expert 测试: {test_id}, 组数: {len(data.groups)}")
        
        return self._to_response(ab_test)

    async def create_job_test(
        self,
        data: ABTestCreateJob,
        created_by: Optional[str] = None,
    ) -> ABTestResponse:
        """
        创建 Job 维度 AB 测试
        
        Args:
            data: 测试创建数据（包含 job_ids）
            created_by: 创建人
            
        Returns:
            创建的测试
        """
        test_id = f"ab-{uuid.uuid4().hex[:12]}"
        
        # 验证组名一致性
        group_names_from_ids = set(data.job_ids.keys())
        group_names_from_groups = {g.group_name for g in data.groups}
        if group_names_from_ids != group_names_from_groups:
            raise ValueError(
                f"组名不匹配: job_ids={group_names_from_ids}, groups={group_names_from_groups}"
            )
        
        ab_test = ABTest(
            test_id=test_id,
            test_name=data.test_name,
            test_type="AGENT_JOB",
            debug_history_ids=None,
            job_ids=data.job_ids,
            groups=[g.model_dump() for g in data.groups],
            status="pending",
            created_by=created_by,
            remark=data.remark,
        )
        
        self.db.add(ab_test)
        await self.db.commit()
        await self.db.refresh(ab_test)
        
        logger.info(f"[ABTest] 创建 Job 测试: {test_id}, 组数: {len(data.groups)}")
        
        return self._to_response(ab_test)

    # ========== 添加关联 ==========

    async def add_debug_histories(
        self,
        test_id: str,
        data: AddDebugHistoryRequest,
    ) -> ABTestResponse:
        """
        向 Expert 测试添加调试历史
        
        Args:
            test_id: 测试ID
            data: 添加请求
            
        Returns:
            更新后的测试
        """
        ab_test = await self._get_test_by_id(test_id)
        if not ab_test:
            raise ValueError(f"测试不存在: {test_id}")
        
        if ab_test.test_type != "EXPERT_CONFIG":
            raise ValueError(f"测试类型不匹配，当前为: {ab_test.test_type}")
        
        # 检查组名是否存在
        existing_groups = {g.get("group_name") for g in ab_test.groups}
        if data.group_name not in existing_groups:
            raise ValueError(f"组名不存在: {data.group_name}")
        
        # 更新 debug_history_ids
        current_ids = ab_test.debug_history_ids or {}
        if data.group_name not in current_ids:
            current_ids[data.group_name] = []
        
        # 追加新的 ID（去重）
        existing_set = set(current_ids[data.group_name])
        for new_id in data.debug_history_ids:
            if new_id not in existing_set:
                current_ids[data.group_name].append(new_id)
        
        ab_test.debug_history_ids = current_ids
        # 显式标记 JSON 字段已修改，否则 SQLAlchemy 检测不到原地修改
        flag_modified(ab_test, "debug_history_ids")
        
        # 重置状态为 pending，需要重新分析
        if ab_test.status == "completed":
            ab_test.status = "pending"
            ab_test.metrics = None
            ab_test.winner = None
            ab_test.recommendation = None
        
        await self.db.commit()
        await self.db.refresh(ab_test)
        
        logger.info(f"[ABTest] 添加调试历史: {test_id}, 组: {data.group_name}, 数量: {len(data.debug_history_ids)}")
        
        return self._to_response(ab_test)

    # ========== 分析测试 ==========

    async def analyze_test(self, test_id: str) -> ABTestAnalyzeResponse:
        """
        分析测试，聚合指标并生成结论
        
        Args:
            test_id: 测试ID
            
        Returns:
            分析结果
        """
        ab_test = await self._get_test_by_id(test_id)
        if not ab_test:
            raise ValueError(f"测试不存在: {test_id}")
        
        # 更新状态为 analyzing
        ab_test.status = "analyzing"
        ab_test.start_time = datetime.now()
        await self.db.commit()
        
        try:
            # 根据类型计算指标
            if ab_test.test_type == "EXPERT_CONFIG":
                metrics = await self._calculate_expert_metrics(ab_test)
            else:  # AGENT_JOB
                metrics = await self._calculate_job_metrics(ab_test)
            
            # 生成推荐结论
            winner, recommendation = self._generate_recommendation(metrics)
            
            # 更新测试结果
            ab_test.metrics = {k: v.model_dump() for k, v in metrics.items()}
            ab_test.winner = winner
            ab_test.recommendation = recommendation
            ab_test.status = "completed"
            ab_test.end_time = datetime.now()
            
            await self.db.commit()
            
            logger.info(f"[ABTest] 分析完成: {test_id}, winner={winner}")
            
            return ABTestAnalyzeResponse(
                test_id=test_id,
                status="completed",
                message="分析完成",
                metrics=metrics,
                winner=winner,
                recommendation=recommendation,
            )
            
        except Exception as e:
            ab_test.status = "failed"
            ab_test.end_time = datetime.now()
            ab_test.remark = f"分析失败: {str(e)}"
            await self.db.commit()
            
            logger.error(f"[ABTest] 分析失败: {test_id}, error={e}")
            raise

    async def _calculate_expert_metrics(self, ab_test: ABTest) -> Dict[str, ABTestMetrics]:
        """
        计算 Expert 维度的指标
        
        路径: debug_history_id → expert_debug_history.trace_id → expert_call_trace
        """
        metrics: Dict[str, ABTestMetrics] = {}
        
        debug_history_ids = ab_test.debug_history_ids or {}
        
        for group_name, history_ids in debug_history_ids.items():
            if not history_ids:
                metrics[group_name] = ABTestMetrics()
                continue
            
            # 获取所有 debug_history 的 trace_id
            stmt = select(ExpertDebugHistory).where(
                ExpertDebugHistory.id.in_(history_ids)
            )
            result = await self.db.execute(stmt)
            histories = result.scalars().all()
            
            trace_ids = [h.trace_id for h in histories if h.trace_id]
            
            if not trace_ids:
                metrics[group_name] = ABTestMetrics(run_count=len(history_ids))
                continue
            
            # 通过 trace_id 查询 expert_call_trace
            metrics[group_name] = await self._aggregate_trace_metrics(trace_ids, len(history_ids))
        
        return metrics

    async def _calculate_job_metrics(self, ab_test: ABTest) -> Dict[str, ABTestMetrics]:
        """
        计算 Job 维度的指标
        
        路径: job_id → content.job_id → expert_call_trace.content_id
        增强指标: Content.is_valid, CriticScoreRecord.score
        """
        metrics: Dict[str, ABTestMetrics] = {}
        
        job_ids = ab_test.job_ids or {}
        
        for group_name, job_id in job_ids.items():
            if not job_id:
                metrics[group_name] = ABTestMetrics()
                continue
            
            # 获取 Job 下所有 content
            content_stmt = select(Content).where(
                and_(
                    Content.job_id == job_id,
                    Content.is_deleted == 0,
                )
            )
            content_result = await self.db.execute(content_stmt)
            contents = content_result.scalars().all()
            
            if not contents:
                metrics[group_name] = ABTestMetrics()
                continue
            
            content_ids = [c.content_id for c in contents]
            
            # 通过 content_id 查询 expert_call_trace
            trace_stmt = select(ExpertCallTrace).where(
                ExpertCallTrace.content_id.in_(content_ids)
            )
            trace_result = await self.db.execute(trace_stmt)
            traces = trace_result.scalars().all()
            
            # 查询 critic_score_record 获取质量评分
            critic_stmt = select(CriticScoreRecord).where(
                and_(
                    CriticScoreRecord.job_id == job_id,
                    CriticScoreRecord.content_id.in_(content_ids),
                )
            )
            critic_result = await self.db.execute(critic_stmt)
            critic_records = critic_result.scalars().all()
            
            # 计算基础指标
            base_metrics = self._aggregate_traces(traces, len(contents))
            
            # 计算质量指标
            quality_metrics = self._calculate_quality_metrics(contents, critic_records)
            
            # 合并指标
            metrics[group_name] = ABTestMetrics(
                avg_time_ms=base_metrics.avg_time_ms,
                avg_tokens=base_metrics.avg_tokens,
                avg_cost=base_metrics.avg_cost,
                success_rate=base_metrics.success_rate,
                run_count=len(contents),
                avg_score=quality_metrics.get("avg_score"),
                pass_rate=quality_metrics.get("pass_rate"),
            )
        
        return metrics
    
    def _calculate_quality_metrics(
        self, 
        contents: List[Content], 
        critic_records: List[CriticScoreRecord]
    ) -> Dict[str, float]:
        """
        计算质量相关指标
        
        Args:
            contents: Content 列表
            critic_records: CriticScoreRecord 列表
            
        Returns:
            质量指标字典: avg_score, pass_rate
        """
        result: Dict[str, float] = {}
        
        if not contents:
            return result
        
        # 计算有效率（基于 is_valid）
        valid_count = sum(1 for c in contents if c.is_valid == 1)
        total_with_decision = sum(1 for c in contents if c.is_valid is not None)
        if total_with_decision > 0:
            result["pass_rate"] = round(valid_count / total_with_decision * 100, 2)
        
        # 计算平均 Critic 评分
        if critic_records:
            total_score = sum(r.score for r in critic_records)
            result["avg_score"] = round(total_score / len(critic_records), 2)
        
        return result

    async def _aggregate_trace_metrics(
        self, 
        trace_ids: List[str], 
        sample_count: int
    ) -> ABTestMetrics:
        """
        通过 trace_id 聚合指标
        """
        # 查询所有相关的 expert_call_trace
        stmt = select(ExpertCallTrace).where(
            ExpertCallTrace.trace_id.in_(trace_ids)
        )
        result = await self.db.execute(stmt)
        traces = result.scalars().all()
        
        return self._aggregate_traces(traces, sample_count)

    def _aggregate_traces(
        self, 
        traces: List[ExpertCallTrace], 
        sample_count: int
    ) -> ABTestMetrics:
        """
        聚合 trace 数据为指标
        """
        if not traces:
            return ABTestMetrics(run_count=sample_count)
        
        total_time = sum(t.duration_ms or 0 for t in traces)
        total_tokens = sum(t.total_tokens or 0 for t in traces)
        total_cost = sum(float(t.total_cost or 0) for t in traces)
        success_count = sum(1 for t in traces if t.status == "success")
        
        # 按 trace_id 分组计算（每个 trace_id 可能有多个 expert 调用）
        trace_groups: Dict[str, List[ExpertCallTrace]] = {}
        for t in traces:
            if t.trace_id not in trace_groups:
                trace_groups[t.trace_id] = []
            trace_groups[t.trace_id].append(t)
        
        num_traces = len(trace_groups) if trace_groups else 1
        
        return ABTestMetrics(
            avg_time_ms=round(total_time / num_traces, 2) if num_traces else 0,
            avg_tokens=round(total_tokens / num_traces) if num_traces else 0,
            avg_cost=round(total_cost / num_traces, 6) if num_traces else 0,
            success_rate=round(success_count / len(traces) * 100, 2) if traces else 0,
            run_count=sample_count,
        )

    def _generate_recommendation(
        self, 
        metrics: Dict[str, ABTestMetrics]
    ) -> tuple[str, str]:
        """
        生成推荐结论
        
        Returns:
            (winner, recommendation)
        """
        if not metrics:
            return "INCONCLUSIVE", "数据不足，无法生成推荐"
        
        # 计算各组得分
        group_scores: Dict[str, float] = {}
        for group_name, m in metrics.items():
            if m.run_count > 0:
                group_scores[group_name] = self._calculate_score(m)
        
        if not group_scores:
            return "INCONCLUSIVE", "所有组均无有效数据"
        
        # 找出最高分
        sorted_groups = sorted(group_scores.items(), key=lambda x: x[1], reverse=True)
        best_group, best_score = sorted_groups[0]
        
        # 检查是否有多个组得分相近（差异小于5%）
        top_groups = [
            g for g, s in sorted_groups 
            if abs(s - best_score) / max(best_score, 0.01) < 0.05
        ]
        
        if len(top_groups) > 1:
            summaries = []
            for group_name in top_groups:
                m = metrics.get(group_name)
                if m:
                    summary = f"{group_name}: 平均时间{m.avg_time_ms}ms, 平均Token{m.avg_tokens}"
                    if m.avg_score is not None:
                        summary += f", 平均评分{m.avg_score}"
                    if m.pass_rate is not None:
                        summary += f", 通过率{m.pass_rate}%"
                    summaries.append(summary)
            return "TIE", f"以下配置组性能相当：\n" + "\n".join(summaries)
        
        # 有明确胜出方
        best_metrics = metrics.get(best_group)
        if not best_metrics:
            return best_group, f"推荐配置组: {best_group}"
        
        comparisons = []
        for group_name, score in sorted_groups[1:]:
            m = metrics.get(group_name)
            if m:
                time_diff = self._calc_percentage_diff(best_metrics.avg_time_ms, m.avg_time_ms)
                token_diff = self._calc_percentage_diff(best_metrics.avg_tokens, m.avg_tokens)
                comparison = f"vs {group_name}: 时间快{time_diff:.1f}%, Token少{token_diff:.1f}%"
                # 添加质量指标对比
                if best_metrics.avg_score is not None and m.avg_score is not None:
                    score_diff = best_metrics.avg_score - m.avg_score
                    comparison += f", 评分高{score_diff:.1f}"
                if best_metrics.pass_rate is not None and m.pass_rate is not None:
                    pass_diff = best_metrics.pass_rate - m.pass_rate
                    comparison += f", 通过率高{pass_diff:.1f}%"
                comparisons.append(comparison)
        
        # 构建性能摘要
        performance_summary = f"性能: 平均时间{best_metrics.avg_time_ms}ms, 平均Token{best_metrics.avg_tokens}"
        if best_metrics.avg_score is not None:
            performance_summary += f", 平均评分{best_metrics.avg_score}"
        if best_metrics.pass_rate is not None:
            performance_summary += f", 通过率{best_metrics.pass_rate}%"
        
        recommendation = (
            f"推荐配置组: {best_group}\n"
            f"{performance_summary}\n"
            + "\n".join(comparisons)
        )
        
        return best_group, recommendation

    def _calculate_score(self, metrics: ABTestMetrics) -> float:
        """
        计算综合得分
        
        考虑因素：
        - 时间（越低越好）
        - Token（越低越好）
        - 成功率（越高越好）
        - 平均质量分（越高越好，如果有的话）
        - 通过率（越高越好，如果有的话）
        """
        time_score = 1000 / (metrics.avg_time_ms or 1)
        token_score = 1000 / (metrics.avg_tokens or 1)
        success_rate = metrics.success_rate
        
        # 基础权重分配
        base_score = time_score * 0.25 + token_score * 0.15 + success_rate * 0.2
        
        # 质量指标（如果存在）
        quality_score = 0.0
        quality_weight = 0.0
        
        if metrics.avg_score is not None:
            quality_score += metrics.avg_score * 0.2
            quality_weight += 0.2
        
        if metrics.pass_rate is not None:
            quality_score += metrics.pass_rate * 0.2
            quality_weight += 0.2
        
        # 如果没有质量指标，将权重分配给基础指标
        if quality_weight == 0:
            return time_score * 0.4 + token_score * 0.3 + success_rate * 0.3
        
        # 归一化总权重
        remaining_weight = 1.0 - quality_weight
        base_weight = 0.6  # 基础指标原始权重
        adjusted_base = base_score * (remaining_weight / base_weight)
        
        return adjusted_base + quality_score

    def _calc_percentage_diff(self, winner_val: float, loser_val: float) -> float:
        """计算百分比差异"""
        if loser_val == 0:
            return 0.0
        return (loser_val - winner_val) / loser_val * 100

    # ========== 查询测试 ==========

    async def get_test(self, test_id: str) -> Optional[ABTestResponse]:
        """获取测试基本信息"""
        ab_test = await self._get_test_by_id(test_id)
        if not ab_test:
            return None
        return self._to_response(ab_test)

    async def get_test_detail(self, test_id: str) -> Optional[ABTestDetailResponse]:
        """获取测试详情（包含各组详细指标）"""
        ab_test = await self._get_test_by_id(test_id)
        if not ab_test:
            return None
        
        # 构建组详情
        group_details: List[GroupMetricsDetail] = []
        metrics_dict = ab_test.metrics or {}
        
        for group in ab_test.groups:
            group_name = group.get("group_name")
            m = metrics_dict.get(group_name, {})
            
            # 获取样本ID列表
            sample_ids: List[Any] = []
            job_id: Optional[str] = None
            critic_details: Optional[List[CriticScoreDetail]] = None
            
            if ab_test.test_type == "EXPERT_CONFIG" and ab_test.debug_history_ids:
                sample_ids = ab_test.debug_history_ids.get(group_name, [])
            elif ab_test.test_type == "AGENT_JOB" and ab_test.job_ids:
                job_id = ab_test.job_ids.get(group_name)
                if job_id:
                    sample_ids = [job_id]
                    # 获取 Critic 评分明细
                    critic_details = await self._get_critic_details_by_job(job_id)
            
            group_details.append(GroupMetricsDetail(
                group_name=group_name,
                description=group.get("description"),
                job_id=job_id,
                metrics=ABTestMetrics(**m) if m else ABTestMetrics(),
                sample_ids=sample_ids,
                critic_details=critic_details,
            ))
        
        return ABTestDetailResponse(
            test=self._to_response(ab_test),
            group_details=group_details,
            comparison={
                "winner": ab_test.winner,
                "recommendation": ab_test.recommendation,
            },
        )

    async def list_tests(
        self,
        page: int = 1,
        page_size: int = 20,
        test_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> ABTestListResponse:
        """获取测试列表"""
        conditions = [ABTest.is_deleted == 0]
        
        if test_type:
            conditions.append(ABTest.test_type == test_type)
        if status:
            conditions.append(ABTest.status == status)
        
        # 查询总数
        count_stmt = select(func.count()).select_from(ABTest).where(and_(*conditions))
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # 查询数据
        stmt = (
            select(ABTest)
            .where(and_(*conditions))
            .order_by(desc(ABTest.create_time))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        tests = result.scalars().all()
        
        return ABTestListResponse(
            items=[self._to_response(t) for t in tests],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update_test(
        self,
        test_id: str,
        data: ABTestUpdate,
    ) -> Optional[ABTestResponse]:
        """更新测试"""
        ab_test = await self._get_test_by_id(test_id)
        if not ab_test:
            return None
        
        if data.test_name is not None:
            ab_test.test_name = data.test_name
        if data.remark is not None:
            ab_test.remark = data.remark
        
        await self.db.commit()
        await self.db.refresh(ab_test)
        
        return self._to_response(ab_test)

    async def delete_test(self, test_id: str) -> bool:
        """删除测试（软删除）"""
        ab_test = await self._get_test_by_id(test_id)
        if not ab_test:
            return False
        
        ab_test.is_deleted = 1
        await self.db.commit()
        
        logger.info(f"[ABTest] 删除测试: {test_id}")
        return True

    # ========== 辅助方法 ==========

    async def _get_test_by_id(self, test_id: str) -> Optional[ABTest]:
        """根据 test_id 获取测试"""
        stmt = select(ABTest).where(
            and_(ABTest.test_id == test_id, ABTest.is_deleted == 0)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_critic_details_by_job(self, job_id: str) -> List[CriticScoreDetail]:
        """
        获取 Job 下各 Critic Expert 的评分明细
        
        按 expert_func 分组统计：平均分、通过数、不通过数、通过率
        """
        # 查询该 job 的所有 critic 评分记录，按 expert_func 分组统计
        stmt = (
            select(
                CriticScoreRecord.expert_func,
                CriticScoreRecord.expert_config_code,
                CriticScoreRecord.model_code,
                func.count(CriticScoreRecord.id).label("total_count"),
                func.avg(CriticScoreRecord.score).label("avg_score"),
                func.sum(CriticScoreRecord.passed).label("pass_count"),
            )
            .where(CriticScoreRecord.job_id == job_id)
            .group_by(
                CriticScoreRecord.expert_func,
                CriticScoreRecord.expert_config_code,
                CriticScoreRecord.model_code,
            )
            .order_by(CriticScoreRecord.expert_func)
        )
        
        result = await self.db.execute(stmt)
        rows = result.all()
        
        critic_details: List[CriticScoreDetail] = []
        for row in rows:
            total_count = row.total_count or 0
            pass_count = int(row.pass_count or 0)
            fail_count = total_count - pass_count
            pass_rate = round(pass_count / total_count * 100, 2) if total_count > 0 else 0
            avg_score = round(float(row.avg_score or 0), 2)
            
            critic_details.append(CriticScoreDetail(
                expert_func=row.expert_func,
                expert_config_code=row.expert_config_code,
                model_code=row.model_code,
                total_count=total_count,
                avg_score=avg_score,
                pass_count=pass_count,
                fail_count=fail_count,
                pass_rate=pass_rate,
            ))
        
        return critic_details

    def _to_response(self, ab_test: ABTest) -> ABTestResponse:
        """转换模型为响应对象"""
        return ABTestResponse(
            id=ab_test.id,
            test_id=ab_test.test_id,
            test_name=ab_test.test_name,
            test_type=ab_test.test_type,
            debug_history_ids=ab_test.debug_history_ids,
            job_ids=ab_test.job_ids,
            groups=ab_test.groups,
            metrics=ab_test.metrics,
            winner=ab_test.winner,
            recommendation=ab_test.recommendation,
            status=ab_test.status,
            start_time=ab_test.start_time,
            end_time=ab_test.end_time,
            create_time=ab_test.create_time,
            update_time=ab_test.update_time,
            created_by=ab_test.created_by,
            remark=ab_test.remark,
        )
