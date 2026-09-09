# 6E SPEC — Backend Query Preview & Validation

Tanggal: 9 September 2026
Project: Tools Pengawas
Branch: `feature/vibe-ui`

## Posisi Bab 6

- [x] 6A — Schema Review
- [x] 6B — Relationship Metadata
- [x] 6B.1 — Composite Relationship
- [x] 6B.2 — Relationship Intelligence
- [x] 6C — Visual Relationship Designer
- [x] 6D — Visual SQL Builder
- [ ] 6E — Backend Query Preview & Validation
  - [ ] 6E.1 — Structured Query Plan
  - [ ] 6E.2 — Query Validator
  - [ ] 6E.3 — Safe SQL Compiler
  - [ ] 6E.4 — Cost / Impact Validation
- [ ] 6F — Data Preview
- [ ] 6G — Create Derived Table
- [ ] 6H — Lineage + Refresh

## Goal

Move query execution authority from frontend-generated SQL strings to a backend-owned,
validated, structured query plan.

Target flow:

```text
Visual SQL Builder
        ↓
Structured Query Plan
        ↓
Backend Validation
        ↓
Safe SQL Compiler
        ↓
EXPLAIN (FORMAT JSON)
        ↓
Warnings / Cost / Estimated Rows
        ↓
6F Data Preview
```

## 6E.1 Structured Query Plan

Frontend must not send raw executable SQL.

Example request:

```json
{
  "base_table": "0016",
  "joins": [
    {
      "relationship_id": 12,
      "join_type": "LEFT JOIN"
    }
  ],
  "columns": [
    {
      "table": "0016",
      "column": "bank_id",
      "alias": "0016__bank_id"
    }
  ]
}
```

Recommended join allowlist:

```text
INNER JOIN
LEFT JOIN
RIGHT JOIN
FULL OUTER JOIN
LEFT ANTI JOIN
RIGHT ANTI JOIN
FULL ANTI JOIN
```

No CROSS JOIN.
No arbitrary expressions.
No raw SQL fragments.

## 6E.2 Query Validator

Backend must validate:

```text
table exists
table is user-visible / not internal metadata
column exists
relationship exists
relationship is active
relationship is fresh / valid for use
join path extends the current graph correctly
composite key is complete
join type is allowlisted
selected columns exist
output aliases are unique
masked columns cannot be returned as output
masked columns may be used internally for JOIN predicates
no CROSS JOIN
no raw SQL
no raw expression
plan size within configured limits
```

Only active approved relationship metadata may be used for validated execution.

## 6E.3 Safe SQL Compiler

Backend compiles the structured plan.

Composite relationship example:

```sql
ON t1."bank_id" = t2."bank_id"
AND t1."bulan" = t2."bulan"
AND t1."tahun" = t2."tahun"
```

Use strict identifier quoting / SQLAlchemy-safe identifier handling.

Do not concatenate arbitrary client-provided SQL.

### Anti Join Semantics

Do not implement complex anti joins by appending all null filters to one final WHERE clause.

Treat each join as a relational step:

```text
step_0 = base table
step_1 = normal join
step_2 = anti join
step_3 = next join
```

Use CTE/subquery/nested relational compilation where needed so:

```text
LEFT ANTI
RIGHT ANTI
FULL ANTI
```

retain correct semantics in multi-step plans.

## 6E.4 Cost / Impact Validation

Before any row preview, run:

```sql
EXPLAIN (FORMAT JSON)
```

Do not use:

```sql
EXPLAIN ANALYZE
```

at this stage.

Extract where practical:

```text
estimated rows
estimated total cost
join type
sequential scan presence
plan node count
```

Generate warnings for:

```text
many-to-many join expansion
high estimated row multiplication
large sequential scan
expensive estimated plan
stale/invalid relationship metadata
high join count
large output-column count
```

## Initial Guardrails

Make configurable via environment/settings.

Suggested starting values:

```text
max joins              = 12
max selected columns   = 200
max relationships/plan = 12
raw SQL                = prohibited
cross join             = prohibited
statement timeout      = backend-controlled
```

## Proposed API

### POST /query-builder/validate

Returns:

```json
{
  "valid": true,
  "warnings": [],
  "estimated_cost": 1234.5,
  "estimated_rows": 50000,
  "plan_summary": {}
}
```

### POST /query-builder/compile

Returns:

```json
{
  "valid": true,
  "generated_sql": "...",
  "warnings": [],
  "plan_summary": {}
}
```

No business data rows are returned in 6E.
That starts in 6F.

## Security Rules

- Frontend cannot execute arbitrary SQL.
- Internal metadata tables cannot be selected as business tables.
- Masked columns cannot be exposed in output.
- Masked columns may be used internally for JOIN predicates if required.
- Relationship must be active and approved.
- Identifier names must be validated and safely quoted.
- Statement timeout must be backend controlled.
- No write SQL.
- Only SELECT-style compilation is allowed.

## Big-Data Principles

- Validation should be metadata-first.
- Avoid full-table scans during validation.
- Use PostgreSQL planner estimates through EXPLAIN.
- Do not calculate exact COUNT(*) during 6E.
- Avoid blocking UI with expensive analysis.
- Keep query execution concerns isolated in a dedicated service layer.

Suggested backend structure:

```text
backend/services/
├── query_plan_service.py
├── query_validation_service.py
├── query_compiler_service.py
└── query_cost_service.py
```

Exact filenames may be adjusted after inspecting current repository structure.

## Testing Requirements

Backend tests should cover:

```text
valid single-table query
valid composite-key join
invalid table
internal metadata table
invalid column
masked output column
masked join-key allowed
inactive relationship
stale relationship
invalid join path
duplicate alias
unsupported join type
join limit
column limit
INNER JOIN
LEFT JOIN
RIGHT JOIN
FULL OUTER JOIN
LEFT ANTI JOIN
RIGHT ANTI JOIN
FULL ANTI JOIN
multi-step anti join semantics
reverse relationship direction
EXPLAIN parsing
statement timeout behavior
```

Frontend regression:

```text
Visual SQL Builder still renders
existing SQL preview still works
current join-type selector preserved
Relationship Designer preserved
Human Approval preserved
frozen header preserved
auto-collapse sidebar preserved
```

## Completion Definition

6E is complete when:

```text
frontend sends structured plan
backend validates plan
backend safely compiles SQL
backend runs EXPLAIN only
backend returns validation + cost warnings
no business rows returned yet
no raw SQL execution from client
```

Then continue to:

```text
6F — Data Preview
```
