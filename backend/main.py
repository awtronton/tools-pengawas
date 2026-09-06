from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from services.excel_processor import get_excel_sheets, process_excel


app = FastAPI(
    title="OJK Data Warehouse API",
    version="1.0.0",
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
# HEALTH CHECK
# =====================================================

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "OJK Data Warehouse API running",
    }


# =====================================================
# DETECT SHEETS
# =====================================================

@app.post("/excel/sheets")
async def detect_sheets(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        sheets = get_excel_sheets(file_bytes)

        return {
            "filename": file.filename,
            "sheets": sheets,
        }

    except Exception as error:
        print("ERROR /excel/sheets:", repr(error))

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# =====================================================
# PREVIEW
# =====================================================

@app.post("/excel/preview")
async def preview_excel(
    file: UploadFile = File(...),
    table_name: str = Form(...),
    month: int = Form(...),
    year: int = Form(...),
    sheet_name: str = Form(...),
    header_row: int = Form(...),
):
    try:
        print(
            "PREVIEW REQUEST:",
            {
                "filename": file.filename,
                "table_name": table_name,
                "month": month,
                "year": year,
                "sheet_name": sheet_name,
                "header_row": header_row,
            },
        )

        file_bytes = await file.read()

        df = process_excel(
            file_bytes=file_bytes,
            sheet_name=sheet_name,
            header_row=header_row,
            month=month,
            year=year,
        )

        # Seluruh row dikirim untuk tahap preview/edit row.
        # Pagination dilakukan di frontend. __row_id hanya ID sementara
        # dan tidak termasuk schema kolom database.
        preview_df = df.reset_index(drop=True).astype(object)
        preview_df = preview_df.where(preview_df.notna(), None)

        preview = preview_df.to_dict(orient="records")
        for row_id, row in enumerate(preview, start=1):
            row["__row_id"] = row_id

        return {
            "filename": file.filename,
            "table_name": table_name,
            "month": month,
            "year": year,
            "sheet_name": sheet_name,
            "header_row": header_row,

            # Kontrak response yang digunakan frontend.
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": [str(column) for column in df.columns],
            "preview": preview,
        }

    except Exception as error:
        print("ERROR /excel/preview:", repr(error))

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )
