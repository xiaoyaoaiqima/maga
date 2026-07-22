from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "patch_wangyue_energy_selling_pairs.py"
SPEC = importlib.util.spec_from_file_location("patch_wangyue_energy_selling_pairs", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_build_next_content_replaces_only_energy_groups_and_keeps_frequency_control() -> None:
    items = [
        {
            "item_no": item_no,
            "post_type": post_type,
            "business_rule": f"old-{item_no}",
            "selling_painpoint_group": "进阶保护力+精力不足",
        }
        for item_no, post_type in ((14, "复购/长期使用"), (17, "问题解决"), (20, "轻测评"))
    ]
    expressions = [
        {
            "source_row_no": source_row_no,
            "selling_painpoint_group": "进阶保护力+精力不足",
            "expression": f"old-{source_row_no}",
        }
        for source_row_no in MODULE.ENERGY_PAIR_EXPRESSIONS
    ]
    source = {
        "items": items,
        "selling_painpoint_expressions": expressions,
        "hard_boundaries": ["existing", MODULE.OLD_ENERGY_PAIR_BOUNDARY],
        "variation_slots": [{"slot_code": "inspiration_material"}],
        "inspiration_usage_interval": 5,
    }

    result = MODULE.build_next_content(source)

    assert source["items"][0]["selling_painpoint_group"] == "进阶保护力+精力不足"
    assert result["inspiration_usage_interval"] == 5
    assert result["variation_slots"] == source["variation_slots"]
    assert MODULE.ENERGY_PAIR_BOUNDARY in result["hard_boundaries"]
    assert MODULE.OLD_ENERGY_PAIR_BOUNDARY not in result["hard_boundaries"]
    by_no = {item["item_no"]: item for item in result["items"]}
    assert by_no[14]["selling_painpoint_group"] == "进阶保护力+眼脑双引擎+精力不足"
    assert by_no[17]["selling_painpoint_group"] == "进阶保护力+营养丰富+精力不足-ugc"
    assert by_no[20]["selling_painpoint_group"] == "进阶保护力+眼脑双引擎+精力不足-ugc"
    assert all(
        "进阶保护力+精力不足" != item["selling_painpoint_group"]
        for item in result["selling_painpoint_expressions"]
    )
