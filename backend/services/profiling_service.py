import hashlib
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import inspect, text

from database.connection import engine
from database.table_service import (
    claim_profile_job,
    create_profile_job_record,
    get_profile_job,
    get_profile_jobs,
    get_recoverable_profile_jobs,
    get_table_column_profiles,
    get_table_data_version,
    mark_table_profile_stale,
    table_exists,
    update_profile_job_progress,
    update_profile_job_record,
    upsert_column_profile,
    validate_column_name,
    validate_table_name,
)


# Single worker is deliberate: profiling can be I/O heavy and should not
# compete with interactive warehouse queries on a local PostgreSQL instance.
# The queue API is decoupled so this executor can later be replaced by
# Celery/RQ/Arq without changing the frontend contract.
_PROFILE_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="warehouse-profiler",
)

DEFAULT_TARGET_SAMPLE_ROWS = 50_000
MAX_FINGERPRINT_VALUES = 64
FINGERPRINT_SOURCE_VALUES = 1_024
FULL_SCAN_ROW_THRESHOLD = 200_000
FULL_SCAN_SIZE_THRESHOLD_BYTES = 64 * 1024 * 1024
FULL_SCAN_HARD_ROW_LIMIT = 2_000_000
FULL_SCAN_HARD_SIZE_LIMIT_BYTES = 512 * 1024 * 1024
MIN_SAMPLE_PERCENT = 0.01
MAX_SAMPLE_PERCENT = 10.0


def _type_family(data_type: str) -> str:
    value = str(data_type or "").upper()

    if any(
        token in value
        for token in (
            "SMALLINT",
            "INTEGER",
            "BIGINT",
            "NUMERIC",
            "DECIMAL",
            "REAL",
            "FLOAT",
            "DOUBLE",
        )
    ):
        return "numeric"

    if any(
        token in value
        for token in (
            "CHAR",
            "TEXT",
            "STRING",
            "VARCHAR",
        )
    ):
        return "text"

    if "TIMESTAMP" in value:
        return "timestamp"

    if value.startswith("DATE"):
        return "date"

    if "BOOL" in value:
        return "boolean"

    if "UUID" in value:
        return "uuid"

    return "other"


def _fingerprint_supported(type_family: str) -> bool:
    return type_family in {
        "numeric",
        "text",
        "timestamp",
        "date",
        "boolean",
        "uuid",
    }


def _normalize_hash_value(value) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().casefold()
    if not normalized:
        return None

    return hashlib.sha256(
        normalized.encode("utf-8", errors="ignore")
    ).hexdigest()


def _estimate_table(table_name: str) -> dict:
    table_name = validate_table_name(table_name)

    query = text(
        """
        SELECT
            COALESCE(c.reltuples, 0)::bigint AS row_estimate,
            pg_total_relation_size(c.oid)::bigint AS table_size_bytes
        FROM pg_class c
        JOIN pg_namespace n
          ON n.oid = c.relnamespace
        WHERE c.relname = :table_name
          AND n.nspname = current_schema()
        LIMIT 1
        """
    )

    with engine.connect() as connection:
        row = connection.execute(
            query,
            {"table_name": table_name},
        ).mappings().one_or_none()

    if row is None:
        return {
            "row_count_estimate": None,
            "table_size_bytes": None,
        }

    estimate = int(row["row_estimate"] or 0)
    return {
        "row_count_estimate": (
            estimate if estimate >= 0 else None
        ),
        "table_size_bytes": int(row["table_size_bytes"] or 0),
    }


def _resolve_strategy(
    *,
    requested_strategy: str,
    row_count_estimate: int | None,
    table_size_bytes: int | None,
    target_sample_rows: int,
) -> dict:
    strategy = str(requested_strategy or "adaptive").lower()

    if strategy == "full":
        too_many_rows = (
            row_count_estimate is not None
            and row_count_estimate > FULL_SCAN_HARD_ROW_LIMIT
        )
        too_large = (
            table_size_bytes is not None
            and table_size_bytes > FULL_SCAN_HARD_SIZE_LIMIT_BYTES
        )
        if too_many_rows or too_large:
            raise ValueError(
                "Full profiling diblokir untuk tabel besar. "
                "Gunakan profile_strategy='adaptive' atau 'sampled'."
            )
        return {
            "profile_mode": "full",
            "sample_percent": None,
        }

    if strategy == "sampled":
        should_sample = True
    else:
        should_sample = not (
            row_count_estimate is not None
            and row_count_estimate <= FULL_SCAN_ROW_THRESHOLD
            and (table_size_bytes or 0) <= FULL_SCAN_SIZE_THRESHOLD_BYTES
        )

    if not should_sample:
        return {
            "profile_mode": "full",
            "sample_percent": None,
        }

    if row_count_estimate and row_count_estimate > 0:
        percent = (
            float(target_sample_rows)
            / float(row_count_estimate)
            * 100.0
        )
    else:
        # PostgreSQL reltuples may be missing before ANALYZE. A small default
        # SYSTEM sample plus a hard row LIMIT protects the warehouse from a
        # full scan even when statistics are unavailable.
        percent = 1.0

    percent = max(
        MIN_SAMPLE_PERCENT,
        min(MAX_SAMPLE_PERCENT, percent),
    )

    return {
        "profile_mode": "sampled",
        "sample_percent": round(percent, 6),
    }


def _quoted_identifier(value: str) -> str:
    return engine.dialect.identifier_preparer.quote(value)


def _create_temp_sample(
    connection,
    *,
    job_id: int,
    table_name: str,
    profile_mode: str,
    sample_percent: float | None,
    target_sample_rows: int,
) -> tuple[str, int]:
    temp_name = f"tmp_profile_{int(job_id)}"
    quoted_temp = _quoted_identifier(temp_name)
    quoted_table = _quoted_identifier(table_name)

    connection.execute(
        text(f"DROP TABLE IF EXISTS {quoted_temp}")
    )

    if profile_mode == "sampled":
        percent = float(sample_percent or 1.0)
        create_sql = (
            f"CREATE TEMP TABLE {quoted_temp} AS "
            f"SELECT * FROM {quoted_table} "
            f"TABLESAMPLE SYSTEM ({percent:.6f}) "
            f"LIMIT {int(target_sample_rows)}"
        )
    else:
        create_sql = (
            f"CREATE TEMP TABLE {quoted_temp} AS "
            f"SELECT * FROM {quoted_table}"
        )

    connection.execute(text(create_sql))

    sample_count = int(
        connection.execute(
            text(
                f"SELECT COUNT(*) FROM {quoted_temp}"
            )
        ).scalar_one()
        or 0
    )

    # SYSTEM sampling can return zero rows for a sparse/very small relation.
    # The fallback is still bounded by target_sample_rows.
    if profile_mode == "sampled" and sample_count == 0:
        connection.execute(
            text(f"DROP TABLE IF EXISTS {quoted_temp}")
        )
        connection.execute(
            text(
                f"CREATE TEMP TABLE {quoted_temp} AS "
                f"SELECT * FROM {quoted_table} "
                f"LIMIT {int(target_sample_rows)}"
            )
        )
        sample_count = int(
            connection.execute(
                text(
                    f"SELECT COUNT(*) FROM {quoted_temp}"
                )
            ).scalar_one()
            or 0
        )

    return temp_name, sample_count


def _profile_column(
    connection,
    *,
    temp_name: str,
    column_name: str,
    data_type: str,
    profile_mode: str,
    row_count_estimate: int | None,
    table_size_bytes: int | None,
    sample_row_count: int,
) -> dict:
    validate_column_name(column_name)
    quoted_temp = _quoted_identifier(temp_name)
    quoted_column = _quoted_identifier(column_name)

    # Prefix truncation protects memory when profiling large text/blob-like
    # columns. Relationship keys are normally far below this length.
    normalized_expression = (
        f"LEFT(CAST({quoted_column} AS TEXT), 512)"
    )

    stats_sql = text(
        f"""
        SELECT
            COUNT({quoted_column})::bigint AS non_null_count,
            COUNT(DISTINCT {normalized_expression})::bigint AS distinct_count,
            AVG(
                LEAST(
                    LENGTH(CAST({quoted_column} AS TEXT)),
                    512
                )
            )::double precision AS avg_length
        FROM {quoted_temp}
        """
    )

    stats = connection.execute(stats_sql).mappings().one()

    non_null_count = int(stats["non_null_count"] or 0)
    distinct_count = int(stats["distinct_count"] or 0)

    null_ratio = None
    if sample_row_count > 0:
        null_ratio = round(
            max(
                0.0,
                min(
                    1.0,
                    1.0
                    - (
                        float(non_null_count)
                        / float(sample_row_count)
                    ),
                ),
            ),
            8,
        )

    distinct_ratio = None
    if non_null_count > 0:
        distinct_ratio = round(
            max(
                0.0,
                min(
                    1.0,
                    float(distinct_count)
                    / float(non_null_count),
                ),
            ),
            8,
        )

    family = _type_family(data_type)
    fingerprints = []

    if _fingerprint_supported(family) and non_null_count > 0:
        value_rows = connection.execute(
            text(
                f"""
                SELECT DISTINCT {normalized_expression} AS value
                FROM {quoted_temp}
                WHERE {quoted_column} IS NOT NULL
                LIMIT {int(FINGERPRINT_SOURCE_VALUES)}
                """
            )
        ).scalars().all()

        hashes = {
            digest
            for value in value_rows
            if (digest := _normalize_hash_value(value))
        }
        fingerprints = sorted(hashes)[:MAX_FINGERPRINT_VALUES]

    return {
        "data_type": data_type,
        "type_family": family,
        "profile_mode": profile_mode,
        "row_count_estimate": row_count_estimate,
        "table_size_bytes": table_size_bytes,
        "sample_row_count": sample_row_count,
        "sample_non_null_count": non_null_count,
        "sample_distinct_count": distinct_count,
        "null_ratio": null_ratio,
        "distinct_ratio": distinct_ratio,
        "avg_length": (
            round(float(stats["avg_length"]), 4)
            if stats["avg_length"] is not None
            else None
        ),
        "value_fingerprint": fingerprints,
        "fingerprint_version": "sha256_min64_v1",
    }


def run_profile_job(job_id: int):
    job_id = int(job_id)

    try:
        job = claim_profile_job(job_id)
        if job is None:
            return None

        table_name = validate_table_name(job["table_name"])
        if not table_exists(table_name):
            raise ValueError(
                f"Tabel '{table_name}' tidak ditemukan."
            )

        source_data_version = get_table_data_version(
            table_name
        )

        metrics = _estimate_table(table_name)
        strategy = _resolve_strategy(
            requested_strategy=job["profile_strategy"],
            row_count_estimate=metrics["row_count_estimate"],
            table_size_bytes=metrics["table_size_bytes"],
            target_sample_rows=job["target_sample_rows"],
        )

        inspector = inspect(engine)
        column_metadata = {
            item["name"]: item
            for item in inspector.get_columns(table_name)
        }

        requested_columns = job["requested_columns"]
        if requested_columns:
            columns = [
                column
                for column in requested_columns
                if column in column_metadata
            ]
        else:
            columns = list(column_metadata.keys())

        if not columns:
            raise ValueError(
                "Tidak ada kolom valid yang dapat diprofiling."
            )

        update_profile_job_progress(
            job_id,
            processed_columns=0,
            total_columns=len(columns),
            source_data_version=source_data_version,
        )

        profiles = []

        with engine.connect() as connection:
            if engine.dialect.name == "postgresql":
                connection.execute(
                    text(
                        "SET LOCAL statement_timeout = '10min'"
                    )
                )
                connection.execute(
                    text(
                        "SET LOCAL lock_timeout = '30s'"
                    )
                )

            temp_name, sample_row_count = _create_temp_sample(
                connection,
                job_id=job_id,
                table_name=table_name,
                profile_mode=strategy["profile_mode"],
                sample_percent=strategy["sample_percent"],
                target_sample_rows=job["target_sample_rows"],
            )

            for column_name in columns:
                data_type = str(
                    column_metadata[column_name]["type"]
                )
                profile = _profile_column(
                    connection,
                    temp_name=temp_name,
                    column_name=column_name,
                    data_type=data_type,
                    profile_mode=strategy["profile_mode"],
                    row_count_estimate=metrics["row_count_estimate"],
                    table_size_bytes=metrics["table_size_bytes"],
                    sample_row_count=sample_row_count,
                )
                profile.update(
                    table_name=table_name,
                    column_name=column_name,
                    source_data_version=source_data_version,
                )
                profiles.append(
                    upsert_column_profile(profile)
                )
                update_profile_job_progress(
                    job_id,
                    processed_columns=len(profiles),
                    total_columns=len(columns),
                    source_data_version=source_data_version,
                )

        current_data_version = get_table_data_version(
            table_name
        )
        stale_on_completion = (
            current_data_version != source_data_version
        )
        if stale_on_completion:
            mark_table_profile_stale(
                table_name,
                "table_changed_during_profile",
            )

        summary = {
            "table_name": table_name,
            "profile_mode": strategy["profile_mode"],
            "sample_percent": strategy["sample_percent"],
            "row_count_estimate": metrics["row_count_estimate"],
            "table_size_bytes": metrics["table_size_bytes"],
            "sample_row_count": (
                profiles[0]["sample_row_count"]
                if profiles
                else 0
            ),
            "profiled_columns": len(profiles),
            "fingerprint_values_per_column_max": MAX_FINGERPRINT_VALUES,
            "source_data_version": source_data_version,
            "current_data_version": current_data_version,
            "stale_on_completion": stale_on_completion,
        }

        return update_profile_job_record(
            job_id,
            status="completed",
            result_summary=summary,
        )

    except Exception as error:
        try:
            update_profile_job_record(
                job_id,
                status="failed",
                error_message=str(error),
            )
        except Exception:
            pass
        print(
            "ERROR profiling job",
            job_id,
            repr(error),
        )
        return None


def _submit_profile_job(job_id: int):
    _PROFILE_EXECUTOR.submit(
        run_profile_job,
        int(job_id),
    )


def queue_profile_job(
    *,
    table_name: str,
    columns: list[str] | None = None,
    target_sample_rows: int = DEFAULT_TARGET_SAMPLE_ROWS,
    profile_strategy: str = "adaptive",
):
    job, created = create_profile_job_record(
        table_name=table_name,
        requested_columns=columns,
        target_sample_rows=target_sample_rows,
        profile_strategy=profile_strategy,
    )

    if created:
        _submit_profile_job(job["id"])

    return {
        "job": job,
        "created": created,
        "message": (
            "Profiling job masuk antrean."
            if created
            else (
                "Tabel tersebut sudah memiliki profiling job "
                "yang sedang queued/running."
            )
        ),
    }


def recover_profile_queue():
    job_ids = get_recoverable_profile_jobs()
    for job_id in job_ids:
        _submit_profile_job(job_id)
    return len(job_ids)


def get_table_profile_snapshot(table_name: str):
    table_name = validate_table_name(table_name)
    if not table_exists(table_name):
        raise ValueError(
            f"Tabel '{table_name}' tidak ditemukan."
        )

    profiles = get_table_column_profiles(table_name)
    return {
        "table_name": table_name,
        "profiled": bool(profiles),
        "profile_count": len(profiles),
        "stale_count": sum(
            1 for profile in profiles
            if profile["is_stale"]
        ),
        "profiles": profiles,
    }


def list_profile_jobs(
    *,
    table_name: str | None = None,
    limit: int = 50,
):
    return get_profile_jobs(
        table_name=table_name,
        limit=limit,
    )


def get_profile_job_status(job_id: int):
    return get_profile_job(job_id)
