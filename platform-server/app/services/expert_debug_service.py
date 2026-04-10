"""
Expert 调试服务
"""
import asyncio
import random
import time
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func, update
from sqlalchemy.orm import attributes
from loguru import logger

from app.models.expert_debug_history import ExpertDebugHistory
from app.models.expert_config import ExpertConfig
from app.models.expert_call_trace import ExpertCallTrace
from app.models.plugin import Plugin
from app.models.plugin_context import PluginContext
from app.models.content import Content
from app.models.expert_batch_score_result import ExpertBatchScoreResult
from app.models.expert_debug_batch_task import ExpertDebugBatchTask
from app.services.expert_config_service import ExpertConfigService
from app.services.plugin_context_service import PluginContextService
from app.services.diversity_analysis_service import DiversityAnalysisService
from app.schemas.diversity_analysis import DiversityAnalysisRequest
from app.services.richness_analysis_service import RichnessAnalysisService
from app.schemas.richness_analysis import RichnessAnalysisRequest
from app.services.critic_score_service import CriticScoreService
from app.utils.job_test_helper import JobTestHelper
from app.utils.expert_caller import ExpertCaller, TraceData
from app.schemas.expert_debug import (
    ExpertDebugRequest,
    ExpertDebugResponse,
    TokenUsage,
    PreviewPromptRequest,
    PreviewPromptResponse,
    PluginVariable,
    PluginVariableOption,
    PluginVariablesResponse,
    ExpertPluginVariablesResponse,
    BatchDebugRequest,
    BatchDebugResponse,
    BatchDebugResultItem,
    StrategyInfo,
    StrategyNodeInfo,
)


from app.services.trace_service import TraceService
from app.schemas.trace import TraceSpanCreate

class ExpertDebugService:
    """Expert 调试服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.expert_config_service = ExpertConfigService(db)
        self.context_service = PluginContextService(db)
        self.trace_service = TraceService(db)

    async def debug(self, request: ExpertDebugRequest) -> ExpertDebugResponse:
        """
        执行 Expert 调试
        
        Args:
            request: 调试请求
        
        Returns:
            调试响应
        """
        start_time = time.time()
        trace_id = f"trace-{uuid.uuid4().hex[:8]}"
        sub_job_id = f"debug-{uuid.uuid4().hex[:12]}"
        
        # 创建追踪数据上下文
        trace_data = TraceData(
            job_id=f"debug_{request.expert_config_code}",
            sub_job_id=sub_job_id,
            content_id=sub_job_id,  # Debug 模式下 content_id 与 sub_job_id 相同
            trace_id=trace_id,
        )
        
        # 获取 Expert 配置
        expert_config = await self.expert_config_service.get_by_code(request.expert_config_code)
        if not expert_config:
            return await self._save_and_return_error(
                request=request,
                error_message=f"ExpertConfig '{request.expert_config_code}' not found",
                trace_id=trace_id,
                execution_time_ms=int((time.time() - start_time) * 1000)
            )
        
        try:
            # 确定使用的模型配置
            model_code = request.model_code or expert_config.model_code
            model_config_used = {
                **(expert_config.model_config or {}),
                **(request.model_cfg_override or {})
            }
            
            # 构建 plugin_config_snapshot
            if request.plugin_config_snapshot:
                plugin_config_snapshot = request.plugin_config_snapshot
            elif expert_config.plugin_config:
                plugin_config_snapshot = await JobTestHelper.build_plugin_config_snapshot(
                    self.db,
                    expert_config.expert_config_code,
                    expert_config.plugin_config
                )
            else:
                plugin_config_snapshot = []
            
            # 渲染 Prompt
            tenant_code = expert_config.tenant_code or "default"
            if request.prompt_override:
                rendered_prompt = request.prompt_override
            elif expert_config.prompt_template:
                rendered_prompt = await JobTestHelper.render_prompt_with_snapshot_and_context(
                    self.db,
                    expert_config.prompt_template,
                    plugin_config_snapshot,
                    tenant_code=tenant_code
                )
            else:
                rendered_prompt = ""
            
            # 构建调用 payload
            payload = ExpertCaller.build_expert_payload(
                job_id=f"debug_{trace_id}",
                sub_job_id=f"debug_{trace_id}",
                content_id=f"debug_{trace_id}",
                expert_task_id=0,
                expert_config_code=expert_config.expert_config_code,
                prompt=rendered_prompt,
                content=request.content,
                model_code=model_code,
                model_config=model_config_used,
                plugin_config_snapshot=plugin_config_snapshot
            )
            
            # 根据 expert_type 调用不同的服务
            if expert_config.expert_type.upper() == "ANALYSIS":
                # ... (Analysis logic)
                trace_info = None
            else:
                logger.debug(f"[DEBUG LOG] Calling Expert: app={expert_config.expert_app}, method={expert_config.expert_service}/{expert_config.expert_func}")
                # 其他类型：通过 Dapr HTTP 调用 Expert 服务（异步）
                call_result = await ExpertCaller.call_expert(
                    expert_app=expert_config.expert_app,
                    expert_service=expert_config.expert_service,
                    expert_func=expert_config.expert_func,
                    payload=payload,
                    trace_data=TraceData(
                        job_id=f"debug_{trace_id}",
                        sub_job_id=f"debug_{trace_id}",
                        trace_id=trace_id
                    )
                )

                logger.debug(f"[DEBUG LOG] Expert Call Returned. Keys: {call_result.keys() if isinstance(call_result, dict) else 'Not Dict'}")

                # 解析返回结果（可能包含追踪信息）
                if isinstance(call_result, dict) and "trace_info" in call_result:
                    response_data = call_result.get("response", {})
                    trace_info = call_result.get("trace_info", {})
                    logger.debug(f"[DEBUG LOG] trace_info found in response: {trace_info}")
                else:
                    response_data = call_result
                    trace_info = None
                    logger.debug(f"[DEBUG LOG] No trace_info in response. response_data keys: {response_data.keys() if isinstance(response_data, dict) else 'Not Dict'}")

            execution_time_ms = int((time.time() - start_time) * 1000)

            # 提取输出内容和 token 使用情况
            # Expert 服务可能返回不同字段：
            # - GENERATION 类型: generatedContent
            # - CRITIC 类型: reason, message, score
            # - 其他类型: content, result

            # 优先从字段中提取，GENERATION 类型排除 "生成成功" 等状态词作为内容
            output_content = (
                response_data.get("generatedContent", "")
                or response_data.get("generated_content")
                or response_data.get("content", "")
                or response_data.get("result", "")
            )

            # 如果是 GENERATION 类型且提取的内容太短或包含状态词，尝试从全量输出中解析
            if expert_config.expert_type.upper() == "GENERATION":
                if not output_content or output_content in ["生成成功", "SUCCESS"]:
                    # 尝试从 expert_total_output 找更合适的字段
                    output_content = response_data.get("generated_content") or response_data.get("content", "")
            else:
                # 非生成类可以接受 reason 或 message
                if not output_content:
                    output_content = response_data.get("reason", "") or response_data.get("message", "")
            
            # 如果是 CRITIC 类型，构建更详细的输出
            if not output_content and "score" in response_data:
                score = response_data.get("score")
                reason = response_data.get("reason", "")
                message = response_data.get("message", "")
                output_content = f"评分: {score}\n原因: {reason}\n消息: {message}"
            
            # 构建结果摘要
            result_summary = {
                "generated_content_preview": output_content[:500] if output_content else "",
                "content_id": response_data.get("contentId") or response_data.get("content_id"),
                "success": True,
            }
            
            # 记录追踪到数据库
            logger.debug(f"[DEBUG LOG] Ready to save trace. trace_info is {'Present' if trace_info else 'None'}")

            if trace_info:
                # 补充必要字段 (Provider Code 从 Trace Data 中提取或回退)
                current_provider = (
                    trace_info.get("provider_code") or
                    (response_data.get("metadata", {}).get("provider") if isinstance(response_data, dict) else None) or
                    (response_data.get("provider") if isinstance(response_data, dict) else None)
                )
                logger.debug(f"[DEBUG LOG] Extracted provider: {current_provider}")

                trace_info["provider_code"] = current_provider

                # 如果依然没拿到 Provider，尝试通过 Model Code 反查 (兜底策略)
                current_model = trace_info.get("model_code") or model_code
                if not current_provider and current_model:
                    logger.debug(f"[DEBUG LOG] Provider is missing. Backfilling for model: {current_model}")
                    try:
                        # 临时查一下路由表 (简单查询，取第一个匹配的)
                        from app.models.llm_model_route import LLMModelRoute
                        stmt = select(LLMModelRoute).where(
                            LLMModelRoute.model_code == current_model,
                            LLMModelRoute.is_deleted == 0
                        ).limit(1)
                        route_res = await self.db.execute(stmt)
                        route = route_res.scalar_one_or_none()
                        if route:
                            current_provider = route.provider_code
                            trace_info["provider_code"] = current_provider
                            logger.debug(f"[DEBUG LOG] Backfilled provider_code '{current_provider}' for model '{current_model}'")
                        else:
                            logger.debug(f"[DEBUG LOG] Backfill failed: No route found for model {current_model}")
                    except Exception as e:
                        logger.error(f"[Expert Debug] Failed to backfill provider_code: {e}")

                # 将 trace_info 转换为 TraceSpanCreate 对象并写入数据库
                try:
                    trace_create = TraceSpanCreate(
                        job_id=trace_info.get("job_id", f"debug_{trace_id}"),
                        sub_job_id=trace_info.get("sub_job_id", trace_id),
                        content_id=trace_info.get("content_id"),
                        trace_id=trace_info.get("trace_id", trace_id),
                        span_id=trace_info.get("span_id", f"span-{uuid.uuid4().hex[:8]}"),
                        stage="debug",
                        expert_config_code=expert_config.expert_config_code,
                        expert_type=expert_config.expert_type,
                        service_app=trace_info.get("service_app", expert_config.expert_app),
                        service_method=trace_info.get("service_method", expert_config.expert_func),
                        status=trace_info.get("status", "success"),
                        start_time_ms=int(trace_info.get("start_time", datetime.now()).timestamp() * 1000),
                        end_time_ms=int(trace_info.get("end_time", datetime.now()).timestamp() * 1000),
                        duration_ms=trace_info.get("duration_ms", 0),
                        model_code=trace_info.get("model_code", model_code),
                        provider_code=trace_info.get("provider_code"), # 关键：传入 Provider Code
                        input_tokens=trace_info.get("input_tokens", 0),
                        output_tokens=trace_info.get("output_tokens", 0),
                        total_tokens=trace_info.get("total_tokens", 0),
                        experiment_id=trace_info.get("experiment_id"),
                        experiment_group=trace_info.get("experiment_group"),
                    )

                    logger.debug(f"[DEBUG LOG] Calling TraceService.create_trace_span with: provider={trace_create.provider_code}, model={trace_create.model_code}, tokens={trace_create.total_tokens}")
                    await self.trace_service.create_trace_span(trace_create)
                    logger.error(f"[Expert Debug] Trace saved successfully: {trace_create.span_id}")
                except Exception as e:
                    logger.error(f"[Expert Debug] Failed to save trace to DB: {e}", exc_info=True)

            token_usage_data = response_data.get("token_usage") or response_data.get("usage")
            
            token_usage = None
            if token_usage_data:
                token_usage = TokenUsage(
                    prompt_tokens=token_usage_data.get("prompt_tokens", 0),
                    completion_tokens=token_usage_data.get("completion_tokens", 0),
                    total_tokens=token_usage_data.get("total_tokens", 0)
                )
            
            # Calculate execution time for success path
            execution_time_ms = int((time.time() - start_time) * 1000)

            # 保存历史记录（包含完整的 Expert 返回结果）
            history = ExpertDebugHistory(
                expert_config_code=expert_config.expert_config_code,
                expert_config_name=expert_config.expert_config_name,
                success=True,
                model_code=model_code,
                model_config_used=model_config_used,
                prompt_template=expert_config.prompt_template,
                plugin_config_snapshot=plugin_config_snapshot,
                rendered_prompt=rendered_prompt,
                prompt_override=request.prompt_override,
                input_content=request.content,
                output_content=output_content,
                expert_total_output=response_data,  # 保存完整的返回结果
                execution_time_ms=execution_time_ms,
                token_usage=token_usage.model_dump() if token_usage else None,
                trace_id=trace_id
            )
            self.db.add(history)
            await self.db.commit()
            await self.db.refresh(history)
            
            # 写入 critic_score_record（仅 CRITIC 类型）
            if expert_config.expert_type.upper() == "CRITIC" and isinstance(response_data, dict):
                try:
                    critic_score = response_data.get("score")
                    if critic_score is not None:
                        critic_score_service = CriticScoreService(self.db)
                        # BAN 类型是 0/1 分制（1=通过），CRITIC 类型是 60 分及格
                        from app.services.critic_score_service import BAN_EXPERT_FUNCS
                        expert_func = expert_config.expert_func
                        score_int = int(critic_score)
                        # 优先使用 API 返回的 passed 字段（BAN 类型专家会返回此字段）
                        passed_from_api = response_data.get("passed")
                        if passed_from_api is not None:
                            # API 返回了 passed 字段，直接使用
                            passed = bool(passed_from_api)
                        else:
                            # API 没有返回 passed 字段，使用兜底逻辑
                            passed = score_int == 1 if expert_func in BAN_EXPERT_FUNCS else score_int >= 60
                        await critic_score_service.create_score_record(
                            job_id=f"debug_{history.id}",
                            sub_job_id=sub_job_id,
                            content_id=f"debug-{history.id}",
                            expert_config_code=expert_config.expert_config_code,
                            expert_func=expert_func,
                            score=score_int,
                            passed=passed,
                            reason=response_data.get("reason"),
                            highlights=response_data.get("highlights"),  # 兼容旧字段
                            problem_tags=response_data.get("problem_tags"),
                            problem_snippets=response_data.get("problem_snippets"),
                            model_code=model_code,
                            duration_ms=execution_time_ms,
                            trace_id=trace_id,
                            # debug 场景专属字段
                            source_type="debug",
                            debug_history_id=history.id,
                        )
                        logger.info(
                            f"[Expert Debug] Saved critic_score_record: "
                            f"debug_history_id={history.id}, expert_func={expert_config.expert_func}, score={critic_score}"
                        )
                except Exception as score_record_err:
                    # 写入评分记录失败不阻断主流程
                    logger.warning(f"[Expert Debug] Failed to save critic_score_record: {score_record_err}")
            
            return ExpertDebugResponse(
                id=history.id,
                success=True,
                expert_config_code=expert_config.expert_config_code,
                expert_config_name=expert_config.expert_config_name,
                model_code=model_code,
                model_config_used=model_config_used,
                prompt_template=expert_config.prompt_template,
                plugin_config_snapshot=plugin_config_snapshot,
                rendered_prompt=rendered_prompt,
                prompt_override=request.prompt_override,
                input_content=request.content,
                output_content=output_content,
                expert_total_output=response_data,  # 返回完整的结果
                execution_time_ms=execution_time_ms,
                token_usage=token_usage,
                trace_id=trace_id,
                create_time=history.create_time
            )
            
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return await self._save_and_return_error(
                request=request,
                expert_config=expert_config,
                error_message=str(e),
                trace_id=trace_id,
                execution_time_ms=execution_time_ms
            )
    
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
                stage="debug",
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
            self.db.add(trace)
            await self.db.commit()
            logger.debug(f"[Expert Debug] Trace saved: span_id={trace_info.get('span_id')}")
        except Exception as e:
            logger.error(f"[Expert Debug] Failed to save trace: {e}")
            # 不抛出异常，追踪记录失败不应影响主流程
    
    async def _save_and_return_error(
        self,
        request: ExpertDebugRequest,
        error_message: str,
        trace_id: str,
        execution_time_ms: int,
        expert_config: Optional[ExpertConfig] = None
    ) -> ExpertDebugResponse:
        """保存错误记录并返回错误响应"""
        history = ExpertDebugHistory(
            expert_config_code=request.expert_config_code,
            expert_config_name=expert_config.expert_config_name if expert_config else None,
            success=False,
            error_message=error_message,
            model_code=request.model_code or (expert_config.model_code if expert_config else None),
            plugin_config_snapshot=request.plugin_config_snapshot,
            prompt_override=request.prompt_override,
            input_content=request.content,
            execution_time_ms=execution_time_ms,
            trace_id=trace_id
        )
        self.db.add(history)
        await self.db.commit()
        await self.db.refresh(history)
        
        return ExpertDebugResponse(
            id=history.id,
            success=False,
            expert_config_code=request.expert_config_code,
            expert_config_name=expert_config.expert_config_name if expert_config else None,
            input_content=request.content,
            execution_time_ms=execution_time_ms,
            error_message=error_message,
            trace_id=trace_id,
            create_time=history.create_time
        )
    
    async def preview_prompt(self, request: PreviewPromptRequest) -> PreviewPromptResponse:
        """
        预览 Prompt 渲染结果
        
        Args:
            request: 预览请求
        
        Returns:
            预览响应
        """
        from app.schemas.expert_debug import PluginSegment
        
        # 获取 Expert 配置
        expert_config = await self.expert_config_service.get_by_code(request.expert_config_code)
        if not expert_config:
            raise ValueError(f"ExpertConfig '{request.expert_config_code}' not found")
        
        # 构建 plugin_config_snapshot
        if request.plugin_config_snapshot:
            plugin_config_snapshot = request.plugin_config_snapshot
        elif expert_config.plugin_config:
            plugin_config_snapshot = await JobTestHelper.build_plugin_config_snapshot(
                self.db,
                expert_config.expert_config_code,
                expert_config.plugin_config
            )
        else:
            plugin_config_snapshot = []

        # 获取实际使用的变量值（兼容策略模式和旧模式）
        variables_used: Dict[str, str] = {}
        all_context_names: set[str] = set()
        all_node_ids: set[str] = set()

        # 第一步：分类收集变量（区分 context_name 和 node_id）
        for plugin_item in plugin_config_snapshot:
            plugin_vars = plugin_item.get("variable_mapping", {})
            for var_name, var_value in plugin_vars.items():
                if not var_value:
                    continue
                # 策略模式：node:id 或 node:id:corpus_index 格式
                if isinstance(var_value, str) and var_value.startswith("node:"):
                    # 支持 node:id1,id2 或 node:id1:0,id2:1 格式，统一提取纯 node_id
                    raw_node_ids = [
                        nid.strip() for nid in var_value[5:].split(",") if nid.strip()
                    ]
                    for raw_id in raw_node_ids:
                        all_node_ids.add(raw_id.split(":")[0])
                # 新模式：keyword_tree 对象（用于后台任务）
                elif isinstance(var_value, dict) and var_value.get("source") == "keyword_tree":
                    # 暂时跳过，由 render_prompt_with_segments 处理
                    pass
                # 旧模式：context_name 字符串
                elif isinstance(var_value, str):
                    all_context_names.add(var_value)

        # 第二步：批量查询旧模式的 context
        context_map: Dict[str, Any] = {}
        if all_context_names:
            context_map = await self.context_service.get_by_context_names_batch(
                list(all_context_names)
            )

        # 第三步：批量查询策略模式的节点语料
        node_map: Dict[str, Any] = {}
        if all_node_ids:
            try:
                from app.utils.job_test_helper import _fetch_corpus_from_tree
                tenant_code = expert_config.tenant_code or "default"
                node_map = await _fetch_corpus_from_tree(list(all_node_ids), tenant_code=tenant_code)
            except Exception as e:
                logger.warning(f"获取节点语料失败: {e}")

        # 第四步：组装 variables_used
        for plugin_item in plugin_config_snapshot:
            plugin_vars = plugin_item.get("variable_mapping", {})
            for var_name, var_value in plugin_vars.items():
                if not var_value:
                    continue

                # 策略模式：node:id 或 node:id:corpus_index 格式
                # 支持逗号分隔的多个 ID：node:id1,id2,id3
                if isinstance(var_value, str) and var_value.startswith("node:"):
                    # 提取 node_id 部分（去掉 "node:" 前缀）
                    node_ids_str = var_value[5:]
                    # 拆分逗号分隔的多个 node_id
                    node_ids = [
                        nid.strip().split(":")[0]
                        for nid in node_ids_str.split(",")
                        if nid.strip()
                    ]

                    # Preview 接口只返回 variables_used，因此这里统一写可读摘要
                    if node_ids:
                        node_names = []
                        for nid in node_ids:
                            node_info = node_map.get(nid)
                            if node_info and isinstance(node_info, dict):
                                node_names.append(node_info.get("name", nid))
                            else:
                                node_names.append(nid)
                        variables_used[var_name] = ",".join(node_names)

                # 新模式：keyword_tree 对象（用于后台任务）
                elif isinstance(var_value, dict) and var_value.get("source") == "keyword_tree":
                    # 暂时显示配置信息
                    node_ids = var_value.get("selected_node_ids", [])
                    variables_used[var_name] = f"[keyword_tree: {len(node_ids)} 个节点]"

                # 旧模式：context_name 字符串
                elif isinstance(var_value, str):
                    plugin_context = context_map.get(var_value)
                    if plugin_context:
                        variables_used[var_name] = plugin_context.context or var_value
                    else:
                        variables_used[var_name] = var_value
        
        # 渲染 Prompt 并获取分段信息
        rendered_prompt = ""
        plugin_segments: List[PluginSegment] = []
        
        # 获取租户编码
        tenant_code = expert_config.tenant_code or "default"

        if expert_config.plugin_config and plugin_config_snapshot:
            # 使用新方法获取分段渲染结果
            rendered_prompt, segments_data = await JobTestHelper.render_prompt_with_segments(
                self.db,
                expert_config.plugin_config,
                plugin_config_snapshot,
                tenant_code=tenant_code
            )
            # 转换为 PluginSegment 对象
            plugin_segments = [
                PluginSegment(
                    plugin_code=seg["plugin_code"],
                    plugin_name=seg["plugin_name"],
                    content=seg["content"]
                )
                for seg in segments_data
            ]
        elif expert_config.prompt_template:
            # 没有 plugin_config 时使用原始模板渲染
            rendered_prompt = await JobTestHelper.render_prompt_with_snapshot_and_context(
                self.db,
                expert_config.prompt_template,
                plugin_config_snapshot,
                tenant_code=tenant_code
            )
        
        return PreviewPromptResponse(
            expert_config_code=expert_config.expert_config_code,
            prompt_template=expert_config.prompt_template,
            plugin_config=expert_config.plugin_config,
            plugin_config_snapshot=plugin_config_snapshot,
            rendered_prompt=rendered_prompt,
            plugin_segments=plugin_segments,
            variables_used=variables_used
        )
    
    async def get_plugin_variables(self, expert_config_code: str) -> ExpertPluginVariablesResponse:
        """
        获取 Expert 关联的所有 Plugin 变量选项（性能优化版：批量查询）

        Args:
            expert_config_code: Expert 配置编码

        Returns:
            Plugin 变量列表
        """
        # 重新查询 Expert 配置以确保获取最新的 plugin_config（避免 SQLAlchemy session 缓存）
        # 使用新的查询而不是刷新，确保绕过 session 缓存，直接从数据库获取最新数据
        stmt = select(ExpertConfig).where(
            ExpertConfig.expert_config_code == expert_config_code,
            ExpertConfig.is_deleted == 0
        )
        result = await self.db.execute(stmt)
        expert_config = result.scalar_one_or_none()
        
        if not expert_config:
            raise ValueError(f"ExpertConfig '{expert_config_code}' not found")

        if not expert_config.plugin_config:
            return ExpertPluginVariablesResponse(
                expert_config_code=expert_config_code,
                plugins=[],
            )

        # ========== 第一步：收集所有需要查询的 context_names、node_ids 和 plugin_codes ==========
        all_context_names: set[str] = set()
        all_plugin_codes: set[str] = set()
        all_node_ids: set[str] = set()  # 新模式：关键词树节点 ID
        keyword_tree_vars: dict[str, dict] = {}  # 新模式变量配置缓存

        for plugin_item in expert_config.plugin_config:
            plugin_code = plugin_item.get("plugin_code")
            if plugin_code:
                all_plugin_codes.add(plugin_code)

            variables = plugin_item.get("variable_mapping", {})
            for var_name, context_value in variables.items():
                # 新模式：keyword_tree 对象
                if isinstance(context_value, dict) and context_value.get("source") == "keyword_tree":
                    node_ids = context_value.get("selected_node_ids", [])
                    all_node_ids.update([str(nid) for nid in node_ids])
                    keyword_tree_vars[f"{plugin_code}:{var_name}"] = context_value
                # 旧模式：字符串或字符串数组
                elif isinstance(context_value, str):
                    all_context_names.add(context_value)
                elif isinstance(context_value, list):
                    all_context_names.update(context_value)

        # ========== 第二步：批量查询所有 Context（旧模式，1次查询） ==========
        context_map = await self.context_service.get_by_context_names_batch(
            list(all_context_names)
        )

        # ========== 第三步：批量查询关键词树节点（新模式） ==========
        node_map: dict[str, dict] = {}
        if all_node_ids:
            try:
                from app.utils.job_test_helper import _fetch_corpus_from_tree
                # 使用 expert_config 的 tenant_code
                tenant_code = expert_config.tenant_code or "default"
                node_map = await _fetch_corpus_from_tree(list(all_node_ids), tenant_code=tenant_code)
            except Exception as e:
                logger.warning(f"获取关键词树节点失败: {e}")

        # ========== 第四步：批量查询所有 Plugin（1次查询） ==========
        plugin_map: dict[str, Plugin] = {}
        if all_plugin_codes:
            stmt = select(Plugin).where(
                and_(
                    Plugin.plugin_code.in_(list(all_plugin_codes)),
                    Plugin.is_deleted == 0,
                )
            )
            result = await self.db.execute(stmt)
            for plugin in result.scalars().all():
                plugin_map[plugin.plugin_code] = plugin

        # ========== 第四.五步：获取策略模式的节点池详情（性能优化：并行查询） ==========
        strategy_node_pools: dict[int, dict] = {}  # {strategy_id: {label: [node_details]}}
        strategy_details: dict[int, dict] = {}  # {strategy_id: strategy_info}

        # 收集所有需要查询的 strategy_id（去重）
        unique_strategy_ids: set[int] = set()
        strategy_to_plugins: Dict[int, List[str]] = {}
        for plugin in plugin_map.values():
            if plugin.strategy_id and plugin.variable_mappings:
                unique_strategy_ids.add(plugin.strategy_id)
                strategy_to_plugins.setdefault(plugin.strategy_id, []).append(
                    plugin.plugin_code
                )

        # 并行查询所有策略详情和节点池（添加全局超时控制）
        if unique_strategy_ids:
            from app.utils.strategy_helper import fetch_strategy_detail, fetch_strategy_node_pool_details
            tenant_code = expert_config.tenant_code or "default"

            # 使用 asyncio.gather 并行查询所有策略
            fetch_tasks = []
            for strategy_id in unique_strategy_ids:
                fetch_tasks.append(
                    self._fetch_single_strategy(
                        strategy_id=strategy_id,
                        tenant_code=tenant_code,
                        expert_config_code=expert_config_code,
                        plugin_codes=strategy_to_plugins.get(strategy_id, []),
                    )
                )

            # 并行执行所有查询，添加全局超时控制（8秒，留 2 秒给其他操作）
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*fetch_tasks, return_exceptions=True),
                    timeout=8.0
                )

                # 处理结果
                for result in results:
                    if isinstance(result, Exception):
                        logger.warning(f"策略查询失败: {result}")
                        continue

                    if result:
                        # result 是元组 (strategy_id, strategy, pool_details)
                        strategy_id, strategy, pool_details = result
                        if pool_details:
                            # pool_details 已经是按 label 组织的节点池详情
                            strategy_node_pools[strategy_id] = pool_details
                        # 存储策略详情（包含 strategy_name）
                        if strategy:
                            strategy_details[strategy_id] = strategy
            except asyncio.TimeoutError:
                logger.warning(f"策略查询全局超时，跳过策略节点池详情加载")

        # ========== 第五步：组装结果 ==========
        plugins_response: List[PluginVariablesResponse] = []

        for plugin_item in expert_config.plugin_config:
            plugin_code = plugin_item.get("plugin_code")
            variables = plugin_item.get("variable_mapping", {})

            if not plugin_code:
                continue

            plugin = plugin_map.get(plugin_code)
            plugin_variables: List[PluginVariable] = []

            # ========== 策略绑定模式 (strategy_id + variable_mappings) ==========
            if plugin and plugin.strategy_id and plugin.variable_mappings:
                strategy = strategy_details.get(plugin.strategy_id)
                pool_details = strategy_node_pools.get(plugin.strategy_id, {})
                
                # 获取 expert_config.plugin_config 中配置的变量名集合（用于过滤）
                configured_variable_names = set(variables.keys()) if variables else set()
                
                for mapping in plugin.variable_mappings:
                    var_name = mapping.get("variable_name")
                    label = mapping.get("label")
                    if not var_name or not label:
                        continue
                    
                    # 如果 expert_config.plugin_config 中配置了变量，只返回配置中存在的变量
                    # 如果 variable_mapping 为空或未配置，则返回所有变量（兼容旧数据）
                    if configured_variable_names and var_name not in configured_variable_names:
                        continue
                    
                    # 获取该 label 对应的节点数据
                    label_data = pool_details.get(label, {})
                    nodes = label_data.get("nodes", [])
                    select_mode = label_data.get("select_mode", "multiple")
                    
                    # 构建策略节点信息
                    strategy_nodes = [
                        StrategyNodeInfo(
                            node_id=n["id"],
                            node_name=n["name"],
                            corpus_count=n.get("corpus_count", 0),
                            corpus_preview=n.get("corpus_preview"),
                            select_mode=select_mode,
                        )
                        for n in nodes
                    ]

                    plugin_variables.append(
                        PluginVariable(
                            variable_name=var_name,
                            source="strategy",
                            options=[],  # 策略模式不使用 options，使用 strategy_nodes
                            selected=strategy_nodes[0].node_id if strategy_nodes else None,
                            # 不在此添加 strategy_info，在插件级别统一添加
                            strategy_nodes=strategy_nodes,
                        )
                    )
                
                # 策略模式处理完成，跳过旧模式逻辑
                # 策略模式处理（插件级别提供一次 strategy_info）

                # 在插件级别创建统一的策略信息
                plugin_strategy_info = None
                if plugin.strategy_id:
                    # 计算所有维度的节点总数
                    total_nodes = sum(
                        len(pool_details.get(label, {}).get("nodes", []))
                        for label in pool_details.keys()
                    )
                    
                    # 收集所有 label（一个策略可能关联多个维度）
                    labels = list(pool_details.keys()) if pool_details else []
                    
                    # 添加日志：打印构建的策略信息
                    logger.info(
                        f"[plugin_strategy_info] plugin_code={plugin_code}, "
                        f"strategy_id={plugin.strategy_id}, "
                        f"strategy_name={strategy.get('name') if strategy else None}, "
                        f"labels={labels}"
                    )
                    
                    plugin_strategy_info = StrategyInfo(
                        strategy_id=plugin.strategy_id,
                        strategy_name=strategy.get("name", "") if strategy else "",
                        label=",".join(labels) if labels else "",  # 合并所有 label，多个维度用逗号分隔
                        node_count=total_nodes,
                    )

                if plugin_variables:
                    plugins_response.append(
                        PluginVariablesResponse(
                            plugin_code=plugin_code,
                            plugin_name=plugin.plugin_name if plugin else None,
                            variables=plugin_variables,
                            strategy_info=plugin_strategy_info,  # 使用统一的策略信息
                        )
                    )
                continue

            # ========== 以下是旧模式逻辑 ==========
            for var_name, context_value in variables.items():
                options: List[PluginVariableOption] = []

                # 新模式：keyword_tree 对象
                if isinstance(context_value, dict) and context_value.get("source") == "keyword_tree":
                    node_ids = [str(nid) for nid in context_value.get("selected_node_ids", [])]
                    strategy = context_value.get("strategy", "random")
                    label = context_value.get("label", "")

                    for node_id in node_ids:
                        node_data = node_map.get(node_id, {})
                        node_name = node_data.get("name", f"节点{node_id}")
                        corpus_list = node_data.get("corpus", [])

                        # 生成预览文本（展示 fields 内容）
                        if corpus_list:
                            first_corpus = corpus_list[0]
                            if isinstance(first_corpus, dict) and "fields" in first_corpus:
                                # 结构化语料：展示所有字段
                                fields = first_corpus.get("fields", {})
                                preview_parts = []
                                for k, v in fields.items():
                                    v_str = str(v)
                                    if len(v_str) > 30:
                                        preview_parts.append(f"{k}: {v_str[:30]}...")
                                    else:
                                        preview_parts.append(f"{k}: {v_str}")
                                preview = " | ".join(preview_parts)
                            elif isinstance(first_corpus, dict) and "text" in first_corpus:
                                preview = first_corpus.get("text", "")[:150]
                            else:
                                preview = str(first_corpus)[:150]
                        else:
                            preview = "(无语料)"

                        options.append(
                            PluginVariableOption(
                                context_name=node_name,  # 节点名称
                                context_preview=preview,  # 语料内容预览
                                node_id=node_id,  # 节点 ID，用于渲染时获取语料
                            )
                        )

                    if options:
                        # 新模式的 selected 保存完整配置
                        plugin_variables.append(
                            PluginVariable(
                                variable_name=var_name,
                                options=options,
                                selected=options[0].context_name if options else None,
                                source="keyword_tree",
                                keyword_tree_config=context_value,  # 保存原始配置供前端使用
                                strategy=strategy,
                            )
                        )

                # 旧模式：字符串或字符串数组
                else:
                    if isinstance(context_value, str):
                        context_list = [context_value]
                    elif isinstance(context_value, list):
                        context_list = context_value
                    else:
                        continue

                    for context_name in context_list:
                        plugin_context = context_map.get(context_name)
                        if plugin_context:
                            preview = (
                                plugin_context.context[:100]
                                if plugin_context.context
                                else None
                            )
                            if preview and len(plugin_context.context) > 100:
                                preview += "..."

                            options.append(
                                PluginVariableOption(
                                    context_name=context_name, context_preview=preview
                                )
                            )

                    if options:
                        plugin_variables.append(
                            PluginVariable(
                                variable_name=var_name,
                                options=options,
                                selected=options[0].context_name if options else None,
                            )
                        )

            if plugin_variables:
                plugins_response.append(
                    PluginVariablesResponse(
                        plugin_code=plugin_code,
                        plugin_name=plugin.plugin_name if plugin else None,
                        variables=plugin_variables,
                    )
                )

        return ExpertPluginVariablesResponse(
            expert_config_code=expert_config_code, plugins=plugins_response
        )

    async def _fetch_single_strategy(
        self,
        strategy_id: int,
        tenant_code: str,
        expert_config_code: str,
        plugin_codes: List[str],
    ) -> Optional[tuple[int, dict, dict]]:
        """
        查询单个策略的详情和节点池（优化版：减少外部调用）

        Args:
            strategy_id: 策略 ID
            tenant_code: 租户代码
            expert_config_code: Expert 配置编码（用于追踪日志）
            plugin_codes: 触发该策略查询的插件编码列表

        Returns:
            (strategy_id, strategy_detail, pool_details) 或 None
        """
        logger.info(f"[_fetch_single_strategy] Starting fetch for strategy_id={strategy_id}")
        
        try:
            from app.utils.strategy_helper import fetch_strategy_detail, fetch_strategy_node_pool_details

            # 使用较短的超时时间，避免累积超时
            strategy = await asyncio.wait_for(
                fetch_strategy_detail(strategy_id, tenant_code),
                timeout=5.0  # 5秒超时
            )
            logger.info(f"[_fetch_single_strategy] fetch_strategy_detail returned: type={type(strategy)}, is_empty={not strategy}")
            
            if not strategy:
                logger.info(
                    f"策略不存在或已删除，跳过策略详情加载: "
                    f"expert_config={expert_config_code}, "
                    f"strategy_id={strategy_id}, "
                    f"plugin_codes={plugin_codes}"
                )
                return None

            node_pools = strategy.get("node_pools", {})
            pool_details = {}

            # 添加日志：检查 node_pools
            logger.info(f"[_fetch_single_strategy] strategy_id={strategy_id}, node_pools keys={list(node_pools.keys()) if isinstance(node_pools, dict) else type(node_pools)}")

            # 如果有节点池，查询节点池详情（使用较短超时）
            if node_pools:
                try:
                    logger.info(f"[_fetch_single_strategy] Fetching node pool details for strategy_id={strategy_id}")
                    pool_details = await asyncio.wait_for(
                        fetch_strategy_node_pool_details(
                            strategy_id, node_pools, tenant_code
                        ),
                        timeout=5.0  # 5秒超时
                    )
                    logger.info(f"[_fetch_single_strategy] Got pool_details for strategy_id={strategy_id}, keys={list(pool_details.keys()) if pool_details else 'empty'}")
                except asyncio.TimeoutError:
                    logger.warning(f"获取节点池详情超时: strategy_id={strategy_id}")
                    # 超时时返回空节点池，不影响主流程
                    pool_details = {}
                except Exception as e:
                    logger.error(f"获取节点池详情异常: strategy_id={strategy_id}, error={e}", exc_info=True)
                    pool_details = {}
            else:
                logger.info(f"[_fetch_single_strategy] No node_pools for strategy_id={strategy_id}")

            # 添加日志：打印返回的策略详情
            logger.info(
                f"[_fetch_single_strategy] Returning strategy: id={strategy_id}, "
                f"name={strategy.get('name') if strategy else None}, "
                f"strategy_keys={list(strategy.keys()) if strategy else []}"
            )
            return (strategy_id, strategy, pool_details)

        except asyncio.TimeoutError:
            logger.warning(
                f"获取策略详情超时: "
                f"expert_config={expert_config_code}, "
                f"strategy_id={strategy_id}, "
                f"plugin_codes={plugin_codes}"
            )
            return None
        except Exception as e:
            logger.warning(
                f"获取策略详情失败: "
                f"expert_config={expert_config_code}, "
                f"strategy_id={strategy_id}, "
                f"plugin_codes={plugin_codes}, error={e}"
            )
            return None

    async def get_history_list(
        self,
        expert_config_code: Optional[str] = None,
        success: Optional[bool] = None,
        is_starred: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[List[ExpertDebugHistory], int]:
        """
        获取调试历史列表
        
        Args:
            expert_config_code: 筛选特定 Expert
            success: 筛选成功/失败
            is_starred: 筛选收藏
            page: 页码
            page_size: 每页数量
        
        Returns:
            (历史记录列表, 总数)
        """
        conditions = [ExpertDebugHistory.is_deleted == 0]
        
        if expert_config_code:
            conditions.append(ExpertDebugHistory.expert_config_code == expert_config_code)
        if success is not None:
            conditions.append(ExpertDebugHistory.success == success)
        if is_starred is not None:
            conditions.append(ExpertDebugHistory.is_starred == is_starred)
        
        # 获取总数
        count_stmt = select(func.count(ExpertDebugHistory.id)).where(and_(*conditions))
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # 获取列表
        stmt = select(ExpertDebugHistory).where(
            and_(*conditions)
        ).order_by(desc(ExpertDebugHistory.create_time)).offset(
            (page - 1) * page_size
        ).limit(page_size)
        
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        
        return items, total
    
    async def get_history_by_id(self, history_id: int) -> Optional[ExpertDebugHistory]:
        """获取单条历史记录"""
        stmt = select(ExpertDebugHistory).where(
            and_(
                ExpertDebugHistory.id == history_id,
                ExpertDebugHistory.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def star_history(self, history_id: int, is_starred: bool) -> bool:
        """收藏/取消收藏历史记录"""
        # 先检查记录是否存在
        history = await self.get_history_by_id(history_id)
        if not history:
            return False
        
        # 使用显式 UPDATE 语句
        stmt = update(ExpertDebugHistory).where(
            ExpertDebugHistory.id == history_id
        ).values(is_starred=is_starred)
        await self.db.execute(stmt)
        await self.db.commit()
        return True
    
    async def delete_history(self, history_id: int) -> bool:
        """删除历史记录（软删除）"""
        # 先检查记录是否存在
        history = await self.get_history_by_id(history_id)
        if not history:
            return False
        
        # 使用显式 UPDATE 语句
        stmt = update(ExpertDebugHistory).where(
            ExpertDebugHistory.id == history_id
        ).values(is_deleted=1)
        await self.db.execute(stmt)
        await self.db.commit()
        return True

    async def _execute_analysis_expert(
        self,
        expert_config: ExpertConfig,
        plugin_config_snapshot: List[Dict[str, Any]],
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行 ANALYSIS 类型的 Expert（本地调用，不走服务间调用）

        Args:
            expert_config: Expert 配置
            plugin_config_snapshot: 插件配置快照
            payload: 调用 payload

        Returns:
            分析结果字典
        """
        expert_func = expert_config.expert_func.lower() if expert_config.expert_func else ""

        # 从 plugin_config_snapshot 提取参数
        params = self._extract_analysis_params(plugin_config_snapshot)

        logger.info(f"[ANALYSIS Expert] Executing {expert_func} with params: {params}")

        # 根据 expert_func 分发到不同的分析服务
        if "diversity" in expert_func or "多样性" in expert_func:
            return await self._execute_diversity_analysis(params)
        elif "richness" in expert_func or "丰富度" in expert_func:
            return await self._execute_richness_analysis(params)
        elif "guidance" in expert_func or "指导" in expert_func:
            return await self._execute_get_guidance(params)
        else:
            return {
                "error": f"Unknown analysis function: {expert_func}",
                "supported_functions": ["diversity_analysis", "richness_analysis", "get_guidance"]
            }

    def _extract_analysis_params(
        self,
        plugin_config_snapshot: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        从 plugin_config_snapshot 提取分析参数

        支持的变量名：
        - job_id / 任务Job_ID / 任务ID
        - dimensions / 维度dimension / 维度
        """
        params = {}

        for plugin_item in plugin_config_snapshot:
            variable_mapping = plugin_item.get("variable_mapping", {})

            for var_name, context_value in variable_mapping.items():
                # 处理 job_id
                if any(k in var_name.lower() for k in ["job_id", "任务", "job"]):
                    params["job_id"] = context_value

                # 处理 dimensions
                elif any(k in var_name.lower() for k in ["dimension", "维度"]):
                    if isinstance(context_value, list):
                        params["dimensions"] = context_value
                    elif isinstance(context_value, str):
                        # 逗号分隔的字符串
                        params["dimensions"] = [d.strip() for d in context_value.split(",")]

        return params

    async def _execute_diversity_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行多样性分析"""
        job_id = params.get("job_id")
        if not job_id:
            return {"error": "job_id is required", "message": "请在插件中配置任务Job_ID变量"}

        dimensions = params.get("dimensions")

        service = DiversityAnalysisService(self.db)
        request = DiversityAnalysisRequest(
            job_id=job_id,
            dimensions=dimensions,
            include_invalid=False,
            include_test=False
        )

        result = await service.analyze(request)

        # 转换为可序列化的字典
        return {
            "success": True,
            "analysis_type": "diversity_analysis",
            "job_id": result.job_id,
            "total_articles": result.total_articles,
            "analysis_time": result.analysis_time.isoformat() if result.analysis_time else None,
            "dimensions": [
                {
                    "dimension_name": d.dimension_name,
                    "total_count": d.total_count,
                    "distribution": d.distribution,
                    "percentage": d.percentage,
                    "recommended_weights": d.recommended_weights
                }
                for d in result.dimensions
            ],
            "low_coverage_alerts": result.low_coverage_alerts,
            "generation_guidance": result.generation_guidance,
            # 用于调试面板显示
            "generatedContent": self._format_analysis_result(result),
            "content": self._format_analysis_result(result),
        }

    async def _execute_richness_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行丰富度分析"""
        job_id = params.get("job_id")
        if not job_id:
            return {"error": "job_id is required", "message": "请在插件中配置任务Job_ID变量"}

        dimensions = params.get("dimensions")

        service = RichnessAnalysisService(self.db)
        request = RichnessAnalysisRequest(
            job_id=job_id,
            dimensions=dimensions,
            include_invalid=False,
            include_test=False
        )

        result = await service.analyze(request)

        # 转换为可序列化的字典
        return {
            "success": True,
            "analysis_type": "richness_analysis",
            "job_id": result.job_id,
            "total_articles": result.total_articles,
            "analysis_time": result.analysis_time.isoformat() if result.analysis_time else None,
            "richness_score": result.richness_score,
            "score_breakdown": result.score_breakdown.model_dump(),
            "dimensions": [
                {
                    "dimension_name": d.dimension_name,
                    "total_count": d.total_count,
                    "stats": d.stats.model_dump(),
                    "distribution": d.distribution,
                    "percentage": d.percentage,
                    "uniformity_score": d.uniformity_score,
                    "coverage_score": d.coverage_score,
                    "high_score_ratio": d.high_score_ratio
                }
                for d in result.dimensions
            ],
            "gaps": [gap.model_dump() for gap in result.gaps],
            "combo_gaps": [gap.model_dump() for gap in result.combo_gaps],
            "generation_guidance": result.generation_guidance,
            # 用于调试面板显示
            "generatedContent": self._format_richness_result(result),
            "content": self._format_richness_result(result),
        }

    async def _execute_get_guidance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取生文指导权重"""
        job_id = params.get("job_id")
        if not job_id:
            return {"error": "job_id is required", "message": "请在插件中配置任务Job_ID变量"}

        dimensions = params.get("dimensions")

        service = DiversityAnalysisService(self.db)
        guidance = await service.get_generation_guidance(job_id, dimensions)

        return {
            "success": True,
            "analysis_type": "generation_guidance",
            "job_id": job_id,
            "generation_guidance": guidance,
            "generatedContent": self._format_guidance_result(guidance),
            "content": self._format_guidance_result(guidance),
        }

    def _format_analysis_result(self, result) -> str:
        """格式化分析结果为可读文本"""
        lines = [
            f"📊 多样性分析报告",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"📌 任务ID: {result.job_id}",
            f"📝 分析文章数: {result.total_articles}",
            f"⚠️ 低覆盖率告警: {len(result.low_coverage_alerts)} 项",
            "",
        ]

        for dim in result.dimensions:
            lines.append(f"📈 {dim.dimension_name} (共 {dim.total_count} 篇)")
            for option, count in sorted(dim.distribution.items(), key=lambda x: -x[1]):
                pct = dim.percentage.get(option, 0)
                weight = dim.recommended_weights.get(option, 0)
                bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                lines.append(f"  {option}: {count}篇 ({pct}%) [{bar}] 权重:{weight:.2f}")
            lines.append("")

        if result.low_coverage_alerts:
            lines.append("⚠️ 低覆盖率告警:")
            for alert in result.low_coverage_alerts:
                lines.append(f"  - {alert['dimension']}/{alert['option']}: 仅 {alert['count']} 篇 ({alert['percentage']}%)")

        lines.append("")
        lines.append("📋 生文指导权重 (权重越高，越需要补充):")
        for dim_name, weights in result.generation_guidance.items():
            lines.append(f"  {dim_name}:")
            for option, weight in sorted(weights.items(), key=lambda x: -x[1]):
                lines.append(f"    {option}: {weight:.3f}")

        return "\n".join(lines)

    def _format_guidance_result(self, guidance: Dict[str, Dict[str, float]]) -> str:
        """格式化指导权重为可读文本"""
        lines = ["📋 生文指导权重", "━━━━━━━━━━━━━━━━━━━━", ""]

        for dim_name, weights in guidance.items():
            lines.append(f"📈 {dim_name}:")
            for option, weight in sorted(weights.items(), key=lambda x: -x[1]):
                bar = "█" * int(weight * 20) + "░" * (20 - int(weight * 20))
                lines.append(f"  {option}: {weight:.3f} [{bar}]")
            lines.append("")

        return "\n".join(lines)

    def _format_richness_result(self, result) -> str:
        """格式化丰富度分析结果为可读文本"""
        lines = [
            f"📊 内容丰富度分析报告",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"📌 任务ID: {result.job_id}",
            f"📝 分析文章数: {result.total_articles}",
            f"🎯 综合丰富度评分: {result.richness_score:.1f}/100",
            "",
            f"📈 评分分解:",
            f"  ├─ 分布均匀度: {result.score_breakdown.distribution_uniformity:.1f}",
            f"  ├─ 分值覆盖度: {result.score_breakdown.coverage_rate:.1f}",
            f"  └─ 高分占比: {result.score_breakdown.high_score_ratio:.1f}",
            "",
        ]

        # 各维度详情
        lines.append("📋 各维度分析:")
        for dim in result.dimensions:
            lines.append(f"  ▶ {dim.dimension_name}")
            lines.append(f"    统计: 均值={dim.stats.avg:.1f}, 标准差={dim.stats.std:.1f}, 范围=[{dim.stats.min:.0f}-{dim.stats.max:.0f}]")
            lines.append(f"    评分: 均匀度={dim.uniformity_score:.1f}%, 覆盖度={dim.coverage_score:.1f}%, 高分比={dim.high_score_ratio:.1f}%")

            # 分布条形图
            if dim.distribution:
                dist_str = " ".join([f"{k}:{v}" for k, v in sorted(dim.distribution.items(), key=lambda x: int(x[0]))])
                lines.append(f"    分布: {dist_str}")
            lines.append("")

        # 缺口分析
        if result.gaps:
            lines.append("⚠️ 内容缺口告警:")
            for gap in result.gaps[:10]:  # 最多显示10条
                if gap.gap_type == "missing_values":
                    lines.append(f"  - {gap.dimension}: 缺少分值 {gap.missing_values}")
                elif gap.gap_type == "low_count":
                    lines.append(f"  - {gap.dimension}: 数量过少 {gap.low_count_values}")
            lines.append("")

        # 组合缺口
        if result.combo_gaps:
            lines.append("🔗 组合缺口:")
            for combo in result.combo_gaps[:5]:
                lines.append(f"  - {combo.description}")
            lines.append("")

        # 生成指导
        lines.append("📋 生成指导权重 (按档位: 低/中/高):")
        for dim_name, weights in result.generation_guidance.items():
            weight_str = ", ".join([f"{k}:{v:.2f}" for k, v in weights.items()])
            lines.append(f"  {dim_name}: {weight_str}")

        return "\n".join(lines)
    
    async def batch_score(
        self,
        expert_config_code: str,
        content_ids: Optional[List[str]] = None,
        max_count: Optional[int] = None,
        test_case_only: bool = True,
        concurrency: int = 5,
    ) -> Dict[str, Any]:
        """
        批量评分：获取文章，并行调用专家评分，保存结果
        
        Args:
            expert_config_code: expert_config 配置 code
            content_ids: 指定 content_id 列表（为空则获取所有符合条件的文章）
            max_count: 最大审核数量（0 或不传表示不限制）
            test_case_only: 是否只查询测试用例（默认 True 保持向后兼容，False 则查询所有文章）
            concurrency: 并行执行数量（默认 5）
        
        Returns:
            批量评分结果
        """
        import asyncio
        
        # 获取 Expert 配置
        expert_config = await self.expert_config_service.get_by_code(expert_config_code)
        if not expert_config:
            raise ValueError(f"ExpertConfig '{expert_config_code}' not found")
        
        # 构建查询
        query = select(Content).where(Content.is_deleted == 0)
        
        # 如果指定了 content_ids，直接按 content_id 查询（不限制 is_test_case）
        if content_ids:
            query = query.where(Content.content_id.in_(content_ids))
        elif test_case_only:
            # 未指定 content_ids 且 test_case_only=True 时，只查询测试用例
            query = query.where(Content.is_test_case == 1)
        
        if max_count and max_count > 0:
            query = query.limit(max_count)
        
        test_cases = await self.db.execute(query)
        test_cases = test_cases.scalars().all()
        
        if not test_cases:
            return {
                "expert_config_code": expert_config_code,
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "results": []
            }
        
        # 预先构建 plugin_config_snapshot（所有文章共用）
        if expert_config.plugin_config:
            plugin_config_snapshot = await JobTestHelper.build_plugin_config_snapshot(
                self.db,
                expert_config.expert_config_code,
                expert_config.plugin_config
            )
        else:
            plugin_config_snapshot = []
        
        # 预先渲染 Prompt（所有文章共用模板）
        rendered_prompt_template = ""
        if expert_config.prompt_template:
            rendered_prompt_template = await JobTestHelper.render_prompt_with_snapshot_and_context(
                self.db,
                expert_config.prompt_template,
                plugin_config_snapshot
            )
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(concurrency)
        results_list: List[Dict] = []
        
        async def score_single_content(test_case: Content) -> Dict:
            """评分单篇文章"""
            async with semaphore:
                return await self._score_single_content(
                    test_case=test_case,
                    expert_config=expert_config,
                    plugin_config_snapshot=plugin_config_snapshot,
                    rendered_prompt_template=rendered_prompt_template,
                )
        
        # 并行执行所有评分任务
        logger.info(f"[BatchScore] Starting parallel scoring: {len(test_cases)} articles, concurrency={concurrency}")
        tasks = [score_single_content(tc) for tc in test_cases]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        results = []
        success_count = 0
        failed_count = 0
        
        for r in results_list:
            if isinstance(r, Exception):
                failed_count += 1
                logger.error(f"[BatchScore] Task exception: {r}")
            elif isinstance(r, dict):
                if r.get("success"):
                    success_count += 1
                else:
                    failed_count += 1
                if r.get("result"):
                    results.append(r["result"])
        
        logger.info(f"[BatchScore] Completed: success={success_count}, failed={failed_count}")
        
        return {
            "expert_config_code": expert_config_code,
            "total": len(test_cases),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results
        }
    
    async def _score_single_content(
        self,
        test_case: Content,
        expert_config,
        plugin_config_snapshot: List,
        rendered_prompt_template: str,
    ) -> Dict:
        """评分单篇文章（内部方法，使用独立数据库会话）"""
        from app.core.database import async_session_factory
        
        start_time = time.time()
        trace_id = f"batch-{uuid.uuid4().hex[:8]}"
        expert_config_code = expert_config.expert_config_code
        
        # 使用独立的数据库会话
        async with async_session_factory() as db_session:
            try:
                # 构建文章内容
                title = test_case.title or ""
                body = test_case.content or ""
                content = f"【标题】{title}\n\n【正文】{body}"
                
                # 构建调用 payload
                payload = ExpertCaller.build_expert_payload(
                    job_id=f"batch_{trace_id}",
                    sub_job_id=f"batch_{trace_id}",
                    content_id=test_case.content_id,
                    expert_task_id=0,
                    expert_config_code=expert_config_code,
                    prompt=rendered_prompt_template,
                    content=content,
                    model_code=expert_config.model_code,
                    model_config=expert_config.model_config,
                    plugin_config_snapshot=plugin_config_snapshot
                )
                
                # 调用 Expert 服务
                if expert_config.expert_type.upper() == "ANALYSIS":
                    response_data = await self._execute_analysis_expert(
                        expert_config=expert_config,
                        plugin_config_snapshot=plugin_config_snapshot,
                        payload=payload
                    )
                else:
                    trace_data = TraceData(
                        job_id=f"batch_{trace_id}",
                        sub_job_id=f"batch_{trace_id}",
                        content_id=test_case.content_id,
                        trace_id=trace_id,
                    )
                    call_result = await ExpertCaller.call_expert(
                        expert_app=expert_config.expert_app,
                        expert_service=expert_config.expert_service,
                        expert_func=expert_config.expert_func,
                        payload=payload,
                        timeout=120,
                        trace_data=trace_data,
                        expert_config_code=expert_config_code,
                        expert_type=expert_config.expert_type,
                    )
                    if isinstance(call_result, dict) and "trace_info" in call_result:
                        response_data = call_result.get("response", {})
                    else:
                        response_data = call_result
                
                execution_time_ms = int((time.time() - start_time) * 1000)
                
                data = response_data if isinstance(response_data, dict) else {}

                # 提取评分结果（JSON 输出）
                score = data.get("score")
                reason = data.get("reason", "")
                highlights = data.get("highlights", "")  # 兼容旧字段
                problem_tags = data.get("problem_tags")
                problem_snippets = data.get("problem_snippets")
                
                # 保存结果到 expert_batch_score_result 表
                result = ExpertBatchScoreResult(
                    expert_config_code=expert_config_code,
                    content_id=test_case.content_id,
                    title=title,
                    content=body,
                    score=score,
                    reason=reason,
                    highlights=highlights,
                    problem_tags=problem_tags if isinstance(problem_tags, list) else None,
                    problem_snippets=problem_snippets if isinstance(problem_snippets, list) else None,
                    model_code=expert_config.model_code,
                    execution_time_ms=execution_time_ms,
                    success=True
                )
                db_session.add(result)
                await db_session.commit()
                await db_session.refresh(result)
                
                # 同步写入 critic_score_record 表（CRITIC/BAN 类型）
                if expert_config.expert_type.upper() in ("CRITIC", "BAN") and score is not None:
                    try:
                        critic_score_service = CriticScoreService(db_session)
                        # 优先使用 API 返回的 passed 字段（BAN 类型专家会返回此字段）
                        passed_from_api = data.get("passed")
                        if passed_from_api is not None:
                            # API 返回了 passed 字段，直接使用
                            passed = bool(passed_from_api)
                        else:
                            # API 没有返回 passed 字段，使用兜底逻辑
                            # 判断是否通过（BAN 类型 1=通过，CRITIC 类型 >=60 通过）
                            passed = score == 1 if expert_config.expert_type.upper() == "BAN" else score >= 60
                        
                        await critic_score_service.create_score_record(
                            job_id=f"batch_{trace_id}",
                            sub_job_id=f"batch_{trace_id}",
                            content_id=test_case.content_id,
                            expert_config_code=expert_config_code,
                            expert_func=expert_config.expert_func,
                            expert_type=expert_config.expert_type,
                            model_code=expert_config.model_code,
                            score=score,
                            passed=passed,
                            reason=reason,
                            problem_tags=problem_tags if isinstance(problem_tags, list) else None,
                            problem_snippets=problem_snippets if isinstance(problem_snippets, list) else None,
                            source_type="batch_score",
                            duration_ms=execution_time_ms,
                            trace_id=trace_id,
                            # 从 Content 表获取 tenant_id 和 activity_id
                            tenant_id=test_case.tenant_id,
                            activity_id=test_case.activity_id,
                        )
                        logger.info(
                            f"[BatchScore] Created critic_score_record: "
                            f"content_id={test_case.content_id}, expert_func={expert_config.expert_func}, score={score}"
                        )
                    except Exception as score_record_err:
                        logger.warning(f"[BatchScore] Failed to create critic_score_record: {score_record_err}")
                
                return {"success": True, "result": result}
                
            except Exception as e:
                execution_time_ms = int((time.time() - start_time) * 1000)
                error_message = str(e)
                logger.error(f"批量评分失败: {expert_config_code}, content_id={test_case.content_id}, error={error_message}")
                
                # 保存失败结果
                result = ExpertBatchScoreResult(
                    expert_config_code=expert_config_code,
                    content_id=test_case.content_id,
                    title=test_case.title or "",
                    content=test_case.content or "",
                    execution_time_ms=execution_time_ms,
                    error_message=error_message,
                    success=False
                )
                db_session.add(result)
                await db_session.commit()
                await db_session.refresh(result)
                
                return {"success": False, "result": result}

    async def batch_debug(self, request: BatchDebugRequest) -> BatchDebugResponse:
        """
        批量随机调试：执行多次随机变量组合的调试

        Args:
            request: 批量调试请求

        Returns:
            批量调试响应
        """
        start_total_time = time.time()

        # 获取 Expert 配置
        expert_config = await self.expert_config_service.get_by_code(request.expert_config_code)
        if not expert_config:
            raise ValueError(f"ExpertConfig '{request.expert_config_code}' not found")

        results: List[BatchDebugResultItem] = []
        success_count = 0
        failed_count = 0

        # 构建所有需要执行的变量快照列表
        snapshots_to_run: List[Optional[List[Dict[str, Any]]]] = []

        # 如果 include_current 且提供了当前变量，首次使用当前变量
        if request.include_current and request.current_plugin_config_snapshot:
            snapshots_to_run.append(request.current_plugin_config_snapshot)
            remaining_count = request.count - 1
        else:
            remaining_count = request.count

        # 生成随机变量快照
        for _ in range(remaining_count):
            if expert_config.plugin_config:
                try:
                    random_snapshot = await JobTestHelper.build_plugin_config_snapshot(
                        self.db,
                        expert_config.expert_config_code,
                        expert_config.plugin_config
                    )
                    snapshots_to_run.append(random_snapshot)
                except Exception as e:
                    logger.warning(f"[Batch Debug] Failed to generate random snapshot: {e}")
                    snapshots_to_run.append(None)
            else:
                snapshots_to_run.append([])

        # 顺序执行调试任务（避免共享 session 的并发问题）
        for i, snapshot in enumerate(snapshots_to_run):
            index = i + 1
            try:
                debug_request = ExpertDebugRequest(
                    expert_config_code=request.expert_config_code,
                    content=request.content,
                    plugin_config_snapshot=snapshot,
                    model_code=request.model_code,
                    model_cfg_override=request.model_cfg_override,
                    prompt_override=request.prompt_override
                )

                result = await self.debug(debug_request)

                # 构建变量摘要
                variable_summary = self._build_variable_summary(snapshot)

                # 构建输出预览
                output_preview = ""
                if result.output_content:
                    output_preview = result.output_content[:200]
                    if len(result.output_content) > 200:
                        output_preview += "..."

                # 从 expert_total_output 中提取标题
                title = ""
                if result.expert_total_output:
                    title = result.expert_total_output.get("title", "") or result.expert_total_output.get("output_title", "") or ""

                results.append(BatchDebugResultItem(
                    index=index,
                    success=result.success,
                    plugin_config_snapshot=snapshot,
                    variable_summary=variable_summary,
                    title=title,
                    output_preview=output_preview,
                    output_content=result.output_content,
                    execution_time_ms=result.execution_time_ms,
                    error_message=result.error_message,
                    history_id=result.id
                ))

                logger.info(f"[Batch Debug] Task {index}/{len(snapshots_to_run)} completed: success={result.success}")

            except Exception as e:
                logger.error(f"[Batch Debug] Task {index} failed: {e}")
                results.append(BatchDebugResultItem(
                    index=index,
                    success=False,
                    plugin_config_snapshot=snapshot,
                    variable_summary=self._build_variable_summary(snapshot),
                    error_message=str(e)
                ))

        # 统计结果
        for result in results:
            if result.success:
                success_count += 1
            else:
                failed_count += 1

        total_time_ms = int((time.time() - start_total_time) * 1000)

        return BatchDebugResponse(
            expert_config_code=expert_config.expert_config_code,
            expert_config_name=expert_config.expert_config_name,
            total=len(results),
            success_count=success_count,
            failed_count=failed_count,
            total_time_ms=total_time_ms,
            results=list(results)
        )

    def _build_variable_summary(self, snapshot: Optional[List[Dict[str, Any]]]) -> str:
        """构建变量摘要字符串"""
        if not snapshot:
            return "(无变量)"

        summary_parts = []
        for plugin_item in snapshot:
            variable_mapping = plugin_item.get("variable_mapping", {})
            for var_name, context_name in variable_mapping.items():
                summary_parts.append(str(context_name))

        if not summary_parts:
            return "(无变量)"

        # 最多显示 3 个，超过则省略
        if len(summary_parts) > 3:
            return " + ".join(summary_parts[:3]) + f" + {len(summary_parts) - 3} more"

        return " + ".join(summary_parts)

    async def create_batch_debug_task(self, request: BatchDebugRequest) -> str:
        """
        创建批量调试任务（异步模式）

        Args:
            request: 批量调试请求

        Returns:
            task_id: 任务唯一标识
        """
        # 获取 Expert 配置
        expert_config = await self.expert_config_service.get_by_code(request.expert_config_code)
        if not expert_config:
            raise ValueError(f"ExpertConfig '{request.expert_config_code}' not found")

        # 生成任务 ID
        task_id = f"batch_debug_{uuid.uuid4().hex[:16]}"

        # 创建任务记录
        task = ExpertDebugBatchTask(
            task_id=task_id,
            expert_config_code=expert_config.expert_config_code,
            expert_config_name=expert_config.expert_config_name,
            status="pending",
            total=request.count,
            completed=0,
            success_count=0,
            failed_count=0,
            request_params=request.model_dump(),
            results=[],
            start_time=None,
            end_time=None
        )

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)

        logger.info(f"[Batch Debug] Created task: {task_id}, total={request.count}")

        return task_id

    async def execute_batch_debug_task(self, task_id: str, db_factory=None):
        """
        执行批量调试任务（后台任务，并行执行）

        Args:
            task_id: 任务 ID
            db_factory: 数据库会话工厂（用于并行执行时创建独立会话）
        """
        import asyncio
        
        try:
            # 查询任务
            result = await self.db.execute(
                select(ExpertDebugBatchTask).where(ExpertDebugBatchTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                logger.error(f"[Batch Debug] Task not found: {task_id}")
                return

            # 更新任务状态为 running
            task.status = "running"
            task.start_time = datetime.now()
            await self.db.commit()

            # 解析请求参数
            request_params = task.request_params
            request = BatchDebugRequest(**request_params)

            # 获取 Expert 配置
            expert_config = await self.expert_config_service.get_by_code(request.expert_config_code)
            if not expert_config:
                raise ValueError(f"ExpertConfig '{request.expert_config_code}' not found")

            # 构建所有需要执行的变量快照列表
            snapshots_to_run: List[Optional[List[Dict[str, Any]]]] = []

            # 如果 include_current 且提供了当前变量，首次使用当前变量
            if request.include_current and request.current_plugin_config_snapshot:
                snapshots_to_run.append(request.current_plugin_config_snapshot)
                remaining_count = request.count - 1
            else:
                remaining_count = request.count

            # 生成随机变量快照
            for _ in range(remaining_count):
                if expert_config.plugin_config:
                    try:
                        random_snapshot = await JobTestHelper.build_plugin_config_snapshot(
                            self.db,
                            expert_config.expert_config_code,
                            expert_config.plugin_config
                        )
                        snapshots_to_run.append(random_snapshot)
                    except Exception as e:
                        logger.warning(f"[Batch Debug] Failed to generate random snapshot: {e}")
                        snapshots_to_run.append(None)
                else:
                    snapshots_to_run.append([])

            # 定义单个执行任务的异步函数
            async def execute_single(index: int, snapshot: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
                """执行单次随机生成"""
                try:
                    logger.info(f"[Batch Debug] Executing index {index}")
                    if db_factory:
                        async with db_factory() as db_session:
                            service = ExpertDebugService(db_session)
                            debug_request = ExpertDebugRequest(
                                expert_config_code=request.expert_config_code,
                                content=request.content,
                                plugin_config_snapshot=snapshot,
                                model_code=request.model_code,
                                model_cfg_override=request.model_cfg_override,
                                prompt_override=request.prompt_override
                            )
                            result = await service.debug(debug_request)
                    else:
                        # 兼容旧调用方式
                        debug_request = ExpertDebugRequest(
                            expert_config_code=request.expert_config_code,
                            content=request.content,
                            plugin_config_snapshot=snapshot,
                            model_code=request.model_code,
                            model_cfg_override=request.model_cfg_override,
                            prompt_override=request.prompt_override
                        )
                        result = await self.debug(debug_request)

                    logger.info(f"[Batch Debug] Index {index} completed, success={result.success}")

                    # 构建变量摘要
                    variable_summary = self._build_variable_summary(snapshot)

                    # 构建输出预览
                    output_preview = ""
                    if result.output_content:
                        output_preview = result.output_content[:200]
                        if len(result.output_content) > 200:
                            output_preview += "..."

                    # 从 expert_total_output 中提取标题
                    title = ""
                    if result.expert_total_output:
                        title = result.expert_total_output.get("title", "") or result.expert_total_output.get("output_title", "") or ""

                    return {
                        "index": index,
                        "success": result.success,
                        "plugin_config_snapshot": snapshot,
                        "variable_summary": variable_summary,
                        "title": title,
                        "output_preview": output_preview,
                        "output_content": result.output_content,
                        "execution_time_ms": result.execution_time_ms,
                        "error_message": result.error_message,
                        "history_id": result.id
                    }
                except Exception as e:
                    logger.error(f"[Batch Debug] Index {index} error: {e}")
                    return {
                        "index": index,
                        "success": False,
                        "plugin_config_snapshot": snapshot,
                        "variable_summary": self._build_variable_summary(snapshot),
                        "error_message": str(e)
                    }

            # 并行执行所有生成任务
            tasks = [execute_single(i + 1, snapshot) for i, snapshot in enumerate(snapshots_to_run)]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理可能的异常结果
            results: List[Dict[str, Any]] = []
            for i, r in enumerate(raw_results):
                if isinstance(r, Exception):
                    logger.error(f"[Batch Debug] Task {i+1} raised exception: {r}")
                    results.append({
                        "index": i + 1,
                        "success": False,
                        "plugin_config_snapshot": snapshots_to_run[i],
                        "variable_summary": self._build_variable_summary(snapshots_to_run[i]),
                        "error_message": str(r)
                    })
                else:
                    results.append(r)
            
            # 按 index 排序
            results.sort(key=lambda x: x.get("index", 0))

            # 更新数据库中的任务状态
            result_query = await self.db.execute(
                select(ExpertDebugBatchTask).where(ExpertDebugBatchTask.task_id == task_id)
            )
            task = result_query.scalar_one_or_none()
            if task:
                task.results = results
                task.completed = len(results)
                task.success_count = sum(1 for r in results if r.get("success"))
                task.failed_count = sum(1 for r in results if not r.get("success"))
                task.status = "completed"
                task.end_time = datetime.now()
                attributes.flag_modified(task, 'results')
                await self.db.commit()
                logger.info(f"[Batch Debug] Task {task_id} completed: success={task.success_count}, failed={task.failed_count}")

        except Exception as e:
            logger.error(f"[Batch Debug] Task {task_id} execution failed: {e}")
            # 更新任务状态为失败
            try:
                result = await self.db.execute(
                    select(ExpertDebugBatchTask).where(ExpertDebugBatchTask.task_id == task_id)
                )
                task = result.scalar_one_or_none()
                if task:
                    task.status = "failed"
                    task.error_message = str(e)
                    task.end_time = datetime.now()
                    await self.db.commit()
            except Exception as commit_error:
                logger.error(f"[Batch Debug] Failed to update task status: {commit_error}")

    async def get_batch_debug_task_status(self, task_id: str) -> Optional[ExpertDebugBatchTask]:
        """
        查询批量调试任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务对象
        """
        result = await self.db.execute(
            select(ExpertDebugBatchTask).where(ExpertDebugBatchTask.task_id == task_id)
        )
        return result.scalar_one_or_none()
