import hashlib
import heapq
import re
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

from database.table_service import (
    SYSTEM_COLUMNS,
    claim_relationship_candidate_job,
    create_relationship_candidate_job_record,
    get_active_relationship_column_pairs,
    get_column_profiles_for_tables,
    get_profiled_table_names,
    get_recoverable_relationship_candidate_jobs,
    get_relationship_candidate_job,
    get_relationship_candidate_jobs,
    get_relationship_candidates,
    get_relationship_candidate_scores,
    update_relationship_candidate_job,
    upsert_relationship_candidate,
)


# Candidate discovery only reads profiling metadata. It never scans warehouse
# tables. The in-process queue is intentionally replaceable by Celery/RQ/Arq
# later without changing the HTTP contract.
_CANDIDATE_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="relationship-candidate",
)

DETECTOR_VERSION = "metadata_candidate_v1"
MAX_PAIR_EVALUATIONS = 500_000
MAX_PROFILE_COLUMNS_PER_JOB = 200_000
MAX_TOKEN_BUCKET = 750
MAX_FINGERPRINT_BUCKET = 500
MAX_NAME_BUCKET = 5_000

SUPPORTED_FAMILIES = {
    "numeric",
    "text",
    "date",
    "timestamp",
    "boolean",
    "uuid",
}

GENERIC_TOKENS = {
    "id",
    "code",
    "number",
    "name",
    "date",
    "value",
    "amount",
    "status",
    "type",
    "key",
}

TOKEN_ALIASES = {
    "kode": "code",
    "code": "code",
    "kd": "code",
    "nomor": "number",
    "no": "number",
    "num": "number",
    "number": "number",
    "bulan": "month",
    "month": "month",
    "bln": "month",
    "tahun": "year",
    "year": "year",
    "thn": "year",
    "rekening": "account",
    "account": "account",
    "acct": "account",
    "nasabah": "party",
    "debitur": "party",
    "customer": "party",
    "cust": "party",
    "bank": "bank",
    "bpr": "bank",
}


def _hash_key(*parts: str) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_candidate_key(
    table_a: str,
    column_a: str,
    table_b: str,
    column_b: str,
) -> str:
    left = f"{table_a}.{column_a}"
    right = f"{table_b}.{column_b}"
    ordered = sorted((left, right))
    return _hash_key("column_pair", *ordered)


def _table_pair_key(table_a: str, table_b: str) -> str:
    ordered = sorted((table_a, table_b))
    return _hash_key("table_pair", *ordered)


def _split_tokens(name: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name or ""))
    raw = [
        token.lower()
        for token in re.split(r"[^A-Za-z0-9]+", value)
        if token
    ]

    # Handle common compact forms such as bankid / idbank conservatively.
    expanded = []
    for token in raw:
        if token.endswith("id") and len(token) > 4:
            expanded.extend([token[:-2], "id"])
        elif token.startswith("id") and len(token) > 4:
            expanded.extend(["id", token[2:]])
        else:
            expanded.append(token)

    return [TOKEN_ALIASES.get(token, token) for token in expanded if token]


def _name_features(source_name: str, target_name: str) -> dict:
    source_tokens = _split_tokens(source_name)
    target_tokens = _split_tokens(target_name)
    source_set = set(source_tokens)
    target_set = set(target_tokens)

    source_compact = "".join(source_tokens)
    target_compact = "".join(target_tokens)

    token_union = source_set | target_set
    token_intersection = source_set & target_set
    token_jaccard = (
        len(token_intersection) / len(token_union)
        if token_union
        else 0.0
    )

    sequence = SequenceMatcher(
        None,
        source_compact,
        target_compact,
    ).ratio()

    signature_equal = bool(source_set) and source_set == target_set
    compact_equal = bool(source_compact) and source_compact == target_compact

    similarity = max(
        token_jaccard,
        sequence * 0.92,
        1.0 if signature_equal or compact_equal else 0.0,
    )

    return {
        "similarity": round(min(1.0, similarity), 6),
        "source_tokens": source_tokens,
        "target_tokens": target_tokens,
        "shared_tokens": sorted(token_intersection),
        "signature_equal": signature_equal,
        "compact_equal": compact_equal,
    }


def _fingerprint_overlap(source_profile: dict, target_profile: dict) -> dict:
    if (
        source_profile.get("fingerprint_version")
        != target_profile.get("fingerprint_version")
    ):
        return {
            "overlap": 0.0,
            "shared": 0,
            "source_count": 0,
            "target_count": 0,
            "comparable": False,
        }

    source_values = set(source_profile.get("value_fingerprint") or [])
    target_values = set(target_profile.get("value_fingerprint") or [])

    if not source_values or not target_values:
        return {
            "overlap": 0.0,
            "shared": 0,
            "source_count": len(source_values),
            "target_count": len(target_values),
            "comparable": False,
        }

    shared = len(source_values & target_values)
    denominator = min(len(source_values), len(target_values))
    overlap = shared / denominator if denominator else 0.0

    return {
        "overlap": round(min(1.0, overlap), 6),
        "shared": shared,
        "source_count": len(source_values),
        "target_count": len(target_values),
        "comparable": True,
    }


def _families_compatible(source_family: str, target_family: str) -> bool:
    if source_family == target_family:
        return source_family in SUPPORTED_FAMILIES

    # DATE and TIMESTAMP are semantically close enough to be discovered as
    # candidates. Query validation can later require explicit casts.
    return {source_family, target_family} == {"date", "timestamp"}


def _candidate_score(
    *,
    source_profile: dict,
    target_profile: dict,
    name_features: dict,
    fingerprint: dict,
) -> tuple[float, dict]:
    source_column = source_profile["column_name"]
    target_column = target_profile["column_name"]

    same_system_key = (
        source_column == target_column
        and source_column in SYSTEM_COLUMNS
    )

    name_score = float(name_features["similarity"])
    fingerprint_score = float(fingerprint["overlap"])

    # This is a discovery rank, not a final relationship confidence score.
    # Exact/similar names are intentionally strong because high-cardinality
    # relationship keys may have little fingerprint overlap in small samples.
    score = (
        0.50 * name_score
        + 0.40 * fingerprint_score
        + 0.10
    )

    if name_features["signature_equal"]:
        score = max(score, 0.82)
    if same_system_key:
        score = max(score, 0.97)

    source_tokens = set(name_features["source_tokens"])
    target_tokens = set(name_features["target_tokens"])
    only_generic_name = bool(source_tokens | target_tokens) and (
        (source_tokens | target_tokens) <= GENERIC_TOKENS
    )

    if only_generic_name and fingerprint_score < 0.10 and not same_system_key:
        score *= 0.72

    evidence = {
        "discovery_only": True,
        "datatype_family_match": (
            source_profile["type_family"] == target_profile["type_family"]
        ),
        "source_type_family": source_profile["type_family"],
        "target_type_family": target_profile["type_family"],
        "name": {
            "similarity": name_score,
            "signature_equal": name_features["signature_equal"],
            "compact_equal": name_features["compact_equal"],
            "shared_tokens": name_features["shared_tokens"],
        },
        "fingerprint": fingerprint,
        "same_system_key": same_system_key,
        "source_distinct_ratio": source_profile.get("distinct_ratio"),
        "target_distinct_ratio": target_profile.get("distinct_ratio"),
        "source_null_ratio": source_profile.get("null_ratio"),
        "target_null_ratio": target_profile.get("null_ratio"),
    }

    return round(max(0.0, min(1.0, score)), 6), evidence


def _build_target_indexes(target_profiles: list[dict]):
    name_index = {}
    token_index = {}
    fingerprint_index = {}

    for index, profile in enumerate(target_profiles):
        tokens = _split_tokens(profile["column_name"])
        signature = "|".join(sorted(set(tokens)))
        if signature:
            name_index.setdefault(signature, []).append(index)

        for token in set(tokens):
            if len(token) >= 3 and token not in GENERIC_TOKENS:
                token_index.setdefault(token, []).append(index)

        for digest in set(profile.get("value_fingerprint") or []):
            fingerprint_index.setdefault(digest, []).append(index)

    # Extremely broad buckets create O(n²) behavior and are therefore omitted.
    name_index = {
        key: values
        for key, values in name_index.items()
        if len(values) <= MAX_NAME_BUCKET
    }
    token_index = {
        key: values
        for key, values in token_index.items()
        if len(values) <= MAX_TOKEN_BUCKET
    }
    fingerprint_index = {
        key: values
        for key, values in fingerprint_index.items()
        if len(values) <= MAX_FINGERPRINT_BUCKET
    }

    return name_index, token_index, fingerprint_index


def _candidate_target_indexes(
    source_profile: dict,
    *,
    name_index: dict,
    token_index: dict,
    fingerprint_index: dict,
):
    matches = set()
    tokens = _split_tokens(source_profile["column_name"])
    signature = "|".join(sorted(set(tokens)))

    if signature:
        matches.update(name_index.get(signature, []))

    for token in set(tokens):
        if len(token) >= 3 and token not in GENERIC_TOKENS:
            matches.update(token_index.get(token, []))

    for digest in set(source_profile.get("value_fingerprint") or []):
        matches.update(fingerprint_index.get(digest, []))

    return matches


def _existing_pair_keys() -> set[str]:
    keys = set()
    for pair in get_active_relationship_column_pairs():
        keys.add(
            _canonical_candidate_key(
                pair["source_table"],
                pair["source_column"],
                pair["target_table"],
                pair["target_column"],
            )
        )
    return keys


def _resolve_job_profiles(job: dict):
    all_profiled_tables = get_profiled_table_names(include_stale=False)
    all_profiled_set = set(all_profiled_tables)

    mode = job["scan_mode"]
    requested_sources = list(job["source_tables"] or [])
    requested_targets = list(job["target_tables"] or [])

    if mode == "selected":
        source_tables = requested_sources
        target_tables = requested_targets
    elif mode == "source_vs_all":
        source_tables = requested_sources
        target_tables = all_profiled_tables
    else:
        source_tables = all_profiled_tables
        target_tables = all_profiled_tables

    missing_source_profiles = sorted(
        table for table in source_tables if table not in all_profiled_set
    )
    missing_target_profiles = sorted(
        table for table in target_tables if table not in all_profiled_set
    )

    source_profiles = get_column_profiles_for_tables(
        source_tables,
        include_stale=False,
    )
    target_profiles = get_column_profiles_for_tables(
        target_tables,
        include_stale=False,
    )

    if not job["include_system_columns"]:
        source_profiles = [
            profile
            for profile in source_profiles
            if profile["column_name"] not in SYSTEM_COLUMNS
        ]
        target_profiles = [
            profile
            for profile in target_profiles
            if profile["column_name"] not in SYSTEM_COLUMNS
        ]

    source_profiles = [
        profile
        for profile in source_profiles
        if profile["type_family"] in SUPPORTED_FAMILIES
    ]
    target_profiles = [
        profile
        for profile in target_profiles
        if profile["type_family"] in SUPPORTED_FAMILIES
    ]

    considered = len(source_profiles) + len(target_profiles)
    if considered > MAX_PROFILE_COLUMNS_PER_JOB:
        raise ValueError(
            "Candidate job mencakup terlalu banyak profile column "
            f"({considered:,}). Persempit scope atau pecah menjadi beberapa job."
        )

    return {
        "source_profiles": source_profiles,
        "target_profiles": target_profiles,
        "missing_source_profiles": missing_source_profiles,
        "missing_target_profiles": missing_target_profiles,
        "profile_columns_considered": considered,
    }


def run_relationship_candidate_job(job_id: int):
    job_id = int(job_id)

    try:
        job = claim_relationship_candidate_job(job_id)
        if job is None:
            return None

        resolved = _resolve_job_profiles(job)
        source_profiles = resolved["source_profiles"]
        target_profiles = resolved["target_profiles"]

        update_relationship_candidate_job(
            job_id,
            profile_columns_considered=resolved["profile_columns_considered"],
        )

        name_index, token_index, fingerprint_index = _build_target_indexes(
            target_profiles
        )
        existing_keys = _existing_pair_keys()
        seen_keys = set()
        heap = []
        sequence = 0
        pair_evaluations = 0
        skipped_existing = 0
        truncated = False

        for source_profile in source_profiles:
            target_indexes = _candidate_target_indexes(
                source_profile,
                name_index=name_index,
                token_index=token_index,
                fingerprint_index=fingerprint_index,
            )

            for target_index in target_indexes:
                if pair_evaluations >= MAX_PAIR_EVALUATIONS:
                    truncated = True
                    break

                target_profile = target_profiles[target_index]

                if source_profile["table_name"] == target_profile["table_name"]:
                    continue

                if not _families_compatible(
                    source_profile["type_family"],
                    target_profile["type_family"],
                ):
                    continue

                candidate_key = _canonical_candidate_key(
                    source_profile["table_name"],
                    source_profile["column_name"],
                    target_profile["table_name"],
                    target_profile["column_name"],
                )

                if candidate_key in seen_keys:
                    continue
                seen_keys.add(candidate_key)
                pair_evaluations += 1

                if candidate_key in existing_keys:
                    skipped_existing += 1
                    continue

                name_features = _name_features(
                    source_profile["column_name"],
                    target_profile["column_name"],
                )
                fingerprint = _fingerprint_overlap(
                    source_profile,
                    target_profile,
                )
                score, evidence = _candidate_score(
                    source_profile=source_profile,
                    target_profile=target_profile,
                    name_features=name_features,
                    fingerprint=fingerprint,
                )

                if score < float(job["min_discovery_score"]):
                    continue

                candidate = {
                    "candidate_key": candidate_key,
                    "table_pair_key": _table_pair_key(
                        source_profile["table_name"],
                        target_profile["table_name"],
                    ),
                    "source_table": source_profile["table_name"],
                    "source_column": source_profile["column_name"],
                    "target_table": target_profile["table_name"],
                    "target_column": target_profile["column_name"],
                    "source_profile_version": source_profile["profile_version"],
                    "target_profile_version": target_profile["profile_version"],
                    "source_data_version": source_profile["source_data_version"],
                    "target_data_version": target_profile["source_data_version"],
                    "source_type_family": source_profile["type_family"],
                    "target_type_family": target_profile["type_family"],
                    "name_similarity": name_features["similarity"],
                    "fingerprint_overlap": fingerprint["overlap"],
                    "discovery_score": score,
                    "evidence": evidence,
                    "detector_version": DETECTOR_VERSION,
                    "last_seen_job_id": job_id,
                }

                sequence += 1
                heap_item = (score, sequence, candidate)
                if len(heap) < int(job["max_candidates"]):
                    heapq.heappush(heap, heap_item)
                elif score > heap[0][0]:
                    heapq.heapreplace(heap, heap_item)

            if truncated:
                break

        ranked = [
            item[2]
            for item in sorted(heap, key=lambda item: (-item[0], item[1]))
        ]

        persisted = [
            upsert_relationship_candidate(candidate)
            for candidate in ranked
        ]

        summary = {
            "detector_version": DETECTOR_VERSION,
            "metadata_only": True,
            "warehouse_rows_scanned": 0,
            "source_profile_columns": len(source_profiles),
            "target_profile_columns": len(target_profiles),
            "profile_columns_considered": resolved[
                "profile_columns_considered"
            ],
            "pair_evaluations": pair_evaluations,
            "pair_evaluation_hard_limit": MAX_PAIR_EVALUATIONS,
            "generated_count": len(persisted),
            "skipped_existing_count": skipped_existing,
            "truncated": truncated,
            "missing_source_profiles": resolved["missing_source_profiles"],
            "missing_target_profiles": resolved["missing_target_profiles"],
            "note": (
                "discovery_score adalah ranking kandidat awal, bukan final "
                "relationship confidence. Scoring final ada di Step 6B.2.3."
            ),
        }

        return update_relationship_candidate_job(
            job_id,
            status="completed",
            profile_columns_considered=resolved["profile_columns_considered"],
            pair_evaluations=pair_evaluations,
            generated_count=len(persisted),
            skipped_existing_count=skipped_existing,
            truncated=truncated,
            result_summary=summary,
        )

    except Exception as error:
        try:
            update_relationship_candidate_job(
                job_id,
                status="failed",
                error_message=str(error),
            )
        except Exception:
            pass
        print("ERROR relationship candidate job", job_id, repr(error))
        return None


def _submit_candidate_job(job_id: int):
    _CANDIDATE_EXECUTOR.submit(
        run_relationship_candidate_job,
        int(job_id),
    )


def queue_relationship_candidate_job(
    *,
    scan_mode: str = "selected",
    source_tables: list[str] | None = None,
    target_tables: list[str] | None = None,
    min_discovery_score: float = 0.45,
    max_candidates: int = 1000,
    include_system_columns: bool = True,
):
    job, created = create_relationship_candidate_job_record(
        scan_mode=scan_mode,
        source_tables=source_tables,
        target_tables=target_tables,
        min_discovery_score=min_discovery_score,
        max_candidates=max_candidates,
        include_system_columns=include_system_columns,
    )

    if created:
        _submit_candidate_job(job["id"])

    return {
        "job": job,
        "created": created,
        "message": (
            "Relationship candidate job masuk antrean."
            if created
            else "Candidate job dengan scope yang sama masih queued/running."
        ),
    }


def recover_relationship_candidate_queue():
    job_ids = get_recoverable_relationship_candidate_jobs()
    for job_id in job_ids:
        _submit_candidate_job(job_id)
    return len(job_ids)


def list_relationship_candidate_jobs(*, limit: int = 50):
    return get_relationship_candidate_jobs(limit=limit)


def get_relationship_candidate_job_status(job_id: int):
    return get_relationship_candidate_job(job_id)


def list_relationship_candidates(
    *,
    source_table: str | None = None,
    target_table: str | None = None,
    status: str | None = None,
    include_stale: bool = False,
    min_discovery_score: float = 0.0,
    limit: int = 200,
):
    rows = get_relationship_candidates(
        source_table=source_table,
        target_table=target_table,
        status=status,
        include_stale=include_stale,
        min_discovery_score=min_discovery_score,
        limit=limit,
    )
    scores = get_relationship_candidate_scores([row["id"] for row in rows])
    for row in rows:
        row["quality_score"] = scores.get(row["id"])
    return rows
