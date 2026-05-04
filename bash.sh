python3 scripts/batch_prompt_optimizer_from_txt.py \
  --prompt-file local_data/prompt.txt \
  --input local_data/samples.csv \
  --output local_data/output.csv \
  --limit 10 \
  --concurrency 3 \
  --resume


python3 scripts/optimize_prompt_from_txts.py \
  --prompt-file local_data/prompt.txt \
  --content-file local_data/content.txt \
  --problem-file local_data/problem.txt \
  --output local_data/prompt_optimize_result.json
