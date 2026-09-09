"""Human decisions over bounded metadata snapshots. Never executes warehouse SELECTs."""
import json

from sqlalchemy import inspect, or_, select, text

from database import table_service as db
from services.relationship_freshness_service import (
    evidence_digest, material_signature, validate_freshness,
)


class ReviewConflict(ValueError):
    pass


class ReviewNotFound(ValueError):
    pass


def _json(value):
    return json.loads(json.dumps(value, default=lambda v: v.isoformat()))


def _ids(candidate_id, candidate_ids=None):
    ids = [int(candidate_id)] + [int(v) for v in (candidate_ids or [])]
    ids = sorted(set(ids))
    if len(ids) > 12 or any(v < 1 for v in ids):
        raise ValueError("Review harus memiliki 1–12 candidate.")
    return ids


def _load_review(connection, ids):
    statement = select(db.relationship_candidates_table).where(
        db.relationship_candidates_table.c.id.in_(ids)).order_by(db.relationship_candidates_table.c.id)
    rows = connection.execute(statement).mappings().all()
    if len(rows) != len(ids):
        raise ReviewNotFound("Candidate tidak ditemukan.")
    tables = sorted({r[s + "_table"] for r in rows for s in ("source", "target")})
    db.lock_relationship_tables(connection, tables)
    # Refresh after acquiring the same locks used by data/profile/analysis writers.
    rows = connection.execute(statement.with_for_update()).mappings().all()
    candidates = [db._serialize_relationship_candidate(r) for r in rows]
    if len({tuple(sorted((c["source_table"], c["target_table"]))) for c in candidates}) != 1:
        raise ValueError("Composite review harus menghubungkan dua tabel yang sama.")
    profiles = {(r["table_name"], r["column_name"]): db._serialize_profile_row(r)
                for r in connection.execute(select(db.column_profiles_table).where(
                    or_(*[(db.column_profiles_table.c.table_name == c[side + "_table"]) &
                          (db.column_profiles_table.c.column_name == c[side + "_column"])
                          for c in candidates for side in ("source", "target")]))).mappings()}
    versions = dict(connection.execute(select(db.table_state_table.c.table_name,
        db.table_state_table.c.data_version).where(db.table_state_table.c.table_name.in_(tables))).all())
    scores = {r["candidate_id"]: db._serialize_relationship_candidate_score(r)
              for r in connection.execute(select(db.relationship_candidate_scores_table).where(
                  db.relationship_candidate_scores_table.c.candidate_id.in_(ids))).mappings()}
    estimates = {r["candidate_id"]: db._serialize_relationship_cardinality_estimate(r)
                 for r in connection.execute(select(db.relationship_cardinality_estimates_table).where(
                     db.relationship_cardinality_estimates_table.c.candidate_id.in_(ids))).mappings()}
    masked = {table: db._relationship_masked_columns(table, connection=connection) for table in tables}
    inspector = inspect(connection)
    schema = {table: {col["name"]: str(col["type"]) for col in inspector.get_columns(table)}
              if inspector.has_table(table) else {} for table in tables}
    snapshots = []
    for candidate in candidates:
        score = scores.get(candidate["id"])
        estimate = estimates.get(candidate["id"])
        freshness = validate_freshness(candidate, profiles, versions, score, estimate)
        pair_profiles, columns = {}, {}
        for side in ("source", "target"):
            table, column = candidate[f"{side}_table"], candidate[f"{side}_column"]
            profile = profiles.get((table, column))
            # Review needs aggregate evidence, never fingerprint arrays or raw values.
            pair_profiles[side] = ({k: v for k, v in profile.items() if k != "value_fingerprint"}
                                   if profile else None)
            columns[side] = {"exists": column in schema[table],
                             "data_type": schema[table].get(column), "masked": column in masked[table]}
            if not columns[side]["exists"]:
                freshness["reasons"].append(f"{side}_column_missing")
        freshness["is_fresh"] = not freshness["reasons"]
        blockers = list(freshness["reasons"])
        if candidate["status"] not in {"pending", "stale"}:
            blockers.append("candidate_already_decided")
        if any(not p or p["sample_non_null_count"] < 2 for p in pair_profiles.values()):
            blockers.append("insufficient_profile_evidence")
        snapshots.append({"candidate": candidate, "profiles": pair_profiles, "columns": columns,
                          "data_versions": versions, "quality_score": score,
                          "cardinality_estimate": estimate, "freshness": freshness,
                          "approval_blockers": blockers})
    snapshots = _json(snapshots)
    return {"candidates": snapshots, "review_revision": evidence_digest(snapshots),
            "can_approve": all(not s["approval_blockers"] for s in snapshots)}


def get_candidate_review(candidate_id, candidate_ids=None):
    db.ensure_internal_tables()
    with db.engine.begin() as connection:
        return _load_review(connection, _ids(candidate_id, candidate_ids))


def _serialize_review(row):
    return _json(dict(row))


def get_candidate_review_history(candidate_id, limit=50, before_id=None):
    db.ensure_internal_tables()
    query = select(db.relationship_reviews_table).join(db.relationship_review_candidates_table,
        db.relationship_review_candidates_table.c.review_id == db.relationship_reviews_table.c.id).where(
            db.relationship_review_candidates_table.c.candidate_id == int(candidate_id))
    if before_id is not None:
        query = query.where(db.relationship_reviews_table.c.id < int(before_id))
    with db.engine.connect() as connection:
        rows = connection.execute(query.order_by(db.relationship_reviews_table.c.id.desc()).limit(
            max(1, min(int(limit), 200)))).mappings().all()
    return [_serialize_review(r) for r in rows]


def decide_candidate(candidate_id, decision, payload):
    if decision not in {"approved", "rejected"}:
        raise ValueError("Decision tidak valid.")
    db.ensure_internal_tables()
    ids = _ids(candidate_id, payload.get("candidate_ids"))
    reviewed_by = str(payload.get("reviewed_by") or "").strip()
    note = str(payload.get("review_note") or "").strip()
    request_key = str(payload.get("request_key") or "").strip()
    if not reviewed_by or len(reviewed_by) > 180 or not request_key or len(request_key) > 64 or len(note) > 4000:
        raise ValueError("Identitas reviewer, request key, atau panjang catatan tidak valid.")
    request_digest = evidence_digest({"anchor": int(candidate_id), "decision": decision, "payload": payload})
    with db.engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                               {"key": "relationship_review_request:" + request_key})
        previous = connection.execute(select(db.relationship_reviews_table).where(
            db.relationship_reviews_table.c.request_key == request_key)).mappings().one_or_none()
        if previous:
            if previous["request_digest"] != request_digest:
                raise ReviewConflict("Request key telah digunakan untuk keputusan berbeda.")
            return {"review": _serialize_review(previous), "replayed": True}
        detail = _load_review(connection, ids)
        if payload.get("expected_revision") != detail["review_revision"]:
            raise ReviewConflict("Evidence berubah sejak dibuka. Muat ulang review.")
        if any(s["candidate"]["status"] in {"promoted", "rejected"} for s in detail["candidates"]):
            raise ReviewConflict("Candidate sudah diputuskan. Muat ulang review.")
        if decision == "approved" and not detail["can_approve"]:
            raise ReviewConflict("Evidence belum lengkap atau stale. Jalankan analisis ulang sebelum approval.")
        if decision == "rejected" and not note:
            raise ValueError("Catatan alasan penolakan wajib diisi.")
        anchor = next(s for s in detail["candidates"] if s["candidate"]["id"] == int(candidate_id))
        source_table, target_table = (anchor["candidate"][s + "_table"] for s in ("source", "target"))
        pairs = []
        for snapshot in detail["candidates"]:
            c = snapshot["candidate"]
            reverse = c["source_table"] != source_table
            pairs.append({"source_column": c["target_column" if reverse else "source_column"],
                          "target_column": c["source_column" if reverse else "target_column"]})
        estimate = anchor["cardinality_estimate"] or {}
        cardinality = payload.get("cardinality") or estimate.get("estimated_cardinality")
        composite = len(pairs) > 1
        override = cardinality != estimate.get("estimated_cardinality")
        confirmation = {"composite": composite, "cardinality": cardinality,
                        "cardinality_overridden": override,
                        "composite_cardinality_confirmed": bool(payload.get("composite_cardinality_confirmed")),
                        "column_pairs": pairs, "source_table": source_table, "target_table": target_table}
        relationship_id = None
        if decision == "approved":
            if composite and not payload.get("composite_cardinality_confirmed"):
                raise ValueError("Konfirmasi cardinality composite wajib diberikan oleh reviewer.")
            if (composite or override) and not note:
                raise ValueError("Catatan alasan cardinality composite/override wajib diisi.")
            if cardinality not in db.RELATIONSHIP_CARDINALITIES:
                raise ValueError("Cardinality tidak valid.")
            try:
                relationship = db.create_table_relationship(
                    relationship_name=payload.get("relationship_name"),
                    source_table=source_table, target_table=target_table,
                    column_pairs=pairs, cardinality=cardinality, connection=connection)
            except ValueError as error:
                raise ReviewConflict(str(error)) from error
            relationship_id = relationship["id"]
        result = connection.execute(db.relationship_reviews_table.insert().values(
            request_key=request_key, request_digest=request_digest, reviewed_by=reviewed_by,
            reviewer_source="self_declared", review_note=note, decision=decision,
            promoted_relationship_id=relationship_id, snapshot=detail, confirmation=confirmation))
        review_id = int(result.inserted_primary_key[0])
        connection.execute(db.relationship_review_candidates_table.insert(), [
            {"review_id": review_id, "candidate_id": s["candidate"]["id"],
             "material_signature": material_signature(s["candidate"])} for s in detail["candidates"]])
        connection.execute(db.relationship_candidates_table.update().where(
            db.relationship_candidates_table.c.id.in_(ids)).values(
                status="promoted" if decision == "approved" else "rejected"))
        row = connection.execute(select(db.relationship_reviews_table).where(
            db.relationship_reviews_table.c.id == review_id)).mappings().one()
        return {"review": _serialize_review(row), "replayed": False}
