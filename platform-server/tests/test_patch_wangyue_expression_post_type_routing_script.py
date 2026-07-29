from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "patch_wangyue_expression_post_type_routing.py"
SPEC = importlib.util.spec_from_file_location("patch_wangyue_expression_post_type_routing", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_build_next_content_adds_only_configured_post_type_routes() -> None:
    source = {
        "items": [{"rule_id": "business_rule_008"}],
        "hard_boundaries": ["existing"],
        "variation_slots": [{"slot_code": "inspiration_material"}],
        "selling_painpoint_expressions": [
            {
                "source_row_no": source_row_no,
                "selling_painpoint_group": "营养丰富+营养不足-ugc",
                "expression": f"expression-{source_row_no}",
            }
            for source_row_no in [*MODULE.EXPRESSION_POST_TYPE_ROUTES, 104]
        ],
    }

    result = MODULE.build_next_content(source)
    by_row = {
        item["source_row_no"]: item
        for item in result["selling_painpoint_expressions"]
    }

    assert source["selling_painpoint_expressions"][0].get("applicable_post_types") is None
    assert result["items"] == source["items"]
    assert result["hard_boundaries"] == source["hard_boundaries"]
    assert result["variation_slots"] == source["variation_slots"]
    assert by_row[99]["applicable_post_types"] == ["对比选择"]
    assert "applicable_post_types" not in by_row[104]
