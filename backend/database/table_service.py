import re
from contextlib import nullcontext

from services.relationship_freshness_service import (
    material_signature, quality_signature, candidate_signature, validate_freshness, VERSION_FIELDS,
)

import pandas as pd
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    cast,
    delete,
    func,
    inspect,
    or_,
    select,
    text,
)

from database.connection import engine


SYSTEM_COLUMNS = {"bank_id", "bulan", "tahun"}
SCHEMA_MAPPING_TABLE_NAME = "warehouse_schema_mapping"
COLUMN_SETTINGS_TABLE_NAME = "warehouse_column_settings"
RELATIONSHIPS_TABLE_NAME = "warehouse_table_relationships"
RELATIONSHIP_COLUMNS_TABLE_NAME = "warehouse_relationship_columns"
COLUMN_PROFILES_TABLE_NAME = "warehouse_column_profiles"
PROFILE_JOBS_TABLE_NAME = "warehouse_profile_jobs"
TABLE_STATE_TABLE_NAME = "warehouse_table_state"
RELATIONSHIP_CANDIDATES_TABLE_NAME = "warehouse_relationship_candidates"
RELATIONSHIP_CANDIDATE_JOBS_TABLE_NAME = "warehouse_relationship_candidate_jobs"
RELATIONSHIP_CANDIDATE_SCORES_TABLE_NAME = "warehouse_relationship_candidate_scores"
RELATIONSHIP_SCORING_JOBS_TABLE_NAME = "warehouse_relationship_scoring_jobs"
RELATIONSHIP_CARDINALITY_ESTIMATES_TABLE_NAME = "warehouse_relationship_cardinality_estimates"
RELATIONSHIP_CARDINALITY_JOBS_TABLE_NAME = "warehouse_relationship_cardinality_jobs"
RELATIONSHIP_REVIEWS_TABLE_NAME = "warehouse_relationship_reviews"
RELATIONSHIP_REVIEW_CANDIDATES_TABLE_NAME = "warehouse_relationship_review_candidates"
MASK_VALUE = "••••••••"
PROFILE_JOB_STATUSES = {
    "queued",
    "running",
    "completed",
    "failed",
}
RELATIONSHIP_CANDIDATE_JOB_STATUSES = {
    "queued",
    "running",
    "completed",
    "failed",
}
RELATIONSHIP_SCORING_JOB_STATUSES = {
    "queued", "running", "completed", "failed",
}
RELATIONSHIP_CARDINALITY_JOB_STATUSES = {
    "queued", "running", "completed", "failed",
}
RELATIONSHIP_CANDIDATE_STATUSES = {
    "pending",
    "rejected",
    "promoted",
    "stale",
}
RELATIONSHIP_CARDINALITIES = {
    "one_to_one",
    "one_to_many",
    "many_to_one",
    "many_to_many",
}
INTERNAL_TABLES = {
    SCHEMA_MAPPING_TABLE_NAME,
    COLUMN_SETTINGS_TABLE_NAME,
    RELATIONSHIPS_TABLE_NAME,
    RELATIONSHIP_COLUMNS_TABLE_NAME,
    COLUMN_PROFILES_TABLE_NAME,
    PROFILE_JOBS_TABLE_NAME,
    TABLE_STATE_TABLE_NAME,
    RELATIONSHIP_CANDIDATES_TABLE_NAME,
    RELATIONSHIP_CANDIDATE_JOBS_TABLE_NAME,
    RELATIONSHIP_CANDIDATE_SCORES_TABLE_NAME,
    RELATIONSHIP_SCORING_JOBS_TABLE_NAME,
    RELATIONSHIP_CARDINALITY_ESTIMATES_TABLE_NAME,
    RELATIONSHIP_CARDINALITY_JOBS_TABLE_NAME,
    RELATIONSHIP_REVIEWS_TABLE_NAME,
    RELATIONSHIP_REVIEW_CANDIDATES_TABLE_NAME,
}


# =====================================================
# INTERNAL METADATA TABLE
# =====================================================

metadata = MetaData()

schema_mapping_table = Table(
    SCHEMA_MAPPING_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("table_name", String(63), nullable=False),
    Column("source_ordinal", Integer, nullable=False),
    Column("source_column", String(255), nullable=False),
    Column("database_column", String(63), nullable=False),
    UniqueConstraint(
        "table_name",
        "source_ordinal",
        name="uq_schema_mapping_table_ordinal",
    ),
)

column_settings_table = Table(
    COLUMN_SETTINGS_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("table_name", String(63), nullable=False),
    Column("column_name", String(63), nullable=False),
    Column(
        "is_masked",
        Boolean,
        nullable=False,
        default=False,
    ),
    UniqueConstraint(
        "table_name",
        "column_name",
        name="uq_column_settings_table_column",
    ),
)


relationships_table = Table(
    RELATIONSHIPS_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("relationship_name", String(180), nullable=False),
    Column("source_table", String(63), nullable=False),
    # source_column / target_column tetap dipertahankan sebagai
    # primary pair agar metadata lama dan frontend lama tetap kompatibel.
    Column("source_column", String(63), nullable=False),
    Column("target_table", String(63), nullable=False),
    Column("target_column", String(63), nullable=False),
    Column("cardinality", String(32), nullable=False),
    Column(
        "is_active",
        Boolean,
        nullable=False,
        default=True,
    ),
    Column(
        "created_at",
        DateTime,
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        "updated_at",
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
)


relationship_columns_table = Table(
    RELATIONSHIP_COLUMNS_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("relationship_id", Integer, nullable=False),
    Column("source_column", String(63), nullable=False),
    Column("target_column", String(63), nullable=False),
    Column("ordinal", Integer, nullable=False),
    UniqueConstraint(
        "relationship_id",
        "ordinal",
        name="uq_relationship_columns_relationship_ordinal",
    ),
)


column_profiles_table = Table(
    COLUMN_PROFILES_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("table_name", String(63), nullable=False),
    Column("column_name", String(63), nullable=False),
    Column("data_type", String(128), nullable=False),
    Column("type_family", String(32), nullable=False),
    Column("profile_version", Integer, nullable=False, default=1),
    Column("profile_mode", String(32), nullable=False),
    Column("source_data_version", BigInteger, nullable=False, default=1),
    Column("row_count_estimate", BigInteger, nullable=True),
    Column("table_size_bytes", BigInteger, nullable=True),
    Column("sample_row_count", BigInteger, nullable=False, default=0),
    Column("sample_non_null_count", BigInteger, nullable=False, default=0),
    Column("sample_distinct_count", BigInteger, nullable=False, default=0),
    Column("null_ratio", Float, nullable=True),
    Column("distinct_ratio", Float, nullable=True),
    Column("avg_length", Float, nullable=True),
    Column("value_fingerprint", JSON, nullable=True),
    Column(
        "fingerprint_version",
        String(32),
        nullable=False,
        default="sha256_min64_v1",
    ),
    Column("is_stale", Boolean, nullable=False, default=False),
    Column("stale_reason", String(255), nullable=True),
    Column(
        "last_profiled_at",
        DateTime,
        nullable=False,
        server_default=func.now(),
    ),
    UniqueConstraint(
        "table_name",
        "column_name",
        name="uq_column_profiles_table_column",
    ),
)


profile_jobs_table = Table(
    PROFILE_JOBS_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("table_name", String(63), nullable=False),
    Column("status", String(24), nullable=False),
    Column("requested_columns", JSON, nullable=True),
    Column("target_sample_rows", Integer, nullable=False, default=50000),
    Column("profile_strategy", String(32), nullable=False, default="adaptive"),
    Column("source_data_version", BigInteger, nullable=True),
    Column("total_columns", Integer, nullable=False, default=0),
    Column("processed_columns", Integer, nullable=False, default=0),
    Column(
        "worker_backend",
        String(32),
        nullable=False,
        default="in_process_v1",
    ),
    Column(
        "created_at",
        DateTime,
        nullable=False,
        server_default=func.now(),
    ),
    Column("started_at", DateTime, nullable=True),
    Column("finished_at", DateTime, nullable=True),
    Column("error_message", Text, nullable=True),
    Column("result_summary", JSON, nullable=True),
)


table_state_table = Table(
    TABLE_STATE_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("table_name", String(63), nullable=False, unique=True),
    Column("data_version", BigInteger, nullable=False, default=1),
    Column(
        "updated_at",
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
)


relationship_candidates_table = Table(
    RELATIONSHIP_CANDIDATES_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("candidate_key", String(64), nullable=False, unique=True),
    Column("table_pair_key", String(64), nullable=False),
    Column("source_table", String(63), nullable=False),
    Column("source_column", String(63), nullable=False),
    Column("target_table", String(63), nullable=False),
    Column("target_column", String(63), nullable=False),
    Column("source_profile_version", Integer, nullable=False),
    Column("target_profile_version", Integer, nullable=False),
    Column("source_data_version", BigInteger, nullable=False),
    Column("target_data_version", BigInteger, nullable=False),
    Column("source_type_family", String(32), nullable=False),
    Column("target_type_family", String(32), nullable=False),
    Column("name_similarity", Float, nullable=False, default=0.0),
    Column("fingerprint_overlap", Float, nullable=False, default=0.0),
    Column("discovery_score", Float, nullable=False, default=0.0),
    Column("evidence", JSON, nullable=True),
    Column("detector_version", String(48), nullable=False),
    Column("status", String(24), nullable=False, default="pending"),
    Column("is_stale", Boolean, nullable=False, default=False),
    Column("stale_reason", String(255), nullable=True),
    Column("last_seen_job_id", Integer, nullable=True),
    Column(
        "created_at",
        DateTime,
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        "updated_at",
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
)


relationship_candidate_jobs_table = Table(
    RELATIONSHIP_CANDIDATE_JOBS_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("status", String(24), nullable=False),
    Column("scan_mode", String(32), nullable=False),
    Column("source_tables", JSON, nullable=True),
    Column("target_tables", JSON, nullable=True),
    Column("min_discovery_score", Float, nullable=False, default=0.45),
    Column("max_candidates", Integer, nullable=False, default=1000),
    Column("include_system_columns", Boolean, nullable=False, default=True),
    Column("profile_columns_considered", Integer, nullable=False, default=0),
    Column("pair_evaluations", BigInteger, nullable=False, default=0),
    Column("generated_count", Integer, nullable=False, default=0),
    Column("skipped_existing_count", Integer, nullable=False, default=0),
    Column("truncated", Boolean, nullable=False, default=False),
    Column(
        "worker_backend",
        String(32),
        nullable=False,
        default="in_process_v1",
    ),
    Column(
        "created_at",
        DateTime,
        nullable=False,
        server_default=func.now(),
    ),
    Column("started_at", DateTime, nullable=True),
    Column("finished_at", DateTime, nullable=True),
    Column("error_message", Text, nullable=True),
    Column("result_summary", JSON, nullable=True),
)


relationship_candidate_scores_table = Table(
    RELATIONSHIP_CANDIDATE_SCORES_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("candidate_id", Integer, nullable=False, unique=True),
    Column("candidate_key", String(64), nullable=False),
    Column("scoring_version", String(48), nullable=False),
    Column("source_profile_version", Integer, nullable=False),
    Column("target_profile_version", Integer, nullable=False),
    Column("source_data_version", BigInteger, nullable=False),
    Column("target_data_version", BigInteger, nullable=False),
    Column("semantic_score", Float, nullable=False, default=0.0),
    Column("datatype_score", Float, nullable=False, default=0.0),
    Column("fingerprint_score", Float, nullable=True),
    Column("profile_quality_score", Float, nullable=False, default=0.0),
    Column("key_plausibility_score", Float, nullable=False, default=0.0),
    Column("evidence_sufficiency_score", Float, nullable=False, default=0.0),
    Column("penalty_score", Float, nullable=False, default=0.0),
    Column("confidence_score", Float, nullable=False, default=0.0),
    Column("confidence_level", String(24), nullable=False),
    Column("component_scores", JSON, nullable=True),
    Column("quality_flags", JSON, nullable=True),
    Column("rationale", JSON, nullable=True),
    Column("is_stale", Boolean, nullable=False, default=False),
    Column("stale_reason", String(255), nullable=True),
    Column("last_scored_job_id", Integer, nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("updated_at", DateTime, nullable=False, server_default=func.now(), onupdate=func.now()),
)

relationship_scoring_jobs_table = Table(
    RELATIONSHIP_SCORING_JOBS_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("status", String(24), nullable=False),
    Column("source_tables", JSON, nullable=True),
    Column("target_tables", JSON, nullable=True),
    Column("candidate_status", String(24), nullable=True),
    Column("min_discovery_score", Float, nullable=False, default=0.45),
    Column("max_candidates", Integer, nullable=False, default=5000),
    Column("candidate_count", Integer, nullable=False, default=0),
    Column("scored_count", Integer, nullable=False, default=0),
    Column("skipped_count", Integer, nullable=False, default=0),
    Column("worker_backend", String(32), nullable=False, default="in_process_v1"),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("started_at", DateTime, nullable=True),
    Column("finished_at", DateTime, nullable=True),
    Column("error_message", Text, nullable=True),
    Column("result_summary", JSON, nullable=True),
)


relationship_cardinality_estimates_table = Table(
    RELATIONSHIP_CARDINALITY_ESTIMATES_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("candidate_id", Integer, nullable=False, unique=True),
    Column("candidate_key", String(64), nullable=False),
    Column("estimation_version", String(48), nullable=False),
    Column("source_profile_version", Integer, nullable=False),
    Column("target_profile_version", Integer, nullable=False),
    Column("source_data_version", BigInteger, nullable=False),
    Column("target_data_version", BigInteger, nullable=False),
    Column("source_role", String(24), nullable=False),
    Column("target_role", String(24), nullable=False),
    Column("source_role_confidence", Float, nullable=False, default=0.0),
    Column("target_role_confidence", Float, nullable=False, default=0.0),
    Column("estimated_cardinality", String(32), nullable=False),
    Column("cardinality_confidence", Float, nullable=False, default=0.0),
    Column("evidence", JSON, nullable=True),
    Column("quality_flags", JSON, nullable=True),
    Column("requires_review", Boolean, nullable=False, default=True),
    Column("is_stale", Boolean, nullable=False, default=False),
    Column("stale_reason", String(255), nullable=True),
    Column("last_estimated_job_id", Integer, nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column(
        "updated_at",
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
)


relationship_cardinality_jobs_table = Table(
    RELATIONSHIP_CARDINALITY_JOBS_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("status", String(24), nullable=False),
    Column("source_tables", JSON, nullable=True),
    Column("target_tables", JSON, nullable=True),
    Column("candidate_status", String(24), nullable=True),
    Column("min_discovery_score", Float, nullable=False, default=0.45),
    Column("min_quality_score", Float, nullable=False, default=0.0),
    Column("max_candidates", Integer, nullable=False, default=5000),
    Column("candidate_count", Integer, nullable=False, default=0),
    Column("estimated_count", Integer, nullable=False, default=0),
    Column("skipped_count", Integer, nullable=False, default=0),
    Column("worker_backend", String(32), nullable=False, default="in_process_v1"),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("started_at", DateTime, nullable=True),
    Column("finished_at", DateTime, nullable=True),
    Column("error_message", Text, nullable=True),
    Column("result_summary", JSON, nullable=True),
)


# Append-only decision ledger. No cascading relationship FK: audit survives deletion.
relationship_reviews_table = Table(
    RELATIONSHIP_REVIEWS_TABLE_NAME, metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("request_key", String(64), nullable=False, unique=True),
    Column("request_digest", String(64), nullable=False),
    Column("reviewed_by", String(180), nullable=False),
    Column("reviewer_source", String(48), nullable=False),
    Column("reviewed_at", DateTime, nullable=False, server_default=func.now()),
    Column("review_note", Text, nullable=False),
    Column("decision", String(24), nullable=False),
    Column("promoted_relationship_id", Integer, nullable=True),
    Column("snapshot", JSON, nullable=False),
    Column("confirmation", JSON, nullable=False),
)
relationship_review_candidates_table = Table(
    RELATIONSHIP_REVIEW_CANDIDATES_TABLE_NAME, metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("review_id", Integer, nullable=False),
    Column("candidate_id", Integer, nullable=False),
    Column("material_signature", String(64), nullable=False),
    UniqueConstraint("review_id", "candidate_id", name="uq_review_candidate"),
)
Index("ix_review_candidates_history", relationship_review_candidates_table.c.candidate_id,
      relationship_review_candidates_table.c.review_id)


Index(
    "ix_column_profiles_table_stale",
    column_profiles_table.c.table_name,
    column_profiles_table.c.is_stale,
)

Index(
    "ix_profile_jobs_table_status",
    profile_jobs_table.c.table_name,
    profile_jobs_table.c.status,
)


Index(
    "ix_relationship_candidates_status_score",
    relationship_candidates_table.c.status,
    relationship_candidates_table.c.is_stale,
    relationship_candidates_table.c.discovery_score,
)

Index(
    "ix_relationship_candidates_table_pair",
    relationship_candidates_table.c.source_table,
    relationship_candidates_table.c.target_table,
)

Index(
    "ix_relationship_candidate_jobs_status",
    relationship_candidate_jobs_table.c.status,
    relationship_candidate_jobs_table.c.id,
)

Index(
    "ix_relationship_candidate_scores_confidence",
    relationship_candidate_scores_table.c.is_stale,
    relationship_candidate_scores_table.c.confidence_score,
)


Index(
    "ix_relationship_cardinality_estimates_cardinality",
    relationship_cardinality_estimates_table.c.is_stale,
    relationship_cardinality_estimates_table.c.estimated_cardinality,
    relationship_cardinality_estimates_table.c.cardinality_confidence,
)

Index(
    "ix_relationship_cardinality_jobs_status",
    relationship_cardinality_jobs_table.c.status,
    relationship_cardinality_jobs_table.c.id,
)

Index(
    "ix_relationship_scoring_jobs_status",
    relationship_scoring_jobs_table.c.status,
    relationship_scoring_jobs_table.c.id,
)


def _backfill_relationship_columns():
    """Migrate relationship lama menjadi composite metadata 1-pair.

    Table header lama tetap menjadi source of truth untuk primary pair.
    Fungsi ini idempotent: relationship yang sudah memiliki child pair
    tidak akan diinsert ulang.
    """
    with engine.begin() as connection:
        relationship_rows = connection.execute(
            select(relationships_table)
        ).mappings().all()

        if not relationship_rows:
            return

        existing_ids = set(
            connection.execute(
                select(
                    relationship_columns_table.c.relationship_id
                ).distinct()
            ).scalars().all()
        )

        pending = [
            {
                "relationship_id": int(row["id"]),
                "source_column": row["source_column"],
                "target_column": row["target_column"],
                "ordinal": 1,
            }
            for row in relationship_rows
            if int(row["id"]) not in existing_ids
        ]

        if pending:
            connection.execute(
                relationship_columns_table.insert(),
                pending,
            )


def ensure_internal_tables():
    metadata.create_all(
        engine,
        tables=[
            schema_mapping_table,
            column_settings_table,
            relationships_table,
            relationship_columns_table,
            column_profiles_table,
            profile_jobs_table,
            table_state_table,
            relationship_candidates_table,
            relationship_candidate_jobs_table,
            relationship_candidate_scores_table,
            relationship_scoring_jobs_table,
            relationship_cardinality_estimates_table,
            relationship_cardinality_jobs_table,
            relationship_reviews_table,
            relationship_review_candidates_table,
        ],
    )
    _backfill_relationship_columns()


# =====================================================
# COLUMN PROFILING METADATA
# =====================================================

def lock_relationship_tables(connection, table_names):
    if connection.dialect.name == "postgresql":
        for table_name in sorted(set(table_names)):
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                               {"key": "relationship_evidence:" + table_name})


def _invalidate_analysis(connection, table_name, reason):
    candidate_ids = select(relationship_candidates_table.c.id).where(or_(
        relationship_candidates_table.c.source_table == table_name,
        relationship_candidates_table.c.target_table == table_name,
    ))
    for table in (relationship_candidate_scores_table, relationship_cardinality_estimates_table):
        connection.execute(table.update().where(table.c.candidate_id.in_(candidate_ids)).values(
            is_stale=True, stale_reason=reason, updated_at=func.now()))
    connection.execute(relationship_candidates_table.update().where(
        relationship_candidates_table.c.id.in_(candidate_ids)).values(
            is_stale=True, stale_reason=reason, updated_at=func.now()))


def _validate_analysis_write(connection, analysis):
    candidate = connection.execute(select(relationship_candidates_table).where(
        relationship_candidates_table.c.id == analysis["candidate_id"])).mappings().one_or_none()
    if candidate is None:
        raise ValueError("Candidate tidak ditemukan.")
    lock_relationship_tables(connection, [candidate["source_table"], candidate["target_table"]])
    candidate = dict(connection.execute(select(relationship_candidates_table).where(
        relationship_candidates_table.c.id == analysis["candidate_id"])).mappings().one())
    _validate_candidate_write(connection, candidate)
    if analysis["candidate_key"] != candidate["candidate_key"] or any(
        analysis[k] != candidate[k] for k in VERSION_FIELDS
    ):
        raise ValueError("Evidence berubah saat analisis. Jalankan analisis ulang.")
    lineage = analysis.get("rationale") if "rationale" in analysis else analysis.get("evidence")
    if (lineage or {}).get("candidate_signature") != candidate_signature(candidate):
        raise ValueError("Candidate evidence berubah saat analisis. Jalankan analisis ulang.")
    return candidate


def _validate_candidate_write(connection, candidate):
    tables = [candidate["source_table"], candidate["target_table"]]
    lock_relationship_tables(connection, tables)
    rows = connection.execute(select(column_profiles_table).where(
        or_(*[(column_profiles_table.c.table_name == candidate[side + "_table"]) &
              (column_profiles_table.c.column_name == candidate[side + "_column"])
              for side in ("source", "target")]))).mappings().all()
    profiles = {(r["table_name"], r["column_name"]): r for r in rows}
    versions = dict(connection.execute(select(table_state_table.c.table_name,
        table_state_table.c.data_version).where(table_state_table.c.table_name.in_(tables))).all())
    freshness = validate_freshness(candidate, profiles, versions, require_analysis=False)
    if not freshness["is_fresh"]:
        raise ValueError("Evidence sudah stale: " + ", ".join(freshness["reasons"]))


def _assert_no_relationship_duplicate(connection, source_table, target_table, pairs, exclude_id=None):
    lock_relationship_tables(connection, [source_table, target_table])
    rows = connection.execute(select(relationships_table).where(
        relationships_table.c.is_active.is_(True),
        or_((relationships_table.c.source_table == source_table) &
            (relationships_table.c.target_table == target_table),
            (relationships_table.c.source_table == target_table) &
            (relationships_table.c.target_table == source_table)),
    )).mappings().all()
    signature = _relationship_pair_signature(pairs)
    for row in rows:
        if row["id"] == exclude_id:
            continue
        existing = _relationship_pair_rows(row["id"], connection=connection) or [row]
        if row["source_table"] == source_table and row["target_table"] == target_table:
            match = _relationship_pair_signature(existing) == signature
        else:
            match = False
        if row["source_table"] == target_table and row["target_table"] == source_table:
            match = match or tuple(sorted((p["target_column"], p["source_column"]) for p in existing)) == signature
        if match:
            raise ValueError("Relationship untuk pasangan kolom tersebut sudah tersedia.")


def _serialize_profile_row(row):
    return {
        "id": int(row["id"]),
        "table_name": row["table_name"],
        "column_name": row["column_name"],
        "data_type": row["data_type"],
        "type_family": row["type_family"],
        "profile_version": int(row["profile_version"] or 1),
        "profile_mode": row["profile_mode"],
        "source_data_version": int(row["source_data_version"] or 1),
        "row_count_estimate": (
            int(row["row_count_estimate"])
            if row["row_count_estimate"] is not None
            else None
        ),
        "table_size_bytes": (
            int(row["table_size_bytes"])
            if row["table_size_bytes"] is not None
            else None
        ),
        "sample_row_count": int(row["sample_row_count"] or 0),
        "sample_non_null_count": int(
            row["sample_non_null_count"] or 0
        ),
        "sample_distinct_count": int(
            row["sample_distinct_count"] or 0
        ),
        "null_ratio": row["null_ratio"],
        "distinct_ratio": row["distinct_ratio"],
        "avg_length": row["avg_length"],
        "value_fingerprint": row["value_fingerprint"] or [],
        "fingerprint_version": row["fingerprint_version"],
        "is_stale": bool(row["is_stale"]),
        "stale_reason": row["stale_reason"],
        "last_profiled_at": row["last_profiled_at"],
    }


def _ensure_table_state_connection(connection, table_name: str):
    row = connection.execute(
        select(table_state_table).where(
            table_state_table.c.table_name == table_name
        )
    ).mappings().one_or_none()

    if row is None:
        connection.execute(
            table_state_table.insert().values(
                table_name=table_name,
                data_version=1,
            )
        )
        return 1

    return int(row["data_version"] or 1)


def _bump_table_data_version_connection(connection, table_name: str):
    current = _ensure_table_state_connection(connection, table_name)
    next_version = current + 1
    connection.execute(
        table_state_table.update()
        .where(table_state_table.c.table_name == table_name)
        .values(
            data_version=next_version,
            updated_at=func.now(),
        )
    )
    return next_version


def get_table_data_version(table_name: str):
    table_name = validate_table_name(table_name)
    ensure_internal_tables()

    with engine.begin() as connection:
        return _ensure_table_state_connection(
            connection,
            table_name,
        )


def get_table_column_profiles(table_name: str):
    table_name = validate_table_name(table_name)
    ensure_internal_tables()

    statement = (
        select(column_profiles_table)
        .where(column_profiles_table.c.table_name == table_name)
        .order_by(column_profiles_table.c.id)
    )

    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [_serialize_profile_row(row) for row in rows]


def mark_table_profile_stale(
    table_name: str,
    reason: str = "table_data_changed",
):
    table_name = validate_table_name(table_name)
    ensure_internal_tables()
    reason = str(reason or "table_data_changed").strip()[:255]

    with engine.begin() as connection:
        lock_relationship_tables(connection, [table_name])
        result = connection.execute(
            column_profiles_table.update()
            .where(column_profiles_table.c.table_name == table_name)
            .values(
                is_stale=True,
                stale_reason=reason,
            )
        )
        candidate_ids = select(
            relationship_candidates_table.c.id
        ).where(
            or_(
                relationship_candidates_table.c.source_table == table_name,
                relationship_candidates_table.c.target_table == table_name,
            )
        )
        connection.execute(
            relationship_candidates_table.update()
            .where(
                or_(
                    relationship_candidates_table.c.source_table == table_name,
                    relationship_candidates_table.c.target_table == table_name,
                )
            )
            .values(
                is_stale=True,
                stale_reason=reason,
                updated_at=func.now(),
            )
        )
        connection.execute(
            relationship_candidate_scores_table.update()
            .where(
                relationship_candidate_scores_table.c.candidate_id.in_(
                    candidate_ids
                )
            )
            .values(
                is_stale=True,
                stale_reason=reason,
                updated_at=func.now(),
            )
        )
        connection.execute(
            relationship_cardinality_estimates_table.update()
            .where(
                relationship_cardinality_estimates_table.c.candidate_id.in_(
                    candidate_ids
                )
            )
            .values(
                is_stale=True,
                stale_reason=reason,
                updated_at=func.now(),
            )
        )

    return int(result.rowcount or 0)


def _mark_table_profile_stale_best_effort(
    table_name: str,
    reason: str,
):
    try:
        mark_table_profile_stale(table_name, reason)
    except Exception as error:
        print(
            "WARNING profile stale marker:",
            table_name,
            repr(error),
        )


def upsert_column_profile(profile: dict):
    ensure_internal_tables()

    table_name = validate_table_name(profile["table_name"])
    column_name = validate_column_name(profile["column_name"])

    with engine.begin() as connection:
        lock_relationship_tables(connection, [table_name])
        current = connection.execute(
            select(column_profiles_table).where(
                column_profiles_table.c.table_name == table_name,
                column_profiles_table.c.column_name == column_name,
            )
        ).mappings().one_or_none()

        values = {
            "table_name": table_name,
            "column_name": column_name,
            "data_type": str(profile["data_type"])[:128],
            "type_family": str(profile["type_family"])[:32],
            "profile_mode": str(profile["profile_mode"])[:32],
            "source_data_version": int(
                profile.get("source_data_version") or 1
            ),
            "row_count_estimate": profile.get("row_count_estimate"),
            "table_size_bytes": profile.get("table_size_bytes"),
            "sample_row_count": int(profile.get("sample_row_count") or 0),
            "sample_non_null_count": int(
                profile.get("sample_non_null_count") or 0
            ),
            "sample_distinct_count": int(
                profile.get("sample_distinct_count") or 0
            ),
            "null_ratio": profile.get("null_ratio"),
            "distinct_ratio": profile.get("distinct_ratio"),
            "avg_length": profile.get("avg_length"),
            "value_fingerprint": profile.get("value_fingerprint") or [],
            "fingerprint_version": str(
                profile.get("fingerprint_version") or "sha256_min64_v1"
            )[:32],
            "is_stale": False,
            "stale_reason": None,
            "last_profiled_at": func.now(),
        }

        if current is None:
            values["profile_version"] = 1
            result = connection.execute(
                column_profiles_table.insert().values(**values)
            )
            profile_id = int(result.inserted_primary_key[0])
        else:
            profile_id = int(current["id"])
            values["profile_version"] = int(
                current["profile_version"] or 1
            ) + 1
            connection.execute(
                column_profiles_table.update()
                .where(column_profiles_table.c.id == profile_id)
                .values(**values)
            )

        _invalidate_analysis(connection, table_name, "profile_updated")
        row = connection.execute(
            select(column_profiles_table).where(
                column_profiles_table.c.id == profile_id
            )
        ).mappings().one()

    return _serialize_profile_row(row)


def _serialize_profile_job(row):
    return {
        "id": int(row["id"]),
        "table_name": row["table_name"],
        "status": row["status"],
        "requested_columns": row["requested_columns"],
        "target_sample_rows": int(row["target_sample_rows"] or 0),
        "profile_strategy": row["profile_strategy"],
        "source_data_version": (
            int(row["source_data_version"])
            if row["source_data_version"] is not None
            else None
        ),
        "total_columns": int(row["total_columns"] or 0),
        "processed_columns": int(row["processed_columns"] or 0),
        "progress_pct": (
            round(
                (float(row["processed_columns"] or 0)
                 / float(row["total_columns"])) * 100.0,
                1,
            )
            if int(row["total_columns"] or 0) > 0
            else 0.0
        ),
        "worker_backend": row["worker_backend"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "error_message": row["error_message"],
        "result_summary": row["result_summary"],
    }


def create_profile_job_record(
    *,
    table_name: str,
    requested_columns: list[str] | None,
    target_sample_rows: int,
    profile_strategy: str = "adaptive",
):
    table_name = validate_table_name(table_name)
    ensure_internal_tables()

    if not table_exists(table_name):
        raise ValueError(f"Tabel '{table_name}' tidak ditemukan.")

    columns = get_table_columns(table_name)
    requested = None

    if requested_columns:
        requested = []
        seen = set()
        for raw_column in requested_columns:
            column = validate_column_name(raw_column)
            if column not in columns:
                raise ValueError(
                    f"Kolom '{column}' tidak ditemukan pada tabel "
                    f"'{table_name}'."
                )
            if column not in seen:
                requested.append(column)
                seen.add(column)

    target_sample_rows = int(target_sample_rows)
    if target_sample_rows < 1000 or target_sample_rows > 250000:
        raise ValueError(
            "target_sample_rows harus berada pada rentang 1.000-250.000."
        )

    strategy = str(profile_strategy or "adaptive").strip().lower()
    if strategy not in {"adaptive", "sampled", "full"}:
        raise ValueError(
            "profile_strategy harus 'adaptive', 'sampled', atau 'full'."
        )

    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    "hashtext(:lock_key))"
                ),
                {"lock_key": f"profile:{table_name}"},
            )

        active = connection.execute(
            select(profile_jobs_table).where(
                profile_jobs_table.c.table_name == table_name,
                profile_jobs_table.c.status.in_(["queued", "running"]),
            ).order_by(profile_jobs_table.c.id.desc())
        ).mappings().first()

        if active is not None:
            return _serialize_profile_job(active), False

        result = connection.execute(
            profile_jobs_table.insert().values(
                table_name=table_name,
                status="queued",
                requested_columns=requested,
                target_sample_rows=target_sample_rows,
                profile_strategy=strategy,
                worker_backend="in_process_v1",
            )
        )
        job_id = int(result.inserted_primary_key[0])
        row = connection.execute(
            select(profile_jobs_table).where(
                profile_jobs_table.c.id == job_id
            )
        ).mappings().one()

    return _serialize_profile_job(row), True


def get_profile_job(job_id: int):
    ensure_internal_tables()
    job_id = int(job_id)

    with engine.connect() as connection:
        row = connection.execute(
            select(profile_jobs_table).where(
                profile_jobs_table.c.id == job_id
            )
        ).mappings().one_or_none()

    if row is None:
        raise ValueError("Profiling job tidak ditemukan.")

    return _serialize_profile_job(row)


def get_profile_jobs(
    table_name: str | None = None,
    limit: int = 50,
):
    ensure_internal_tables()
    limit = max(1, min(int(limit), 200))

    statement = select(profile_jobs_table)
    if table_name:
        table_name = validate_table_name(table_name)
        statement = statement.where(
            profile_jobs_table.c.table_name == table_name
        )

    statement = statement.order_by(
        profile_jobs_table.c.id.desc()
    ).limit(limit)

    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [_serialize_profile_job(row) for row in rows]


def update_profile_job_progress(
    job_id: int,
    *,
    processed_columns: int,
    total_columns: int,
    source_data_version: int | None = None,
):
    ensure_internal_tables()
    values = {
        "processed_columns": max(0, int(processed_columns)),
        "total_columns": max(0, int(total_columns)),
    }
    if source_data_version is not None:
        values["source_data_version"] = int(source_data_version)

    with engine.begin() as connection:
        result = connection.execute(
            profile_jobs_table.update()
            .where(profile_jobs_table.c.id == int(job_id))
            .values(**values)
        )
        if not result.rowcount:
            raise ValueError("Profiling job tidak ditemukan.")

    return get_profile_job(job_id)


def claim_profile_job(job_id: int):
    ensure_internal_tables()
    job_id = int(job_id)

    with engine.begin() as connection:
        result = connection.execute(
            profile_jobs_table.update()
            .where(
                profile_jobs_table.c.id == job_id,
                profile_jobs_table.c.status == "queued",
            )
            .values(
                status="running",
                started_at=func.now(),
                finished_at=None,
                error_message=None,
            )
        )

        if not result.rowcount:
            return None

        row = connection.execute(
            select(profile_jobs_table).where(
                profile_jobs_table.c.id == job_id
            )
        ).mappings().one()

    return _serialize_profile_job(row)


def update_profile_job_record(
    job_id: int,
    *,
    status: str,
    result_summary: dict | None = None,
    error_message: str | None = None,
):
    ensure_internal_tables()
    job_id = int(job_id)
    status = str(status).strip().lower()

    if status not in PROFILE_JOB_STATUSES:
        raise ValueError("Status profiling job tidak valid.")

    values = {"status": status}

    if status == "running":
        values.update(
            started_at=func.now(),
            finished_at=None,
            error_message=None,
        )
    elif status in {"completed", "failed"}:
        values["finished_at"] = func.now()

    if result_summary is not None:
        values["result_summary"] = result_summary

    if error_message is not None:
        values["error_message"] = str(error_message)[:8000]

    with engine.begin() as connection:
        result = connection.execute(
            profile_jobs_table.update()
            .where(profile_jobs_table.c.id == job_id)
            .values(**values)
        )
        if not result.rowcount:
            raise ValueError("Profiling job tidak ditemukan.")

    return get_profile_job(job_id)


def get_recoverable_profile_jobs():
    ensure_internal_tables()

    with engine.begin() as connection:
        connection.execute(
            profile_jobs_table.update()
            .where(profile_jobs_table.c.status == "running")
            .values(
                status="queued",
                started_at=None,
                finished_at=None,
                error_message=(
                    "Worker restart terdeteksi; job diantrikan kembali."
                ),
            )
        )

        rows = connection.execute(
            select(profile_jobs_table.c.id)
            .where(profile_jobs_table.c.status == "queued")
            .order_by(profile_jobs_table.c.id)
        ).scalars().all()

    return [int(job_id) for job_id in rows]



# =====================================================
# RELATIONSHIP INTELLIGENCE METADATA
# =====================================================

def get_column_profiles_for_tables(
    table_names: list[str] | None = None,
    *,
    include_stale: bool = False,
):
    """Read profiling metadata in one query.

    Relationship discovery must operate on metadata, not on warehouse rows.
    This function is intentionally bulk-oriented so candidate generation does
    not issue one SQL query per table when the warehouse grows.
    """
    ensure_internal_tables()

    normalized_tables = None
    if table_names:
        normalized_tables = []
        seen = set()
        for raw_table in table_names:
            table_name = validate_table_name(raw_table)
            if table_name not in seen:
                normalized_tables.append(table_name)
                seen.add(table_name)

    statement = select(column_profiles_table)

    if normalized_tables:
        statement = statement.where(
            column_profiles_table.c.table_name.in_(normalized_tables)
        )

    if not include_stale:
        statement = statement.where(
            column_profiles_table.c.is_stale.is_(False)
        )

    statement = statement.order_by(
        column_profiles_table.c.table_name,
        column_profiles_table.c.id,
    )

    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [_serialize_profile_row(row) for row in rows]


def get_profiled_table_names(*, include_stale: bool = False):
    ensure_internal_tables()

    statement = select(
        column_profiles_table.c.table_name
    ).distinct()

    if not include_stale:
        statement = statement.where(
            column_profiles_table.c.is_stale.is_(False)
        )

    statement = statement.order_by(column_profiles_table.c.table_name)

    with engine.connect() as connection:
        rows = connection.execute(statement).scalars().all()

    return list(rows)


def get_active_relationship_column_pairs():
    """Return active relationship pairs without expensive schema reflection."""
    ensure_internal_tables()

    statement = (
        select(
            relationships_table.c.source_table,
            relationship_columns_table.c.source_column,
            relationships_table.c.target_table,
            relationship_columns_table.c.target_column,
        )
        .join(
            relationship_columns_table,
            relationship_columns_table.c.relationship_id
            == relationships_table.c.id,
        )
        .where(relationships_table.c.is_active.is_(True))
    )

    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [dict(row) for row in rows]


def _serialize_relationship_candidate(row):
    if row is None:
        return None

    return {
        "id": int(row["id"]),
        "candidate_key": row["candidate_key"],
        "table_pair_key": row["table_pair_key"],
        "source_table": row["source_table"],
        "source_column": row["source_column"],
        "target_table": row["target_table"],
        "target_column": row["target_column"],
        "source_profile_version": int(row["source_profile_version"] or 1),
        "target_profile_version": int(row["target_profile_version"] or 1),
        "source_data_version": int(row["source_data_version"] or 1),
        "target_data_version": int(row["target_data_version"] or 1),
        "source_type_family": row["source_type_family"],
        "target_type_family": row["target_type_family"],
        "name_similarity": round(float(row["name_similarity"] or 0.0), 6),
        "fingerprint_overlap": round(
            float(row["fingerprint_overlap"] or 0.0), 6
        ),
        "discovery_score": round(float(row["discovery_score"] or 0.0), 6),
        "evidence": row["evidence"] or {},
        "detector_version": row["detector_version"],
        "status": row["status"],
        "is_stale": bool(row["is_stale"]),
        "stale_reason": row["stale_reason"],
        "last_seen_job_id": (
            int(row["last_seen_job_id"])
            if row["last_seen_job_id"] is not None
            else None
        ),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def upsert_relationship_candidate(candidate: dict):
    ensure_internal_tables()

    source_table = validate_table_name(candidate["source_table"])
    target_table = validate_table_name(candidate["target_table"])
    source_column = validate_column_name(candidate["source_column"])
    target_column = validate_column_name(candidate["target_column"])

    candidate_key = str(candidate["candidate_key"]).strip().lower()
    table_pair_key = str(candidate["table_pair_key"]).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", candidate_key):
        raise ValueError("candidate_key harus berupa SHA-256 hex.")
    if not re.fullmatch(r"[0-9a-f]{64}", table_pair_key):
        raise ValueError("table_pair_key harus berupa SHA-256 hex.")

    values = {
        "candidate_key": candidate_key,
        "table_pair_key": table_pair_key,
        "source_table": source_table,
        "source_column": source_column,
        "target_table": target_table,
        "target_column": target_column,
        "source_profile_version": int(candidate["source_profile_version"]),
        "target_profile_version": int(candidate["target_profile_version"]),
        "source_data_version": int(candidate["source_data_version"]),
        "target_data_version": int(candidate["target_data_version"]),
        "source_type_family": str(candidate["source_type_family"])[:32],
        "target_type_family": str(candidate["target_type_family"])[:32],
        "name_similarity": float(candidate.get("name_similarity") or 0.0),
        "fingerprint_overlap": float(
            candidate.get("fingerprint_overlap") or 0.0
        ),
        "discovery_score": float(candidate.get("discovery_score") or 0.0),
        "evidence": candidate.get("evidence") or {},
        "detector_version": str(candidate["detector_version"])[:48],
        "is_stale": False,
        "stale_reason": None,
        "last_seen_job_id": int(candidate["last_seen_job_id"]),
        "updated_at": func.now(),
    }

    with engine.begin() as connection:
        _validate_candidate_write(connection, values)
        current = connection.execute(
            select(relationship_candidates_table).where(
                relationship_candidates_table.c.candidate_key == candidate_key
            )
        ).mappings().one_or_none()

        if current is None:
            values["status"] = "pending"
            result = connection.execute(
                relationship_candidates_table.insert().values(**values)
            )
            candidate_id = int(result.inserted_primary_key[0])
        else:
            candidate_id = int(current["id"])
            # Human decisions are preserved when the detector sees the same
            # candidate again. 6B.2.5 will expose explicit reset/review flows.
            values["status"] = (
                current["status"]
                if current["status"] in {"rejected", "promoted"}
                else "pending"
            )
            if current["status"] == "rejected":
                rejected_signature = connection.execute(select(
                    relationship_review_candidates_table.c.material_signature).join(relationship_reviews_table,
                        relationship_reviews_table.c.id == relationship_review_candidates_table.c.review_id).where(
                            relationship_review_candidates_table.c.candidate_id == candidate_id,
                            relationship_reviews_table.c.decision == "rejected").order_by(
                                relationship_reviews_table.c.id.desc()).limit(1)).scalar_one_or_none()
                if (rejected_signature or material_signature(current)) != material_signature(values):
                    values["status"] = "pending"
            if any(current[k] != values[k] for k in VERSION_FIELDS) or any(
                current[k] != values[k] for k in ("source_table", "source_column", "target_table", "target_column", "evidence", "detector_version")
            ):
                for table in (relationship_candidate_scores_table, relationship_cardinality_estimates_table):
                    connection.execute(table.update().where(table.c.candidate_id == candidate_id).values(
                        is_stale=True, stale_reason="candidate_reanalysed", updated_at=func.now()))
            connection.execute(
                relationship_candidates_table.update()
                .where(relationship_candidates_table.c.id == candidate_id)
                .values(**values)
            )

        row = connection.execute(
            select(relationship_candidates_table).where(
                relationship_candidates_table.c.id == candidate_id
            )
        ).mappings().one()

    return _serialize_relationship_candidate(row)


def get_relationship_candidates(
    *,
    source_table: str | None = None,
    target_table: str | None = None,
    status: str | None = None,
    include_stale: bool = False,
    min_discovery_score: float = 0.0,
    limit: int = 200,
):
    ensure_internal_tables()
    limit = max(1, min(int(limit), 2000))
    min_discovery_score = max(0.0, min(float(min_discovery_score), 1.0))

    statement = select(relationship_candidates_table)

    if source_table:
        source_table = validate_table_name(source_table)
        statement = statement.where(
            relationship_candidates_table.c.source_table == source_table
        )
    if target_table:
        target_table = validate_table_name(target_table)
        statement = statement.where(
            relationship_candidates_table.c.target_table == target_table
        )
    if status:
        status = str(status).strip().lower()
        if status not in RELATIONSHIP_CANDIDATE_STATUSES:
            raise ValueError("Status relationship candidate tidak valid.")
        statement = statement.where(
            relationship_candidates_table.c.status == status
        )
    if not status:
        # Reviewed candidates remain available through explicit status filters/history.
        statement = statement.where(relationship_candidates_table.c.status.notin_(["rejected", "promoted"]))
    if not include_stale:
        statement = statement.where(
            relationship_candidates_table.c.is_stale.is_(False)
        )

    statement = (
        statement.where(
            relationship_candidates_table.c.discovery_score
            >= min_discovery_score
        )
        .order_by(
            relationship_candidates_table.c.discovery_score.desc(),
            relationship_candidates_table.c.id.desc(),
        )
        .limit(limit)
    )

    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [_serialize_relationship_candidate(row) for row in rows]


def mark_relationship_candidates_stale_for_table(
    table_name: str,
    reason: str = "table_profile_changed",
    *,
    connection=None,
):
    ensure_internal_tables()
    table_name = validate_table_name(table_name)
    reason = str(reason or "table_profile_changed").strip()[:255]

    def apply(conn):
        lock_relationship_tables(conn, [table_name])
        candidate_ids = select(relationship_candidates_table.c.id).where(
            or_(
                relationship_candidates_table.c.source_table == table_name,
                relationship_candidates_table.c.target_table == table_name,
            )
        )
        candidate_result = conn.execute(
            relationship_candidates_table.update()
            .where(
                or_(
                    relationship_candidates_table.c.source_table == table_name,
                    relationship_candidates_table.c.target_table == table_name,
                )
            )
            .values(is_stale=True, stale_reason=reason, updated_at=func.now())
        )
        conn.execute(
            relationship_candidate_scores_table.update()
            .where(
                relationship_candidate_scores_table.c.candidate_id.in_(
                    candidate_ids
                )
            )
            .values(
                is_stale=True,
                stale_reason=reason,
                updated_at=func.now(),
            )
        )
        conn.execute(
            relationship_cardinality_estimates_table.update()
            .where(
                relationship_cardinality_estimates_table.c.candidate_id.in_(
                    candidate_ids
                )
            )
            .values(
                is_stale=True,
                stale_reason=reason,
                updated_at=func.now(),
            )
        )
        return int(candidate_result.rowcount or 0)

    if connection is not None:
        return apply(connection)
    with engine.begin() as local_connection:
        return apply(local_connection)


def _serialize_relationship_candidate_job(row):
    if row is None:
        return None

    return {
        "id": int(row["id"]),
        "status": row["status"],
        "scan_mode": row["scan_mode"],
        "source_tables": row["source_tables"] or [],
        "target_tables": row["target_tables"] or [],
        "min_discovery_score": round(
            float(row["min_discovery_score"] or 0.0), 6
        ),
        "max_candidates": int(row["max_candidates"] or 0),
        "include_system_columns": bool(row["include_system_columns"]),
        "profile_columns_considered": int(
            row["profile_columns_considered"] or 0
        ),
        "pair_evaluations": int(row["pair_evaluations"] or 0),
        "generated_count": int(row["generated_count"] or 0),
        "skipped_existing_count": int(row["skipped_existing_count"] or 0),
        "truncated": bool(row["truncated"]),
        "worker_backend": row["worker_backend"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "error_message": row["error_message"],
        "result_summary": row["result_summary"],
    }


def _normalize_candidate_job_tables(table_names):
    if not table_names:
        return []

    warehouse_tables = set(get_all_tables())
    normalized = []
    seen = set()

    for raw_table in table_names:
        table_name = validate_table_name(raw_table)
        if table_name not in warehouse_tables:
            raise ValueError(f"Tabel '{table_name}' tidak ditemukan.")
        if table_name not in seen:
            normalized.append(table_name)
            seen.add(table_name)

    if len(normalized) > 500:
        raise ValueError("Satu candidate job maksimal mencakup 500 tabel per scope.")

    return normalized


def create_relationship_candidate_job_record(
    *,
    scan_mode: str,
    source_tables: list[str] | None,
    target_tables: list[str] | None,
    min_discovery_score: float,
    max_candidates: int,
    include_system_columns: bool = True,
):
    ensure_internal_tables()

    scan_mode = str(scan_mode or "selected").strip().lower()
    if scan_mode not in {"selected", "source_vs_all", "all_profiled"}:
        raise ValueError(
            "scan_mode harus 'selected', 'source_vs_all', atau 'all_profiled'."
        )

    sources = _normalize_candidate_job_tables(source_tables)
    targets = _normalize_candidate_job_tables(target_tables)

    if scan_mode == "selected" and (not sources or not targets):
        raise ValueError(
            "scan_mode='selected' membutuhkan source_tables dan target_tables."
        )
    if scan_mode == "source_vs_all" and not sources:
        raise ValueError(
            "scan_mode='source_vs_all' membutuhkan source_tables."
        )

    min_discovery_score = float(min_discovery_score)
    if min_discovery_score < 0.0 or min_discovery_score > 1.0:
        raise ValueError("min_discovery_score harus berada pada rentang 0-1.")

    max_candidates = int(max_candidates)
    if max_candidates < 1 or max_candidates > 10000:
        raise ValueError("max_candidates harus berada pada rentang 1-10.000.")

    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    "hashtext(:lock_key))"
                ),
                {"lock_key": "relationship_candidate_job_queue"},
            )

        active_rows = connection.execute(
            select(relationship_candidate_jobs_table).where(
                relationship_candidate_jobs_table.c.status.in_(
                    ["queued", "running"]
                )
            )
        ).mappings().all()

        for active in active_rows:
            same_scope = (
                active["scan_mode"] == scan_mode
                and (active["source_tables"] or []) == sources
                and (active["target_tables"] or []) == targets
                and abs(
                    float(active["min_discovery_score"])
                    - min_discovery_score
                ) < 1e-9
                and int(active["max_candidates"]) == max_candidates
                and bool(active["include_system_columns"])
                == bool(include_system_columns)
            )
            if same_scope:
                return _serialize_relationship_candidate_job(active), False

        result = connection.execute(
            relationship_candidate_jobs_table.insert().values(
                status="queued",
                scan_mode=scan_mode,
                source_tables=sources,
                target_tables=targets,
                min_discovery_score=min_discovery_score,
                max_candidates=max_candidates,
                include_system_columns=bool(include_system_columns),
                worker_backend="in_process_v1",
            )
        )
        job_id = int(result.inserted_primary_key[0])
        row = connection.execute(
            select(relationship_candidate_jobs_table).where(
                relationship_candidate_jobs_table.c.id == job_id
            )
        ).mappings().one()

    return _serialize_relationship_candidate_job(row), True


def get_relationship_candidate_job(job_id: int):
    ensure_internal_tables()
    job_id = int(job_id)

    with engine.connect() as connection:
        row = connection.execute(
            select(relationship_candidate_jobs_table).where(
                relationship_candidate_jobs_table.c.id == job_id
            )
        ).mappings().one_or_none()

    if row is None:
        raise ValueError("Relationship candidate job tidak ditemukan.")

    return _serialize_relationship_candidate_job(row)


def get_relationship_candidate_jobs(*, limit: int = 50):
    ensure_internal_tables()
    limit = max(1, min(int(limit), 200))

    statement = (
        select(relationship_candidate_jobs_table)
        .order_by(relationship_candidate_jobs_table.c.id.desc())
        .limit(limit)
    )

    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [_serialize_relationship_candidate_job(row) for row in rows]


def claim_relationship_candidate_job(job_id: int):
    ensure_internal_tables()
    job_id = int(job_id)

    with engine.begin() as connection:
        result = connection.execute(
            relationship_candidate_jobs_table.update()
            .where(
                relationship_candidate_jobs_table.c.id == job_id,
                relationship_candidate_jobs_table.c.status == "queued",
            )
            .values(
                status="running",
                started_at=func.now(),
                finished_at=None,
                error_message=None,
            )
        )
        if not result.rowcount:
            return None

        row = connection.execute(
            select(relationship_candidate_jobs_table).where(
                relationship_candidate_jobs_table.c.id == job_id
            )
        ).mappings().one()

    return _serialize_relationship_candidate_job(row)


def update_relationship_candidate_job(
    job_id: int,
    *,
    status: str | None = None,
    profile_columns_considered: int | None = None,
    pair_evaluations: int | None = None,
    generated_count: int | None = None,
    skipped_existing_count: int | None = None,
    truncated: bool | None = None,
    result_summary: dict | None = None,
    error_message: str | None = None,
):
    ensure_internal_tables()
    job_id = int(job_id)
    values = {}

    if status is not None:
        status = str(status).strip().lower()
        if status not in RELATIONSHIP_CANDIDATE_JOB_STATUSES:
            raise ValueError("Status relationship candidate job tidak valid.")
        values["status"] = status
        if status == "running":
            values.update(
                started_at=func.now(),
                finished_at=None,
                error_message=None,
            )
        elif status in {"completed", "failed"}:
            values["finished_at"] = func.now()

    integer_fields = {
        "profile_columns_considered": profile_columns_considered,
        "pair_evaluations": pair_evaluations,
        "generated_count": generated_count,
        "skipped_existing_count": skipped_existing_count,
    }
    for field, value in integer_fields.items():
        if value is not None:
            values[field] = max(0, int(value))

    if truncated is not None:
        values["truncated"] = bool(truncated)
    if result_summary is not None:
        values["result_summary"] = result_summary
    if error_message is not None:
        values["error_message"] = str(error_message)[:8000]

    if not values:
        return get_relationship_candidate_job(job_id)

    with engine.begin() as connection:
        result = connection.execute(
            relationship_candidate_jobs_table.update()
            .where(relationship_candidate_jobs_table.c.id == job_id)
            .values(**values)
        )
        if not result.rowcount:
            raise ValueError("Relationship candidate job tidak ditemukan.")

    return get_relationship_candidate_job(job_id)


def get_recoverable_relationship_candidate_jobs():
    ensure_internal_tables()

    with engine.begin() as connection:
        connection.execute(
            relationship_candidate_jobs_table.update()
            .where(relationship_candidate_jobs_table.c.status == "running")
            .values(
                status="queued",
                started_at=None,
                finished_at=None,
                error_message=(
                    "Worker restart terdeteksi; job diantrikan kembali."
                ),
            )
        )

        rows = connection.execute(
            select(relationship_candidate_jobs_table.c.id)
            .where(relationship_candidate_jobs_table.c.status == "queued")
            .order_by(relationship_candidate_jobs_table.c.id)
        ).scalars().all()

    return [int(job_id) for job_id in rows]


# =====================================================
# RELATIONSHIP QUALITY SCORING METADATA
# =====================================================

def _serialize_relationship_candidate_score(row):
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "candidate_id": int(row["candidate_id"]),
        "candidate_key": row["candidate_key"],
        "scoring_version": row["scoring_version"],
        "source_profile_version": int(row["source_profile_version"]),
        "target_profile_version": int(row["target_profile_version"]),
        "source_data_version": int(row["source_data_version"]),
        "target_data_version": int(row["target_data_version"]),
        "semantic_score": round(float(row["semantic_score"] or 0), 6),
        "datatype_score": round(float(row["datatype_score"] or 0), 6),
        "fingerprint_score": (round(float(row["fingerprint_score"]), 6) if row["fingerprint_score"] is not None else None),
        "profile_quality_score": round(float(row["profile_quality_score"] or 0), 6),
        "key_plausibility_score": round(float(row["key_plausibility_score"] or 0), 6),
        "evidence_sufficiency_score": round(float(row["evidence_sufficiency_score"] or 0), 6),
        "penalty_score": round(float(row["penalty_score"] or 0), 6),
        "confidence_score": round(float(row["confidence_score"] or 0), 6),
        "confidence_level": row["confidence_level"],
        "component_scores": row["component_scores"] or {},
        "quality_flags": row["quality_flags"] or [],
        "rationale": row["rationale"] or {},
        "is_stale": bool(row["is_stale"]),
        "stale_reason": row["stale_reason"],
        "last_scored_job_id": int(row["last_scored_job_id"]) if row["last_scored_job_id"] is not None else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def upsert_relationship_candidate_score(score: dict):
    ensure_internal_tables()
    candidate_id = int(score["candidate_id"])
    values = {
        "candidate_id": candidate_id,
        "candidate_key": str(score["candidate_key"]),
        "scoring_version": str(score["scoring_version"])[:48],
        "source_profile_version": int(score["source_profile_version"]),
        "target_profile_version": int(score["target_profile_version"]),
        "source_data_version": int(score["source_data_version"]),
        "target_data_version": int(score["target_data_version"]),
        "semantic_score": float(score["semantic_score"]),
        "datatype_score": float(score["datatype_score"]),
        "fingerprint_score": score.get("fingerprint_score"),
        "profile_quality_score": float(score["profile_quality_score"]),
        "key_plausibility_score": float(score["key_plausibility_score"]),
        "evidence_sufficiency_score": float(score["evidence_sufficiency_score"]),
        "penalty_score": float(score.get("penalty_score") or 0),
        "confidence_score": float(score["confidence_score"]),
        "confidence_level": str(score["confidence_level"])[:24],
        "component_scores": score.get("component_scores") or {},
        "quality_flags": score.get("quality_flags") or [],
        "rationale": score.get("rationale") or {},
        "is_stale": False,
        "stale_reason": None,
        "last_scored_job_id": int(score["last_scored_job_id"]),
        "updated_at": func.now(),
    }
    with engine.begin() as connection:
        _validate_analysis_write(connection, score)
        connection.execute(relationship_cardinality_estimates_table.update().where(
            relationship_cardinality_estimates_table.c.candidate_id == candidate_id).values(
                is_stale=True, stale_reason="quality_rescored", updated_at=func.now()))
        current = connection.execute(select(relationship_candidate_scores_table).where(relationship_candidate_scores_table.c.candidate_id == candidate_id)).mappings().one_or_none()
        if current is None:
            result = connection.execute(relationship_candidate_scores_table.insert().values(**values))
            score_id = int(result.inserted_primary_key[0])
        else:
            score_id = int(current["id"])
            connection.execute(relationship_candidate_scores_table.update().where(relationship_candidate_scores_table.c.id == score_id).values(**values))
        row = connection.execute(select(relationship_candidate_scores_table).where(relationship_candidate_scores_table.c.id == score_id)).mappings().one()
    return _serialize_relationship_candidate_score(row)


def get_relationship_candidate_scores(candidate_ids):
    ensure_internal_tables()
    ids = sorted({int(v) for v in (candidate_ids or [])})
    if not ids:
        return {}
    with engine.connect() as connection:
        rows = connection.execute(select(relationship_candidate_scores_table).where(relationship_candidate_scores_table.c.candidate_id.in_(ids))).mappings().all()
    return {int(row["candidate_id"]): _serialize_relationship_candidate_score(row) for row in rows}


def get_relationship_candidates_for_scoring(*, source_tables=None, target_tables=None, status="pending", min_discovery_score=0.45, max_candidates=5000):
    ensure_internal_tables()
    max_candidates = max(1, min(int(max_candidates), 10000))
    statement = select(relationship_candidates_table).where(
        relationship_candidates_table.c.is_stale.is_(False),
        relationship_candidates_table.c.discovery_score >= max(0.0, min(float(min_discovery_score), 1.0)),
    )
    if status:
        status = str(status).strip().lower()
        if status not in RELATIONSHIP_CANDIDATE_STATUSES:
            raise ValueError("Status relationship candidate tidak valid.")
        statement = statement.where(relationship_candidates_table.c.status == status)
    if source_tables:
        source_tables = _normalize_candidate_job_tables(source_tables)
        statement = statement.where(relationship_candidates_table.c.source_table.in_(source_tables))
    if target_tables:
        target_tables = _normalize_candidate_job_tables(target_tables)
        statement = statement.where(relationship_candidates_table.c.target_table.in_(target_tables))
    statement = statement.order_by(relationship_candidates_table.c.discovery_score.desc(), relationship_candidates_table.c.id.desc()).limit(max_candidates)
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return [_serialize_relationship_candidate(row) for row in rows]


def _serialize_relationship_scoring_job(row):
    if row is None:
        return None
    return {
        "id": int(row["id"]), "status": row["status"],
        "source_tables": row["source_tables"] or [], "target_tables": row["target_tables"] or [],
        "candidate_status": row["candidate_status"],
        "min_discovery_score": round(float(row["min_discovery_score"] or 0), 6),
        "max_candidates": int(row["max_candidates"] or 0),
        "candidate_count": int(row["candidate_count"] or 0), "scored_count": int(row["scored_count"] or 0),
        "skipped_count": int(row["skipped_count"] or 0), "worker_backend": row["worker_backend"],
        "created_at": row["created_at"], "started_at": row["started_at"], "finished_at": row["finished_at"],
        "error_message": row["error_message"], "result_summary": row["result_summary"],
    }


def create_relationship_scoring_job_record(*, source_tables=None, target_tables=None, candidate_status="pending", min_discovery_score=0.45, max_candidates=5000):
    ensure_internal_tables()
    sources = _normalize_candidate_job_tables(source_tables)
    targets = _normalize_candidate_job_tables(target_tables)
    candidate_status = str(candidate_status or "pending").strip().lower()
    if candidate_status not in RELATIONSHIP_CANDIDATE_STATUSES:
        raise ValueError("candidate_status tidak valid.")
    min_discovery_score = max(0.0, min(float(min_discovery_score), 1.0))
    max_candidates = int(max_candidates)
    if max_candidates < 1 or max_candidates > 10000:
        raise ValueError("max_candidates harus 1-10.000.")
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": "relationship_scoring_job_queue"})
        active = connection.execute(select(relationship_scoring_jobs_table).where(relationship_scoring_jobs_table.c.status.in_(["queued", "running"]))).mappings().all()
        for row in active:
            if (row["source_tables"] or []) == sources and (row["target_tables"] or []) == targets and row["candidate_status"] == candidate_status and abs(float(row["min_discovery_score"])-min_discovery_score) < 1e-9 and int(row["max_candidates"]) == max_candidates:
                return _serialize_relationship_scoring_job(row), False
        result = connection.execute(relationship_scoring_jobs_table.insert().values(status="queued", source_tables=sources, target_tables=targets, candidate_status=candidate_status, min_discovery_score=min_discovery_score, max_candidates=max_candidates, worker_backend="in_process_v1"))
        job_id = int(result.inserted_primary_key[0])
        row = connection.execute(select(relationship_scoring_jobs_table).where(relationship_scoring_jobs_table.c.id == job_id)).mappings().one()
    return _serialize_relationship_scoring_job(row), True


def get_relationship_scoring_job(job_id: int):
    ensure_internal_tables()
    with engine.connect() as connection:
        row = connection.execute(select(relationship_scoring_jobs_table).where(relationship_scoring_jobs_table.c.id == int(job_id))).mappings().one_or_none()
    if row is None: raise ValueError("Relationship scoring job tidak ditemukan.")
    return _serialize_relationship_scoring_job(row)


def get_relationship_scoring_jobs(*, limit=50):
    ensure_internal_tables(); limit=max(1,min(int(limit),200))
    with engine.connect() as connection:
        rows=connection.execute(select(relationship_scoring_jobs_table).order_by(relationship_scoring_jobs_table.c.id.desc()).limit(limit)).mappings().all()
    return [_serialize_relationship_scoring_job(r) for r in rows]


def claim_relationship_scoring_job(job_id: int):
    ensure_internal_tables(); job_id=int(job_id)
    with engine.begin() as connection:
        result=connection.execute(relationship_scoring_jobs_table.update().where(relationship_scoring_jobs_table.c.id==job_id, relationship_scoring_jobs_table.c.status=="queued").values(status="running", started_at=func.now(), finished_at=None, error_message=None))
        if not result.rowcount: return None
        row=connection.execute(select(relationship_scoring_jobs_table).where(relationship_scoring_jobs_table.c.id==job_id)).mappings().one()
    return _serialize_relationship_scoring_job(row)


def update_relationship_scoring_job(job_id: int, *, status=None, candidate_count=None, scored_count=None, skipped_count=None, result_summary=None, error_message=None):
    ensure_internal_tables(); values={}
    if status is not None:
        status=str(status).strip().lower()
        if status not in RELATIONSHIP_SCORING_JOB_STATUSES: raise ValueError("Status relationship scoring job tidak valid.")
        values["status"]=status
        if status=="running": values.update(started_at=func.now(), finished_at=None, error_message=None)
        elif status in {"completed","failed"}: values["finished_at"]=func.now()
    for field,value in {"candidate_count":candidate_count,"scored_count":scored_count,"skipped_count":skipped_count}.items():
        if value is not None: values[field]=max(0,int(value))
    if result_summary is not None: values["result_summary"]=result_summary
    if error_message is not None: values["error_message"]=str(error_message)[:8000]
    if not values: return get_relationship_scoring_job(job_id)
    with engine.begin() as connection:
        result=connection.execute(relationship_scoring_jobs_table.update().where(relationship_scoring_jobs_table.c.id==int(job_id)).values(**values))
        if not result.rowcount: raise ValueError("Relationship scoring job tidak ditemukan.")
    return get_relationship_scoring_job(job_id)


def get_recoverable_relationship_scoring_jobs():
    ensure_internal_tables()
    with engine.begin() as connection:
        connection.execute(relationship_scoring_jobs_table.update().where(relationship_scoring_jobs_table.c.status=="running").values(status="queued", started_at=None, finished_at=None, error_message="Worker restart terdeteksi; scoring job diantrikan kembali."))
        rows=connection.execute(select(relationship_scoring_jobs_table.c.id).where(relationship_scoring_jobs_table.c.status=="queued").order_by(relationship_scoring_jobs_table.c.id)).scalars().all()
    return [int(v) for v in rows]


# =====================================================
# RELATIONSHIP CARDINALITY ESTIMATION METADATA
# =====================================================

def _serialize_relationship_cardinality_estimate(row):
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "candidate_id": int(row["candidate_id"]),
        "candidate_key": row["candidate_key"],
        "estimation_version": row["estimation_version"],
        "source_profile_version": int(row["source_profile_version"]),
        "target_profile_version": int(row["target_profile_version"]),
        "source_data_version": int(row["source_data_version"]),
        "target_data_version": int(row["target_data_version"]),
        "source_role": row["source_role"],
        "target_role": row["target_role"],
        "source_role_confidence": round(
            float(row["source_role_confidence"] or 0.0), 6
        ),
        "target_role_confidence": round(
            float(row["target_role_confidence"] or 0.0), 6
        ),
        "estimated_cardinality": row["estimated_cardinality"],
        "cardinality_confidence": round(
            float(row["cardinality_confidence"] or 0.0), 6
        ),
        "evidence": row["evidence"] or {},
        "quality_flags": row["quality_flags"] or [],
        "requires_review": bool(row["requires_review"]),
        "is_stale": bool(row["is_stale"]),
        "stale_reason": row["stale_reason"],
        "last_estimated_job_id": (
            int(row["last_estimated_job_id"])
            if row["last_estimated_job_id"] is not None
            else None
        ),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def upsert_relationship_cardinality_estimate(estimate: dict):
    ensure_internal_tables()
    candidate_id = int(estimate["candidate_id"])
    cardinality = str(estimate["estimated_cardinality"]).strip().lower()
    if cardinality not in RELATIONSHIP_CARDINALITIES:
        raise ValueError("Estimasi cardinality tidak valid.")

    source_role = str(estimate["source_role"]).strip().lower()
    target_role = str(estimate["target_role"]).strip().lower()
    if source_role not in {"one", "many"} or target_role not in {"one", "many"}:
        raise ValueError("Role cardinality harus 'one' atau 'many'.")

    values = {
        "candidate_id": candidate_id,
        "candidate_key": str(estimate["candidate_key"]),
        "estimation_version": str(estimate["estimation_version"])[:48],
        "source_profile_version": int(estimate["source_profile_version"]),
        "target_profile_version": int(estimate["target_profile_version"]),
        "source_data_version": int(estimate["source_data_version"]),
        "target_data_version": int(estimate["target_data_version"]),
        "source_role": source_role,
        "target_role": target_role,
        "source_role_confidence": max(
            0.0, min(float(estimate["source_role_confidence"]), 1.0)
        ),
        "target_role_confidence": max(
            0.0, min(float(estimate["target_role_confidence"]), 1.0)
        ),
        "estimated_cardinality": cardinality,
        "cardinality_confidence": max(
            0.0, min(float(estimate["cardinality_confidence"]), 1.0)
        ),
        "evidence": estimate.get("evidence") or {},
        "quality_flags": estimate.get("quality_flags") or [],
        "requires_review": bool(estimate.get("requires_review", True)),
        "is_stale": False,
        "stale_reason": None,
        "last_estimated_job_id": int(estimate["last_estimated_job_id"]),
        "updated_at": func.now(),
    }

    with engine.begin() as connection:
        _validate_analysis_write(connection, estimate)
        score_row = connection.execute(select(relationship_candidate_scores_table).where(
            relationship_candidate_scores_table.c.candidate_id == candidate_id)).mappings().one_or_none()
        current_score = _serialize_relationship_candidate_score(score_row)
        if (estimate.get("evidence") or {}).get("quality_score_signature") != quality_signature(current_score):
            raise ValueError("Quality score berubah saat estimasi. Jalankan cardinality ulang.")
        current = connection.execute(
            select(relationship_cardinality_estimates_table).where(
                relationship_cardinality_estimates_table.c.candidate_id
                == candidate_id
            )
        ).mappings().one_or_none()

        if current is None:
            result = connection.execute(
                relationship_cardinality_estimates_table.insert().values(
                    **values
                )
            )
            estimate_id = int(result.inserted_primary_key[0])
        else:
            estimate_id = int(current["id"])
            connection.execute(
                relationship_cardinality_estimates_table.update()
                .where(
                    relationship_cardinality_estimates_table.c.id
                    == estimate_id
                )
                .values(**values)
            )

        row = connection.execute(
            select(relationship_cardinality_estimates_table).where(
                relationship_cardinality_estimates_table.c.id == estimate_id
            )
        ).mappings().one()

    return _serialize_relationship_cardinality_estimate(row)


def get_relationship_cardinality_estimates(candidate_ids):
    ensure_internal_tables()
    ids = sorted({int(value) for value in (candidate_ids or [])})
    if not ids:
        return {}

    with engine.connect() as connection:
        rows = connection.execute(
            select(relationship_cardinality_estimates_table).where(
                relationship_cardinality_estimates_table.c.candidate_id.in_(
                    ids
                )
            )
        ).mappings().all()

    return {
        int(row["candidate_id"]): _serialize_relationship_cardinality_estimate(
            row
        )
        for row in rows
    }


def _serialize_relationship_cardinality_job(row):
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "status": row["status"],
        "source_tables": row["source_tables"] or [],
        "target_tables": row["target_tables"] or [],
        "candidate_status": row["candidate_status"],
        "min_discovery_score": round(
            float(row["min_discovery_score"] or 0.0), 6
        ),
        "min_quality_score": round(
            float(row["min_quality_score"] or 0.0), 6
        ),
        "max_candidates": int(row["max_candidates"] or 0),
        "candidate_count": int(row["candidate_count"] or 0),
        "estimated_count": int(row["estimated_count"] or 0),
        "skipped_count": int(row["skipped_count"] or 0),
        "worker_backend": row["worker_backend"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "error_message": row["error_message"],
        "result_summary": row["result_summary"],
    }


def create_relationship_cardinality_job_record(
    *,
    source_tables=None,
    target_tables=None,
    candidate_status="pending",
    min_discovery_score=0.45,
    min_quality_score=0.0,
    max_candidates=5000,
):
    ensure_internal_tables()
    sources = _normalize_candidate_job_tables(source_tables)
    targets = _normalize_candidate_job_tables(target_tables)

    candidate_status = str(candidate_status or "pending").strip().lower()
    if candidate_status not in RELATIONSHIP_CANDIDATE_STATUSES:
        raise ValueError("candidate_status tidak valid.")

    min_discovery_score = max(
        0.0, min(float(min_discovery_score), 1.0)
    )
    min_quality_score = max(0.0, min(float(min_quality_score), 1.0))
    max_candidates = int(max_candidates)
    if max_candidates < 1 or max_candidates > 10000:
        raise ValueError("max_candidates harus 1-10.000.")

    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtext(:lock_key))"
                ),
                {"lock_key": "relationship_cardinality_job_queue"},
            )

        active = connection.execute(
            select(relationship_cardinality_jobs_table).where(
                relationship_cardinality_jobs_table.c.status.in_(
                    ["queued", "running"]
                )
            )
        ).mappings().all()

        for row in active:
            same_scope = (
                (row["source_tables"] or []) == sources
                and (row["target_tables"] or []) == targets
                and row["candidate_status"] == candidate_status
                and abs(
                    float(row["min_discovery_score"])
                    - min_discovery_score
                )
                < 1e-9
                and abs(
                    float(row["min_quality_score"])
                    - min_quality_score
                )
                < 1e-9
                and int(row["max_candidates"]) == max_candidates
            )
            if same_scope:
                return _serialize_relationship_cardinality_job(row), False

        result = connection.execute(
            relationship_cardinality_jobs_table.insert().values(
                status="queued",
                source_tables=sources,
                target_tables=targets,
                candidate_status=candidate_status,
                min_discovery_score=min_discovery_score,
                min_quality_score=min_quality_score,
                max_candidates=max_candidates,
                worker_backend="in_process_v1",
            )
        )
        job_id = int(result.inserted_primary_key[0])
        row = connection.execute(
            select(relationship_cardinality_jobs_table).where(
                relationship_cardinality_jobs_table.c.id == job_id
            )
        ).mappings().one()

    return _serialize_relationship_cardinality_job(row), True


def get_relationship_cardinality_job(job_id: int):
    ensure_internal_tables()
    with engine.connect() as connection:
        row = connection.execute(
            select(relationship_cardinality_jobs_table).where(
                relationship_cardinality_jobs_table.c.id == int(job_id)
            )
        ).mappings().one_or_none()
    if row is None:
        raise ValueError("Relationship cardinality job tidak ditemukan.")
    return _serialize_relationship_cardinality_job(row)


def get_relationship_cardinality_jobs(*, limit=50):
    ensure_internal_tables()
    limit = max(1, min(int(limit), 200))
    with engine.connect() as connection:
        rows = connection.execute(
            select(relationship_cardinality_jobs_table)
            .order_by(relationship_cardinality_jobs_table.c.id.desc())
            .limit(limit)
        ).mappings().all()
    return [_serialize_relationship_cardinality_job(row) for row in rows]


def claim_relationship_cardinality_job(job_id: int):
    ensure_internal_tables()
    job_id = int(job_id)
    with engine.begin() as connection:
        result = connection.execute(
            relationship_cardinality_jobs_table.update()
            .where(
                relationship_cardinality_jobs_table.c.id == job_id,
                relationship_cardinality_jobs_table.c.status == "queued",
            )
            .values(
                status="running",
                started_at=func.now(),
                finished_at=None,
                error_message=None,
            )
        )
        if not result.rowcount:
            return None
        row = connection.execute(
            select(relationship_cardinality_jobs_table).where(
                relationship_cardinality_jobs_table.c.id == job_id
            )
        ).mappings().one()
    return _serialize_relationship_cardinality_job(row)


def update_relationship_cardinality_job(
    job_id: int,
    *,
    status=None,
    candidate_count=None,
    estimated_count=None,
    skipped_count=None,
    result_summary=None,
    error_message=None,
):
    ensure_internal_tables()
    values = {}

    if status is not None:
        status = str(status).strip().lower()
        if status not in RELATIONSHIP_CARDINALITY_JOB_STATUSES:
            raise ValueError("Status relationship cardinality job tidak valid.")
        values["status"] = status
        if status == "running":
            values.update(
                started_at=func.now(),
                finished_at=None,
                error_message=None,
            )
        elif status in {"completed", "failed"}:
            values["finished_at"] = func.now()

    for field, value in {
        "candidate_count": candidate_count,
        "estimated_count": estimated_count,
        "skipped_count": skipped_count,
    }.items():
        if value is not None:
            values[field] = max(0, int(value))

    if result_summary is not None:
        values["result_summary"] = result_summary
    if error_message is not None:
        values["error_message"] = str(error_message)[:8000]

    if not values:
        return get_relationship_cardinality_job(job_id)

    with engine.begin() as connection:
        result = connection.execute(
            relationship_cardinality_jobs_table.update()
            .where(
                relationship_cardinality_jobs_table.c.id == int(job_id)
            )
            .values(**values)
        )
        if not result.rowcount:
            raise ValueError("Relationship cardinality job tidak ditemukan.")

    return get_relationship_cardinality_job(job_id)


def get_recoverable_relationship_cardinality_jobs():
    ensure_internal_tables()
    with engine.begin() as connection:
        connection.execute(
            relationship_cardinality_jobs_table.update()
            .where(relationship_cardinality_jobs_table.c.status == "running")
            .values(
                status="queued",
                started_at=None,
                finished_at=None,
                error_message=(
                    "Worker restart terdeteksi; cardinality job "
                    "diantrikan kembali."
                ),
            )
        )
        rows = connection.execute(
            select(relationship_cardinality_jobs_table.c.id)
            .where(relationship_cardinality_jobs_table.c.status == "queued")
            .order_by(relationship_cardinality_jobs_table.c.id)
        ).scalars().all()
    return [int(value) for value in rows]


# =====================================================
# VALIDATION
# =====================================================

def validate_table_name(table_name: str) -> str:
    table_name = str(table_name).strip()

    if not table_name:
        raise ValueError("Nama tabel tidak boleh kosong.")

    if len(table_name) > 63:
        raise ValueError("Nama tabel maksimal 63 karakter.")

    if not re.fullmatch(r"[A-Za-z0-9_]+", table_name):
        raise ValueError(
            "Nama tabel hanya boleh mengandung huruf, angka, dan underscore."
        )

    if table_name in INTERNAL_TABLES:
        raise ValueError(
            f"Nama tabel '{table_name}' dicadangkan untuk metadata sistem."
        )

    return table_name


def validate_column_name(column_name: str) -> str:
    column_name = str(column_name).strip()

    if not column_name:
        raise ValueError("Nama kolom tidak boleh kosong.")

    if len(column_name) > 63:
        raise ValueError(
            f"Nama kolom '{column_name}' melebihi 63 karakter."
        )

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", column_name):
        raise ValueError(
            f"Nama kolom '{column_name}' tidak valid. "
            "Gunakan huruf, angka, dan underscore."
        )

    return column_name


def validate_dataframe_columns(df: pd.DataFrame):
    columns = [str(column) for column in df.columns]

    duplicates = [
        column
        for column in set(columns)
        if columns.count(column) > 1
    ]

    if duplicates:
        raise ValueError(
            "Terdapat nama kolom duplikat: "
            + ", ".join(sorted(duplicates))
        )

    for column in columns:
        validate_column_name(column)


# =====================================================
# TABLE INFORMATION
# =====================================================

def table_exists(table_name: str) -> bool:
    table_name = validate_table_name(table_name)
    inspector = inspect(engine)
    return inspector.has_table(table_name)


def get_table_columns(table_name: str):
    table_name = validate_table_name(table_name)
    inspector = inspect(engine)

    if not inspector.has_table(table_name):
        raise ValueError(
            f"Tabel '{table_name}' tidak ditemukan."
        )

    columns = inspector.get_columns(table_name)

    return [
        column["name"]
        for column in columns
    ]


def get_all_tables():
    ensure_internal_tables()

    inspector = inspect(engine)

    return sorted(
        table_name
        for table_name in inspector.get_table_names()
        if table_name not in INTERNAL_TABLES
    )


def _get_reflected_table(table_name: str):
    table_name = validate_table_name(table_name)

    if not table_exists(table_name):
        raise ValueError(
            f"Tabel '{table_name}' tidak ditemukan."
        )

    reflected_metadata = MetaData()

    return Table(
        table_name,
        reflected_metadata,
        autoload_with=engine,
    )


# =====================================================
# PERSISTENT SOURCE → DATABASE SCHEMA MAPPING
# =====================================================

def get_schema_mapping(table_name: str):
    table_name = validate_table_name(table_name)
    ensure_internal_tables()

    statement = (
        select(
            schema_mapping_table.c.source_ordinal,
            schema_mapping_table.c.source_column,
            schema_mapping_table.c.database_column,
        )
        .where(
            schema_mapping_table.c.table_name == table_name
        )
        .order_by(
            schema_mapping_table.c.source_ordinal
        )
    )

    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [
        {
            "source_ordinal": int(row["source_ordinal"]),
            "source_column": row["source_column"],
            "database_column": row["database_column"],
        }
        for row in rows
    ]


def require_schema_mapping(table_name: str):
    mapping = get_schema_mapping(table_name)

    if mapping:
        return mapping

    # Auto-bootstrap untuk tabel yang dibuat sebelum fitur schema mapping.
    # Karena existing upload menggunakan ordinal kolom, schema database
    # yang sudah ada dapat dijadikan baseline tanpa perlu rename ulang.
    database_columns = get_table_columns(table_name)

    business_columns = [
        column
        for column in database_columns
        if column not in SYSTEM_COLUMNS
    ]

    if not business_columns:
        raise ValueError(
            f"Tabel '{table_name}' tidak memiliki kolom bisnis "
            "yang dapat digunakan sebagai schema existing."
        )

    bootstrap_mapping = [
        {
            "source_ordinal": ordinal,
            "source_column": column,
            "database_column": column,
        }
        for ordinal, column in enumerate(
            business_columns,
            start=1,
        )
    ]

    ensure_internal_tables()

    with engine.begin() as connection:
        _insert_schema_mapping(
            connection=connection,
            table_name=table_name,
            schema_mapping=bootstrap_mapping,
        )

    return bootstrap_mapping


def get_expected_source_columns(table_name: str):
    return [
        item["database_column"]
        for item in require_schema_mapping(table_name)
    ]


def _insert_schema_mapping(
    connection,
    table_name: str,
    schema_mapping: list[dict],
):
    if not schema_mapping:
        raise ValueError(
            "Schema mapping tabel baru tidak boleh kosong."
        )

    normalized = []

    for index, item in enumerate(
        schema_mapping,
        start=1,
    ):
        source_column = str(
            item.get("source_column", "")
        ).strip()

        database_column = validate_column_name(
            item.get("database_column", "")
        )

        if not source_column:
            raise ValueError(
                f"Nama kolom sumber pada urutan {index} tidak boleh kosong."
            )

        normalized.append(
            {
                "table_name": table_name,
                "source_ordinal": int(
                    item.get("source_ordinal", index)
                ),
                "source_column": source_column,
                "database_column": database_column,
            }
        )

    ordinals = [
        item["source_ordinal"]
        for item in normalized
    ]

    if len(ordinals) != len(set(ordinals)):
        raise ValueError(
            "Schema mapping memiliki source ordinal duplikat."
        )

    db_columns = [
        item["database_column"]
        for item in normalized
    ]

    if len(db_columns) != len(set(db_columns)):
        raise ValueError(
            "Schema mapping memiliki nama kolom database duplikat."
        )

    connection.execute(
        delete(schema_mapping_table).where(
            schema_mapping_table.c.table_name == table_name
        )
    )

    connection.execute(
        schema_mapping_table.insert(),
        normalized,
    )


# =====================================================
# SCHEMA VALIDATION
# =====================================================

def validate_existing_table_schema(
    table_name: str,
    df: pd.DataFrame,
):
    database_columns = get_table_columns(table_name)
    upload_columns = [str(column) for column in df.columns]

    missing_in_database = [
        column
        for column in upload_columns
        if column not in database_columns
    ]

    missing_in_upload = [
        column
        for column in database_columns
        if column not in upload_columns
    ]

    if missing_in_database or missing_in_upload:
        messages = []

        if missing_in_database:
            messages.append(
                "Kolom upload yang tidak terdapat pada tabel database: "
                + ", ".join(missing_in_database)
            )

        if missing_in_upload:
            messages.append(
                "Kolom database yang tidak terdapat pada file upload: "
                + ", ".join(missing_in_upload)
            )

        raise ValueError(
            "Schema tidak sesuai. "
            + " | ".join(messages)
        )

    return df[database_columns]


def validate_period_columns(table_name: str):
    columns = set(get_table_columns(table_name))
    missing = sorted(SYSTEM_COLUMNS - columns)

    if missing:
        raise ValueError(
            f"Tabel '{table_name}' belum memiliki kolom sistem "
            f"{', '.join(missing)}. Tabel lama tersebut tidak dapat "
            "menggunakan proteksi periode berbasis bank_id."
        )


# =====================================================
# PERIOD / DUPLICATE PROTECTION
# =====================================================

def count_period_rows(
    table_name: str,
    bank_id: str,
    month: int,
    year: int,
) -> int:
    validate_period_columns(table_name)
    table = _get_reflected_table(table_name)

    statement = (
        select(func.count())
        .select_from(table)
        .where(
            table.c.bank_id == str(bank_id),
            table.c.bulan == int(month),
            table.c.tahun == int(year),
        )
    )

    with engine.connect() as connection:
        return int(
            connection.execute(statement).scalar_one()
        )


def delete_period_rows(
    table_name: str,
    bank_id: str,
    month: int,
    year: int,
) -> int:
    validate_period_columns(table_name)
    table = _get_reflected_table(table_name)

    statement = (
        delete(table)
        .where(
            table.c.bank_id == str(bank_id),
            table.c.bulan == int(month),
            table.c.tahun == int(year),
        )
    )

    with engine.begin() as connection:
        result = connection.execute(statement)
        return int(result.rowcount or 0)


# =====================================================
# CREATE / APPEND
# =====================================================

def create_new_table(
    table_name: str,
    df: pd.DataFrame,
    schema_mapping: list[dict],
):
    table_name = validate_table_name(table_name)

    if table_exists(table_name):
        raise ValueError(
            f"Tabel '{table_name}' sudah tersedia."
        )

    validate_dataframe_columns(df)
    ensure_internal_tables()

    # CREATE TABLE + schema mapping disimpan dalam satu transaksi.
    with engine.begin() as connection:
        df.to_sql(
            name=table_name,
            con=connection,
            if_exists="fail",
            index=False,
            method="multi",
            chunksize=1000,
        )

        _insert_schema_mapping(
            connection=connection,
            table_name=table_name,
            schema_mapping=schema_mapping,
        )

        _ensure_table_state_connection(
            connection,
            table_name,
        )

    return {
        "table_name": table_name,
        "mode": "new",
        "inserted_rows": len(df),
    }


def append_existing_table(
    table_name: str,
    df: pd.DataFrame,
):
    table_name = validate_table_name(table_name)

    if not table_exists(table_name):
        raise ValueError(
            f"Tabel '{table_name}' tidak ditemukan."
        )

    validate_dataframe_columns(df)

    df = validate_existing_table_schema(
        table_name,
        df,
    )

    with engine.begin() as connection:
        lock_relationship_tables(connection, [table_name])
        df.to_sql(
            name=table_name,
            con=connection,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=1000,
        )
        _bump_table_data_version_connection(
            connection,
            table_name,
        )

    _mark_table_profile_stale_best_effort(
        table_name,
        "rows_appended",
    )

    return {
        "table_name": table_name,
        "mode": "existing",
        "inserted_rows": len(df),
    }


def replace_period_data(
    table_name: str,
    df: pd.DataFrame,
    bank_id: str,
    month: int,
    year: int,
):
    table_name = validate_table_name(table_name)

    if not table_exists(table_name):
        raise ValueError(
            f"Tabel '{table_name}' tidak ditemukan."
        )

    validate_dataframe_columns(df)
    validate_period_columns(table_name)

    df = validate_existing_table_schema(
        table_name,
        df,
    )

    table = _get_reflected_table(table_name)

    delete_statement = (
        delete(table)
        .where(
            table.c.bank_id == str(bank_id),
            table.c.bulan == int(month),
            table.c.tahun == int(year),
        )
    )

    with engine.begin() as connection:
        lock_relationship_tables(connection, [table_name])
        delete_result = connection.execute(
            delete_statement
        )

        deleted_rows = int(
            delete_result.rowcount or 0
        )

        df.to_sql(
            name=table_name,
            con=connection,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=1000,
        )

        _bump_table_data_version_connection(
            connection,
            table_name,
        )

    _mark_table_profile_stale_best_effort(
        table_name,
        "period_replaced",
    )

    return {
        "table_name": table_name,
        "mode": "existing",
        "duplicate_action": "replace",
        "replaced_rows": deleted_rows,
        "inserted_rows": len(df),
    }


# =====================================================
# COLUMN MASKING SETTINGS
# =====================================================

def get_masked_columns(table_name: str):
    table_name = validate_table_name(table_name)
    ensure_internal_tables()

    statement = (
        select(
            column_settings_table.c.column_name
        )
        .where(
            column_settings_table.c.table_name
            == table_name,
            column_settings_table.c.is_masked
            .is_(True),
        )
        .order_by(
            column_settings_table.c.column_name
        )
    )

    with engine.connect() as connection:
        rows = connection.execute(
            statement
        ).scalars().all()

    return set(rows)


def set_column_masking(
    table_name: str,
    column_name: str,
    masked: bool,
):
    table_name = validate_table_name(table_name)
    column_name = validate_column_name(
        column_name
    )

    if column_name in SYSTEM_COLUMNS:
        raise ValueError(
            f"Kolom sistem '{column_name}' "
            "tidak dapat dimasking."
        )

    columns = get_table_columns(table_name)

    if column_name not in columns:
        raise ValueError(
            f"Kolom '{column_name}' tidak ditemukan "
            f"pada tabel '{table_name}'."
        )

    ensure_internal_tables()

    with engine.begin() as connection:
        lock_relationship_tables(connection, [table_name])
        existing_id = connection.execute(
            select(
                column_settings_table.c.id
            ).where(
                column_settings_table.c.table_name
                == table_name,
                column_settings_table.c.column_name
                == column_name,
            )
        ).scalar_one_or_none()

        if existing_id is None:
            connection.execute(
                column_settings_table.insert().values(
                    table_name=table_name,
                    column_name=column_name,
                    is_masked=bool(masked),
                )
            )
        else:
            connection.execute(
                column_settings_table.update()
                .where(
                    column_settings_table.c.id
                    == existing_id
                )
                .values(
                    is_masked=bool(masked)
                )
            )

    return {
        "table_name": table_name,
        "column_name": column_name,
        "masked": bool(masked),
    }


# =====================================================
# DATA TABLE CATALOG / COLUMN REVIEW
# =====================================================

def get_table_summary(table_name: str):
    table_name = validate_table_name(table_name)
    table = _get_reflected_table(table_name)
    columns = get_table_columns(table_name)

    with engine.connect() as connection:
        row_count = int(
            connection.execute(
                select(func.count()).select_from(table)
            ).scalar_one()
        )

        bank_count = None
        min_year = None
        max_year = None

        if "bank_id" in columns:
            bank_count = int(
                connection.execute(
                    select(
                        func.count(
                            func.distinct(table.c.bank_id)
                        )
                    ).select_from(table)
                ).scalar_one()
                or 0
            )

        if "tahun" in columns:
            min_year, max_year = connection.execute(
                select(
                    func.min(table.c.tahun),
                    func.max(table.c.tahun),
                ).select_from(table)
            ).one()

    schema_mapping = get_schema_mapping(table_name)

    return {
        "table_name": table_name,
        "row_count": row_count,
        "column_count": len(columns),
        "bank_count": bank_count,
        "min_year": int(min_year) if min_year is not None else None,
        "max_year": int(max_year) if max_year is not None else None,
        "schema_status": (
            "mapped"
            if schema_mapping
            else "unmapped"
        ),
    }


def get_all_table_summaries():
    return [
        get_table_summary(table_name)
        for table_name in get_all_tables()
    ]


def get_table_column_details(table_name: str):
    table_name = validate_table_name(table_name)
    inspector = inspect(engine)

    if not inspector.has_table(table_name):
        raise ValueError(
            f"Tabel '{table_name}' tidak ditemukan."
        )

    mapping = get_schema_mapping(table_name)
    mapping_by_database_column = {
        item["database_column"]: item
        for item in mapping
    }
    masked_columns = get_masked_columns(
        table_name
    )

    details = []

    for ordinal, column in enumerate(
        inspector.get_columns(table_name),
        start=1,
    ):
        name = column["name"]
        mapping_item = mapping_by_database_column.get(name)

        details.append(
            {
                "ordinal": ordinal,
                "column_name": name,
                "data_type": str(column["type"]),
                "nullable": bool(column.get("nullable", True)),
                "source_column": (
                    mapping_item["source_column"]
                    if mapping_item
                    else None
                ),
                "source_ordinal": (
                    mapping_item["source_ordinal"]
                    if mapping_item
                    else None
                ),
                "editable": name not in SYSTEM_COLUMNS,
                "system_column": name in SYSTEM_COLUMNS,
                "maskable": name not in SYSTEM_COLUMNS,
                "masked": name in masked_columns,
            }
        )

    return details


def rename_table_column(
    table_name: str,
    old_name: str,
    new_name: str,
):
    table_name = validate_table_name(table_name)
    old_name = validate_column_name(old_name)
    new_name = validate_column_name(new_name)

    if old_name in SYSTEM_COLUMNS:
        raise ValueError(
            f"Kolom sistem '{old_name}' tidak dapat diubah."
        )

    if new_name in SYSTEM_COLUMNS:
        raise ValueError(
            f"Nama '{new_name}' dicadangkan untuk kolom sistem."
        )

    columns = get_table_columns(table_name)

    if old_name not in columns:
        raise ValueError(
            f"Kolom '{old_name}' tidak ditemukan pada tabel '{table_name}'."
        )

    if new_name == old_name:
        raise ValueError(
            "Nama kolom baru sama dengan nama kolom saat ini."
        )

    if new_name in columns:
        raise ValueError(
            f"Kolom '{new_name}' sudah terdapat pada tabel '{table_name}'."
        )

    preparer = engine.dialect.identifier_preparer
    quoted_table = preparer.quote(table_name)
    quoted_old = preparer.quote(old_name)
    quoted_new = preparer.quote(new_name)

    ensure_internal_tables()

    with engine.begin() as connection:
        lock_relationship_tables(connection, [table_name])
        _invalidate_analysis(connection, table_name, "column_renamed")
        connection.execute(
            text(
                f"ALTER TABLE {quoted_table} "
                f"RENAME COLUMN {quoted_old} TO {quoted_new}"
            )
        )

        connection.execute(
            schema_mapping_table.update()
            .where(
                schema_mapping_table.c.table_name == table_name,
                schema_mapping_table.c.database_column == old_name,
            )
            .values(
                database_column=new_name
            )
        )

        connection.execute(
            column_settings_table.update()
            .where(
                column_settings_table.c.table_name == table_name,
                column_settings_table.c.column_name == old_name,
            )
            .values(
                column_name=new_name
            )
        )

        connection.execute(
            column_profiles_table.update()
            .where(
                column_profiles_table.c.table_name == table_name,
                column_profiles_table.c.column_name == old_name,
            )
            .values(
                column_name=new_name,
                is_stale=True,
                stale_reason="column_renamed",
            )
        )

        connection.execute(
            relationship_candidates_table.update()
            .where(
                or_(
                    relationship_candidates_table.c.source_table == table_name,
                    relationship_candidates_table.c.target_table == table_name,
                )
            )
            .values(
                is_stale=True,
                stale_reason="column_renamed",
                updated_at=func.now(),
            )
        )

        connection.execute(
            relationships_table.update()
            .where(
                relationships_table.c.source_table
                == table_name,
                relationships_table.c.source_column
                == old_name,
            )
            .values(
                source_column=new_name,
                updated_at=func.now(),
            )
        )

        connection.execute(
            relationships_table.update()
            .where(
                relationships_table.c.target_table
                == table_name,
                relationships_table.c.target_column
                == old_name,
            )
            .values(
                target_column=new_name,
                updated_at=func.now(),
            )
        )

        source_relationship_ids = select(
            relationships_table.c.id
        ).where(
            relationships_table.c.source_table
            == table_name
        )

        target_relationship_ids = select(
            relationships_table.c.id
        ).where(
            relationships_table.c.target_table
            == table_name
        )

        connection.execute(
            relationship_columns_table.update()
            .where(
                relationship_columns_table.c.relationship_id
                .in_(source_relationship_ids),
                relationship_columns_table.c.source_column
                == old_name,
            )
            .values(
                source_column=new_name
            )
        )

        connection.execute(
            relationship_columns_table.update()
            .where(
                relationship_columns_table.c.relationship_id
                .in_(target_relationship_ids),
                relationship_columns_table.c.target_column
                == old_name,
            )
            .values(
                target_column=new_name
            )
        )

        connection.execute(
            relationships_table.update()
            .where(
                or_(
                    relationships_table.c.source_table
                    == table_name,
                    relationships_table.c.target_table
                    == table_name,
                )
            )
            .values(
                updated_at=func.now(),
            )
        )

    return {
        "table_name": table_name,
        "old_name": old_name,
        "new_name": new_name,
    }


# =====================================================
# TABLE RELATIONSHIPS
# =====================================================

def _get_column_metadata(
    table_name: str,
    column_name: str,
    connection=None,
):
    table_name = validate_table_name(table_name)
    column_name = validate_column_name(
        column_name
    )

    inspector = inspect(connection if connection is not None else engine)

    if not inspector.has_table(table_name):
        raise ValueError(
            f"Tabel '{table_name}' tidak ditemukan."
        )

    for column in inspector.get_columns(
        table_name
    ):
        if column["name"] == column_name:
            return {
                "column_name": column_name,
                "data_type": str(
                    column["type"]
                ),
                "nullable": bool(
                    column.get(
                        "nullable",
                        True,
                    )
                ),
            }

    raise ValueError(
        f"Kolom '{column_name}' tidak ditemukan "
        f"pada tabel '{table_name}'."
    )


def _relationship_type_family(
    data_type: str,
):
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

    return value or "unknown"


def _relationship_compatibility(
    source_type: str,
    target_type: str,
):
    source_family = _relationship_type_family(
        source_type
    )
    target_family = _relationship_type_family(
        target_type
    )

    compatible = (
        source_family == target_family
    )

    return {
        "compatible": compatible,
        "source_family": source_family,
        "target_family": target_family,
        "message": (
            None
            if compatible
            else (
                "Datatype kedua kolom berbeda. "
                "Relasi tetap dapat disimpan sebagai "
                "metadata, tetapi Visual SQL Builder "
                "mungkin memerlukan casting."
            )
        ),
    }


def _relationship_pair_rows(
    relationship_id: int,
    *,
    connection=None,
):
    statement = (
        select(
            relationship_columns_table
        )
        .where(
            relationship_columns_table.c.relationship_id
            == int(relationship_id)
        )
        .order_by(
            relationship_columns_table.c.ordinal,
            relationship_columns_table.c.id,
        )
    )

    if connection is not None:
        return connection.execute(
            statement
        ).mappings().all()

    with engine.connect() as local_connection:
        return local_connection.execute(
            statement
        ).mappings().all()


def _relationship_masked_columns(
    table_name: str,
    *,
    connection=None,
):
    statement = (
        select(
            column_settings_table.c.column_name
        )
        .where(
            column_settings_table.c.table_name
            == table_name,
            column_settings_table.c.is_masked
            .is_(True),
        )
    )

    if connection is not None:
        rows = connection.execute(
            statement
        ).scalars().all()
        return set(rows)

    with engine.connect() as local_connection:
        rows = local_connection.execute(
            statement
        ).scalars().all()

    return set(rows)


def _normalize_relationship_pairs(
    *,
    source_table: str,
    target_table: str,
    source_column: str | None = None,
    target_column: str | None = None,
    column_pairs: list | None = None,
    connection=None,
):
    raw_pairs = list(column_pairs or [])

    if not raw_pairs:
        raw_pairs = [
            {
                "source_column": source_column,
                "target_column": target_column,
            }
        ]

    if len(raw_pairs) > 12:
        raise ValueError(
            "Satu relationship maksimal memiliki "
            "12 pasangan kolom."
        )

    normalized = []
    seen = set()

    for index, pair in enumerate(
        raw_pairs,
        start=1,
    ):
        if hasattr(pair, "model_dump"):
            pair = pair.model_dump()
        elif hasattr(pair, "dict"):
            pair = pair.dict()

        if not isinstance(pair, dict):
            raise ValueError(
                "Format pasangan kolom relationship "
                "tidak valid."
            )

        raw_source_name = pair.get(
            "source_column"
        )
        raw_target_name = pair.get(
            "target_column"
        )

        if (
            not raw_source_name
            or not raw_target_name
        ):
            raise ValueError(
                "Setiap pasangan relationship "
                "harus memiliki source_column dan "
                "target_column."
            )

        source_name = validate_column_name(
            raw_source_name
        )
        target_name = validate_column_name(
            raw_target_name
        )

        signature = (
            source_name,
            target_name,
        )

        if signature in seen:
            raise ValueError(
                "Pasangan kolom relationship tidak "
                "boleh duplikat."
            )

        if (
            source_table == target_table
            and source_name == target_name
        ):
            raise ValueError(
                "Source dan target tidak boleh "
                "merupakan kolom yang sama."
            )

        source_meta = _get_column_metadata(
            source_table,
            source_name,
            connection=connection,
        )
        target_meta = _get_column_metadata(
            target_table,
            target_name,
            connection=connection,
        )

        compatibility = (
            _relationship_compatibility(
                source_meta["data_type"],
                target_meta["data_type"],
            )
        )

        normalized.append(
            {
                "ordinal": index,
                "source_column": source_name,
                "target_column": target_name,
                "source_data_type":
                    source_meta["data_type"],
                "target_data_type":
                    target_meta["data_type"],
                "compatible":
                    compatibility["compatible"],
                "compatibility_message":
                    compatibility["message"],
            }
        )
        seen.add(signature)

    if not normalized:
        raise ValueError(
            "Relationship minimal memiliki satu "
            "pasangan kolom."
        )

    return normalized


def _relationship_pair_signature(
    pairs,
):
    return tuple(
        sorted(
            (
                pair["source_column"],
                pair["target_column"],
            )
            for pair in pairs
        )
    )


def _serialize_relationship(
    row,
    *,
    connection=None,
):
    if not row:
        return None

    pair_rows = _relationship_pair_rows(
        row["id"],
        connection=connection,
    )

    # Fallback untuk database yang sangat lama sebelum backfill.
    if not pair_rows:
        pair_rows = [
            {
                "relationship_id": row["id"],
                "source_column":
                    row["source_column"],
                "target_column":
                    row["target_column"],
                "ordinal": 1,
            }
        ]

    source_masked_columns = (
        _relationship_masked_columns(
            row["source_table"],
            connection=connection,
        )
    )
    target_masked_columns = (
        _relationship_masked_columns(
            row["target_table"],
            connection=connection,
        )
    )

    serialized_pairs = []

    for pair in pair_rows:
        source_meta = _get_column_metadata(
            row["source_table"],
            pair["source_column"],
            connection=connection,
        )
        target_meta = _get_column_metadata(
            row["target_table"],
            pair["target_column"],
            connection=connection,
        )

        compatibility = (
            _relationship_compatibility(
                source_meta["data_type"],
                target_meta["data_type"],
            )
        )

        serialized_pairs.append(
            {
                "ordinal": int(
                    pair["ordinal"]
                ),
                "source_column":
                    pair["source_column"],
                "source_data_type":
                    source_meta["data_type"],
                "source_masked":
                    pair["source_column"]
                    in source_masked_columns,
                "target_column":
                    pair["target_column"],
                "target_data_type":
                    target_meta["data_type"],
                "target_masked":
                    pair["target_column"]
                    in target_masked_columns,
                "compatible":
                    compatibility["compatible"],
                "compatibility_message":
                    compatibility["message"],
            }
        )

    primary = serialized_pairs[0]
    incompatible_count = sum(
        1
        for pair in serialized_pairs
        if not pair["compatible"]
    )

    compatibility_message = (
        None
        if incompatible_count == 0
        else (
            f"{incompatible_count} dari "
            f"{len(serialized_pairs)} pasangan "
            "kolom memiliki datatype berbeda. "
            "Relationship tetap disimpan sebagai "
            "metadata, tetapi query mungkin "
            "memerlukan casting."
        )
    )

    return {
        "id": int(row["id"]),
        "relationship_name":
            row["relationship_name"],
        "source_table":
            row["source_table"],
        # Legacy primary pair tetap dikirim agar komponen lama tidak rusak.
        "source_column":
            primary["source_column"],
        "source_data_type":
            primary["source_data_type"],
        "source_masked":
            any(
                pair["source_masked"]
                for pair in serialized_pairs
            ),
        "target_table":
            row["target_table"],
        "target_column":
            primary["target_column"],
        "target_data_type":
            primary["target_data_type"],
        "target_masked":
            any(
                pair["target_masked"]
                for pair in serialized_pairs
            ),
        "column_pairs":
            serialized_pairs,
        "pair_count":
            len(serialized_pairs),
        "cardinality":
            row["cardinality"],
        "is_active":
            bool(row["is_active"]),
        "compatible":
            incompatible_count == 0,
        "compatibility_message":
            compatibility_message,
        "created_at":
            row["created_at"],
        "updated_at":
            row["updated_at"],
    }


def get_table_relationships(
    table_name: str | None = None,
):
    ensure_internal_tables()

    statement = select(
        relationships_table
    )

    if table_name:
        table_name = validate_table_name(
            table_name
        )
        statement = statement.where(
            or_(
                relationships_table.c.source_table
                == table_name,
                relationships_table.c.target_table
                == table_name,
            )
        )

    statement = statement.order_by(
        relationships_table.c.id
    )

    relationships = []

    with engine.connect() as connection:
        rows = connection.execute(
            statement
        ).mappings().all()

        for row in rows:
            try:
                relationships.append(
                    _serialize_relationship(
                        row,
                        connection=connection,
                    )
                )
            except ValueError:
                # Metadata relasi yang sudah tidak memiliki
                # table/column valid diabaikan dari UI.
                continue

    return relationships


def create_table_relationship(
    *,
    relationship_name: str | None,
    source_table: str,
    target_table: str,
    cardinality: str,
    source_column: str | None = None,
    target_column: str | None = None,
    column_pairs: list | None = None,
    connection=None,
):
    source_table = validate_table_name(
        source_table
    )
    target_table = validate_table_name(
        target_table
    )
    cardinality = str(
        cardinality or ""
    ).strip()

    if cardinality not in (
        RELATIONSHIP_CARDINALITIES
    ):
        raise ValueError(
            "Cardinality tidak valid."
        )

    pairs = _normalize_relationship_pairs(
        source_table=source_table,
        target_table=target_table,
        source_column=source_column,
        target_column=target_column,
        column_pairs=column_pairs,
        connection=connection,
    )

    primary = pairs[0]

    name = str(
        relationship_name or ""
    ).strip()

    if not name:
        if len(pairs) == 1:
            name = (
                f"{source_table}."
                f"{primary['source_column']} ↔ "
                f"{target_table}."
                f"{primary['target_column']}"
            )
        else:
            key_preview = ", ".join(
                pair["source_column"]
                for pair in pairs[:4]
            )
            if len(pairs) > 4:
                key_preview += ", …"

            name = (
                f"{source_table} ↔ "
                f"{target_table} "
                f"({key_preview})"
            )

    if len(name) > 180:
        raise ValueError(
            "Nama relationship maksimal "
            "180 karakter."
        )

    if connection is None:
        ensure_internal_tables()

    with (engine.begin() if connection is None else nullcontext(connection)) as connection:
        lock_relationship_tables(connection, [source_table, target_table])
        # Revalidate schema while coordinated with rename/masking/data writers.
        pairs = _normalize_relationship_pairs(source_table=source_table, target_table=target_table,
                                              column_pairs=pairs, connection=connection)
        _assert_no_relationship_duplicate(connection, source_table, target_table, pairs)
        result = connection.execute(
            relationships_table.insert().values(
                relationship_name=name,
                source_table=source_table,
                source_column=
                    primary["source_column"],
                target_table=target_table,
                target_column=
                    primary["target_column"],
                cardinality=cardinality,
                is_active=True,
            )
        )

        relationship_id = int(
            result.inserted_primary_key[0]
        )

        connection.execute(
            relationship_columns_table.insert(),
            [
                {
                    "relationship_id":
                        relationship_id,
                    "source_column":
                        pair["source_column"],
                    "target_column":
                        pair["target_column"],
                    "ordinal":
                        pair["ordinal"],
                }
                for pair in pairs
            ],
        )

        row = connection.execute(
            select(
                relationships_table
            ).where(
                relationships_table.c.id
                == relationship_id
            )
        ).mappings().one()

        serialized = _serialize_relationship(
            row,
            connection=connection,
        )

    return serialized


def update_table_relationship(
    relationship_id: int,
    *,
    relationship_name: str | None = None,
    cardinality: str | None = None,
    is_active: bool | None = None,
):
    ensure_internal_tables()

    relationship_id = int(
        relationship_id
    )

    with engine.begin() as connection:
        current = connection.execute(
            select(
                relationships_table
            ).where(
                relationships_table.c.id
                == relationship_id
            )
        ).mappings().one_or_none()

        if current is None:
            raise ValueError(
                "Relationship tidak ditemukan."
            )

        lock_relationship_tables(connection, [current["source_table"], current["target_table"]])
        if is_active:
            _assert_no_relationship_duplicate(connection, current["source_table"], current["target_table"],
                _relationship_pair_rows(relationship_id, connection=connection) or [current], exclude_id=relationship_id)
        values = {
            "updated_at": func.now(),
        }

        if relationship_name is not None:
            name = str(
                relationship_name
            ).strip()

            if not name:
                raise ValueError(
                    "Nama relationship tidak "
                    "boleh kosong."
                )

            if len(name) > 180:
                raise ValueError(
                    "Nama relationship maksimal "
                    "180 karakter."
                )

            values["relationship_name"] = (
                name
            )

        if cardinality is not None:
            cardinality = str(
                cardinality
            ).strip()

            if cardinality not in (
                RELATIONSHIP_CARDINALITIES
            ):
                raise ValueError(
                    "Cardinality tidak valid."
                )

            values["cardinality"] = (
                cardinality
            )

        if is_active is not None:
            values["is_active"] = bool(
                is_active
            )

        connection.execute(
            relationships_table.update()
            .where(
                relationships_table.c.id
                == relationship_id
            )
            .values(**values)
        )

        row = connection.execute(
            select(
                relationships_table
            ).where(
                relationships_table.c.id
                == relationship_id
            )
        ).mappings().one()

        serialized = _serialize_relationship(
            row,
            connection=connection,
        )

    return serialized


def delete_table_relationship(
    relationship_id: int,
):
    ensure_internal_tables()

    relationship_id = int(
        relationship_id
    )

    with engine.begin() as connection:
        current = connection.execute(
            select(
                relationships_table
            ).where(
                relationships_table.c.id
                == relationship_id
            )
        ).mappings().one_or_none()

        if current is None:
            raise ValueError(
                "Relationship tidak ditemukan."
            )

        lock_relationship_tables(connection, [current["source_table"], current["target_table"]])
        connection.execute(
            relationship_columns_table.delete()
            .where(
                relationship_columns_table.c.relationship_id
                == relationship_id
            )
        )

        connection.execute(
            relationships_table.delete()
            .where(
                relationships_table.c.id
                == relationship_id
            )
        )

    return {
        "id": relationship_id,
        "deleted": True,
    }


# =====================================================
# TABLE EXPLORER
# =====================================================

def get_table_explorer_options(table_name: str):
    table_name = validate_table_name(table_name)
    table = _get_reflected_table(table_name)
    columns = get_table_column_details(table_name)

    options = {
        "bank_ids": [],
        "months": [],
        "years": [],
    }

    with engine.connect() as connection:
        if "bank_id" in table.c:
            rows = connection.execute(
                select(table.c.bank_id)
                .where(table.c.bank_id.is_not(None))
                .distinct()
                .order_by(table.c.bank_id)
            ).scalars().all()

            options["bank_ids"] = [
                str(value)
                for value in rows
            ]

        if "bulan" in table.c:
            rows = connection.execute(
                select(table.c.bulan)
                .where(table.c.bulan.is_not(None))
                .distinct()
                .order_by(table.c.bulan)
            ).scalars().all()

            options["months"] = [
                int(value)
                for value in rows
            ]

        if "tahun" in table.c:
            rows = connection.execute(
                select(table.c.tahun)
                .where(table.c.tahun.is_not(None))
                .distinct()
                .order_by(table.c.tahun)
            ).scalars().all()

            options["years"] = [
                int(value)
                for value in rows
            ]

    return {
        "table_name": table_name,
        "columns": columns,
        "filters": options,
    }


def explore_table_data(
    table_name: str,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    bank_id: str | None = None,
    month: int | None = None,
    year: int | None = None,
    sort_column: str | None = None,
    sort_direction: str = "asc",
):
    table_name = validate_table_name(table_name)
    table = _get_reflected_table(table_name)
    column_names = [
        column.name
        for column in table.columns
    ]
    masked_columns = get_masked_columns(
        table_name
    )

    page = max(int(page or 1), 1)
    page_size = max(
        min(int(page_size or 20), 200),
        1,
    )

    filters = []

    if bank_id and "bank_id" in table.c:
        filters.append(
            table.c.bank_id == str(bank_id)
        )

    if month is not None and "bulan" in table.c:
        filters.append(
            table.c.bulan == int(month)
        )

    if year is not None and "tahun" in table.c:
        filters.append(
            table.c.tahun == int(year)
        )

    search = str(search or "").strip()

    if search:
        search_pattern = f"%{search}%"

        search_clauses = [
            cast(column, String).ilike(
                search_pattern
            )
            for column in table.columns
            if column.name
            not in masked_columns
        ]

        if search_clauses:
            filters.append(
                or_(*search_clauses)
            )

    count_statement = (
        select(func.count())
        .select_from(table)
    )

    if filters:
        count_statement = (
            count_statement.where(*filters)
        )

    with engine.connect() as connection:
        total_rows = int(
            connection.execute(
                count_statement
            ).scalar_one()
            or 0
        )

        total_pages = max(
            (total_rows + page_size - 1)
            // page_size,
            1,
        )

        page = min(page, total_pages)

        statement = select(table)

        if filters:
            statement = statement.where(
                *filters
            )

        sort_direction = str(
            sort_direction or "asc"
        ).lower()

        if sort_direction not in {
            "asc",
            "desc",
        }:
            sort_direction = "asc"

        if sort_column:
            sort_column = validate_column_name(
                sort_column
            )

            if sort_column not in column_names:
                raise ValueError(
                    f"Kolom sort '{sort_column}' "
                    f"tidak ditemukan pada tabel "
                    f"'{table_name}'."
                )

            if sort_column in masked_columns:
                raise ValueError(
                    f"Kolom '{sort_column}' sedang "
                    "dimasking dan tidak dapat "
                    "digunakan untuk sorting."
                )

            sort_expression = table.c[
                sort_column
            ]

            statement = statement.order_by(
                sort_expression.desc()
                if sort_direction == "desc"
                else sort_expression.asc()
            )

        else:
            default_sort_columns = [
                name
                for name in (
                    "bank_id",
                    "tahun",
                    "bulan",
                )
                if name in table.c
            ]

            if default_sort_columns:
                statement = statement.order_by(
                    *[
                        table.c[name].asc()
                        for name in default_sort_columns
                    ]
                )
            elif column_names:
                statement = statement.order_by(
                    table.c[
                        column_names[0]
                    ].asc()
                )

        statement = (
            statement
            .offset(
                (page - 1) * page_size
            )
            .limit(page_size)
        )

        rows = connection.execute(
            statement
        ).mappings().all()

    return {
        "table_name": table_name,
        "rows": [
            {
                key: (
                    MASK_VALUE
                    if key in masked_columns
                    else value
                )
                for key, value
                in dict(row).items()
            }
            for row in rows
        ],
        "masked_columns": sorted(
            masked_columns
        ),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_rows": total_rows,
            "total_pages": total_pages,
        },
        "sort": {
            "column": sort_column,
            "direction": sort_direction,
        },
        "filters": {
            "search": search,
            "bank_id": bank_id,
            "month": month,
            "year": year,
        },
    }
