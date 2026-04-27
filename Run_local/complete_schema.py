import argparse
import json
import os
import re
import shutil
import sqlite3
from urllib import error as urllib_error
from urllib import request as urllib_request

import pandas as pd
from tqdm import tqdm

from config import (
    AGENT_RETRIEVAL_TOP_K as CONFIG_AGENT_RETRIEVAL_TOP_K,
    CANDIDATE_DB_MIN_HIT_COUNT as CONFIG_CANDIDATE_DB_MIN_HIT_COUNT,
    CANDIDATE_DB_STRONG_DISTANCE_QUANTILE as CONFIG_CANDIDATE_DB_STRONG_DISTANCE_QUANTILE,
    ENABLE_CONTEXT_CONTROL as CONFIG_ENABLE_CONTEXT_CONTROL,
    MAX_CONTEXT_CHARS as CONFIG_MAX_CONTEXT_CHARS,
    MAX_DATABASE_SWITCHES as CONFIG_MAX_DATABASE_SWITCHES,
    MAX_MEMORY_ACTIONS as CONFIG_MAX_MEMORY_ACTIONS,
    MAX_MEMORY_OBSERVED_COLUMNS as CONFIG_MAX_MEMORY_OBSERVED_COLUMNS,
    MAX_MEMORY_SCHEMA_CHARS as CONFIG_MAX_MEMORY_SCHEMA_CHARS,
    MAX_MEMORY_SQL_TESTS as CONFIG_MAX_MEMORY_SQL_TESTS,
    MAX_RECENT_TURN_CHARS as CONFIG_MAX_RECENT_TURN_CHARS,
    MODEL_DISCUSSION_TURNS as CONFIG_MODEL_DISCUSSION_TURNS,
    OLLAMA_BASE_URL as CONFIG_OLLAMA_BASE_URL,
    OLLAMA_MODEL as CONFIG_OLLAMA_MODEL,
    RECENT_CONTEXT_TURNS as CONFIG_RECENT_CONTEXT_TURNS,
    RETRIEVAL_DEVICE as CONFIG_RETRIEVAL_DEVICE,
    SENTENCE_TRANSFORMER_MODEL,
    get_env,
)
from cost_tool import SampleCostRecorder
from prompt_template import SCHEMA_LINKING, SQLITE, SQLITE_DIALECT_OPTIMIZATION, USER_INPUT
from retrieve_topk_schema import get_next_k_results, update_instance_retrieval_scope
from utils import (
    AGENT_LINKED_COLUMNS_FILE,
    AGENT_SCHEMA_LINKING_ACTIONS_FILE,
    AGENT_UNLINKED_COLUMNS_FILE,
    DEFAULT_DATA_ROOT,
    DEFAULT_DATASET_NAME,
    DEFAULT_LOG_ROOT,
    ERROR_FILE,
    INITIAL_VECTOR_RETRIEVED_COLUMNS_FILE,
    INPUT_MESSAGES_FILE,
    MODEL_OUTPUT_FILE,
    RULE_AUGMENTED_INITIAL_SCHEMA_FILE,
    SCHEMA_LINKING_PROMPT_FILE,
    SCHEMA_LINKING_STATUS_FILE,
    build_schema_result_snapshot,
    column_key,
    get_backup_dir,
    get_cache_dir,
    get_documents_path,
    get_embedding_metadata_path,
    get_embeddings_dir,
    get_gold_sl_path,
    get_pipeline_dir,
    get_pipeline_sample_dir,
    get_sample_dir,
    get_sqlite_dir,
    get_status_dir,
    get_summary_dir,
    load_dataset_data,
    load_schema_linking_status,
    merge_schema_records,
    parse_bool,
    parse_model_output,
    pipeline_file,
    pipeline_sample_file,
    sample_file,
    schema_to_records,
    status_file,
    summary_file,
    table_db_id,
    write_json,
)


OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", CONFIG_OLLAMA_BASE_URL).rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", CONFIG_OLLAMA_MODEL)
QUALIFIED_TABLE_PATTERN = re.compile(r'"([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)"')
QUOTED_DB_TABLE_PATTERN = re.compile(r'"([A-Za-z0-9_]+)"\s*\.\s*"([A-Za-z0-9_]+)"')
QUOTED_DB_UNQUOTED_TABLE_PATTERN = re.compile(r'"([A-Za-z0-9_]+)"\s*\.\s*([A-Za-z0-9_]+)\b')
QUOTED_PRAGMA_PATTERN = re.compile(r'"([A-Za-z0-9_]+)"\s*\.\s*pragma_table_info\s*\(', re.IGNORECASE)
UNQUOTED_DB_TABLE_PATTERN = re.compile(r'(?<![\w"])\b([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\b')

CANDIDATE_DB_MIN_HIT_COUNT = get_env(
    "CANDIDATE_DB_MIN_HIT_COUNT",
    CONFIG_CANDIDATE_DB_MIN_HIT_COUNT,
    int,
    aliases=("REACTLINK_CANDIDATE_DB_MIN_HIT_COUNT",),
)
CANDIDATE_DB_STRONG_DISTANCE_QUANTILE = get_env(
    "CANDIDATE_DB_STRONG_DISTANCE_QUANTILE",
    CONFIG_CANDIDATE_DB_STRONG_DISTANCE_QUANTILE,
    float,
    aliases=("REACTLINK_CANDIDATE_DB_STRONG_DISTANCE_QUANTILE",),
)
MAX_DATABASE_SWITCHES = get_env(
    "MAX_DATABASE_SWITCHES",
    CONFIG_MAX_DATABASE_SWITCHES,
    int,
    aliases=("REACTLINK_MAX_DATABASE_SWITCHES",),
)
ENABLE_CONTEXT_CONTROL = get_env(
    "ENABLE_CONTEXT_CONTROL",
    CONFIG_ENABLE_CONTEXT_CONTROL,
    bool,
    aliases=("REACTLINK_ENABLE_CONTEXT_CONTROL",),
)
MAX_CONTEXT_CHARS = get_env(
    "MAX_CONTEXT_CHARS",
    CONFIG_MAX_CONTEXT_CHARS,
    int,
    aliases=("REACTLINK_MAX_CONTEXT_CHARS",),
)
RECENT_CONTEXT_TURNS = get_env(
    "RECENT_CONTEXT_TURNS",
    CONFIG_RECENT_CONTEXT_TURNS,
    int,
    aliases=("REACTLINK_RECENT_CONTEXT_TURNS",),
)
MAX_MEMORY_ACTIONS = get_env(
    "MAX_MEMORY_ACTIONS",
    CONFIG_MAX_MEMORY_ACTIONS,
    int,
    aliases=("REACTLINK_MAX_MEMORY_ACTIONS",),
)
MAX_MEMORY_OBSERVED_COLUMNS = get_env(
    "MAX_MEMORY_OBSERVED_COLUMNS",
    CONFIG_MAX_MEMORY_OBSERVED_COLUMNS,
    int,
    aliases=("REACTLINK_MAX_MEMORY_OBSERVED_COLUMNS",),
)
MAX_MEMORY_SQL_TESTS = get_env(
    "MAX_MEMORY_SQL_TESTS",
    CONFIG_MAX_MEMORY_SQL_TESTS,
    int,
    aliases=("REACTLINK_MAX_MEMORY_SQL_TESTS",),
)
MAX_MEMORY_SCHEMA_CHARS = get_env(
    "MAX_MEMORY_SCHEMA_CHARS",
    CONFIG_MAX_MEMORY_SCHEMA_CHARS,
    int,
    aliases=("REACTLINK_MAX_MEMORY_SCHEMA_CHARS",),
)
MAX_RECENT_TURN_CHARS = get_env(
    "MAX_RECENT_TURN_CHARS",
    CONFIG_MAX_RECENT_TURN_CHARS,
    int,
    aliases=("REACTLINK_MAX_RECENT_TURN_CHARS",),
)
MODEL_DISCUSSION_TURNS = get_env(
    "MODEL_DISCUSSION_TURNS",
    CONFIG_MODEL_DISCUSSION_TURNS,
    int,
    aliases=("REACTLINK_MODEL_DISCUSSION_TURNS",),
)
AGENT_RETRIEVAL_TOP_K = get_env(
    "AGENT_RETRIEVAL_TOP_K",
    CONFIG_AGENT_RETRIEVAL_TOP_K,
    int,
    aliases=("REACTLINK_AGENT_RETRIEVAL_TOP_K",),
)
RETRIEVAL_DEVICE = get_env(
    "RETRIEVAL_DEVICE",
    CONFIG_RETRIEVAL_DEVICE,
    aliases=("REACTLINK_RETRIEVAL_DEVICE",),
)
CONTEXT_TOKEN_USAGE_FILE = "context_token_usage.json"
RAW_INPUT_MESSAGES_FILE = "input_messages_raw.txt"


def configure_runtime(args):
    global OLLAMA_BASE_URL
    global OLLAMA_MODEL
    global CANDIDATE_DB_MIN_HIT_COUNT
    global CANDIDATE_DB_STRONG_DISTANCE_QUANTILE
    global MAX_DATABASE_SWITCHES
    global ENABLE_CONTEXT_CONTROL
    global MAX_CONTEXT_CHARS
    global RECENT_CONTEXT_TURNS
    global MAX_MEMORY_ACTIONS
    global MAX_MEMORY_OBSERVED_COLUMNS
    global MAX_MEMORY_SQL_TESTS
    global MAX_MEMORY_SCHEMA_CHARS
    global MAX_RECENT_TURN_CHARS
    global MODEL_DISCUSSION_TURNS
    global AGENT_RETRIEVAL_TOP_K
    global RETRIEVAL_DEVICE

    OLLAMA_BASE_URL = args.ollama_base_url.rstrip("/")
    OLLAMA_MODEL = args.ollama_model
    CANDIDATE_DB_MIN_HIT_COUNT = args.candidate_db_min_hit_count
    CANDIDATE_DB_STRONG_DISTANCE_QUANTILE = args.candidate_db_strong_distance_quantile
    MAX_DATABASE_SWITCHES = args.max_database_switches
    ENABLE_CONTEXT_CONTROL = args.enable_context_control
    MAX_CONTEXT_CHARS = args.max_context_chars
    RECENT_CONTEXT_TURNS = args.recent_context_turns
    MAX_MEMORY_ACTIONS = args.max_memory_actions
    MAX_MEMORY_OBSERVED_COLUMNS = args.max_memory_observed_columns
    MAX_MEMORY_SQL_TESTS = args.max_memory_sql_tests
    MAX_MEMORY_SCHEMA_CHARS = args.max_memory_schema_chars
    MAX_RECENT_TURN_CHARS = args.max_recent_turn_chars
    MODEL_DISCUSSION_TURNS = args.model_discussion_turns
    AGENT_RETRIEVAL_TOP_K = args.agent_retrieval_top_k
    RETRIEVAL_DEVICE = args.retrieval_device

    if args.sentence_transformer_model:
        os.environ["SENTENCE_TRANSFORMER_MODEL"] = args.sentence_transformer_model


def chat_with_ollama(messages):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }

    request = urllib_request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib_request.urlopen(request, timeout=600) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP error {e.code}: {body}") from e
    except urllib_error.URLError as e:
        raise RuntimeError(f"Failed to connect to Ollama at {OLLAMA_BASE_URL}: {e}") from e

    message = response_data.get("message", {})
    content = message.get("content", "")
    if not content:
        raise RuntimeError(f"Ollama returned an empty response: {response_data}")
    return content, response_data


def normalize_attached_table_references(sql: str) -> str:
    return QUALIFIED_TABLE_PATTERN.sub(r'"\1"."\2"', sql)


def load_available_db_ids(sqlite_dir: str):
    return {
        os.path.splitext(filename)[0]
        for filename in os.listdir(sqlite_dir)
        if filename.endswith(".sqlite")
    }


def extract_referenced_db_ids(sql: str, available_db_ids: set):
    db_ids = set()

    for match in QUOTED_DB_TABLE_PATTERN.finditer(sql):
        db_id = match.group(1)
        if db_id in available_db_ids:
            db_ids.add(db_id)

    for match in QUOTED_DB_UNQUOTED_TABLE_PATTERN.finditer(sql):
        db_id = match.group(1)
        if db_id in available_db_ids:
            db_ids.add(db_id)

    for match in QUOTED_PRAGMA_PATTERN.finditer(sql):
        db_id = match.group(1)
        if db_id in available_db_ids:
            db_ids.add(db_id)

    for match in UNQUOTED_DB_TABLE_PATTERN.finditer(sql):
        db_id = match.group(1)
        if db_id in available_db_ids:
            db_ids.add(db_id)

    return sorted(db_ids)


def build_sqlite_connection(db_ids, sqlite_dir: str):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    for db_id in db_ids:
        db_path = os.path.join(sqlite_dir, f"{db_id}.sqlite")
        conn.execute(f'ATTACH DATABASE ? AS "{db_id}"', (db_path,))
    return conn


def backup_instance_state(instance_id: str, log_path: str):
    cache_dir = get_cache_dir(log_path)
    status_dir = get_status_dir(log_path)
    backup_dir = get_backup_dir(log_path)

    os.makedirs(backup_dir, exist_ok=True)

    cache_file = os.path.join(cache_dir, f"{instance_id}.json")
    status_file = os.path.join(status_dir, f"{instance_id}.json")

    backup_cache_file = os.path.join(backup_dir, f"{instance_id}_cache.json")
    backup_status_file = os.path.join(backup_dir, f"{instance_id}_status.json")

    if os.path.exists(cache_file) and not os.path.exists(backup_cache_file):
        shutil.copy2(cache_file, backup_cache_file)
    if os.path.exists(status_file) and not os.path.exists(backup_status_file):
        shutil.copy2(status_file, backup_status_file)


def restore_instance_state(instance_id: str, log_path: str):
    cache_dir = get_cache_dir(log_path)
    status_dir = get_status_dir(log_path)
    backup_dir = get_backup_dir(log_path)

    backup_cache_file = os.path.join(backup_dir, f"{instance_id}_cache.json")
    backup_status_file = os.path.join(backup_dir, f"{instance_id}_status.json")

    cache_file = os.path.join(cache_dir, f"{instance_id}.json")
    status_file = os.path.join(status_dir, f"{instance_id}.json")

    if os.path.exists(backup_cache_file):
        shutil.copy2(backup_cache_file, cache_file)
    if os.path.exists(backup_status_file):
        shutil.copy2(backup_status_file, status_file)


def sql_execution(instance_id, sql, sqlite_dir):
    normalized_sql = normalize_attached_table_references(sql)
    available_db_ids = load_available_db_ids(sqlite_dir)
    referenced_db_ids = extract_referenced_db_ids(normalized_sql, available_db_ids)
    if not referenced_db_ids:
        return "error", (
            "No database ids were found in the SQL query. "
            "Use full table names like \"db_id\".\"table_name\" in the global SQLite space."
        )
    if len(referenced_db_ids) > 10:
        return "error", (
            f"The SQL query references {len(referenced_db_ids)} databases, "
            "which exceeds SQLite's ATTACH limit of 10."
        )

    conn = build_sqlite_connection(referenced_db_ids, sqlite_dir)
    try:
        df = pd.read_sql_query(normalized_sql, conn)
        if df.empty:
            return "empty", "No data found for the specified query."
        return "success", df
    except Exception as e:
        return "error", f"Error occurred while fetching data: {e}"
    finally:
        conn.close()


def load_metadata(dataset_name: str, data_root: str):
    with open(get_embedding_metadata_path(dataset_name, data_root), "r", encoding="utf-8") as f:
        return json.load(f)


def find_column_metadata(metadata: list, table: str, column: str):
    for record in metadata:
        if record["table"].lower() == table.lower() and record["column"].lower() == column.lower():
            return {
                "table": record["table"],
                "column": record["column"],
                "column_type": record["column_type"],
                "column_value": record["column_value"],
                "description": record["description"],
            }
    return None


def format_db_distribution(records: list) -> str:
    counts = {}
    for record in records:
        db_id = table_db_id(record.get("table", ""))
        if not db_id:
            continue
        counts[db_id] = counts.get(db_id, 0) + 1

    if not counts:
        return "(no db_id prefixes found)"

    return ", ".join(
        f"{db_id}: {count}"
        for db_id, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if q <= 0:
        return min(values)
    if q >= 1:
        return max(values)

    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def candidate_db_stats_from_schema(schema_info: dict) -> list[dict]:
    stats = {}
    tables = schema_info.get("table_candidates", [])
    distances = schema_info.get("distances", [])

    for index, table in enumerate(tables):
        db_id = table_db_id(table)
        if not db_id:
            continue
        distance = None
        if index < len(distances):
            try:
                distance = float(distances[index])
            except (TypeError, ValueError):
                distance = None

        item = stats.setdefault(
            db_id,
            {
                "db_id": db_id,
                "hit_count": 0,
                "min_distance": None,
                "distance_sum": 0.0,
                "distance_count": 0,
            },
        )
        item["hit_count"] += 1
        if distance is not None:
            item["distance_sum"] += distance
            item["distance_count"] += 1
            if item["min_distance"] is None or distance < item["min_distance"]:
                item["min_distance"] = distance

    rows = []
    for item in stats.values():
        row = dict(item)
        row["mean_distance"] = (
            row["distance_sum"] / row["distance_count"]
            if row["distance_count"]
            else None
        )
        rows.append(row)

    return sorted(
        rows,
        key=lambda row: (
            row["min_distance"] is None,
            row["min_distance"] if row["min_distance"] is not None else float("inf"),
            -row["hit_count"],
            row["db_id"],
        ),
    )


def candidate_db_ids_from_schema(
    schema_info: dict,
    min_hit_count: int = CANDIDATE_DB_MIN_HIT_COUNT,
    strong_distance_quantile: float = CANDIDATE_DB_STRONG_DISTANCE_QUANTILE,
) -> set:
    stats = candidate_db_stats_from_schema(schema_info)
    if not stats:
        return set()

    distance_values = [
        row["min_distance"]
        for row in stats
        if row["min_distance"] is not None
    ]
    distance_threshold = (
        quantile(distance_values, strong_distance_quantile)
        if distance_values
        else None
    )

    kept = set()
    for row in stats:
        strong_distance_hit = (
            distance_threshold is not None
            and row["min_distance"] is not None
            and row["min_distance"] <= distance_threshold
        )
        if row["hit_count"] >= min_hit_count or strong_distance_hit:
            kept.add(row["db_id"])

    return kept


def tables_for_candidate_databases(db_documents: dict, candidate_db_ids: set) -> list:
    if not candidate_db_ids:
        return list(db_documents.keys())
    return [
        table
        for table in db_documents.keys()
        if table_db_id(table) in candidate_db_ids
    ]


def write_agent_columns(path: str, question: str, db_name: str, db_id: str, records: list):
    write_json(path, {
        "question": question,
        "db_name": db_name,
        "db_id": db_id,
        "columns": records,
    })


def write_schema_linking_status(
    path: str,
    selected_db_id: str | None,
    is_finished: bool,
    is_error: bool,
    database_switch_count: int = 0,
    database_selection_history: list | None = None,
    termination_reason: str | None = None,
    final_records: list | None = None,
    error_message: str | None = None,
    turns_used: int | None = None,
):
    payload = {
        "selected_db_id": selected_db_id,
        "is_finished": is_finished,
        "is_error": is_error,
        "termination_reason": termination_reason,
        "database_switch_count": database_switch_count,
        "database_selection_history": database_selection_history or [],
    }
    if turns_used is not None:
        payload["turns_used"] = turns_used
    if final_records is not None:
        payload.update(
            build_schema_result_snapshot(
                selected_db_id=selected_db_id,
                final_records=final_records,
                is_finished=is_finished,
                is_error=is_error,
                termination_reason=termination_reason,
                error_message=error_message,
            )
        )
    elif error_message is not None:
        payload["error_message"] = error_message
    write_json(path, payload)


def refresh_uncompleted_instances_file(log_path: str, dataset_name: str, instance_ids: list[str]) -> list[str]:
    remaining_instance_ids = []
    for instance_id in instance_ids:
        status = load_schema_linking_status(pipeline_sample_file(log_path, instance_id, SCHEMA_LINKING_STATUS_FILE))
        if not status.get("is_finished", False):
            remaining_instance_ids.append(instance_id)

    os.makedirs(get_status_dir(log_path), exist_ok=True)
    output_path = status_file(log_path, "uncompleted_instances.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        for instance_id in remaining_instance_ids:
            f.write(instance_id + "\n")

    return remaining_instance_ids


def format_observed_columns(results):
    columns = []
    for result in results:
        metadata = result["metadata"]
        columns.append({
            "table": metadata["table"],
            "column": metadata["column"],
            "column_type": metadata["column_type"],
            "column_value": metadata["column_value"],
            "description": metadata["description"],
            "distance": result.get("distance"),
        })
    return columns


def truncate_text(text, max_chars: int) -> str:
    text = "" if text is None else str(text)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    suffix = f"\n...[truncated {omitted} chars]"
    if len(suffix) >= max_chars:
        return text[:max_chars]
    return text[: max_chars - len(suffix)].rstrip() + suffix


def compact_description(description: str, max_chars: int = 180) -> str:
    return truncate_text(" ".join(str(description or "").split()), max_chars)


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    # A deterministic approximation keeps before/after comparisons cheap across backends.
    return max(1, (len(text) + 3) // 4)


def estimate_messages_tokens(messages: list[dict]) -> int:
    return estimate_text_tokens(json.dumps(messages, ensure_ascii=False))


def extract_response_token_usage(response_data: dict) -> dict:
    usage = response_data.get("usage") if isinstance(response_data, dict) else None
    if not isinstance(usage, dict):
        usage = response_data if isinstance(response_data, dict) else {}

    prompt_tokens = (
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("prompt_eval_count")
        or usage.get("input_eval_count")
        or 0
    )
    completion_tokens = (
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("eval_count")
        or usage.get("output_eval_count")
        or 0
    )

    try:
        prompt_tokens = max(0, int(prompt_tokens))
    except (TypeError, ValueError):
        prompt_tokens = 0
    try:
        completion_tokens = max(0, int(completion_tokens))
    except (TypeError, ValueError):
        completion_tokens = 0

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def format_compact_record(record: dict) -> str:
    table = record.get("table", "")
    column = record.get("column", "")
    column_type = record.get("column_type", "")
    description = compact_description(record.get("description", ""))
    suffix = f" - {description}" if description else ""
    return f"- {table}.{column} ({column_type}){suffix}"


def format_compact_records(records: list, max_chars: int = MAX_MEMORY_SCHEMA_CHARS) -> str:
    if not records:
        return "- (none)"

    lines = []
    used = 0
    for record in records:
        line = format_compact_record(record)
        if lines and used + len(line) + 1 > max_chars:
            remaining = len(records) - len(lines)
            lines.append(f"- ... {remaining} more columns omitted")
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def compact_observed_columns(observed_columns: list, limit: int = MAX_MEMORY_OBSERVED_COLUMNS) -> list:
    compacted = []
    seen = set()
    for record in reversed(observed_columns):
        key = column_key(record.get("table", ""), record.get("column", ""))
        if key in seen:
            continue
        seen.add(key)
        compacted.append({
            "table": record.get("table", ""),
            "column": record.get("column", ""),
            "column_type": record.get("column_type", ""),
            "distance": record.get("distance"),
            "description": compact_description(record.get("description", "")),
        })
        if len(compacted) >= limit:
            break
    return list(reversed(compacted))


def summarize_action_result(result) -> str:
    if isinstance(result, dict):
        if "linked" in result:
            record = result["linked"]
            return f"linked {record.get('table', '')}.{record.get('column', '')}"
        if "unlinked" in result:
            record = result["unlinked"]
            return f"unlinked {record.get('table', '')}.{record.get('column', '')}"
        if "columns" in result:
            columns = result.get("columns") or []
            names = [
                f"{item.get('table', '')}.{item.get('column', '')}"
                for item in columns[:5]
            ]
            return f"observed {len(columns)} columns: {', '.join(names)}"
        if "selected_db_id" in result:
            return f"selected db_id={result.get('selected_db_id')}; {result.get('reason', '')}"
        return truncate_text(json.dumps(result, ensure_ascii=False), 500)
    return truncate_text(result, 500)


def format_recent_actions(actions: list, limit: int = MAX_MEMORY_ACTIONS) -> str:
    if not actions:
        return "- (none)"

    lines = []
    for action in actions[-limit:]:
        status = f", status={action.get('status')}" if action.get("status") else ""
        result = summarize_action_result(action.get("result", ""))
        lines.append(
            f"- turn {action.get('turn')}: {action.get('call', '')}{status} -> {result}"
        )
    return "\n".join(lines)


def format_sql_history(tested_sql: list, limit: int = MAX_MEMORY_SQL_TESTS) -> str:
    if not tested_sql:
        return "- (none)"

    lines = []
    for item in tested_sql[-limit:]:
        query = truncate_text(" ".join(str(item.get("query", "")).split()), 320)
        result = truncate_text(" ".join(str(item.get("result", "")).split()), 500)
        lines.append(f"- status={item.get('status')}; query={query}; result={result}")
    return "\n".join(lines)


def build_agent_memory(
    selected_db_id,
    database_switch_count: int,
    database_selection_history: list,
    initial_records: list,
    linked_records: list,
    unlinked_records: list,
    observed_columns: list,
    tested_sql: list,
    all_actions: list,
) -> str:
    current_records = merge_schema_records(
        initial_records,
        linked_records,
        unlinked_records,
        selected_db_id=selected_db_id,
    )
    db_distribution = format_db_distribution(current_records)
    observed = compact_observed_columns(observed_columns)

    memory = (
        "[Controlled Agent Memory]\n"
        "This memory is the source of truth when earlier raw conversation turns are omitted.\n\n"
        "Current database state:\n"
        f"- selected db_id: {selected_db_id or '(not selected yet)'}\n"
        f"- database switches used: {database_switch_count}/{MAX_DATABASE_SWITCHES}\n"
        f"- database selection history: {json.dumps(database_selection_history, ensure_ascii=False)}\n"
        f"- current linked column count: {len(current_records)}\n"
        f"- current db_id distribution: {db_distribution}\n\n"
        "Current linked schema:\n"
        f"{format_compact_records(current_records)}\n\n"
        "Columns explicitly unlinked:\n"
        f"{format_compact_records(unlinked_records, max_chars=6000)}\n\n"
        "Recently observed candidate columns from retrieval:\n"
        f"{json.dumps(observed, ensure_ascii=False, indent=2) if observed else '- (none)'}\n\n"
        "SQL/test history:\n"
        f"{format_sql_history(tested_sql)}\n\n"
        "Recent action history:\n"
        f"{format_recent_actions(all_actions)}\n\n"
        "Operational reminders:\n"
        "- Observation actions do not change the linked schema.\n"
        "- Use @link_column or @unlink_column to change schema membership.\n"
        "- Use @finish_schema_linking() by itself only after the schema is sufficient and belongs to one db_id."
    )
    return memory


def build_controlled_messages(
    system_prompt: str,
    initial_user_content: str,
    conversation_history: list,
    agent_memory: str,
) -> list:
    raw_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_user_content},
    ]
    for turn in conversation_history:
        raw_messages.append({"role": "assistant", "content": turn["assistant"]})
        raw_messages.append({"role": "user", "content": turn["tool_result"]})

    if not ENABLE_CONTEXT_CONTROL:
        return raw_messages

    recent_turn_count = min(RECENT_CONTEXT_TURNS, len(conversation_history))
    memory = agent_memory

    while True:
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": initial_user_content + "\n\n" + truncate_text(memory, MAX_CONTEXT_CHARS),
            },
        ]
        for turn in conversation_history[-recent_turn_count:]:
            messages.append({
                "role": "assistant",
                "content": truncate_text(turn["assistant"], MAX_RECENT_TURN_CHARS),
            })
            messages.append({
                "role": "user",
                "content": truncate_text(turn["tool_result"], MAX_RECENT_TURN_CHARS),
            })

        if len(json.dumps(messages, ensure_ascii=False)) <= MAX_CONTEXT_CHARS:
            break
        if recent_turn_count > 0:
            recent_turn_count -= 1
            continue
        if len(memory) > MAX_MEMORY_SCHEMA_CHARS:
            memory = truncate_text(memory, MAX_MEMORY_SCHEMA_CHARS)
            continue
        break

    raw_chars = len(json.dumps(raw_messages, ensure_ascii=False))
    controlled_chars = len(json.dumps(messages, ensure_ascii=False))
    if controlled_chars >= raw_chars:
        return raw_messages
    return messages


def build_context_usage_summary(
    instance_id: str,
    turn_records: list,
    is_finished: bool,
    is_error: bool,
    termination_reason: str | None = None,
) -> dict:
    raw_total = sum(item["raw_prompt_tokens_estimated"] for item in turn_records)
    controlled_total = sum(item["controlled_prompt_tokens_estimated"] for item in turn_records)
    actual_prompt_total = sum(item["actual_prompt_tokens"] for item in turn_records)
    completion_total = sum(item["completion_tokens"] for item in turn_records)
    reduction = max(0, raw_total - controlled_total)
    ratio = reduction / raw_total if raw_total else 0.0

    return {
        "instance_id": instance_id,
        "context_control_enabled": ENABLE_CONTEXT_CONTROL,
        "turns": len(turn_records),
        "is_finished": is_finished,
        "is_error": is_error,
        "termination_reason": termination_reason,
        "raw_prompt_tokens_estimated_total": raw_total,
        "controlled_prompt_tokens_estimated_total": controlled_total,
        "actual_prompt_tokens_total": actual_prompt_total,
        "completion_tokens_total": completion_total,
        "total_tokens_after_actual": actual_prompt_total + completion_total,
        "prompt_token_reduction_estimated_total": reduction,
        "prompt_token_reduction_ratio_estimated": ratio,
        "turn_records": turn_records,
    }


def handle_finish_schema_linking(tool_call_count, initial_records, linked_records, unlinked_records, selected_db_id):
    if tool_call_count > 1:
        return "Error: @finish_schema_linking() must be called by itself.", selected_db_id, False

    current_records = merge_schema_records(
        initial_records,
        linked_records,
        unlinked_records,
        selected_db_id=selected_db_id,
    )
    current_db_ids = {
        table_db_id(record.get("table", ""))
        for record in current_records
        if table_db_id(record.get("table", ""))
    }
    if len(current_db_ids) != 1:
        return (
            "Error: final linked schema must contain columns from exactly one selected "
            f"db_id, but it currently spans {len(current_db_ids)} db_ids. "
            "Use @select_database(db_id=\"...\") to choose the answer database or "
            "@unlink_column to remove columns from other databases."
        ), selected_db_id, False

    return (
        f"Schema linking finished with selected db_id: {selected_db_id or next(iter(current_db_ids))}.",
        selected_db_id or next(iter(current_db_ids)),
        True,
    )


def handle_select_database(
    func,
    turn_id,
    sqlite_dir,
    selected_db_id,
    database_switch_count,
    database_selection_history,
    initial_records,
    linked_records,
    unlinked_records,
):
    candidate_db_id = func["db_id"]
    selection_reason = func.get("reason", "").strip()
    available_db_ids = load_available_db_ids(sqlite_dir)
    if not candidate_db_id:
        return "Error: db_id is empty.", selected_db_id, database_switch_count
    if not selection_reason:
        return (
            "Error: @select_database must include a non-empty reason, for example "
            "@select_database(db_id=\"...\", reason=\"...\")."
        ), selected_db_id, database_switch_count
    if candidate_db_id not in available_db_ids:
        return (
            f"Error: database {candidate_db_id} was not found in the global SQLite space. "
            "Use a db_id prefix that appears in candidate table names or inspection queries."
        ), selected_db_id, database_switch_count
    if selected_db_id is not None and candidate_db_id != selected_db_id and database_switch_count >= MAX_DATABASE_SWITCHES:
        return (
            f"Error: database switching limit exceeded. You already switched databases "
            f"{database_switch_count} times; at most {MAX_DATABASE_SWITCHES} switches are allowed. "
            f"Keep working within the current selected db_id {selected_db_id} or finish if sufficient."
        ), selected_db_id, database_switch_count

    is_switch = selected_db_id is not None and candidate_db_id != selected_db_id
    previous_db_id = selected_db_id
    if is_switch:
        database_switch_count += 1
    selected_db_id = candidate_db_id
    database_selection_history.append({
        "turn": turn_id,
        "db_id": selected_db_id,
        "reason": selection_reason,
        "is_switch": is_switch,
        "previous_db_id": previous_db_id,
        "switch_count": database_switch_count,
    })
    scoped_records = merge_schema_records(
        initial_records,
        linked_records,
        unlinked_records,
        selected_db_id=selected_db_id,
    )
    return {
        "selected_db_id": selected_db_id,
        "message": (
            "The linked schema is now scoped to this selected database. "
            "Continue linking any missing columns from the same db_id."
        ),
        "reason": selection_reason,
        "is_switch": is_switch,
        "database_switch_count": database_switch_count,
        "max_database_switches": MAX_DATABASE_SWITCHES,
        "current_scoped_columns": len(scoped_records),
    }, selected_db_id, database_switch_count


def handle_find_relevant_columns(func, instance_id, db_name, embed_path, cache_path, status_path, retrieval_scope_db_ids, observed_columns):
    query = func["query"]
    if not query:
        return {"columns": [], "message": "Error: query is empty."}

    semantic_results, _, completion_message = get_next_k_results(
        instance_id=instance_id,
        question=query,
        db_name=db_name,
        embed_path=embed_path,
        top_k=AGENT_RETRIEVAL_TOP_K,
        cache_dir=cache_path,
        status_dir=status_path,
        device=RETRIEVAL_DEVICE,
        allowed_db_ids=retrieval_scope_db_ids,
    )
    columns = format_observed_columns(semantic_results)
    observed_columns.extend(columns)
    return {
        "columns": columns,
        "message": completion_message,
        "note": (
            "These columns are observed only and are retrieved within the initial candidate "
            "database scope. Use them to choose one database, then @link_column only columns "
            "from that selected db_id."
        ),
    }


def handle_sql_action(func, instance_id, sqlite_dir, tested_sql):
    query = func["query"]
    if not query:
        return "Error: query is empty.", "error"

    exec_status, sql_result = sql_execution(instance_id, query, sqlite_dir)
    result = str(sql_result)
    if func["tool"] == "test_sql":
        referenced_db_ids = extract_referenced_db_ids(
            normalize_attached_table_references(query),
            load_available_db_ids(sqlite_dir),
        )
        if len(referenced_db_ids) > 1:
            result += (
                "\n\nWarning: this draft answer query references multiple databases "
                f"({', '.join(referenced_db_ids)}). For schema linking, the final answer "
                "must use one selected db_id only. Use inspection results to choose one "
                "database and unlink columns from the others."
            )
        tested_sql.append({
            "query": query,
            "status": exec_status,
            "result": result,
        })
    return result, exec_status


def handle_link_column(func, metadata, selected_db_id, initial_records, linked_records, unlinked_records):
    table = func["table"]
    column = func["column"]
    record = find_column_metadata(metadata, table, column)
    if record is None:
        return (
            f"Error: column {table}.{column} was not found in metadata. "
            "Use @find_relevant_columns or @inspect_database to verify the table and column name."
        ), linked_records, unlinked_records
    if selected_db_id and table_db_id(record["table"]) != selected_db_id:
        return (
            f"Error: selected db_id is {selected_db_id}, but {record['table']} belongs to "
            f"{table_db_id(record['table'])}. Link columns from the selected database only, "
            "or call @select_database with a different db_id if the evidence supports changing it."
        ), linked_records, unlinked_records

    key = column_key(record["table"], record["column"])
    unlinked_records = [
        item for item in unlinked_records
        if column_key(item["table"], item["column"]) != key
    ]
    existing_keys = {
        column_key(item["table"], item["column"])
        for item in initial_records + linked_records
    }
    if key not in existing_keys:
        linked_records.append(record)
        return {"linked": record}, linked_records, unlinked_records
    return {"linked": record, "message": "Column is already in the linked schema."}, linked_records, unlinked_records


def handle_unlink_column(func, metadata, unlinked_records):
    table = func["table"]
    column = func["column"]
    record = find_column_metadata(metadata, table, column) or {
        "table": table,
        "column": column,
        "column_type": "",
        "column_value": [],
        "description": "",
    }
    key = column_key(record["table"], record["column"])
    if key not in {column_key(item["table"], item["column"]) for item in unlinked_records}:
        unlinked_records.append(record)
    return {"unlinked": record}


def format_action_result(result):
    return json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, dict) else result


def build_schema_status_message(selected_db_id, database_switch_count, initial_records, linked_records, unlinked_records):
    current_records = merge_schema_records(
        initial_records,
        linked_records,
        unlinked_records,
        selected_db_id=selected_db_id,
    )
    db_distribution = format_db_distribution(current_records)
    current_db_ids = {
        table_db_id(record.get("table", ""))
        for record in current_records
        if table_db_id(record.get("table", ""))
    }
    single_db_reminder = ""
    if len(current_db_ids) > 1:
        single_db_reminder = (
            "\nSingle-database reminder: the current linked schema still spans multiple db_ids. "
            "Choose the one db_id that can answer the full question and use @unlink_column to remove "
            "columns from the others before finishing."
        )
    return (
        "\nCurrent linked schema status:\n"
        f"- selected db_id: {selected_db_id or '(not selected yet)'}\n"
        f"- database switches used: {database_switch_count}/{MAX_DATABASE_SWITCHES}\n"
        f"- initial columns: {len(initial_records)}\n"
        f"- agent linked columns: {len(linked_records)}\n"
        f"- agent unlinked columns: {len(unlinked_records)}\n"
        f"- current final columns: {len(current_records)}\n"
        f"- current db_id distribution: {db_distribution}"
        f"{single_db_reminder}\n"
        "Remember: observation actions do not change the linked schema. Use @link_column or "
        "@unlink_column for schema changes. Use @finish_schema_linking() by itself when done."
    )


def process_instances(instances, log_path, dataset_name, data_root, write_sample_debug: bool = False):
    cache_path = get_cache_dir(log_path)
    status_path = get_status_dir(log_path)
    cost_output_path = summary_file(log_path, "cost.json")
    sqlite_dir = get_sqlite_dir(dataset_name, data_root)
    embed_path = get_embeddings_dir(dataset_name, data_root)
    metadata = load_metadata(dataset_name, data_root)

    with open(get_documents_path(dataset_name, data_root), "r", encoding="utf-8") as f:
        documents = json.load(f)

    dataset_data = load_dataset_data(dataset_name, data_root)
    with open(pipeline_file(log_path, INITIAL_VECTOR_RETRIEVED_COLUMNS_FILE), "r", encoding="utf-8") as f:
        initial_retrieved_candidates = json.load(f)

    for instance_id, info in tqdm(instances.items(), leave=False, desc="Schema completion"):
        with SampleCostRecorder(
            sample_id=instance_id,
            output_path=cost_output_path,
        ) as cost_recorder:
            restore_instance_state(instance_id, log_path)
            os.makedirs(get_pipeline_sample_dir(log_path, instance_id), exist_ok=True)
            if write_sample_debug:
                os.makedirs(get_sample_dir(log_path, instance_id), exist_ok=True)

            if instance_id not in dataset_data:
                raise ValueError(f"Instance ID {instance_id} not found in {get_gold_sl_path(dataset_name, data_root)}")

            question = info["question"]
            db_name = info["db_name"]
            db_id = info.get("db_id", "")
            knowledge_data = info.get("external_knowledge") or ""
            db_documents = documents[db_name]

            with open(pipeline_sample_file(log_path, instance_id, SCHEMA_LINKING_PROMPT_FILE), "r", encoding="utf-8") as f:
                linked_schema_prompt = f.read()

            initial_retrieved_schema = initial_retrieved_candidates.get(instance_id, {})
            candidate_db_ids = candidate_db_ids_from_schema(initial_retrieved_schema)
            all_tables = tables_for_candidate_databases(db_documents, candidate_db_ids)
            retrieval_scope_db_ids = sorted(candidate_db_ids) if candidate_db_ids else None
            update_instance_retrieval_scope(
                instance_id=instance_id,
                embed_path=embed_path,
                cache_dir=cache_path,
                status_dir=status_path,
                allowed_db_ids=retrieval_scope_db_ids,
            )
            all_actions = []

            initial_records = schema_to_records(info)
            linked_records = []
            unlinked_records = []
            observed_columns = []
            tested_sql = []
            selected_db_id = None
            database_switch_count = 0
            database_selection_history = []

            system_prompt = SCHEMA_LINKING.format(
                SQL_TYPE=SQLITE,
                SQL_OPTIMIZATION=SQLITE_DIALECT_OPTIMIZATION,
            )

            initial_user_content = USER_INPUT.format(
                LINKED_SCHEMA=linked_schema_prompt,
                USER_QUESTION=question,
                EXTERNAL_KNOWLEDGE=knowledge_data,
                ALL_TABLES=json.dumps(all_tables, ensure_ascii=False),
            )
            raw_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": initial_user_content},
            ]
            conversation_history = []
            context_token_usage = []
            if write_sample_debug:
                all_model_output = ""
                all_inputs = "Initial embedding database pruning and schema linking prompt:\n"
                all_inputs += linked_schema_prompt
                all_inputs += "\n\n" + "=" * 80 + "\n\n"
                all_raw_inputs = all_inputs

            is_finished = False
            is_error = False
            termination_reason = None
            error_message = None

            for turn_id in range(MODEL_DISCUSSION_TURNS):
                if is_finished or is_error:
                    break

                agent_memory = build_agent_memory(
                    selected_db_id,
                    database_switch_count,
                    database_selection_history,
                    initial_records,
                    linked_records,
                    unlinked_records,
                    observed_columns,
                    tested_sql,
                    all_actions,
                )
                context_messages = build_controlled_messages(
                    system_prompt,
                    initial_user_content,
                    conversation_history,
                    agent_memory,
                )
                raw_prompt_tokens_estimated = estimate_messages_tokens(raw_messages)
                controlled_prompt_tokens_estimated = estimate_messages_tokens(context_messages)
                if write_sample_debug:
                    all_inputs += f"Turn {turn_id} controlled messages:\n"
                    all_inputs += json.dumps(context_messages, ensure_ascii=False, indent=2)
                    all_inputs += "\n\n" + "=" * 80 + "\n\n"
                    all_raw_inputs += f"Turn {turn_id} raw messages:\n"
                    all_raw_inputs += json.dumps(raw_messages, ensure_ascii=False, indent=2)
                    all_raw_inputs += "\n\n" + "=" * 80 + "\n\n"

                try:
                    model_output, response_data = chat_with_ollama(context_messages)
                    cost_recorder.add_response_usage(response_data)
                    response_usage = extract_response_token_usage(response_data)
                except Exception as e:
                    model_output = f"Model call failed: {e}"
                    error_message = str(e)
                    response_usage = {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                    }
                    is_error = True
                    termination_reason = "model_call_failed"
                if write_sample_debug:
                    all_model_output += f"Turn {turn_id} model output:\n{model_output}\n\n"
                    all_model_output += "=" * 80 + "\n\n"

                reduction = max(0, raw_prompt_tokens_estimated - controlled_prompt_tokens_estimated)
                context_token_usage.append({
                    "turn": turn_id,
                    "raw_prompt_tokens_estimated": raw_prompt_tokens_estimated,
                    "controlled_prompt_tokens_estimated": controlled_prompt_tokens_estimated,
                    "actual_prompt_tokens": response_usage["prompt_tokens"],
                    "completion_tokens": response_usage["completion_tokens"],
                    "actual_total_tokens": response_usage["total_tokens"],
                    "prompt_token_reduction_estimated": reduction,
                    "prompt_token_reduction_ratio_estimated": (
                        reduction / raw_prompt_tokens_estimated
                        if raw_prompt_tokens_estimated
                        else 0.0
                    ),
                    "context_control_applied": controlled_prompt_tokens_estimated < raw_prompt_tokens_estimated,
                    "context_chars": len(json.dumps(context_messages, ensure_ascii=False)),
                    "raw_context_chars": len(json.dumps(raw_messages, ensure_ascii=False)),
                })

                try:
                    full_lines, tool_calls = parse_model_output(model_output)
                except Exception as e:
                    full_lines = []
                    tool_calls = []
                    is_error = True
                    termination_reason = "parse_model_output_failed"
                    error_message = str(e)
                    if write_sample_debug:
                        with open(sample_file(log_path, instance_id, ERROR_FILE), "w", encoding="utf-8") as f:
                            f.write(f"Failed to parse model output: {e}\n\n{model_output}")

                func_messages = ""
                turn_actions = []

                if not tool_calls and not is_error:
                    func_messages = (
                        "No valid action calls were parsed. Use one or more of the defined actions exactly as specified."
                    )

                for line, func in zip(full_lines, tool_calls):
                    action_record = {
                        "turn": turn_id,
                        "call": line,
                        "tool": func["tool"],
                    }

                    if func["tool"] == "finish_schema_linking":
                        result, selected_db_id, is_finished = handle_finish_schema_linking(
                            len(tool_calls),
                            initial_records,
                            linked_records,
                            unlinked_records,
                            selected_db_id,
                        )
                        func_messages += f"Action: {line}\nThe action returns:\n{result}\n\n"
                        action_record["result"] = result
                        if is_finished:
                            turn_actions.append(action_record)
                            break

                    elif func["tool"] == "select_database":
                        result, selected_db_id, database_switch_count = handle_select_database(
                            func,
                            turn_id,
                            sqlite_dir,
                            selected_db_id,
                            database_switch_count,
                            database_selection_history,
                            initial_records,
                            linked_records,
                            unlinked_records,
                        )
                        func_messages += f"Action: {line}\nThe action returns:\n{format_action_result(result)}\n\n"
                        action_record["result"] = result

                    elif func["tool"] == "find_relevant_columns":
                        result = handle_find_relevant_columns(
                            func,
                            instance_id,
                            db_name,
                            embed_path,
                            cache_path,
                            status_path,
                            retrieval_scope_db_ids,
                            observed_columns,
                        )
                        func_messages += f"Action: {line}\nThe action returns:\n{format_action_result(result)}\n\n"
                        action_record["result"] = result

                    elif func["tool"] in {"inspect_database", "test_sql"}:
                        result, exec_status = handle_sql_action(func, instance_id, sqlite_dir, tested_sql)
                        func_messages += f"Action: {line}\nThe action returns status={exec_status}:\n{result}\n\n"
                        action_record["status"] = exec_status
                        action_record["result"] = result

                    elif func["tool"] == "link_column":
                        result, linked_records, unlinked_records = handle_link_column(
                            func,
                            metadata,
                            selected_db_id,
                            initial_records,
                            linked_records,
                            unlinked_records,
                        )
                        func_messages += f"Action: {line}\nThe action returns:\n{format_action_result(result)}\n\n"
                        action_record["result"] = result

                    elif func["tool"] == "unlink_column":
                        result = handle_unlink_column(func, metadata, unlinked_records)
                        func_messages += f"Action: {line}\nThe action returns:\n{format_action_result(result)}\n\n"
                        action_record["result"] = result

                    turn_actions.append(action_record)

                all_actions.extend(turn_actions)

                func_messages += build_schema_status_message(
                    selected_db_id,
                    database_switch_count,
                    initial_records,
                    linked_records,
                    unlinked_records,
                )

                raw_messages.append({"role": "assistant", "content": model_output})
                raw_messages.append({"role": "user", "content": func_messages})
                conversation_history.append({
                    "turn": turn_id,
                    "assistant": model_output,
                    "tool_result": func_messages,
                })

            if not is_finished and not is_error:
                termination_reason = "max_turns_exceeded"

            if is_error:
                print(f"Error occurred for instance {instance_id}. Skipping...")

            final_records = merge_schema_records(
                initial_records,
                linked_records,
                unlinked_records,
                selected_db_id=selected_db_id,
            )

            context_usage_summary = build_context_usage_summary(
                instance_id,
                context_token_usage,
                is_finished,
                is_error,
                termination_reason,
            )
            if write_sample_debug:
                with open(sample_file(log_path, instance_id, CONTEXT_TOKEN_USAGE_FILE), "w", encoding="utf-8") as f:
                    json.dump(context_usage_summary, f, ensure_ascii=False, indent=2)
                with open(sample_file(log_path, instance_id, MODEL_OUTPUT_FILE), "w", encoding="utf-8") as f:
                    f.write(all_model_output)
                with open(sample_file(log_path, instance_id, INPUT_MESSAGES_FILE), "w", encoding="utf-8") as f:
                    f.write(all_inputs)
                with open(sample_file(log_path, instance_id, RAW_INPUT_MESSAGES_FILE), "w", encoding="utf-8") as f:
                    f.write(all_raw_inputs)
                with open(sample_file(log_path, instance_id, AGENT_SCHEMA_LINKING_ACTIONS_FILE), "w", encoding="utf-8") as f:
                    json.dump(all_actions, f, ensure_ascii=False, indent=2)

            write_agent_columns(
                pipeline_sample_file(log_path, instance_id, AGENT_LINKED_COLUMNS_FILE),
                question,
                db_name,
                db_id,
                linked_records,
            )
            write_agent_columns(
                pipeline_sample_file(log_path, instance_id, AGENT_UNLINKED_COLUMNS_FILE),
                question,
                db_name,
                db_id,
                unlinked_records,
            )
            write_schema_linking_status(
                pipeline_sample_file(log_path, instance_id, SCHEMA_LINKING_STATUS_FILE),
                selected_db_id,
                is_finished,
                is_error,
                database_switch_count=database_switch_count,
                database_selection_history=database_selection_history,
                termination_reason=termination_reason,
                final_records=final_records,
                error_message=error_message,
                turns_used=len(context_token_usage),
            )
            if write_sample_debug:
                write_agent_columns(
                    sample_file(log_path, instance_id, AGENT_LINKED_COLUMNS_FILE),
                    question,
                    db_name,
                    db_id,
                    linked_records,
                )
                write_agent_columns(
                    sample_file(log_path, instance_id, AGENT_UNLINKED_COLUMNS_FILE),
                    question,
                    db_name,
                    db_id,
                    unlinked_records,
                )
                write_schema_linking_status(
                    sample_file(log_path, instance_id, SCHEMA_LINKING_STATUS_FILE),
                    selected_db_id,
                    is_finished,
                    is_error,
                    database_switch_count=database_switch_count,
                    database_selection_history=database_selection_history,
                    termination_reason=termination_reason,
                    final_records=final_records,
                    error_message=error_message,
                    turns_used=len(context_token_usage),
                )


def complete_schema(log_path, dataset_name, data_root=DEFAULT_DATA_ROOT, write_sample_debug: bool = False):
    os.makedirs(get_cache_dir(log_path), exist_ok=True)
    os.makedirs(get_status_dir(log_path), exist_ok=True)
    os.makedirs(get_backup_dir(log_path), exist_ok=True)
    os.makedirs(get_pipeline_dir(log_path), exist_ok=True)
    os.makedirs(get_summary_dir(log_path), exist_ok=True)

    with open(pipeline_file(log_path, RULE_AUGMENTED_INITIAL_SCHEMA_FILE), "r", encoding="utf-8") as f:
        initial_candidates = json.load(f)

    dataset_data = load_dataset_data(dataset_name, data_root)
    instance_ids = list(dataset_data.keys())

    print("Backup instance retrieval status ...")
    for instance_id in instance_ids:
        backup_instance_state(instance_id, log_path)

    clean_instance_ids = []
    for instance_id in instance_ids:
        status = load_schema_linking_status(pipeline_sample_file(log_path, instance_id, SCHEMA_LINKING_STATUS_FILE))
        if status.get("is_finished", False):
            continue
        clean_instance_ids.append(instance_id)

    print(f"Unfinished instances: {len(clean_instance_ids)}")

    uncompleted_file = status_file(log_path, "uncompleted_instances.txt")
    with open(uncompleted_file, "w", encoding="utf-8") as f:
        for instance_id in clean_instance_ids:
            f.write(instance_id + "\n")

    if not clean_instance_ids:
        remaining_instance_ids = refresh_uncompleted_instances_file(log_path, dataset_name, instance_ids)
        print(f"Remaining unfinished instances: {len(remaining_instance_ids)}")
        return

    instances_to_process = {
        instance_id: initial_candidates[instance_id]
        for instance_id in clean_instance_ids
    }
    try:
        process_instances(
            instances_to_process,
            log_path,
            dataset_name,
            data_root,
            write_sample_debug=write_sample_debug,
        )
    finally:
        from model_manager import model_manager
        model_manager.release_model()

    remaining_instance_ids = refresh_uncompleted_instances_file(log_path, dataset_name, instance_ids)
    print(f"Remaining unfinished instances: {len(remaining_instance_ids)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--log_path", type=str, default=os.path.join(DEFAULT_LOG_ROOT, DEFAULT_DATASET_NAME))
    parser.add_argument("--dataset_name", type=str, default=DEFAULT_DATASET_NAME)
    parser.add_argument("--data_root", type=str, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--ollama_base_url", type=str, default=OLLAMA_BASE_URL)
    parser.add_argument("--ollama_model", type=str, default=OLLAMA_MODEL)
    parser.add_argument(
        "--sentence_transformer_model",
        type=str,
        default=os.environ.get("SENTENCE_TRANSFORMER_MODEL", SENTENCE_TRANSFORMER_MODEL),
    )
    parser.add_argument("--candidate_db_min_hit_count", type=int, default=CANDIDATE_DB_MIN_HIT_COUNT)
    parser.add_argument("--candidate_db_strong_distance_quantile", type=float, default=CANDIDATE_DB_STRONG_DISTANCE_QUANTILE)
    parser.add_argument("--max_database_switches", type=int, default=MAX_DATABASE_SWITCHES)
    parser.add_argument("--enable_context_control", type=parse_bool, default=ENABLE_CONTEXT_CONTROL)
    parser.add_argument("--max_context_chars", type=int, default=MAX_CONTEXT_CHARS)
    parser.add_argument("--recent_context_turns", type=int, default=RECENT_CONTEXT_TURNS)
    parser.add_argument("--max_memory_actions", type=int, default=MAX_MEMORY_ACTIONS)
    parser.add_argument("--max_memory_observed_columns", type=int, default=MAX_MEMORY_OBSERVED_COLUMNS)
    parser.add_argument("--max_memory_sql_tests", type=int, default=MAX_MEMORY_SQL_TESTS)
    parser.add_argument("--max_memory_schema_chars", type=int, default=MAX_MEMORY_SCHEMA_CHARS)
    parser.add_argument("--max_recent_turn_chars", type=int, default=MAX_RECENT_TURN_CHARS)
    parser.add_argument("--model_discussion_turns", type=int, default=MODEL_DISCUSSION_TURNS)
    parser.add_argument("--agent_retrieval_top_k", type=int, default=AGENT_RETRIEVAL_TOP_K)
    parser.add_argument("--retrieval_device", type=str, default=RETRIEVAL_DEVICE)
    parser.add_argument("--write_sample_debug", type=parse_bool, default=False)
    args = parser.parse_args()
    configure_runtime(args)
    print("Starting schema completion...")
    complete_schema(
        args.log_path,
        args.dataset_name,
        data_root=args.data_root,
        write_sample_debug=args.write_sample_debug,
    )
    print("Schema completion finished.")
