from copy import deepcopy

import pytest

from app.models.maga_assets import AssetRegistry
from app.services.asset_node_graph_service import compile_article_business_rule_node_graph


def _asset() -> AssetRegistry:
    return AssetRegistry(
        id=1966,
        asset_type="article_business_rule_set",
        asset_key="chunyue_probe",
        display_name="莼悦规则探针",
        version_no=28,
        status="active",
        asset_stage="production",
        source_hash=None,
        content_json={
            "generation_instruction": "写一篇小红书妈妈 UGC 奶粉选择或使用记录。",
            "writing_requirements": ["从真实生活动作写起。"],
            "generation_requirements": ["标题不超过20字。"],
            "variation_slots": [
                {
                    "slot_code": "info_source",
                    "slot_name": "信息来源线索",
                    "options": ["正文不写来源", "母婴店导购"],
                }
            ],
            "items": [
                {
                    "rule_id": "rule_001",
                    "source_row_no": 1,
                    "business_rule": "有机品质+奶粉选择",
                    "content_direction": "写妈妈选奶时确认莼悦。",
                    "selling_painpoint_group": "有机品质+奶粉选择",
                    "examples": [],
                    "supplements": [],
                },
                {
                    "rule_id": "rule_002",
                    "source_row_no": 2,
                    "business_rule": "肚肚适应+敏敏相关",
                    "content_direction": "写转奶期的日常适应观察。",
                    "selling_painpoint_group": "肚肚适应+敏敏相关",
                    "examples": [],
                    "supplements": [],
                },
            ],
            "selling_painpoint_expressions": [
                {
                    "source_row_no": 11,
                    "selling_painpoint_group": "有机品质+奶粉选择",
                    "expression": "莼悦是欧盟认证的有机产品。",
                },
                {
                    "source_row_no": 12,
                    "selling_painpoint_group": "有机品质+奶粉选择",
                    "expression": "皇家美素佳儿有荷兰自家牧场。",
                },
                {
                    "source_row_no": 13,
                    "selling_painpoint_group": "肚肚适应+敏敏相关",
                    "expression": "宝宝适应得很好，也愿意喝。",
                },
            ],
        },
        metadata_json={},
        created_by="test",
    )


def test_compiler_builds_nodes_relations_and_raap_grouped_candidates():
    graph = compile_article_business_rule_node_graph(_asset())

    assert graph.manifest["rule_count"] == 2
    assert graph.manifest["expression_count"] == 3
    assert graph.manifest["logical_combination_count"] == 6

    nodes = {node.node_key: node for node in graph.nodes}
    allowed = [
        relation
        for relation in graph.relations
        if relation.relation_type == "allowed_expression"
    ]
    assert len(allowed) == 3
    for relation in allowed:
        rule_group = nodes[relation.source_node_key].properties["selling_painpoint_group"]
        expression_group = nodes[relation.target_node_key].properties["selling_painpoint_group"]
        assert rule_group == expression_group

    combinations = graph.raap_export["strategy_blueprint"]["combinations"]
    groups: dict[str, list[dict]] = {}
    for combination in combinations:
        groups.setdefault(combination["group_id"], []).append(combination)
    assert len(groups["rule_expression"]) == 3
    assert len(groups["slot_info_source"]) == 2
    assert len(groups["fixed_requirements"]) == 1
    assert {tuple(sorted(item["nodes"])) for item in groups["rule_expression"]} == {
        ("business_rule", "selling_expression")
    }


def test_compiler_is_deterministic_and_content_addressed():
    first = compile_article_business_rule_node_graph(_asset())
    second = compile_article_business_rule_node_graph(_asset())
    assert first.manifest["bundle_hash"] == second.manifest["bundle_hash"]
    assert first.raap_export == second.raap_export

    changed = _asset()
    changed.content_json = deepcopy(changed.content_json)
    changed.content_json["items"][0]["content_direction"] += "只写真实观察。"
    changed_graph = compile_article_business_rule_node_graph(changed)
    assert changed_graph.manifest["content_hash"] != first.manifest["content_hash"]
    assert changed_graph.manifest["bundle_hash"] != first.manifest["bundle_hash"]


def test_compiler_rejects_cross_group_holes():
    asset = _asset()
    asset.content_json = deepcopy(asset.content_json)
    asset.content_json["selling_painpoint_expressions"] = [
        asset.content_json["selling_painpoint_expressions"][0]
    ]

    with pytest.raises(ValueError, match="rule_002 has no expression"):
        compile_article_business_rule_node_graph(asset)


def test_compiler_rejects_rule_level_variation_slots_in_v1():
    asset = _asset()
    asset.content_json = deepcopy(asset.content_json)
    asset.content_json["items"][0]["variation_slots"] = [
        {"slot_code": "scene", "options": ["厨房"]}
    ]

    with pytest.raises(ValueError, match="asset-level variation slots"):
        compile_article_business_rule_node_graph(asset)
