"""Business-owned forbidden terms managed from operator feedback."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maga_assets import AssetRegistry

BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE = "business_forbidden_terms"
DEFAULT_BUSINESS_FORBIDDEN_TERMS_ASSET_KEY = "default_business_forbidden_terms"
BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION = "2"
FORBIDDEN_TERM_ENFORCEMENTS = {"replace", "model_rewrite", "hard_ban"}
FORBIDDEN_TERM_MATCH_MODES = {
    "literal",
    "activity_prize_context",
    "detection_page_context",
    "registration_required_context",
    "risk_polarity_context",
}
A2_SENTIMENT_COMMENT_ASSET_KEY = "a2_sentiment_comment_activity"
A2_REIYU_UGC_POST_ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
A2_REIYU_QWEN_PLUS_MODEL_CONFIG = {
    "provider_code": "aliyun",
    "model_code": "qwen-plus",
    "ge_model": "qwen-plus",
    "ae_model": "qwen-plus",
}
A2_SENTIMENT_COMMENT_SEED_TERMS = (
    {
        "term": "小程序",
        "reason": "小红书不能出现微信生态的词",
        "enabled": True,
        "replacement": "",
        "source": "operator_rule",
        "created_by": "ops",
    },
    {
        "term": "0.03",
        "reason": "业务新要求：暂不露出蜡样/蜡毒检测的明确数值",
        "enabled": True,
        "replacement": "",
        "source": "operator_rule",
        "created_by": "ops",
    },
    {
        "term": "60+",
        "reason": "业务新要求：暂不露出检测报告/检测项目的明确数量",
        "enabled": True,
        "replacement": "",
        "source": "operator_rule",
        "created_by": "ops",
    },
    {
        "term": "60多项",
        "reason": "业务新要求：暂不露出检测报告/检测项目的明确数量",
        "enabled": True,
        "replacement": "",
        "source": "operator_rule",
        "created_by": "ops",
    },
)
A2_SENTIMENT_COMMENT_SEED_TERM = A2_SENTIMENT_COMMENT_SEED_TERMS[0]


def _a2_reiyu_entry(
    term: str,
    *,
    enforcement: str,
    reason: str,
    replacement: str = "",
    match_mode: str = "literal",
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "term": term,
        "reason": reason,
        "enabled": True,
        "replacement": replacement,
        "enforcement": enforcement,
        "match_mode": match_mode,
        "rewrite_model_config": {},
        "source": "operator_rule_20260721",
        "created_by": "ops",
    }
    if enforcement == "model_rewrite":
        entry["rewrite_model_config"] = dict(A2_REIYU_QWEN_PLUS_MODEL_CONFIG)
    return entry


A2_REIYU_REPLACE_TERMS = {
    "A2至初": "a2至初",
    "a2至现在": "a2至初现在",
    "A2蛋白质": "A2蛋白",
    "a2蛋白质": "A2蛋白",
    "肚子": "肚肚",
    "脾胃": "肚肚状态",
    "大脑": "🧠",
    "眼睛": "👀",
    "敏感": "敏敏",
    "粑粑": "💩",
    "预防针": "💉",
    "微信": "🌍",
    "QQ": "🌍",
    "小红书": "🍠",
    "朋友圈": "pyq",
    "钱": "💰",
    "免费": "🆓",
    "母乳": "母R",
    "批批检透明": "每批都有检测，信息更透明",
    "叫会员礼遇活动": "发现a2上了会员礼遇活动",
    "emoji": "",
    "♀️": "",
    "♂": "",
    "#": "",
    "🎵": "",
}
A2_REIYU_MODEL_REWRITE_TERMS = (
    "顺手",
    "顺口",
    "顺便",
    "麻烦",
    "薅",
    "白嫖",
    "羊毛",
    "真的会谢",
    "彩虹屁",
    "挺逗",
    "Emm",
    "笑哭R",
    "顺便看到",
    "带一嘴",
    "失败",
    "避雷",
)
A2_REIYU_REGISTRATION_REWRITE_TERMS = ("报名",)
A2_REIYU_RISK_POLARITY_REWRITE_TERMS = ("踩雷", "翻车")
A2_REIYU_DETECTION_NAVIGATION_REWRITE_TERMS = (
    "往下翻",
    "翻着翻着",
    "往下滑",
    "仔细翻",
    "翻了翻活动页面",
)
A2_REIYU_HARD_BAN_TERMS = (
    "质量问题",
    "风险澄清",
    "问题批次",
    "没货",
    "缺货",
    "召回",
    "买不到",
    "断货",
    "断供",
    "不好买",
    "又没了",
    "断粮",
    "抢不到",
    "真伪",
    "假货",
    "代购不确定",
    "被迫转奶",
    "维权",
    "投诉",
    "塌房",
    "爆雷",
    "正文",
    "标题",
    "卖点",
    "痛点",
    "问配方",
    "填表",
    "自己账号",
    "无限",
    "全检",
    "A2蛋白质检测",
    "生产批号",
    "新码",
    "空罐",
    "攒着罐子",
    "攒罐子",
    "囤了好几罐",
    "扫罐底码就能抽奖",
    "一罐小车车",
    "婴儿车抽奖",
)
A2_REIYU_CONTEXTUAL_PRIZE_HARD_BAN_TERMS = (
    "赢一辆",
    "积木",
    "拉链包",
    "小玩具",
    "小书包",
    "辅食碗",
    "贝亲",
)
A2_REIYU_UGC_POST_SEED_TERMS = (
    *(
        _a2_reiyu_entry(
            term,
            enforcement="replace",
            replacement=replacement,
            reason="运营确认可做确定性规范化",
        )
        for term, replacement in A2_REIYU_REPLACE_TERMS.items()
    ),
    *(
        _a2_reiyu_entry(
            term,
            enforcement="model_rewrite",
            reason="运营确认应由 qwen-plus 结合上下文自然改写，不做字符串硬删",
        )
        for term in A2_REIYU_MODEL_REWRITE_TERMS
    ),
    *(
        _a2_reiyu_entry(
            term,
            enforcement="model_rewrite",
            match_mode="registration_required_context",
            reason="只有正文写成需要报名、先报名或报名参加时改写；不用报名、无需报名等正确规则说明放行",
        )
        for term in A2_REIYU_REGISTRATION_REWRITE_TERMS
    ),
    *(
        _a2_reiyu_entry(
            term,
            enforcement="model_rewrite",
            match_mode="risk_polarity_context",
            reason="只在句子明确表达风险发生时改写；不踩雷、没翻车等正向否定表达放行",
        )
        for term in A2_REIYU_RISK_POLARITY_REWRITE_TERMS
    ),
    *(
        _a2_reiyu_entry(
            term,
            enforcement="model_rewrite",
            match_mode="detection_page_context",
            reason="只在用翻页动作承接每批检测信息时，由 qwen-plus 改写来源关系",
        )
        for term in A2_REIYU_DETECTION_NAVIGATION_REWRITE_TERMS
    ),
    *(
        _a2_reiyu_entry(
            term,
            enforcement="hard_ban",
            reason="运营确认属于供应风险、指令泄露、检测乱编、旧罐暗示或明确机制错误",
        )
        for term in A2_REIYU_HARD_BAN_TERMS
    ),
    *(
        _a2_reiyu_entry(
            term,
            enforcement="hard_ban",
            match_mode="activity_prize_context",
            reason="仅在活动奖品或兑换机制语境中属于新增奖品或机制错误",
        )
        for term in A2_REIYU_CONTEXTUAL_PRIZE_HARD_BAN_TERMS
    ),
)


@dataclass(frozen=True)
class BusinessForbiddenTermUpdateResult:
    asset: AssetRegistry | None
    asset_key: str
    added_terms: list[str]
    updated_terms: list[str]
    existing_terms: list[str]
    all_terms: list[str]


class BusinessForbiddenTermService:
    """Persist and read deterministic business forbidden-word lists."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_terms(self, *, asset_key: str | None = None, include_default: bool = True) -> list[str]:
        keys = _asset_keys_for_lookup(asset_key, include_default=include_default)
        terms: list[str] = []
        for key in keys:
            try:
                asset = await self._latest_asset(key)
            except SQLAlchemyError:
                continue
            if asset is None:
                continue
            for term in _terms_from_content(asset.content_json or {}):
                if term not in terms:
                    terms.append(term)
        return terms

    async def list_entries(
        self,
        *,
        asset_key: str | None = None,
        include_default: bool = True,
    ) -> list[dict[str, Any]]:
        keys = _asset_keys_for_lookup(asset_key, include_default=include_default)
        entries: list[dict[str, Any]] = []
        seen_terms: set[str] = set()
        for key in keys:
            try:
                asset = await self._latest_asset(key)
            except SQLAlchemyError:
                continue
            if asset is None:
                continue
            for entry in _term_entries_from_content(asset.content_json or {}):
                normalized = _normalized_entry(entry, fallback_asset_key=key)
                term = _term_from_entry(normalized)
                if not term or term in seen_terms:
                    continue
                seen_terms.add(term)
                entries.append(normalized)
        return entries

    async def list_replacements(self, *, asset_key: str | None = None, include_default: bool = True) -> dict[str, str]:
        keys = _asset_keys_for_lookup(asset_key, include_default=include_default)
        replacements: dict[str, str] = {}
        for key in keys:
            try:
                asset = await self._latest_asset(key)
            except SQLAlchemyError:
                continue
            if asset is None:
                continue
            for entry in _term_entries_from_content(asset.content_json or {}):
                if entry.get("enabled") is False:
                    continue
                term = _term_from_entry(entry)
                replacement = _replacement_from_entry(entry)
                if term and replacement and term not in replacements:
                    replacements[term] = replacement
        return replacements

    async def add_terms(
        self,
        *,
        asset_key: str | None,
        terms: list[str],
        created_by: str | None,
        source_context: dict[str, Any] | None = None,
    ) -> BusinessForbiddenTermUpdateResult:
        entries = [
            {
                "term": term,
                "source": "content_batch_feedback",
                "reason": "运营反馈不希望出现",
            }
            for term in normalize_business_forbidden_terms(terms)
        ]
        return await self.upsert_entries(
            asset_key=asset_key,
            entries=entries,
            created_by=created_by or "content_batch_workbench",
            source_context=source_context,
        )

    async def upsert_entries(
        self,
        *,
        asset_key: str | None,
        entries: list[dict[str, Any]],
        created_by: str | None,
        source_context: dict[str, Any] | None = None,
    ) -> BusinessForbiddenTermUpdateResult:
        normalized_asset_key = _normalize_asset_key(asset_key)
        normalized_new_entries = normalize_business_forbidden_term_entries(entries)
        if not normalized_new_entries:
            raise ValueError("business forbidden terms cannot be empty")

        current = await self._latest_asset(normalized_asset_key)
        entries = _term_entries_from_content(current.content_json if current else {})
        existing_terms = _terms_from_entries(entries)
        next_entries = [_normalized_entry(entry, fallback_asset_key=normalized_asset_key) for entry in entries]
        added_terms: list[str] = []
        updated_terms: list[str] = []
        now = _now_iso()

        for new_entry in normalized_new_entries:
            term = _term_from_entry(new_entry)
            match_index = next(
                (idx for idx, entry in enumerate(next_entries) if _term_from_entry(entry) == term),
                None,
            )
            entry_patch = {
                "term": term,
                "enabled": bool(new_entry.get("enabled", True)),
                "source": str(new_entry.get("source") or "operator_rule").strip() or "operator_rule",
                "created_by": created_by or str(new_entry.get("created_by") or "content_batch_workbench"),
                "reason": str(new_entry.get("reason") or new_entry.get("note") or "运营反馈不希望出现").strip(),
                "replacement": str(new_entry.get("replacement") or "").strip(),
                "enforcement": _enforcement_from_entry(new_entry),
                "match_mode": _match_mode_from_entry(new_entry),
                "rewrite_model_config": _rewrite_model_config_from_entry(new_entry),
                **({"source_context": source_context} if source_context else {}),
            }
            if match_index is None:
                next_entries.append(
                    {
                        **entry_patch,
                        "created_at": str(new_entry.get("created_at") or now),
                    }
                )
                added_terms.append(term)
            else:
                existing = dict(next_entries[match_index])
                update_patch = {
                    key: value
                    for key, value in entry_patch.items()
                    if key != "created_by" and value not in (None, "")
                }
                next_entries[match_index] = {
                    **existing,
                    **update_patch,
                    "enabled": entry_patch["enabled"],
                    "created_at": existing.get("created_at") or now,
                    "updated_at": now,
                    "updated_by": created_by or "content_batch_workbench",
                }
                updated_terms.append(term)

        if not added_terms and not updated_terms:
            return BusinessForbiddenTermUpdateResult(
                asset=current,
                asset_key=normalized_asset_key,
                added_terms=[],
                updated_terms=[],
                existing_terms=existing_terms,
                all_terms=existing_terms,
            )

        await self.db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                AssetRegistry.asset_key == normalized_asset_key,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        content_json = {
            "schema_version": BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION,
            "asset_type": BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
            "terms": next_entries,
        }
        asset = AssetRegistry(
            asset_type=BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
            asset_key=normalized_asset_key,
            display_name=f"{normalized_asset_key} 业务违禁词",
            version_no=await self._next_asset_version(normalized_asset_key),
            status="active",
            asset_stage="production",
            source_name="content_batch_feedback",
            content_json=content_json,
            metadata_json={
                "schema_version": BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION,
                "term_count": len(_terms_from_entries(next_entries)),
                "added_term_count": len(added_terms),
                "updated_term_count": len(updated_terms),
            },
            created_by=created_by or "content_batch_workbench",
        )
        self.db.add(asset)
        await self.db.flush()
        return BusinessForbiddenTermUpdateResult(
            asset=asset,
            asset_key=normalized_asset_key,
            added_terms=added_terms,
            updated_terms=updated_terms,
            existing_terms=existing_terms,
            all_terms=_terms_from_entries(next_entries),
        )

    async def set_enabled(
        self,
        *,
        asset_key: str | None,
        term: str,
        enabled: bool,
        created_by: str | None,
    ) -> BusinessForbiddenTermUpdateResult:
        normalized_asset_key = _normalize_asset_key(asset_key)
        normalized_terms = normalize_business_forbidden_terms([term])
        if not normalized_terms:
            raise ValueError("business forbidden term cannot be empty")
        current = await self._latest_asset(normalized_asset_key)
        if current is None:
            raise ValueError("business forbidden terms asset not found")
        entries = [
            _normalized_entry(entry, fallback_asset_key=normalized_asset_key)
            for entry in _term_entries_from_content(current.content_json)
        ]
        existing_terms = _terms_from_entries(entries)
        target = normalized_terms[0]
        updated_terms: list[str] = []
        now = _now_iso()
        for entry in entries:
            if _term_from_entry(entry) == target:
                entry["enabled"] = enabled
                entry["updated_at"] = now
                entry["updated_by"] = created_by or "content_batch_workbench"
                updated_terms.append(target)
                break
        if not updated_terms:
            raise ValueError("business forbidden term not found")
        asset = await self._replace_asset(
            normalized_asset_key,
            entries,
            created_by=created_by or "content_batch_workbench",
            source_name="business_forbidden_terms_status",
            added_term_count=0,
            updated_term_count=1,
        )
        return BusinessForbiddenTermUpdateResult(
            asset=asset,
            asset_key=normalized_asset_key,
            added_terms=[],
            updated_terms=updated_terms,
            existing_terms=existing_terms,
            all_terms=_terms_from_entries(entries),
        )

    async def _replace_asset(
        self,
        asset_key: str,
        entries: list[dict[str, Any]],
        *,
        created_by: str,
        source_name: str,
        added_term_count: int,
        updated_term_count: int,
    ) -> AssetRegistry:
        await self.db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        asset = AssetRegistry(
            asset_type=BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
            asset_key=asset_key,
            display_name=f"{asset_key} 业务违禁词",
            version_no=await self._next_asset_version(asset_key),
            status="active",
            asset_stage="production",
            source_name=source_name,
            content_json={
                "schema_version": BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION,
                "asset_type": BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                "terms": entries,
            },
            metadata_json={
                "schema_version": BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION,
                "term_count": len(_terms_from_entries(entries)),
                "added_term_count": added_term_count,
                "updated_term_count": updated_term_count,
            },
            created_by=created_by,
        )
        self.db.add(asset)
        await self.db.flush()
        return asset

    async def _latest_asset(self, asset_key: str) -> AssetRegistry | None:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
                AssetRegistry.asset_stage == "production",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _next_asset_version(self, asset_key: str) -> int:
        result = await self.db.execute(
            select(AssetRegistry.version_no)
            .where(
                AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
            )
            .order_by(AssetRegistry.version_no.desc())
            .limit(1)
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1


def normalize_business_forbidden_terms(terms: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for raw in terms or []:
        value = str(raw or "").strip()
        if not value:
            continue
        value = " ".join(value.split())
        if len(value) > 100:
            raise ValueError("business forbidden term is too long")
        if value not in normalized:
            normalized.append(value)
    return normalized


def normalize_business_forbidden_term_entries(entries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_terms: set[str] = set()
    for raw in entries or []:
        if not isinstance(raw, dict):
            continue
        terms = normalize_business_forbidden_terms([_term_from_entry(raw)])
        if not terms:
            continue
        term = terms[0]
        if term in seen_terms:
            continue
        reason = str(raw.get("reason") or raw.get("note") or "").strip()
        if len(reason) > 1000:
            raise ValueError("business forbidden term reason is too long")
        replacement = str(raw.get("replacement") or raw.get("rewrite_to") or raw.get("replace_with") or "").strip()
        if len(replacement) > 100:
            raise ValueError("business forbidden term replacement is too long")
        enforcement = _enforcement_from_entry(raw)
        match_mode = _match_mode_from_entry(raw)
        normalized.append(
            {
                **raw,
                "term": term,
                "reason": reason,
                "replacement": replacement,
                "enforcement": enforcement,
                "match_mode": match_mode,
                "rewrite_model_config": _rewrite_model_config_from_entry(raw),
                "enabled": raw.get("enabled") is not False,
            }
        )
        seen_terms.add(term)
    return normalized


def _normalize_asset_key(asset_key: str | None) -> str:
    return (asset_key or DEFAULT_BUSINESS_FORBIDDEN_TERMS_ASSET_KEY).strip() or DEFAULT_BUSINESS_FORBIDDEN_TERMS_ASSET_KEY


def _asset_keys_for_lookup(asset_key: str | None, *, include_default: bool) -> list[str]:
    keys: list[str] = []
    normalized = (asset_key or "").strip()
    if normalized:
        keys.append(normalized)
    if include_default and DEFAULT_BUSINESS_FORBIDDEN_TERMS_ASSET_KEY not in keys:
        keys.append(DEFAULT_BUSINESS_FORBIDDEN_TERMS_ASSET_KEY)
    return keys


def _terms_from_content(content_json: dict[str, Any]) -> list[str]:
    return _terms_from_entries(_term_entries_from_content(content_json))


def _term_entries_from_content(content_json: dict[str, Any] | None) -> list[dict[str, Any]]:
    raw_terms = (content_json or {}).get("terms")
    if not isinstance(raw_terms, list):
        raw_terms = (content_json or {}).get("items")
    entries: list[dict[str, Any]] = []
    for item in raw_terms or []:
        if isinstance(item, str):
            entries.append({"term": item, "enabled": True})
        elif isinstance(item, dict):
            entries.append(item)
    return entries


def _normalized_entry(entry: dict[str, Any], *, fallback_asset_key: str | None = None) -> dict[str, Any]:
    term = _term_from_entry(entry)
    return {
        "term": term,
        "reason": str(entry.get("reason") or entry.get("note") or "").strip(),
        "enabled": entry.get("enabled") is not False,
        "created_at": str(entry.get("created_at") or ""),
        "created_by": str(entry.get("created_by") or "").strip(),
        "updated_at": str(entry.get("updated_at") or ""),
        "updated_by": str(entry.get("updated_by") or "").strip(),
        "replacement": _replacement_from_entry(entry),
        "enforcement": _enforcement_from_entry(entry),
        "match_mode": _match_mode_from_entry(entry),
        "rewrite_model_config": _rewrite_model_config_from_entry(entry),
        "source": str(entry.get("source") or "").strip(),
        "asset_key": str(entry.get("asset_key") or fallback_asset_key or "").strip(),
        **({"source_context": entry.get("source_context")} if entry.get("source_context") is not None else {}),
    }


def _terms_from_entries(entries: list[dict[str, Any]]) -> list[str]:
    terms: list[str] = []
    for entry in entries:
        if entry.get("enabled") is False:
            continue
        value = _term_from_entry(entry)
        if value and value not in terms:
            terms.append(value)
    return terms


def _term_from_entry(entry: dict[str, Any]) -> str:
    return str(entry.get("term") or entry.get("word") or entry.get("name") or "").strip()


def _replacement_from_entry(entry: dict[str, Any]) -> str:
    return str(
        entry.get("replacement")
        or entry.get("rewrite_to")
        or entry.get("replace_with")
        or entry.get("suggested_replacement")
        or ""
    ).strip()


def _enforcement_from_entry(entry: dict[str, Any]) -> str:
    value = str(entry.get("enforcement") or "").strip()
    if value and value not in FORBIDDEN_TERM_ENFORCEMENTS:
        raise ValueError(f"unsupported business forbidden term enforcement: {value}")
    return value


def _match_mode_from_entry(entry: dict[str, Any]) -> str:
    value = str(entry.get("match_mode") or "literal").strip() or "literal"
    if value not in FORBIDDEN_TERM_MATCH_MODES:
        raise ValueError(f"unsupported business forbidden term match mode: {value}")
    return value


def _rewrite_model_config_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    value = entry.get("rewrite_model_config")
    return dict(value) if isinstance(value, dict) else {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
