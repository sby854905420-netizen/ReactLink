#!/bin/bash


# Quick-edit preparation settings. Set a value to empty to use config.py defaults.
PREP_DATASET_NAME="MMQA_SMOKE"
PREP_SENTENCE_TRANSFORMER_MODEL="Qwen/Qwen3-Embedding-0.6B"
PREP_RECREATE="false"
PREP_BATCH_SIZE="1024"

python ./Run_local/prepare_docs_embeddings.py \
    --dataset_name "$PREP_DATASET_NAME" \
    --sentence_transformer_model "$PREP_SENTENCE_TRANSFORMER_MODEL" \
    --recreate "$PREP_RECREATE" \
    --batch_size "$PREP_BATCH_SIZE"
