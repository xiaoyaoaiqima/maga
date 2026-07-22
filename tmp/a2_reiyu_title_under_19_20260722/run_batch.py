from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path


BASE_SCRIPT = Path(
    "/Users/luxifa/maga/tmp/a2_reiyu_reward_completion_cleanup_20260722/run_batch.py"
)
spec = importlib.util.spec_from_file_location("a2_reiyu_base_batch", BASE_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load batch runner: {BASE_SCRIPT}")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

runner.CANDIDATE_ASSET_ID = 1985
runner.OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_title_under_19_20260722")


if __name__ == "__main__":
    asyncio.run(runner.main())
