import re

import pandas as pd
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    delete,
    func,
    inspect,
    select,
)

from database.connection import engine


SYSTEM_COLUMNS = {"bank_id", "bulan", "tahun"}
SCHEMA_MAPPING_TABLE_NAME = "warehouse_schema_mapping"
INTERNAL_TABLES = {SCHEMA_MAPPING_TABLE_NAME}


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


def ensure_internal_tables():
    metadata.create_all(
        engine,
        tables=[schema_mapping_table],
    )


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

    df.to_sql(
        name=table_name,
        con=engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=1000,
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

    return {
        "table_name": table_name,
        "mode": "existing",
        "duplicate_action": "replace",
        "replaced_rows": deleted_rows,
        "inserted_rows": len(df),
    }
