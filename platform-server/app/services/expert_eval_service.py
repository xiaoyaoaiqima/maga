"""
Expert Eval service - 批量评分（test_case / expert_eval_run / expert_eval_result）
"""
# pylint: disable=not-callable
# pylint: disable=broad-exception-caught

import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Optional, Any

from loguru import logger
from sqlalchemy import and_, func, select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expert_config import ExpertConfig
from app.models.test_case import TestCase
from app.models.expert_eval_run import ExpertEvalRun
from app.models.expert_eval_result import ExpertEvalResult
from app.services.critic_score_service import CriticScoreService
from app.utils.expert_caller import ExpertCaller, TraceData
from app.utils.job_test_helper import JobTestHelper


def _format_article_text(*, title: Optional[str], content: str) -> str:
    title_text = (title or "").strip()
    if not title_text:
        return f"正文：{content}"
    return f"标题：{title_text}\n正文：{content}"


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return int(float(value))
        except Exception:
            return None
    return None


def _extract_critic_fields(
    response_data: dict[str, Any],
) -> tuple[Optional[int], Optional[str], Optional[list], Optional[list], Optional[str]]:
    # 优先走结构化字段
    score = _safe_int(response_data.get("score"))
    reason = response_data.get("reason")
    problem_tags = response_data.get("problem_tags")
    problem_snippets = response_data.get("problem_snippets")
    highlights = response_data.get("highlights")  # 兼容旧字段
    if score is not None or reason is not None or problem_tags is not None or problem_snippets is not None or highlights is not None:
        return score, reason, problem_tags, problem_snippets, highlights

    # 兼容：输出在 message/content/result/generatedContent 里，且为 JSON 字符串
    maybe_text = (
        response_data.get("message")
        or response_data.get("content")
        or response_data.get("result")
        or response_data.get("generatedContent")
        or response_data.get("generated_content")
    )
    if not isinstance(maybe_text, str) or not maybe_text.strip():
        return None, None, None

    text = maybe_text.strip()
    try:
        parsed = json.loads(text)
    except Exception:
        return None, None, None

    if not isinstance(parsed, dict):
        return None, None, None, None, None

    return (
        _safe_int(parsed.get("score")),
        parsed.get("reason"),
        parsed.get("problem_tags"),
        parsed.get("problem_snippets"),
        parsed.get("highlights"),
    )


def _snapshot_expert_config(expert_config: ExpertConfig) -> dict[str, Any]:
    return {
        "expert_config_code": expert_config.expert_config_code,
        "expert_config_name": expert_config.expert_config_name,
        "expert_type": expert_config.expert_type,
        "expert_app": expert_config.expert_app,
        "expert_service": expert_config.expert_service,
        "expert_func": expert_config.expert_func,
        "prompt_template": expert_config.prompt_template,
        "plugin_config": expert_config.plugin_config,
        "model_code": expert_config.model_code,
        "model_config": expert_config.model_config,
    }


class ExpertEvalService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_runs(
        self,
        *,
        expert_config_code: Optional[str],
        test_set_code: Optional[str] = None,
        status: Optional[str],
        page: int,
        page_size: int,
    ) -> tuple[int, list[ExpertEvalRun]]:
        conditions = []
        if expert_config_code:
            conditions.append(ExpertEvalRun.expert_config_code == expert_config_code)
        if test_set_code:
            # 从 JSON 字段 select_params 中筛选 test_set_code
            conditions.append(
                ExpertEvalRun.select_params["test_set_code"].as_string() == test_set_code
            )
        if status:
            conditions.append(ExpertEvalRun.status == status)

        where_clause = and_(*conditions) if conditions else None

        total_stmt = select(func.count()).select_from(ExpertEvalRun)
        if where_clause is not None:
            total_stmt = total_stmt.where(where_clause)
        total = (await self.db.execute(total_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = select(ExpertEvalRun).order_by(desc(ExpertEvalRun.id)).offset(offset).limit(page_size)
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        items = (await self.db.execute(stmt)).scalars().all()
        return total, list(items)

    async def list_results(
        self,
        *,
        run_id: int,
        success: Optional[bool],
        page: int,
        page_size: int,
    ) -> tuple[int, list[ExpertEvalResult]]:
        conditions = [ExpertEvalResult.run_id == run_id]
        if success is not None:
            conditions.append(ExpertEvalResult.success == (1 if success else 0))
        where_clause = and_(*conditions)

        total_stmt = select(func.count()).select_from(ExpertEvalResult).where(where_clause)
        total = (await self.db.execute(total_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = (
            select(ExpertEvalResult)
            .where(where_clause)
            .order_by(desc(ExpertEvalResult.id))
            .offset(offset)
            .limit(page_size)
        )
        items = (await self.db.execute(stmt)).scalars().all()
        return total, list(items)

    async def get_result_detail(
        self,
        *,
        result_id: int,
    ) -> tuple[Optional[ExpertEvalResult], Optional[TestCase]]:
        result = (
            await self.db.execute(select(ExpertEvalResult).where(ExpertEvalResult.id == result_id))
        ).scalar_one_or_none()
        if not result:
            return None, None

        test_case = (
            await self.db.execute(select(TestCase).where(TestCase.id == result.test_case_id))
        ).scalar_one_or_none()
        return result, test_case

    async def create_run(
        self,
        *,
        expert_config_code: str,
        test_set_code: Optional[str],
        test_case_ids: Optional[list[int]],
        max_count: int,
        start_no: Optional[int] = None,
        end_no: Optional[int] = None,
        article_concurrency: int,
        created_by: Optional[str] = None,
    ) -> ExpertEvalRun:
        expert_config = await self._get_expert_config_or_raise(expert_config_code)

        # 先选样，避免创建"total_count=0"的空 run
        selected_test_cases = await self._select_test_cases(
            test_set_code=test_set_code,
            test_case_ids=test_case_ids,
            max_count=max_count,
            start_no=start_no,
            end_no=end_no,
        )
        if not selected_test_cases:
            if test_case_ids:
                raise ValueError("未找到 test_case：请检查 test_case_ids 是否有效且 enabled=1")
            if test_set_code:
                raise ValueError(f"未找到测试用例：test_set_code={test_set_code}（请检查 enabled=1 / is_deleted=0）")
            raise ValueError("未找到测试用例：请先导入 test_case，或在请求里传 test_set_code/test_case_ids")

        run_code = f"eval_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        selected_ids = [tc.id for tc in selected_test_cases]
        select_params = {
            "test_set_code": test_set_code,
            "test_case_ids": test_case_ids,
            "max_count": max_count,
            "start_no": start_no,
            "end_no": end_no,
            "article_concurrency": article_concurrency,
            "selected_ids": selected_ids,
        }

        run = ExpertEvalRun(
            run_code=run_code,
            expert_config_code=expert_config.expert_config_code,
            expert_config_snapshot=_snapshot_expert_config(expert_config),
            select_params=select_params,
            status="running",
            total_count=len(selected_test_cases),
            success_count=0,
            failed_count=0,
            created_by=created_by,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)

        return run

    async def execute_run(self, *, run_id: int) -> None:
        """
        后台执行一个已创建的 run。
        说明：该方法会自行更新 run 的 status/success_count/failed_count/end_time。
        """
        run = (await self.db.execute(select(ExpertEvalRun).where(ExpertEvalRun.id == run_id))).scalar_one_or_none()
        if not run:
            raise ValueError(f"run_id 不存在：{run_id}")

        if run.status != "running":
            # 已执行/已取消则不重复跑
            return

        expert_config = await self._get_expert_config_or_raise(run.expert_config_code)
        select_params = run.select_params or {}

        selected_ids = select_params.get("selected_ids") if isinstance(select_params, dict) else None
        test_cases: list[TestCase]
        if isinstance(selected_ids, list) and selected_ids:
            items = (
                await self.db.execute(select(TestCase).where(and_(TestCase.id.in_(selected_ids), TestCase.is_deleted == 0)))
            ).scalars().all()
            by_id = {x.id: x for x in items}
            test_cases = [by_id[i] for i in selected_ids if i in by_id]
        else:
            test_cases = await self._select_test_cases(
                test_set_code=select_params.get("test_set_code") if isinstance(select_params, dict) else None,
                test_case_ids=select_params.get("test_case_ids") if isinstance(select_params, dict) else None,
                max_count=int(select_params.get("max_count") or 50) if isinstance(select_params, dict) else 50,
                start_no=select_params.get("start_no") if isinstance(select_params, dict) else None,
                end_no=select_params.get("end_no") if isinstance(select_params, dict) else None,
            )

        if not test_cases:
            await self.db.execute(
                update(ExpertEvalRun)
                .where(ExpertEvalRun.id == run.id)
                .values(status="failed", end_time=func.now())
            )
            await self.db.commit()
            return

        try:
            await self._execute_run(
                run=run,
                expert_config=expert_config,
                test_cases=test_cases,
                article_concurrency=int(select_params.get("article_concurrency") or 4) if isinstance(select_params, dict) else 4,
            )
        except Exception as e:
            logger.exception(f"[ExpertEval] execute_run failed: run_id={run.id}, err={e}")
            await self.db.execute(
                update(ExpertEvalRun)
                .where(ExpertEvalRun.id == run.id)
                .values(status="failed", end_time=func.now())
            )
            await self.db.commit()

    async def _get_expert_config_or_raise(self, expert_config_code: str) -> ExpertConfig:
        stmt = select(ExpertConfig).where(
            and_(
                ExpertConfig.expert_config_code == expert_config_code,
                ExpertConfig.is_deleted == 0,
            )
        )
        expert_config = (await self.db.execute(stmt)).scalar_one_or_none()
        if not expert_config:
            raise ValueError(f"expert_config_code 不存在：{expert_config_code}")
        return expert_config

    async def _select_test_cases(
        self,
        *,
        test_set_code: Optional[str],
        test_case_ids: Optional[list[int]],
        max_count: int,
        start_no: Optional[int] = None,
        end_no: Optional[int] = None,
    ) -> list[TestCase]:
        conditions = [TestCase.is_deleted == 0, TestCase.enabled == 1]

        if test_case_ids:
            conditions.append(TestCase.id.in_(test_case_ids))
        else:
            if test_set_code:
                conditions.append(TestCase.test_set_code == test_set_code)
            # test_set_code 为空时：不做过滤，直接取最近的 enabled 用例

        # 范围抽样（按 create_time DESC 的“第 N 篇到第 M 篇”）
        offset = None
        limit = None
        if not test_case_ids and (start_no is not None or end_no is not None):
            s = int(start_no or 1)
            e = int(end_no or s)
            if s < 1:
                raise ValueError("start_no 必须 >= 1")
            if e < s:
                raise ValueError("end_no 必须 >= start_no")
            offset = s - 1
            limit = e - s + 1
        else:
            limit = max_count

        stmt = (
            select(TestCase)
            .where(and_(*conditions))
            .order_by(desc(TestCase.create_time))
        )
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        items = (await self.db.execute(stmt)).scalars().all()
        return list(items)

    async def _execute_run(
        self,
        *,
        run: ExpertEvalRun,
        expert_config: ExpertConfig,
        test_cases: list[TestCase],
        article_concurrency: int,
    ) -> None:
        # plugin_config_snapshot 与 prompt_template 对整次 run 是稳定的，先构建一次
        plugin_config_snapshot = []
        if expert_config.plugin_config:
            plugin_config_snapshot = await JobTestHelper.build_plugin_config_snapshot(
                self.db,
                expert_config.expert_config_code,
                expert_config.plugin_config,
            )

        rendered_prompt_base = ""
        if expert_config.prompt_template:
            rendered_prompt_base = await JobTestHelper.render_prompt_with_snapshot_and_context(
                self.db,
                expert_config.prompt_template,
                plugin_config_snapshot,
            )

        sem = asyncio.Semaphore(article_concurrency)
        db_lock = asyncio.Lock()
        success_count = 0
        failed_count = 0

        async def run_one(case: TestCase) -> None:
            nonlocal success_count, failed_count
            async with sem:
                start_ts = time.time()
                trace_id = f"eval-{uuid.uuid4().hex[:12]}"
                trace_data = TraceData(
                    job_id=f"eval_{run.run_code}",
                    sub_job_id=f"eval_{run.id}_{case.id}",
                    content_id=str(case.id),
                    trace_id=trace_id,
                )

                content_text = _format_article_text(title=case.title, content=case.content)
                prompt = rendered_prompt_base or ""
                if "$content$" in prompt:
                    prompt = prompt.replace("$content$", content_text)

                payload = ExpertCaller.build_expert_payload(
                    job_id=f"eval_{run.run_code}",
                    sub_job_id=f"eval_{run.id}_{case.id}",
                    content_id=str(case.id),
                    expert_task_id=0,
                    expert_config_code=expert_config.expert_config_code,
                    prompt=prompt,
                    content=content_text,
                    model_code=expert_config.model_code,
                    model_config=expert_config.model_config or None,
                    plugin_config_snapshot=plugin_config_snapshot,
                )

                response_data: dict[str, Any] | None = None
                error_message: Optional[str] = None
                is_success = True
                score: Optional[int] = None
                reason: Optional[str] = None
                highlights: Optional[str] = None
                problem_tags: Optional[list] = None
                problem_snippets: Optional[list] = None
                model_code_used: Optional[str] = expert_config.model_code
                token_usage: Optional[dict[str, Any]] = None

                try:
                    call_result = await ExpertCaller.call_expert(
                        expert_app=expert_config.expert_app,
                        expert_service=expert_config.expert_service,
                        expert_func=expert_config.expert_func,
                        payload=payload,
                        timeout=180,
                        trace_data=trace_data,
                        expert_config_code=expert_config.expert_config_code,
                        expert_type=expert_config.expert_type,
                    )
                    if isinstance(call_result, dict) and "trace_info" in call_result:
                        response_data = call_result.get("response", {}) or {}
                    else:
                        response_data = call_result or {}

                    score, reason, problem_tags, problem_snippets, highlights = _extract_critic_fields(response_data)
                    token_usage = response_data.get("token_usage") or response_data.get("usage")
                    if isinstance(response_data.get("model_code"), str):
                        model_code_used = response_data.get("model_code")
                except Exception as e:
                    is_success = False
                    error_message = str(e)
                    response_data = None

                latency_ms = int((time.time() - start_ts) * 1000)

                async with db_lock:
                    result = ExpertEvalResult(
                        run_id=run.id,
                        test_case_id=case.id,
                        score=score,
                        reason=reason,
                        highlights=highlights,
                        problem_tags=problem_tags if isinstance(problem_tags, list) else None,
                        problem_snippets=problem_snippets if isinstance(problem_snippets, list) else None,
                        raw_output=response_data,
                        rendered_prompt=prompt,
                        model_code=model_code_used,
                        provider_code=None,
                        token_usage=token_usage,
                        latency_ms=latency_ms,
                        trace_id=trace_id,
                        success=1 if is_success else 0,
                        error_message=error_message,
                    )
                    self.db.add(result)
                    await self.db.commit()

                    # 同步写入统一的 Critic 事实表（用于可视化）
                    try:
                        score_int = int(score or 0)
                        # 优先使用 API 返回的 passed 字段（BAN 类型专家会返回此字段）
                        passed_from_api = response_data.get("passed") if response_data else None
                        if passed_from_api is not None:
                            # API 返回了 passed 字段，直接使用
                            passed_bool = bool(passed_from_api)
                        else:
                            # API 没有返回 passed 字段，使用兜底逻辑
                            passed_bool = bool(is_success and score_int >= 70)  # 先用默认阈值 70，后续可接入指标定义表
                        critic_service = CriticScoreService(self.db)
                        await critic_service.create_score_record(
                            job_id=f"evalrun_{run.id}",
                            sub_job_id=f"evalrun_{run.id}_{case.id}",
                            content_id=f"tc-{case.id}",
                            expert_task_id=None,
                            expert_config_code=expert_config.expert_config_code,
                            expert_func=expert_config.expert_func,
                            model_code=model_code_used,
                            provider_code=None,
                            score=score_int,
                            passed=passed_bool,
                            reason=reason,
                            highlights=highlights,
                            problem_tags=problem_tags if isinstance(problem_tags, list) else None,
                            problem_snippets=problem_snippets if isinstance(problem_snippets, list) else None,
                            duration_ms=latency_ms,
                            trace_id=trace_id,
                            source_type="eval_run",
                            test_set_code=case.test_set_code,
                            run_id=run.id,
                            test_case_id=case.id,
                        )
                    except Exception:
                        # 不影响主流程（eval_result 已落库）
                        pass

                    if is_success:
                        success_count += 1
                    else:
                        failed_count += 1

                    await self.db.execute(
                        update(ExpertEvalRun)
                        .where(ExpertEvalRun.id == run.id)
                        .values(success_count=success_count, failed_count=failed_count)
                    )
                    await self.db.commit()

        await asyncio.gather(*(run_one(tc) for tc in test_cases))

        await self.db.execute(
            update(ExpertEvalRun)
            .where(ExpertEvalRun.id == run.id)
            .values(status="success", end_time=func.now())
        )
        await self.db.commit()

