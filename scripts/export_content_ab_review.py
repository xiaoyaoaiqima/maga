#!/usr/bin/env python3
"""Render one generic content-generation A/B review preview from normalized JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TIER_ORDER = {"hold_out": 0, "light_fix_usable": 1, "not_run": 1.5, "direct_pool": 2}


def _text(value: Any, default: str = "-") -> str:
    text = str(value or "").strip()
    return text or default


def _items(arm: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in arm.get("items") or [] if isinstance(item, dict)]


def _llm_tier(item: dict[str, Any]) -> str:
    review = item.get("llm_review") if isinstance(item.get("llm_review"), dict) else {}
    tier = str(review.get("tier") or review.get("business_usability_tier") or "").strip()
    return tier if tier in TIER_ORDER else "not_run"


def _machine_pass(item: dict[str, Any]) -> bool:
    review = item.get("machine_review") if isinstance(item.get("machine_review"), dict) else {}
    return bool(review.get("pass"))


def _item_failed(item: dict[str, Any]) -> bool:
    return item.get("status") == "failed" or not str(item.get("content") or "").strip()


def _marker(item: dict[str, Any]) -> tuple[str, str]:
    if _item_failed(item):
        return "⛔", "生成失败"
    tier = _llm_tier(item)
    if tier == "hold_out":
        return "💣", "需修"
    if tier == "light_fix_usable":
        return "⚠️", "重点看"
    if tier == "not_run":
        return "👀", "LLM review未运行"
    return "✅", "可用"


def _item_ref(item: dict[str, Any]) -> str:
    return _text(item.get("pair_id") or item.get("item_no") or item.get("id"))


def _arm_metrics(arm: dict[str, Any]) -> dict[str, Any]:
    items = _items(arm)
    counts = {"direct_pool": 0, "light_fix_usable": 0, "hold_out": 0, "not_run": 0}
    for item in items:
        counts[_llm_tier(item)] += 1
    failed = sum(_item_failed(item) for item in items)
    machine_pass = sum(_machine_pass(item) for item in items)
    return {
        "attempted": int((arm.get("metrics") or {}).get("attempted") or len(items)),
        "generated": len(items) - failed,
        "failed": failed,
        "machine_pass": machine_pass,
        **counts,
    }


def _join_refs(items: list[dict[str, Any]], tier: str) -> str:
    refs = [_item_ref(item) for item in items if _llm_tier(item) == tier]
    return ", ".join(refs) if refs else "-"


def _format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        text = f"`{json.dumps(value, ensure_ascii=False)}`"
    else:
        text = _text(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def _dimension_table(experiment: dict[str, Any]) -> list[str]:
    arms = experiment["arms"]
    headers = ["维度", *[_text(arm.get("label") or arm.get("arm_id")) for arm in arms]]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for dimension in experiment.get("changed_dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        values = dimension.get("values") if isinstance(dimension.get("values"), dict) else {}
        row = [_text(dimension.get("name"))]
        for arm in arms:
            row.append(_format_value(values.get(str(arm.get("arm_id")))))
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _controlled_lines(experiment: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in experiment.get("controlled_dimensions") or []:
        if not isinstance(item, dict):
            continue
        lines.append(f"- {_text(item.get('name'))}：{_format_value(item.get('value'))}")
    return lines or ["- 未声明"]


def _metrics_table(experiment: dict[str, Any]) -> list[str]:
    lines = [
        "| 组别 | attempted | generated | failed | machine pass | LLM直接可用 | LLM小改可用 | LLM需修 | LLM未运行 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for arm in experiment["arms"]:
        metrics = _arm_metrics(arm)
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(arm.get("label") or arm.get("arm_id")),
                    str(metrics["attempted"]),
                    str(metrics["generated"]),
                    str(metrics["failed"]),
                    str(metrics["machine_pass"]),
                    str(metrics["direct_pool"]),
                    str(metrics["light_fix_usable"]),
                    str(metrics["hold_out"]),
                    str(metrics["not_run"]),
                ]
            )
            + " |"
        )
    return lines


def _extra_metrics(experiment: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for arm in experiment["arms"]:
        metrics = arm.get("metrics") if isinstance(arm.get("metrics"), dict) else {}
        extras = {
            key: value
            for key, value in metrics.items()
            if key not in {"attempted", "generated", "failed", "machine_pass", "direct_pool", "light_fix_usable", "hold_out"}
        }
        if extras:
            lines.append(f"- {_text(arm.get('label') or arm.get('arm_id'))}：" + "；".join(f"{key}={_format_value(value)}" for key, value in extras.items()))
    return lines


def _review_lines(item: dict[str, Any]) -> list[str]:
    machine = item.get("machine_review") if isinstance(item.get("machine_review"), dict) else {}
    llm = item.get("llm_review") if isinstance(item.get("llm_review"), dict) else {}
    operator = item.get("operator_review") if isinstance(item.get("operator_review"), dict) else {}
    machine_text = "通过" if machine.get("pass") else "未通过"
    if machine.get("reason"):
        machine_text += f"：{machine['reason']}"
    issue_codes = ", ".join(str(code) for code in llm.get("issue_codes") or []) or "无"
    lines = [
        f"- 机器审核：{machine_text}",
        f"- LLM review：{_llm_tier(item)}；{_text(llm.get('reason'), 'not run')}",
        f"- LLM问题码：`{issue_codes}`",
        f"- 修改方向：{_text(llm.get('rewrite_direction'), '无需修改')}",
    ]
    if operator:
        lines.append(f"- 运营判断：{_text(operator.get('status'))}；{_text(operator.get('reason'))}")
    else:
        lines.append("- 运营判断：not run")
    return lines


def _aggregate_sections(experiment: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for arm in experiment["arms"]:
        label = _text(arm.get("label") or arm.get("arm_id"))
        lines.extend([f"## {label} 明细", ""])
        items = sorted(
            _items(arm),
            key=lambda item: (TIER_ORDER.get(_llm_tier(item), 0), _item_ref(item)),
        )
        for item in items:
            marker, status = _marker(item)
            lines.extend(
                [
                    f"### {marker} {_item_ref(item)}｜{status}｜{_text(item.get('category'), '')}",
                    "",
                    *_review_lines(item),
                    "",
                    str(item.get("content") or ""),
                    "",
                ]
            )
    return lines


def _pair_status(items: list[dict[str, Any]]) -> tuple[str, str]:
    if any(_item_failed(item) for item in items):
        return "⛔", "存在生成失败"
    worst = min(TIER_ORDER.get(_llm_tier(item), 0) for item in items)
    if worst == TIER_ORDER["hold_out"]:
        return "💣", "至少一组需修"
    if worst == TIER_ORDER["light_fix_usable"]:
        return "⚠️", "至少一组重点看"
    if worst == TIER_ORDER["not_run"]:
        return "👀", "至少一组LLM review未运行"
    return "✅", "两组均可用"


def _paired_sections(experiment: dict[str, Any]) -> list[str]:
    arms = experiment["arms"]
    pairs: dict[str, dict[str, dict[str, Any]]] = {}
    for arm in arms:
        arm_id = str(arm.get("arm_id"))
        for item in _items(arm):
            pairs.setdefault(_item_ref(item), {})[arm_id] = item
    ordered = sorted(
        pairs.items(),
        key=lambda pair: (
            min(TIER_ORDER.get(_llm_tier(item), 0) for item in pair[1].values()),
            pair[0],
        ),
    )
    lines = ["## 配对 Review", ""]
    for pair_id, pair in ordered:
        marker, status = _pair_status(list(pair.values()))
        lines.extend([f"### {marker} pair {pair_id}｜{status}", ""])
        for arm in arms:
            arm_id = str(arm.get("arm_id"))
            item = pair.get(arm_id)
            lines.extend([f"#### {_text(arm.get('label') or arm_id)}", ""])
            if not item:
                lines.extend(["⛔ 无对应产出", ""])
                continue
            lines.extend([*_review_lines(item), "", str(item.get("content") or ""), ""])
    return lines


def validate_experiment(experiment: dict[str, Any]) -> None:
    arms = experiment.get("arms")
    if not isinstance(arms, list) or len(arms) < 2:
        raise ValueError("A/B review requires at least two arms")
    arm_ids = [str(arm.get("arm_id") or "") for arm in arms if isinstance(arm, dict)]
    if len(arm_ids) != len(arms) or any(not arm_id for arm_id in arm_ids):
        raise ValueError("every arm requires arm_id")
    if len(set(arm_ids)) != len(arm_ids):
        raise ValueError("arm_id must be unique")


def render_experiment_preview(experiment: dict[str, Any]) -> str:
    validate_experiment(experiment)
    lines = [
        f"# {_text(experiment.get('title'), 'Content A/B Review')}",
        "",
        f"结论：{_text(experiment.get('conclusion'), '待 review')}",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 实验信息",
        "",
        f"- experiment_id：`{_text(experiment.get('experiment_id'))}`",
        f"- content_type：`{_text(experiment.get('content_type'))}`",
        f"- comparison_mode：`{_text(experiment.get('comparison_mode'), 'aggregate')}`",
        "",
        "## 唯一变量",
        "",
        *_dimension_table(experiment),
        "",
        "## 保持一致",
        "",
        *_controlled_lines(experiment),
        "",
        "## A/B 指标",
        "",
        *_metrics_table(experiment),
        "",
    ]
    extras = _extra_metrics(experiment)
    if extras:
        lines.extend(["### 补充指标", "", *extras, ""])
    lines.extend(["## 分组结论", ""])
    conclusions = experiment.get("group_conclusions") or []
    if conclusions:
        lines.extend(f"- {item}" for item in conclusions)
    else:
        lines.append("- 未提供")
    lines.append("")
    for arm in experiment["arms"]:
        items = _items(arm)
        lines.append(
            f"- {_text(arm.get('label') or arm.get('arm_id'))}：direct `{_join_refs(items, 'direct_pool')}`；watch `{_join_refs(items, 'light_fix_usable')}`；needs-fix `{_join_refs(items, 'hold_out')}`；LLM not-run `{_join_refs(items, 'not_run')}`"
        )
    lines.append("")
    if experiment.get("comparison_mode") == "paired":
        lines.extend(_paired_sections(experiment))
    else:
        lines.extend(_aggregate_sections(experiment))
    artifacts = experiment.get("artifacts") if isinstance(experiment.get("artifacts"), dict) else {}
    lines.extend(["## 调试信息", ""])
    for key, value in artifacts.items():
        lines.append(f"- {key}：`{value}`")
    if not artifacts:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-json", required=True, type=Path)
    parser.add_argument("--preview-md", required=True, type=Path)
    args = parser.parse_args()
    experiment = json.loads(args.experiment_json.read_text(encoding="utf-8"))
    args.preview_md.parent.mkdir(parents=True, exist_ok=True)
    args.preview_md.write_text(render_experiment_preview(experiment), encoding="utf-8")
    print(args.preview_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
