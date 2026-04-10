"""
Tencent content safety helpers (text/image) with graceful degradation.

SDK is optional. If credentials or SDK are missing, returns a mock "Pass".
"""
import base64
import json
import os
from typing import Any, Dict, Optional

from loguru import logger

TENCENT_CMS_SECRET_ID = os.getenv("TENCENT_CMS_SECRET_ID", "")
TENCENT_CMS_SECRET_KEY = os.getenv("TENCENT_CMS_SECRET_KEY", "")
DISABLE_TENCENT_VERIFY = os.getenv("DISABLE_TENCENT_VERIFY", "0") == "1"
REGION = os.getenv("TENCENT_CMS_REGION", "ap-shanghai")
TEXT_BIZTYPE = os.getenv("TENCENT_TEXT_BIZTYPE", "article_review")
IMAGE_BIZTYPE = os.getenv("TENCENT_IMAGE_BIZTYPE", "article_image_review")


try:  # Optional SDK imports
    from tencentcloud.common import credential  # type: ignore
    from tencentcloud.common.profile.client_profile import ClientProfile  # type: ignore
    from tencentcloud.common.profile.http_profile import HttpProfile  # type: ignore
    from tencentcloud.tms.v20201229 import tms_client, models as tms_models  # type: ignore
    from tencentcloud.ims.v20201229 import ims_client, models as ims_models  # type: ignore

    SDK_AVAILABLE = True
except Exception as sdk_err:  # pragma: no cover
    logger.warning(f"Tencent SDK not available, fallback to mock: {sdk_err}")
    credential = None  # type: ignore
    ClientProfile = None  # type: ignore
    HttpProfile = None  # type: ignore
    tms_client = None  # type: ignore
    tms_models = None  # type: ignore
    ims_client = None  # type: ignore
    ims_models = None  # type: ignore
    SDK_AVAILABLE = False


def _dummy_response(suggestion: str, source: str) -> Dict[str, Any]:
    return {
        "suggestion": suggestion,
        "request_id": f"{source}-mock",
        "raw": {"Suggestion": suggestion, "RequestId": f"{source}-mock"},
        "mock": True,
    }


def _need_mock() -> bool:
    return DISABLE_TENCENT_VERIFY or not SDK_AVAILABLE or not (TENCENT_CMS_SECRET_ID and TENCENT_CMS_SECRET_KEY)


def verify_text_content(text_content: str, biztype: Optional[str] = None) -> Dict[str, Any]:
    """
    Text moderation via Tencent TMS. Returns dict with suggestion/request_id/raw.
    Falls back to mock pass when SDK/creds disabled or missing.
    """
    if _need_mock():
        return _dummy_response("Pass", "tms")

    http_profile = HttpProfile()  # type: ignore
    http_profile.endpoint = "tms.tencentcloudapi.com"  # type: ignore
    client_profile = ClientProfile()  # type: ignore
    client_profile.http_profile = http_profile  # type: ignore
    cred = credential.Credential(TENCENT_CMS_SECRET_ID, TENCENT_CMS_SECRET_KEY)  # type: ignore
    client = tms_client.TmsClient(cred, REGION, client_profile)  # type: ignore

    payload = {
        "Content": base64.b64encode(text_content.encode("utf-8")).decode("utf-8"),
        "BizType": biztype or TEXT_BIZTYPE,
    }
    req = tms_models.TextModerationRequest()  # type: ignore
    req.from_json_string(json.dumps(payload))  # type: ignore

    try:
        resp = client.TextModeration(req)  # type: ignore
        return {
            "suggestion": getattr(resp, "Suggestion", "Pass"),
            "request_id": getattr(resp, "RequestId", ""),
            "raw": json.loads(resp.to_json_string()),
            "mock": False,
        }
    except Exception as err:  # pragma: no cover
        logger.error(f"Tencent text moderation failed: {err}")
        return {
            "suggestion": "Pass",
            "request_id": "",
            "raw": {"error": str(err)},
            "mock": True,
        }


def verify_image_content(image_url: str, biztype: Optional[str] = None) -> Dict[str, Any]:
    """
    Image moderation via Tencent IMS. Returns dict with suggestion/request_id/raw.
    Falls back to mock pass when SDK/creds disabled or missing.
    """
    if _need_mock():
        return _dummy_response("Pass", "ims")

    http_profile = HttpProfile()  # type: ignore
    http_profile.endpoint = "ims.tencentcloudapi.com"  # type: ignore
    client_profile = ClientProfile()  # type: ignore
    client_profile.http_profile = http_profile  # type: ignore
    cred = credential.Credential(TENCENT_CMS_SECRET_ID, TENCENT_CMS_SECRET_KEY)  # type: ignore
    client = ims_client.ImsClient(cred, REGION, client_profile)  # type: ignore

    payload = {
        "FileUrl": image_url,
        "BizType": biztype or IMAGE_BIZTYPE,
    }
    req = ims_models.ImageModerationRequest()  # type: ignore
    req.from_json_string(json.dumps(payload))  # type: ignore

    try:
        resp = client.ImageModeration(req)  # type: ignore
        return {
            "suggestion": getattr(resp, "Suggestion", "Pass"),
            "request_id": getattr(resp, "RequestId", ""),
            "raw": json.loads(resp.to_json_string()),
            "mock": False,
        }
    except Exception as err:  # pragma: no cover
        logger.error(f"Tencent image moderation failed: {err}")
        return {
            "suggestion": "Pass",
            "request_id": "",
            "raw": {"error": str(err)},
            "mock": True,
        }
