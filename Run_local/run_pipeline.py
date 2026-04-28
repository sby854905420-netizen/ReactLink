import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

from config import get_runtime_config, parse_bool
from utils import (
    BACKUP_DIR_NAME,
    CACHE_DIR_NAME,
    STATUS_DIR_NAME,
    SUMMARY_DIR_NAME,
    get_documents_path,
    get_embedding_index_path,
    get_embedding_metadata_path,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ReactLink local pipeline.")
    parser.add_argument("--dataset_name", "--dataset-name", default=None)
    parser.add_argument("--ollama_base_url", "--ollama-base-url", default=None)
    parser.add_argument("--model_discussion_turns", "--model-discussion-turns", default=None)
    parser.add_argument("--ollama_model", "--ollama-model", default=None)
    parser.add_argument("--write_sample_debug", "--write-sample-debug", default=None)
    parser.add_argument("--top_n", "--top-n", default=None)
    parser.add_argument("--run_id", "--run-id", default=None)
    parser.add_argument("--log_path", "--log-path", default=None)
    return parser.parse_args()


def apply_override(name: str, value) -> None:
    if value is not None and str(value) != "":
        os.environ[name] = str(value)


def make_run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{time.time_ns() % 1_000_000_000:09d}"


def require_inputs(config: dict) -> None:
    dataset_name = config["DATASET_NAME"]
    data_root = config["DATA_ROOT"]
    required_paths = [
        get_documents_path(dataset_name, data_root),
        get_embedding_index_path(dataset_name, data_root),
        get_embedding_metadata_path(dataset_name, data_root),
    ]
    missing_paths = [path for path in required_paths if not os.path.isfile(path)]
    if not missing_paths:
        return

    print(f"Missing generated documents or embeddings for dataset: {dataset_name}", file=sys.stderr)
    for path in missing_paths:
        print(f"  missing: {path}", file=sys.stderr)
    print("Run this first:", file=sys.stderr)
    print(f"  bash prepare_docs_embeddings.sh {dataset_name!r}", file=sys.stderr)
    raise SystemExit(1)


def prepare_log_dirs(config: dict) -> None:
    log_path = config["LOG_PATH"]
    for dirname in (SUMMARY_DIR_NAME, CACHE_DIR_NAME, STATUS_DIR_NAME, BACKUP_DIR_NAME):
        os.makedirs(os.path.join(log_path, dirname), exist_ok=True)

    reset_cost = config["RESET_COST"]
    if reset_cost is True or str(reset_cost).lower() in {"1", "true"}:
        for path in (
            os.path.join(log_path, SUMMARY_DIR_NAME, "cost.json"),
            os.path.join(log_path, SUMMARY_DIR_NAME, "cost.json.lock"),
            os.path.join(log_path, CACHE_DIR_NAME, "_locks", "cost.json.lock"),
        ):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


def print_config(config: dict, run_id: str) -> None:
    print(
        "\n".join(
            [
                "Resolved ReactLink run configuration:",
                f"  DATASET_NAME={config['DATASET_NAME']}",
                f"  OLLAMA_BASE_URL={config['OLLAMA_BASE_URL']}",
                f"  OLLAMA_MODEL={config['OLLAMA_MODEL']}",
                f"  MODEL_DISCUSSION_TURNS={config['MODEL_DISCUSSION_TURNS']}",
                f"  WRITE_SAMPLE_DEBUG={config['WRITE_SAMPLE_DEBUG']}",
                f"  TOP_N={config['TOP_N']}",
                f"  RUN_ID={run_id}",
                f"  LOG_PATH={config['LOG_PATH']}",
            ]
        )
    )


def script_path(name: str) -> str:
    return os.path.join(BASE_DIR, name)


def run_step(script_name: str, *args: str) -> None:
    subprocess.run(
        [sys.executable, script_path(script_name), *args],
        cwd=PROJECT_ROOT,
        check=True,
    )


def main() -> None:
    args = parse_args()

    apply_override("DATASET_NAME", args.dataset_name)
    apply_override("OLLAMA_BASE_URL", args.ollama_base_url)
    apply_override("MODEL_DISCUSSION_TURNS", args.model_discussion_turns)
    apply_override("OLLAMA_MODEL", args.ollama_model)
    apply_override("WRITE_SAMPLE_DEBUG", args.write_sample_debug)
    apply_override("TOP_N", args.top_n)
    apply_override("RUN_ID", args.run_id)

    user_log_path = os.environ.get("LOG_PATH")
    if args.log_path:
        user_log_path = args.log_path
        os.environ["LOG_PATH"] = args.log_path

    config = get_runtime_config()
    run_id = os.environ.get("RUN_ID") or make_run_id()
    if not user_log_path:
        config["LOG_PATH"] = os.path.join(
            config["LOG_ROOT"],
            config["DATASET_NAME"],
            config["SAFE_MODEL_NAME"],
            run_id,
        )

    for key, value in config.items():
        os.environ[key] = "1" if value is True else "0" if value is False else str(value)
    os.environ["RUN_ID"] = run_id

    require_inputs(config)
    prepare_log_dirs(config)
    print_config(config, run_id)

    common_args = [
        "--log_path",
        config["LOG_PATH"],
        "--dataset_name",
        config["DATASET_NAME"],
        "--data_root",
        config["DATA_ROOT"],
        "--write_sample_debug",
        str(config["WRITE_SAMPLE_DEBUG"]),
    ]

    run_step(
        "retrieve_topk_schema.py",
        *common_args,
        "--top_n",
        str(config["TOP_N"]),
        "--retrieval_device",
        config["RETRIEVAL_DEVICE"],
        "--sentence_transformer_model",
        config["SENTENCE_TRANSFORMER_MODEL"],
    )
    run_step("add_id.py", *common_args)
    run_step("generate_schema.py", *common_args, "--is_initial")
    run_step(
        "complete_schema.py",
        *common_args,
        "--ollama_base_url",
        config["OLLAMA_BASE_URL"],
        "--ollama_model",
        config["OLLAMA_MODEL"],
        "--sentence_transformer_model",
        config["SENTENCE_TRANSFORMER_MODEL"],
        "--model_discussion_turns",
        str(config["MODEL_DISCUSSION_TURNS"]),
        "--retrieval_device",
        config["RETRIEVAL_DEVICE"],
    )
    run_step("postprocess.py", *common_args)
    run_step("generate_schema.py", *common_args)


if __name__ == "__main__":
    main()
