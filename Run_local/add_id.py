import json
import os
import argparse

from cost_tool import SampleCostRecorder
from utils import (
    DEFAULT_DATA_ROOT,
    DEFAULT_DATASET_NAME,
    DEFAULT_LOG_ROOT,
    INITIAL_VECTOR_RETRIEVED_COLUMNS_FILE,
    RULE_AUGMENTED_INITIAL_SCHEMA_FILE,
    get_cache_dir,
    get_embedding_metadata_path,
    get_pipeline_dir,
    get_sample_dir,
    get_status_dir,
    load_dataset_data,
    load_instance_cache,
    load_instance_status,
    parse_bool,
    pipeline_file,
    sample_file,
    save_instance_cache,
    save_instance_status,
    summary_file,
    table_db_id,
)


def refresh_retrieval_status_counts(status: dict, cache: dict, metadata: list[dict]) -> bool:
    before = json.dumps(status, sort_keys=True)
    allowed_db_ids = sorted(status.get("candidate_db_ids", [])) if status.get("scope") == "candidate_db_ids" else []

    scoped_indices = set()
    for index, record in enumerate(metadata):
        db_id = table_db_id(record.get("table", ""))
        if not allowed_db_ids or db_id in allowed_db_ids:
            scoped_indices.add(index)

    used_count = len(set(cache.get("used_indices", [])).intersection(scoped_indices))
    total_available = len(scoped_indices)
    remaining_count = max(0, total_available - used_count)

    status["total_available"] = int(total_available)
    status["used_count"] = int(used_count)
    status["remaining_count"] = int(remaining_count)
    status["total_available_in_scope"] = int(total_available)
    status["used_count_in_scope"] = int(used_count)
    status["remaining_count_in_scope"] = int(remaining_count)
    status["global_total_available"] = int(len(metadata))
    status["is_complete"] = remaining_count <= 0

    return before != json.dumps(status, sort_keys=True)


def add_pre_rule(
    log_path,
    dataset_name: str = DEFAULT_DATASET_NAME,
    data_root: str = DEFAULT_DATA_ROOT,
    write_sample_debug: bool = False,
):
    cache_path = get_cache_dir(log_path)
    status_path = get_status_dir(log_path)
    cost_output_path = summary_file(log_path, "cost.json")
    dataset_data = load_dataset_data(dataset_name, data_root)

    with open(pipeline_file(log_path, INITIAL_VECTOR_RETRIEVED_COLUMNS_FILE), "r", encoding="utf-8") as f:
        initial_candidates = json.load(f)

    add_id_candidates = {}
    metadata_path = get_embedding_metadata_path(dataset_name, data_root)
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    for instance_id, schema_info in initial_candidates.items():
        with SampleCostRecorder(
            sample_id=instance_id,
            output_path=cost_output_path,
        ):
            db_name = schema_info["db_name"]
            question = schema_info["question"]
            table_candidates = schema_info["table_candidates"]
            column_candidates = schema_info["column_candidates"]
            add_id_candidates[instance_id] = {
                "question": question,
                "db_name": db_name,
                "db_id": schema_info.get("db_id", dataset_data[instance_id]["db_id"]),
                "table_candidates": table_candidates,
                "column_candidates": column_candidates,
                "column_types": schema_info["column_types"].copy(),
                "column_values": schema_info["column_values"].copy(),
                "descriptions": schema_info["descriptions"].copy(),
            }

            status = load_instance_status(instance_id, status_path)
            cache = load_instance_cache(instance_id, cache_path)
            status_updated = refresh_retrieval_status_counts(status, cache, metadata)

            if status["is_complete"]:
                if status_updated:
                    save_instance_status(instance_id, status_path, status)
                continue

            seen_tables = []
            cache_updated = False

            for table in table_candidates:
                if table not in seen_tables:
                    seen_tables.append(table)
                else:
                    continue

                for index, all_columns in enumerate(metadata):
                    if all_columns["table"] != table:
                        continue

                    column =  all_columns["column"]
                    column_type = all_columns["column_type"]
                    column_value = all_columns["column_value"]
                    description = all_columns["description"]

                    if ("id" in column.lower() or "name" in column.lower() or "code" in column.lower()) and index not in cache["used_indices"]:
                        add_id_candidates[instance_id]["table_candidates"].append(table)
                        add_id_candidates[instance_id]["column_candidates"].append(column)
                        add_id_candidates[instance_id]["column_types"].append(column_type)
                        add_id_candidates[instance_id]["column_values"].append(column_value)
                        add_id_candidates[instance_id]["descriptions"].append(description)

                        cache["used_indices"].append(index)
                        cache_updated = True
                        status_updated = True

                        refresh_retrieval_status_counts(status, cache, metadata)
                        if status["is_complete"]:
                            break

                if status["is_complete"]:
                    break

            if status_updated:
                refresh_retrieval_status_counts(status, cache, metadata)
                save_instance_status(instance_id, status_path, status)

            if cache_updated:
                save_instance_cache(instance_id, cache_path, cache)

    os.makedirs(get_pipeline_dir(log_path), exist_ok=True)
    with open(pipeline_file(log_path, RULE_AUGMENTED_INITIAL_SCHEMA_FILE), "w", encoding="utf-8") as f:
        json.dump(add_id_candidates, f, ensure_ascii=False, indent=4)

    if write_sample_debug:
        for instance_id, schema_info in add_id_candidates.items():
            os.makedirs(get_sample_dir(log_path, instance_id), exist_ok=True)
            with open(sample_file(log_path, instance_id, RULE_AUGMENTED_INITIAL_SCHEMA_FILE), "w", encoding="utf-8") as f:
                json.dump(schema_info, f, ensure_ascii=False, indent=2)
    
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--log_path', type=str, default=os.path.join(DEFAULT_LOG_ROOT, DEFAULT_DATASET_NAME))
    parser.add_argument('--dataset_name', type=str, default=DEFAULT_DATASET_NAME)
    parser.add_argument('--data_root', type=str, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--write_sample_debug", type=parse_bool, default=False)
    args = parser.parse_args()

    add_pre_rule(args.log_path, args.dataset_name, args.data_root, write_sample_debug=args.write_sample_debug)
