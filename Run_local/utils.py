import os
import json
import re

from config import (
    PROJECT_ROOT,
    DEFAULT_DATA_ROOT,
    DEFAULT_DATASET_NAME,
    DEFAULT_LOG_ROOT,
    parse_bool,
)

SUMMARY_DIR_NAME = "_summary"
CACHE_DIR_NAME = "cache"
STATUS_DIR_NAME = "status"
BACKUP_DIR_NAME = "backup"
PIPELINE_DIR_NAME = "_pipeline"
INITIAL_VECTOR_RETRIEVED_COLUMNS_FILE = "initial_vector_retrieved_columns.json"
RULE_AUGMENTED_INITIAL_SCHEMA_FILE = "rule_augmented_initial_schema.json"
AGENT_SCHEMA_LINKING_ACTIONS_FILE = "agent_schema_linking_actions.json"
AGENT_LINKED_COLUMNS_FILE = "agent_linked_columns.json"
AGENT_UNLINKED_COLUMNS_FILE = "agent_unlinked_columns.json"
FINAL_PROMPT_LINKED_SCHEMA_FILE = "final_prompt_linked_schema.json"
FINAL_SCHEMA_LINKING_COLUMNS_FILE = "final_schema_linking_columns.json"
SCHEMA_LINKING_PROMPT_FILE = "schema_linking_prompt.txt"
FINAL_SCHEMA_PROMPT_DIR_NAME = "final_schema_prompt"
MODEL_OUTPUT_FILE = "model_output.txt"
INPUT_MESSAGES_FILE = "input_messages.txt"
ERROR_FILE = "error.txt"
SCHEMA_LINKING_STATUS_FILE = "schema_linking_status.json"
RESULT_MANIFEST_FILE = "result_manifest.json"


def resolve_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    cwd_path = os.path.abspath(path)
    if os.path.exists(cwd_path):
        return cwd_path
    return os.path.abspath(os.path.join(PROJECT_ROOT, path))


def get_dataset_root(dataset_name: str = DEFAULT_DATASET_NAME, data_root: str = DEFAULT_DATA_ROOT) -> str:
    return os.path.join(resolve_path(data_root), dataset_name)


def get_dataset_schema_name(dataset_name: str = DEFAULT_DATASET_NAME) -> str:
    return dataset_name


def get_db_info_path(dataset_name: str = DEFAULT_DATASET_NAME, data_root: str = DEFAULT_DATA_ROOT) -> str:
    return os.path.join(get_dataset_root(dataset_name, data_root), "db_info.json")


def get_gold_sl_path(dataset_name: str = DEFAULT_DATASET_NAME, data_root: str = DEFAULT_DATA_ROOT) -> str:
    return os.path.join(get_dataset_root(dataset_name, data_root), "gold_sl.json")


def get_gold_sql_path(dataset_name: str = DEFAULT_DATASET_NAME, data_root: str = DEFAULT_DATA_ROOT) -> str:
    return os.path.join(get_dataset_root(dataset_name, data_root), "gold_sql.json")


def get_sqlite_dir(dataset_name: str = DEFAULT_DATASET_NAME, data_root: str = DEFAULT_DATA_ROOT) -> str:
    return os.path.join(get_dataset_root(dataset_name, data_root), "Sqlite_database")


def get_documents_dir(dataset_name: str = DEFAULT_DATASET_NAME, data_root: str = DEFAULT_DATA_ROOT) -> str:
    return os.path.join(get_dataset_root(dataset_name, data_root), "documents")


def get_documents_path(dataset_name: str = DEFAULT_DATASET_NAME, data_root: str = DEFAULT_DATA_ROOT) -> str:
    return os.path.join(get_documents_dir(dataset_name, data_root), "column_documents.json")


def get_embeddings_dir(dataset_name: str = DEFAULT_DATASET_NAME, data_root: str = DEFAULT_DATA_ROOT) -> str:
    return os.path.join(get_dataset_root(dataset_name, data_root), "embeddings")


def get_embedding_index_path(dataset_name: str = DEFAULT_DATASET_NAME, data_root: str = DEFAULT_DATA_ROOT) -> str:
    return os.path.join(get_embeddings_dir(dataset_name, data_root), "index.faiss")


def get_embedding_metadata_path(dataset_name: str = DEFAULT_DATASET_NAME, data_root: str = DEFAULT_DATA_ROOT) -> str:
    return os.path.join(get_embeddings_dir(dataset_name, data_root), "metadata.json")


def get_summary_dir(log_path: str) -> str:
    return os.path.join(resolve_path(log_path), SUMMARY_DIR_NAME)


def get_cache_dir(log_path: str) -> str:
    return os.path.join(resolve_path(log_path), CACHE_DIR_NAME)


def get_status_dir(log_path: str) -> str:
    return os.path.join(resolve_path(log_path), STATUS_DIR_NAME)


def get_backup_dir(log_path: str) -> str:
    return os.path.join(resolve_path(log_path), BACKUP_DIR_NAME)


def get_pipeline_dir(log_path: str) -> str:
    return os.path.join(get_cache_dir(log_path), PIPELINE_DIR_NAME)


def get_sample_dir(log_path: str, data_id: str) -> str:
    return os.path.join(resolve_path(log_path), str(data_id))


def get_pipeline_sample_dir(log_path: str, data_id: str) -> str:
    return os.path.join(get_pipeline_dir(log_path), "samples", str(data_id))


def get_final_schema_prompt_dir(log_path: str) -> str:
    return os.path.join(resolve_path(log_path), FINAL_SCHEMA_PROMPT_DIR_NAME)


def ensure_sample_dir(log_path: str, data_id: str) -> str:
    sample_dir = get_sample_dir(log_path, data_id)
    os.makedirs(sample_dir, exist_ok=True)
    return sample_dir


def summary_file(log_path: str, filename: str) -> str:
    return os.path.join(get_summary_dir(log_path), filename)


def cache_file(log_path: str, filename: str) -> str:
    return os.path.join(get_cache_dir(log_path), filename)


def status_file(log_path: str, filename: str) -> str:
    return os.path.join(get_status_dir(log_path), filename)


def backup_file(log_path: str, filename: str) -> str:
    return os.path.join(get_backup_dir(log_path), filename)


def pipeline_file(log_path: str, filename: str) -> str:
    return os.path.join(get_pipeline_dir(log_path), filename)


def sample_file(log_path: str, data_id: str, filename: str) -> str:
    return os.path.join(get_sample_dir(log_path, data_id), filename)


def final_schema_prompt_file(log_path: str, data_id: str) -> str:
    return os.path.join(get_final_schema_prompt_dir(log_path), f"{data_id}.txt")


def pipeline_sample_file(log_path: str, data_id: str, filename: str) -> str:
    return os.path.join(get_pipeline_sample_dir(log_path, data_id), filename)


def _json_default(value):
    if hasattr(value, "item") and type(value).__module__.startswith("numpy"):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def load_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, payload, indent: int = 2) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=indent, default=_json_default)


def load_instance_cache(instance_id: str, cache_dir: str) -> dict:
    return load_json(os.path.join(cache_dir, f"{instance_id}.json"), {"used_indices": []})


def save_instance_cache(instance_id: str, cache_dir: str, cache_data: dict) -> None:
    if "used_indices" in cache_data:
        cache_data["used_indices"] = [int(idx) for idx in cache_data["used_indices"]]
    write_json(os.path.join(cache_dir, f"{instance_id}.json"), cache_data)


def load_instance_status(instance_id: str, status_dir: str) -> dict:
    return load_json(
        os.path.join(status_dir, f"{instance_id}.json"),
        {
            "is_complete": False,
            "total_available": 0,
            "used_count": 0,
            "remaining_count": 0,
        },
    )


def save_instance_status(instance_id: str, status_dir: str, status_data: dict) -> None:
    write_json(os.path.join(status_dir, f"{instance_id}.json"), status_data)


def load_agent_columns(path: str) -> list:
    payload = load_json(path, {})
    return payload.get("columns", []) if isinstance(payload, dict) else []


def load_schema_linking_status(path: str) -> dict:
    return load_json(path, {})


def load_dataset_data(dataset_name: str = DEFAULT_DATASET_NAME, data_root: str = DEFAULT_DATA_ROOT):
    data_file = get_gold_sl_path(dataset_name, data_root)
    with open(data_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    dataset_schema_name = get_dataset_schema_name(dataset_name)
    normalized = {}

    items = raw_data.items() if isinstance(raw_data, dict) else enumerate(raw_data)
    for fallback_id, item in items:
        data_id = str(item.get("id", fallback_id))
        normalized[data_id] = {
            "id": data_id,
            "question": item["question"],
            "db_name": dataset_schema_name,
            "db_id": item["db_id"],
            "tables": item.get("tables", []),
            "columns_by_table": item.get("columns_by_table", {}),
            "external_knowledge": item.get("external_knowledge"),
        }

    return normalized


def determine_embedding_path(
    instance_id: str,
    dataset_name: str = DEFAULT_DATASET_NAME,
    data_root: str = DEFAULT_DATA_ROOT,
) -> str:
    return get_embeddings_dir(dataset_name, data_root)


def table_db_id(table: str) -> str:
    if "." not in table:
        return ""
    return table.split(".", 1)[0]


def record_db_ids(records: list) -> list:
    db_ids = []
    seen = set()
    for record in records:
        db_id = table_db_id(record.get("table", ""))
        if db_id and db_id not in seen:
            seen.add(db_id)
            db_ids.append(db_id)
    return db_ids


def derive_schema_result_status(is_finished: bool, is_error: bool) -> str:
    if is_finished:
        return "finished"
    if is_error:
        return "error"
    return "best_effort"


def build_schema_result_snapshot(
    selected_db_id: str | None,
    final_records: list,
    is_finished: bool,
    is_error: bool,
    termination_reason: str | None = None,
    error_message: str | None = None,
) -> dict:
    status = derive_schema_result_status(is_finished, is_error)
    final_db_ids = record_db_ids(final_records)
    normalized_termination_reason = termination_reason or status
    is_usable = status != "error" and len(final_records) > 0 and len(final_db_ids) == 1

    return {
        "status": status,
        "termination_reason": normalized_termination_reason,
        "selected_db_id": selected_db_id,
        "final_db_ids": final_db_ids,
        "final_column_count": len(final_records),
        "is_usable": is_usable,
        "error_message": error_message,
    }


def parse_model_output(output: str):
    full_lines = []
    tool_calls = []

    call_types = [
        "@select_database",
        "@find_relevant_columns",
        "@inspect_database",
        "@test_sql",
        "@link_column",
        "@unlink_column",
        "@finish_schema_linking",
    ]
    
    lines = output.splitlines()
    lines = [line.strip() for line in lines]
    i = 0
    blocks = []
    
    while i < len(lines):
        line = lines[i]

        if any(line.startswith(call_type) for call_type in call_types):
            stack = []
            block_lines = [line]
            
            open_pos = line.find('(')
            if open_pos != -1:
                stack.append('(')

                for c in line[open_pos+1:]:
                    if c == '(':
                        stack.append('(')
                    elif c == ')':
                        stack.pop()  
                        if not stack:  
                            break
                
                j = i + 1
                while stack and j < len(lines):
                    next_line = lines[j].strip()
                    block_lines.append(next_line)
                    
                    for c in next_line:
                        if c == '(':
                            stack.append('(')
                        elif c == ')':
                            if stack:  
                                stack.pop()
                            if not stack:  
                                break
                    
                    j += 1
                    if not stack:  
                        break
                
                i = j
                blocks.append('\n'.join(block_lines))
            else:
                i += 1
        else:
            i += 1
    
    for block in blocks:
        for call_type in call_types:
            if block.strip().startswith(call_type):
                full_lines.append(block)

                if call_type == "@find_relevant_columns":
                    query = extract_call_argument(block, "query")
                    tool_calls.append({
                        "tool": "find_relevant_columns",
                        "query": query,
                    })

                elif call_type == "@select_database":
                    db_id_match = re.search(r'db_id\s*[:=]\s*["\']([^"\']*)["\']', block)
                    reason_match = re.search(r'reason\s*[:=]\s*["\']([^"\']*)["\']', block)
                    tool_calls.append({
                        "tool": "select_database",
                        "db_id": db_id_match.group(1) if db_id_match else "",
                        "reason": reason_match.group(1) if reason_match else "",
                    })

                elif call_type == "@inspect_database":
                    query = extract_call_argument(block, "query")
                    tool_calls.append({
                        "tool": "inspect_database",
                        "query": query,
                    })

                elif call_type == "@test_sql":
                    query = extract_call_argument(block, "query")
                    tool_calls.append({
                        "tool": "test_sql",
                        "query": query,
                    })

                elif call_type == "@link_column":
                    table_match = re.search(r'table\s*[:=]\s*["\']([^"\']*)["\']', block)
                    column_match = re.search(r'column\s*[:=]\s*["\']([^"\']*)["\']', block)

                    tool_calls.append({
                        "tool": "link_column",
                        "table": table_match.group(1) if table_match else "",
                        "column": column_match.group(1) if column_match else "",
                    })

                elif call_type == "@unlink_column":
                    table_match = re.search(r'table\s*[:=]\s*["\']([^"\']*)["\']', block)
                    column_match = re.search(r'column\s*[:=]\s*["\']([^"\']*)["\']', block)

                    tool_calls.append({
                        "tool": "unlink_column",
                        "table": table_match.group(1) if table_match else "",
                        "column": column_match.group(1) if column_match else ""
                    })

                elif call_type == "@finish_schema_linking":
                    tool_calls.append({
                        "tool": "finish_schema_linking"
                    })
                break

    return full_lines, tool_calls


def extract_call_argument(block: str, argument_name: str) -> str:
    query_match = re.search(rf'{argument_name}\s*[:=]\s*"""(.*?)"""', block, re.DOTALL)
    if not query_match:
        query_match = re.search(rf"{argument_name}\s*[:=]\s*'''(.*?)'''", block, re.DOTALL)
    if not query_match:
        query_match = re.search(rf'{argument_name}\s*[:=]\s*["\']([^"\']*)["\']', block)

    if query_match:
        return query_match.group(1)

    query_start = re.search(rf'{argument_name}\s*[:=]\s*', block)
    if not query_start:
        return ""

    query_text = block[query_start.end():].strip()
    if query_text.startswith('"') or query_text.startswith("'"):
        quote = query_text[0]
        return query_text[1:-1] if query_text.endswith(quote) else query_text[1:]

    if query_text.endswith(")"):
        query_text = query_text[:-1].strip()

    return query_text


def column_key(table: str, column: str) -> str:
    return f"{table.lower()}::{column.lower()}"


def schema_to_records(schema_info: dict) -> list:
    records = []
    for table, column, column_type, column_value, description in zip(
        schema_info.get("table_candidates", []),
        schema_info.get("column_candidates", []),
        schema_info.get("column_types", []),
        schema_info.get("column_values", []),
        schema_info.get("descriptions", []),
    ):
        records.append({
            "table": table,
            "column": column,
            "column_type": column_type,
            "column_value": column_value,
            "description": description,
        })
    return records


def merge_schema_records(
    initial_records: list,
    linked_records: list,
    unlinked_records: list,
    selected_db_id: str | None = None,
) -> list:
    removed_keys = {column_key(record["table"], record["column"]) for record in unlinked_records}
    final_records = []
    seen = set()

    for record in initial_records + linked_records:
        if selected_db_id and table_db_id(record.get("table", "")) != selected_db_id:
            continue
        key = column_key(record["table"], record["column"])
        if key in removed_keys or key in seen:
            continue
        seen.add(key)
        final_records.append(record)

    return final_records


def records_to_schema(question: str, db_name: str, records: list, db_id: str | None = None) -> dict:
    schema = {
        "question": question,
        "db_name": db_name,
        "table_candidates": [],
        "column_candidates": [],
        "column_types": [],
        "column_values": [],
        "descriptions": [],
    }
    if db_id is not None:
        schema["db_id"] = db_id

    seen = set()
    for record in records:
        key = column_key(record["table"], record["column"])
        if key in seen:
            continue
        seen.add(key)
        schema["table_candidates"].append(record["table"])
        schema["column_candidates"].append(record["column"])
        schema["column_types"].append(record.get("column_type", ""))
        schema["column_values"].append(record.get("column_value", []))
        schema["descriptions"].append(record.get("description", ""))

    return schema


def write_sample_and_summary(log_path: str, data_id: str, filename: str, sample_payload: dict, summary_payload: dict):
    os.makedirs(get_summary_dir(log_path), exist_ok=True)
    os.makedirs(get_sample_dir(log_path, data_id), exist_ok=True)
    with open(sample_file(log_path, data_id, filename), "w", encoding="utf-8") as f:
        json.dump(sample_payload, f, ensure_ascii=False, indent=2)
    with open(summary_file(log_path, filename), "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, ensure_ascii=False, indent=2)
