#!/usr/bin/env python3
"""Run one prompt through the configured DeepSeek-compatible chat endpoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SCRIPT_DIR = REPO_ROOT / ".local/archive/content-generation-scripts/20260704_ugc_ppl_script_cleanup/scripts"
sys.path.insert(0, str(ARCHIVE_SCRIPT_DIR))

from run_a2_month_center_direction_batch import call_model, load_dotenv  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--output-file", required=True, type=Path)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--temperature", type=float, default=0.85)
    parser.add_argument("--max-tokens", type=int, default=1600)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()

    load_dotenv(args.dotenv)
    prompt = args.prompt_file.read_text(encoding="utf-8")
    raw = call_model(
        prompt=prompt,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        base_url_override=args.base_url,
    )
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(raw, encoding="utf-8")
    print(args.output_file)


if __name__ == "__main__":
    main()
