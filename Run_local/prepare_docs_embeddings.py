import argparse
import os

from config import BATCH_SIZE, DATA_ROOT, DATASET_NAME, SENTENCE_TRANSFORMER_MODEL, parse_bool
from utils import (
    get_documents_path,
    get_embedding_index_path,
    get_embedding_metadata_path,
    get_embeddings_dir,
)


# Quick-edit preparation settings.
DEFAULT_DATASET_NAME = "MMQA_SMOKE"
DEFAULT_SENTENCE_TRANSFORMER_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_BATCH_SIZE = 1024
DEFAULT_RECREATE = False


def first_non_empty(*values):
    for value in values:
        if value is not None and str(value) != "":
            return value
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare ReactLink column documents and embedding indexes.",
    )
    parser.add_argument("dataset", nargs="?", help="Dataset name.")
    parser.add_argument("--dataset_name", "--dataset-name", dest="dataset_name", default=None)
    parser.add_argument("--data_root", "--data-root", default=DATA_ROOT)
    parser.add_argument("--batch_size", "--batch-size", default=None)
    parser.add_argument(
        "--sentence_transformer_model",
        "--sentence-transformer-model",
        default=None,
    )
    parser.add_argument(
        "--recreate",
        nargs="?",
        const="true",
        default=None,
        help="Recreate docs and embeddings even if they already exist.",
    )
    parser.add_argument(
        "--no-recreate",
        action="store_const",
        const="false",
        dest="recreate",
        help="Reuse existing docs and embeddings when present.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_name = first_non_empty(args.dataset_name, args.dataset, DEFAULT_DATASET_NAME, DATASET_NAME)
    data_root = args.data_root
    batch_size = int(first_non_empty(args.batch_size, DEFAULT_BATCH_SIZE, BATCH_SIZE))
    sentence_transformer_model = first_non_empty(
        args.sentence_transformer_model,
        DEFAULT_SENTENCE_TRANSFORMER_MODEL,
        SENTENCE_TRANSFORMER_MODEL,
    )
    recreate = DEFAULT_RECREATE if args.recreate is None or str(args.recreate) == "" else parse_bool(args.recreate)

    documents_path = get_documents_path(dataset_name, data_root)
    embedding_index_path = get_embedding_index_path(dataset_name, data_root)
    embedding_metadata_path = get_embedding_metadata_path(dataset_name, data_root)

    if recreate or not os.path.isfile(documents_path):
        from generate_docs import generate_documents

        generate_documents(dataset_name=dataset_name, data_root=data_root)
    else:
        print(f"Documents already exist, skipping: {documents_path}")

    if (
        recreate
        or not os.path.isfile(embedding_index_path)
        or not os.path.isfile(embedding_metadata_path)
    ):
        from embedding_docs import embed_documents

        embed_documents(
            documents_path,
            get_embeddings_dir(dataset_name, data_root),
            batch_size=batch_size,
            model_name=sentence_transformer_model,
        )
    else:
        print(f"Embeddings already exist, skipping: {get_embeddings_dir(dataset_name, data_root)}")


if __name__ == "__main__":
    main()
