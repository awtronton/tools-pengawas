# CODEX HANDOFF — Tools Pengawas

Tanggal: 9 September 2026  
Branch development: `feature/vibe-ui`

## Posisi Bab 6

- [x] 6A — Schema Review
- [x] 6B — Relationship Metadata
- [x] 6B.1 — Composite Relationship
- [ ] 6B.2 — Relationship Intelligence
  - [x] 6B.2.1 — Column Profiling Layer
  - [x] 6B.2.2 — Candidate Relationship Generator
  - [x] 6B.2.3 — Relationship Scoring
  - [x] 6B.2.4 — Cardinality Estimation
  - [ ] 6B.2.5 — Human Approval ← NEXT
- [x] 6C — Visual Relationship Designer
- [x] 6D — Visual SQL Builder
- [x] 6D.1 — Left/Right Anti Join
- [x] 6D.2 — Full Anti Join
- [ ] 6E — Backend Query Preview & Validation
- [ ] 6F — Data Preview
- [ ] 6G — Create Derived Table
- [ ] 6H — Lineage + Refresh

## Current architecture

Frontend:
- React + Vite
- Monday/Vibe-inspired UI
- `@xyflow/react`
- `elkjs`

Backend:
- FastAPI
- SQLAlchemy
- PostgreSQL

Important database/system metadata:
- `warehouse_schema_mapping`
- `warehouse_column_settings`
- `warehouse_table_relationships`
- `warehouse_relationship_columns`
- `warehouse_column_profiles`
- `warehouse_profile_jobs`
- `warehouse_table_state`
- `warehouse_relationship_candidates`
- `warehouse_relationship_candidate_jobs`
- `warehouse_relationship_candidate_scores`
- `warehouse_relationship_scoring_jobs`
- `warehouse_relationship_cardinality_estimates`
- `warehouse_relationship_cardinality_jobs`

## Current UI state — preserve

Do not redesign shell unless explicitly requested.

Current shell:
- divider between sidebar/header/body removed;
- breadcrumb/path tracker is on the right side of frozen header;
- global search is an icon that opens an animated popover;
- page title is frozen in header;
- small gray badge + description are under page title in frozen header;
- redundant category text such as `DATA WAREHOUSE` removed from body;
- desktop sidebar auto-expands on pointer enter and auto-collapses on pointer leave;
- Workspace Switcher is preserved;
- minimum UI font target is 11px.

Do not overwrite unrelated:
- `DashboardLayout.jsx`
- `WorkspacePageHeader.jsx`
- `vibe-shell.css`
unless the requested task actually requires them.

## Relationship foundation

Relationship supports composite keys, e.g.:

```text
bank_id ↔ bank_id
bulan   ↔ bulan
tahun   ↔ tahun
```

Visual SQL Builder should generate:

```sql
ON t1."bank_id" = t2."bank_id"
AND t1."bulan" = t2."bulan"
AND t1."tahun" = t2."tahun"
```

Relationship metadata is semantic metadata, not PostgreSQL physical foreign keys.

## Relationship Intelligence — big-data principles

The system is being designed for large future warehouse volumes.

Principles:
- avoid brute-force full warehouse scans;
- metadata-first;
- asynchronous jobs;
- adaptive sampling/profiling;
- version/stale protection;
- hard limits on candidate/job size;
- no raw sample values stored when fingerprints are sufficient;
- candidate detection/scoring/cardinality should use profile metadata wherever possible.

### 6B.2.1 Column Profiling

Implemented:
- `warehouse_column_profiles`
- async profiling jobs
- adaptive sample strategy
- stale/data-version tracking
- fingerprinting
- no raw sample-value persistence
- profiling job recovery after restart

### 6B.2.2 Candidate Generator

Implemented:
- metadata-only candidate generation
- inverted indexes
- candidate job queue
- candidate stale invalidation
- existing relationship protection
- hard pair-evaluation limits

### 6B.2.3 Relationship Scoring

Implemented:
- discovery score is separate from quality/confidence score
- asynchronous scoring
- confidence levels
- quality flags
- metadata-only
- candidate API enriched with `quality_score`

### 6B.2.4 Cardinality Estimation

Implemented:
- `1:1`, `1:N`, `N:1`, `N:N`
- metadata-only
- uses profiling statistics
- sampled uniqueness treated conservatively
- many-to-many expansion warning
- candidate API enriched with `cardinality_estimate`

## Next task — 6B.2.5 Human Approval

Goal:
Create a human-review workflow that combines:
- candidate discovery evidence;
- quality/confidence score;
- cardinality estimate;
- quality flags;
- profile freshness/stale state.

Required behavior:
1. Reviewer can inspect a candidate.
2. Reviewer can approve or reject.
3. Approval promotes the candidate into active relationship metadata.
4. Approval must support composite relationships where applicable.
5. Do not auto-promote without user approval.
6. Reject should remain auditable and prevent immediate repeated recommendation unless data/profile materially changes.
7. Preserve candidate/score/cardinality lineage.
8. Stale candidates must not be approvable without re-analysis.
9. Existing/reverse duplicate relationships must remain protected.
10. Do not bypass column masking or other security behavior.
11. Keep backend scalable and metadata-first.
12. Avoid unrelated UI/layout changes.

Suggested workflow states:

```text
pending
reviewing
approved
rejected
promoted
stale
```

Suggested metadata/audit fields:
- reviewed_by
- reviewed_at
- review_note
- decision
- promoted_relationship_id
- candidate_detector_version
- profile/data versions used for decision

## Instructions to Codex before editing

1. Inspect the current workspace and Git diff.
2. Read existing implementations for:
   - profiling;
   - relationship candidate generation;
   - relationship scoring;
   - cardinality estimation;
   - relationship create/update/delete.
3. Verify existing API contracts before changing them.
4. Propose the smallest coherent implementation plan for 6B.2.5.
5. Preserve backward compatibility.
6. Run backend syntax/tests and frontend build/lint where available.
7. Show a concise summary of files changed and tests performed.
8. Do not commit automatically unless explicitly asked.

## After 6B.2.5

Continue:

```text
6E — Backend Query Preview & Validation
6F — Data Preview
6G — Create Derived Table
6H — Lineage + Refresh
```

For 6E, do not execute raw SQL received from the frontend. The backend should receive a structured query plan and validate tables, columns, relationships, join types, masking, identifiers, and limits before executing a SELECT.
