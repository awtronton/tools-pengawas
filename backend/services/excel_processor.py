import io
import re
import pandas as pd


def clean_column_name(column):
    """
    Membersihkan nama kolom agar SQL-ready.
    """

    column = str(column).strip().lower()

    column = column.replace("\n", " ")

    column = re.sub(r"\s+", "_", column)

    column = column.replace(".", "")
    column = column.replace("/", "_")
    column = column.replace("-", "_")
    column = column.replace("(", "")
    column = column.replace(")", "")
    column = column.replace("%", "persen")

    column = re.sub(
        r"[^a-zA-Z0-9_]",
        "",
        column
    )

    column = re.sub(
        r"_+",
        "_",
        column
    )

    column = column.strip("_")

    if not column:
        column = "unnamed"

    return column


def make_unique_columns(columns):
    """
    Menghindari duplicate column name.
    """

    result = []
    counter = {}

    for column in columns:

        if column not in counter:
            counter[column] = 1
            result.append(column)

        else:
            counter[column] += 1

            result.append(
                f"{column}_{counter[column]}"
            )

    return result


def clean_value(value):
    """
    Membersihkan isi cell.
    """

    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")

    if isinstance(value, float):
        if value.is_integer():
            return int(value)

    if isinstance(value, str):
        value = value.strip()

        if value == "":
            return None

        return value

    return value


def clean_dataframe(
    df,
    month,
    year
):
    """
    Membersihkan dataframe dan
    menambahkan metadata periode.
    """

    # hapus row kosong
    df = df.dropna(
        how="all"
    )

    # hapus column kosong
    df = df.dropna(
        axis=1,
        how="all"
    )

    # clean column names
    columns = [
        clean_column_name(column)
        for column in df.columns
    ]

    columns = make_unique_columns(
        columns
    )

    df.columns = columns

    # clean values
    for column in df.columns:

        df[column] = df[column].apply(
            clean_value
        )

    # metadata periode
    df["bulan"] = int(month)
    df["tahun"] = int(year)

    return df


def get_excel_sheets(file_bytes):
    """
    Mendapatkan daftar sheet Excel.
    """

    excel_file = pd.ExcelFile(
        io.BytesIO(file_bytes)
    )

    return excel_file.sheet_names


def process_excel(
    file_bytes,
    sheet_name,
    header_row,
    month,
    year
):
    """
    Membaca dan membersihkan Excel.
    """

    df = pd.read_excel(
        io.BytesIO(file_bytes),
        sheet_name=sheet_name,
        header=header_row - 1,
        dtype=object
    )

    df = clean_dataframe(
        df,
        month,
        year
    )

    return df