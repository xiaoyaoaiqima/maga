from fastapi import APIRouter
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

from app.services.content_generation_service import ContentGenerationService

router = APIRouter(tags=["dapr-http-invoke"])


class EchoReq(BaseModel):
    message: str = "Hello"


class EchoDataReq(BaseModel):
    data: dict


@router.post("/demo.DemoService/Echo")
async def http_echo(req: EchoReq):
    return {
        "message": req.message,
        "service": "raap_service_generation_experts",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/demo.DemoService/EchoData")
async def http_echo_data(req: EchoDataReq):
    return {
        "message": "Data received successfully",
        "service": "raap_service_generation_experts",
        "timestamp": datetime.utcnow().isoformat(),
        "receivedData": req.data,
    }


class ModelCfg(BaseModel):
    temperature: float = 0.7
    max_tokens: int = 2000


class GenerateByTaskReq(BaseModel):
    job_id: str
    sub_job_id: str
    content_id: str
    expert_task_id: int
    expert_config_code: str
    prompt: str
    model_code: str = "deepseek-v4-flash"
    model_cfg: ModelCfg = Field(alias="model_config")
    content: Optional[str] = None
    brand_id: Optional[int] = None
    activity_id: Optional[int] = None


@router.post("/content_generation.ContentGenerationService/GenerateByTask")
async def http_generate_by_task(req: GenerateByTaskReq):
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"[Dapr HTTP] GenerateByTask received: model={req.model_code}")
    
    service = ContentGenerationService()
    payload = {
        "job_id": req.job_id,
        "sub_job_id": req.sub_job_id,
        "content_id": req.content_id,
        "expert_task_id": req.expert_task_id,
        "expert_config_code": req.expert_config_code,
        "prompt": req.prompt,
        "model_code": req.model_code,
        "model_config": {
            "temperature": req.model_cfg.temperature,
            "max_tokens": req.model_cfg.max_tokens,
        },
    }
    if req.content is not None:
        payload["content"] = req.content
    if req.brand_id is not None:
        payload["brand_id"] = req.brand_id
    if req.activity_id is not None:
        payload["activity_id"] = req.activity_id

    resp = await service.GenerateByTask(payload, None)
    
    provider = getattr(resp, "provider", "")
    
    # 尝试从响应中获取 cost 信息（如果服务层已返回）
    # 注意：TaskGenerateResponse 目前没有定义 cost 字段，可能需要扩展 Schema
    input_cost = getattr(resp, "input_cost", 0.0)
    output_cost = getattr(resp, "output_cost", 0.0)
    total_cost = getattr(resp, "total_cost", 0.0)
    
    # 记录 Trace（Expert 层）
    # 只有当这里作为整个调用的入口时才记录？
    # 或者由 decorator 自动记录？
    # 目前 GenerateByTask 内部已经有详细日志，但 Trace 上报可能在这里补充
    
    logger.info(f"[Dapr HTTP] GenerateByTask completed: success={resp.success}, provider={provider}, cost=${total_cost}")
    
    return {
        "success": bool(getattr(resp, "success", False)),
        "message": getattr(resp, "message", ""),
        "job_id": getattr(resp, "job_id", ""),
        "sub_job_id": getattr(resp, "sub_job_id", ""),
        "content_id": getattr(resp, "content_id", ""),
        "expert_task_id": getattr(resp, "expert_task_id", 0),
        "title": getattr(resp, "title", ""),
        "generated_content": getattr(resp, "generated_content", ""),
        "execution_time": getattr(resp, "execution_time", 0.0),
        "llm_time": getattr(resp, "llm_time", 0.0),
        "input_tokens": getattr(resp, "input_tokens", 0),
        "output_tokens": getattr(resp, "output_tokens", 0),
        "total_tokens": getattr(resp, "total_tokens", 0),
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": total_cost,
        "model_used": getattr(resp, "model_used", ""),
        "provider": provider,
        "error": getattr(resp, "error", ""),
    }
