"""
文件池 Schemas（KnowledgeBaseFile - 单个上传的文件）
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema
from pydantic import computed_field


class KnowledgeBaseFileItem(BaseSchema):
    """文件池响应项"""
    id: int
    knowledge_base_id: int
    file_name: str
    file_path: str
    file_size: int
    file_type: str
    status: str
    parsed_count: int
    total_count: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

    # 前端兼容字段（computed_field 会自动序列化到 JSON）
    @computed_field
    def create_time(self) -> str:
        """创建时间（前端兼容）"""
        return self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else ""

    @computed_field
    def update_time(self) -> str:
        """更新时间（前端兼容）"""
        return self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else ""


class KnowledgeBaseFileCreate(BaseSchema):
    """创建文件池请求（内部使用）"""
    knowledge_base_id: int = Field(..., description="所属文档池ID")
    file_name: str = Field(..., max_length=255, description="文件名")
    file_path: str = Field(..., max_length=500, description="文件存储路径")
    file_size: int = Field(..., description="文件大小（字节）")
    file_type: str = Field(..., max_length=20, description="文件类型: excel/csv/pdf/word")
    created_by: Optional[str] = Field(default=None, max_length=64, description="创建人ID")


class KnowledgeBaseFileUpdate(BaseSchema):
    """更新文件池请求"""
    status: Optional[str] = Field(default=None, max_length=20, description="状态")
    parsed_count: Optional[int] = Field(default=None, description="成功解析的行数")
    total_count: Optional[int] = Field(default=None, description="文件总行数")
    error_message: Optional[str] = Field(default=None, max_length=1000, description="错误信息")


class KnowledgeBaseFileListQuery(BaseSchema):
    """文件池列表查询参数"""
    knowledge_base_id: Optional[int] = None
    status: Optional[str] = None


class KnowledgeBaseFileUploadRequest(BaseSchema):
    """文件上传请求"""
    knowledge_base_id: int = Field(..., description="所属文档池ID")


class KnowledgeBaseFileUploadResponse(BaseSchema):
    """文件上传响应"""
    file_id: int
    status: str
    message: str


class KnowledgeBaseFileBatchParseRequest(BaseSchema):
    """批量解析请求"""
    document_ids: list[int] = Field(..., description="文件ID列表（前端使用字段名）")
    file_ids: Optional[list[int]] = Field(default=None, description="文件ID列表（备用字段名）")
