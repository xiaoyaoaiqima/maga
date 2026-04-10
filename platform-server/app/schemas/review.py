"""
Review schemas
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ContentItem(BaseModel):
    """内容项"""
    id: int
    content_id: str
    title: Optional[str] = None
    content: str
    review_status: str
    quality_level: Optional[str] = None
    quality_score: Optional[float] = None


class ContentListResponse(BaseModel):
    """内容列表响应"""
    total: int
    items: List[ContentItem]


