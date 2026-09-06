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

    throw new Error(
      errorBody.detail ||
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
  tableName,
  month,
  year,
  sheetName,
  headerRow,
}) {
  const formData = new FormData();

  formData.append("file", file);
  formData.append("table_name", tableName);
  formData.append("month", String(month));
  formData.append("year", String(year));
  formData.append("sheet_name", sheetName);
  formData.append("header_row", String(headerRow));

  return requestJson(
    `${API_URL}/excel/preview`,
    {
      method: "POST",
      body: formData,
    },
    "Gagal memproses file Excel"
  );
}