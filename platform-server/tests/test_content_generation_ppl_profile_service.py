from app.schemas.content_batch_report import ContentPPLRunStartRequest
from app.services.content_generation_ppl_profile_service import ContentGenerationPPLProfileService


def test_wangyue_alias_resolves_to_v3_profile_defaults():
    service = ContentGenerationPPLProfileService()

    profile = service.require_profile("wangyue")
    request = service.build_article_request(profile, ContentPPLRunStartRequest(profile_code="wangyue"))

    assert profile.profile_code == "wangyue_v3_0705_article"
    assert request.asset_key == "wangyue_v3_core_storyline_article_rules"
    assert request.keyword_asset_key is None
    assert request.prompt_mode == "layered_article"
    assert request.count == 20
    assert request.articles_per_prompt == 1


def test_wangyue_article_profile_carries_draft_rule_override():
    service = ContentGenerationPPLProfileService()
    profile = service.require_profile("wangyue")

    request = service.build_article_request(
        profile,
        ContentPPLRunStartRequest(
            profile_code="wangyue",
            rule_id="V3M-01",
            source_row_no=1,
            draft_corpus="替换后的 V3M-01 规则语料",
            draft_rule_id="V3M-01",
            draft_source_row_no=1,
        ),
    )

    assert request.draft_corpus == "替换后的 V3M-01 规则语料"
    assert request.draft_rule_id == "V3M-01"
    assert request.draft_source_row_no == 1
    assert request.count == 20
    assert request.articles_per_prompt == 1


def test_wangyue_article_profile_forces_one_article_when_request_asks_for_two():
    service = ContentGenerationPPLProfileService()
    profile = service.require_profile("wangyue")

    request = service.build_article_request(
        profile,
        ContentPPLRunStartRequest(
            profile_code="wangyue",
            articles_per_prompt=2,
        ),
    )

    assert profile.default_articles_per_prompt == 1
    assert profile.allow_articles_per_prompt_override is False
    assert request.articles_per_prompt == 1


def test_legacy_wangyue_profile_stays_available():
    service = ContentGenerationPPLProfileService()

    profile = service.require_profile("wangyue_legacy")

    assert profile.profile_code == "wangyue_0705_article"
    assert profile.asset_key == "wangyue_v353_protection_review_concrete_anchor_article_rules"
