import { useMemo, useRef, useState } from 'react'
import {
  detectExcelSheets,
  previewExcel,
} from '../services/dataWarehouseService'
import {
  UploadCloud,
  FileSpreadsheet,
  Database,
  CalendarDays,
  Table2,
  CheckCircle2,
  AlertCircle,
  X,
  LoaderCircle,
  Trash2,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  PencilLine,
} from 'lucide-react'

import DashboardLayout from '../layouts/DashboardLayout'

const months = [
  { value: 1, label: 'Januari' },
  { value: 2, label: 'Februari' },
  { value: 3, label: 'Maret' },
  { value: 4, label: 'April' },
  { value: 5, label: 'Mei' },
  { value: 6, label: 'Juni' },
  { value: 7, label: 'Juli' },
  { value: 8, label: 'Agustus' },
  { value: 9, label: 'September' },
  { value: 10, label: 'Oktober' },
  { value: 11, label: 'November' },
  { value: 12, label: 'Desember' },
]


function normalizePreviewResponse(result) {
  const rawRows =
    Array.isArray(result?.preview)
      ? result.preview
      : Array.isArray(result?.preview_rows)
        ? result.preview_rows
        : Array.isArray(result?.rows)
          ? result.rows
          : Array.isArray(result?.data)
            ? result.data
            : []

  let columns = Array.isArray(result?.columns)
    ? result.columns.map((column) => String(column))
    : []

  if (
    columns.length === 0 &&
    rawRows.length > 0 &&
    rawRows[0] &&
    typeof rawRows[0] === 'object' &&
    !Array.isArray(rawRows[0])
  ) {
    columns = Object.keys(rawRows[0])
  }

  return {
    ...result,
    columns,
    preview: rawRows,
  }
}

function safeCellValue(value) {
  if (value === null || value === undefined) return ''

  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }

  return String(value)
}

function normalizeSqlIdentifier(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/%/g, 'persen')
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/_+/g, '_')
}

function UploadData() {
  const inputRef = useRef(null)

  const [file, setFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [excelSheets, setExcelSheets] = useState([])
  const [selectedSheet, setSelectedSheet] = useState('')

  const [tableMode, setTableMode] = useState('existing')
  const [tableName, setTableName] = useState('')
  const [month, setMonth] = useState(1)
  const [year, setYear] = useState(new Date().getFullYear())
  const [headerRow, setHeaderRow] = useState(1)

  const [previewData, setPreviewData] = useState(null)
  const [processing, setProcessing] = useState(false)
  const [message, setMessage] = useState('')
  const [messageType, setMessageType] = useState('warning')

  const [deletedRowIds, setDeletedRowIds] = useState([])
  const [selectedRowIds, setSelectedRowIds] = useState([])
  const [columnMapping, setColumnMapping] = useState({})
  const [currentPage, setCurrentPage] = useState(1)
  const rowsPerPage = 20

  const existingTables = [
    '1300',
    '0600',
    'laporan_keuangan',
    'kredit_debitur',
    'pengaduan_konsumen',
  ]

  const fileSize = useMemo(() => {
    if (!file) return ''

    const mb = file.size / 1024 / 1024

    return `${mb.toFixed(2)} MB`
  }, [file])

  const selectedMonthLabel =
    months.find((item) => item.value === Number(month))?.label || '-'


  const activePreviewRows = useMemo(() => {
    const rows = Array.isArray(previewData?.preview) ? previewData.preview : []
    const deleted = new Set(deletedRowIds)
    return rows.filter((row) => !deleted.has(row.__row_id))
  }, [previewData, deletedRowIds])

  const totalPages = Math.max(
    1,
    Math.ceil(activePreviewRows.length / rowsPerPage),
  )

  const paginatedRows = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage
    return activePreviewRows.slice(start, start + rowsPerPage)
  }, [activePreviewRows, currentPage])

  const columnValidation = useMemo(() => {
    if (!previewData || tableMode !== 'new') {
      return { valid: true, errors: {} }
    }

    const columns = Array.isArray(previewData.columns) ? previewData.columns : []
    const errors = {}
    const seen = new Map()

    columns.forEach((column) => {
      const mapped = String(columnMapping[column] ?? '').trim()

      if (!mapped) {
        errors[column] = 'Nama kolom wajib diisi.'
        return
      }

      if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(mapped)) {
        errors[column] = 'Gunakan huruf, angka, dan underscore; tidak boleh diawali angka.'
        return
      }

      const key = mapped.toLowerCase()
      if (seen.has(key)) {
        errors[column] = `Duplikat dengan kolom ${seen.get(key)}.`
        return
      }

      seen.set(key, column)
    })

    return {
      valid: Object.keys(errors).length === 0,
      errors,
    }
  }, [previewData, tableMode, columnMapping])

  function showMessage(text, type = 'warning') {
    setMessage(text)
    setMessageType(type)
  }

  async function handleExcelFile(selectedFile) {
    if (!selectedFile) return

    const extension = selectedFile.name
      .split('.')
      .pop()
      ?.toLowerCase()

    if (!['xls', 'xlsx'].includes(extension)) {
      showMessage('File harus berformat XLS atau XLSX.', 'warning')
      return
    }

    try {
      setProcessing(true)
      setPreviewData(null)
      setExcelSheets([])
      setSelectedSheet('')
      showMessage('', 'warning')

      const result = await detectExcelSheets(selectedFile)
      const sheets = Array.isArray(result?.sheets) ? result.sheets : []

      setFile(selectedFile)
      setExcelSheets(sheets)

      if (sheets.length > 0) {
        setSelectedSheet(sheets[0])
        showMessage(
          `File berhasil dibaca. Ditemukan ${sheets.length} sheet Excel.`,
          'success',
        )
      } else {
        showMessage(
          'File berhasil dibaca, tetapi backend tidak menemukan sheet yang dapat diproses.',
          'warning',
        )
      }
    } catch (error) {
      console.error(error)
      setFile(null)
      setExcelSheets([])
      setSelectedSheet('')
      showMessage(
        error.message || 'Gagal membaca struktur file Excel.',
        'warning',
      )
    } finally {
      setProcessing(false)
    }
  }

  async function handleFileInput(event) {
    await handleExcelFile(event.target.files?.[0])
  }

  async function handleDrop(event) {
    event.preventDefault()
    setDragging(false)

    await handleExcelFile(event.dataTransfer.files?.[0])
  }

  async function handleSubmit(event) {
    event.preventDefault()

    if (!file) {
      showMessage('Silakan pilih file XLS/XLSX terlebih dahulu.', 'warning')
      return
    }

    if (!tableName.trim()) {
      showMessage('Nama tabel wajib ditentukan.', 'warning')
      return
    }

    if (!selectedSheet) {
      showMessage('Pilih sheet Excel yang akan diproses.', 'warning')
      return
    }

    if (!year || String(year).length !== 4) {
      showMessage('Tahun harus menggunakan format YYYY.', 'warning')
      return
    }

    if (!headerRow || Number(headerRow) < 1) {
      showMessage('Baris header minimal bernilai 1.', 'warning')
      return
    }

    try {
      setProcessing(true)
      setPreviewData(null)
      showMessage('', 'warning')

      const result = await previewExcel({
        file,
        tableName: tableName.trim(),
        month: Number(month),
        year: Number(year),
        sheetName: selectedSheet,
        headerRow: Number(headerRow),
      })

      console.log('PREVIEW RESPONSE:', result)

      const normalizedResult = normalizePreviewResponse(result)
      setPreviewData(normalizedResult)
      setDeletedRowIds([])
      setSelectedRowIds([])
      setCurrentPage(1)

      const initialMapping = {}
      ;(normalizedResult.columns || []).forEach((column) => {
        initialMapping[column] = normalizeSqlIdentifier(column) || `kolom_${Object.keys(initialMapping).length + 1}`
      })
      setColumnMapping(initialMapping)

      showMessage(
        `Preview berhasil dibuat${
          result?.row_count !== undefined
            ? ` untuk ${result.row_count} baris data`
            : ''
        }.`,
        'success',
      )
    } catch (error) {
      console.error(error)
      showMessage(
        error.message || 'Gagal memproses dan membuat preview data.',
        'warning',
      )
    } finally {
      setProcessing(false)
    }
  }

  function resetFile() {
    setFile(null)
    setExcelSheets([])
    setSelectedSheet('')
    setPreviewData(null)
    setDeletedRowIds([])
    setSelectedRowIds([])
    setColumnMapping({})
    setCurrentPage(1)
    showMessage('', 'warning')

    if (inputRef.current) {
      inputRef.current.value = ''
    }
  }

  function deleteSingleRow(rowId) {
    setDeletedRowIds((current) =>
      current.includes(rowId) ? current : [...current, rowId],
    )
    setSelectedRowIds((current) => current.filter((id) => id !== rowId))
    setCurrentPage(1)
  }

  function deleteSelectedRows() {
    if (selectedRowIds.length === 0) return

    setDeletedRowIds((current) => [
      ...new Set([...current, ...selectedRowIds]),
    ])
    setSelectedRowIds([])
    setCurrentPage(1)
  }

  function resetDeletedRows() {
    setDeletedRowIds([])
    setSelectedRowIds([])
    setCurrentPage(1)
  }

  function toggleRowSelection(rowId) {
    setSelectedRowIds((current) =>
      current.includes(rowId)
        ? current.filter((id) => id !== rowId)
        : [...current, rowId],
    )
  }

  function toggleCurrentPageSelection() {
    const pageIds = paginatedRows.map((row) => row.__row_id)
    const allSelected = pageIds.length > 0 && pageIds.every((id) => selectedRowIds.includes(id))

    if (allSelected) {
      setSelectedRowIds((current) =>
        current.filter((id) => !pageIds.includes(id)),
      )
      return
    }

    setSelectedRowIds((current) => [...new Set([...current, ...pageIds])])
  }

  function updateColumnName(originalColumn, value) {
    setColumnMapping((current) => ({
      ...current,
      [originalColumn]: value,
    }))
  }

  function normalizeColumnName(originalColumn) {
    setColumnMapping((current) => ({
      ...current,
      [originalColumn]: normalizeSqlIdentifier(current[originalColumn]),
    }))
  }

  return (
    <DashboardLayout>
      <main className="mx-auto w-full max-w-6xl space-y-6">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-blue-50 p-2.5 text-blue-600">
              <Database size={21} />
            </div>

            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-600">
                Data Warehouse
              </div>

              <h1 className="mt-1 text-lg font-extrabold text-slate-800">
                Upload Data Terstruktur
              </h1>

              <p className="mt-1 text-xs text-slate-400">
                Unggah file XLS/XLSX, tentukan tabel tujuan dan periode data,
                lalu sistem akan membersihkan struktur menjadi SQL-ready.
              </p>
            </div>
          </div>
        </div>

        {message && (
          <div
            className={`flex items-start gap-2 rounded-xl border px-4 py-3 text-xs font-bold ${
              messageType === 'success'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-amber-200 bg-amber-50 text-amber-700'
            }`}
          >
            {messageType === 'success' ? (
              <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
            ) : (
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
            )}

            <span>{message}</span>
          </div>
        )}

        <form
          onSubmit={handleSubmit}
          className="space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <section>
            <div className="mb-3">
              <h2 className="text-xs font-extrabold uppercase tracking-wider text-slate-800">
                1. Pilih File Excel
              </h2>

              <p className="mt-1 text-xs text-slate-400">
                Mendukung format .xls dan .xlsx.
              </p>
            </div>

            {!file ? (
              <div
                onDragOver={(event) => {
                  event.preventDefault()
                  setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
                onClick={() => {
                  if (!processing) inputRef.current?.click()
                }}
                className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition ${
                  dragging
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-slate-300 bg-slate-50 hover:border-blue-400 hover:bg-blue-50/50'
                } ${processing ? 'pointer-events-none opacity-70' : ''}`}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept=".xls,.xlsx"
                  onChange={handleFileInput}
                  className="hidden"
                />

                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-white text-blue-600 shadow-sm">
                  {processing ? (
                    <LoaderCircle size={26} className="animate-spin" />
                  ) : (
                    <UploadCloud size={26} />
                  )}
                </div>

                <p className="mt-4 text-sm font-extrabold text-slate-700">
                  {processing
                    ? 'Membaca struktur Excel...'
                    : 'Drag & Drop file XLS/XLSX di sini'}
                </p>

                <p className="mt-1 text-xs text-slate-400">
                  {processing
                    ? 'Backend sedang mendeteksi daftar sheet.'
                    : 'atau klik area ini untuk memilih file'}
                </p>
              </div>
            ) : (
              <div className="flex items-center justify-between rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                <div className="flex items-center gap-3">
                  <div className="rounded-xl bg-white p-2 text-emerald-600">
                    <FileSpreadsheet size={22} />
                  </div>

                  <div>
                    <p className="text-sm font-bold text-slate-800">
                      {file.name}
                    </p>

                    <p className="mt-0.5 text-[11px] text-slate-500">
                      {fileSize}
                      {excelSheets.length > 0
                        ? ` • ${excelSheets.length} sheet terdeteksi`
                        : ''}
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={resetFile}
                  disabled={processing}
                  className="rounded-lg p-2 text-slate-400 hover:bg-white hover:text-red-500 disabled:cursor-not-allowed disabled:opacity-50"
                  aria-label="Hapus file"
                >
                  <X size={18} />
                </button>
              </div>
            )}
          </section>

          <section className="border-t border-slate-100 pt-5">
            <div className="mb-4">
              <h2 className="text-xs font-extrabold uppercase tracking-wider text-slate-800">
                2. Tentukan Tabel Tujuan
              </h2>
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-600">
                  Mode Tabel
                </label>

                <select
                  value={tableMode}
                  onChange={(event) => {
                    setTableMode(event.target.value)
                    setTableName('')
                    setPreviewData(null)
                  }}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-bold text-slate-800 outline-none focus:border-blue-500"
                >
                  <option value="existing">
                    Pilih tabel yang sudah ada
                  </option>

                  <option value="new">
                    Buat tabel baru
                  </option>
                </select>
              </div>

              <div className="lg:col-span-2">
                <label className="mb-1.5 flex items-center gap-2 text-xs font-bold text-slate-600">
                  <Table2 size={14} />
                  Nama Table
                </label>

                {tableMode === 'existing' ? (
                  <select
                    value={tableName}
                    onChange={(event) => {
                      setTableName(event.target.value)
                      setPreviewData(null)
                    }}
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-bold text-slate-800 outline-none focus:border-blue-500"
                  >
                    <option value="">
                      Pilih table...
                    </option>

                    {existingTables.map((table) => (
                      <option key={table} value={table}>
                        {table}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={tableName}
                    onChange={(event) => {
                      setTableName(event.target.value)
                      setPreviewData(null)
                    }}
                    placeholder="contoh: kredit_debitur"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-bold text-slate-800 outline-none focus:border-blue-500"
                  />
                )}
              </div>
            </div>
          </section>

          <section className="border-t border-slate-100 pt-5">
            <div className="mb-4">
              <h2 className="text-xs font-extrabold uppercase tracking-wider text-slate-800">
                3. Tentukan Periode Data
              </h2>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1.5 flex items-center gap-2 text-xs font-bold text-slate-600">
                  <CalendarDays size={14} />
                  Bulan
                </label>

                <select
                  value={month}
                  onChange={(event) => {
                    setMonth(Number(event.target.value))
                    setPreviewData(null)
                  }}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-bold text-slate-800 outline-none focus:border-blue-500"
                >
                  {months.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-600">
                  Tahun (YYYY)
                </label>

                <input
                  type="number"
                  value={year}
                  onChange={(event) => {
                    setYear(event.target.value)
                    setPreviewData(null)
                  }}
                  placeholder="2026"
                  min="2000"
                  max="2100"
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-bold text-slate-800 outline-none focus:border-blue-500"
                />
              </div>
            </div>
          </section>

          <section className="border-t border-slate-100 pt-5">
            <div className="mb-4">
              <h2 className="text-xs font-extrabold uppercase tracking-wider text-slate-800">
                4. Struktur Excel
              </h2>

              <p className="mt-1 text-xs text-slate-400">
                Daftar sheet dibaca otomatis dari file Excel oleh backend.
                Tentukan baris yang berisi nama kolom sebagai header.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-600">
                  Nama Sheet
                </label>

                <select
                  value={selectedSheet}
                  onChange={(event) => {
                    setSelectedSheet(event.target.value)
                    setPreviewData(null)
                  }}
                  disabled={!file || excelSheets.length === 0 || processing}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-bold text-slate-800 outline-none focus:border-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {excelSheets.length === 0 ? (
                    <option value="">Upload file terlebih dahulu</option>
                  ) : (
                    excelSheets.map((sheet) => (
                      <option key={sheet} value={sheet}>
                        {sheet}
                      </option>
                    ))
                  )}
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-600">
                  Baris Header
                </label>

                <input
                  type="number"
                  min="1"
                  value={headerRow}
                  onChange={(event) => {
                    setHeaderRow(Number(event.target.value))
                    setPreviewData(null)
                  }}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-bold text-slate-800 outline-none focus:border-blue-500"
                />
              </div>
            </div>
          </section>

          <section className="rounded-xl border border-blue-100 bg-blue-50/50 p-4">
            <h3 className="text-[10px] font-bold uppercase tracking-wider text-blue-700">
              Metadata Upload
            </h3>

            <div className="mt-3 grid grid-cols-2 gap-3 text-xs md:grid-cols-5">
              <div>
                <p className="text-slate-400">Table</p>
                <p className="mt-1 font-bold text-slate-800">
                  {tableName || '-'}
                </p>
              </div>

              <div>
                <p className="text-slate-400">Bulan</p>
                <p className="mt-1 font-bold text-slate-800">
                  {selectedMonthLabel}
                </p>
              </div>

              <div>
                <p className="text-slate-400">Tahun</p>
                <p className="mt-1 font-bold text-slate-800">
                  {year || '-'}
                </p>
              </div>

              <div>
                <p className="text-slate-400">Sheet</p>
                <p className="mt-1 truncate font-bold text-slate-800">
                  {selectedSheet || '-'}
                </p>
              </div>

              <div>
                <p className="text-slate-400">Header</p>
                <p className="mt-1 font-bold text-slate-800">
                  Baris {headerRow}
                </p>
              </div>
            </div>
          </section>

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={processing}
              className="flex items-center gap-2 rounded-xl bg-blue-600 px-6 py-2.5 text-xs font-bold text-white shadow-md shadow-blue-600/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {processing ? (
                <LoaderCircle size={16} className="animate-spin" />
              ) : (
                <UploadCloud size={16} />
              )}

              {processing ? 'Memproses...' : 'Proses & Preview Data'}
            </button>
          </div>
        </form>

        {previewData && (
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 p-5">
              <div className="flex flex-col justify-between gap-3 md:flex-row md:items-center">
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-600">
                    SQL-Ready Preview
                  </div>

                  <h2 className="mt-1 text-base font-extrabold text-slate-800">
                    Preview Hasil Cleaning
                  </h2>

                  <p className="mt-1 text-xs text-slate-400">
                    Hapus baris yang tidak ingin disimpan. Perubahan nama kolom hanya tersedia saat membuat tabel baru.
                  </p>
                </div>

                <div className="flex flex-wrap gap-2 text-[11px] font-bold">
                  <span className="rounded-lg bg-slate-100 px-3 py-2 text-slate-600">
                    {previewData.row_count ?? previewData.preview?.length ?? 0} baris awal
                  </span>

                  <span className="rounded-lg bg-red-50 px-3 py-2 text-red-600">
                    {deletedRowIds.length} dihapus
                  </span>

                  <span className="rounded-lg bg-emerald-50 px-3 py-2 text-emerald-700">
                    {activePreviewRows.length} akan disimpan
                  </span>

                  <span className="rounded-lg bg-blue-50 px-3 py-2 text-blue-700">
                    {previewData.table_name || tableName}
                  </span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 border-b border-slate-100 bg-slate-50/60 p-4 text-xs md:grid-cols-4">
              <div>
                <p className="text-slate-400">File</p>
                <p className="mt-1 truncate font-bold text-slate-700">
                  {previewData.filename || file?.name || '-'}
                </p>
              </div>

              <div>
                <p className="text-slate-400">Sheet</p>
                <p className="mt-1 truncate font-bold text-slate-700">
                  {previewData.sheet_name || selectedSheet}
                </p>
              </div>

              <div>
                <p className="text-slate-400">Periode</p>
                <p className="mt-1 font-bold text-slate-700">
                  {selectedMonthLabel} {previewData.year || year}
                </p>
              </div>

              <div>
                <p className="text-slate-400">Mode</p>
                <p className="mt-1 font-bold text-slate-700">
                  {tableMode === 'new' ? 'Buat tabel baru' : 'Append ke tabel existing'}
                </p>
              </div>
            </div>

            {tableMode === 'new' && (
              <div className="border-b border-slate-100 p-5">
                <div className="mb-4 flex items-start gap-3">
                  <div className="rounded-lg bg-blue-50 p-2 text-blue-600">
                    <PencilLine size={16} />
                  </div>
                  <div>
                    <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-800">
                      Struktur Kolom Tabel Baru
                    </h3>
                    <p className="mt-1 text-xs text-slate-400">
                      Nama kolom dapat diperbaiki sebelum tabel pertama kali dibuat. Nilai data tidak diubah.
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  {(previewData.columns || []).map((column) => (
                    <div
                      key={column}
                      className="rounded-xl border border-slate-200 bg-slate-50 p-3"
                    >
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] sm:items-start">
                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                            Original
                          </p>
                          <p className="mt-1 truncate text-xs font-bold text-slate-700">
                            {column}
                          </p>
                        </div>

                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                            Nama Kolom Database
                          </p>
                          <input
                            value={columnMapping[column] ?? ''}
                            onChange={(event) => updateColumnName(column, event.target.value)}
                            onBlur={() => normalizeColumnName(column)}
                            className={`mt-1 w-full rounded-lg border bg-white px-3 py-2 text-xs font-bold outline-none ${
                              columnValidation.errors[column]
                                ? 'border-red-300 text-red-700 focus:border-red-500'
                                : 'border-slate-200 text-slate-700 focus:border-blue-500'
                            }`}
                          />
                          {columnValidation.errors[column] && (
                            <p className="mt-1 text-[10px] font-semibold text-red-500">
                              {columnValidation.errors[column]}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {tableMode === 'existing' && (
              <div className="border-b border-blue-100 bg-blue-50/40 px-5 py-3 text-xs text-blue-700">
                Struktur kolom mengikuti schema tabel <strong>{tableName}</strong>. Rename kolom dilakukan melalui Table Explorer, bukan pada proses upload.
              </div>
            )}

            <div className="flex flex-col justify-between gap-3 border-b border-slate-100 p-4 md:flex-row md:items-center">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={deleteSelectedRows}
                  disabled={selectedRowIds.length === 0}
                  className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-[11px] font-bold text-red-600 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <Trash2 size={14} />
                  Hapus {selectedRowIds.length > 0 ? `${selectedRowIds.length} Baris` : 'Baris Terpilih'}
                </button>

                <button
                  type="button"
                  onClick={resetDeletedRows}
                  disabled={deletedRowIds.length === 0}
                  className="flex items-center gap-2 rounded-lg bg-slate-100 px-3 py-2 text-[11px] font-bold text-slate-600 hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <RotateCcw size={14} />
                  Pulihkan Baris Dihapus
                </button>
              </div>

              <p className="text-[11px] text-slate-400">
                Pilih checkbox untuk menghapus beberapa row sekaligus.
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-xs">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="sticky left-0 z-10 w-12 border-b border-slate-200 bg-slate-50 px-3 py-3 text-center">
                      <input
                        type="checkbox"
                        checked={
                          paginatedRows.length > 0 &&
                          paginatedRows.every((row) => selectedRowIds.includes(row.__row_id))
                        }
                        onChange={toggleCurrentPageSelection}
                        aria-label="Pilih semua row pada halaman ini"
                      />
                    </th>
                    <th className="whitespace-nowrap border-b border-slate-200 px-3 py-3 font-extrabold text-slate-600">
                      Row
                    </th>
                    {(Array.isArray(previewData.columns) ? previewData.columns : []).map((column) => (
                      <th
                        key={column}
                        className="whitespace-nowrap border-b border-slate-200 px-4 py-3 font-extrabold text-slate-600"
                      >
                        {tableMode === 'new'
                          ? columnMapping[column] || column
                          : String(column)}
                      </th>
                    ))}
                    <th className="sticky right-0 z-10 border-b border-slate-200 bg-slate-50 px-3 py-3 text-center font-extrabold text-slate-600">
                      Aksi
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {paginatedRows.map((row) => (
                    <tr
                      key={row.__row_id}
                      className="border-b border-slate-100 last:border-b-0 hover:bg-slate-50/70"
                    >
                      <td className="sticky left-0 bg-white px-3 py-3 text-center">
                        <input
                          type="checkbox"
                          checked={selectedRowIds.includes(row.__row_id)}
                          onChange={() => toggleRowSelection(row.__row_id)}
                          aria-label={`Pilih row ${row.__row_id}`}
                        />
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 font-bold text-slate-400">
                        {row.__row_id}
                      </td>
                      {(Array.isArray(previewData.columns) ? previewData.columns : []).map((column) => (
                        <td
                          key={`${row.__row_id}-${column}`}
                          className="max-w-xs whitespace-nowrap px-4 py-3 text-slate-600"
                        >
                          {safeCellValue(row?.[column])}
                        </td>
                      ))}
                      <td className="sticky right-0 bg-white px-3 py-3 text-center">
                        <button
                          type="button"
                          onClick={() => deleteSingleRow(row.__row_id)}
                          className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600"
                          aria-label={`Hapus row ${row.__row_id}`}
                        >
                          <Trash2 size={15} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {paginatedRows.length === 0 && (
                <div className="p-8 text-center text-xs font-bold text-slate-400">
                  Tidak ada row aktif untuk ditampilkan.
                </div>
              )}
            </div>

            <div className="flex flex-col justify-between gap-3 border-t border-slate-100 p-4 md:flex-row md:items-center">
              <p className="text-[11px] text-slate-400">
                Menampilkan {activePreviewRows.length === 0 ? 0 : (currentPage - 1) * rowsPerPage + 1}–{Math.min(currentPage * rowsPerPage, activePreviewRows.length)} dari {activePreviewRows.length} row aktif.
              </p>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                  disabled={currentPage <= 1}
                  className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronLeft size={15} />
                </button>

                <span className="min-w-20 text-center text-[11px] font-bold text-slate-600">
                  {currentPage} / {totalPages}
                </span>

                <button
                  type="button"
                  onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
                  disabled={currentPage >= totalPages}
                  className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronRight size={15} />
                </button>
              </div>
            </div>

            <div className="flex flex-col justify-between gap-3 border-t border-slate-100 bg-slate-50/50 p-4 md:flex-row md:items-center">
              <div>
                <p className="text-xs font-bold text-slate-700">
                  {activePreviewRows.length} row siap disimpan
                </p>
                <p className="mt-1 text-[11px] text-slate-400">
                  {tableMode === 'new'
                    ? columnValidation.valid
                      ? 'Nama kolom tabel baru sudah valid.'
                      : 'Perbaiki nama kolom yang masih tidak valid sebelum menyimpan.'
                    : 'Data akan di-append mengikuti schema tabel existing.'}
                </p>
              </div>

              <button
                type="button"
                disabled
                className="rounded-xl bg-slate-200 px-5 py-2.5 text-xs font-bold text-slate-500"
              >
                Simpan ke Database
              </button>
            </div>
          </section>
        )}
      </main>
    </DashboardLayout>
  )
}

export default UploadData
