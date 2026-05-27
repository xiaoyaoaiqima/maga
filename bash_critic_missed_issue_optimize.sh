#!/usr/bin/env bash
set -euo pipefail

python3 scripts/optimize_critic_prompt_for_missed_issue.py \
  --content-file local_data/content.txt \
  --prompt-file local_data/critic_prompt.txt \
  --problem-file local_data/problem.txt \
  --output critic_missed_issue_optimize_result.json
