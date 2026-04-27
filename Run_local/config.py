import argparse
import os
import re
import shlex


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# Quick-edit run settings.
# Put each dataset folder under PROJECT_ROOT/Data, then change DATASET_NAME here.
DATASET_NAME = "MMQA_SMOKE"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen2.5:14b"
MODEL_DISCUSSION_TURNS = 20

# Defaults below normally do not need to change.
DATA_ROOT = os.path.join(PROJECT_ROOT, "Data")
LOG_ROOT = os.path.join(PROJECT_ROOT, "logs")
TOP_N = 50
RESET_COST = True
SENTENCE_TRANSFORMER_MODEL = "BAAI/bge-large-en-v1.5"
RETRIEVAL_DEVICE = "cuda:0"

CANDIDATE_DB_MIN_HIT_COUNT = 2
CANDIDATE_DB_STRONG_DISTANCE_QUANTILE = 0.2
MAX_DATABASE_SWITCHES = 2
ENABLE_CONTEXT_CONTROL = True
MAX_CONTEXT_CHARS = 60000
RECENT_CONTEXT_TURNS = 2
MAX_MEMORY_ACTIONS = 30
MAX_MEMORY_OBSERVED_COLUMNS = 40
MAX_MEMORY_SQL_TESTS = 8
MAX_MEMORY_SCHEMA_CHARS = 12000
MAX_RECENT_TURN_CHARS = 12000
AGENT_RETRIEVAL_TOP_K = 3
WRITE_SAMPLE_DEBUG = True

BATCH_SIZE = 1024
RECREATE_DOCS_EMBEDDINGS = False

DEFAULT_DATASET_NAME = DATASET_NAME
DEFAULT_DATA_ROOT = DATA_ROOT
DEFAULT_LOG_ROOT = LOG_ROOT


def parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Expected boolean value, got: {value}")


def get_env(name: str, default, cast=str, aliases: tuple[str, ...] = ()):
    for env_name in (name, *aliases):
        if env_name in os.environ:
            value = os.environ[env_name]
            if cast is bool:
                return parse_bool(value)
            return cast(value)
    return default


def safe_path_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(name)).strip("_") or "default"


def get_runtime_config() -> dict:
    dataset_name = get_env("DATASET_NAME", DATASET_NAME)
    data_root = get_env("DATA_ROOT", DATA_ROOT)
    log_root = get_env("LOG_ROOT", LOG_ROOT)
    ollama_model = get_env("OLLAMA_MODEL", OLLAMA_MODEL)
    safe_model_name = safe_path_name(ollama_model)

    return {
        "DATASET_NAME": dataset_name,
        "DATA_ROOT": data_root,
        "LOG_ROOT": log_root,
        "TOP_N": get_env("TOP_N", TOP_N, int),
        "RESET_COST": get_env("RESET_COST", RESET_COST, bool),
        "OLLAMA_BASE_URL": get_env("OLLAMA_BASE_URL", OLLAMA_BASE_URL),
        "OLLAMA_MODEL": ollama_model,
        "SAFE_MODEL_NAME": safe_model_name,
        "LOG_PATH": get_env(
            "LOG_PATH",
            os.path.join(log_root, dataset_name, safe_model_name),
        ),
        "SENTENCE_TRANSFORMER_MODEL": get_env(
            "SENTENCE_TRANSFORMER_MODEL",
            SENTENCE_TRANSFORMER_MODEL,
        ),
        "RETRIEVAL_DEVICE": get_env(
            "RETRIEVAL_DEVICE",
            RETRIEVAL_DEVICE,
            aliases=("REACTLINK_RETRIEVAL_DEVICE",),
        ),
        "CANDIDATE_DB_MIN_HIT_COUNT": get_env(
            "CANDIDATE_DB_MIN_HIT_COUNT",
            CANDIDATE_DB_MIN_HIT_COUNT,
            int,
            aliases=("REACTLINK_CANDIDATE_DB_MIN_HIT_COUNT",),
        ),
        "CANDIDATE_DB_STRONG_DISTANCE_QUANTILE": get_env(
            "CANDIDATE_DB_STRONG_DISTANCE_QUANTILE",
            CANDIDATE_DB_STRONG_DISTANCE_QUANTILE,
            float,
            aliases=("REACTLINK_CANDIDATE_DB_STRONG_DISTANCE_QUANTILE",),
        ),
        "MAX_DATABASE_SWITCHES": get_env(
            "MAX_DATABASE_SWITCHES",
            MAX_DATABASE_SWITCHES,
            int,
            aliases=("REACTLINK_MAX_DATABASE_SWITCHES",),
        ),
        "ENABLE_CONTEXT_CONTROL": get_env(
            "ENABLE_CONTEXT_CONTROL",
            ENABLE_CONTEXT_CONTROL,
            bool,
            aliases=("REACTLINK_ENABLE_CONTEXT_CONTROL",),
        ),
        "MAX_CONTEXT_CHARS": get_env(
            "MAX_CONTEXT_CHARS",
            MAX_CONTEXT_CHARS,
            int,
            aliases=("REACTLINK_MAX_CONTEXT_CHARS",),
        ),
        "RECENT_CONTEXT_TURNS": get_env(
            "RECENT_CONTEXT_TURNS",
            RECENT_CONTEXT_TURNS,
            int,
            aliases=("REACTLINK_RECENT_CONTEXT_TURNS",),
        ),
        "MAX_MEMORY_ACTIONS": get_env(
            "MAX_MEMORY_ACTIONS",
            MAX_MEMORY_ACTIONS,
            int,
            aliases=("REACTLINK_MAX_MEMORY_ACTIONS",),
        ),
        "MAX_MEMORY_OBSERVED_COLUMNS": get_env(
            "MAX_MEMORY_OBSERVED_COLUMNS",
            MAX_MEMORY_OBSERVED_COLUMNS,
            int,
            aliases=("REACTLINK_MAX_MEMORY_OBSERVED_COLUMNS",),
        ),
        "MAX_MEMORY_SQL_TESTS": get_env(
            "MAX_MEMORY_SQL_TESTS",
            MAX_MEMORY_SQL_TESTS,
            int,
            aliases=("REACTLINK_MAX_MEMORY_SQL_TESTS",),
        ),
        "MAX_MEMORY_SCHEMA_CHARS": get_env(
            "MAX_MEMORY_SCHEMA_CHARS",
            MAX_MEMORY_SCHEMA_CHARS,
            int,
            aliases=("REACTLINK_MAX_MEMORY_SCHEMA_CHARS",),
        ),
        "MAX_RECENT_TURN_CHARS": get_env(
            "MAX_RECENT_TURN_CHARS",
            MAX_RECENT_TURN_CHARS,
            int,
            aliases=("REACTLINK_MAX_RECENT_TURN_CHARS",),
        ),
        "MODEL_DISCUSSION_TURNS": get_env(
            "MODEL_DISCUSSION_TURNS",
            MODEL_DISCUSSION_TURNS,
            int,
            aliases=("REACTLINK_MODEL_DISCUSSION_TURNS",),
        ),
        "AGENT_RETRIEVAL_TOP_K": get_env(
            "AGENT_RETRIEVAL_TOP_K",
            AGENT_RETRIEVAL_TOP_K,
            int,
            aliases=("REACTLINK_AGENT_RETRIEVAL_TOP_K",),
        ),
        "WRITE_SAMPLE_DEBUG": get_env("WRITE_SAMPLE_DEBUG", WRITE_SAMPLE_DEBUG, bool),
        "BATCH_SIZE": get_env("BATCH_SIZE", BATCH_SIZE, int),
        "RECREATE": get_env("RECREATE", RECREATE_DOCS_EMBEDDINGS, bool),
    }


def format_shell_value(value) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def print_shell_config() -> None:
    for key, value in get_runtime_config().items():
        print(f"{key}={shlex.quote(format_shell_value(value))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ReactLink runtime configuration")
    parser.add_argument("--shell", action="store_true", help="Print shell assignments for run scripts.")
    args = parser.parse_args()

    if args.shell:
        print_shell_config()
    else:
        for key, value in get_runtime_config().items():
            print(f"{key}={format_shell_value(value)}")
