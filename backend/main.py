import json
from io import BytesIO

import pandas as pd
from pydantic import BaseModel
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from database.table_service import (
    append_existing_table,
    count_period_rows,
    create_new_table,
    create_table_relationship,
    delete_table_relationship,
    get_all_tables,
    get_all_table_summaries,
    get_schema_mapping,
    get_table_column_details,
    get_table_explorer_options,
    get_table_relationships,
    get_table_summary,
    explore_table_data,
    rename_table_column,
    set_column_masking,
    update_table_relationship,
    replace_period_data,
    require_schema_mapping,
)
from master_data.banks import (
    get_all_banks,
    get_bank_by_name,
)
from services.excel_processor import (
    get_excel_sheets,
    process_excel,
)
from services.profiling_service import (
    get_profile_job_status,
    get_table_profile_snapshot,
    list_profile_jobs,
    queue_profile_job,
    recover_profile_queue,
)
from services.relationship_scoring_service import (
    get_relationship_scoring_job_status,
    list_relationship_scoring_jobs,
    queue_relationship_scoring_job,
    recover_relationship_scoring_queue,
)
from services.relationship_cardinality_service import (
    get_relationship_cardinality_job_status,
    list_relationship_cardinality_jobs,
    queue_relationship_cardinality_job,
    recover_relationship_cardinality_queue,
)
from services.relationship_intelligence_service import (
    get_relationship_candidate_job_status,
    list_relationship_candidate_jobs,
    list_relationship_candidates,
    queue_relationship_candidate_job,
    recover_relationship_candidate_queue,
)


app = FastAPI(
    title="OJK Data Warehouse API",
    version="1.6.0",
)


# =====================================================
# CORS
# =====================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================
# HELPERS
# =====================================================

SYSTEM_COLUMNS = {"bank_id", "bulan", "tahun"}


class RenameColumnRequest(BaseModel):
    old_name: str
    new_name: str


class ColumnMaskingRequest(BaseModel):
    column_name: str
    masked: bool



class RelationshipColumnPairRequest(BaseModel):
    source_column: str
    target_column: str


class RelationshipCreateRequest(BaseModel):
    relationship_name: str | None = None
    source_table: str
    source_column: str | None = None
    target_table: str
    target_column: str | None = None
    column_pairs: list[RelationshipColumnPairRequest] | None = None
    cardinality: str


class RelationshipUpdateRequest(BaseModel):
    relationship_name: str | None = None
    cardinality: str | None = None
    is_active: bool | None = None


class ProfilingJobCreateRequest(BaseModel):
    table_name: str
    columns: list[str] | None = None
    target_sample_rows: int = 50000
    profile_strategy: str = "adaptive"


class RelationshipCandidateJobCreateRequest(BaseModel):
    scan_mode: str = "selected"
    source_tables: list[str] | None = None
    target_tables: list[str] | None = None
    min_discovery_score: float = 0.45
    max_candidates: int = 1000
    include_system_columns: bool = True


class RelationshipScoringJobCreateRequest(BaseModel):
    source_tables: list[str] | None = None
    target_tables: list[str] | None = None
    candidate_status: str = "pending"
    min_discovery_score: float = 0.45
    max_candidates: int = 5000


class RelationshipCardinalityJobCreateRequest(BaseModel):
    source_tables: list[str] | None = None
    target_tables: list[str] | None = None
    candidate_status: str = "pending"
    min_discovery_score: float = 0.45
    min_quality_score: float = 0.55
    max_candidates: int = 5000


def dataframe_to_records(df):
    return json.loads(
        df.to_json(
            orient="records",
            date_format="iso",
        )
    )


def parse_json_list(value: str, field_name: str):
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Format {field_name} tidak valid."
        ) from error

    if not isinstance(parsed, list):
        raise ValueError(
            f"{field_name} harus berupa array JSON."
        )

    return parsed


def parse_json_dict(value: str, field_name: str):
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Format {field_name} tidak valid."
        ) from error

    if not isinstance(parsed, dict):
        raise ValueError(
            f"{field_name} harus berupa object JSON."
        )

    return parsed


def clean_existing_value(value):
    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")

    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, str):
        value = value.strip()
        return value if value else None

    return value


def attach_bank_id(df, bank_name: str):
    bank = get_bank_by_name(bank_name)

    if "bank_id" in df.columns:
        raise ValueError(
            "File sumber sudah memiliki kolom 'bank_id'. "
            "Nama tersebut dicadangkan sebagai kolom sistem."
        )

    df = df.copy()
    df.insert(0, "bank_id", bank["bank_id"])

    return df, bank


def process_existing_excel(
    *,
    file_bytes: bytes,
    table_name: str,
    sheet_name: str,
    first_data_row: int,
    month: int,
    year: int,
):
    """
    Existing table:
    - tidak membaca header dari file;
    - data dimulai dari first_data_row;
    - nama kolom mengikuti schema mapping tabel existing;
    - mapping dilakukan berdasarkan ordinal/urutan kolom.
    """
    if not first_data_row or int(first_data_row) < 1:
        raise ValueError(
            "Baris pertama data minimal bernilai 1."
        )

    mapping = require_schema_mapping(table_name)

    expected_columns = [
        item["database_column"]
        for item in mapping
    ]

    df = pd.read_excel(
        BytesIO(file_bytes),
        sheet_name=sheet_name,
        header=None,
        skiprows=int(first_data_row) - 1,
        dtype=object,
    )

    # Hanya buang row/column yang benar-benar kosong seluruhnya.
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")
    df = df.reset_index(drop=True)

    actual_column_count = len(df.columns)
    expected_column_count = len(expected_columns)

    if actual_column_count != expected_column_count:
        raise ValueError(
            "Struktur file tidak sesuai dengan schema tabel "
            f"'{table_name}'. Tabel membutuhkan "
            f"{expected_column_count} kolom data, sedangkan file "
            f"menghasilkan {actual_column_count} kolom setelah "
            "kolom kosong dibersihkan. Periksa Baris Pertama Data "
            "atau perubahan format file."
        )

    # Header preview dan save mengikuti database, bukan header XLS.
    df.columns = expected_columns

    for column in df.columns:
        df[column] = df[column].map(
            clean_existing_value
        )

    df["bulan"] = int(month)
    df["tahun"] = int(year)

    return df


def process_upload_by_mode(
    *,
    file_bytes: bytes,
    table_mode: str,
    table_name: str,
    sheet_name: str,
    header_row: int | None,
    first_data_row: int | None,
    month: int,
    year: int,
):
    if table_mode == "new":
        if not header_row or int(header_row) < 1:
            raise ValueError(
                "Baris Header wajib diisi untuk tabel baru."
            )

        return process_excel(
            file_bytes=file_bytes,
            sheet_name=sheet_name,
            header_row=int(header_row),
            month=month,
            year=year,
        )

    if table_mode == "existing":
        return process_existing_excel(
            file_bytes=file_bytes,
            table_name=table_name,
            sheet_name=sheet_name,
            first_data_row=int(
                first_data_row or 0
            ),
            month=month,
            year=year,
        )

    raise ValueError(
        "table_mode harus bernilai 'new' atau 'existing'."
    )


# =====================================================
# PROFILING RUNTIME
# =====================================================

@app.on_event("startup")
def recover_warehouse_profiling_queue():
    try:
        recovered = recover_profile_queue()
        if recovered:
            print(
                f"Recovered {recovered} profiling job(s)."
            )
    except Exception as error:
        print(
            "WARNING profiling queue recovery:",
            repr(error),
        )


@app.on_event("startup")
def recover_relationship_intelligence_queue():
    try:
        recovered = recover_relationship_candidate_queue()
        if recovered:
            print(
                f"Recovered {recovered} relationship candidate job(s)."
            )
    except Exception as error:
        print(
            "WARNING relationship candidate queue recovery:",
            repr(error),
        )


@app.on_event("startup")
def recover_relationship_scoring_runtime():
    try:
        recovered = recover_relationship_scoring_queue()
        if recovered:
            print(f"Recovered {recovered} relationship scoring job(s).")
    except Exception as error:
        print("WARNING relationship scoring queue recovery:", repr(error))


@app.on_event("startup")
def recover_relationship_cardinality_runtime():
    try:
        recovered = recover_relationship_cardinality_queue()
        if recovered:
            print(
                f"Recovered {recovered} relationship cardinality job(s)."
            )
    except Exception as error:
        print(
            "WARNING relationship cardinality queue recovery:",
            repr(error),
        )


# =====================================================
# HEALTH CHECK
# =====================================================

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "OJK Data Warehouse API running",
    }


# =====================================================
# DATABASE TABLES
# =====================================================

@app.get("/tables")
def list_tables():
    try:
        tables = get_all_tables()

        return {
            "status": "success",
            "count": len(tables),
            "tables": tables,
        }

    except Exception as error:
        print(
            "ERROR /tables:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.get("/tables-summary")
def table_summaries():
    try:
        summaries = get_all_table_summaries()

        return {
            "status": "success",
            "count": len(summaries),
            "tables": summaries,
        }

    except Exception as error:
        print(
            "ERROR /tables-summary:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.get("/tables/{table_name}/detail")
def table_detail(table_name: str):
    try:
        summary = get_table_summary(table_name)
        columns = get_table_column_details(table_name)

        return {
            "status": "success",
            "summary": summary,
            "columns": columns,
        }

    except Exception as error:
        print(
            "ERROR /tables/{table_name}/detail:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.patch("/tables/{table_name}/column")
def rename_column(
    table_name: str,
    payload: RenameColumnRequest,
):
    try:
        result = rename_table_column(
            table_name=table_name,
            old_name=payload.old_name,
            new_name=payload.new_name,
        )

        return {
            "status": "success",
            "message": "Nama kolom berhasil diperbarui.",
            **result,
        }

    except Exception as error:
        print(
            "ERROR PATCH /tables/{table_name}/column:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.patch("/tables/{table_name}/column-masking")
def update_column_masking(
    table_name: str,
    payload: ColumnMaskingRequest,
):
    try:
        result = set_column_masking(
            table_name=table_name,
            column_name=payload.column_name,
            masked=payload.masked,
        )

        return {
            "status": "success",
            "message": (
                "Masking kolom berhasil diperbarui."
            ),
            **result,
        }

    except Exception as error:
        print(
            "ERROR PATCH /tables/{table_name}/column-masking:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# =====================================================
# COLUMN PROFILING
# =====================================================

@app.post("/profiling/jobs")
def create_profiling_job(
    payload: ProfilingJobCreateRequest,
):
    try:
        result = queue_profile_job(
            table_name=payload.table_name,
            columns=payload.columns,
            target_sample_rows=(
                payload.target_sample_rows
            ),
            profile_strategy=(
                payload.profile_strategy
            ),
        )

        return {
            "status": "success",
            **result,
        }

    except Exception as error:
        print(
            "ERROR POST /profiling/jobs:",
            repr(error),
        )
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.get("/profiling/jobs")
def profiling_jobs(
    table_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    try:
        rows = list_profile_jobs(
            table_name=table_name,
            limit=limit,
        )
        return {
            "status": "success",
            "count": len(rows),
            "jobs": rows,
        }
    except Exception as error:
        print(
            "ERROR GET /profiling/jobs:",
            repr(error),
        )
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.get("/profiling/jobs/{job_id}")
def profiling_job(job_id: int):
    try:
        job = get_profile_job_status(job_id)
        return {
            "status": "success",
            "job": job,
        }
    except Exception as error:
        print(
            "ERROR GET /profiling/jobs/{job_id}:",
            repr(error),
        )
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.get("/profiling/tables/{table_name}")
def table_profile(table_name: str):
    try:
        snapshot = get_table_profile_snapshot(
            table_name
        )
        return {
            "status": "success",
            **snapshot,
        }
    except Exception as error:
        print(
            "ERROR GET /profiling/tables/{table_name}:",
            repr(error),
        )
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )



# =====================================================
# RELATIONSHIP INTELLIGENCE — CANDIDATE GENERATOR
# =====================================================

@app.post("/relationship-intelligence/candidate-jobs")
def create_relationship_candidate_job(
    payload: RelationshipCandidateJobCreateRequest,
):
    try:
        result = queue_relationship_candidate_job(
            scan_mode=payload.scan_mode,
            source_tables=payload.source_tables,
            target_tables=payload.target_tables,
            min_discovery_score=payload.min_discovery_score,
            max_candidates=payload.max_candidates,
            include_system_columns=payload.include_system_columns,
        )
        return {
            "status": "success",
            **result,
        }
    except Exception as error:
        print(
            "ERROR POST /relationship-intelligence/candidate-jobs:",
            repr(error),
        )
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.get("/relationship-intelligence/candidate-jobs")
def relationship_candidate_jobs(
    limit: int = Query(50, ge=1, le=200),
):
    try:
        rows = list_relationship_candidate_jobs(limit=limit)
        return {
            "status": "success",
            "count": len(rows),
            "jobs": rows,
        }
    except Exception as error:
        print(
            "ERROR GET /relationship-intelligence/candidate-jobs:",
            repr(error),
        )
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.get("/relationship-intelligence/candidate-jobs/{job_id}")
def relationship_candidate_job(job_id: int):
    try:
        job = get_relationship_candidate_job_status(job_id)
        return {
            "status": "success",
            "job": job,
        }
    except Exception as error:
        print(
            "ERROR GET /relationship-intelligence/candidate-jobs/{job_id}:",
            repr(error),
        )
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.get("/relationship-intelligence/candidates")
def relationship_candidates(
    source_table: str | None = Query(None),
    target_table: str | None = Query(None),
    candidate_status: str | None = Query(None, alias="status"),
    include_stale: bool = Query(False),
    min_discovery_score: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(200, ge=1, le=2000),
):
    try:
        rows = list_relationship_candidates(
            source_table=source_table,
            target_table=target_table,
            status=candidate_status,
            include_stale=include_stale,
            min_discovery_score=min_discovery_score,
            limit=limit,
        )
        return {
            "status": "success",
            "count": len(rows),
            "candidates": rows,
        }
    except Exception as error:
        print(
            "ERROR GET /relationship-intelligence/candidates:",
            repr(error),
        )
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )



# =====================================================
# RELATIONSHIP INTELLIGENCE — QUALITY SCORING
# =====================================================

@app.post("/relationship-intelligence/scoring-jobs")
def create_relationship_scoring_job(payload: RelationshipScoringJobCreateRequest):
    try:
        result = queue_relationship_scoring_job(
            source_tables=payload.source_tables, target_tables=payload.target_tables,
            candidate_status=payload.candidate_status, min_discovery_score=payload.min_discovery_score,
            max_candidates=payload.max_candidates,
        )
        return {"status":"success", **result}
    except Exception as error:
        print("ERROR POST /relationship-intelligence/scoring-jobs:", repr(error))
        raise HTTPException(status_code=400, detail=str(error))

@app.get("/relationship-intelligence/scoring-jobs")
def relationship_scoring_jobs(limit: int = Query(50, ge=1, le=200)):
    try:
        rows=list_relationship_scoring_jobs(limit=limit)
        return {"status":"success","count":len(rows),"jobs":rows}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))

@app.get("/relationship-intelligence/scoring-jobs/{job_id}")
def relationship_scoring_job(job_id: int):
    try:
        return {"status":"success","job":get_relationship_scoring_job_status(job_id)}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


# =====================================================
# RELATIONSHIP INTELLIGENCE — CARDINALITY ESTIMATION
# =====================================================

@app.post("/relationship-intelligence/cardinality-jobs")
def create_relationship_cardinality_job(
    payload: RelationshipCardinalityJobCreateRequest,
):
    try:
        result = queue_relationship_cardinality_job(
            source_tables=payload.source_tables,
            target_tables=payload.target_tables,
            candidate_status=payload.candidate_status,
            min_discovery_score=payload.min_discovery_score,
            min_quality_score=payload.min_quality_score,
            max_candidates=payload.max_candidates,
        )
        return {"status": "success", **result}
    except Exception as error:
        print(
            "ERROR POST /relationship-intelligence/cardinality-jobs:",
            repr(error),
        )
        raise HTTPException(status_code=400, detail=str(error))


@app.get("/relationship-intelligence/cardinality-jobs")
def relationship_cardinality_jobs(
    limit: int = Query(50, ge=1, le=200),
):
    try:
        rows = list_relationship_cardinality_jobs(limit=limit)
        return {"status": "success", "count": len(rows), "jobs": rows}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.get("/relationship-intelligence/cardinality-jobs/{job_id}")
def relationship_cardinality_job(job_id: int):
    try:
        return {
            "status": "success",
            "job": get_relationship_cardinality_job_status(job_id),
        }
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


# =====================================================
# TABLE RELATIONSHIPS
# =====================================================

@app.get("/relationships")
def relationships(
    table_name: str | None = Query(None),
):
    try:
        rows = get_table_relationships(
            table_name=table_name
        )

        return {
            "status": "success",
            "count": len(rows),
            "relationships": rows,
        }

    except Exception as error:
        print(
            "ERROR GET /relationships:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.post("/relationships")
def create_relationship(
    payload: RelationshipCreateRequest,
):
    try:
        result = create_table_relationship(
            relationship_name=(
                payload.relationship_name
            ),
            source_table=payload.source_table,
            source_column=payload.source_column,
            target_table=payload.target_table,
            target_column=payload.target_column,
            column_pairs=[
                {
                    "source_column":
                        pair.source_column,
                    "target_column":
                        pair.target_column,
                }
                for pair in (
                    payload.column_pairs or []
                )
            ] or None,
            cardinality=payload.cardinality,
        )

        return {
            "status": "success",
            "message": (
                "Relationship berhasil dibuat."
            ),
            "relationship": result,
        }

    except Exception as error:
        print(
            "ERROR POST /relationships:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.patch("/relationships/{relationship_id}")
def update_relationship(
    relationship_id: int,
    payload: RelationshipUpdateRequest,
):
    try:
        result = update_table_relationship(
            relationship_id,
            relationship_name=(
                payload.relationship_name
            ),
            cardinality=(
                payload.cardinality
            ),
            is_active=payload.is_active,
        )

        return {
            "status": "success",
            "message": (
                "Relationship berhasil diperbarui."
            ),
            "relationship": result,
        }

    except Exception as error:
        print(
            "ERROR PATCH /relationships/{relationship_id}:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.delete("/relationships/{relationship_id}")
def delete_relationship(
    relationship_id: int,
):
    try:
        result = delete_table_relationship(
            relationship_id
        )

        return {
            "status": "success",
            "message": (
                "Relationship berhasil dihapus."
            ),
            **result,
        }

    except Exception as error:
        print(
            "ERROR DELETE /relationships/{relationship_id}:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.get("/tables/{table_name}/explorer/options")
def table_explorer_options(table_name: str):
    try:
        result = get_table_explorer_options(
            table_name
        )

        return {
            "status": "success",
            **result,
        }

    except Exception as error:
        print(
            "ERROR /tables/{table_name}/explorer/options:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.get("/tables/{table_name}/explorer")
def table_explorer(
    table_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(
        20,
        ge=1,
        le=200,
    ),
    search: str | None = Query(None),
    bank_id: str | None = Query(None),
    month: int | None = Query(
        None,
        ge=1,
        le=12,
    ),
    year: int | None = Query(
        None,
        ge=1900,
        le=2200,
    ),
    sort_column: str | None = Query(None),
    sort_direction: str = Query("asc"),
):
    try:
        result = explore_table_data(
            table_name,
            page=page,
            page_size=page_size,
            search=search,
            bank_id=bank_id,
            month=month,
            year=year,
            sort_column=sort_column,
            sort_direction=sort_direction,
        )

        return {
            "status": "success",
            **result,
        }

    except Exception as error:
        print(
            "ERROR /tables/{table_name}/explorer:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.get("/tables/{table_name}/schema-mapping")
def table_schema_mapping(table_name: str):
    try:
        mapping = get_schema_mapping(
            table_name
        )

        return {
            "status": "success",
            "table_name": table_name,
            "count": len(mapping),
            "mapping": mapping,
        }

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# =====================================================
# MASTER BANKS
# =====================================================

@app.get("/banks")
def list_banks():
    try:
        banks = get_all_banks()

        return {
            "status": "success",
            "count": len(banks),
            "banks": banks,
        }

    except Exception as error:
        print(
            "ERROR /banks:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# =====================================================
# EXCEL SHEETS
# =====================================================

@app.post("/excel/sheets")
async def detect_sheets(
    file: UploadFile = File(...),
):
    try:
        file_bytes = await file.read()

        sheets = get_excel_sheets(
            file_bytes
        )

        return {
            "filename": file.filename,
            "sheets": sheets,
        }

    except Exception as error:
        print(
            "ERROR /excel/sheets:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# =====================================================
# PREVIEW EXCEL
# =====================================================

@app.post("/excel/preview")
async def preview_excel(
    file: UploadFile = File(...),
    table_mode: str = Form(...),
    table_name: str = Form(...),
    bank_name: str = Form(...),
    month: int = Form(...),
    year: int = Form(...),
    sheet_name: str = Form(...),
    header_row: int | None = Form(None),
    first_data_row: int | None = Form(None),
):
    try:
        table_mode = table_mode.strip().lower()

        file_bytes = await file.read()

        df = process_upload_by_mode(
            file_bytes=file_bytes,
            table_mode=table_mode,
            table_name=table_name,
            sheet_name=sheet_name,
            header_row=header_row,
            first_data_row=first_data_row,
            month=month,
            year=year,
        )

        df, bank = attach_bank_id(
            df,
            bank_name,
        )

        df = df.reset_index(drop=True)
        df.insert(
            0,
            "__row_id",
            range(1, len(df) + 1),
        )

        preview = dataframe_to_records(df)

        database_columns = [
            str(column)
            for column in df.columns
            if column != "__row_id"
        ]

        return {
            "status": "success",
            "filename": file.filename,
            "table_mode": table_mode,
            "table_name": table_name,
            "bank_name": bank["bank_name"],
            "bank_id": bank["bank_id"],
            "month": month,
            "year": year,
            "sheet_name": sheet_name,
            "header_row": (
                header_row
                if table_mode == "new"
                else None
            ),
            "first_data_row": (
                first_data_row
                if table_mode == "existing"
                else None
            ),
            "row_count": len(df),
            "column_count": len(
                database_columns
            ),
            "columns": database_columns,
            "preview": preview,
        }

    except Exception as error:
        print(
            "ERROR /excel/preview:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# =====================================================
# CHECK EXISTING PERIOD
# =====================================================

@app.post("/excel/check-period")
async def check_excel_period(
    table_name: str = Form(...),
    bank_name: str = Form(...),
    month: int = Form(...),
    year: int = Form(...),
):
    try:
        bank = get_bank_by_name(
            bank_name
        )

        row_count = count_period_rows(
            table_name=table_name,
            bank_id=bank["bank_id"],
            month=month,
            year=year,
        )

        return {
            "status": "success",
            "table_name": table_name,
            "bank_name": bank["bank_name"],
            "bank_id": bank["bank_id"],
            "month": month,
            "year": year,
            "exists": row_count > 0,
            "row_count": row_count,
        }

    except Exception as error:
        print(
            "ERROR /excel/check-period:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# =====================================================
# SAVE EXCEL TO DATABASE
# =====================================================

@app.post("/excel/save")
async def save_excel(
    file: UploadFile = File(...),
    table_mode: str = Form(...),
    table_name: str = Form(...),
    bank_name: str = Form(...),
    month: int = Form(...),
    year: int = Form(...),
    sheet_name: str = Form(...),
    header_row: int | None = Form(None),
    first_data_row: int | None = Form(None),
    deleted_rows: str = Form("[]"),
    column_mapping: str = Form("{}"),
    duplicate_action: str = Form("block"),
):
    try:
        table_mode = table_mode.strip().lower()

        if table_mode not in {
            "new",
            "existing",
        }:
            raise ValueError(
                "table_mode harus bernilai 'new' atau 'existing'."
            )

        duplicate_action = duplicate_action.strip().lower()

        if duplicate_action not in {
            "block",
            "replace",
            "append",
        }:
            raise ValueError(
                "duplicate_action harus bernilai "
                "'block', 'replace', atau 'append'."
            )

        deleted_row_ids = parse_json_list(
            deleted_rows,
            "deleted_rows",
        )

        column_map = parse_json_dict(
            column_mapping,
            "column_mapping",
        )

        file_bytes = await file.read()

        df = process_upload_by_mode(
            file_bytes=file_bytes,
            table_mode=table_mode,
            table_name=table_name,
            sheet_name=sheet_name,
            header_row=header_row,
            first_data_row=first_data_row,
            month=month,
            year=year,
        )

        df, bank = attach_bank_id(
            df,
            bank_name,
        )

        original_rows = len(df)

        df = df.reset_index(drop=True)
        df.insert(
            0,
            "__row_id",
            range(1, len(df) + 1),
        )

        normalized_deleted_rows = []

        for row_id in deleted_row_ids:
            try:
                parsed_row_id = int(row_id)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Row ID '{row_id}' tidak valid."
                ) from error

            if parsed_row_id < 1:
                raise ValueError(
                    "Row ID harus lebih besar dari 0."
                )

            if (
                parsed_row_id
                not in normalized_deleted_rows
            ):
                normalized_deleted_rows.append(
                    parsed_row_id
                )

        valid_row_ids = set(
            df["__row_id"].tolist()
        )

        invalid_row_ids = [
            row_id
            for row_id in normalized_deleted_rows
            if row_id not in valid_row_ids
        ]

        if invalid_row_ids:
            raise ValueError(
                "Terdapat row ID yang tidak valid: "
                + ", ".join(
                    map(str, invalid_row_ids)
                )
            )

        if normalized_deleted_rows:
            df = df[
                ~df["__row_id"].isin(
                    normalized_deleted_rows
                )
            ]

        df = df.drop(
            columns=["__row_id"]
        ).reset_index(drop=True)

        if df.empty:
            raise ValueError(
                "Tidak ada data yang dapat disimpan "
                "setelah penghapusan row."
            )

        previous_period_rows = 0

        # -----------------------------------------
        # NEW TABLE
        # -----------------------------------------
        if table_mode == "new":
            protected_columns = SYSTEM_COLUMNS

            for old_name, new_name in column_map.items():
                old_name = str(old_name)
                new_name = str(
                    new_name
                ).strip()

                if old_name in protected_columns:
                    raise ValueError(
                        f"Kolom sistem '{old_name}' "
                        "tidak dapat diubah."
                    )

                if old_name not in df.columns:
                    raise ValueError(
                        f"Kolom '{old_name}' "
                        "tidak ditemukan."
                    )

                if not new_name:
                    raise ValueError(
                        f"Nama baru untuk kolom "
                        f"'{old_name}' tidak boleh kosong."
                    )

            source_business_columns = [
                str(column)
                for column in df.columns
                if str(column) not in SYSTEM_COLUMNS
            ]

            schema_mapping = []

            for ordinal, source_column in enumerate(
                source_business_columns,
                start=1,
            ):
                final_column = str(
                    column_map.get(
                        source_column,
                        source_column,
                    )
                ).strip()

                schema_mapping.append(
                    {
                        "source_ordinal": ordinal,
                        "source_column": source_column,
                        "database_column": final_column,
                    }
                )

            if column_map:
                df = df.rename(
                    columns=column_map
                )

            result = create_new_table(
                table_name=table_name,
                df=df,
                schema_mapping=schema_mapping,
            )

        # -----------------------------------------
        # EXISTING TABLE
        # -----------------------------------------
        else:
            if column_map:
                raise ValueError(
                    "Nama kolom tidak dapat diubah "
                    "saat upload ke tabel existing."
                )

            previous_period_rows = count_period_rows(
                table_name=table_name,
                bank_id=bank["bank_id"],
                month=month,
                year=year,
            )

            if previous_period_rows > 0:
                if duplicate_action == "block":
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "DUPLICATE_PERIOD",
                            "message": (
                                f"Data {bank['bank_name']} periode "
                                f"{month}/{year} sudah tersedia."
                            ),
                            "table_name": table_name,
                            "bank_name": bank["bank_name"],
                            "bank_id": bank["bank_id"],
                            "month": month,
                            "year": year,
                            "row_count": previous_period_rows,
                        },
                    )

                if duplicate_action == "replace":
                    result = replace_period_data(
                        table_name=table_name,
                        df=df,
                        bank_id=bank["bank_id"],
                        month=month,
                        year=year,
                    )

                else:
                    result = append_existing_table(
                        table_name=table_name,
                        df=df,
                    )

            else:
                result = append_existing_table(
                    table_name=table_name,
                    df=df,
                )

        return {
            "status": "success",
            "message": "Data berhasil disimpan ke database.",
            "table_name": result["table_name"],
            "table_mode": result["mode"],
            "bank_name": bank["bank_name"],
            "bank_id": bank["bank_id"],
            "month": month,
            "year": year,
            "original_rows": original_rows,
            "deleted_rows": len(
                normalized_deleted_rows
            ),
            "duplicate_action": (
                result.get("duplicate_action")
                if table_mode == "existing"
                else None
            ),
            "previous_period_rows": (
                previous_period_rows
                if table_mode == "existing"
                else 0
            ),
            "replaced_rows": result.get(
                "replaced_rows",
                0,
            ),
            "inserted_rows": result[
                "inserted_rows"
            ],
        }

    except HTTPException:
        raise

    except Exception as error:
        print(
            "ERROR /excel/save:",
            repr(error),
        )

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )
