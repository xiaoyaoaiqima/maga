"""Build reviewable Wangyue keyword-asset drafts from real-post evidence."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.schemas.assets import AssetCandidateCreate
from app.services.asset_service import AssetService
from app.services.real_post_evidence_service import RealPostEvidenceResult, RealPostEvidenceRow
from app.services.system_prompt_keyword_service import CONTENT_GENERATION_KEYWORDS_ASSET_TYPE


DEFAULT_WANGYUE_EVIDENCE_KEYWORD_ASSET_KEY = "wangyue_article_generation_keywords_real_post_evidence_draft"
DEFAULT_WANGYUE_EVIDENCE_CATEGORY_CODE = "article_wangyue_real_post_evidence_texture"


@dataclass(frozen=True)
class WangyueEvidenceAssetDraft:
    asset_type: str
    asset_key: str
    display_name: str
    content_json: dict[str, Any]
    metadata_json: dict[str, Any]
    source_hash: str


class WangyueEvidenceAssetDraftService:
    def __init__(self, asset_service: AssetService | None = None) -> None:
        self.asset_service = asset_service

    def build_keyword_asset_draft(
        self,
        evidence: RealPostEvidenceResult,
        *,
        asset_key: str = DEFAULT_WANGYUE_EVIDENCE_KEYWORD_ASSET_KEY,
        category_code: str = DEFAULT_WANGYUE_EVIDENCE_CATEGORY_CODE,
        display_name: str = "旺玥真人帖证据纹理-候选草案",
    ) -> WangyueEvidenceAssetDraft:
        stable_rows = [row for row in evidence.rows if row.allow_asset == "stable_candidate"]
        texture_rows = [row for row in evidence.rows if row.allow_asset == "texture_only"]
        risk_rows = [row for row in evidence.rows if row.allow_asset in {"risk_reference", "exclude"}]
        sub_keywords = build_sub_keywords(stable_rows, texture_rows, risk_rows)
        content_json = {
            "schema_version": "2",
            "asset_key": asset_key,
            "categories": [
                {
                    "category_code": category_code,
                    "category_name": "旺玥真人帖证据纹理",
                    "enabled": True,
                    "applicable_content_types": ["article"],
                    "selection_strategy": "random_one",
                    "description": (
                        "低权重表达证据：只调产品出现资格、标题松散、状态观察、结尾停法和说话毛边；"
                        "不提供新的旺玥产品事实。"
                    ),
                    "sub_keywords": sub_keywords,
                }
            ],
        }
        metadata_json = {
            "asset_stage": "candidate",
            "source": "maga_real_post_evidence_service",
            "evidence_profile": evidence.stats.get("profile"),
            "evidence_stats": evidence.stats,
            "stable_source_rows": [row.source_row_no for row in stable_rows],
            "texture_only_source_rows": [row.source_row_no for row in texture_rows],
            "risk_source_rows": [row.source_row_no for row in risk_rows],
            "boundary": [
                "raw posts are not copied into prompts",
                "product facts still come from Wangyue business rules",
                "candidate asset requires human review before production use",
            ],
        }
        source_hash = _json_hash({"content_json": content_json, "metadata_json": metadata_json})
        return WangyueEvidenceAssetDraft(
            asset_type=CONTENT_GENERATION_KEYWORDS_ASSET_TYPE,
            asset_key=asset_key,
            display_name=display_name,
            content_json=content_json,
            metadata_json=metadata_json,
            source_hash=source_hash,
        )

    async def create_candidate_asset(self, draft: WangyueEvidenceAssetDraft, *, created_by: str = "maga-real-post-evidence") -> Any:
        if self.asset_service is None:
            raise ValueError("asset_service is required to create candidate assets")
        return await self.asset_service.create_candidate_asset(
            AssetCandidateCreate(
                asset_type=draft.asset_type,
                asset_key=draft.asset_key,
                display_name=draft.display_name,
                source_name="maga_real_post_evidence_service",
                source_uri="service://maga/real-post-evidence",
                source_hash=draft.source_hash,
                content_json=draft.content_json,
                metadata_json=draft.metadata_json,
                created_by=created_by,
            )
        )


def build_sub_keywords(
    stable_rows: list[RealPostEvidenceRow],
    texture_rows: list[RealPostEvidenceRow],
    risk_rows: list[RealPostEvidenceRow],
) -> list[dict[str, Any]]:
    rows = stable_rows + texture_rows
    layer_set = {layer for row in rows for layer in row.usable_layers}
    sub_keywords: list[dict[str, Any]] = []

    if any(layer.startswith("product_entry") for layer in layer_set):
        sub_keywords.append(
            _keyword(
                "wangyue_real_post_product_presence",
                "真人帖机制-产品出现资格",
                "真实儿童奶粉帖证据：产品通常先有出现资格，再被写进帖子，比如复购、补货、对比后选择、被问起或孩子接受。只借“产品为什么会出现在帖子里”的机制，不借原帖品牌、年龄、数字、季节疾病、医生建议或孩子自己操作奶粉的动作。",
                stable_rows,
                layer_prefixes=("product_entry",),
            )
        )
    if any(layer.startswith("title_shape") for layer in layer_set):
        sub_keywords.append(
            _keyword(
                "wangyue_real_post_title_loose",
                "真人帖机制-标题松散",
                "真实帖标题经常不是完整卖点句，而是短名词、短动作、半句记录或当天想到的一个小点。只借标题松散度；标题仍要跟正文一致，不能截断正文残句，也不能写低龄、季节活动或疾病大环境。",
                rows,
                layer_prefixes=("title_shape",),
            )
        )
    if any(layer.startswith("proof_surface") for layer in layer_set):
        sub_keywords.append(
            _keyword(
                "wangyue_real_post_benefit_observation",
                "真人帖机制-状态观察证明",
                "真实儿童奶粉帖的正向证明常落在自家观察里，比如接受度、状态、精力、专注或日常营养安排变顺，而不是医学结论。具体痛点、卖点、成分和正向证据必须听本篇业务规则，不把保护类成分写成身形增长原因。",
                stable_rows,
                layer_prefixes=("proof_surface",),
            )
        )
    if any(layer.startswith("life_entry") or layer.startswith("texture") for layer in layer_set):
        sub_keywords.append(
            _keyword(
                "wangyue_real_post_life_texture",
                "真人帖机制-生活入口毛边",
                "真实帖子里的生活入口不只围绕冲奶动作，也会从家里一句话、放学回家、饭桌、出门、玩、画、老师或朋友随口问起这些普通现场进入。只借生活观察来源，不新增产品动作、固定喝法或业务规则外的卖点。",
                rows,
                layer_prefixes=("life_entry", "texture"),
            )
        )
    if any(layer.startswith("ending") or layer.startswith("ending_or_entry") for layer in layer_set):
        sub_keywords.append(
            _keyword(
                "wangyue_real_post_ending_fact_stop",
                "真人帖机制-事实停住",
                "真实帖子结尾可以停在一个事实、孩子反应、手边动作、当天记录或没说满的念头上，不一定每篇都总结推荐。只借自然停顿方式，不强行互动提问，不补齐业务规则没有要求的选择链、复购链或安心总结。",
                rows,
                layer_prefixes=("ending", "ending_or_entry"),
            )
        )
    if texture_rows:
        sub_keywords.append(
            _keyword(
                "wangyue_real_post_tone_fragment",
                "真人帖机制-说话毛边",
                "真实帖子常有一点边写边想、顺手补一句、前后不完全对称的松散感；它服务真人感和多样性，不负责提供新的产品事实。只借语气和句子节奏，不照搬原句，不把求助帖、低龄转奶、季节疾病、身高体检或强功效话术迁移到旺玥正文。",
                texture_rows,
                layer_prefixes=(),
            )
        )
    if risk_rows:
        sub_keywords.append(
            _keyword(
                "wangyue_real_post_risk_boundary",
                "真人帖机制-风险边界",
                "真实帖里出现过的低龄、转奶、季节疾病、医生体检、孩子自己泡奶粉、便携奶粉动作和强功效表达，只能作为风险边界参考。生成旺玥时不能迁移这些事实链路。",
                risk_rows,
                layer_prefixes=(),
                enabled=False,
            )
        )
    return sub_keywords


def _keyword(
    code: str,
    name: str,
    corpus: str,
    rows: list[RealPostEvidenceRow],
    *,
    layer_prefixes: tuple[str, ...],
    enabled: bool = True,
) -> dict[str, Any]:
    if layer_prefixes:
        source_rows = [
            row.source_row_no
            for row in rows
            if any(layer.startswith(prefix) for layer in row.usable_layers for prefix in layer_prefixes)
        ]
    else:
        source_rows = [row.source_row_no for row in rows]
    return {
        "keyword_code": code,
        "keyword_name": name,
        "enabled": enabled,
        "corpus": [corpus],
        "source": {
            "type": "real_post_mechanism_evidence",
            "source_rows": source_rows[:30],
            "note": "derived from classified real-post evidence rows; raw posts are not copied into prompt",
        },
    }


def render_asset_draft_markdown(draft: WangyueEvidenceAssetDraft) -> str:
    category = (draft.content_json.get("categories") or [{}])[0]
    lines = [
        "# 旺玥真人帖证据 Asset Draft",
        "",
        f"- asset_type: `{draft.asset_type}`",
        f"- asset_key: `{draft.asset_key}`",
        f"- source_hash: `{draft.source_hash}`",
        f"- category_code: `{category.get('category_code')}`",
        f"- sub_keywords: {len(category.get('sub_keywords') or [])}",
        "",
        "## Boundary",
        "",
    ]
    for item in draft.metadata_json.get("boundary") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Sub Keywords", ""])
    for keyword in category.get("sub_keywords") or []:
        lines.extend(
            [
                f"### {keyword['keyword_code']}｜{keyword['keyword_name']}",
                "",
                f"- enabled: `{keyword.get('enabled', True)}`",
                f"- source_rows: `{keyword.get('source', {}).get('source_rows', [])}`",
                "",
                keyword["corpus"][0],
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _json_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
