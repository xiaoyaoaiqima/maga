from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / ".local/codex/run_chunyue_candidate_smoke.py"
SPEC = importlib.util.spec_from_file_location("run_chunyue_candidate_smoke", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_expression_content_preserved_for_continuous_source():
    expression = "担心化学残留，怕影响宝宝发育"

    assert MODULE.expression_content_preserved(expression, f"我一直{expression}，所以认真选奶。")


def test_expression_content_preserved_when_channel_is_inserted_between_segments():
    expression = "担心奶粉中有化学残留，敏敏宝宝喝了之后很少出现敏敏情况"
    body = "担心奶粉中有化学残留。后来在妈妈群看到说莼悦，敏敏宝宝喝了之后很少出现敏敏情况。"

    assert MODULE.expression_content_preserved(expression, body)


def test_expression_content_preserved_rejects_rewritten_segment():
    expression = "担心奶粉中有化学残留，怕影响宝宝发育"
    body = "担心奶粉里可能有残留，怕影响宝宝发育。"

    assert not MODULE.expression_content_preserved(expression, body)


def test_expression_content_preserved_rejects_reordered_segments():
    expression = "担心奶粉中有化学残留，怕影响宝宝发育"
    body = "怕影响宝宝发育，所以担心奶粉中有化学残留。"

    assert not MODULE.expression_content_preserved(expression, body)
