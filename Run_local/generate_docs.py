import json
import os
import argparse

from utils import (
    DEFAULT_DATA_ROOT,
    DEFAULT_DATASET_NAME,
    get_db_info_path,
    get_documents_dir,
    get_documents_path,
    get_dataset_schema_name,
)


def qualify_table_name(db_id: str, table_name: str) -> str:
    return f"{db_id}.{table_name}"


def generate_documents(dataset_name: str = DEFAULT_DATASET_NAME, data_root: str = DEFAULT_DATA_ROOT):
    db_info_path = get_db_info_path(dataset_name, data_root)
    with open(db_info_path, "r", encoding="utf-8") as f:
        schemas = json.load(f)

    schema_name = get_dataset_schema_name(dataset_name)
    documents = {schema_name: {}}

    for schema in schemas:
        db_id = schema["db_id"]
        table_names = schema["table_names"]
        column_names = schema["column_names"]
        column_types = schema["column_types"]
        column_descriptions = schema["column_descriptions"]
        sample_rows = schema.get("sample_rows", {})

        tables = {}
        for table_name in table_names:
            qualified_table_name = qualify_table_name(db_id, table_name)
            tables[table_name] = {
                "qualified_table_name": qualified_table_name,
                "columns": [],
                "column_types": [],
                "descriptions": [],
                "sample_rows": sample_rows.get(table_name, []),
            }

        for idx in range(1, len(column_names)):
            table_idx, column_name = column_names[idx]
            if table_idx < 0:
                continue

            table_name = table_names[table_idx]
            tables[table_name]["columns"].append(column_name)
            tables[table_name]["column_types"].append(column_types[idx])

            column_desc = column_descriptions[idx]
            tables[table_name]["descriptions"].append("" if column_desc is None else column_desc)

        for table_name, table_info in tables.items():
            qualified_table_name = table_info["qualified_table_name"]
            documents[schema_name][qualified_table_name] = {
                "similar_tables": [],
                "columns": {},
                "column_types": table_info["column_types"],
                "sample_values": [],
            }

            for column_name in table_info["columns"]:
                column_values = []
                for sample_row in table_info["sample_rows"]:
                    column_values.append(str(sample_row.get(column_name, "")))
                documents[schema_name][qualified_table_name]["sample_values"].append(column_values)

            for column_name, column_type, column_desc in zip(
                table_info["columns"],
                table_info["column_types"],
                table_info["descriptions"],
            ):
                desc = (
                    "column name: " + column_name + "\n"
                    + "column type: " + column_type + "\n"
                    + "table name: " + qualified_table_name + "\n"
                    + "description: " + column_desc + "\n"
                )
                documents[schema_name][qualified_table_name]["columns"][column_name] = desc

    os.makedirs(get_documents_dir(dataset_name, data_root), exist_ok=True)
    output_file = get_documents_path(dataset_name, data_root)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=4, ensure_ascii=False)
    print(f"Documents saved to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset_name", type=str, default=DEFAULT_DATASET_NAME)
    parser.add_argument("--data_root", type=str, default=DEFAULT_DATA_ROOT)
    args = parser.parse_args()

    print(f"Generate documents for {args.dataset_name} global SQLite space...")
    generate_documents(dataset_name=args.dataset_name, data_root=args.data_root)
