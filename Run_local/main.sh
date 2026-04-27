#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SCRIPT_DIR"

if [[ $# -gt 0 ]]; then
    export DATASET_NAME="$1"
fi

USER_LOG_PATH="${LOG_PATH:-}"
set -a
eval "$(python config.py --shell)"
set +a
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S_%N)}"
if [[ -z "$USER_LOG_PATH" ]]; then
    LOG_PATH="$LOG_ROOT/$DATASET_NAME/$SAFE_MODEL_NAME/$RUN_ID"
fi

export OLLAMA_BASE_URL OLLAMA_MODEL SENTENCE_TRANSFORMER_MODEL

DOCUMENTS_PATH="$DATA_ROOT/$DATASET_NAME/documents/column_documents.json"
EMBEDDING_INDEX_PATH="$DATA_ROOT/$DATASET_NAME/embeddings/index.faiss"
EMBEDDING_METADATA_PATH="$DATA_ROOT/$DATASET_NAME/embeddings/metadata.json"

if [[ ! -f "$DOCUMENTS_PATH" || ! -f "$EMBEDDING_INDEX_PATH" || ! -f "$EMBEDDING_METADATA_PATH" ]]; then
    echo "Missing generated documents or embeddings for dataset: $DATASET_NAME" >&2
    echo "Run this first:" >&2
    echo "  bash prepare_docs_embeddings.sh \"$DATASET_NAME\"" >&2
    exit 1
fi

mkdir -p "$LOG_PATH/_summary" "$LOG_PATH/cache" "$LOG_PATH/status" "$LOG_PATH/backup"
if [[ "$RESET_COST" == "1" || "${RESET_COST,,}" == "true" ]]; then
    rm -f "$LOG_PATH/_summary/cost.json" "$LOG_PATH/_summary/cost.json.lock" "$LOG_PATH/cache/_locks/cost.json.lock"
fi

cat <<EOF
Resolved ReactLink run configuration:
  DATASET_NAME=$DATASET_NAME
  OLLAMA_BASE_URL=$OLLAMA_BASE_URL
  OLLAMA_MODEL=$OLLAMA_MODEL
  MODEL_DISCUSSION_TURNS=$MODEL_DISCUSSION_TURNS
  RUN_ID=$RUN_ID
  LOG_PATH=$LOG_PATH
EOF

python retrieve_topk_schema.py \
    --log_path "$LOG_PATH" \
    --top_n "$TOP_N" \
    --dataset_name "$DATASET_NAME" \
    --data_root "$DATA_ROOT" \
    --retrieval_device "$RETRIEVAL_DEVICE" \
    --sentence_transformer_model "$SENTENCE_TRANSFORMER_MODEL" \
    --write_sample_debug "$WRITE_SAMPLE_DEBUG"

python add_id.py \
    --log_path "$LOG_PATH" \
    --dataset_name "$DATASET_NAME" \
    --data_root "$DATA_ROOT" \
    --write_sample_debug "$WRITE_SAMPLE_DEBUG"

python generate_schema.py \
    --log_path "$LOG_PATH" \
    --is_initial \
    --dataset_name "$DATASET_NAME" \
    --data_root "$DATA_ROOT" \
    --write_sample_debug "$WRITE_SAMPLE_DEBUG"

python complete_schema.py \
    --log_path "$LOG_PATH" \
    --dataset_name "$DATASET_NAME" \
    --data_root "$DATA_ROOT" \
    --ollama_base_url "$OLLAMA_BASE_URL" \
    --ollama_model "$OLLAMA_MODEL" \
    --sentence_transformer_model "$SENTENCE_TRANSFORMER_MODEL" \
    --model_discussion_turns "$MODEL_DISCUSSION_TURNS" \
    --retrieval_device "$RETRIEVAL_DEVICE" \
    --write_sample_debug "$WRITE_SAMPLE_DEBUG"

python postprocess.py \
    --log_path "$LOG_PATH" \
    --dataset_name "$DATASET_NAME" \
    --data_root "$DATA_ROOT" \
    --write_sample_debug "$WRITE_SAMPLE_DEBUG"

python generate_schema.py \
    --log_path "$LOG_PATH" \
    --dataset_name "$DATASET_NAME" \
    --data_root "$DATA_ROOT" \
    --write_sample_debug "$WRITE_SAMPLE_DEBUG"
