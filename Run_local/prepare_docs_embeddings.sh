#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SCRIPT_DIR"

# Quick-edit preparation settings.
# Put each dataset folder under PROJECT_ROOT/Data, then change DATASET_NAME here.
DATASET_NAME="MMQA_SMOKE"
SENTENCE_TRANSFORMER_MODEL="Qwen/Qwen3-Embedding-0.6B"
BATCH_SIZE=1024
RECREATE=false

# Defaults below normally do not need to change.
DATA_ROOT="$PROJECT_ROOT/Data"

usage() {
    cat <<'EOF'
Usage: bash prepare_docs_embeddings.sh [DATASET_NAME] [options]

Options:
  --dataset_name NAME     Dataset name. Defaults to the quick-edit setting in this file.
  --data_root PATH        Data root. Defaults to PROJECT_ROOT/Data.
  --batch_size N          Embedding batch size. Defaults to the quick-edit setting in this file.
  --sentence_transformer_model NAME
                          Embedding model. Defaults to the quick-edit setting in this file.
  --recreate [BOOL]       Recreate docs and embeddings even if they already exist.
                          BOOL can be true/false/1/0/yes/no. If omitted, true.
  --no-recreate           Reuse existing docs and embeddings when present.
  -h, --help              Show this help.
EOF
}

DATASET_NAME_SET=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dataset_name|--dataset-name)
            DATASET_NAME="$2"
            DATASET_NAME_SET=1
            shift 2
            ;;
        --data_root|--data-root)
            DATA_ROOT="$2"
            shift 2
            ;;
        --batch_size|--batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --sentence_transformer_model|--sentence-transformer-model)
            SENTENCE_TRANSFORMER_MODEL="$2"
            shift 2
            ;;
        --recreate)
            if [[ $# -gt 1 && "$2" != --* ]]; then
                RECREATE="$2"
                shift 2
            else
                RECREATE=true
                shift
            fi
            ;;
        --recreate=*)
            RECREATE="${1#*=}"
            shift
            ;;
        --no-recreate)
            RECREATE=false
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
        *)
            if [[ "$DATASET_NAME_SET" -eq 0 ]]; then
                DATASET_NAME="$1"
                DATASET_NAME_SET=1
                shift
            else
                echo "Unexpected argument: $1" >&2
                usage >&2
                exit 1
            fi
            ;;
    esac
done

case "${RECREATE,,}" in
    true|1|yes|y)
        RECREATE=true
        ;;
    false|0|no|n)
        RECREATE=false
        ;;
    *)
        echo "Invalid recreate value: $RECREATE" >&2
        usage >&2
        exit 1
        ;;
esac

DOCUMENTS_PATH="$DATA_ROOT/$DATASET_NAME/documents/column_documents.json"
EMBEDDING_INDEX_PATH="$DATA_ROOT/$DATASET_NAME/embeddings/index.faiss"
EMBEDDING_METADATA_PATH="$DATA_ROOT/$DATASET_NAME/embeddings/metadata.json"

if [[ "$RECREATE" == true || ! -f "$DOCUMENTS_PATH" ]]; then
    python generate_docs.py --dataset_name "$DATASET_NAME" --data_root "$DATA_ROOT"
else
    echo "Documents already exist, skipping: $DOCUMENTS_PATH"
fi

if [[ "$RECREATE" == true || ! -f "$EMBEDDING_INDEX_PATH" || ! -f "$EMBEDDING_METADATA_PATH" ]]; then
    python embedding_docs.py \
        --dataset_name "$DATASET_NAME" \
        --data_root "$DATA_ROOT" \
        --batch_size "$BATCH_SIZE" \
        --sentence_transformer_model "$SENTENCE_TRANSFORMER_MODEL"
else
    echo "Embeddings already exist, skipping: $DATA_ROOT/$DATASET_NAME/embeddings"
fi
