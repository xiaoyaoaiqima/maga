"""Profile registry for thin PPL-style content generation entrypoints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.schemas.content_batch_report import (
    ContentBatchStartRequest,
    ContentCommentBatchStartRequest,
    ContentPPLProfileResponse,
    ContentPPLRunStartRequest,
)

PPLContentType = Literal["article", "comment"]
COMMENT_PPL_MAX_COUNT = 100


@dataclass(frozen=True)
class ContentGenerationPPLProfile:
    profile_code: str
    label: str
    content_type: PPLContentType
    asset_key: str
    keyword_asset_key: str | None = None
    quality_guard_profile_key: str | None = None
    description: str = ""
    default_count: int = 10
    aliases: tuple[str, ...] = ()

    def response(self) -> ContentPPLProfileResponse:
        return ContentPPLProfileResponse(
            profile_code=self.profile_code,
            label=self.label,
            content_type=self.content_type,
            asset_key=self.asset_key,
            keyword_asset_key=self.keyword_asset_key,
            quality_guard_profile_key=self.quality_guard_profile_key,
            description=self.description,
            default_count=self.default_count,
            aliases=list(self.aliases),
        )


PPL_PROFILES: tuple[ContentGenerationPPLProfile, ...] = (
    ContentGenerationPPLProfile(
        profile_code="royal_friso_ugc_article",
        label="皇家美素佳儿UGC帖子",
        content_type="article",
        asset_key="royal_friso_ugc_post_rules_v1",
        keyword_asset_key="royal_friso_ugc_post_keywords_v1",
        description="皇家美素佳儿帖子生文：低浓度生活UGC，使用皇家专属规则和表达扩散语料。",
        aliases=("royal", "royal_friso"),
    ),
    ContentGenerationPPLProfile(
        profile_code="wangyue_0705_article",
        label="旺玥0705活动帖子",
        content_type="article",
        asset_key="wangyue_v353_protection_review_concrete_anchor_article_rules",
        keyword_asset_key="wangyue_article_generation_keywords_v352_real_middle_bridge",
        description="旺玥0705帖子生文：产品出现资格和正向反馈按旺玥文章规则走。",
        aliases=("wangyue", "wangyue_article"),
    ),
    ContentGenerationPPLProfile(
        profile_code="a2_sentiment_post_article",
        label="A2舆情改善帖子",
        content_type="article",
        asset_key="a2_sentiment_post_activity",
        quality_guard_profile_key="a2_sentiment_post_202606",
        description="A2舆情改善帖子生文：帖子规则走 article PPL，不和评论母池混用。",
        aliases=("a2_post", "a2_article"),
    ),
    ContentGenerationPPLProfile(
        profile_code="a2_sentiment_comment",
        label="A2舆情改善评论",
        content_type="comment",
        asset_key="a2_sentiment_comment_activity",
        keyword_asset_key="default_content_generation_keywords",
        quality_guard_profile_key="a2_sentiment_comment_202606",
        description="A2舆情改善评论生文：评论业务规则、评论格式和A2评论质量guard。",
        aliases=("a2_comment",),
    ),
)


class ContentGenerationPPLProfileService:
    """Resolve operator-facing profile codes into existing article/comment batch requests."""

    def __init__(self) -> None:
        self._profiles = {profile.profile_code: profile for profile in PPL_PROFILES}
        self._aliases = {
            alias: profile.profile_code
            for profile in PPL_PROFILES
            for alias in profile.aliases
        }

    def list_profiles(self) -> list[ContentPPLProfileResponse]:
        return [profile.response() for profile in PPL_PROFILES]

    def require_profile(self, profile_code: str) -> ContentGenerationPPLProfile:
        normalized = str(profile_code or "").strip()
        canonical = self._aliases.get(normalized, normalized)
        profile = self._profiles.get(canonical)
        if not profile:
            available = ", ".join(profile.profile_code for profile in PPL_PROFILES)
            raise ValueError(f"unknown PPL profile: {profile_code}; available profiles: {available}")
        return profile

    def build_article_request(
        self,
        profile: ContentGenerationPPLProfile,
        request: ContentPPLRunStartRequest,
    ) -> ContentBatchStartRequest:
        if profile.content_type != "article":
            raise ValueError(f"profile {profile.profile_code} is not an article profile")
        return ContentBatchStartRequest(
            asset_key=profile.asset_key,
            keyword_asset_key=request.keyword_asset_key or profile.keyword_asset_key,
            rule_id=request.rule_id,
            source_row_no=request.source_row_no,
            count=request.count or profile.default_count,
            executor_code=request.executor_code or DEFAULT_EXECUTOR_CODE,
            generation_model_config=request.generation_model_config,
            model_config_rotation=list(request.model_config_rotation),
            created_by=request.created_by,
        )

    def build_comment_request(
        self,
        profile: ContentGenerationPPLProfile,
        request: ContentPPLRunStartRequest,
    ) -> ContentCommentBatchStartRequest:
        if profile.content_type != "comment":
            raise ValueError(f"profile {profile.profile_code} is not a comment profile")
        count = request.count or profile.default_count
        if count > COMMENT_PPL_MAX_COUNT:
            raise ValueError(f"comment PPL profile count must be <= {COMMENT_PPL_MAX_COUNT}")
        return ContentCommentBatchStartRequest(
            asset_key=profile.asset_key,
            keyword_asset_key=request.keyword_asset_key or profile.keyword_asset_key,
            quality_guard_profile_key=(
                request.quality_guard_profile_key or profile.quality_guard_profile_key
            ),
            business_rule=request.business_rule,
            rule_id=request.rule_id,
            source_row_no=request.source_row_no,
            draft_corpus=request.draft_corpus,
            draft_rule_id=request.draft_rule_id,
            draft_source_row_no=request.draft_source_row_no,
            count=count,
            executor_code=request.executor_code or DEFAULT_EXECUTOR_CODE,
            created_by=request.created_by,
        )
