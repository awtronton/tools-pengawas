import math
from services.relationship_freshness_service import quality_signature, candidate_signature, VERSION_FIELDS
from concurrent.futures import ThreadPoolExecutor

from database.table_service import (
    claim_relationship_cardinality_job,
    create_relationship_cardinality_job_record,
    get_column_profiles_for_tables,
    get_recoverable_relationship_cardinality_jobs,
    get_relationship_candidate_scores,
    get_relationship_candidates_for_scoring,
    get_relationship_cardinality_job,
    get_relationship_cardinality_jobs,
    update_relationship_cardinality_job,
    upsert_relationship_cardinality_estimate,
)

_CARDINALITY_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="relationship-cardinality",
)

CARDINALITY_ESTIMATION_VERSION = "metadata_cardinality_v1"
TARGET_CONFIDENCE_SAMPLE_ROWS = 50000


def _clamp(value):
    return max(0.0, min(float(value), 1.0))


def _sample_coverage(profile):
    if not profile:
        return 0.0

    if str(profile.get("profile_mode") or "").lower() == "full":
        return 1.0

    sample_rows = int(profile.get("sample_row_count") or 0)
    estimated_rows = profile.get("row_count_estimate")
    if estimated_rows is None:
        return 0.0

    estimated_rows = int(estimated_rows or 0)
    if estimated_rows <= 0:
        return 0.0

    return _clamp(float(sample_rows) / float(estimated_rows))


def _sample_size_strength(non_null_count):
    count = max(0, int(non_null_count or 0))
    if count <= 1:
        return 0.0

    return _clamp(
        math.log1p(count)
        / math.log1p(TARGET_CONFIDENCE_SAMPLE_ROWS)
    )


def estimate_column_role(profile, *, side):
    """Estimate whether one column behaves as ONE or MANY.

    A duplicate observed inside a real sample proves the column is not unique
    across the full table. The reverse is not true: a sampled column with no
    duplicate is only a candidate for uniqueness, so confidence is capped
    until a full profile or substantial sample coverage is available.
    """
    if not profile:
        return {
            "role": "one",
            "confidence": 0.0,
            "flags": [f"missing_{side}_profile"],
            "evidence": {},
        }

    non_null = int(profile.get("sample_non_null_count") or 0)
    distinct = int(profile.get("sample_distinct_count") or 0)
    duplicate_count = max(0, non_null - distinct)
    duplicate_ratio = (
        float(duplicate_count) / float(non_null)
        if non_null > 0
        else 0.0
    )
    null_ratio = float(profile.get("null_ratio") or 0.0)
    profile_mode = str(profile.get("profile_mode") or "sampled").lower()
    coverage = _sample_coverage(profile)
    sample_strength = _sample_size_strength(non_null)
    avg_length = float(profile.get("avg_length") or 0.0)

    flags = []

    if non_null < 2:
        flags.append(f"insufficient_{side}_non_null_rows")
        role = "one"
        confidence = 0.10 if non_null == 1 else 0.0
    elif duplicate_count > 0:
        # At least one observed duplicate is direct evidence that this side is
        # MANY. Confidence grows with repeated duplicate evidence.
        role = "many"
        repeated_duplicate_strength = _clamp(duplicate_ratio * 20.0)
        confidence = 0.92 + 0.07 * repeated_duplicate_strength
        flags.append(f"observed_{side}_duplicates")
    else:
        role = "one"
        if profile_mode == "full":
            confidence = 0.995
        else:
            # No duplicate in a sample is only provisional uniqueness.
            # Sample size gives evidence, while actual table coverage is the
            # strongest protection against a high-cardinality false positive.
            confidence = (
                0.30
                + 0.35 * sample_strength
                + 0.30 * math.sqrt(coverage)
            )
            confidence = min(confidence, 0.90)
            flags.append(f"sampled_{side}_uniqueness_unconfirmed")

    if null_ratio >= 0.50:
        confidence *= 0.90
        flags.append(f"high_{side}_null_ratio")
    elif null_ratio >= 0.20:
        confidence *= 0.96
        flags.append(f"moderate_{side}_null_ratio")

    # Profiling normalizes relationship values to a bounded text prefix.
    # Extremely long text fields therefore need human review before a
    # duplicate observation is treated as business-key evidence.
    if avg_length >= 500.0:
        confidence *= 0.88
        flags.append(f"{side}_long_text_key_risk")

    evidence = {
        "profile_mode": profile_mode,
        "sample_row_count": int(profile.get("sample_row_count") or 0),
        "sample_non_null_count": non_null,
        "sample_distinct_count": distinct,
        "duplicate_count": duplicate_count,
        "duplicate_ratio": round(duplicate_ratio, 8),
        "distinct_ratio": profile.get("distinct_ratio"),
        "null_ratio": profile.get("null_ratio"),
        "sample_coverage_estimate": round(coverage, 8),
        "sample_size_strength": round(sample_strength, 8),
        "row_count_estimate": profile.get("row_count_estimate"),
    }

    return {
        "role": role,
        "confidence": _clamp(confidence),
        "flags": flags,
        "evidence": evidence,
    }


def _map_cardinality(source_role, target_role):
    mapping = {
        ("one", "one"): "one_to_one",
        ("one", "many"): "one_to_many",
        ("many", "one"): "many_to_one",
        ("many", "many"): "many_to_many",
    }
    return mapping[(source_role, target_role)]


def estimate_candidate_cardinality(
    candidate,
    source_profile,
    target_profile,
    quality_score=None,
):
    source = estimate_column_role(source_profile, side="source")
    target = estimate_column_role(target_profile, side="target")

    cardinality = _map_cardinality(source["role"], target["role"])
    base_confidence = min(
        source["confidence"],
        target["confidence"],
    )

    quality_confidence = None
    if quality_score and not quality_score.get("is_stale"):
        quality_confidence = _clamp(
            quality_score.get("confidence_score") or 0.0
        )

    # Relationship quality is supportive evidence, not direct cardinality
    # evidence. It may slightly temper the estimate but cannot manufacture
    # uniqueness that was not observed in profiling.
    if quality_confidence is None:
        cardinality_confidence = base_confidence * 0.92
    else:
        cardinality_confidence = base_confidence * (
            0.85 + 0.15 * quality_confidence
        )

    flags = list(source["flags"]) + list(target["flags"])
    if quality_confidence is None:
        flags.append("quality_score_missing")
    elif quality_confidence < 0.55:
        flags.append("low_relationship_quality")

    if cardinality == "many_to_many":
        flags.append("many_to_many_join_expansion_risk")

    sampled_uniqueness = any(
        "uniqueness_unconfirmed" in flag
        for flag in flags
    )
    requires_review = (
        cardinality_confidence < 0.85
        or sampled_uniqueness
        or cardinality == "many_to_many"
        or (quality_confidence is not None and quality_confidence < 0.70)
    )

    return {
        "candidate_id": candidate["id"],
        "candidate_key": candidate["candidate_key"],
        "estimation_version": CARDINALITY_ESTIMATION_VERSION,
        "source_profile_version": candidate["source_profile_version"],
        "target_profile_version": candidate["target_profile_version"],
        "source_data_version": candidate["source_data_version"],
        "target_data_version": candidate["target_data_version"],
        "source_role": source["role"],
        "target_role": target["role"],
        "source_role_confidence": source["confidence"],
        "target_role_confidence": target["confidence"],
        "estimated_cardinality": cardinality,
        "cardinality_confidence": _clamp(cardinality_confidence),
        "evidence": {
            "candidate_signature": candidate_signature(candidate),
            "metadata_only": True,
            "warehouse_rows_scanned": 0,
            "source": source["evidence"],
            "target": target["evidence"],
            "relationship_quality_confidence": quality_confidence,
            "quality_score_signature": quality_signature(quality_score),
            "method": (
                "observed_sample_duplicates_and_conservative_"
                "uniqueness_estimation"
            ),
        },
        "quality_flags": sorted(set(flags)),
        "requires_review": requires_review,
    }


def run_relationship_cardinality_job(job_id: int):
    try:
        job = claim_relationship_cardinality_job(job_id)
        if job is None:
            return None

        candidates = get_relationship_candidates_for_scoring(
            source_tables=job["source_tables"],
            target_tables=job["target_tables"],
            status=job["candidate_status"],
            min_discovery_score=job["min_discovery_score"],
            max_candidates=job["max_candidates"],
        )

        scores = get_relationship_candidate_scores(
            [candidate["id"] for candidate in candidates]
        )

        eligible = []
        skipped_quality = 0
        for candidate in candidates:
            score = scores.get(candidate["id"])
            if job["min_quality_score"] > 0:
                if (
                    score is None
                    or score.get("is_stale")
                    or any(score.get(k) != candidate[k] for k in VERSION_FIELDS)
                    or float(score.get("confidence_score") or 0.0)
                    < job["min_quality_score"]
                ):
                    skipped_quality += 1
                    continue
            eligible.append(candidate)

        tables = sorted(
            {candidate["source_table"] for candidate in eligible}
            | {candidate["target_table"] for candidate in eligible}
        )
        profiles = get_column_profiles_for_tables(
            tables, include_stale=False,
        ) if tables else []
        profile_map = {
            (profile["table_name"], profile["column_name"]): profile
            for profile in profiles
        }

        estimated_count = 0
        skipped_profile = 0
        cardinalities = {
            "one_to_one": 0,
            "one_to_many": 0,
            "many_to_one": 0,
            "many_to_many": 0,
        }
        review_count = 0

        for candidate in eligible:
            source_profile = profile_map.get(
                (candidate["source_table"], candidate["source_column"])
            )
            target_profile = profile_map.get(
                (candidate["target_table"], candidate["target_column"])
            )

            versions_match = (
                source_profile
                and target_profile
                and source_profile["profile_version"]
                == candidate["source_profile_version"]
                and target_profile["profile_version"]
                == candidate["target_profile_version"]
                and source_profile["source_data_version"]
                == candidate["source_data_version"]
                and target_profile["source_data_version"]
                == candidate["target_data_version"]
            )
            if not versions_match:
                skipped_profile += 1
                continue

            estimate = estimate_candidate_cardinality(
                candidate,
                source_profile,
                target_profile,
                scores.get(candidate["id"]),
            )
            estimate["last_estimated_job_id"] = job_id
            saved = upsert_relationship_cardinality_estimate(estimate)

            estimated_count += 1
            cardinalities[saved["estimated_cardinality"]] = (
                cardinalities.get(saved["estimated_cardinality"], 0) + 1
            )
            if saved["requires_review"]:
                review_count += 1

        skipped_count = skipped_quality + skipped_profile
        summary = {
            "estimation_version": CARDINALITY_ESTIMATION_VERSION,
            "metadata_only": True,
            "warehouse_rows_scanned": 0,
            "candidate_count": len(candidates),
            "eligible_count": len(eligible),
            "estimated_count": estimated_count,
            "skipped_quality_count": skipped_quality,
            "skipped_profile_count": skipped_profile,
            "requires_review_count": review_count,
            "cardinalities": cardinalities,
        }

        return update_relationship_cardinality_job(
            job_id,
            status="completed",
            candidate_count=len(candidates),
            estimated_count=estimated_count,
            skipped_count=skipped_count,
            result_summary=summary,
        )
    except Exception as error:
        try:
            update_relationship_cardinality_job(
                job_id,
                status="failed",
                error_message=str(error),
            )
        except Exception:
            pass
        print(
            "ERROR relationship cardinality job",
            job_id,
            repr(error),
        )
        return None


def _submit(job_id):
    _CARDINALITY_EXECUTOR.submit(
        run_relationship_cardinality_job,
        int(job_id),
    )


def queue_relationship_cardinality_job(**kwargs):
    job, created = create_relationship_cardinality_job_record(**kwargs)
    if created:
        _submit(job["id"])
    return {
        "job": job,
        "created": created,
        "message": (
            "Relationship cardinality job masuk antrean."
            if created
            else "Cardinality job dengan scope yang sama masih queued/running."
        ),
    }


def recover_relationship_cardinality_queue():
    ids = get_recoverable_relationship_cardinality_jobs()
    for job_id in ids:
        _submit(job_id)
    return len(ids)


def list_relationship_cardinality_jobs(*, limit=50):
    return get_relationship_cardinality_jobs(limit=limit)


def get_relationship_cardinality_job_status(job_id: int):
    return get_relationship_cardinality_job(job_id)
