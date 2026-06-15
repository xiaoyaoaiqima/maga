"""Shared asset_type names for operator business-rule packages."""
from __future__ import annotations

ARTICLE_BUSINESS_RULE_ASSET_TYPE = "article_business_rule_set"
COMMENT_BUSINESS_RULE_ASSET_TYPE = "comment_business_rule_set"

LEGACY_COMMENT_BUSINESS_RULE_ASSET_TYPE = "comment_business_rule_set"
LEGACY_PRODUCT_EXPERIENCE_RULE_ASSET_TYPE = "product_experience_rule_set"

COMMENT_BUSINESS_RULE_ASSET_TYPES = (
    COMMENT_BUSINESS_RULE_ASSET_TYPE,
    LEGACY_COMMENT_BUSINESS_RULE_ASSET_TYPE,
)
ARTICLE_BUSINESS_RULE_ASSET_TYPES = (
    ARTICLE_BUSINESS_RULE_ASSET_TYPE,
    LEGACY_PRODUCT_EXPERIENCE_RULE_ASSET_TYPE,
)

BUSINESS_RULE_ASSET_TYPES = (
    *COMMENT_BUSINESS_RULE_ASSET_TYPES,
    *ARTICLE_BUSINESS_RULE_ASSET_TYPES,
)


def content_type_for_business_rule_asset_type(asset_type: str | None) -> str | None:
    if asset_type in COMMENT_BUSINESS_RULE_ASSET_TYPES:
        return "comment"
    if asset_type in ARTICLE_BUSINESS_RULE_ASSET_TYPES:
        return "article"
    return None
