"""MAGA-native Xiaohongshu real-post acquisition.

This service intentionally does not import or call crawler projects. It keeps
only the small TikHub search/detail adapter needed by MAGA evidence workflows.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

from app.core.config import settings


TIKHUB_XHS_API_PREFIX = "/api/v1/xiaohongshu"
SEARCH_ENDPOINT = "app_v2/search_notes"
DETAIL_ENDPOINTS = ("app_v2/get_image_note_detail", "app_v2/get_video_note_detail")
DEFAULT_TIKHUB_BASE_URL = "https://api.tikhub.io"


@dataclass(frozen=True)
class XhsSearchRequest:
    keyword: str
    limit: int = 20
    sort: str = "general"
    note_type: str = "不限"
    time_filter: str = "不限"
    delay_ms: int = 800
    search_page_size: int = 20
    detail_concurrency: int = 4


@dataclass(frozen=True)
class XhsRealPostRecord:
    source_keyword: str
    search_rank: int | str
    note_id: str
    title: str
    content: str
    note_url: str
    xsec_token: str
    note_type: str
    likes: int | str
    comments_count: int | str
    collected_count: int | str
    shared_count: int | str
    publish_time: str
    ip_location: str
    image_url: str
    detail_status: str
    detail_errors: list[str]
    raw_note_json: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "XhsRealPostRecord":
        return cls(
            source_keyword=str(value.get("source_keyword") or value.get("keyword") or ""),
            search_rank=value.get("search_rank") or "",
            note_id=str(value.get("note_id") or ""),
            title=str(value.get("title") or value.get("note_title") or ""),
            content=str(value.get("content") or value.get("desc") or value.get("note_desc") or ""),
            note_url=str(value.get("note_url") or value.get("url") or ""),
            xsec_token=str(value.get("xsec_token") or ""),
            note_type=str(value.get("note_type") or ""),
            likes=value.get("likes") or value.get("note_likes") or "",
            comments_count=value.get("comments_count") or value.get("comments") or value.get("note_comments_count") or "",
            collected_count=value.get("collected_count") or value.get("note_collected_count") or "",
            shared_count=value.get("shared_count") or value.get("note_shared_count") or "",
            publish_time=str(value.get("publish_time") or value.get("note_publish_time") or ""),
            ip_location=str(value.get("ip_location") or value.get("note_ip_location") or ""),
            image_url=str(value.get("image_url") or value.get("note_image_url") or ""),
            detail_status=str(value.get("detail_status") or ""),
            detail_errors=list(value.get("detail_errors") or []),
            raw_note_json=value.get("raw_note_json") if isinstance(value.get("raw_note_json"), dict) else {},
            created_at=str(value.get("created_at") or datetime.now(timezone.utc).isoformat()),
        )


class XhsRealPostAcquisitionService:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key or _configured_api_key()
        self.base_url = (base_url or _configured_base_url()).rstrip("/")
        self.timeout_seconds = timeout_seconds or int(settings.MAGA_TIKHUB_TIMEOUT_SECONDS)
        self._client = client

    def estimate_calls(self, keywords: list[str], *, per_keyword: int, page_size: int = 20) -> dict[str, int]:
        keyword_count = len([keyword for keyword in keywords if keyword.strip()])
        search_calls = keyword_count * max(1, -(-per_keyword // max(1, page_size)))
        detail_calls = keyword_count * max(0, per_keyword)
        return {
            "keywords": keyword_count,
            "per_keyword": per_keyword,
            "search_calls": search_calls,
            "detail_calls": detail_calls,
            "total_calls": search_calls + detail_calls,
        }

    async def fetch_keyword(self, request: XhsSearchRequest) -> list[XhsRealPostRecord]:
        if not request.keyword.strip():
            return []
        if not self.api_key and self._client is None:
            raise ValueError("TikHub api key missing. Set MAGA_TIKHUB_API_KEY.")
        if self._client is None:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": _authorization_header(self.api_key)},
                timeout=self.timeout_seconds,
            ) as client:
                scoped = XhsRealPostAcquisitionService(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout_seconds=self.timeout_seconds,
                    client=client,
                )
                return await scoped.fetch_keyword(request)

        search_notes = await self._fetch_search_notes(request)
        semaphore = asyncio.Semaphore(max(1, request.detail_concurrency))

        async def fetch_one(note: dict[str, Any]) -> XhsRealPostRecord:
            async with semaphore:
                return await self._fetch_note_detail(request.keyword, note, request.delay_ms)

        return await asyncio.gather(*(fetch_one(note) for note in search_notes))

    async def fetch_keywords(self, requests: list[XhsSearchRequest]) -> list[XhsRealPostRecord]:
        if self._client is None:
            if not self.api_key:
                raise ValueError("TikHub api key missing. Set MAGA_TIKHUB_API_KEY.")
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": _authorization_header(self.api_key)},
                timeout=self.timeout_seconds,
            ) as client:
                scoped = XhsRealPostAcquisitionService(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout_seconds=self.timeout_seconds,
                    client=client,
                )
                return await scoped.fetch_keywords(requests)
        records: list[XhsRealPostRecord] = []
        for request in requests:
            records.extend(await self.fetch_keyword(request))
        return records

    async def _fetch_search_notes(self, request: XhsSearchRequest) -> list[dict[str, Any]]:
        notes: list[dict[str, Any]] = []
        seen: set[str] = set()
        page = 1
        search_id = ""
        search_session_id = ""
        while len(notes) < request.limit:
            payload = await self._api_get(
                SEARCH_ENDPOINT,
                {
                    "keyword": request.keyword,
                    "page": page,
                    "sort_type": request.sort,
                    "note_type": request.note_type,
                    "time_filter": request.time_filter,
                    "search_id": search_id,
                    "search_session_id": search_session_id,
                },
            )
            items = extract_search_items(payload)
            if not items:
                break
            for item in items:
                if not isinstance(item, dict):
                    continue
                note = extract_search_note(item, len(notes))
                note["source_keyword"] = request.keyword
                if not note["note_id"] or note["note_id"] in seen:
                    continue
                seen.add(note["note_id"])
                notes.append(note)
                if len(notes) >= request.limit:
                    break
            search_id = get_path(payload, "data.search_id") or search_id
            search_session_id = get_path(payload, "data.search_session_id") or search_session_id
            next_page = get_path(payload, "data.next_page")
            if len(items) < request.search_page_size or not next_page or int(next_page) == page:
                break
            page = int(next_page)
            await sleep_ms(request.delay_ms)
        return notes

    async def _fetch_note_detail(self, keyword: str, note: dict[str, Any], delay_ms: int) -> XhsRealPostRecord:
        errors: list[str] = []
        for endpoint in DETAIL_ENDPOINTS:
            try:
                payload = await self._api_get(endpoint, {"note_id": note["note_id"]})
                detail = extract_detail_note(payload)
                if detail:
                    return record_from_note(keyword, merge_detail_into_note(note, detail))
                errors.append(f"{endpoint}: missing note detail")
            except Exception as exc:  # noqa: BLE001 - retain partial search result
                errors.append(f"{endpoint}: {str(exc).splitlines()[0]}")
            await sleep_ms(delay_ms)
        failed = {
            **note,
            "detail_status": "failed",
            "note_type": "",
            "note_desc": "",
            "note_likes": "",
            "note_comments_count": "",
            "note_collected_count": "",
            "note_shared_count": "",
            "note_publish_time": "",
            "note_ip_location": "",
            "note_image_url": "",
            "raw_note_json": note.get("raw_search_note") or {},
            "detail_errors": errors,
        }
        return record_from_note(keyword, failed)

    async def _api_get(self, path: str, query: dict[str, Any]) -> dict[str, Any]:
        client = self._client
        if client is None:
            headers = {"Authorization": _authorization_header(self.api_key)}
            async with httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=self.timeout_seconds) as owned:
                return await self._api_get_with_client(owned, path, query)
        return await self._api_get_with_client(client, path, query)

    async def _api_get_with_client(self, client: httpx.AsyncClient, path: str, query: dict[str, Any]) -> dict[str, Any]:
        url_path = f"{TIKHUB_XHS_API_PREFIX}/{path}"
        last_error: Exception | None = None
        for attempt in range(1, 5):
            try:
                response = await client.get(url_path, params=clean_query(query), follow_redirects=True)
                payload = response.json()
            except Exception as exc:  # noqa: BLE001 - retry transient provider failures
                last_error = exc
                if attempt == 4:
                    break
                await sleep_ms(1000 * attempt * attempt)
                continue
            if response.is_success and isinstance(payload, dict):
                return payload
            error = RuntimeError(f"HTTP {response.status_code} for {url_path}")
            retryable = response.status_code in (408, 429) or response.status_code >= 500
            if not retryable:
                raise error
            last_error = error
            await sleep_ms(1000 * attempt * attempt)
        raise last_error or RuntimeError(f"TikHub request failed: {path}")


def record_from_note(keyword: str, note: dict[str, Any]) -> XhsRealPostRecord:
    return XhsRealPostRecord(
        source_keyword=keyword,
        search_rank=note.get("search_rank", ""),
        note_id=str(note.get("note_id") or ""),
        title=str(note.get("note_title") or ""),
        content=str(note.get("note_desc") or ""),
        note_url=str(note.get("note_url") or ""),
        xsec_token=str(note.get("xsec_token") or ""),
        note_type=str(note.get("note_type") or ""),
        likes=note.get("note_likes") or "",
        comments_count=note.get("note_comments_count") or "",
        collected_count=note.get("note_collected_count") or "",
        shared_count=note.get("note_shared_count") or "",
        publish_time=str(note.get("note_publish_time") or ""),
        ip_location=str(note.get("note_ip_location") or ""),
        image_url=str(note.get("note_image_url") or ""),
        detail_status=str(note.get("detail_status") or ""),
        detail_errors=list(note.get("detail_errors") or []),
        raw_note_json=note.get("raw_note_json") if isinstance(note.get("raw_note_json"), dict) else {},
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def extract_search_items(payload: dict[str, Any]) -> list[Any]:
    return first_array_at_any_path(
        payload,
        [
            "data.items",
            "data.notes",
            "data.note_list",
            "data.feeds",
            "data.list",
            "data.data.items",
            "data.data.notes",
            "data.data.note_list",
            "items",
            "notes",
            "note_list",
        ],
    ) or deep_find_array(payload, {"items", "notes", "note_list", "feeds", "list"}) or []


def extract_detail_note(payload: dict[str, Any]) -> dict[str, Any] | None:
    note_list = first_array_at_any_path(
        payload,
        [
            "data.data.0.note_list",
            "data.data.data.0.note_list",
            "data.note_list",
            "data.data.note_list",
            "note_list",
        ],
    ) or deep_find_array(payload, {"note_list"})
    if note_list and isinstance(note_list[0], dict):
        return note_list[0]
    direct = get_path(payload, "data.data.note") or get_path(payload, "data.note") or get_path(payload, "note")
    return direct if isinstance(direct, dict) else None


def extract_search_note(raw: dict[str, Any], index: int) -> dict[str, Any]:
    source = raw.get("note_card") or raw.get("note") or raw.get("model") or raw
    user = (
        source.get("user")
        or source.get("user_info")
        or source.get("userInfo")
        or raw.get("user")
        or raw.get("user_info")
        or raw.get("userInfo")
        or {}
    )
    nested_note = source.get("note") or {}
    note_id = pick(source, ["note_id", "id", "noteId"]) or pick(raw, ["note_id", "id", "noteId"]) or pick(
        nested_note, ["id", "note_id"]
    )
    xsec_token = (
        pick(source, ["xsec_token", "xsecToken"])
        or pick(raw, ["xsec_token", "xsecToken"])
        or pick(nested_note, ["xsec_token", "xsecToken"])
    )
    return {
        "search_rank": index + 1,
        "note_id": str(note_id or ""),
        "xsec_token": str(xsec_token or ""),
        "note_url": build_note_url(note_id, xsec_token),
        "note_title": str(pick(source, ["title", "display_title", "desc"]) or ""),
        "note_author_id": str(pick(user, ["user_id", "userId", "id", "userid"]) or ""),
        "note_author_name": str(pick(user, ["nickname", "nick_name", "nickName", "name"]) or ""),
        "raw_search_note": raw,
    }


def merge_detail_into_note(note: dict[str, Any], detail_raw: dict[str, Any]) -> dict[str, Any]:
    user = detail_raw.get("user") or detail_raw.get("user_info") or detail_raw.get("userInfo") or {}
    share_link = (detail_raw.get("share_info") or {}).get("link") or ""
    share_xsec_token = extract_xsec_token(share_link)
    images = detail_raw.get("images_list") or detail_raw.get("image_list") or detail_raw.get("images") or []
    return {
        **note,
        "detail_status": "ok",
        "note_id": pick(detail_raw, ["id", "note_id", "noteId"]) or note.get("note_id", ""),
        "xsec_token": share_xsec_token or note.get("xsec_token", ""),
        "note_url": share_link or note.get("note_url", ""),
        "note_title": pick(detail_raw, ["title", "display_title"]) or note.get("note_title", ""),
        "note_author_id": pick(user, ["user_id", "userId", "id", "userid"]) or note.get("note_author_id", ""),
        "note_author_name": pick(user, ["nickname", "nick_name", "nickName", "name"]) or note.get("note_author_name", ""),
        "note_type": pick(detail_raw, ["type", "note_type", "noteType", "model_type"]) or "",
        "note_desc": pick(detail_raw, ["desc", "description"]) or "",
        "note_likes": pick(detail_raw, ["liked_count", "likedCount", "like_count", "likeCount"]) or "",
        "note_comments_count": pick(detail_raw, ["comments_count", "comment_count", "commentsCount", "commentCount"]) or "",
        "note_collected_count": pick(detail_raw, ["collected_count", "collectedCount", "collect_count", "collectCount"]) or "",
        "note_shared_count": pick(detail_raw, ["shared_count", "sharedCount", "share_count", "shareCount"]) or "",
        "note_publish_time": normalize_time(
            pick(detail_raw, ["time", "timestamp", "create_time", "createTime", "created_at", "createdAt"])
        ),
        "note_ip_location": pick(detail_raw, ["ip_location", "ipLocation"]) or "",
        "note_image_url": first_image_url(images) or (detail_raw.get("share_info") or {}).get("image") or "",
        "raw_note_json": detail_raw,
    }


def clean_query(query: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in query.items() if value not in (None, "")}


async def sleep_ms(ms: int) -> None:
    if ms > 0:
        await asyncio.sleep(ms / 1000)


def first_array_at_any_path(root: Any, candidate_paths: list[str]) -> list[Any] | None:
    for path in candidate_paths:
        value = get_path(root, path)
        if isinstance(value, list):
            return value
    return None


def get_path(root: Any, path: str) -> Any:
    value = root
    for key in path.split("."):
        if value is None:
            return None
        if isinstance(value, list):
            if not key.isdigit():
                return None
            index = int(key)
            value = value[index] if index < len(value) else None
        elif isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


def deep_find_array(root: Any, key_names: set[str]) -> list[Any] | None:
    queue = [root]
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        if not isinstance(current, (dict, list)) or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, list):
            queue.extend(current)
            continue
        for key, value in current.items():
            if key in key_names and isinstance(value, list):
                return value
            if isinstance(value, (dict, list)):
                queue.append(value)
    return None


def first_image_url(images: list[Any]) -> str:
    for image in images:
        if not isinstance(image, dict):
            continue
        url = (
            image.get("url")
            or image.get("url_default")
            or image.get("origin_url")
            or get_path(image, "info_list.0.url")
            or image.get("live_photo_file_id")
        )
        if url:
            return str(url)
    return ""


def extract_xsec_token(url: str) -> str:
    if not url:
        return ""
    try:
        return parse_qs(urlparse(url).query).get("xsec_token", [""])[0]
    except Exception:
        return ""


def build_note_url(note_id: Any, xsec_token: Any) -> str:
    if not note_id:
        return ""
    parsed = urlparse(f"https://www.xiaohongshu.com/explore/{note_id}")
    query = {"xsec_source": "pc_search"}
    if xsec_token:
        query["xsec_token"] = str(xsec_token)
    return urlunparse(parsed._replace(query=urlencode(query)))


def pick(obj: dict[str, Any] | None, keys: list[str]) -> Any:
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if obj.get(key) is not None:
            return obj[key]
    return None


def normalize_time(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    seconds = numeric / 1000 if numeric > 10_000_000_000 else numeric
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


def _authorization_header(api_key: str) -> str:
    token = api_key.strip()
    return token if token.lower().startswith("bearer ") else f"Bearer {token}"


def _configured_api_key() -> str:
    return settings.MAGA_TIKHUB_API_KEY or os.getenv("MAGA_TIKHUB_API_KEY", "")


def _configured_base_url() -> str:
    return settings.MAGA_TIKHUB_BASE_URL or os.getenv("MAGA_TIKHUB_BASE_URL", "") or DEFAULT_TIKHUB_BASE_URL
