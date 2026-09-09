"""Pure, shared evidence validation; no warehouse reads or database writes."""
import hashlib
import json


VERSION_FIELDS = (
    "source_profile_version", "target_profile_version",
    "source_data_version", "target_data_version",
)


def evidence_digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str,
        allow_nan=False,
    ).encode()).hexdigest()


def candidate_signature(candidate):
    fields = (*VERSION_FIELDS, "candidate_key", "source_table", "source_column", "target_table",
              "target_column", "source_type_family", "target_type_family", "detector_version",
              "evidence", "discovery_score", "name_similarity", "fingerprint_overlap")
    return evidence_digest({k: candidate.get(k) for k in fields})


def quality_signature(score):
    if not score:
        return None
    return evidence_digest({k: v for k, v in dict(score).items()
                            if k not in {"created_at", "updated_at", "last_scored_job_id"}})


def material_signature(candidate):
    """A rerun alone is not material. Data changes or 5-point evidence buckets are.

    Canonical endpoint order also prevents reverse discovery bypassing a rejection.
    Profile revision numbers and sampling timestamps intentionally do not count.
    """
    evidence = candidate.get("evidence") or {}
    def bucket(value):
        return None if value is None else round(float(value) * 20)
    sides = []
    for side in ("source", "target"):
        sides.append({
            "table": candidate[f"{side}_table"],
            "column": candidate[f"{side}_column"],
            "data_version": candidate[f"{side}_data_version"],
            "type_family": candidate[f"{side}_type_family"],
            "distinct": bucket(evidence.get(f"{side}_distinct_ratio")),
            "null": bucket(evidence.get(f"{side}_null_ratio")),
        })
    return evidence_digest({"sides": sorted(sides, key=lambda s: (s["table"], s["column"]))})


def validate_freshness(candidate, profiles, data_versions, score=None, estimate=None,
                       *, require_analysis=True):
    reasons = []
    if candidate.get("is_stale") or candidate.get("status") == "stale":
        reasons.append("candidate_stale")
    for side in ("source", "target"):
        table = candidate[f"{side}_table"]
        profile = profiles.get((table, candidate[f"{side}_column"]))
        if not profile:
            reasons.append(f"{side}_profile_missing")
            continue
        if profile.get("is_stale"):
            reasons.append(f"{side}_profile_stale")
        if profile["profile_version"] != candidate[f"{side}_profile_version"]:
            reasons.append(f"{side}_profile_version_changed")
        version = data_versions.get(table)
        if (version is None or profile["source_data_version"] != version
                or candidate[f"{side}_data_version"] != version):
            reasons.append(f"{side}_data_version_changed")
    if require_analysis:
        for name, analysis in (("quality_score", score), ("cardinality_estimate", estimate)):
            if not analysis:
                reasons.append(f"{name}_missing")
                continue
            if analysis.get("is_stale"):
                reasons.append(f"{name}_stale")
            if (analysis.get("candidate_id") != candidate["id"]
                    or analysis.get("candidate_key") != candidate["candidate_key"]
                    or any(analysis.get(k) != candidate[k] for k in VERSION_FIELDS)):
                reasons.append(f"{name}_version_mismatch")
        if score and (score.get("rationale") or {}).get("candidate_signature") != candidate_signature(candidate):
            reasons.append("quality_candidate_evidence_changed")
        if estimate and (estimate.get("evidence") or {}).get("candidate_signature") != candidate_signature(candidate):
            reasons.append("cardinality_candidate_evidence_changed")
        if estimate:
            evidence = estimate.get("evidence") or {}
            if "quality_score_signature" not in evidence:
                reasons.append("cardinality_quality_lineage_missing")
            elif evidence["quality_score_signature"] != quality_signature(score):
                reasons.append("cardinality_quality_changed")
    return {"is_fresh": not reasons, "reasons": reasons}
