from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_a2_single_cause_deescalation_batch import choose_winner  # noqa: E402


def _row(arm: str, tier: str, *, issue_codes: list[str] | None = None) -> dict:
    return {
        "phase": "ab",
        "arm": arm,
        "attempt_weight": 1,
        "machine_pass": True,
        "llm_tier": tier,
        "llm_issue_codes": issue_codes or [],
    }


def test_winner_uses_direct_difference_over_one_first():
    rows = [*[_row("qwen", "direct_pool") for _ in range(4)], _row("deepseek", "direct_pool")]

    winner, evidence = choose_winner(rows)

    assert winner == "qwen"
    assert evidence["direct_diff_qwen_minus_deepseek"] == 3


def test_close_direct_result_prefers_qwen_only_without_extra_holdout_or_high_risk():
    safe_rows = [
        _row("qwen", "direct_pool"),
        _row("qwen", "light_fix_usable"),
        _row("deepseek", "direct_pool"),
        _row("deepseek", "hold_out"),
    ]
    risky_rows = [
        _row("qwen", "direct_pool"),
        _row("qwen", "hold_out", issue_codes=["definitive_causality"]),
        _row("deepseek", "direct_pool"),
        _row("deepseek", "light_fix_usable"),
    ]

    assert choose_winner(safe_rows)[0] == "qwen"
    assert choose_winner(risky_rows)[0] == "deepseek"
