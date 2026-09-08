import re

import pandas as pd
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
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
MASK_VALUE = "••••••••"
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


def ensure_internal_tables():
    metadata.create_all(
        engine,
        tables=[
            schema_mapping_table,
            column_settings_table,
            relationships_table,
        ],
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
):
    table_name = validate_table_name(table_name)
    column_name = validate_column_name(
        column_name
    )

    inspector = inspect(engine)

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


def _serialize_relationship(row):
    if not row:
        return None

    source_meta = _get_column_metadata(
        row["source_table"],
        row["source_column"],
    )
    target_meta = _get_column_metadata(
        row["target_table"],
        row["target_column"],
    )

    compatibility = (
        _relationship_compatibility(
            source_meta["data_type"],
            target_meta["data_type"],
        )
    )

    source_masked = (
        row["source_column"]
        in get_masked_columns(
            row["source_table"]
        )
    )
    target_masked = (
        row["target_column"]
        in get_masked_columns(
            row["target_table"]
        )
    )

    return {
        "id": int(row["id"]),
        "relationship_name":
            row["relationship_name"],
        "source_table":
            row["source_table"],
        "source_column":
            row["source_column"],
        "source_data_type":
            source_meta["data_type"],
        "source_masked":
            source_masked,
        "target_table":
            row["target_table"],
        "target_column":
            row["target_column"],
        "target_data_type":
            target_meta["data_type"],
        "target_masked":
            target_masked,
        "cardinality":
            row["cardinality"],
        "is_active":
            bool(row["is_active"]),
        "compatible":
            compatibility["compatible"],
        "compatibility_message":
            compatibility["message"],
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

    with engine.connect() as connection:
        rows = connection.execute(
            statement
        ).mappings().all()

    relationships = []

    for row in rows:
        try:
            relationships.append(
                _serialize_relationship(row)
            )
        except ValueError:
            # Metadata relasi lama yang sudah tidak
            # memiliki table/column valid tetap
            # diabaikan dari UI sampai dibersihkan.
            continue

    return relationships


def create_table_relationship(
    *,
    relationship_name: str | None,
    source_table: str,
    source_column: str,
    target_table: str,
    target_column: str,
    cardinality: str,
):
    source_table = validate_table_name(
        source_table
    )
    source_column = validate_column_name(
        source_column
    )
    target_table = validate_table_name(
        target_table
    )
    target_column = validate_column_name(
        target_column
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

    if (
        source_table == target_table
        and source_column == target_column
    ):
        raise ValueError(
            "Source dan target tidak boleh "
            "merupakan kolom yang sama."
        )

    source_meta = _get_column_metadata(
        source_table,
        source_column,
    )
    target_meta = _get_column_metadata(
        target_table,
        target_column,
    )

    name = str(
        relationship_name or ""
    ).strip()

    if not name:
        name = (
            f"{source_table}.{source_column} "
            f"↔ "
            f"{target_table}.{target_column}"
        )

    if len(name) > 180:
        raise ValueError(
            "Nama relationship maksimal "
            "180 karakter."
        )

    ensure_internal_tables()

    with engine.begin() as connection:
        existing_rows = connection.execute(
            select(
                relationships_table
            ).where(
                relationships_table.c.is_active
                .is_(True)
            )
        ).mappings().all()

        for row in existing_rows:
            same_direction = (
                row["source_table"]
                == source_table
                and row["source_column"]
                == source_column
                and row["target_table"]
                == target_table
                and row["target_column"]
                == target_column
            )

            reverse_direction = (
                row["source_table"]
                == target_table
                and row["source_column"]
                == target_column
                and row["target_table"]
                == source_table
                and row["target_column"]
                == source_column
            )

            if (
                same_direction
                or reverse_direction
            ):
                raise ValueError(
                    "Relationship untuk pasangan "
                    "kolom tersebut sudah tersedia."
                )

        result = connection.execute(
            relationships_table.insert().values(
                relationship_name=name,
                source_table=source_table,
                source_column=source_column,
                target_table=target_table,
                target_column=target_column,
                cardinality=cardinality,
                is_active=True,
            )
        )

        relationship_id = int(
            result.inserted_primary_key[0]
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
        row
    )

    compatibility = (
        _relationship_compatibility(
            source_meta["data_type"],
            target_meta["data_type"],
        )
    )

    serialized["compatibility_message"] = (
        compatibility["message"]
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

    return _serialize_relationship(row)


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
