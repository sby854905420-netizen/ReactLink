import json
import os
import argparse

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from config import BATCH_SIZE, SENTENCE_TRANSFORMER_MODEL
from utils import DEFAULT_DATA_ROOT, DEFAULT_DATASET_NAME, get_documents_path, get_embeddings_dir

MODEL_NAME = os.environ.get("SENTENCE_TRANSFORMER_MODEL", SENTENCE_TRANSFORMER_MODEL)


def embed_documents(input_file: str, embed_path: str, batch_size: int = 32, model_name: str = MODEL_NAME):
    os.makedirs(embed_path, exist_ok=True)

    model = SentenceTransformer(model_name)

    with open(input_file, "r", encoding="utf-8") as f:
        documents = json.load(f)

    for db_name, tables in tqdm(documents.items()):
        all_descriptions = []
        metadata_mapping = []

        for table_name, table_info in tables.items():
            columns = table_info["columns"]
            column_types = table_info["column_types"]
            column_values = table_info["sample_values"]

            if len(columns) != len(column_types) or len(columns) != len(column_values):
                print(f"Warning: Length mismatch in table {table_name} of database {db_name}.")
                print(
                    f"Columns: {len(columns)}, Column Types: {len(column_types)}, "
                    f"Column Values: {len(column_values)}"
                )

            for (column_name, desc), column_type, column_value in zip(
                columns.items(), column_types, column_values
            ):
                all_descriptions.append(desc)
                metadata_mapping.append(
                    {
                        "table": table_name,
                        "column": column_name,
                        "column_type": column_type,
                        "column_value": column_value,
                        "description": desc,
                    }
                )

        db_embeddings = []
        for i in tqdm(range(0, len(all_descriptions), batch_size), desc=f"Embedding {db_name}", leave=False):
            batch_descriptions = all_descriptions[i:i + batch_size]
            batch_embeddings = model.encode(
                batch_descriptions,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            db_embeddings.extend(batch_embeddings)

        if not db_embeddings:
            raise ValueError(f"No descriptions found for database {db_name}.")

        dimension = len(db_embeddings[0])
        index = faiss.IndexFlatIP(dimension)
        index.add(np.array(db_embeddings, dtype=np.float32))

        faiss.write_index(index, os.path.join(embed_path, "index.faiss"))
        with open(os.path.join(embed_path, "metadata.json"), "w", encoding="utf-8") as f_meta:
            json.dump(metadata_mapping, f_meta, ensure_ascii=False, indent=2)
        print(f"Embedding index for {db_name} saved to {embed_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset_name", type=str, default=DEFAULT_DATASET_NAME)
    parser.add_argument("--data_root", type=str, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--batch_size", type=int, default=BATCH_SIZE)
    parser.add_argument("--sentence_transformer_model", type=str, default=MODEL_NAME)
    args = parser.parse_args()

    print(f"Embedding {args.dataset_name} global SQLite documents...")
    embed_documents(
        get_documents_path(args.dataset_name, args.data_root),
        get_embeddings_dir(args.dataset_name, args.data_root),
        batch_size=args.batch_size,
        model_name=args.sentence_transformer_model,
    )
