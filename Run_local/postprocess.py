import argparse
import json
import os

from cost_tool import SampleCostRecorder
from utils import (
    AGENT_LINKED_COLUMNS_FILE,
    AGENT_UNLINKED_COLUMNS_FILE,
    DEFAULT_DATA_ROOT,
    DEFAULT_DATASET_NAME,
    DEFAULT_LOG_ROOT,
    FINAL_PROMPT_LINKED_SCHEMA_FILE,
    FINAL_SCHEMA_LINKING_COLUMNS_FILE,
    RESULT_MANIFEST_FILE,
    RULE_AUGMENTED_INITIAL_SCHEMA_FILE,
    SCHEMA_LINKING_STATUS_FILE,
    build_schema_result_snapshot,
    load_agent_columns,
    load_schema_linking_status,
    merge_schema_records,
    parse_bool,
    pipeline_file,
    pipeline_sample_file,
    record_db_ids,
    records_to_schema,
    sample_file,
    schema_to_records,
    summary_file,
    get_sample_dir,
    get_summary_dir,
)


def last_explicit_selected_db_id(status: dict) -> str | None:
    history = status.get("database_selection_history", [])
    if isinstance(history, list):
        for selection in reversed(history):
            if isinstance(selection, dict) and selection.get("db_id"):
                return selection["db_id"]
    return status.get("selected_db_id")


def status_flags(status: dict) -> tuple[bool, bool]:
    explicit_status = status.get("status")
    if explicit_status == "finished":
        return True, False
    if explicit_status == "error":
        return False, True
    if explicit_status == "best_effort":
        return False, False
    return bool(status.get("is_finished", False)), bool(status.get("is_error", False))


def build_run_status(counts: dict) -> str:
    if counts["error"]:
        return "completed_with_errors"
    if counts["best_effort"]:
        return "completed_with_unfinished_samples"
    return "success"


def to_schema_linking_columns(data_id: str, db_ids: list, records: list) -> dict:
    db_id = db_ids[0] if len(db_ids) == 1 else ""
    return {
        "db_id": db_id,
        "db_ids": db_ids,
        "columns": [
            {
                "table": record["table"],
                "column": record["column"],
            }
            for record in records
        ],
    }


def merge(
    log_path,
    dataset_name: str = DEFAULT_DATASET_NAME,
    data_root: str = DEFAULT_DATA_ROOT,
    write_sample_debug: bool = False,
):
    summary_dir = get_summary_dir(log_path)
    cost_output_path = summary_file(log_path, "cost.json")
    with open(pipeline_file(log_path, RULE_AUGMENTED_INITIAL_SCHEMA_FILE), "r", encoding="utf-8") as f:
        initial_candidates = json.load(f)

    final_prompt_schemas = {}
    final_schema_linking_columns = {}
    result_manifest = {
        "total": 0,
        "finished": 0,
        "best_effort": 0,
        "error": 0,
        "samples": {},
    }

    for data_id, schema_info in initial_candidates.items():
        with SampleCostRecorder(
            sample_id=data_id,
            output_path=cost_output_path,
        ):
            initial_records = schema_to_records(schema_info)
            linked_records = load_agent_columns(pipeline_sample_file(log_path, data_id, AGENT_LINKED_COLUMNS_FILE))
            unlinked_records = load_agent_columns(pipeline_sample_file(log_path, data_id, AGENT_UNLINKED_COLUMNS_FILE))
            status = load_schema_linking_status(pipeline_sample_file(log_path, data_id, SCHEMA_LINKING_STATUS_FILE))
            selected_db_id = last_explicit_selected_db_id(status)
            final_records = merge_schema_records(
                initial_records,
                linked_records,
                unlinked_records,
                selected_db_id=selected_db_id,
            )
            output_db_ids = [selected_db_id] if selected_db_id else record_db_ids(final_records)

            final_prompt_schema = records_to_schema(
                schema_info["question"],
                schema_info["db_name"],
                final_records,
                db_id=output_db_ids[0] if len(output_db_ids) == 1 else None,
            )
            final_prompt_schema["db_ids"] = output_db_ids
            final_columns = to_schema_linking_columns(data_id, output_db_ids, final_records)
            is_finished, is_error = status_flags(status)
            sample_result = build_schema_result_snapshot(
                selected_db_id=selected_db_id,
                final_records=final_records,
                is_finished=is_finished,
                is_error=is_error,
                termination_reason=status.get("termination_reason"),
                error_message=status.get("error_message"),
            )
            if "turns_used" in status:
                sample_result["turns_used"] = status["turns_used"]

            final_prompt_schemas[data_id] = final_prompt_schema
            final_schema_linking_columns[data_id] = final_columns
            result_manifest["samples"][data_id] = sample_result
            result_manifest["total"] += 1
            result_manifest[sample_result["status"]] += 1

            if write_sample_debug:
                os.makedirs(get_sample_dir(log_path, data_id), exist_ok=True)
                with open(sample_file(log_path, data_id, FINAL_PROMPT_LINKED_SCHEMA_FILE), "w", encoding="utf-8") as f:
                    json.dump(final_prompt_schema, f, ensure_ascii=False, indent=2)
                with open(sample_file(log_path, data_id, FINAL_SCHEMA_LINKING_COLUMNS_FILE), "w", encoding="utf-8") as f:
                    json.dump(final_columns, f, ensure_ascii=False, indent=2)

    os.makedirs(summary_dir, exist_ok=True)
    result_manifest["run_status"] = build_run_status(result_manifest)
    with open(summary_file(log_path, FINAL_PROMPT_LINKED_SCHEMA_FILE), "w", encoding="utf-8") as f:
        json.dump(final_prompt_schemas, f, indent=2, ensure_ascii=False)

    with open(summary_file(log_path, FINAL_SCHEMA_LINKING_COLUMNS_FILE), "w", encoding="utf-8") as f:
        json.dump(final_schema_linking_columns, f, indent=2, ensure_ascii=False)

    with open(summary_file(log_path, RESULT_MANIFEST_FILE), "w", encoding="utf-8") as f:
        json.dump(result_manifest, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--log_path", type=str, default=os.path.join(DEFAULT_LOG_ROOT, DEFAULT_DATASET_NAME))
    parser.add_argument("--dataset_name", type=str, default=DEFAULT_DATASET_NAME)
    parser.add_argument("--data_root", type=str, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--write_sample_debug", type=parse_bool, default=False)
    args = parser.parse_args()
    print("Merging candidate schemas...")
    merge(
        log_path=args.log_path,
        dataset_name=args.dataset_name,
        data_root=args.data_root,
        write_sample_debug=args.write_sample_debug,
    )
    print("Merging completed.")
