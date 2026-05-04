#!/usr/bin/env bash
set -euo pipefail

python3 scripts/optimize_critic_prompt_from_txts.py \
  --content-file local_data/content.txt \
  --critic-prompt-file local_data/critic_prompt.txt \
  --critic-result-file local_data/critic_result.txt \
  --human-feedback-file local_data/human_feedback.txt \
  --output critic_prompt_optimize_result.json
