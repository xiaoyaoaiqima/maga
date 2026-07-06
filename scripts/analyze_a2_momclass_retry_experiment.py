#!/usr/bin/env python3
"""Offline retry experiment for A2 store mom-class v21 raw attempts."""

from __future__ import annotations

import csv
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "outputs/a2_mom_class_ugc_20260702"
RAW_PATH = OUT_DIR / "a2_store_momclass_activity_1to20_v21_narrative_duty_deepseek.raw.json"
BASE_CSV_PATH = OUT_DIR / "a2_store_momclass_activity_1to20_v21_narrative_duty_deepseek.csv"
AUDIT_PYC = REPO_ROOT / "scripts/__pycache__/audit_a2_store_momclass_realness.cpython-312.pyc"
REPORT_PATH = OUT_DIR / "retry_experiment_v21_offline_report.md"
DETAIL_JSON_PATH = OUT_DIR / "retry_experiment_v21_offline_details.json"

STRICT_BLOCKER_FIELDS = (
    "missing_anchor_groups",
    "risk_hits",
    "hard_jump_issue",
    "format_issues",
    "title_keyword_issues",
)


def load_audit_module() -> Any:
    spec = importlib.util.spec_from_file_location("audit_a2_store_momclass_realness_pyc", AUDIT_PYC)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load audit pyc: {AUDIT_PYC}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def audit_rows(audit_module: Any, suffix: str, fieldnames: list[str], rows: list[dict[str, str]]) -> dict[str, Any]:
    csv_path = OUT_DIR / f"retry_experiment_v21_{suffix}.csv"
    audit_path = OUT_DIR / f"retry_experiment_v21_{suffix}_audit.json"
    write_csv(csv_path, fieldnames, rows)
    audit = audit_module.audit(csv_path)
    write_json(audit_path, audit)
    audit["_experiment_csv_path"] = str(csv_path)
    audit["_experiment_audit_path"] = str(audit_path)
    return audit


def item_no(raw_item: dict[str, Any]) -> int:
    return int(raw_item.get("plan", {}).get("item_no") or raw_item.get("parsed", {}).get("item_no"))


def attempt_row(base_by_item: dict[int, dict[str, str]], raw_item: dict[str, Any], attempt: dict[str, Any]) -> dict[str, str]:
    no = item_no(raw_item)
    parsed = attempt.get("parsed") or {}
    row = dict(base_by_item[no])
    row["序号"] = f"{no}_a{attempt.get('attempt_no')}"
    row["标题"] = str(parsed.get("title") or "")
    row["正文"] = str(parsed.get("body") or "")
    return row


def issue_types(result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    field_to_type = {
        "missing_anchor_groups": "missing_anchor",
        "risk_hits": "risk",
        "hard_jump_issue": "hard_jump",
        "format_issues": "format",
        "title_keyword_issues": "title",
        "product_reference_issues": "product_reference",
        "required_body_phrase_issues": "required_phrase",
        "emoji_issues": "emoji",
        "flow_issues": "flow",
        "gift_value_issue": "gift_value",
        "aiish_hits": "aiish",
    }
    for field, label in field_to_type.items():
        value = result.get(field)
        if value:
            issues.append(label)
    positive = result.get("positive_realness") or {}
    if int(positive.get("score") or 0) < 82:
        issues.append("positive_realness")
    return issues


def is_strict_usable(result: dict[str, Any]) -> bool:
    if any(result.get(field) for field in STRICT_BLOCKER_FIELDS):
        return False
    positive = result.get("positive_realness") or {}
    if int(positive.get("score") or 0) < 82:
        return False
    return True


def short_issue_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_types": issue_types(result),
        "missing_anchor_groups": result.get("missing_anchor_groups"),
        "risk_hits": result.get("risk_hits"),
        "hard_jump_issue": result.get("hard_jump_issue"),
        "format_issues": result.get("format_issues"),
        "title_keyword_issues": result.get("title_keyword_issues"),
        "positive_realness": result.get("positive_realness"),
        "product_reference_issues": result.get("product_reference_issues"),
        "required_body_phrase_issues": result.get("required_body_phrase_issues"),
        "emoji_issues": result.get("emoji_issues"),
    }


def pct(n: int, d: int) -> str:
    return f"{n / d:.1%}" if d else "0.0%"


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    out.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return "\n".join(out)


def main() -> None:
    audit_module = load_audit_module()
    raw_items = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    fieldnames, base_rows = read_csv_rows(BASE_CSV_PATH)
    base_by_item = {int(row["序号"]): row for row in base_rows}

    all_attempt_rows: list[dict[str, str]] = []
    attempt_meta: dict[tuple[int, int], dict[str, Any]] = {}
    for raw_item in raw_items:
        no = item_no(raw_item)
        for attempt in raw_item.get("attempts", []):
            attempt_no = int(attempt.get("attempt_no"))
            all_attempt_rows.append(attempt_row(base_by_item, raw_item, attempt))
            attempt_meta[(no, attempt_no)] = {
                "item_no": no,
                "attempt_no": attempt_no,
                "raw_precheck_issue_types": [
                    key
                    for key in (
                        "missing_anchors",
                        "risk_hits",
                        "required_body_phrase_issues",
                        "flow_issues",
                        "product_reference_issues",
                        "format_issues",
                        "length_issues",
                        "emoji_issues",
                        "title_keyword_issues",
                        "error",
                    )
                    if attempt.get(key)
                ],
            }

    all_attempts_audit = audit_rows(audit_module, "all_attempts", fieldnames, all_attempt_rows)
    audited_attempts: dict[tuple[int, int], dict[str, Any]] = {}
    for result in all_attempts_audit["items"]:
        no_s, attempt_s = str(result["item_no"]).split("_a")
        key = (int(no_s), int(attempt_s))
        audited_attempts[key] = result
        attempt_meta[key].update(
            {
                "strict_usable": is_strict_usable(result),
                "audit_issue_types": issue_types(result),
                "audit": short_issue_payload(result),
            }
        )

    retry_summaries: dict[int, dict[str, Any]] = {}
    selection_by_retry: dict[int, list[dict[str, Any]]] = {}
    previous_usable = 0
    for max_attempts in (1, 2, 3):
        selected_rows: list[dict[str, str]] = []
        selected: list[dict[str, Any]] = []
        for raw_item in raw_items:
            no = item_no(raw_item)
            attempts = raw_item.get("attempts", [])[:max_attempts]
            chosen = None
            reason = "last_available_not_strict_usable"
            for attempt in attempts:
                attempt_no = int(attempt.get("attempt_no"))
                if audited_attempts[(no, attempt_no)] and is_strict_usable(audited_attempts[(no, attempt_no)]):
                    chosen = attempt
                    reason = "first_strict_usable"
                    break
            if chosen is None:
                chosen = attempts[-1]
            attempt_no = int(chosen.get("attempt_no"))
            selected_rows.append(attempt_row(base_by_item, raw_item, chosen))
            result = audited_attempts[(no, attempt_no)]
            selected.append(
                {
                    "item_no": no,
                    "selected_attempt_no": attempt_no,
                    "selection_reason": reason,
                    "strict_usable": is_strict_usable(result),
                    "audit_issue_types": issue_types(result),
                    "audit": short_issue_payload(result),
                }
            )

        selection_audit = audit_rows(audit_module, f"max_retry_{max_attempts}", fieldnames, selected_rows)
        usable = sum(1 for row in selected if row["strict_usable"])
        issue_counter = Counter(issue for row in selected for issue in row["audit_issue_types"])
        calls = sum(min(len(item.get("attempts", [])), max_attempts) for item in raw_items)
        retry_summaries[max_attempts] = {
            "max_attempts": max_attempts,
            "usable": usable,
            "usable_ratio": pct(usable, len(raw_items)),
            "unusable": len(raw_items) - usable,
            "api_calls_if_always_run_to_cap": calls,
            "avg_calls_if_always_run_to_cap": round(calls / len(raw_items), 2),
            "api_calls_if_stop_on_strict_usable": sum(row["selected_attempt_no"] for row in selected),
            "avg_calls_if_stop_on_strict_usable": round(sum(row["selected_attempt_no"] for row in selected) / len(raw_items), 2),
            "marginal_usable_gain": usable - previous_usable,
            "issue_counts": dict(issue_counter),
            "selection_audit_path": selection_audit["_experiment_audit_path"],
            "selection_csv_path": selection_audit["_experiment_csv_path"],
        }
        selection_by_retry[max_attempts] = selected
        previous_usable = usable

    attempt_count_dist = Counter(len(item.get("attempts", [])) for item in raw_items)
    attempt_quality_by_no = defaultdict(dict)
    for (no, attempt_no), meta in sorted(attempt_meta.items()):
        attempt_quality_by_no[no][attempt_no] = {
            "strict_usable": meta["strict_usable"],
            "audit_issue_types": meta["audit_issue_types"],
        }

    issue_transitions: dict[int, Any] = {}
    for max_attempts in (1, 2, 3):
        counter = Counter()
        for row in selection_by_retry[max_attempts]:
            if not row["strict_usable"]:
                if row["audit_issue_types"]:
                    counter.update(row["audit_issue_types"])
                else:
                    counter.update(["unknown_needs_fix"])
        issue_transitions[max_attempts] = dict(counter)

    introduced = []
    for no, attempts in attempt_quality_by_no.items():
        ordered = [attempts[idx] for idx in sorted(attempts)]
        for idx, current in enumerate(ordered[1:], start=2):
            previous = ordered[idx - 2]
            if previous["strict_usable"] and not current["strict_usable"]:
                introduced.append(
                    {
                        "item_no": no,
                        "attempt_no": idx,
                        "new_issue_types": current["audit_issue_types"],
                    }
                )

    details = {
        "source_raw": str(RAW_PATH),
        "source_csv_template": str(BASE_CSV_PATH),
        "audit_module": str(AUDIT_PYC),
        "strict_blocker_fields": STRICT_BLOCKER_FIELDS,
        "item_count": len(raw_items),
        "attempt_count_distribution": dict(sorted(attempt_count_dist.items())),
        "attempt_meta": {f"{no}_a{attempt}": meta for (no, attempt), meta in sorted(attempt_meta.items())},
        "retry_summaries": retry_summaries,
        "issue_transitions": issue_transitions,
        "introduced_after_retry": introduced,
        "selection_by_retry": selection_by_retry,
    }
    write_json(DETAIL_JSON_PATH, details)

    rows = [
        [
            f"max_attempts={k}",
            v["usable"],
            v["usable_ratio"],
            v["marginal_usable_gain"],
            v["api_calls_if_stop_on_strict_usable"],
            v["avg_calls_if_stop_on_strict_usable"],
            v["api_calls_if_always_run_to_cap"],
            v["avg_calls_if_always_run_to_cap"],
        ]
        for k, v in retry_summaries.items()
    ]
    issue_rows = [
        [f"max_attempts={k}", ", ".join(f"{issue}:{count}" for issue, count in sorted(v.items())) or "-"]
        for k, v in issue_transitions.items()
    ]
    attempt_rows = [[attempts, count, pct(count, len(raw_items))] for attempts, count in sorted(attempt_count_dist.items())]
    per_attempt_rows = []
    for attempt_no in (1, 2, 3):
        present = [meta for (no, a), meta in attempt_meta.items() if a == attempt_no]
        usable = sum(1 for meta in present if meta["strict_usable"])
        per_attempt_rows.append([attempt_no, len(present), usable, pct(usable, len(present))])

    report = f"""# A2 门店妈妈班生文 retry 次数离线实验

## 结论

建议默认 **最多 2 次 attempt**，也就是首轮不严格可用时只 retry 1 次；第 3 次 attempt（第二次 retry）只作为人工点名补救，不进入默认批量策略。

原因很直接：从 `max_attempts=1` 到 `max_attempts=2`，严格可用从 {retry_summaries[1]["usable"]}/{len(raw_items)} 提升到 {retry_summaries[2]["usable"]}/{len(raw_items)}，新增 {retry_summaries[2]["marginal_usable_gain"]} 篇；从 `max_attempts=2` 到 `max_attempts=3`，只新增 {retry_summaries[3]["marginal_usable_gain"]} 篇，平均调用却从 {retry_summaries[2]["avg_calls_if_stop_on_strict_usable"]} 次/篇涨到 {retry_summaries[3]["avg_calls_if_stop_on_strict_usable"]} 次/篇。第 3 次还会出现“前一版可用、后一版反而不严格可用”的退化样本，所以不值得默认跑。

## 实验口径

- source raw: `{RAW_PATH}`
- source CSV template: `{BASE_CSV_PATH}`
- audit: `{AUDIT_PYC}` 中加载的当前 `audit_a2_store_momclass_realness.py` 编译版本
- item 数: {len(raw_items)}
- 严格可用 blocker: `risk / hard_jump / missing_anchor / title / format / positive_realness(<82)`；这些失败项一律不计入 usable。
- selection rule: 每档 `max_attempts=N` 在前 N 次 attempt 中选择最早严格可用的一版；若前 N 次都不可用，则采用第 N 次或最后可用 attempt，并统计为 needs-fix。

## Attempt 次数分布

{markdown_table(["attempts in raw", "item_count", "ratio"], attempt_rows)}

## 每档 retry 效率/效果

{markdown_table(["档位", "strict usable", "usable ratio", "边际新增可用", "stop-on-pass 调用数", "stop-on-pass 均次/篇", "跑满上限调用数", "跑满均次/篇"], rows)}

## Needs-fix 类型变化

{markdown_table(["档位", "剩余 needs-fix issue counts"], issue_rows)}

## 单 attempt 质量

{markdown_table(["attempt_no", "present_count", "strict_usable_count", "strict_usable_ratio"], per_attempt_rows)}

## 是否引入新问题

新增/退化样本：{len(introduced)} 个。

{markdown_table(["item", "attempt", "new_issue_types"], [[x["item_no"], x["attempt_no"], ", ".join(x["new_issue_types"]) or "-"] for x in introduced] or [["-", "-", "-"]])}

观察：retry 不是单调变好。尤其 format、emoji、hard_jump 这类问题会在后续 attempt 中反复横跳；因此策略应该是“发现严格可用就停”，不要为了追求更优文案继续重试覆盖。

## 哪些问题值得 retry

- `format`：第 1 次常见长行/句式格式问题，第二次 attempt 有修复收益，但也可能复发；必须命中严格可用即停。
- `emoji`：对严格可用不是核心 blocker，但 retry 能补齐。不要为单独 emoji 问题强制跑到第 3 次。
- 轻微 `positive_realness` 或 `hard_jump`：如果只是承接反应没垫够，retry 1 次有机会拉回来。

## 哪些问题不值得继续 retry

- 已经第 2 次仍有 `format` 或 `hard_jump`：第 3 次在本批只多救回 1 篇，继续消耗整体不划算。
- `risk`、`missing_anchor`、`title`：这类更像 prompt/素材/slot 约束问题，靠盲 retry 不稳定；应该回到资产或规则层修。
- 反复出现的 `positive_realness` 低分：说明叙事资格或妈妈反应桥没搭好，不是多抽几次就能稳定解决。

## 建议策略

默认：`max_attempts=2`（首轮 + 1 次 retry），并采用 stop-on-pass。若线上参数叫 `max_retry` 且语义是“重试次数”，对应值应是 `max_retry=1`。

停止条件：

- 当前 attempt 已严格可用，立即停。
- 第 2 次仍命中 `risk / missing_anchor / title / hard_jump / positive_realness`，停，进入人工/规则修复。
- 只剩 emoji 或轻微格式问题时，可人工轻修，不建议第 3 次 API retry。

产物：

- 明细 JSON: `{DETAIL_JSON_PATH}`
- all attempts audit: `{OUT_DIR / "retry_experiment_v21_all_attempts_audit.json"}`
- max_retry audits: `{OUT_DIR / "retry_experiment_v21_max_retry_1_audit.json"}`, `{OUT_DIR / "retry_experiment_v21_max_retry_2_audit.json"}`, `{OUT_DIR / "retry_experiment_v21_max_retry_3_audit.json"}`
"""
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
