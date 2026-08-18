"""Compile MAGA article-rule assets into a system-neutral node graph."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from typing import Any

from app.models.maga_assets import AssetRegistry
from app.schemas.assets import AssetNodeGraphResponse
from app.services.business_rule_asset_types import ARTICLE_BUSINESS_RULE_ASSET_TYPES


NODE_GRAPH_SCHEMA_VERSION = "maga-node-graph/v1"
RAAP_BLUEPRINT_SCHEMA_VERSION = "raap-keyword-strategy-blueprint/v1"


class _Graph:
    def __init__(self) -> None:
        self.nodes: list[dict[str, Any]] = []
        self.node_by_key: dict[str, dict[str, Any]] = {}
        self.relations: list[dict[str, Any]] = []

    def add_node(
        self,
        *,
        node_key: str,
        node_type: str,
        name: str,
        text: str = "",
        source_ref: dict[str, Any] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        if node_key in self.node_by_key:
            raise ValueError(f"duplicate node key: {node_key}")
        normalized_text = str(text or "").strip()
        corpus_items = (
            [
                {
                    "item_key": f"{node_key}:corpus:1",
                    "text": normalized_text,
                    "weight": 1.0,
                    "source_ref": source_ref or {},
                }
            ]
            if normalized_text
            else []
        )
        node = {
            "node_key": node_key,
            "node_type": node_type,
            "name": str(name or node_key).strip(),
            "corpus_items": corpus_items,
            "properties": properties or {},
        }
        self.nodes.append(node)
        self.node_by_key[node_key] = node
        return node_key

    def relate(
        self,
        relation_type: str,
        source_node_key: str,
        target_node_key: str,
        **properties: Any,
    ) -> None:
        self.relations.append(
            {
                "relation_type": relation_type,
                "source_node_key": source_node_key,
                "target_node_key": target_node_key,
                "properties": properties,
            }
        )


def compile_article_business_rule_node_graph(
    asset: AssetRegistry,
) -> AssetNodeGraphResponse:
    """Convert one immutable article-rule version to Node + Relation + Strategy."""
    if asset.asset_type not in ARTICLE_BUSINESS_RULE_ASSET_TYPES:
        raise ValueError("asset is not an article business rule set")

    content = asset.content_json or {}
    rules = [item for item in content.get("items") or [] if isinstance(item, dict)]
    if not rules:
        raise ValueError("article business rule set is empty")
    if any(rule.get("variation_slots") for rule in rules):
        raise ValueError("node graph v1 only supports asset-level variation slots")
    if any((rule.get("examples") or rule.get("supplements")) for rule in rules):
        raise ValueError("node graph v1 does not yet support rule-level examples")

    root_key = f"asset:{asset.asset_key}@v{asset.version_no}"
    graph = _Graph()
    graph.add_node(
        node_key=root_key,
        node_type="asset",
        name=asset.display_name or asset.asset_key,
        properties={
            "asset_type": asset.asset_type,
            "asset_key": asset.asset_key,
            "version_no": asset.version_no,
            "asset_stage": asset.asset_stage,
        },
    )

    bindings: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    combinations: list[dict[str, Any]] = []
    group_sizes: list[int] = []
    fixed_nodes = _add_fixed_nodes(graph, asset, content, root_key, bindings)

    expression_index, expression_count = _add_expression_nodes(
        graph,
        content,
        root_key,
    )
    rule_candidates = _add_rule_nodes(
        graph,
        rules,
        root_key,
        expression_index,
    )
    combinations.extend(rule_candidates)
    group_sizes.append(len(rule_candidates))
    steps.append(_selection_step("business_rule", root_key, "candidate_rule"))
    bindings.append(_binding("business_rule", "MAGA内容方向", "内容方向", 20))

    has_expression_dimension = "selling_expression" in rule_candidates[0]["nodes"]
    if has_expression_dimension:
        steps.append(
            _selection_step(
                "selling_expression",
                None,
                "allowed_expression",
                from_dimension="business_rule",
            )
        )
        bindings.append(
            _binding("selling_expression", "MAGA卖点痛点表达", "本篇素材", 30)
        )

    for slot_index, slot in enumerate(_dict_list(content.get("variation_slots")), start=1):
        slot_candidates, dimension_key, slot_name = _add_slot_nodes(
            graph,
            root_key,
            slot,
            slot_index,
        )
        combinations.extend(slot_candidates)
        group_sizes.append(len(slot_candidates))
        steps.append(
            _selection_step(
                dimension_key,
                root_key,
                f"slot_candidate:{slot.get('slot_code') or slot.get('code') or slot_index}",
            )
        )
        bindings.append(
            _binding(dimension_key, f"MAGA{slot_name}", "本篇素材", 40 + slot_index)
        )

    if fixed_nodes:
        combinations.append(
            {
                "id": _stable_id("fixed", *[fixed_nodes[key] for key in sorted(fixed_nodes)]),
                "name": "MAGA 固定生成约束",
                "nodes": fixed_nodes,
                "group_id": "fixed_requirements",
            }
        )
        group_sizes.append(1)
        for dimension, node_key in fixed_nodes.items():
            steps.append(
                {
                    "dimension_key": dimension,
                    "selection_mode": "select_fixed",
                    "source_node_key": node_key,
                    "from_dimension": None,
                    "relation_type": "requires",
                }
            )

    content_hash = _json_hash(content)
    release_id = f"maga:{asset.asset_key}:v{asset.version_no}:{content_hash[:12]}"
    logical_count = math.prod(group_sizes)
    raap_export = {
        "schema_version": RAAP_BLUEPRINT_SCHEMA_VERSION,
        "node_ref_kind": "maga_node_key",
        "strategy_blueprint": {
            "strategy_name": f"{asset.display_name or asset.asset_key} v{asset.version_no}",
            "description": f"Compiled from MAGA release {release_id}",
            "dimension_contract": sorted(
                bindings,
                key=lambda item: (item["order"], item["dimension_key"]),
            ),
            "combinations": combinations,
            "logical_combination_count": logical_count,
        },
    }
    graph_core = {
        "schema_version": NODE_GRAPH_SCHEMA_VERSION,
        "source": {
            "asset_id": asset.id,
            "asset_type": asset.asset_type,
            "asset_key": asset.asset_key,
            "version_no": asset.version_no,
            "content_hash": content_hash,
        },
        "nodes": graph.nodes,
        "relations": graph.relations,
        "selection_strategy": steps,
        "render_bindings": bindings,
        "raap_export": raap_export,
    }
    manifest = {
        "release_id": release_id,
        "source_system": "MAGA",
        "asset_id": asset.id,
        "asset_type": asset.asset_type,
        "asset_key": asset.asset_key,
        "asset_version": asset.version_no,
        "asset_stage": asset.asset_stage,
        "source_hash": asset.source_hash or content_hash,
        "content_hash": content_hash,
        "bundle_hash": _json_hash(graph_core),
        "node_count": len(graph.nodes),
        "relation_count": len(graph.relations),
        "rule_count": len(rules),
        "expression_count": expression_count,
        "logical_combination_count": logical_count,
    }
    return AssetNodeGraphResponse(
        schema_version=NODE_GRAPH_SCHEMA_VERSION,
        manifest=manifest,
        nodes=graph.nodes,
        relations=graph.relations,
        selection_strategy=steps,
        render_bindings=bindings,
        raap_export=raap_export,
    )


def _add_fixed_nodes(
    graph: _Graph,
    asset: AssetRegistry,
    content: dict[str, Any],
    root_key: str,
    bindings: list[dict[str, Any]],
) -> dict[str, str]:
    specs = [
        ("generation_instruction", "生文指令", str(content.get("generation_instruction") or ""), 10),
        ("writing_requirements", "写法", _bullet_text(content.get("writing_requirements")), 90),
        (
            "generation_requirements",
            "生成要求",
            _bullet_text(
                [
                    *_string_list(content.get("generation_requirements")),
                    *_string_list(content.get("hard_boundaries")),
                ]
            ),
            100,
        ),
    ]
    result: dict[str, str] = {}
    for dimension, name, text, order in specs:
        if not str(text).strip():
            continue
        node_key = graph.add_node(
            node_key=f"{root_key}:{dimension}",
            node_type=dimension,
            name=name,
            text=text,
            source_ref={"asset_field": dimension},
        )
        graph.relate("requires", root_key, node_key)
        result[dimension] = node_key
        bindings.append(_binding(dimension, f"MAGA{name}", name, order))
    return result


def _add_expression_nodes(
    graph: _Graph,
    content: dict[str, Any],
    root_key: str,
) -> tuple[dict[str, list[tuple[dict[str, Any], str]]], int]:
    index: dict[str, list[tuple[dict[str, Any], str]]] = defaultdict(list)
    expressions = [
        item
        for item in content.get("selling_painpoint_expressions") or []
        if isinstance(item, dict) and str(item.get("expression") or "").strip()
    ]
    for position, expression in enumerate(expressions, start=1):
        group = str(expression.get("selling_painpoint_group") or "").strip()
        if not group:
            raise ValueError(f"selling expression {position} has no group")
        source_row_no = expression.get("source_row_no") or position
        node_key = graph.add_node(
            node_key=f"{root_key}:selling_expression:{source_row_no}:{position}",
            node_type="selling_expression",
            name=f"卖点痛点表达 {source_row_no}",
            text=str(expression.get("expression") or ""),
            source_ref={"source_row_no": source_row_no},
            properties={
                "selling_painpoint_group": group,
                "source_row_no": source_row_no,
                "applicable_post_types": _string_list(expression.get("applicable_post_types")),
            },
        )
        graph.relate("contains", root_key, node_key)
        index[group].append((expression, node_key))
    return index, len(expressions)


def _add_rule_nodes(
    graph: _Graph,
    rules: list[dict[str, Any]],
    root_key: str,
    expression_index: dict[str, list[tuple[dict[str, Any], str]]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    expression_modes: set[bool] = set()
    for position, rule in enumerate(rules, start=1):
        rule_id = str(rule.get("rule_id") or f"rule_{position:03d}").strip()
        rule_name = str(rule.get("business_rule") or rule.get("post_type") or rule_id).strip()
        direction = str(rule.get("content_direction") or rule.get("corpus") or "").strip()
        if not direction:
            raise ValueError(f"business rule {rule_id} has no content direction")
        group = str(rule.get("selling_painpoint_group") or "").strip()
        source_row_no = rule.get("source_row_no") or position
        rule_key = graph.add_node(
            node_key=f"{root_key}:business_rule:{rule_id}",
            node_type="business_rule",
            name=rule_name,
            text=direction,
            source_ref={"rule_id": rule_id, "source_row_no": source_row_no},
            properties={
                "rule_id": rule_id,
                "source_row_no": source_row_no,
                "post_type": str(rule.get("post_type") or "").strip(),
                "selling_painpoint_group": group,
                "product_relation": rule.get("product_relation"),
                "product_appearance_mode": rule.get("product_appearance_mode"),
            },
        )
        graph.relate("candidate_rule", root_key, rule_key)
        matches = _matching_expressions(
            expression_index,
            group,
            str(rule.get("post_type") or "").strip(),
        )
        expression_modes.add(bool(matches))
        if group and expression_index and not matches:
            raise ValueError(f"business rule {rule_id} has no expression for group: {group}")
        if not matches:
            candidates.append(_candidate("rule_expression", rule_name, {"business_rule": rule_key}))
            continue
        for expression, expression_key in matches:
            graph.relate(
                "allowed_expression",
                rule_key,
                expression_key,
                selling_painpoint_group=group,
            )
            candidates.append(
                _candidate(
                    "rule_expression",
                    f"{rule_name} + 表达{expression.get('source_row_no') or ''}",
                    {"business_rule": rule_key, "selling_expression": expression_key},
                )
            )
    if len(expression_modes) > 1:
        raise ValueError("node graph v1 cannot mix expression-backed and plain rules")
    return candidates


def _add_slot_nodes(
    graph: _Graph,
    root_key: str,
    slot: dict[str, Any],
    slot_index: int,
) -> tuple[list[dict[str, Any]], str, str]:
    slot_code = str(slot.get("slot_code") or slot.get("code") or slot_index).strip()
    slot_name = str(slot.get("slot_name") or slot.get("name") or slot_code).strip()
    dimension = f"slot_{_identifier(slot_code)}"
    options = _variation_options(slot.get("options"))
    if not options:
        raise ValueError(f"variation slot {slot_code} has no options")
    candidates = []
    for option_index, (value, item_id) in enumerate(options, start=1):
        node_key = graph.add_node(
            node_key=f"{root_key}:slot:{slot_code}:{option_index}",
            node_type="variation_slot",
            name=f"{slot_name} {option_index}",
            text=value,
            source_ref={
                "slot_code": slot_code,
                "option_index": option_index,
                **({"item_id": item_id} if item_id else {}),
            },
            properties={
                "slot_code": slot_code,
                "slot_name": slot_name,
                "option_index": option_index,
                **({"item_id": item_id} if item_id else {}),
            },
        )
        graph.relate(f"slot_candidate:{slot_code}", root_key, node_key)
        candidates.append(_candidate(dimension, value[:255], {dimension: node_key}))
    return candidates, dimension, slot_name


def _matching_expressions(
    index: dict[str, list[tuple[dict[str, Any], str]]],
    group: str,
    post_type: str,
) -> list[tuple[dict[str, Any], str]]:
    groups = [group, f"{group}-ugc"] if group and not group.endswith("-ugc") else [group]
    matches = []
    for candidate_group in groups:
        for expression, node_key in index.get(candidate_group, []):
            applicable = _string_list(expression.get("applicable_post_types"))
            if applicable and post_type not in applicable:
                continue
            matches.append((expression, node_key))
    return matches


def _candidate(group_id: str, name: str, nodes: dict[str, str]) -> dict[str, Any]:
    return {
        "id": _stable_id(group_id, *[f"{key}={nodes[key]}" for key in sorted(nodes)]),
        "name": name,
        "nodes": nodes,
        "group_id": group_id,
    }


def _selection_step(
    dimension: str,
    source_node_key: str | None,
    relation_type: str,
    *,
    from_dimension: str | None = None,
) -> dict[str, Any]:
    return {
        "dimension_key": dimension,
        "selection_mode": "select_one",
        "source_node_key": source_node_key,
        "from_dimension": from_dimension,
        "relation_type": relation_type,
    }


def _binding(dimension: str, variable: str, layer: str, order: int) -> dict[str, Any]:
    return {
        "dimension_key": dimension,
        "variable_name": variable,
        "layer": layer,
        "order": order,
    }


def _variation_options(raw_options: Any) -> list[tuple[str, str | None]]:
    options = []
    for raw in raw_options or []:
        if isinstance(raw, dict):
            value = str(
                raw.get("value")
                or raw.get("text")
                or raw.get("content")
                or raw.get("name")
                or ""
            ).strip()
            item_id = str(raw.get("item_id") or raw.get("id") or "").strip() or None
        else:
            value = str(raw or "").strip()
            item_id = None
        if value:
            options.append((value, item_id))
    return options


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := str(item or "").strip())]


def _bullet_text(value: Any) -> str:
    return "\n".join(f"- {line}" for line in _string_list(value))


def _identifier(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", str(value or "")).strip("_")
    return normalized.lower() or hashlib.sha256(str(value).encode()).hexdigest()[:12]


def _stable_id(*parts: str) -> str:
    return "maga_" + hashlib.sha256("\0".join(parts).encode()).hexdigest()[:24]


def _json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
