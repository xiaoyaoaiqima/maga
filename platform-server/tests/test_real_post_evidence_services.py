import httpx
import pytest

import app.services.xhs_real_post_acquisition_service as acquisition_module
from app.services.real_post_evidence_service import RealPostEvidenceService
from app.services.wangyue_evidence_asset_draft_service import WangyueEvidenceAssetDraftService
from app.services.xhs_real_post_acquisition_service import (
    XhsRealPostAcquisitionService,
    XhsRealPostRecord,
    XhsSearchRequest,
)


@pytest.mark.asyncio
async def test_xhs_real_post_acquisition_uses_maga_native_tikhub_adapter():
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path.endswith("/app_v2/search_notes"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "items": [
                            {
                                "note_card": {
                                    "id": "n1",
                                    "title": "儿童奶粉复购",
                                    "xsec_token": "tok1",
                                    "user": {"nickname": "hidden"},
                                }
                            }
                        ],
                        "next_page": None,
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "data": [
                        {
                            "note_list": [
                                {
                                    "id": "n1",
                                    "title": "儿童奶粉复购",
                                    "desc": "喝了一段时间，孩子愿意喝，家里又补了一罐。",
                                    "liked_count": 12,
                                    "comments_count": 3,
                                    "share_info": {"link": "https://xhslink.com/a?xsec_token=detailtok"},
                                }
                            ]
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://api.tikhub.io", transport=transport) as client:
        service = XhsRealPostAcquisitionService(api_key="test-key", client=client)
        records = await service.fetch_keyword(XhsSearchRequest(keyword="儿童奶粉复购", limit=1, delay_ms=0))

    assert len(records) == 1
    assert records[0].note_id == "n1"
    assert records[0].title == "儿童奶粉复购"
    assert records[0].content == "喝了一段时间，孩子愿意喝，家里又补了一罐。"
    assert records[0].detail_status == "ok"
    assert all("rs-crawler-analysis" not in url for url in requests)


def test_xhs_real_post_acquisition_ignores_legacy_key_env_names(monkeypatch):
    monkeypatch.setattr(acquisition_module.settings, "MAGA_TIKHUB_API_KEY", "")
    monkeypatch.delenv("MAGA_TIKHUB_API_KEY", raising=False)
    monkeypatch.setenv("XHS_TIKHUB_API_KEY", "legacy-xhs-key")
    monkeypatch.setenv("TIKHUB_API_KEY", "legacy-generic-key")

    service = XhsRealPostAcquisitionService()

    assert service.api_key == ""


def test_real_post_evidence_service_dedupes_and_classifies_mechanisms():
    records = [
        XhsRealPostRecord.from_mapping(
            {
                "source_keyword": "儿童奶粉复购",
                "note_id": "n1",
                "title": "又补了一罐",
                "content": "孩子喝了一段时间，口感能接受，家里就又补了一罐。放学回来喝完还去画画，先记录一下。",
                "note_url": "https://www.xiaohongshu.com/explore/n1",
                "detail_status": "ok",
            }
        ),
        XhsRealPostRecord.from_mapping(
            {
                "source_keyword": "儿童奶粉复购",
                "note_id": "n1",
                "title": "重复",
                "content": "重复",
                "detail_status": "ok",
            }
        ),
        XhsRealPostRecord.from_mapping(
            {
                "source_keyword": "3岁 儿童奶粉",
                "note_id": "n2",
                "title": "一岁宝宝转奶",
                "content": "一岁宝宝最近转奶，医生说可以试试。",
                "detail_status": "ok",
            }
        ),
    ]

    result = RealPostEvidenceService().analyze(records)

    assert result.stats["input_count"] == 3
    assert result.stats["deduped_count"] == 2
    assert result.stats["stable_candidate_count"] == 1
    assert result.stats["exclude_count"] == 1
    stable = next(row for row in result.rows if row.allow_asset == "stable_candidate")
    assert "product_entry:rebuy_restock" in stable.usable_layers
    assert "proof_surface:child_acceptance" in stable.usable_layers


def test_wangyue_asset_draft_uses_mechanisms_not_raw_posts():
    raw_sentence = "孩子喝了一段时间，口感能接受，家里就又补了一罐"
    result = RealPostEvidenceService().analyze(
        [
            {
                "source_keyword": "儿童奶粉复购",
                "note_id": "n1",
                "title": "又补了一罐",
                "content": f"{raw_sentence}。放学回来喝完还去画画，先记录一下。",
                "detail_status": "ok",
            }
        ]
    )

    draft = WangyueEvidenceAssetDraftService().build_keyword_asset_draft(result)
    draft_text = str(draft.content_json)

    assert draft.asset_type == "content_generation_keywords"
    assert draft.metadata_json["stable_source_rows"] == [1]
    assert "product_entry" not in draft_text
    assert raw_sentence not in draft_text
    assert "产品出现资格" in draft_text
