const API_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

async function requestJson(url, options, fallbackMessage) {
  let response;

  try {
    response = await fetch(url, options);
  } catch (error) {
    console.error("NETWORK ERROR:", error);

    throw new Error(
      `Tidak dapat terhubung ke backend FastAPI di ${API_URL}. Pastikan server backend masih berjalan dan CORS sudah benar.`
    );
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    const detail = errorBody.detail;
    const detailMessage =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object"
          ? detail.message || JSON.stringify(detail)
          : "";

    throw new Error(
      detailMessage ||
        `${fallbackMessage} (HTTP ${response.status})`
    );
  }

  return response.json();
}

export async function detectExcelSheets(file) {
  const formData = new FormData();
  formData.append("file", file);

  return requestJson(
    `${API_URL}/excel/sheets`,
    {
      method: "POST",
      body: formData,
    },
    "Gagal membaca sheet Excel"
  );
}

export async function previewExcel({
  file,
  tableMode,
  tableName,
  bankName,
  month,
  year,
  sheetName,
  headerRow,
  firstDataRow,
}) {
  const formData = new FormData();

  formData.append("file", file);
  formData.append("table_mode", tableMode);
  formData.append("table_name", tableName);
  formData.append("bank_name", bankName);
  formData.append("month", String(month));
  formData.append("year", String(year));
  formData.append("sheet_name", sheetName);

  if (tableMode === "new") {
    formData.append("header_row", String(headerRow));
  } else {
    formData.append("first_data_row", String(firstDataRow));
  }

  return requestJson(
    `${API_URL}/excel/preview`,
    {
      method: "POST",
      body: formData,
    },
    "Gagal memproses file Excel"
  );
}


export async function getBanks() {
  return requestJson(
    `${API_URL}/banks`,
    {
      method: "GET",
    },
    "Gagal mengambil master bank"
  );
}

export async function getTables() {
  return requestJson(
    `${API_URL}/tables`,
    {
      method: "GET",
    },
    "Gagal mengambil daftar tabel database"
  );
}


export async function checkPeriod({
  tableName,
  bankName,
  month,
  year,
}) {
  const formData = new FormData();

  formData.append("table_name", tableName);
  formData.append("bank_name", bankName);
  formData.append("month", String(month));
  formData.append("year", String(year));

  return requestJson(
    `${API_URL}/excel/check-period`,
    {
      method: "POST",
      body: formData,
    },
    "Gagal memeriksa periode existing"
  );
}

export async function saveExcel({
  file,
  tableMode,
  tableName,
  bankName,
  month,
  year,
  sheetName,
  headerRow,
  firstDataRow,
  deletedRows = [],
  columnMapping = {},
  duplicateAction = "block",
}) {
  const formData = new FormData();

  formData.append("file", file);
  formData.append("table_mode", tableMode);
  formData.append("table_name", tableName);
  formData.append("bank_name", bankName);
  formData.append("month", String(month));
  formData.append("year", String(year));
  formData.append("sheet_name", sheetName);

  if (tableMode === "new") {
    formData.append("header_row", String(headerRow));
  } else {
    formData.append("first_data_row", String(firstDataRow));
  }

  formData.append("deleted_rows", JSON.stringify(deletedRows));
  formData.append("column_mapping", JSON.stringify(columnMapping));
  formData.append("duplicate_action", duplicateAction);

  return requestJson(
    `${API_URL}/excel/save`,
    {
      method: "POST",
      body: formData,
    },
    "Gagal menyimpan data ke database"
  );
}


export async function getTableSummaries() {
  return requestJson(
    `${API_URL}/tables-summary`,
    {
      method: "GET",
    },
    "Gagal membaca ringkasan tabel"
  );
}

export async function getTableDetail(tableName) {
  return requestJson(
    `${API_URL}/tables/${encodeURIComponent(tableName)}/detail`,
    {
      method: "GET",
    },
    "Gagal membaca detail tabel"
  );
}

export async function renameTableColumn({
  tableName,
  oldName,
  newName,
}) {
  return requestJson(
    `${API_URL}/tables/${encodeURIComponent(tableName)}/column`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        old_name: oldName,
        new_name: newName,
      }),
    },
    "Gagal mengubah nama kolom"
  );
}


export async function getTableExplorerOptions(tableName) {
  return requestJson(
    `${API_URL}/tables/${encodeURIComponent(tableName)}/explorer/options`,
    {
      method: "GET",
    },
    "Gagal membaca opsi Table Explorer"
  );
}

export async function exploreTable({
  tableName,
  page = 1,
  pageSize = 20,
  search = "",
  bankId = "",
  month = "",
  year = "",
  sortColumn = "",
  sortDirection = "asc",
}) {
  const params = new URLSearchParams();

  params.set("page", String(page));
  params.set("page_size", String(pageSize));

  if (search) params.set("search", search);
  if (bankId) params.set("bank_id", bankId);
  if (month) params.set("month", String(month));
  if (year) params.set("year", String(year));
  if (sortColumn) params.set("sort_column", sortColumn);

  params.set("sort_direction", sortDirection);

  return requestJson(
    `${API_URL}/tables/${encodeURIComponent(tableName)}/explorer?${params.toString()}`,
    {
      method: "GET",
    },
    "Gagal membaca data Table Explorer"
  );
}


export async function setTableColumnMasking({
  tableName,
  columnName,
  masked,
}) {
  return requestJson(
    `${API_URL}/tables/${encodeURIComponent(tableName)}/column-masking`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        column_name: columnName,
        masked: Boolean(masked),
      }),
    },
    "Gagal memperbarui masking kolom"
  );
}


export async function getTableRelationships(tableName = "") {
  const params = new URLSearchParams();

  if (tableName) {
    params.set("table_name", tableName);
  }

  const suffix = params.toString()
    ? `?${params.toString()}`
    : "";

  return requestJson(
    `${API_URL}/relationships${suffix}`,
    {
      method: "GET",
    },
    "Gagal membaca relationship"
  );
}

export async function createTableRelationship(payload) {
  return requestJson(
    `${API_URL}/relationships`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    "Gagal membuat relationship"
  );
}

export async function updateTableRelationship(
  relationshipId,
  payload
) {
  return requestJson(
    `${API_URL}/relationships/${relationshipId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    "Gagal memperbarui relationship"
  );
}

export async function deleteTableRelationship(relationshipId) {
  return requestJson(
    `${API_URL}/relationships/${relationshipId}`,
    {
      method: "DELETE",
    },
    "Gagal menghapus relationship"
  );
}
