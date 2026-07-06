from app.schemas.content_batch_report import ContentPPLRunStartRequest
from app.services.content_generation_ppl_profile_service import ContentGenerationPPLProfileService


def test_wangyue_alias_resolves_to_v2_profile_defaults():
    service = ContentGenerationPPLProfileService()

    profile = service.require_profile("wangyue")
    request = service.build_article_request(profile, ContentPPLRunStartRequest(profile_code="wangyue"))

    assert profile.profile_code == "wangyue_v2_0705_article"
    assert request.asset_key == "wangyue_v2_core_storyline_article_rules"
    assert request.keyword_asset_key == "wangyue_v2_minimal_generation_keywords"
    assert request.count == 20
    assert request.articles_per_prompt == 2


def test_legacy_wangyue_profile_stays_available():
    service = ContentGenerationPPLProfileService()

    profile = service.require_profile("wangyue_legacy")

    assert profile.profile_code == "wangyue_0705_article"
    assert profile.asset_key == "wangyue_v353_protection_review_concrete_anchor_article_rules"
