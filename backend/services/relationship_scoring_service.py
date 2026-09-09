from concurrent.futures import ThreadPoolExecutor

from database.table_service import (
    claim_relationship_scoring_job,
    create_relationship_scoring_job_record,
    get_column_profiles_for_tables,
    get_recoverable_relationship_scoring_jobs,
    get_relationship_candidate_scores,
    get_relationship_candidates_for_scoring,
    get_relationship_scoring_job,
    get_relationship_scoring_jobs,
    update_relationship_scoring_job,
    upsert_relationship_candidate_score,
)

_SCORING_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="relationship-score")
SCORING_VERSION = "metadata_quality_v1"


def _clamp(value):
    return max(0.0, min(float(value), 1.0))


def _profile_quality(profile):
    if not profile or profile.get("is_stale"):
        return 0.0
    sample = int(profile.get("sample_non_null_count") or 0)
    if sample >= 5000: sample_score = 1.0
    elif sample >= 1000: sample_score = 0.92
    elif sample >= 250: sample_score = 0.80
    elif sample >= 50: sample_score = 0.65
    else: sample_score = 0.40
    null_ratio = profile.get("null_ratio")
    null_score = 0.75 if null_ratio is None else _clamp(1.0 - float(null_ratio))
    return _clamp(0.65 * sample_score + 0.35 * null_score)


def score_candidate(candidate, source_profile, target_profile):
    evidence = candidate.get("evidence") or {}
    semantic = _clamp(candidate.get("name_similarity") or 0)
    if evidence.get("same_system_key"):
        semantic = max(semantic, 0.98)

    sf = candidate.get("source_type_family")
    tf = candidate.get("target_type_family")
    datatype = 1.0 if sf == tf else (0.90 if {sf, tf} == {"date", "timestamp"} else 0.0)

    fp_meta = evidence.get("fingerprint") or {}
    fp_comparable = bool(fp_meta.get("comparable"))
    fingerprint = _clamp(candidate.get("fingerprint_overlap") or 0) if fp_comparable else None

    profile_quality = (_profile_quality(source_profile) + _profile_quality(target_profile)) / 2.0
    sd = float((source_profile or {}).get("distinct_ratio") or 0)
    td = float((target_profile or {}).get("distinct_ratio") or 0)
    key_plausibility = _clamp(max(sd, td))

    source_sample = int((source_profile or {}).get("sample_non_null_count") or 0)
    target_sample = int((target_profile or {}).get("sample_non_null_count") or 0)
    evidence_sufficiency = 0.35
    if semantic >= 0.7: evidence_sufficiency += 0.20
    if datatype >= 0.9: evidence_sufficiency += 0.15
    if min(source_sample, target_sample) >= 250: evidence_sufficiency += 0.15
    if fp_comparable: evidence_sufficiency += 0.15
    evidence_sufficiency = _clamp(evidence_sufficiency)

    components = {
        "semantic": semantic,
        "datatype": datatype,
        "profile_quality": profile_quality,
        "key_plausibility": key_plausibility,
    }
    weights = {"semantic": 0.25, "datatype": 0.15, "profile_quality": 0.15, "key_plausibility": 0.20}
    if fingerprint is not None:
        components["fingerprint"] = fingerprint
        weights["fingerprint"] = 0.25
    total_weight = sum(weights.values())
    weighted = sum(components[k] * weights[k] for k in weights) / total_weight

    flags = []
    penalty = 0.0
    source_null = float((source_profile or {}).get("null_ratio") or 0)
    target_null = float((target_profile or {}).get("null_ratio") or 0)
    if max(source_null, target_null) >= 0.50:
        flags.append("high_null_ratio"); penalty += 0.08
    if min(source_sample, target_sample) < 50:
        flags.append("low_sample_evidence"); penalty += 0.06
    if fingerprint is None:
        flags.append("fingerprint_not_comparable")
    elif fingerprint < 0.10:
        flags.append("weak_value_overlap"); penalty += 0.05
    if max(sd, td) < 0.02 and not evidence.get("same_system_key"):
        flags.append("weak_key_uniqueness"); penalty += 0.05
    if evidence_sufficiency < 0.60:
        flags.append("limited_evidence"); penalty += 0.04

    confidence = _clamp(weighted * (0.85 + 0.15 * evidence_sufficiency) - penalty)
    if confidence >= 0.85: level = "high"
    elif confidence >= 0.70: level = "medium"
    elif confidence >= 0.55: level = "low"
    else: level = "review"

    return {
        "candidate_id": candidate["id"], "candidate_key": candidate["candidate_key"],
        "scoring_version": SCORING_VERSION,
        "source_profile_version": candidate["source_profile_version"], "target_profile_version": candidate["target_profile_version"],
        "source_data_version": candidate["source_data_version"], "target_data_version": candidate["target_data_version"],
        "semantic_score": semantic, "datatype_score": datatype, "fingerprint_score": fingerprint,
        "profile_quality_score": profile_quality, "key_plausibility_score": key_plausibility,
        "evidence_sufficiency_score": evidence_sufficiency, "penalty_score": penalty,
        "confidence_score": confidence, "confidence_level": level,
        "component_scores": {**components, "weights": weights}, "quality_flags": flags,
        "rationale": {"metadata_only": True, "warehouse_rows_scanned": 0, "source_distinct_ratio": sd, "target_distinct_ratio": td, "source_null_ratio": source_null, "target_null_ratio": target_null},
    }


def run_relationship_scoring_job(job_id: int):
    try:
        job = claim_relationship_scoring_job(job_id)
        if job is None: return None
        candidates = get_relationship_candidates_for_scoring(source_tables=job["source_tables"], target_tables=job["target_tables"], status=job["candidate_status"], min_discovery_score=job["min_discovery_score"], max_candidates=job["max_candidates"])
        tables = sorted({c["source_table"] for c in candidates} | {c["target_table"] for c in candidates})
        profiles = get_column_profiles_for_tables(tables, include_stale=False)
        profile_map = {(p["table_name"], p["column_name"]): p for p in profiles}
        scored=0; skipped=0; levels={"high":0,"medium":0,"low":0,"review":0}
        for c in candidates:
            sp=profile_map.get((c["source_table"],c["source_column"])); tp=profile_map.get((c["target_table"],c["target_column"]))
            if not sp or not tp or sp["profile_version"] != c["source_profile_version"] or tp["profile_version"] != c["target_profile_version"] or sp["source_data_version"] != c["source_data_version"] or tp["source_data_version"] != c["target_data_version"]:
                skipped += 1; continue
            score=score_candidate(c,sp,tp); score["last_scored_job_id"]=job_id
            saved=upsert_relationship_candidate_score(score); scored += 1; levels[saved["confidence_level"]]=levels.get(saved["confidence_level"],0)+1
        summary={"scoring_version":SCORING_VERSION,"metadata_only":True,"warehouse_rows_scanned":0,"candidate_count":len(candidates),"scored_count":scored,"skipped_count":skipped,"confidence_levels":levels}
        return update_relationship_scoring_job(job_id,status="completed",candidate_count=len(candidates),scored_count=scored,skipped_count=skipped,result_summary=summary)
    except Exception as error:
        try: update_relationship_scoring_job(job_id,status="failed",error_message=str(error))
        except Exception: pass
        print("ERROR relationship scoring job", job_id, repr(error)); return None


def _submit(job_id): _SCORING_EXECUTOR.submit(run_relationship_scoring_job,int(job_id))

def queue_relationship_scoring_job(**kwargs):
    job,created=create_relationship_scoring_job_record(**kwargs)
    if created: _submit(job["id"])
    return {"job":job,"created":created,"message":"Relationship scoring job masuk antrean." if created else "Scoring job dengan scope yang sama masih queued/running."}

def recover_relationship_scoring_queue():
    ids=get_recoverable_relationship_scoring_jobs()
    for job_id in ids: _submit(job_id)
    return len(ids)

def list_relationship_scoring_jobs(*,limit=50): return get_relationship_scoring_jobs(limit=limit)

def get_relationship_scoring_job_status(job_id:int): return get_relationship_scoring_job(job_id)
