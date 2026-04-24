import json
import os

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm import tqdm


MODEL_NAME = os.environ.get("SENTENCE_TRANSFORMER_MODEL", "BAAI/bge-large-en-v1.5")


def embed_documents(input_file: str, embed_path: str, batch_size: int = 32):
    os.makedirs(embed_path, exist_ok=True)

    model = SentenceTransformer(MODEL_NAME)

    with open(input_file, "r", encoding="utf-8") as f:
        documents = json.load(f)

    for db_name, tables in tqdm(documents.items()):
        db_dir = os.path.join(embed_path, db_name)
        os.makedirs(db_dir, exist_ok=True)

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
            batch_embeddings = model.encode(batch_descriptions, convert_to_numpy=True)
            db_embeddings.extend(batch_embeddings)

        if not db_embeddings:
            raise ValueError(f"No descriptions found for database {db_name}.")

        dimension = len(db_embeddings[0])
        index = faiss.IndexFlatL2(dimension)
        index.add(np.array(db_embeddings, dtype=np.float32))

        faiss.write_index(index, os.path.join(db_dir, "index.faiss"))
        with open(os.path.join(db_dir, "metadata.json"), "w", encoding="utf-8") as f_meta:
            json.dump(metadata_mapping, f_meta, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print("Embedding MMQA global SQLite documents...")
    embed_documents(os.path.join("documents", "localdb.json"), "embeddings/localdb", batch_size=1024)
