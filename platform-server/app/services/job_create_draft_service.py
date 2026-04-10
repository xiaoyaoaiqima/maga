"""
JobCreateDraft service - 草稿创建/更新/校验/编译/创建 Job
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.logger import logger
from app.models.job_create_draft import JobCreateDraft
from app.models.job import Job
from app.models.expert_config import ExpertConfig
from app.models.plugin import Plugin
from app.schemas.job import JobCreate
from app.schemas.job_create_draft import (
    DraftValidationIssue,
    DraftValidationResult,
    JobCreateDraftCreate,
    JobCreateDraftMode,
    JobCreateDraftPatch,
)
from app.services.job_service import JobService
from app.utils.strategy_helper import (
    fetch_strategy_combinations,
    build_expert_param_config_from_combo,
    extract_strategy_combo_summary,
)


def _now_str() -> str:
    # 业务侧不做时区转换：这里仅用于草稿 versions 的可读时间
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _deep_merge_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge patch into base (dict only)."""
    merged: Dict[str, Any] = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge_dict(merged[k], v)  # type: ignore[arg-type]
        else:
            merged[k] = v
    return merged


def _allocate_counts(total_count: int, weights: List[float]) -> List[int]:
    """
    将 weights 分配为整数 counts，保证 sum(counts) == total_count。
    使用“最大余数法”。
    """
    if total_count < 0:
        raise ValueError("total_count 不能为负数")
    if total_count == 0:
        return [0 for _ in weights]

    w_sum = sum(weights)
    if w_sum <= 0:
        raise ValueError("权重/占比总和必须大于 0")

    normalized = [w / w_sum for w in weights]
    raw = [total_count * w for w in normalized]
    floors = [int(x) for x in raw]
    remain = total_count - sum(floors)
    remainders = [(raw[i] - floors[i], i) for i in range(len(weights))]
    remainders.sort(key=lambda x: x[0], reverse=True)
    for j in range(remain):
        floors[remainders[j][1]] += 1
    return floors


class JobCreateDraftService:
    """JobCreateDraft service"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, draft_id: str) -> Optional[JobCreateDraft]:
        stmt = select(JobCreateDraft).where(
            and_(JobCreateDraft.draft_id == draft_id, JobCreateDraft.is_deleted == 0)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: JobCreateDraftCreate) -> JobCreateDraft:
        draft_id = f"draft-{uuid.uuid4().hex[:16]}"
        created_by = data.created_by

        draft_json = data.draft_json or {
            "mode": data.mode,
            "total_count": 0,
            "items": [],
            "rules": [],
            "versions": [{"time": _now_str(), "by": created_by, "note": "create"}],
        }

        # 兜底：确保 mode 与顶层字段一致
        draft_json = dict(draft_json)
        draft_json["mode"] = data.mode

        draft = JobCreateDraft(
            draft_id=draft_id,
            tenant_id=data.tenant_id,
            mode=data.mode,
            draft_json=draft_json,
            remark=data.remark,
            created_by=created_by,
            updated_by=created_by,
        )
        self.db.add(draft)
        await self.db.commit()
        await self.db.refresh(draft)
        return draft

    async def patch(self, draft_id: str, patch_req: JobCreateDraftPatch) -> JobCreateDraft:
        draft = await self.get(draft_id)
        if not draft:
            raise ValueError("草稿不存在")

        draft_json = draft.draft_json or {}
        merged = _deep_merge_dict(draft_json, patch_req.patch)

        # mode 允许通过 patch 更新，但需要同步到列
        mode = merged.get("mode")
        if mode:
            draft.mode = mode

        versions = merged.get("versions")
        if not isinstance(versions, list):
            versions = []
        versions.append(
            {
                "time": _now_str(),
                "by": patch_req.updated_by,
                "note": patch_req.note or "patch",
            }
        )
        merged["versions"] = versions

        draft.draft_json = merged
        draft.updated_by = patch_req.updated_by

        # 草稿变更后，编译/校验结果作废
        draft.validation_json = None
        draft.compiled_json = None

        flag_modified(draft, "draft_json")
        flag_modified(draft, "validation_json")
        flag_modified(draft, "compiled_json")

        await self.db.commit()
        await self.db.refresh(draft)
        return draft

    def _validate_payload(self, mode: JobCreateDraftMode, payload: Dict[str, Any]) -> DraftValidationResult:
        errors: List[DraftValidationIssue] = []
        warnings: List[DraftValidationIssue] = []
        auto_fixes: List[Dict[str, Any]] = []

        # 基础字段
        total_count = payload.get("total_count")
        if not isinstance(total_count, int) or total_count < 0:
            errors.append(
                DraftValidationIssue(
                    code="draft.total_count.invalid",
                    message="total_count 必须为非负整数",
                    path="total_count",
                    level="error",
                )
            )
            total_count = 0

        # mode 一致性
        if payload.get("mode") and payload.get("mode") != mode:
            warnings.append(
                DraftValidationIssue(
                    code="draft.mode.mismatch",
                    message="draft_json.mode 与 draft.mode 不一致，已以 draft.mode 为准",
                    path="mode",
                    level="warning",
                )
            )
            auto_fixes.append({"op": "set", "path": "mode", "value": mode})

        items = payload.get("items", [])
        rules = payload.get("rules", [])
        if mode in ("explicit_combinations", "variants"):
            if not isinstance(items, list):
                errors.append(
                    DraftValidationIssue(
                        code="draft.items.invalid",
                        message="items 必须为数组",
                        path="items",
                        level="error",
                    )
                )
                items = []
            if len(items) == 0:
                warnings.append(
                    DraftValidationIssue(
                        code="draft.items.empty",
                        message="items 为空：当前草稿无法编译出有效分配",
                        path="items",
                        level="warning",
                    )
                )

            # ratio/count 校验
            has_ratio = any(isinstance(i, dict) and i.get("ratio") is not None for i in items)
            has_count = any(isinstance(i, dict) and i.get("count") is not None for i in items)
            if has_ratio and has_count:
                errors.append(
                    DraftValidationIssue(
                        code="draft.items.mixed_allocation",
                        message="items 不允许同时使用 ratio 和 count",
                        path="items",
                        level="error",
                    )
                )

            if has_ratio and not has_count:
                ratios: List[float] = []
                for idx, i in enumerate(items):
                    if not isinstance(i, dict):
                        errors.append(
                            DraftValidationIssue(
                                code="draft.items.item.invalid",
                                message="items 元素必须为对象",
                                path=f"items[{idx}]",
                                level="error",
                            )
                        )
                        continue
                    r = i.get("ratio")
                    if not isinstance(r, (int, float)) or r < 0:
                        errors.append(
                            DraftValidationIssue(
                                code="draft.items.ratio.invalid",
                                message="ratio 必须为非负数字",
                                path=f"items[{idx}].ratio",
                                level="error",
                            )
                        )
                        continue
                    ratios.append(float(r))

                if ratios:
                    r_sum = sum(ratios)
                    if r_sum <= 0:
                        errors.append(
                            DraftValidationIssue(
                                code="draft.items.ratio.sum_zero",
                                message="ratio 总和必须大于 0",
                                path="items",
                                level="error",
                            )
                        )
                    # 允许不等于 100：编译时会归一化
                    if abs(r_sum - 100.0) > 1e-6 and r_sum > 0:
                        warnings.append(
                            DraftValidationIssue(
                                code="draft.items.ratio.sum_not_100",
                                message="ratio 总和不等于 100，将在编译时按权重归一化",
                                path="items",
                                level="warning",
                            )
                        )
                        auto_fixes.append({"op": "normalize_ratio", "path": "items[*].ratio"})

            if has_count and not has_ratio:
                counts: List[int] = []
                for idx, i in enumerate(items):
                    if not isinstance(i, dict):
                        continue
                    c = i.get("count")
                    if not isinstance(c, int) or c < 0:
                        errors.append(
                            DraftValidationIssue(
                                code="draft.items.count.invalid",
                                message="count 必须为非负整数",
                                path=f"items[{idx}].count",
                                level="error",
                            )
                        )
                        continue
                    counts.append(c)
                if counts and sum(counts) != total_count:
                    errors.append(
                        DraftValidationIssue(
                            code="draft.items.count.sum_mismatch",
                            message="items.count 总和必须等于 total_count",
                            path="items",
                            level="error",
                        )
                    )

        if mode == "allocation_rules":
            if not isinstance(rules, list):
                errors.append(
                    DraftValidationIssue(
                        code="draft.rules.invalid",
                        message="rules 必须为数组",
                        path="rules",
                        level="error",
                    )
                )
                rules = []
            if len(rules) == 0:
                warnings.append(
                    DraftValidationIssue(
                        code="draft.rules.empty",
                        message="rules 为空：当前草稿无法编译出有效分配",
                        path="rules",
                        level="warning",
                    )
                )
            ratios: List[float] = []
            for idx, r in enumerate(rules):
                if not isinstance(r, dict):
                    errors.append(
                        DraftValidationIssue(
                            code="draft.rules.rule.invalid",
                            message="rules 元素必须为对象",
                            path=f"rules[{idx}]",
                            level="error",
                        )
                    )
                    continue
                ratio = r.get("ratio")
                if not isinstance(ratio, (int, float)) or ratio < 0:
                    errors.append(
                        DraftValidationIssue(
                            code="draft.rules.ratio.invalid",
                            message="rules[*].ratio 必须为非负数字",
                            path=f"rules[{idx}].ratio",
                            level="error",
                        )
                    )
                    continue
                ratios.append(float(ratio))
            if ratios:
                r_sum = sum(ratios)
                if r_sum <= 0:
                    errors.append(
                        DraftValidationIssue(
                            code="draft.rules.ratio.sum_zero",
                            message="rules.ratio 总和必须大于 0",
                            path="rules",
                            level="error",
                        )
                    )
                if abs(r_sum - 100.0) > 1e-6 and r_sum > 0:
                    warnings.append(
                        DraftValidationIssue(
                            code="draft.rules.ratio.sum_not_100",
                            message="rules.ratio 总和不等于 100，将在编译时按权重归一化",
                            path="rules",
                            level="warning",
                        )
                    )
                    auto_fixes.append({"op": "normalize_ratio", "path": "rules[*].ratio"})

        is_valid = len([e for e in errors if e.level == "error"]) == 0
        return DraftValidationResult(is_valid=is_valid, errors=errors, warnings=warnings, auto_fixes=auto_fixes)

    async def validate(self, draft_id: str) -> DraftValidationResult:
        draft = await self.get(draft_id)
        if not draft:
            raise ValueError("草稿不存在")

        payload = draft.draft_json or {}
        mode: JobCreateDraftMode = draft.mode  # type: ignore[assignment]

        result = self._validate_payload(mode=mode, payload=payload)
        draft.validation_json = result.model_dump()
        flag_modified(draft, "validation_json")
        await self.db.commit()
        await self.db.refresh(draft)
        return result

    def _compile_items_plan(self, mode: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        total_count = int(payload.get("total_count", 0) or 0)
        items = payload.get("items", []) or []
        if not isinstance(items, list):
            raise ValueError("items 必须为数组")

        has_ratio = any(isinstance(i, dict) and i.get("ratio") is not None for i in items)
        has_count = any(isinstance(i, dict) and i.get("count") is not None for i in items)
        if has_ratio and has_count:
            raise ValueError("items 不允许同时使用 ratio 和 count")

        plan_items: List[Dict[str, Any]] = []
        if has_ratio:
            ratios: List[float] = []
            for i in items:
                if not isinstance(i, dict):
                    raise ValueError("items 元素必须为对象")
                r = i.get("ratio")
                if not isinstance(r, (int, float)):
                    raise ValueError("ratio 必须为数字")
                ratios.append(float(r))
            counts = _allocate_counts(total_count=total_count, weights=ratios)
            for idx, i in enumerate(items):
                plan_items.append(
                    {
                        "type": "item",
                        "index": idx,
                        "item_id": i.get("item_id"),
                        "name": i.get("name"),
                        "ratio": i.get("ratio"),
                        "count": counts[idx],
                        # 预留：执行器后续读取
                        "expert_param_config": i.get("expert_param_config"),
                        "variant_ref": i.get("variant_ref"),
                        "overrides": i.get("overrides"),
                    }
                )
        elif has_count:
            counts: List[int] = []
            for i in items:
                if not isinstance(i, dict):
                    raise ValueError("items 元素必须为对象")
                c = i.get("count")
                if not isinstance(c, int):
                    raise ValueError("count 必须为整数")
                counts.append(c)
            if sum(counts) != total_count:
                raise ValueError("items.count 总和必须等于 total_count")
            for idx, i in enumerate(items):
                plan_items.append(
                    {
                        "type": "item",
                        "index": idx,
                        "item_id": i.get("item_id"),
                        "name": i.get("name"),
                        "ratio": i.get("ratio"),
                        "count": i.get("count"),
                        "expert_param_config": i.get("expert_param_config"),
                        "variant_ref": i.get("variant_ref"),
                        "overrides": i.get("overrides"),
                    }
                )
        else:
            # 没有分配信息：默认全部 0（仅用于预览）
            for idx, i in enumerate(items):
                if not isinstance(i, dict):
                    continue
                plan_items.append(
                    {
                        "type": "item",
                        "index": idx,
                        "item_id": i.get("item_id"),
                        "name": i.get("name"),
                        "count": 0,
                        "expert_param_config": i.get("expert_param_config"),
                        "variant_ref": i.get("variant_ref"),
                        "overrides": i.get("overrides"),
                    }
                )

        return {
            "mode": mode,
            "total_count": total_count,
            "plan_items": plan_items,
        }

    def _compile_rules_plan(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        total_count = int(payload.get("total_count", 0) or 0)
        rules = payload.get("rules", []) or []
        if not isinstance(rules, list):
            raise ValueError("rules 必须为数组")

        ratios: List[float] = []
        for r in rules:
            if not isinstance(r, dict):
                raise ValueError("rules 元素必须为对象")
            ratio = r.get("ratio")
            if not isinstance(ratio, (int, float)):
                raise ValueError("rules[*].ratio 必须为数字")
            ratios.append(float(ratio))

        counts = _allocate_counts(total_count=total_count, weights=ratios) if ratios else []
        plan_items: List[Dict[str, Any]] = []
        for idx, r in enumerate(rules):
            plan_items.append(
                {
                    "type": "rule",
                    "index": idx,
                    "priority": r.get("priority"),
                    "condition": r.get("condition"),
                    "ratio": r.get("ratio"),
                    "count": counts[idx] if idx < len(counts) else 0,
                    "name": r.get("name"),
                }
            )

        return {
            "mode": "allocation_rules",
            "total_count": total_count,
            "plan_items": plan_items,
        }

    async def _compile_strategy_v3_plan(self, payload: Dict[str, Any], tenant_code: str = "default") -> Dict[str, Any]:
        """
        编译 strategy_v3 模式草稿（多策略维度合并）

        payload 结构:
        {
            "mode": "strategy_v3",
            "strategy_selections": [
                {"strategy_id": "1", "selected_combo_ids": ["combo_0"]},
                {"strategy_id": "2", "selected_combo_ids": ["combo_0", "combo_1"]}
            ],
            "merged_allocations": {
                "merged_s1combo_0_s2combo_0": 2,
                "merged_s1combo_0_s2combo_1": 1
            },
            "variable_share_mapping": {...},
            "expert_config_code_list": [...]
        }
        """
        strategy_selections = payload.get("strategy_selections", [])
        if not strategy_selections:
            raise ValueError("strategy_v3 模式必须指定 strategy_selections")

        merged_allocations = payload.get("merged_allocations", {})
        variable_share_mapping = payload.get("variable_share_mapping", {})
        expert_config_code_list = payload.get("expert_config_code_list", [])

        # 查询所有 ExpertConfig 及其关联的 Plugin 信息（支持 plugin strategy_id 绑定模式）
        expert_plugin_config_map: Dict[str, List[Dict[str, Any]]] = {}
        if expert_config_code_list:
            try:
                # 查询 ExpertConfig
                stmt = select(ExpertConfig).where(
                    and_(
                        ExpertConfig.expert_config_code.in_(expert_config_code_list),
                        ExpertConfig.is_deleted == 0
                    )
                )
                result = await self.db.execute(stmt)
                expert_configs = result.scalars().all()

                # 收集所有需要查询的 plugin_code
                all_plugin_codes: set[str] = set()
                for ec in expert_configs:
                    if ec.plugin_config:
                        for plugin_item in ec.plugin_config:
                            plugin_code = plugin_item.get("plugin_code")
                            if plugin_code:
                                all_plugin_codes.add(plugin_code)

                # 批量查询 Plugin 表获取 strategy_id 和 variable_mappings
                plugin_map: Dict[str, Plugin] = {}
                if all_plugin_codes:
                    plugin_stmt = select(Plugin).where(
                        and_(
                            Plugin.plugin_code.in_(list(all_plugin_codes)),
                            Plugin.is_deleted == 0,
                        )
                    )
                    plugin_result = await self.db.execute(plugin_stmt)
                    for plugin in plugin_result.scalars().all():
                        plugin_map[plugin.plugin_code] = plugin

                # 合并 ExpertConfig.plugin_config 和 Plugin.strategy_id/variable_mappings
                for ec in expert_configs:
                    if ec.plugin_config:
                        enhanced_plugin_config = []
                        for plugin_item in ec.plugin_config:
                            plugin_code = plugin_item.get("plugin_code")
                            if not plugin_code:
                                continue

                            # 复制原始配置
                            enhanced_item = dict(plugin_item)

                            # 从 Plugin 表补充 strategy_id 和 variable_mappings
                            plugin = plugin_map.get(plugin_code)
                            if plugin:
                                if plugin.strategy_id:
                                    enhanced_item["strategy_id"] = plugin.strategy_id
                                if plugin.variable_mappings:
                                    enhanced_item["variable_mappings"] = plugin.variable_mappings

                            enhanced_plugin_config.append(enhanced_item)

                        expert_plugin_config_map[ec.expert_config_code] = enhanced_plugin_config

            except Exception as e:
                logger.warning(f"[Strategy V3 Compile] 查询 ExpertConfig/Plugin 失败: {e}")

        # 1. 调用 keyword-corpus 服务获取合并组合
        logger.info(f"[Strategy V3 Compile] 获取多策略合并组合: selections={strategy_selections}")

        # ⭐ 从 payload 中提取采样模式参数
        sample_mode = payload.get("sample_mode", "first")
        primary_strategy_id = payload.get("primary_strategy_id")
        total_count = int(payload.get("total_count", 20) or 20)

        try:
            from app.utils.strategy_helper import fetch_merged_strategy_combinations

            merge_result = await fetch_merged_strategy_combinations(
                strategy_selections=strategy_selections,
                tenant_code=tenant_code,
                include_corpus=False,  # 不返回语料内容，减少响应体积
                sample_mode=sample_mode,
                primary_strategy_id=primary_strategy_id,
                target_count=total_count,
            )
        except Exception as e:
            logger.error(f"[Strategy V3 Compile] 获取合并组合失败: {e}")
            raise ValueError(f"获取多策略合并组合失败: {e}")

        merged_combinations = merge_result.get("merged_combinations", [])
        if not merged_combinations:
            raise ValueError("未生成任何合并组合，请检查策略配置")

        logger.info(f"[Strategy V3 Compile] 获取到 {len(merged_combinations)} 个合并组合")

        # 2. 构建 combo_id -> combo 映射
        combo_map = {c.get("id"): c for c in merged_combinations}

        # 3. 根据 merged_allocations 生成 plan_items
        plan_items: List[Dict[str, Any]] = []
        plan_idx = 0

        # ⭐ 动态采样模式（primary_strategy 或 random）下，忽略 merged_allocations
        # 后端已根据采样模式生成了组合，前端保存的分配数据不再适用
        if sample_mode in ["primary_strategy", "random"] or not merged_allocations:
            # 动态采样模式：每个组合生成 1 篇（组合数量和内容由后端控制）
            merged_allocations = {c["id"]: 1 for c in merged_combinations}
            logger.info(
                f"[Strategy V3 Compile] {sample_mode} 模式：使用后端生成的 {len(merged_combinations)} 个组合，"
                f"忽略前端分配数据"
            )

        for combo_id, count in merged_allocations.items():
            if not isinstance(count, int) or count <= 0:
                continue

            combo = combo_map.get(combo_id)
            if not combo:
                logger.warning(f"[Strategy V3 Compile] 合并组合 {combo_id} 不存在")
                continue

            # 为每个分配的篇数生成一个 plan_item
            for _ in range(count):
                merged_nodes = combo.get("merged_nodes", {})

                # 从 merged_nodes 构建 expert_param_config
                expert_param_config = self._build_expert_param_config_from_merged_nodes(
                    merged_nodes=merged_nodes,
                    variable_share_mapping=variable_share_mapping,
                    expert_config_code_list=expert_config_code_list,
                    expert_plugin_config_map=expert_plugin_config_map,
                )

                # 提取策略组合摘要
                strategy_combo = {}
                for dim, node_info in combo.get("merged_nodes", {}).items():
                    if isinstance(node_info, dict):
                        strategy_combo[dim] = {
                            "node_id": node_info.get("id"),
                            "node_name": node_info.get("name"),
                        }

                plan_items.append({
                    "type": "strategy_v3",
                    "index": plan_idx,
                    "merged_combo_id": combo_id,
                    "name": combo.get("name", f"合并组合 {combo_id}"),
                    "source_combos": combo.get("source_combos", []),
                    "strategy_combo": strategy_combo,
                    "expert_param_config": expert_param_config,
                })
                plan_idx += 1
        if not plan_items:
            raise ValueError("未生成任何 plan_item，请检查合并分配配置")

        logger.info(f"[Strategy V3 Compile] 共生成 {len(plan_items)} 个 plan_items")

        # ✅ 优化：只存储配置，不存储 plan_items（执行时动态生成）
        # 这解决了大组合数导致 job_generation_plan 过大的问题
        return {
            "mode": "strategy_v3",
            "strategy_selections": merge_result.get("source_strategies"),
            "sample_mode": payload.get("sample_mode", "first"),
            "primary_strategy_id": payload.get("primary_strategy_id"),
            "target_count": payload.get("total_count", len(plan_items)),
            "variable_share_mapping": variable_share_mapping,
            # ⚠️ 不再存储 plan_items, merged_dimensions, merged_allocations, source_strategies
            # 执行时会通过 fetch_merged_strategy_combinations 动态生成
            # expert_config_code_list 从 job.expert_config_code_list 获取
        }

    def _build_expert_param_config_from_merged_nodes(
        self,
        merged_nodes: Dict[str, Any],
        variable_share_mapping: Dict[str, Any],
        expert_config_code_list: List[str],
        expert_plugin_config_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """
        从合并节点构建 expert_param_config

        与 build_expert_param_config_from_combo 类似，但输入是 merged_nodes
        """
        # 复用现有的构建逻辑
        # merged_nodes 格式: {"人设": {...node_info...}, "场景": {...}, "卖点": {...}}
        # 需要转换为 combo 格式: {"nodes": {...}}
        combo = {"nodes": merged_nodes}

        return build_expert_param_config_from_combo(
            combo=combo,
            variable_share_mapping=variable_share_mapping,
            expert_config_code_list=expert_config_code_list,
            expert_plugin_config_map=expert_plugin_config_map,
        )

    async def compile(self, draft_id: str) -> Dict[str, Any]:
        draft = await self.get(draft_id)
        if not draft:
            raise ValueError("草稿不存在")

        validation = await self.validate(draft_id)
        if not validation.is_valid:
            raise ValueError("草稿未通过校验，无法编译")

        payload = draft.draft_json or {}
        mode: str = draft.mode

        # 获取 tenant_code（用于策略模式调用 keyword-corpus）
        tenant_code = "default"
        if draft.tenant_id:
            from app.models.tenant import Tenant
            from sqlalchemy import select
            result = await self.db.execute(
                select(Tenant.tenant_code).where(Tenant.id == draft.tenant_id, Tenant.is_deleted == 0)
            )
            row = result.scalar_one_or_none()
            if row:
                tenant_code = row

        if mode in ("explicit_combinations", "variants", "ai"):
            compiled = self._compile_items_plan(mode=mode, payload=payload)
        elif mode == "allocation_rules":
            compiled = self._compile_rules_plan(payload=payload)
        elif mode == "strategy_v3":
            compiled = await self._compile_strategy_v3_plan(payload=payload, tenant_code=tenant_code)
        else:
            raise ValueError(f"不支持的 mode: {mode}")

        draft.compiled_json = compiled
        flag_modified(draft, "compiled_json")
        await self.db.commit()
        await self.db.refresh(draft)
        return compiled

    async def create_job(self, draft_id: str) -> Job:
        """
        从草稿创建 Job。

        Returns:
            创建的 Job
        """
        draft = await self.get(draft_id)
        if not draft:
            raise ValueError("草稿不存在")

        # 必须 validated + compiled
        if not draft.validation_json or not bool(draft.validation_json.get("is_valid")):
            raise ValueError("草稿未通过校验，请先调用 validate")
        if not draft.compiled_json:
            raise ValueError("草稿未编译，请先调用 compile")

        # ⭐ 自动检测并重新编译旧格式的 compiled_json（包含 plan_items）
        # 这确保即使 Draft 在代码部署前编译，也能使用新的轻量级格式
        compiled_json = draft.compiled_json or {}
        if compiled_json.get("mode") == "strategy_v3" and "plan_items" in compiled_json:
            logger.info(
                f"[create_job] 检测到旧格式 compiled_json（包含 plan_items），"
                f"自动重新编译以使用轻量级格式"
            )
            await self.compile(draft.draft_id)
            await self.db.refresh(draft)
            compiled_json = draft.compiled_json or {}

        payload = draft.draft_json or {}
        job_name = payload.get("job_name")
        if not isinstance(job_name, str) or not job_name.strip():
            raise ValueError("草稿缺少 job_name")

        job_payload: Dict[str, Any] = {
            "job_name": job_name.strip(),
            "tenant_id": payload.get("tenant_id", draft.tenant_id),
            "activity_id": payload.get("activity_id"),
            "agent_code": payload.get("agent_code"),
            "description": payload.get("description"),
            "article_count": payload.get("total_count"),
            "expert_config_code_list": payload.get("expert_config_code_list") or [],
            "zero_score_invalid_expert_codes": payload.get("zero_score_invalid_expert_codes"),
            # Draft 编译产物落到 Job.job_generation_plan（使用可能重新编译后的版本）
            "job_generation_plan": compiled_json,
        }

        job_service = JobService(self.db)
        job = await job_service.create(JobCreate(**job_payload))

        # 回写草稿编译产物，便于审计/回溯
        try:
            compiled = dict(draft.compiled_json or {})
            compiled["job_id"] = job.job_id
            draft.compiled_json = compiled
            flag_modified(draft, "compiled_json")
            await self.db.commit()
            await self.db.refresh(draft)
        except Exception as e:
            logger.warning(f"回写 draft.compiled_json.job_id 失败: {e}")

        return job



