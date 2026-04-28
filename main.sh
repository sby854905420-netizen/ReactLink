#!/bin/bash



# Quick-edit run settings. Set a value to empty to use config.py defaults.
RUN_DATASET_NAME="MMQA_SMOKE"
RUN_OLLAMA_BASE_URL="http://127.0.0.1:11434"
RUN_OLLAMA_MODEL="qwen2.5:14b"
RUN_MODEL_DISCUSSION_TURNS="20"
RUN_TOP_N="50"
RUN_WRITE_SAMPLE_DEBUG="False"

python ./Run_local/run_pipeline.py \
    --dataset_name "$RUN_DATASET_NAME" \
    --ollama_base_url "$RUN_OLLAMA_BASE_URL" \
    --ollama_model "$RUN_OLLAMA_MODEL" \
    --model_discussion_turns "$RUN_MODEL_DISCUSSION_TURNS" \
    --top_n "$RUN_TOP_N" \
    --write_sample_debug "$RUN_WRITE_SAMPLE_DEBUG"
