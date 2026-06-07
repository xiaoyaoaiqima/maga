"""
模型配置表 - 用于存储 LLM 模型的配置信息
"""
from sqlalchemy import Column, String, Text, Boolean
from app.models.base_model import BaseModel


class ModelConfig(BaseModel):
    """模型配置表（模型元信息表）"""
    __tablename__ = "app_aigc_model_config"

    provider = Column(String(64), nullable=False, comment="模型提供商：openai/deepseek/doubao/claude")
    model = Column(String(128), nullable=False, comment="模型标识：deepseek-v4-flash/doubao-pro-32k")
    endpoint = Column(String(255), nullable=True, comment="模型端点 URL（可选，为空则使用默认）")
    api_key = Column(String(128), nullable=True, comment="API Key")
    
    # 元数据
    description = Column(Text, nullable=True, comment="配置说明")
    enabled = Column(Boolean, default=True, comment="是否启用")
