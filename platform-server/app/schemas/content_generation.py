from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ModelConfig(BaseModel):
    temperature: float = 0.7
    max_tokens: int = 2000
    top_p: Optional[float] = None
    top_k: Optional[int] = None

class TaskGenerateRequest(BaseModel):
    job_id: str
    sub_job_id: str
    content_id: str
    expert_task_id: int
    expert_config_code: str
    prompt: str
    model_code: str = "deepseek-v4-flash"
    model_cfg: ModelConfig = Field(default_factory=ModelConfig, alias="model_config")
    content: Optional[str] = None
    brand_id: Optional[int] = None
    activity_id: Optional[int] = None
    expert_service: Optional[str] = None
    expert_func: Optional[str] = None

class TaskGenerateResponse(BaseModel):
    success: bool
    message: str
    job_id: str
    sub_job_id: str
    content_id: str
    expert_task_id: int
    title: str = ""
    generated_content: str = ""
    execution_time: float = 0.0
    llm_time: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0
    model_used: str = ""
    provider: str = ""
    error: str = ""
