"""
Expert service caller utility - Unified method to call expert services via Dapr HTTP
"""
import warnings
import time
import uuid
import re
from datetime import datetime
from typing import Dict, Any, Optional, List

from app.utils.dapr_http import invoke_method

from app.api.v1.endpoints.metrics import (
    dapr_grpc_requests_total,
    dapr_grpc_request_duration_seconds,
    dapr_http_requests_total,
    dapr_http_request_duration_seconds,
)


class TraceData:
    """追踪数据容器"""
    
    def __init__(
        self,
        job_id: str,
        sub_job_id: str,
        content_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        experiment_id: Optional[str] = None,
        experiment_group: Optional[str] = None,
    ):
        self.job_id = job_id
        self.sub_job_id = sub_job_id
        self.content_id = content_id
        self.trace_id = trace_id or f"trace-{uuid.uuid4().hex[:8]}"
        self.experiment_id = experiment_id
        self.experiment_group = experiment_group


class ExpertCaller:
    """Unified expert service caller via Dapr HTTP"""
    
    @staticmethod
    async def call_expert_http(
        expert_app: str,
        method_path: str,
        payload: Dict[str, Any],
        timeout: int = 300,
        trace_data: Optional[TraceData] = None,
        expert_config_code: Optional[str] = None,
        expert_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        通过 Dapr HTTP Invocation 调用内部服务（Async）
        
        Args:
            expert_app: Dapr app ID (e.g., "raap-service-ag")
            method_path: FastAPI path（必须以 /api/v1/ 开头），例如：/api/v1/critic/review-ban
            payload: Request payload dictionary
            timeout: Request timeout in seconds (default: 300)
            trace_data: Optional trace data for recording
            expert_config_code: Expert config code for tracing
            expert_type: Expert type for tracing (GENERATION/VALIDATION/SCORING)
        
        Returns:
            Response data dictionary with optional trace info
        
        Raises:
            Exception: If the HTTP invocation fails
        """
        if not method_path:
            raise ValueError("method_path 不能为空")
        if not method_path.startswith("/"):
            raise ValueError("method_path 必须以 / 开头")
        if not method_path.startswith("/api/v1/"):
            raise ValueError("method_path 必须以 /api/v1/ 开头")

        # invoke_method 内部会拼接：.../method/{method_name}
        # 这里 method_name 不要以 / 开头，避免出现双斜杠/不一致
        method_name = method_path.lstrip("/")
        
        # 生成 span_id
        span_id = f"span-{uuid.uuid4().hex[:8]}"
        start_time = datetime.now()
        start_ts = time.time()
        
        # 追踪信息
        trace_info = None
        headers = {}
        
        if trace_data:
            trace_info = {
                "job_id": trace_data.job_id,
                "sub_job_id": trace_data.sub_job_id,
                "content_id": trace_data.content_id,
                "trace_id": trace_data.trace_id,
                "span_id": span_id,
                "stage": ExpertCaller._infer_stage(method_name, expert_type),
                "expert_config_code": expert_config_code,
                "expert_type": expert_type,
                "service_app": expert_app,
                "service_method": f"/{method_name}",
                "start_time": start_time,
                "experiment_id": trace_data.experiment_id,
                "experiment_group": trace_data.experiment_group,
            }
            
            # 注入追踪 Header
            headers = {
                "X-Trace-ID": trace_data.trace_id,
                "X-Job-ID": trace_data.job_id,
                "X-Sub-Job-ID": trace_data.sub_job_id,
            }
            if trace_data.content_id:
                headers["X-Content-ID"] = trace_data.content_id
            if trace_data.experiment_id:
                headers["X-Experiment-ID"] = trace_data.experiment_id
            if trace_data.experiment_group:
                headers["X-Experiment-Group"] = trace_data.experiment_group

        try:
            # Call via Dapr HTTP Sidecar
            response_data = await invoke_method(expert_app, method_name, payload, timeout=timeout, headers=headers)
            
            # Record success metrics
            duration = time.time() - start_ts
            duration_ms = int(duration * 1000)

            # 指标：保持旧指标兼容，同时写入新 HTTP 指标
            try:
                dapr_grpc_requests_total.labels(
                    target_service=expert_app,
                    method=f"/{method_name}",
                    status="success",
                ).inc()
                dapr_grpc_request_duration_seconds.labels(
                    target_service=expert_app,
                    method=f"/{method_name}",
                ).observe(duration)

                dapr_http_requests_total.labels(
                    target_service=expert_app,
                    method=f"/{method_name}",
                    status="success",
                ).inc()
                dapr_http_request_duration_seconds.labels(
                    target_service=expert_app,
                    method=f"/{method_name}",
                ).observe(duration)
            except Exception:
                # 指标失败不影响主流程
                pass
            
            # 补充追踪信息
            if trace_info:
                trace_info["status"] = "success"
                trace_info["end_time"] = datetime.now()
                trace_info["duration_ms"] = duration_ms
                # 提取元数据（适配不同服务的返回结构）
                metadata = response_data.get("metadata", {})
                usage_data = metadata.get("usage", {}) if isinstance(metadata, dict) else {}
                
                # 辅助函数：多层级查找
                def find_val(keys, default=None):
                    for k in keys:
                        # 1. 顶层查找
                        if k in response_data: return response_data[k]
                        # 2. 顶层 usage 查找 (适配 AG 服务)
                        top_usage = response_data.get("usage")
                        if isinstance(top_usage, dict) and k in top_usage: return top_usage[k]
                        # 3. metadata 查找
                        if isinstance(metadata, dict) and k in metadata: return metadata[k]
                        # 4. metadata.usage 查找
                        if isinstance(usage_data, dict) and k in usage_data: return usage_data[k]
                    return default

                # 从响应中提取 Token 信息（proto3 JSON 使用 camelCase，也兼容 snake_case）
                if isinstance(response_data, dict):
                    trace_info["input_tokens"] = find_val(["inputTokens", "input_tokens", "prompt_tokens"], 0)
                    trace_info["output_tokens"] = find_val(["outputTokens", "output_tokens", "completion_tokens"], 0)
                    trace_info["total_tokens"] = find_val(["totalTokens", "total_tokens"], 0)
                    
                    # 提取模型和供应商信息
                    trace_info["model_code"] = find_val(["modelUsed", "model_used", "modelCode", "model_code", "model"], payload.get("model_code"))
                    trace_info["provider_code"] = find_val(["providerCode", "provider_code", "provider"])
                    
                    # 启发式估算 (当 Provider 未返回 Token 信息时)
                    if trace_info["input_tokens"] == 0:
                        prompt_text = payload.get("prompt") or payload.get("content") or ""
                        if prompt_text:
                            chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', prompt_text))
                            other_chars = len(prompt_text) - chinese_chars
                            trace_info["input_tokens"] = int(chinese_chars * 1.0 + other_chars * 0.3)
                    
                    if trace_info["output_tokens"] == 0:
                        # 尝试从常见响应字段提取文本进行估算
                        resp_text = (
                            response_data.get("content") or 
                            response_data.get("text") or 
                            response_data.get("response") or 
                            response_data.get("result") or ""
                        )
                        if resp_text and isinstance(resp_text, str):
                            chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', resp_text))
                            other_chars = len(resp_text) - chinese_chars
                            trace_info["output_tokens"] = int(chinese_chars * 1.0 + other_chars * 0.3)

                    # 自动计算 total (如果缺失或因估算更新)
                    if trace_info["total_tokens"] == 0 or (trace_info["input_tokens"] + trace_info["output_tokens"] != trace_info["total_tokens"]):
                         trace_info["total_tokens"] = trace_info["input_tokens"] + trace_info["output_tokens"]

                    # 提取 content_id（如果有）
                    content_id = response_data.get("contentId") or response_data.get("content_id")
                    if content_id:
                        trace_info["content_id"] = content_id
                    # 提取 LLM 耗时
                    llm_time = response_data.get("llmTime") or response_data.get("llm_time")
                    if llm_time:
                        trace_info["model_time_ms"] = int(llm_time * 1000)
            
            # 返回响应，附加追踪信息
            if trace_info:
                return {"response": response_data, "trace_info": trace_info}
            return response_data
            
        except TimeoutError as e:
            # Record timeout
            duration = time.time() - start_ts
            duration_ms = int(duration * 1000)

            try:
                dapr_grpc_requests_total.labels(
                    target_service=expert_app,
                    method=f"/{method_name}",
                    status="timeout",
                ).inc()
                dapr_grpc_request_duration_seconds.labels(
                    target_service=expert_app,
                    method=f"/{method_name}",
                ).observe(duration)

                dapr_http_requests_total.labels(
                    target_service=expert_app,
                    method=f"/{method_name}",
                    status="timeout",
                ).inc()
                dapr_http_request_duration_seconds.labels(
                    target_service=expert_app,
                    method=f"/{method_name}",
                ).observe(duration)
            except Exception:
                pass
            
            if trace_info:
                trace_info["status"] = "timeout"
                trace_info["end_time"] = datetime.now()
                trace_info["duration_ms"] = duration_ms
                trace_info["error_type"] = "timeout"
                trace_info["error_message"] = str(e)
            
            raise
            
        except Exception as e:
            # Record failure
            duration = time.time() - start_ts
            duration_ms = int(duration * 1000)

            try:
                dapr_grpc_requests_total.labels(
                    target_service=expert_app,
                    method=f"/{method_name}",
                    status="failed",
                ).inc()
                dapr_grpc_request_duration_seconds.labels(
                    target_service=expert_app,
                    method=f"/{method_name}",
                ).observe(duration)

                dapr_http_requests_total.labels(
                    target_service=expert_app,
                    method=f"/{method_name}",
                    status="failed",
                ).inc()
                dapr_http_request_duration_seconds.labels(
                    target_service=expert_app,
                    method=f"/{method_name}",
                ).observe(duration)
            except Exception:
                pass
            
            if trace_info:
                trace_info["status"] = "failed"
                trace_info["end_time"] = datetime.now()
                trace_info["duration_ms"] = duration_ms
                trace_info["error_type"] = type(e).__name__
                trace_info["error_message"] = str(e)
            
            raise
    
    @staticmethod
    def _infer_stage(expert_func: str, expert_type: Optional[str]) -> str:
        """根据函数名和类型推断阶段"""
        func_lower = expert_func.lower()
        
        if "ban" in func_lower or "illegal" in func_lower:
            return "ag_ban"
        elif "critic" in func_lower or "score" in func_lower:
            return "ag_critic"
        elif expert_type == "GENERATION" or "generate" in func_lower:
            return "ge_generation"
        elif expert_type == "VALIDATION":
            return "ag_validation"
        else:
            return "expert_call"

    @staticmethod
    async def call_expert(
        expert_app: str,
        expert_service: str,
        expert_func: str,
        payload: Dict[str, Any],
        timeout: int = 300,
        trace_data: Optional[TraceData] = None,
        expert_config_code: Optional[str] = None,
        expert_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        兼容入口（历史遗留）：
        - 旧代码按 “service/method（旧风格）” 的语义传参
        - 这里统一映射成 HTTP path 再调用
        """
        warnings.warn(
            "ExpertCaller.call_expert(expert_service, expert_func) 已弃用，请改用 call_expert_http(expert_app, method_path, ...)",
            DeprecationWarning,
            stacklevel=2,
        )
        method_path = f"/api/v1/{expert_service}/{expert_func}"
        return await ExpertCaller.call_expert_http(
            expert_app=expert_app,
            method_path=method_path,
            payload=payload,
            timeout=timeout,
            trace_data=trace_data,
            expert_config_code=expert_config_code,
            expert_type=expert_type,
        )
    
    @staticmethod
    def build_expert_payload(
        job_id: str,
        sub_job_id: str,
        content_id: str,
        expert_task_id: int,
        expert_config_code: str,
        prompt: str,
        content: str,
        model_code: Optional[str] = None,
        model_config: Optional[Dict[str, Any]] = None,
        plugin_config_snapshot: Optional[List[Dict[str, Any]]] = None,
        extra_params: Optional[Dict[str, Any]] = None,
        tenant_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build expert service call payload
        
        Args:
            job_id: Job ID
            sub_job_id: Sub job ID
            content_id: Content ID
            expert_task_id: Expert task ID
            expert_config_code: Expert config code
            prompt: Rendered prompt
            model_code: Model code (optional, can override expert_config)
            model_config: Model configuration (optional, can override expert_config)
            plugin_config_snapshot: Plugin config snapshot，格式: [{plugin_code, variable_mapping}]
            extra_params: Extra parameters (optional)
            tenant_code: Tenant code for multi-tenant isolation (optional)
        
        Returns:
            Payload dictionary
        """
        payload = {
            "job_id": job_id,
            "sub_job_id": sub_job_id,
            "content_id": content_id,
            "expert_task_id": expert_task_id,
            "expert_config_code": expert_config_code,
            "prompt": prompt,
            "content": content
        }
        
        if model_code:
            payload["model_code"] = model_code
        
        if model_config:
            payload["model_config"] = model_config
        
        if plugin_config_snapshot:
            payload["plugin_config_snapshot"] = plugin_config_snapshot
        
        if extra_params:
            payload["extra_params"] = extra_params
        
        # 租户编码（用于多租户隔离，如违禁词过滤）
        if tenant_code:
            payload["tenant_code"] = tenant_code
        
        return payload
