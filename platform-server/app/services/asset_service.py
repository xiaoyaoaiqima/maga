"""Services for MAGA asset registry and Asset Steward proposal workflow."""
from __future__ import annotations

import copy
from collections import Counter
import re
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maga_assets import AssetChangeProposal, AssetChangeRequest, AssetImportRun, AssetRegistry
from app.services.business_rule_asset_types import (
    ARTICLE_BUSINESS_RULE_ASSET_TYPE,
    ARTICLE_BUSINESS_RULE_ASSET_TYPES,
    COMMENT_BUSINESS_RULE_ASSET_TYPES,
    content_type_for_business_rule_asset_type,
)
from app.services.comment_business_rule_service import (
    COMMENT_BUSINESS_RULE_ASSET_TYPE,
    _clean_corpus_for_prompt,
    _split_examples_from_corpus,
    normalize_comment_prompt_bundle,
)
from app.schemas.assets import (
    AssetCandidateCreate,
    ArticleBusinessRuleFieldsUpdate,
    AssetChangeProposalCreate,
    AssetChangeRequestCreate,
    CommentBusinessRuleExamplesUpdate,
    CommentBusinessRuleDraftSave,
    SellingPainpointExpressionUpdate,
    AssetGenerationOptionsResponse,
)

LEGACY_PRODUCT_EXPERIENCE_RULE_ASSET_TYPE = "product_experience_rule_set"

class AssetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_assets(
        self,
        *,
        asset_type: str | None = None,
        asset_key: str | None = None,
        status: str = "active",
        asset_stage: str | None = "production",
        latest_only: bool = True,
        include_hidden: bool = False,
    ) -> list[AssetRegistry]:
        filters = []
        if asset_type:
            filters.append(AssetRegistry.asset_type == asset_type)
        if asset_key:
            filters.append(AssetRegistry.asset_key == asset_key)
        if status:
            filters.append(AssetRegistry.status == status)
        if asset_stage:
            filters.append(AssetRegistry.asset_stage == asset_stage)
        if latest_only:
            latest_rows = (
                await self.db.execute(
                    select(
                        AssetRegistry.id,
                        AssetRegistry.asset_type,
                        AssetRegistry.asset_key,
                        AssetRegistry.asset_stage,
                        AssetRegistry.version_no,
                    ).where(*filters)
                )
            ).all()
            latest_by_key: dict[tuple[str, str, str], tuple[int, int]] = {}
            for row in latest_rows:
                key = (row.asset_type, row.asset_key, row.asset_stage)
                current = latest_by_key.get(key)
                candidate = (int(row.version_no or 0), int(row.id))
                if current is None or candidate > current:
                    latest_by_key[key] = candidate
            latest_ids = [asset_id for _version_no, asset_id in latest_by_key.values()]
            if not latest_ids:
                return []
            stmt = select(AssetRegistry).where(AssetRegistry.id.in_(latest_ids))
        else:
            stmt = select(AssetRegistry)
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.order_by(
                AssetRegistry.asset_type,
                AssetRegistry.asset_key,
                AssetRegistry.version_no.desc(),
            )
        result = await self.db.execute(stmt)
        assets = list(result.scalars().all())
        if latest_only:
            assets.sort(
                key=lambda asset: (
                    asset.asset_type or "",
                    asset.asset_key or "",
                    -(asset.version_no or 0),
                )
            )
        if include_hidden:
            return assets
        # 历史 probe/focus 资产不删除，只通过 metadata_json.hidden 从运营默认视图隐藏。
        return [asset for asset in assets if not _asset_is_hidden(asset)]

    async def get_latest_asset(
        self,
        asset_type: str,
        asset_key: str,
        *,
        asset_stage: str | None = "production",
        compatible: bool = False,
    ) -> AssetRegistry | None:
        if compatible and asset_type == LEGACY_PRODUCT_EXPERIENCE_RULE_ASSET_TYPE:
            compatible_asset = await self.get_latest_asset(
                ARTICLE_BUSINESS_RULE_ASSET_TYPE,
                asset_key,
                asset_stage=asset_stage,
                compatible=False,
            )
            if compatible_asset is not None:
                return compatible_asset
        stmt = (
            select(AssetRegistry.id)
            .where(
                AssetRegistry.asset_type == asset_type,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
        if asset_stage:
            stmt = stmt.where(AssetRegistry.asset_stage == asset_stage)
        result = await self.db.execute(stmt)
        asset_id = result.scalar_one_or_none()
        if asset_id is None:
            return None
        return await self.db.get(AssetRegistry, asset_id)

    async def _get_latest_comment_business_rule_asset(self, asset_key: str) -> AssetRegistry | None:
        result = await self.db.execute(
            select(AssetRegistry.id)
            .where(
                AssetRegistry.asset_type.in_(COMMENT_BUSINESS_RULE_ASSET_TYPES),
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
                AssetRegistry.asset_stage == "production",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
        asset_id = result.scalar_one_or_none()
        if asset_id is None:
            return None
        return await self.db.get(AssetRegistry, asset_id)

    async def _get_latest_article_business_rule_asset(self, asset_key: str) -> AssetRegistry | None:
        result = await self.db.execute(
            select(AssetRegistry.id)
            .where(
                AssetRegistry.asset_type.in_(ARTICLE_BUSINESS_RULE_ASSET_TYPES),
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
                AssetRegistry.asset_stage == "production",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
        asset_id = result.scalar_one_or_none()
        if asset_id is None:
            return None
        return await self.db.get(AssetRegistry, asset_id)

    async def update_asset_visibility(
        self,
        asset_type: str,
        asset_key: str,
        *,
        hidden: bool,
        reason: str | None = None,
        asset_stage: str | None = "production",
        updated_by: str | None = "maga-operator",
    ) -> AssetRegistry | None:
        asset = await self.get_latest_asset(asset_type, asset_key, asset_stage=asset_stage)
        if asset is None:
            return None
        metadata = dict(asset.metadata_json or {})
        metadata["hidden"] = hidden
        if reason:
            metadata["visibility_reason"] = reason
        if updated_by:
            metadata["visibility_updated_by"] = updated_by
        asset.metadata_json = metadata
        return asset

    async def list_import_runs(self, *, limit: int = 20) -> list[AssetImportRun]:
        result = await self.db.execute(
            select(AssetImportRun).order_by(AssetImportRun.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def list_change_requests(self, *, limit: int = 20, status: str | None = None) -> list[AssetChangeRequest]:
        stmt = select(AssetChangeRequest)
        if status:
            stmt = stmt.where(AssetChangeRequest.status == status)
        result = await self.db.execute(
            stmt.order_by(AssetChangeRequest.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def generation_options(self, *, asset_key: str | None = None) -> AssetGenerationOptionsResponse:
        all_assets = await self.list_assets()
        asset_keys = sorted({asset.asset_key for asset in all_assets if asset.asset_key})
        assets = [asset for asset in all_assets if not asset_key or asset.asset_key == asset_key]
        product_topics: list[str] = []
        target_audiences: list[str] = []
        persona_profiles: list[str] = []

        for asset in assets:
            content = asset.content_json or {}
            if asset.asset_type == "painpoint_model":
                for item in _painpoint_items(content):
                    # 主题是写作切入点，当前由内容模型里的核心痛点承接；
                    # 不混入品牌资料、产品卖点或例文方向，避免和产品/品牌维度耦合。
                    _add_option(product_topics, item.get("topic") or item.get("painpoint"))
                    _add_option(target_audiences, item.get("baby_stage"))
        for asset in await self._list_generation_persona_assets(asset_key=asset_key):
            for item in _content_items(asset.content_json or {}):
                _add_option(persona_profiles, item.get("persona_name"))

        return AssetGenerationOptionsResponse(
            asset_key=asset_key,
            asset_keys=asset_keys,
            product_topics=product_topics,
            target_audiences=target_audiences or _default_target_audiences(asset_key),
            persona_profiles=persona_profiles,
            styles=_default_content_styles(),
        )

    async def _list_generation_persona_assets(self, *, asset_key: str | None) -> list[AssetRegistry]:
        production_assets = await self.list_assets(
            asset_type="persona_profiles",
            asset_key=asset_key,
            asset_stage="production",
        )
        if production_assets:
            return production_assets
        # 本地 MVP 允许读取候选人设做生文调试，但不会把候选人设混入目标人群或风格。
        return await self.list_assets(
            asset_type="persona_profiles",
            asset_key=asset_key,
            asset_stage="candidate",
        )

    async def create_candidate_asset(self, payload: AssetCandidateCreate) -> AssetRegistry:
        """Persist AI-expanded corpus into asset_registry as candidate stage.

        Candidate assets share the same versioned registry as production assets,
        but generation planners keep reading production only until candidates are
        explicitly promoted by a later workflow.
        """
        await self.db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == payload.asset_type,
                AssetRegistry.asset_key == payload.asset_key,
                AssetRegistry.asset_stage == "candidate",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        asset = AssetRegistry(
            asset_type=payload.asset_type,
            asset_key=payload.asset_key,
            display_name=payload.display_name,
            version_no=await self._next_asset_version(payload.asset_type, payload.asset_key),
            status="active",
            asset_stage="candidate",
            source_name=payload.source_name,
            source_uri=payload.source_uri,
            source_hash=payload.source_hash,
            content_json=normalize_asset_content(payload.asset_type, payload.content_json),
            metadata_json={
                "asset_stage": "candidate",
                **(payload.metadata_json or {}),
            },
            created_by=payload.created_by,
        )
        self.db.add(asset)
        await self.db.flush()
        return asset

    async def create_change_request(self, payload: AssetChangeRequestCreate) -> AssetChangeRequest:
        request = AssetChangeRequest(
            source_text=payload.source_text,
            requester=payload.requester,
            context_json=payload.context_json,
            status="pending",
            created_by=payload.created_by,
        )
        self.db.add(request)
        await self.db.flush()
        return request

    async def create_change_proposal(self, payload: AssetChangeProposalCreate) -> AssetChangeProposal:
        proposal = AssetChangeProposal(
            request_id=payload.request_id,
            risk_level=payload.risk_level,
            summary=payload.summary,
            affected_assets_json=payload.affected_assets_json,
            proposed_changes_json=payload.proposed_changes_json,
            risk_notes_json=payload.risk_notes_json,
            smoke_test_json=payload.smoke_test_json,
            status="proposed",
            created_by=payload.created_by,
        )
        self.db.add(proposal)
        await self.db.flush()
        request = await self.db.get(AssetChangeRequest, payload.request_id)
        if request is not None and request.status == "pending":
            request.status = "proposed"
            await self.db.flush()
        return proposal

    async def list_change_proposals(
        self,
        *,
        limit: int = 20,
        status: str | None = None,
    ) -> list[AssetChangeProposal]:
        stmt = select(AssetChangeProposal)
        if status:
            stmt = stmt.where(AssetChangeProposal.status == status)
        result = await self.db.execute(
            stmt.order_by(AssetChangeProposal.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def save_comment_business_rule_draft(self, payload: CommentBusinessRuleDraftSave) -> AssetChangeProposal:
        asset = await self._get_latest_comment_business_rule_asset(payload.asset_key)
        draft_type = "comment_business_rule_item"
        smoke_endpoint = "/api/v1/content-agent/comment-batches/start"
        if asset is None:
            asset = await self._get_latest_article_business_rule_asset(payload.asset_key)
            draft_type = "article_business_rule_item"
            smoke_endpoint = "/api/v1/content-agent/batches/start"
        if asset is None:
            raise ValueError("business rule asset not found")
        _, item = _find_business_rule_item(asset.content_json, rule_id=payload.rule_id, source_row_no=payload.source_row_no)
        draft_corpus = payload.draft_corpus.strip()
        if not draft_corpus:
            raise ValueError("draft_corpus is required")
        draft_comment_prompt_bundle = normalize_comment_prompt_bundle(payload.comment_prompt_bundle)
        if draft_comment_prompt_bundle:
            if draft_type != "comment_business_rule_item":
                raise ValueError("comment_prompt_bundle only supports comment business rules")
            draft_corpus = draft_comment_prompt_bundle["content_direction"]

        request = AssetChangeRequest(
            source_text=f"业务规则草稿：{payload.asset_key}/{item.get('rule_id')}",
            requester=payload.created_by,
            context_json={
                "draft_type": draft_type,
                "asset_type": asset.asset_type,
                "asset_key": payload.asset_key,
                "base_asset_id": asset.id,
                "base_version_no": asset.version_no,
                "rule_id": item.get("rule_id"),
                "source_row_no": item.get("source_row_no"),
            },
            status="draft",
            created_by=payload.created_by,
        )
        self.db.add(request)
        await self.db.flush()

        proposal = AssetChangeProposal(
            request_id=request.id,
            risk_level="medium",
            summary=f"业务规则单条草稿：{item.get('rule_id') or item.get('source_row_no')}",
            affected_assets_json=[
                {
                    "asset_type": asset.asset_type,
                    "asset_key": payload.asset_key,
                    "base_asset_id": asset.id,
                    "base_version_no": asset.version_no,
                    "rule_id": item.get("rule_id"),
                    "source_row_no": item.get("source_row_no"),
                }
            ],
            proposed_changes_json={
                "draft_type": draft_type,
                "asset_type": asset.asset_type,
                "asset_key": payload.asset_key,
                "base_asset_id": asset.id,
                "base_version_no": asset.version_no,
                "target": {
                    "rule_id": item.get("rule_id"),
                    "source_row_no": item.get("source_row_no"),
                    "business_rule": _business_rule_name(item),
                },
                "original_corpus": item.get("corpus") or "",
                "draft_corpus": draft_corpus,
                "draft_examples": _extract_examples_from_corpus(draft_corpus),
                "original_comment_prompt_bundle": copy.deepcopy(item.get("comment_prompt_bundle")),
                "draft_comment_prompt_bundle": draft_comment_prompt_bundle,
            },
            risk_notes_json=[
                "草稿不会影响正式 production 规则包。",
                "发布时会复制当前 active 规则包，只替换目标规则并生成新版本。",
            ],
            smoke_test_json={
                "endpoint": smoke_endpoint,
                "asset_key": payload.asset_key,
                "rule_id": item.get("rule_id"),
                "source_row_no": item.get("source_row_no"),
                "draft_rule_id": item.get("rule_id"),
                "draft_source_row_no": item.get("source_row_no"),
            },
            status="draft",
            created_by=payload.created_by,
        )
        self.db.add(proposal)
        await self.db.flush()
        return proposal

    async def list_comment_business_rule_drafts(
        self,
        *,
        asset_key: str,
        rule_id: str | None = None,
        source_row_no: int | None = None,
        limit: int = 20,
    ) -> list[AssetChangeProposal]:
        result = await self.db.execute(
            select(AssetChangeProposal)
            .where(AssetChangeProposal.status.in_(["draft", "testing"]))
            .order_by(AssetChangeProposal.id.desc())
            .limit(max(1, min(limit * 5, 200)))
        )
        drafts: list[AssetChangeProposal] = []
        for proposal in result.scalars().all():
            changes = proposal.proposed_changes_json or {}
            if changes.get("draft_type") not in ("comment_business_rule_item", "article_business_rule_item"):
                continue
            if changes.get("asset_key") != asset_key:
                continue
            target = changes.get("target") if isinstance(changes.get("target"), dict) else {}
            if rule_id and str(target.get("rule_id") or "") != str(rule_id):
                continue
            if source_row_no is not None and _int_or_none(target.get("source_row_no")) != int(source_row_no):
                continue
            drafts.append(proposal)
            if len(drafts) >= limit:
                break
        return drafts

    async def business_rule_copilot_context(
        self,
        *,
        asset_key: str,
        rule_id: str | None = None,
        source_row_no: int | None = None,
        draft_id: int | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        draft: AssetChangeProposal | None = None
        draft_changes: dict[str, Any] = {}
        if draft_id is not None:
            draft = await self.db.get(AssetChangeProposal, draft_id)
            if draft is None:
                raise ValueError("draft not found")
            draft_changes = draft.proposed_changes_json or {}
            if draft_changes.get("draft_type") not in ("comment_business_rule_item", "article_business_rule_item"):
                raise ValueError("not a business rule draft")
            asset_key = str(draft_changes.get("asset_key") or asset_key or "").strip()
            target = draft_changes.get("target") if isinstance(draft_changes.get("target"), dict) else {}
            rule_id = rule_id or str(target.get("rule_id") or "") or None
            source_row_no = source_row_no if source_row_no is not None else _int_or_none(target.get("source_row_no"))

        asset = await self._get_latest_comment_business_rule_asset(asset_key)
        if asset is None:
            asset = await self._get_latest_article_business_rule_asset(asset_key)
        if asset is None:
            raise ValueError("business rule asset not found")

        index, item = _find_business_rule_item(
            asset.content_json,
            rule_id=rule_id,
            source_row_no=source_row_no,
        )
        content_type = content_type_for_business_rule_asset_type(asset.asset_type)
        endpoint = (
            "/api/v1/content-agent/comment-batches/start"
            if content_type == "comment"
            else "/api/v1/content-agent/batches/start"
        )
        resolved_rule_id = str(item.get("rule_id") or "") or None
        resolved_source_row_no = _int_or_none(item.get("source_row_no"))
        selector_payload = {
            "asset_key": asset.asset_key,
            "rule_id": resolved_rule_id,
            "source_row_no": resolved_source_row_no,
        }
        base_payload = {
            key: value
            for key, value in selector_payload.items()
            if value is not None
        }
        draft_payload_template = {
            **base_payload,
            "draft_rule_id": resolved_rule_id,
            "draft_source_row_no": resolved_source_row_no,
            "draft_corpus": "<fill with candidate corpus>",
        }
        draft_corpus = str(draft_changes.get("draft_corpus") or "").strip()
        if draft_corpus:
            draft_payload_template["draft_corpus"] = draft_corpus

        latest_drafts = await self.list_comment_business_rule_drafts(
            asset_key=asset.asset_key,
            rule_id=resolved_rule_id,
            source_row_no=resolved_source_row_no,
            limit=limit,
        )
        return {
            "asset": {
                "id": asset.id,
                "asset_type": asset.asset_type,
                "asset_key": asset.asset_key,
                "display_name": asset.display_name,
                "version_no": asset.version_no,
                "status": asset.status,
                "asset_stage": asset.asset_stage,
                "source_name": asset.source_name,
                "created_by": asset.created_by,
                "create_time": asset.create_time,
                "update_time": asset.update_time,
            },
            "content_type": content_type,
            "rule": {
                "index": index,
                "item_no": index + 1,
                "rule_id": resolved_rule_id,
                "source_row_no": resolved_source_row_no,
                "business_rule": _business_rule_name(item),
                "corpus": item.get("corpus") or "",
                "examples": item.get("examples") or [],
                "supplements": item.get("supplements") or [],
                "raw": item,
            },
            "selected_draft": comment_business_rule_draft_response(draft) if draft is not None else None,
            "drafts": [comment_business_rule_draft_response(item) for item in latest_drafts],
            "workflow": {
                "save_draft": {
                    "endpoint": "/api/v1/assets/comment-business-rule-drafts",
                    "method": "POST",
                    "payload": {
                        **base_payload,
                        "draft_corpus": "<fill with candidate corpus>",
                        "created_by": "codex-copilot",
                    },
                },
                "publish_draft": {
                    "endpoint": "/api/v1/assets/comment-business-rule-drafts/{draft_id}/publish",
                    "method": "POST",
                    "payload": {"created_by": "codex-copilot"},
                },
                "test_payloads": {
                    "quick_generate_only": {
                        "endpoint": endpoint,
                        "method": "POST",
                        "payload": {
                            **draft_payload_template,
                            "count": 1,
                            "postprocess_mode": "generate_only",
                            "created_by": "codex-copilot",
                        },
                    },
                    "once_full": {
                        "endpoint": endpoint,
                        "method": "POST",
                        "payload": {
                            **draft_payload_template,
                            "count": 1,
                            "created_by": "codex-copilot",
                        },
                    },
                    "ten_parallel": {
                        "endpoint": endpoint,
                        "method": "POST",
                        "payload": {
                            **draft_payload_template,
                            "count": 10,
                            "created_by": "codex-copilot",
                        },
                    },
                },
                "report": {
                    "endpoint": "/api/v1/content-agent/batches/{batch_id}/report?full=true",
                    "method": "GET",
                },
            },
        }

    async def publish_comment_business_rule_draft(
        self,
        draft_id: int,
        *,
        created_by: str | None = "maga-operator",
    ) -> tuple[AssetChangeProposal | None, AssetRegistry | None]:
        proposal = await self.db.get(AssetChangeProposal, draft_id)
        if proposal is None:
            return None, None
        changes = proposal.proposed_changes_json or {}
        draft_type = changes.get("draft_type")
        if draft_type not in ("comment_business_rule_item", "article_business_rule_item"):
            raise ValueError("not a business rule draft")
        if proposal.status == "applied" and proposal.applied_asset_ids_json:
            asset = await self.db.get(AssetRegistry, proposal.applied_asset_ids_json[0])
            return proposal, asset

        asset_key = str(changes.get("asset_key") or "").strip()
        is_article_draft = draft_type == "article_business_rule_item"
        current_asset = (
            await self._get_latest_article_business_rule_asset(asset_key)
            if is_article_draft
            else await self._get_latest_comment_business_rule_asset(asset_key)
        )
        if current_asset is None:
            raise ValueError("business rule asset not found")
        compatible_types = ARTICLE_BUSINESS_RULE_ASSET_TYPES if is_article_draft else COMMENT_BUSINESS_RULE_ASSET_TYPES
        source_prefix = "article_business_rule_draft" if is_article_draft else "comment_business_rule_draft"
        target = changes.get("target") if isinstance(changes.get("target"), dict) else {}
        content_json = copy.deepcopy(current_asset.content_json or {})
        _, item = _find_business_rule_item(
            content_json,
            rule_id=str(target.get("rule_id") or "") or None,
            source_row_no=_int_or_none(target.get("source_row_no")),
        )
        draft_corpus = str(changes.get("draft_corpus") or "").strip()
        if not draft_corpus:
            raise ValueError("draft_corpus is empty")
        if is_article_draft:
            # 重要逻辑：帖子/生文的规则语料与示例池分开维护；发布草稿只替换 corpus。
            item["corpus"] = draft_corpus
        else:
            draft_comment_prompt_bundle = normalize_comment_prompt_bundle(
                changes.get("draft_comment_prompt_bundle")
            )
            if draft_comment_prompt_bundle:
                item["prompt_mode"] = "comment_prompt_bundle"
                item["comment_prompt_bundle"] = draft_comment_prompt_bundle
                item["content_direction"] = draft_comment_prompt_bundle["content_direction"]
                item["activity_material"] = draft_comment_prompt_bundle["activity_material"]
                item["corpus"] = draft_comment_prompt_bundle["content_direction"]
            else:
                clean_corpus, draft_examples = _split_examples_from_corpus(draft_corpus)
                # 重要逻辑：发布草稿只替换目标单条规则，保留当前 active 版本中的其他运营改动；
                # 同时沿用导入器清洗，避免“关键词方向/全量示例”等运营备注进入生产 prompt。
                item["corpus"] = _clean_corpus_for_prompt(clean_corpus, business_rule=_business_rule_name(item))
                if draft_examples:
                    item["examples"] = draft_examples

        await self.db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type.in_(compatible_types),
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        metadata_json = copy.deepcopy(current_asset.metadata_json or {})
        metadata_json.update(
            {
                "rule_count": len(content_json.get("items") or []),
                "example_count": _business_rule_example_count(content_json),
                "last_rule_draft_id": proposal.id,
                "last_rule_draft_base_asset_id": changes.get("base_asset_id"),
                "last_rule_draft_base_version_no": changes.get("base_version_no"),
            }
        )
        asset = AssetRegistry(
            asset_type=current_asset.asset_type,
            asset_key=asset_key,
            display_name=current_asset.display_name,
            version_no=await self._next_compatible_asset_version(compatible_types, asset_key),
            status="active",
            asset_stage="production",
            source_name=f"{source_prefix}:{proposal.id}",
            source_uri=None,
            source_hash=None,
            content_json=content_json,
            metadata_json=metadata_json,
            created_by=created_by,
        )
        self.db.add(asset)
        await self.db.flush()

        proposal.status = "applied"
        proposal.applied_by = created_by
        proposal.applied_asset_ids_json = [asset.id]
        request = await self.db.get(AssetChangeRequest, proposal.request_id)
        if request is not None:
            request.status = "applied"
        await self.db.flush()
        return proposal, asset

    async def update_comment_business_rule_examples(
        self,
        payload: CommentBusinessRuleExamplesUpdate,
    ) -> AssetRegistry:
        return await self.update_business_rule_examples(payload, asset_type="comment")

    async def update_business_rule_examples(
        self,
        payload: CommentBusinessRuleExamplesUpdate,
        *,
        asset_type: str | None = None,
    ) -> AssetRegistry:
        asset = await self._get_latest_comment_business_rule_asset(payload.asset_key)
        compatible_types = COMMENT_BUSINESS_RULE_ASSET_TYPES
        new_asset_type = COMMENT_BUSINESS_RULE_ASSET_TYPE
        source_prefix = "comment_business_rule_examples"
        if asset_type == "article" or (asset is None and asset_type != "comment"):
            asset = await self._get_latest_article_business_rule_asset(payload.asset_key)
            compatible_types = ARTICLE_BUSINESS_RULE_ASSET_TYPES
            new_asset_type = ARTICLE_BUSINESS_RULE_ASSET_TYPE
            source_prefix = "article_business_rule_examples"
        if asset is None:
            raise ValueError("business rule asset not found")
        content_json = copy.deepcopy(asset.content_json or {})
        _, item = _find_business_rule_item(
            content_json,
            rule_id=payload.rule_id,
            source_row_no=payload.source_row_no,
        )
        examples = _clean_text_list(payload.examples) + _clean_text_list(payload.supplements)
        supplements: list[str] = []
        item["examples"] = examples
        item["supplements"] = supplements

        await self.db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type.in_(compatible_types),
                AssetRegistry.asset_key == payload.asset_key,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        metadata_json = copy.deepcopy(asset.metadata_json or {})
        metadata_json.update(
            {
                "rule_count": len(content_json.get("items") or []),
                "example_count": _business_rule_example_count(content_json),
                "last_examples_rule_id": item.get("rule_id"),
                "last_examples_source_row_no": item.get("source_row_no"),
                "last_examples_base_asset_id": asset.id,
                "last_examples_base_version_no": asset.version_no,
            }
        )
        new_asset = AssetRegistry(
            asset_type=new_asset_type,
            asset_key=payload.asset_key,
            display_name=asset.display_name,
            version_no=await self._next_compatible_asset_version(compatible_types, payload.asset_key),
            status="active",
            asset_stage="production",
            source_name=f"{source_prefix}:{item.get('rule_id') or item.get('source_row_no')}",
            source_uri=None,
            source_hash=None,
            content_json=content_json,
            metadata_json=metadata_json,
            created_by=payload.created_by,
        )
        self.db.add(new_asset)
        await self.db.flush()
        return new_asset

    async def update_selling_painpoint_expression(
        self,
        asset_key: str,
        source_row_no: int,
        payload: SellingPainpointExpressionUpdate,
    ) -> AssetRegistry:
        asset = await self.get_latest_asset(ARTICLE_BUSINESS_RULE_ASSET_TYPE, asset_key)
        if asset is None:
            raise ValueError("article business rule asset not found")

        content_json = copy.deepcopy(asset.content_json or {})
        expressions = content_json.get("selling_painpoint_expressions")
        if not isinstance(expressions, list):
            raise ValueError("selling painpoint expressions not found")
        matches = [
            item
            for item in expressions
            if isinstance(item, dict) and _int_or_none(item.get("source_row_no")) == source_row_no
        ]
        if len(matches) != 1:
            raise ValueError("selling painpoint expression selector must match exactly one item")

        item = matches[0]
        current_expression = str(item.get("expression") or "").strip()
        if payload.expected_expression is not None and current_expression != payload.expected_expression.strip():
            raise ValueError("selling painpoint expression changed since review")
        next_expression = payload.expression.strip()
        if current_expression == next_expression:
            return asset
        item["expression"] = next_expression

        await self.db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == ARTICLE_BUSINESS_RULE_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        metadata_json = copy.deepcopy(asset.metadata_json or {})
        metadata_json.update(
            {
                "last_selling_painpoint_expression_source_row_no": source_row_no,
                "last_selling_painpoint_expression_before": current_expression,
                "last_selling_painpoint_expression_after": next_expression,
                "last_selling_painpoint_expression_base_asset_id": asset.id,
                "last_selling_painpoint_expression_base_version_no": asset.version_no,
            }
        )
        new_asset = AssetRegistry(
            asset_type=ARTICLE_BUSINESS_RULE_ASSET_TYPE,
            asset_key=asset_key,
            display_name=asset.display_name,
            version_no=await self._next_asset_version(ARTICLE_BUSINESS_RULE_ASSET_TYPE, asset_key),
            status="active",
            asset_stage="production",
            source_name=f"selling_painpoint_expression:{source_row_no}",
            source_uri=asset.source_uri,
            source_hash=None,
            content_json=content_json,
            metadata_json=metadata_json,
            created_by=payload.created_by,
        )
        self.db.add(new_asset)
        await self.db.flush()
        return new_asset

    async def replace_selling_painpoint_expressions(
        self,
        asset_key: str,
        expressions: list[dict[str, Any]],
        *,
        source_name: str,
        created_by: str | None,
    ) -> AssetRegistry:
        asset = await self.get_latest_asset(ARTICLE_BUSINESS_RULE_ASSET_TYPE, asset_key)
        if asset is None:
            raise ValueError("article business rule asset not found")
        if not expressions:
            raise ValueError("selling painpoint expressions cannot be empty")

        content_json = copy.deepcopy(asset.content_json or {})
        content_json["selling_painpoint_expressions"] = copy.deepcopy(expressions)
        content_json["selling_painpoint_expression_label"] = "卖点痛点表达"
        group_counts = Counter(str(item.get("selling_painpoint_group") or "") for item in expressions)

        await self.db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == ARTICLE_BUSINESS_RULE_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        metadata_json = copy.deepcopy(asset.metadata_json or {})
        metadata_json.update(
            {
                "selling_painpoint_expression_source": source_name,
                "selling_painpoint_expression_count": len(expressions),
                "selling_painpoint_group_count": len(group_counts),
                "selling_painpoint_group_counts": dict(group_counts),
                "last_selling_painpoint_expression_import_base_asset_id": asset.id,
                "last_selling_painpoint_expression_import_base_version_no": asset.version_no,
            }
        )
        new_asset = AssetRegistry(
            asset_type=ARTICLE_BUSINESS_RULE_ASSET_TYPE,
            asset_key=asset_key,
            display_name=asset.display_name,
            version_no=await self._next_asset_version(ARTICLE_BUSINESS_RULE_ASSET_TYPE, asset_key),
            status="active",
            asset_stage="production",
            source_name=f"selling_painpoint_expressions:{source_name}",
            source_uri=asset.source_uri,
            source_hash=None,
            content_json=content_json,
            metadata_json=metadata_json,
            created_by=created_by,
        )
        self.db.add(new_asset)
        await self.db.flush()
        return new_asset

    async def update_article_business_rule_fields(
        self,
        asset_key: str,
        rule_id: str,
        payload: ArticleBusinessRuleFieldsUpdate,
    ) -> AssetRegistry:
        asset = await self.get_latest_asset(ARTICLE_BUSINESS_RULE_ASSET_TYPE, asset_key)
        if asset is None:
            raise ValueError("article business rule asset not found")
        if payload.corpus is None and payload.selling_painpoint_group is None:
            raise ValueError("no article business rule fields to update")

        content_json = copy.deepcopy(asset.content_json or {})
        _, item = _find_business_rule_item(content_json, rule_id=rule_id, source_row_no=None)
        current_corpus = str(item.get("corpus") or "")
        current_group = str(item.get("selling_painpoint_group") or "")
        if payload.expected_corpus is not None and current_corpus != payload.expected_corpus:
            raise ValueError("article business rule corpus changed since review")
        if (
            payload.expected_selling_painpoint_group is not None
            and current_group != payload.expected_selling_painpoint_group
        ):
            raise ValueError("article business rule selling painpoint group changed since review")

        next_corpus = payload.corpus.strip() if payload.corpus is not None else current_corpus
        next_group = (
            payload.selling_painpoint_group.strip()
            if payload.selling_painpoint_group is not None
            else current_group
        )
        if not next_corpus:
            raise ValueError("article business rule corpus cannot be empty")
        if not next_group:
            raise ValueError("article business rule selling painpoint group cannot be empty")
        if next_corpus == current_corpus and next_group == current_group:
            return asset
        item["corpus"] = next_corpus
        item["selling_painpoint_group"] = next_group

        await self.db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == ARTICLE_BUSINESS_RULE_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        metadata_json = copy.deepcopy(asset.metadata_json or {})
        metadata_json.update(
            {
                "last_article_business_rule_id": rule_id,
                "last_article_business_rule_corpus_before": current_corpus,
                "last_article_business_rule_corpus_after": next_corpus,
                "last_article_business_rule_group_before": current_group,
                "last_article_business_rule_group_after": next_group,
                "last_article_business_rule_base_asset_id": asset.id,
                "last_article_business_rule_base_version_no": asset.version_no,
            }
        )
        new_asset = AssetRegistry(
            asset_type=ARTICLE_BUSINESS_RULE_ASSET_TYPE,
            asset_key=asset_key,
            display_name=asset.display_name,
            version_no=await self._next_asset_version(ARTICLE_BUSINESS_RULE_ASSET_TYPE, asset_key),
            status="active",
            asset_stage="production",
            source_name=f"article_business_rule_fields:{rule_id}",
            source_uri=asset.source_uri,
            source_hash=None,
            content_json=content_json,
            metadata_json=metadata_json,
            created_by=payload.created_by,
        )
        self.db.add(new_asset)
        await self.db.flush()
        return new_asset

    async def create_compliance_rule_proposal_from_request(
        self,
        request_id: int,
        *,
        created_by: str = "maga-asset-steward",
    ) -> AssetChangeProposal | None:
        request = await self.db.get(AssetChangeRequest, request_id)
        if request is None:
            return None

        context = request.context_json or {}
        asset_key = str(context.get("asset_key") or "yuanyue").strip() or "yuanyue"
        forbidden_terms = _forbidden_terms_from_change_request(request)
        rule = _compliance_rule_from_change_request(request, forbidden_terms)
        current_asset = await self.get_latest_asset("compliance_rules", asset_key)
        current_items = _content_items(current_asset.content_json or {}) if current_asset else []
        next_items = [*current_items]
        if not _has_matching_rule(next_items, rule):
            next_items.append(rule)

        proposal = AssetChangeProposal(
            request_id=request.id,
            risk_level="high",
            summary=f"新增禁用事实/卖点规则：{', '.join(forbidden_terms) or '见反馈'}",
            affected_assets_json=[
                {"asset_type": "compliance_rules", "asset_key": asset_key},
                {"asset_type": "brand_profile", "asset_key": asset_key},
                {"asset_type": "product_selling_points", "asset_key": asset_key},
            ],
            proposed_changes_json={
                "assets": [
                    {
                        "asset_type": "compliance_rules",
                        "asset_key": asset_key,
                        "asset_stage": "candidate",
                        "display_name": f"{asset_key} 候选审核规则",
                        "content_json": {
                            "items": next_items,
                            "source_request_id": request.id,
                            "proposal_note": "候选规则需人工确认后再晋级 production。",
                        },
                    }
                ]
            },
            risk_notes_json=[
                "该草案来自运营反馈，默认作为候选资产，不直接覆盖正式规则。",
                "应用后请在资料训练页核对候选 compliance_rules，再决定是否晋级正式资产。",
            ],
            smoke_test_json={
                "asset_key": asset_key,
                "forbidden_terms": forbidden_terms,
                "expected": "后续生文与 AE 审核不得出现这些错误事实或禁用卖点。",
            },
            status="proposed",
            created_by=created_by,
        )
        self.db.add(proposal)
        request.status = "proposed"
        await self.db.flush()
        return proposal

    async def apply_change_proposal(self, proposal_id: int, *, applied_by: str = "maga-asset-steward") -> tuple[AssetChangeProposal | None, list[int]]:
        result = await self.db.execute(select(AssetChangeProposal).where(AssetChangeProposal.id == proposal_id))
        proposal = result.scalar_one_or_none()
        if proposal is None:
            return None, []
        if proposal.status == "applied":
            return proposal, list(proposal.applied_asset_ids_json or [])

        created_ids: list[int] = []
        for item in _proposed_assets(proposal.proposed_changes_json):
            asset = AssetRegistry(
                asset_type=item["asset_type"],
                asset_key=item["asset_key"],
                display_name=item.get("display_name"),
                version_no=await self._next_asset_version(item["asset_type"], item["asset_key"]),
                status="active",
                asset_stage=item.get("asset_stage") or "production",
                source_name=f"asset_change_proposal:{proposal.id}",
                source_uri=None,
                source_hash=None,
                content_json=item.get("content_json") or {},
                metadata_json={"proposal_id": proposal.id, "request_id": proposal.request_id},
                created_by=applied_by,
            )
            self.db.add(asset)
            await self.db.flush()
            created_ids.append(asset.id)

        proposal.status = "applied"
        proposal.applied_by = applied_by
        proposal.applied_asset_ids_json = created_ids
        request = await self.db.get(AssetChangeRequest, proposal.request_id)
        if request is not None:
            request.status = "applied"
        await self.db.flush()
        return proposal, created_ids

    async def _next_asset_version(self, asset_type: str, asset_key: str) -> int:
        result = await self.db.execute(
            select(AssetRegistry.version_no)
            .where(AssetRegistry.asset_type == asset_type, AssetRegistry.asset_key == asset_key)
            .order_by(AssetRegistry.version_no.desc())
            .limit(1)
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1

    async def _next_compatible_asset_version(self, asset_types: tuple[str, ...], asset_key: str) -> int:
        result = await self.db.execute(
            select(AssetRegistry.version_no)
            .where(AssetRegistry.asset_type.in_(asset_types), AssetRegistry.asset_key == asset_key)
            .order_by(AssetRegistry.version_no.desc())
            .limit(1)
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1


def _proposed_assets(changes: dict[str, Any]) -> list[dict[str, Any]]:
    assets = changes.get("assets") if isinstance(changes, dict) else None
    return [item for item in assets or [] if isinstance(item, dict) and item.get("asset_type") and item.get("asset_key")]


def _find_business_rule_item(
    content_json: dict[str, Any] | None,
    *,
    rule_id: str | None,
    source_row_no: int | None,
) -> tuple[int, dict[str, Any]]:
    items = (content_json or {}).get("items")
    if not isinstance(items, list):
        raise ValueError("comment business rule asset has no items")
    matches: list[tuple[int, dict[str, Any]]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if rule_id and str(item.get("rule_id") or "") == str(rule_id):
            matches.append((index, item))
            continue
        if source_row_no is not None and _int_or_none(item.get("source_row_no")) == int(source_row_no):
            matches.append((index, item))
    if not matches:
        raise ValueError("comment business rule item not found")
    if len(matches) > 1:
        raise ValueError("comment business rule selector matched multiple items")
    return matches[0]


def _business_rule_name(item: dict[str, Any]) -> str | None:
    value = item.get("business_rule")
    if value is None:
        value = item.get("comment_" + "angle")
    normalized = str(value or "").strip()
    return normalized or None


def _extract_examples_from_corpus(corpus: str) -> list[str]:
    examples: list[str] = []
    in_examples = False
    for raw_line in str(corpus or "").splitlines():
        line = raw_line.strip()
        if line == "示例：":
            in_examples = True
            continue
        if in_examples and line.startswith("注意："):
            break
        if in_examples and line.startswith("- "):
            example = line[2:].strip()
            if example:
                examples.append(example)
    return examples


def _business_rule_example_count(content_json: dict[str, Any] | None) -> int:
    total = 0
    for item in (content_json or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        total += len(item.get("examples") or []) + len(item.get("supplements") or [])
    return total


def _clean_text_list(values: list[Any] | None) -> list[str]:
    return [str(value or "").strip() for value in values or [] if str(value or "").strip()]


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def comment_business_rule_draft_response(proposal: AssetChangeProposal) -> dict[str, Any]:
    changes = proposal.proposed_changes_json or {}
    target = changes.get("target") if isinstance(changes.get("target"), dict) else {}
    return {
        "id": proposal.id,
        "status": proposal.status,
        "asset_key": str(changes.get("asset_key") or ""),
        "base_asset_id": changes.get("base_asset_id"),
        "base_version_no": changes.get("base_version_no"),
        "rule_id": target.get("rule_id"),
        "source_row_no": target.get("source_row_no"),
        "business_rule": target.get("business_rule"),
        "original_corpus": changes.get("original_corpus"),
        "draft_corpus": str(changes.get("draft_corpus") or ""),
        "original_comment_prompt_bundle": changes.get("original_comment_prompt_bundle"),
        "draft_comment_prompt_bundle": changes.get("draft_comment_prompt_bundle"),
        "created_by": proposal.created_by,
        "applied_by": proposal.applied_by,
        "create_time": proposal.create_time,
        "update_time": proposal.update_time,
    }


def _forbidden_terms_from_change_request(request: AssetChangeRequest) -> list[str]:
    text = request.source_text or ""
    context = request.context_json or {}
    candidates = []
    candidates.extend(str(term) for term in context.get("detected_terms") or [])
    candidates.extend(re.findall(r"[A-Za-z][A-Za-z0-9]*(?:\s*[A-Za-z0-9]+)*\s*(?:蛋白|公司)?", text))
    terms: list[str] = []
    for candidate in candidates:
        normalized = re.sub(r"\s+", "", str(candidate or "")).strip("，。；、:：. ")
        if not normalized:
            continue
        lower = normalized.lower()
        if lower in {"a2", "a2蛋白", "a2公司"}:
            value = {"a2": "a2", "a2蛋白": "a2蛋白", "a2公司": "a2公司"}[lower]
            if value not in terms:
                terms.append(value)
    if terms:
        return terms
    if "a2" in text.lower():
        return ["a2", "a2蛋白", "a2公司"]
    return []


def _compliance_rule_from_change_request(request: AssetChangeRequest, forbidden_terms: list[str]) -> dict[str, Any]:
    text = request.source_text.strip()
    terms = forbidden_terms or ["见反馈"]
    return {
        "dimension": f"禁止错误关联或提及：{'、'.join(terms)}",
        "rule_type": "forbidden_product_fact",
        "risk_level": "high",
        "review_status": "pending",
        "forbidden_terms": terms,
        "feedback": text,
        "source": "content_batch_feedback",
        "source_request_id": request.id,
        "suggested_action": "命中后要求改写，删除错误事实或禁用卖点。",
    }


def _has_matching_rule(items: list[dict[str, Any]], rule: dict[str, Any]) -> bool:
    rule_terms = set(rule.get("forbidden_terms") or [])
    for item in items:
        if not isinstance(item, dict):
            continue
        item_terms = set(item.get("forbidden_terms") or [])
        if rule_terms and rule_terms <= item_terms:
            return True
        if item.get("dimension") == rule.get("dimension"):
            return True
    return False


def normalize_asset_content(asset_type: str, content: dict[str, Any]) -> dict[str, Any]:
    if asset_type != "painpoint_expression_candidates":
        return content
    return _normalize_painpoint_expression_candidates(content)


def _normalize_painpoint_expression_candidates(content: dict[str, Any]) -> dict[str, Any]:
    items = content.get("items") if isinstance(content, dict) else None
    if not isinstance(items, list):
        return content

    normalized_items = [dict(item) for item in items if isinstance(item, dict)]
    symptom_profiles = _build_symptom_profiles(normalized_items)
    symptom_offsets: dict[str, int] = {}
    for item in normalized_items:
        if _clean_text(item.get("symptom")):
            continue
        topic = _clean_text(item.get("topic") or item.get("painpoint"))
        expression = _clean_text(item.get("expression") or item.get("description"))
        symptom = _infer_symptom(topic, expression, symptom_profiles, symptom_offsets)
        if symptom:
            # 候选扩写必须挂回已有“具体表现”，否则运营看到的层级会退化成未归类描述。
            item["symptom"] = symptom
            item.setdefault("symptom_source", "auto_inferred")

    return {**content, "items": normalized_items}


def _build_symptom_profiles(items: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    profiles: dict[str, dict[str, list[str]]] = {}
    for item in items:
        topic = _clean_text(item.get("topic") or item.get("painpoint"))
        symptom = _clean_text(item.get("symptom"))
        if not topic or not symptom:
            continue
        profile = profiles.setdefault(topic, {}).setdefault(symptom, [symptom])
        for key in ("expression", "description"):
            value = _clean_text(item.get(key))
            if value:
                profile.append(value)
    return profiles


def _infer_symptom(
    topic: str | None,
    expression: str | None,
    profiles: dict[str, dict[str, list[str]]],
    offsets: dict[str, int],
) -> str | None:
    if not topic:
        return None
    topic_profiles = profiles.get(topic) or {}
    if not topic_profiles:
        return None
    if not expression:
        return _next_symptom(topic, topic_profiles, offsets)

    scores = [
        (_similarity_score(expression, profile_texts), symptom)
        for symptom, profile_texts in topic_profiles.items()
    ]
    scores.sort(reverse=True)
    if scores and scores[0][0] > 0:
        return scores[0][1]
    return _next_symptom(topic, topic_profiles, offsets)


def _next_symptom(topic: str, topic_profiles: dict[str, list[str]], offsets: dict[str, int]) -> str:
    symptoms = list(topic_profiles)
    offset = offsets.get(topic, 0)
    offsets[topic] = offset + 1
    return symptoms[offset % len(symptoms)]


def _similarity_score(expression: str, profile_texts: list[str]) -> float:
    expression_terms = _text_terms(expression)
    if not expression_terms:
        return 0
    best = 0.0
    for text in profile_texts:
        terms = _text_terms(text)
        if not terms:
            continue
        overlap = len(expression_terms & terms)
        if overlap == 0:
            continue
        best = max(best, overlap / len(expression_terms | terms))
    return best


def _text_terms(value: str) -> set[str]:
    text = re.sub(r"\s+", "", str(value or "").strip())
    if not text:
        return set()
    terms = set(re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", text))
    terms.update(text[index : index + 2] for index in range(max(len(text) - 1, 0)))
    return {term for term in terms if term.strip()}


def _clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _content_items(content: dict[str, Any]) -> list[dict[str, Any]]:
    items = content.get("items") if isinstance(content, dict) else None
    return [item for item in items or [] if isinstance(item, dict)]


def _asset_is_hidden(asset: AssetRegistry) -> bool:
    metadata = asset.metadata_json or {}
    content = asset.content_json or {}
    return bool(metadata.get("hidden") or content.get("hidden"))


def _painpoint_items(content: dict[str, Any]) -> list[dict[str, Any]]:
    topics = content.get("topics") if isinstance(content, dict) else None
    if isinstance(topics, list) and topics:
        return [item for item in topics if isinstance(item, dict)]
    return _content_items(content)


def _add_option(options: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in options:
        options.append(text)


def _add_split_options(options: list[str], value: Any) -> None:
    for item in str(value or "").replace("、", "/").split("/"):
        _add_option(options, item)


def _default_target_audiences(asset_key: str | None) -> list[str]:
    if asset_key == "yuanyue":
        return ["新手妈妈", "转奶期宝宝家长", "敏感宝宝家长", "奶量焦虑宝宝家长"]
    return ["新手妈妈"]


def _default_content_styles() -> list[str]:
    return [
        "经验复盘",
        "情绪共情",
        "口语分享",
        "清单型",
        "避坑提醒",
        "专业解释",
        "场景共鸣",
        "轻种草",
    ]
