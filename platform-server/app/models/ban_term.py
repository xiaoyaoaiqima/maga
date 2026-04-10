"""
BAN 词表（违禁词/白名单）模型

说明：
- 存放 KeywordFilterService 用到的 whitelist / blacklist
- 支持在线更新：通过 ban_term_meta.active_version 触发服务端刷新缓存
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, Index, Integer, String, UniqueConstraint

from app.models.base_model import BaseModel


class BanTerm(BaseModel):
    """BAN 词条表"""

    __tablename__ = "ban_term"

    tenant_code = Column(
        String(64),
        nullable=False,
        default="default",
        comment="租户编码（如 friso / default）",
    )
    term = Column(String(255), nullable=False, comment="词条（原样保存）")
    list_type = Column(
        String(16),
        nullable=False,
        comment="名单类型：WHITELIST（安全词）/ BLACKLIST（违禁词）",
    )
    category = Column(
        String(64),
        nullable=False,
        default="global",
        comment="分组（如 medical / wangyue / global），用于管理与审计",
    )
    enabled = Column(Boolean, nullable=False, default=True, comment="是否启用")

    __table_args__ = (
        Index("idx_ban_term_tenant_list_enabled", "tenant_code", "list_type", "enabled"),
        # 允许软删除后重新插入：将 is_deleted 纳入唯一约束
        UniqueConstraint(
            "tenant_code",
            "list_type",
            "category",
            "term",
            "is_deleted",
            name="uk_ban_term_tenant_list_category_term",
        ),
    )


class BanTermMeta(BaseModel):
    """BAN 词表版本控制（用于热更新）"""

    __tablename__ = "ban_term_meta"

    # 单行表：约定 id=1
    id = Column(BigInteger, primary_key=True, autoincrement=False, comment="固定为 1")
    active_version = Column(Integer, nullable=False, default=1, comment="当前生效版本号")
