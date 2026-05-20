#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$ROOT_DIR/.env" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      export "$line"
    fi
  done <"$ROOT_DIR/.env"
fi

if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  echo "请先设置 DEEPSEEK_API_KEY"
  exit 1
fi

python3 "$ROOT_DIR/scripts/optimize_prompt_from_txts.py" \
  --prompt-file "$ROOT_DIR/local_data/prompt.txt" \
  --content-file "$ROOT_DIR/local_data/content.txt" \
  --problem-file "$ROOT_DIR/local_data/problem.txt" \
  --output "$ROOT_DIR/local_data/prompt_optimize_result.json" \
  --model deepseek-chat \
  --base-url "${DEEPSEEK_API_BASE:-https://api.deepseek.com}" \
  --api-key "$DEEPSEEK_API_KEY" \
  --generation-model deepseek-chat \
  --generation-base-url "${DEEPSEEK_API_BASE:-https://api.deepseek.com}" \
  --generation-api-key "$DEEPSEEK_API_KEY" \
  --new-prompt-output "$ROOT_DIR/local_data/new_prompt.txt" \
  --new-content-output "$ROOT_DIR/local_data/new_content.txt"
