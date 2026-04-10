from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MetricDefinitionBase(BaseModel):
    """指标定义基础模型"""
    metric_key: str
    metric_name: str
    description: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    display_format: Optional[str] = None
    display_order: int = 0


class MetricDefinitionCreate(MetricDefinitionBase):
    """创建指标定义"""
    pass


class MetricDefinitionUpdate(BaseModel):
    """更新指标定义"""
    metric_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    display_format: Optional[str] = None
    display_order: Optional[int] = None


class MetricDefinitionResponse(MetricDefinitionBase):
    """指标定义响应"""
    id: int
    create_time: datetime
    update_time: datetime

    model_config = ConfigDict(from_attributes=True)

