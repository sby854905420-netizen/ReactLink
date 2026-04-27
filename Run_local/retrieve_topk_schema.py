import os
import json
import argparse
from tqdm import tqdm
import faiss
from cost_tool import SampleCostRecorder
from config import RETRIEVAL_DEVICE, SENTENCE_TRANSFORMER_MODEL, TOP_N
from utils import (
    DEFAULT_DATA_ROOT,
    DEFAULT_DATASET_NAME,
    DEFAULT_LOG_ROOT,
    INITIAL_VECTOR_RETRIEVED_COLUMNS_FILE,
    determine_embedding_path,
    get_cache_dir,
    get_pipeline_dir,
    get_sample_dir,
    get_status_dir,
    get_summary_dir,
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


def normalize_allowed_db_ids(allowed_db_ids):
    if not allowed_db_ids:
        return None
    return sorted({str(db_id) for db_id in allowed_db_ids if str(db_id)})


def metadata_in_scope(metadata: dict, allowed_db_ids: list[str] | None) -> bool:
    if not allowed_db_ids:
        return True
    return table_db_id(metadata.get("table", "")) in allowed_db_ids


def status_matches_scope(status: dict, allowed_db_ids: list[str] | None) -> bool:
    expected_scope = "candidate_db_ids" if allowed_db_ids else "global"
    if status.get("scope", "global") != expected_scope:
        return False
    if expected_scope == "candidate_db_ids":
        return sorted(status.get("candidate_db_ids", [])) == allowed_db_ids
    return True


def _retrieve_with_device_filtered(
    question: str,
    db_name: str,
    embed_path: str,
    excluded_indices: set,
    top_k: int = 5,
    device: str = "cuda:0",
    allowed_db_ids: list[str] | None = None,
):
    from model_manager import model_manager
    index_path = os.path.join(embed_path, "index.faiss")
    index = faiss.read_index(index_path)
    metadata_path = os.path.join(embed_path, "metadata.json")
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata_mapping = json.load(f)
    model_manager.load_model(device=device)
    question_embedding = model_manager.encode(question)
    similarity_scores, indices = index.search(question_embedding.reshape(1, -1), len(metadata_mapping))
    scoped_indices = {
        idx
        for idx, metadata in enumerate(metadata_mapping)
        if metadata_in_scope(metadata, allowed_db_ids)
    }
    filtered_results = []

    for i in range(len(indices[0])):
        idx = int(indices[0][i])
        if 0 <= idx < len(metadata_mapping) and idx in scoped_indices and idx not in excluded_indices:
            metadata = metadata_mapping[idx]
            filtered_results.append({
                "index": idx,
                "similarity_score": float(similarity_scores[0][i]),
                "metadata": metadata
            })
            if len(filtered_results) >= top_k:
                break

    return filtered_results, len(scoped_indices), scoped_indices, len(metadata_mapping)


def get_next_k_results(
    instance_id: str,
    question: str,
    db_name: str,
    embed_path: str,
    top_k: int,
    cache_dir: str,
    status_dir: str,
    device: str,
    allowed_db_ids=None,
):
    allowed_db_ids = normalize_allowed_db_ids(allowed_db_ids)
    cache = load_instance_cache(instance_id, cache_dir)
    status = load_instance_status(instance_id, status_dir)

    used_indices = set(cache.get("used_indices", []))

    if status_matches_scope(status, allowed_db_ids) and status.get("is_complete", False):
        print(f"Instance {instance_id} retrieve all completed.")
        return [], {}, "All columns in this databases are retrieved. There is no need to retrieve again."

    results, total_available, scoped_indices, global_total_available = _retrieve_with_device_filtered(
        question=question,
        db_name=db_name,
        embed_path=embed_path,
        excluded_indices=used_indices,
        top_k=top_k,
        device=device,
        allowed_db_ids=allowed_db_ids,
    )

    new_used_indices = [int(result["index"]) for result in results]
    all_used_indices = sorted(used_indices.union(new_used_indices))

    cache["used_indices"] = all_used_indices
    save_instance_cache(instance_id, cache_dir, cache)

    used_count = len(set(all_used_indices).intersection(scoped_indices))
    remaining_count = max(0, total_available - used_count)
    is_complete = len(results) < top_k or remaining_count <= 0
    scope = "candidate_db_ids" if allowed_db_ids else "global"

    status = {
        "scope": scope,
        "candidate_db_ids": allowed_db_ids or [],
        "is_complete": is_complete,
        "total_available": int(total_available),
        "used_count": int(used_count),
        "remaining_count": int(remaining_count),
        "total_available_in_scope": int(total_available),
        "used_count_in_scope": int(used_count),
        "remaining_count_in_scope": int(remaining_count),
        "global_total_available": int(global_total_available),
    }
    save_instance_status(instance_id, status_dir, status)
    
    metadata_mapping = {}
    for result in results:
        metadata_mapping[result["index"]] = result["metadata"]
    
    if is_complete:
        return results, metadata_mapping, "All columns in this databases are retrieved. There is no need to retrieve again."
    else:
        return results, metadata_mapping, ""


def update_instance_retrieval_scope(
    instance_id: str,
    embed_path: str,
    cache_dir: str,
    status_dir: str,
    allowed_db_ids=None,
) -> dict:
    allowed_db_ids = normalize_allowed_db_ids(allowed_db_ids)
    metadata_path = os.path.join(embed_path, "metadata.json")
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata_mapping = json.load(f)

    scoped_indices = {
        idx
        for idx, metadata in enumerate(metadata_mapping)
        if metadata_in_scope(metadata, allowed_db_ids)
    }
    cache = load_instance_cache(instance_id, cache_dir)
    used_count = len(set(cache.get("used_indices", [])).intersection(scoped_indices))
    total_available = len(scoped_indices)
    remaining_count = max(0, total_available - used_count)
    scope = "candidate_db_ids" if allowed_db_ids else "global"

    status = {
        "scope": scope,
        "candidate_db_ids": allowed_db_ids or [],
        "is_complete": remaining_count <= 0,
        "total_available": int(total_available),
        "used_count": int(used_count),
        "remaining_count": int(remaining_count),
        "total_available_in_scope": int(total_available),
        "used_count_in_scope": int(used_count),
        "remaining_count_in_scope": int(remaining_count),
        "global_total_available": int(len(metadata_mapping)),
    }
    save_instance_status(instance_id, status_dir, status)
    return status


def process_items_with_device(items, device, top_k, log_dir, dataset_name, data_root, write_sample_debug=False):
    print(f"Loading retrieval model on {device}...")
    try:
        from model_manager import model_manager
        model_manager.load_model(device=device)
        memory_info = model_manager.get_memory_usage()
        if memory_info:
            print(f"Retrieval model loaded on {memory_info['device']}")
        else:
            print("Retrieval model loaded on CPU")
    except Exception as e:
        print(f"Retrieval model load failed: {e}")
        print("Falling back to CPU mode")
        model_manager.load_model(device="cpu")

    results_by_instance = {}

    cache_dir = get_cache_dir(log_dir)
    status_dir = get_status_dir(log_dir)
    cost_output_path = summary_file(log_dir, "cost.json")

    for instance_id, item in tqdm(items.items(), desc="Initial retrieval"):
        with SampleCostRecorder(
            sample_id=instance_id,
            output_path=cost_output_path,
        ):
            question = item["question"]
            db_name = item["db_name"]

            embed_path = determine_embedding_path(instance_id, dataset_name, data_root)

            results, metadata_mapping, completion_message = get_next_k_results(
                instance_id=instance_id,
                question=question,
                db_name=db_name,
                embed_path=embed_path,
                top_k=top_k,
                cache_dir=cache_dir,
                status_dir=status_dir,
                device=device
            )

            table_candidates = []
            column_candidates = []
            column_types = []
            descriptions = []
            column_values = []
            similarity_scores = []

            for result in results:
                metadata = result["metadata"]

                table = metadata["table"]
                table_candidates.append(table)

                column = metadata["column"]
                column_candidates.append(column)

                column_type = metadata["column_type"]
                column_types.append(column_type)

                column_value = metadata["column_value"]
                column_values.append(column_value)

                description = metadata["description"]
                descriptions.append(description)

                similarity_scores.append(result["similarity_score"])

            results_by_instance[instance_id] = {
                "question": question,
                "db_name": db_name,
                "db_id": item.get("db_id"),
                "column_candidates": column_candidates,
                "column_types": column_types,
                "column_values": column_values,
                "table_candidates": table_candidates,
                "descriptions": descriptions,
                "similarity_scores": similarity_scores,
                "retrieved_count": len(results)
            }
            if write_sample_debug:
                os.makedirs(get_sample_dir(log_dir, instance_id), exist_ok=True)
                with open(sample_file(log_dir, instance_id, INITIAL_VECTOR_RETRIEVED_COLUMNS_FILE), "w", encoding="utf-8") as f:
                    json.dump(results_by_instance[instance_id], f, ensure_ascii=False, indent=2)

    return results_by_instance


def retrieve_additional(
    instance_id: str,
    question: str,
    additional_k: int,
    log_dir: str,
    dataset_name: str = DEFAULT_DATASET_NAME,
    data_root: str = DEFAULT_DATA_ROOT,
    device: str = "cuda:0",
):
    cache_dir = get_cache_dir(log_dir)
    status_dir = get_status_dir(log_dir)

    spider2_data = load_dataset_data(dataset_name, data_root)
    
    if instance_id not in spider2_data:
        raise ValueError(f"Instance {instance_id} does not exist")
    
    db_name = spider2_data[instance_id]["db_name"]
    embed_path = determine_embedding_path(instance_id, dataset_name, data_root)
    
    results, metadata_mapping, completion_message = get_next_k_results(
        instance_id=instance_id,
        question=question,
        db_name=db_name,
        embed_path=embed_path,
        top_k=additional_k,
        cache_dir=cache_dir,
        status_dir=status_dir,
        device=device
    )
    
    formatted_results = []
    for result in results:
        metadata = result["metadata"]
        formatted_results.append({
            "table": metadata["table"],
            "column": metadata["column"],
            "column_type": metadata["column_type"],
            "column_value": metadata["column_value"],
            "description": metadata["description"],
            "similarity_score": result["similarity_score"]
        })
    
    return formatted_results, completion_message


def retrieve(
    log_dir: str,
    top_n: int = 50,
    dataset_name: str = DEFAULT_DATASET_NAME,
    data_root: str = DEFAULT_DATA_ROOT,
    device: str = "cuda:0",
    write_sample_debug: bool = False,
):
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(get_summary_dir(log_dir), exist_ok=True)
    os.makedirs(get_cache_dir(log_dir), exist_ok=True)
    os.makedirs(get_pipeline_dir(log_dir), exist_ok=True)
    os.makedirs(get_status_dir(log_dir), exist_ok=True)

    spider2_data = load_dataset_data(dataset_name, data_root)

    instance_ids = list(spider2_data.keys())
    try:
        all_candidates = process_items_with_device(
            spider2_data,
            device,
            top_n,
            log_dir,
            dataset_name,
            data_root,
            write_sample_debug=write_sample_debug,
        )

        with open(pipeline_file(log_dir, INITIAL_VECTOR_RETRIEVED_COLUMNS_FILE), "w", encoding="utf-8") as f:
            json.dump(all_candidates, f, ensure_ascii=False, indent=2)
    finally:
        from model_manager import model_manager
        model_manager.release_model()

    print(f"Retrieval completed, results saved to {log_dir}/")
    print(f"Cache saved to {get_cache_dir(log_dir)}/")
    print(f"Status saved to {get_status_dir(log_dir)}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--log_path', type=str, default=os.path.join(DEFAULT_LOG_ROOT, DEFAULT_DATASET_NAME))
    parser.add_argument('--top_n', type=int, default=TOP_N)
    parser.add_argument('--dataset_name', type=str, default=DEFAULT_DATASET_NAME)
    parser.add_argument('--data_root', type=str, default=DEFAULT_DATA_ROOT)
    parser.add_argument('--device', '--retrieval_device', dest='device', type=str, default=RETRIEVAL_DEVICE)
    parser.add_argument('--sentence_transformer_model', type=str, default=SENTENCE_TRANSFORMER_MODEL)
    parser.add_argument("--write_sample_debug", type=parse_bool, default=False)
    args = parser.parse_args()

    if args.sentence_transformer_model:
        os.environ["SENTENCE_TRANSFORMER_MODEL"] = args.sentence_transformer_model

    retrieve(
        args.log_path,
        top_n=args.top_n,
        dataset_name=args.dataset_name,
        data_root=args.data_root,
        device=args.device,
        write_sample_debug=args.write_sample_debug,
    )
