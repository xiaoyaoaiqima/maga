import csv
import json
from pathlib import Path


SOURCE = Path(
    "/Users/luxifa/maga/outputs/a2_reiyu_business_rules_20260721/"
    "a2礼遇UGC分享贴_业务规则.csv"
)
OUTPUT = Path("/Users/luxifa/maga/tmp/a2_reiyu_slot_ab_20260721/current_rules.json")

with SOURCE.open("r", encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file)
    rows = list(reader)
    headers = list(reader.fieldnames or [])

if len(headers) != 16 or len(rows) != 8:
    raise SystemExit(f"unexpected source shape: headers={len(headers)} rows={len(rows)}")

OUTPUT.write_text(
    json.dumps({"headers": headers, "rows": rows}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(f"headers={len(headers)} rows={len(rows)} output={OUTPUT}")
