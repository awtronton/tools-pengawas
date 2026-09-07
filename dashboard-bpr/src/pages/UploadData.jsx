import { useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@vibe/core'
import {
  detectExcelSheets,
  previewExcel,
  saveExcel,
  getTables,
  getBanks,
  checkPeriod,
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
  Save,
} from 'lucide-react'

import DashboardLayout from '../layouts/DashboardLayout'
import WorkspacePageHeader from '../components/ui/WorkspacePageHeader'
import '../styles/upload-vibe.css'

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
  const [banks, setBanks] = useState([])
  const [selectedBankName, setSelectedBankName] = useState('')
  const [loadingBanks, setLoadingBanks] = useState(false)
  const [bankLoadError, setBankLoadError] = useState('')
  const [month, setMonth] = useState(1)
  const [year, setYear] = useState(new Date().getFullYear())
  const [headerRow, setHeaderRow] = useState(1)
  const [firstDataRow, setFirstDataRow] = useState(1)

  const [previewData, setPreviewData] = useState(null)
  const [processing, setProcessing] = useState(false)
  const [message, setMessage] = useState('')
  const [messageType, setMessageType] = useState('warning')

  const [deletedRowIds, setDeletedRowIds] = useState([])
  const [selectedRowIds, setSelectedRowIds] = useState([])
  const [columnMapping, setColumnMapping] = useState({})
  const [currentPage, setCurrentPage] = useState(1)
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState(null)
  const [duplicateWarning, setDuplicateWarning] = useState(null)
  const rowsPerPage = 20

  const [existingTables, setExistingTables] = useState([])
  const [loadingTables, setLoadingTables] = useState(false)
  const [tableLoadError, setTableLoadError] = useState('')

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

  async function loadExistingTables({ silent = false } = {}) {
    try {
      setLoadingTables(true)
      setTableLoadError('')

      const result = await getTables()
      const tables = Array.isArray(result?.tables) ? result.tables : []

      setExistingTables(tables)

      // Bila tabel yang sebelumnya dipilih sudah tidak ada,
      // reset pilihan agar tidak menyimpan ke target yang salah.
      setTableName((current) => {
        if (tableMode !== 'existing') return current
        if (!current) return current
        return tables.includes(current) ? current : ''
      })
    } catch (error) {
      console.error(error)
      setExistingTables([])
      setTableLoadError(
        error.message || 'Gagal mengambil daftar tabel dari database.',
      )

      if (!silent) {
        showMessage(
          error.message || 'Gagal mengambil daftar tabel dari database.',
          'warning',
        )
      }
    } finally {
      setLoadingTables(false)
    }
  }

  async function loadBanks({ silent = false } = {}) {
    try {
      setLoadingBanks(true)
      setBankLoadError('')

      const result = await getBanks()
      const bankList = Array.isArray(result?.banks) ? result.banks : []

      setBanks(bankList)

      setSelectedBankName((current) => {
        if (!current) return current
        return bankList.some((bank) => bank.bank_name === current)
          ? current
          : ''
      })
    } catch (error) {
      console.error(error)
      setBanks([])
      setBankLoadError(
        error.message || 'Gagal mengambil master bank.',
      )

      if (!silent) {
        showMessage(
          error.message || 'Gagal mengambil master bank.',
          'warning',
        )
      }
    } finally {
      setLoadingBanks(false)
    }
  }

  useEffect(() => {
    loadExistingTables({ silent: true })
    loadBanks({ silent: true })
    // master tabel dan bank cukup dimuat saat halaman pertama kali dibuka
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
      setSaveResult(null)
      setDuplicateWarning(null)
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

    if (!selectedBankName) {
      showMessage('Pilih nama bank terlebih dahulu.', 'warning')
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

    if (tableMode === 'new' && (!headerRow || Number(headerRow) < 1)) {
      showMessage('Baris Header minimal bernilai 1.', 'warning')
      return
    }

    if (
      tableMode === 'existing' &&
      (!firstDataRow || Number(firstDataRow) < 1)
    ) {
      showMessage('Baris Pertama Data minimal bernilai 1.', 'warning')
      return
    }

    try {
      setProcessing(true)
      setPreviewData(null)
      setSaveResult(null)
      setDuplicateWarning(null)
      showMessage('', 'warning')

      const result = await previewExcel({
        file,
        tableMode,
        tableName: tableName.trim(),
        bankName: selectedBankName,
        month: Number(month),
        year: Number(year),
        sheetName: selectedSheet,
        headerRow: Number(headerRow),
        firstDataRow: Number(firstDataRow),
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
    setSaveResult(null)
    setDuplicateWarning(null)
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

  function buildEffectiveColumnMapping() {
    const effectiveColumnMapping = {}

    if (tableMode === 'new') {
      ;(previewData?.columns || []).forEach((column) => {
        const mappedName = String(columnMapping[column] ?? column).trim()

        if (['bank_id', 'bulan', 'tahun'].includes(String(column).toLowerCase())) {
          return
        }

        if (mappedName && mappedName !== String(column)) {
          effectiveColumnMapping[column] = mappedName
        }
      })
    }

    return effectiveColumnMapping
  }

  function validateBeforeSave() {
    if (!previewData || !file) {
      showMessage('Preview data belum tersedia.', 'warning')
      return false
    }

    if (activePreviewRows.length === 0) {
      showMessage('Tidak ada row yang dapat disimpan.', 'warning')
      return false
    }

    if (tableMode === 'new' && !columnValidation.valid) {
      showMessage(
        'Masih terdapat nama kolom yang tidak valid. Perbaiki terlebih dahulu.',
        'warning',
      )
      return false
    }

    return true
  }

  async function performDatabaseSave(duplicateAction = 'block') {
    const effectiveColumnMapping = buildEffectiveColumnMapping()

    try {
      setSaving(true)
      setSaveResult(null)
      showMessage('', 'warning')

      const result = await saveExcel({
        file,
        tableMode,
        tableName: tableName.trim(),
        bankName: selectedBankName,
        month: Number(month),
        year: Number(year),
        sheetName: selectedSheet,
        headerRow: Number(headerRow),
        firstDataRow: Number(firstDataRow),
        deletedRows: deletedRowIds,
        columnMapping: effectiveColumnMapping,
        duplicateAction,
      })

      setSaveResult(result)
      setDuplicateWarning(null)

      await loadExistingTables({ silent: true })

      showMessage(
        `${result.inserted_rows ?? activePreviewRows.length} row berhasil disimpan ke tabel ${result.table_name ?? tableName}.`,
        'success',
      )
    } catch (error) {
      console.error(error)
      showMessage(
        error.message || 'Gagal menyimpan data ke database.',
        'warning',
      )
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveToDatabase() {
    if (!validateBeforeSave()) return

    if (tableMode === 'existing') {
      try {
        setSaving(true)
        showMessage('', 'warning')

        const periodResult = await checkPeriod({
          tableName: tableName.trim(),
          bankName: selectedBankName,
          month: Number(month),
          year: Number(year),
        })

        if (periodResult.exists) {
          setDuplicateWarning(periodResult)
          return
        }
      } catch (error) {
        console.error(error)
        showMessage(
          error.message || 'Gagal memeriksa periode existing.',
          'warning',
        )
        return
      } finally {
        setSaving(false)
      }
    }

    const confirmationText = [
      'Simpan data ke database?',
      '',
      `Tabel: ${tableName}`,
      `Bank: ${selectedBankName}`,
      `Mode: ${tableMode === 'new' ? 'Buat tabel baru' : 'Append ke tabel existing'}`,
      `Periode: ${selectedMonthLabel} ${year}`,
      `${
        tableMode === 'new'
          ? `Baris Header: ${headerRow}`
          : `Baris Pertama Data: ${firstDataRow}`
      }`,
      `Data awal: ${previewData.row_count ?? previewData.preview?.length ?? 0} row`,
      `Dihapus: ${deletedRowIds.length} row`,
      `Akan disimpan: ${activePreviewRows.length} row`,
    ].join('\n')

    if (!window.confirm(confirmationText)) {
      return
    }

    await performDatabaseSave('block')
  }

  async function handleDuplicateAction(action) {
    if (action === 'cancel') {
      setDuplicateWarning(null)
      return
    }

    const actionLabel =
      action === 'replace'
        ? 'menghapus data periode lama dan menggantinya dengan data upload baru'
        : 'menambahkan data upload baru tanpa menghapus data periode lama'

    const confirmed = window.confirm(
      `Anda akan ${actionLabel}.\n\n` +
      `Tabel: ${tableName}\n` +
      `Bank: ${duplicateWarning?.bank_name || selectedBankName}\n` +
      `Periode: ${selectedMonthLabel} ${year}\n` +
      `Data existing: ${duplicateWarning?.row_count ?? 0} row\n` +
      `Data upload: ${activePreviewRows.length} row\n\n` +
      'Lanjutkan?',
    )

    if (!confirmed) return

    setDuplicateWarning(null)
    await performDatabaseSave(action)
  }

  return (
    <DashboardLayout>
      <main className="tp-upload-page mx-auto w-full max-w-[1480px] space-y-5">
        <WorkspacePageHeader
          eyebrow="Data Warehouse"
          title="Upload Data"
          description="Tambahkan data XLS/XLSX ke warehouse, tentukan bank dan periode, lalu validasi hasil cleaning sebelum disimpan ke PostgreSQL."
          icon={Database}
          badge="Upload Workspace"
        />

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
          className="tp-upload-form space-y-6 rounded-xl border border-slate-200 bg-white p-6"
        >
          <section>
            <div className="mb-3">
              <h2 className="text-[13px] font-medium text-slate-800">
                1. Pilih file Excel
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
                className={`tp-upload-dropzone cursor-pointer rounded-xl border border-dashed p-10 text-center transition ${
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
              <div className="tp-upload-selected-file flex items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50 p-4">
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
              <h2 className="text-[13px] font-medium text-slate-800">
                2. Tentukan tabel tujuan
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
                    const nextMode = event.target.value
                    setTableMode(nextMode)
                    setTableName('')
                    setPreviewData(null)
                    setSaveResult(null)

                    if (nextMode === 'existing') {
                      loadExistingTables({ silent: true })
                    }
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
                  <div className="space-y-2">
                    <select
                      value={tableName}
                      onChange={(event) => {
                        setTableName(event.target.value)
                        setPreviewData(null)
                        setSaveResult(null)
                      }}
                      disabled={loadingTables || existingTables.length === 0}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-bold text-slate-800 outline-none focus:border-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <option value="">
                        {loadingTables
                          ? 'Memuat tabel database...'
                          : existingTables.length === 0
                            ? 'Belum ada tabel di database'
                            : 'Pilih table...'}
                      </option>

                      {existingTables.map((table) => (
                        <option key={table} value={table}>
                          {table}
                        </option>
                      ))}
                    </select>

                    <div className="flex items-center justify-between gap-3">
                      <p className={`text-[10px] ${
                        tableLoadError ? 'font-semibold text-red-500' : 'text-slate-400'
                      }`}>
                        {tableLoadError
                          ? tableLoadError
                          : `${existingTables.length} tabel tersedia di PostgreSQL.`}
                      </p>

                      <button
                        type="button"
                        onClick={() => loadExistingTables()}
                        disabled={loadingTables}
                        className="text-[10px] font-bold text-blue-600 hover:text-blue-700 disabled:opacity-40"
                      >
                        {loadingTables ? 'Memuat...' : 'Refresh'}
                      </button>
                    </div>
                  </div>
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
              <h2 className="text-[13px] font-medium text-slate-800">
                3. Tentukan bank & periode data
              </h2>
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-600">
                  Nama Bank
                </label>

                <select
                  value={selectedBankName}
                  onChange={(event) => {
                    setSelectedBankName(event.target.value)
                    setPreviewData(null)
                    setSaveResult(null)
                  }}
                  disabled={loadingBanks || banks.length === 0}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-bold text-slate-800 outline-none focus:border-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <option value="">
                    {loadingBanks
                      ? 'Memuat master bank...'
                      : banks.length === 0
                        ? 'Master bank belum tersedia'
                        : 'Pilih bank...'}
                  </option>

                  {banks.map((bank) => (
                    <option key={bank.bank_id} value={bank.bank_name}>
                      {bank.bank_name}
                    </option>
                  ))}
                </select>

                <div className="mt-2 flex items-center justify-between gap-3">
                  <p className={`text-[10px] ${
                    bankLoadError ? 'font-semibold text-red-500' : 'text-slate-400'
                  }`}>
                    {bankLoadError
                      ? bankLoadError
                      : `${banks.length} bank tersedia.`}
                  </p>

                  <button
                    type="button"
                    onClick={() => loadBanks()}
                    disabled={loadingBanks}
                    className="text-[10px] font-bold text-blue-600 hover:text-blue-700 disabled:opacity-40"
                  >
                    {loadingBanks ? 'Memuat...' : 'Refresh'}
                  </button>
                </div>
              </div>

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
              <h2 className="text-[13px] font-medium text-slate-800">
                4. Struktur Excel
              </h2>

              <p className="mt-1 text-xs text-slate-400">
                {tableMode === 'new'
                  ? 'Untuk tabel baru, tentukan baris yang berisi nama kolom sebagai header.'
                  : 'Untuk tabel existing, cukup tentukan baris pertama data. Header preview akan mengikuti schema tabel yang sudah tersimpan.'}
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
                    setSaveResult(null)
                    setDuplicateWarning(null)
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
                  {tableMode === 'new' ? 'Baris Header' : 'Baris Pertama Data'}
                </label>

                {tableMode === 'new' ? (
                  <input
                    type="number"
                    min="1"
                    value={headerRow}
                    onChange={(event) => {
                      setHeaderRow(Number(event.target.value))
                      setPreviewData(null)
                      setSaveResult(null)
                    }}
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-bold text-slate-800 outline-none focus:border-blue-500"
                  />
                ) : (
                  <input
                    type="number"
                    min="1"
                    value={firstDataRow}
                    onChange={(event) => {
                      setFirstDataRow(Number(event.target.value))
                      setPreviewData(null)
                      setSaveResult(null)
                      setDuplicateWarning(null)
                    }}
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-bold text-slate-800 outline-none focus:border-blue-500"
                  />
                )}

                <p className="mt-1.5 text-[10px] text-slate-400">
                  {tableMode === 'new'
                    ? 'Contoh: isi 17 jika nama kolom berada pada baris Excel ke-17.'
                    : 'Contoh: isi 18 jika data pertama dimulai pada baris Excel ke-18. Nama kolom tidak dibaca dari file.'}
                </p>
              </div>
            </div>
          </section>

          <section className="tp-upload-metadata rounded-lg border border-slate-200 bg-slate-50/70 p-4">
            <h3 className="text-[10px] font-medium uppercase tracking-[0.06em] text-blue-700">
              Metadata Upload
            </h3>

            <div className="mt-3 grid grid-cols-2 gap-3 text-xs md:grid-cols-6">
              <div>
                <p className="text-slate-400">Table</p>
                <p className="mt-1 font-bold text-slate-800">
                  {tableName || '-'}
                </p>
              </div>

              <div>
                <p className="text-slate-400">Bank</p>
                <p className="mt-1 truncate font-bold text-slate-800">
                  {selectedBankName || '-'}
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
                <p className="text-slate-400">
                  {tableMode === 'new' ? 'Header' : 'Data Mulai'}
                </p>
                <p className="mt-1 font-bold text-slate-800">
                  Baris {tableMode === 'new' ? headerRow : firstDataRow}
                </p>
              </div>
            </div>
          </section>

          <div className="flex justify-end">
            <Button
              type="submit"
              disabled={processing}
              className="tp-vibe-primary-action"
            >
              <span className="flex items-center gap-2">
                {processing ? (
                  <LoaderCircle size={16} className="animate-spin" />
                ) : (
                  <UploadCloud size={16} />
                )}

                {processing ? 'Memproses...' : 'Proses & Preview Data'}
              </span>
            </Button>
          </div>
        </form>

        {previewData && (
          <section className="tp-upload-preview overflow-hidden rounded-xl border border-slate-200 bg-white">
            <div className="border-b border-slate-100 p-5">
              <div className="flex flex-col justify-between gap-3 md:flex-row md:items-center">
                <div>
                  <div className="text-[10px] font-medium uppercase tracking-[0.10em] text-emerald-600">
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

            <div className="grid grid-cols-2 gap-3 border-b border-slate-100 bg-slate-50/60 p-4 text-xs md:grid-cols-5">
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
                <p className="text-slate-400">Bank</p>
                <p className="mt-1 truncate font-bold text-slate-700">
                  {previewData.bank_name || selectedBankName}
                  {previewData.bank_id ? ` (${previewData.bank_id})` : ''}
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
                    <h3 className="text-[13px] font-medium text-slate-800">
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
                          <p className="text-[10px] font-medium uppercase tracking-[0.06em] text-slate-400">
                            Original
                          </p>
                          <p className="mt-1 truncate text-xs font-bold text-slate-700">
                            {column}
                          </p>
                        </div>

                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-[0.06em] text-slate-400">
                            Nama Kolom Database
                          </p>
                          <input
                            value={columnMapping[column] ?? ''}
                            onChange={(event) => updateColumnName(column, event.target.value)}
                            onBlur={() => normalizeColumnName(column)}
                            disabled={['bank_id', 'bulan', 'tahun'].includes(String(column).toLowerCase())}
                            className={`mt-1 w-full rounded-lg border px-3 py-2 text-xs font-bold outline-none ${
                              ['bank_id', 'bulan', 'tahun'].includes(String(column).toLowerCase())
                                ? 'cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400'
                                : columnValidation.errors[column]
                                  ? 'border-red-300 bg-white text-red-700 focus:border-red-500'
                                  : 'border-slate-200 bg-white text-slate-700 focus:border-blue-500'
                            }`}
                          />
                          {['bulan', 'tahun'].includes(String(column).toLowerCase()) ? (
                            <p className="mt-1 text-[10px] font-semibold text-slate-400">
                              Kolom sistem periode.
                            </p>
                          ) : (
                            columnValidation.errors[column] && (
                              <p className="mt-1 text-[10px] font-semibold text-red-500">
                                {columnValidation.errors[column]}
                              </p>
                            )
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
                Header preview mengikuti schema tabel <strong>{tableName}</strong> yang sudah dikunci saat tabel pertama kali dibuat. Kolom sistem <strong>bank_id</strong>, <strong>bulan</strong>, dan <strong>tahun</strong> ditambahkan otomatis. Rename kolom existing dilakukan melalui Table Explorer.
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

              <Button
                type="button"
                onClick={handleSaveToDatabase}
                disabled={
                  saving ||
                  activePreviewRows.length === 0 ||
                  (tableMode === 'new' && !columnValidation.valid)
                }
                className="tp-vibe-primary-action"
              >
                <span className="flex items-center gap-2">
                  {saving ? (
                    <LoaderCircle size={15} className="animate-spin" />
                  ) : (
                    <Save size={15} />
                  )}
                  {saving ? 'Menyimpan...' : 'Simpan ke Database'}
                </span>
              </Button>
            </div>
          </section>
        )}

        {duplicateWarning && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
            <div className="tp-upload-modal w-full max-w-lg rounded-xl border border-amber-200 bg-white shadow-2xl">
              <div className="border-b border-slate-100 p-5">
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-amber-50 p-2.5 text-amber-600">
                    <AlertCircle size={21} />
                  </div>

                  <div>
                    <div className="text-[10px] font-medium uppercase tracking-[0.10em] text-amber-600">
                      Duplicate Period Detected
                    </div>

                    <h2 className="mt-1 text-base font-extrabold text-slate-800">
                      Data Periode Sudah Tersedia
                    </h2>

                    <p className="mt-1 text-xs text-slate-500">
                      Tentukan tindakan sebelum data baru disimpan.
                    </p>
                  </div>
                </div>
              </div>

              <div className="space-y-4 p-5">
                <div className="grid grid-cols-2 gap-3 rounded-xl bg-slate-50 p-4 text-xs">
                  <div>
                    <p className="text-slate-400">Tabel</p>
                    <p className="mt-1 font-bold text-slate-800">
                      {duplicateWarning.table_name}
                    </p>
                  </div>

                  <div>
                    <p className="text-slate-400">Bank</p>
                    <p className="mt-1 font-bold text-slate-800">
                      {duplicateWarning.bank_name}
                    </p>
                    <p className="mt-0.5 text-[10px] text-slate-400">
                      {duplicateWarning.bank_id}
                    </p>
                  </div>

                  <div>
                    <p className="text-slate-400">Periode</p>
                    <p className="mt-1 font-bold text-slate-800">
                      {selectedMonthLabel} {duplicateWarning.year}
                    </p>
                  </div>

                  <div>
                    <p className="text-slate-400">Data Existing</p>
                    <p className="mt-1 font-bold text-amber-700">
                      {duplicateWarning.row_count} row
                    </p>
                  </div>
                </div>

                <div className="space-y-2 text-xs text-slate-600">
                  <p>
                    <strong>Ganti Data Periode</strong> akan menghapus seluruh data
                    untuk bank dan periode tersebut, kemudian memasukkan data upload baru.
                  </p>
                  <p>
                    <strong>Tetap Tambahkan</strong> akan mempertahankan data existing
                    dan menambahkan data upload sebagai row baru.
                  </p>
                </div>
              </div>

              <div className="flex flex-col-reverse gap-2 border-t border-slate-100 p-4 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={() => handleDuplicateAction('cancel')}
                  disabled={saving}
                  className="rounded-xl border border-slate-200 px-4 py-2.5 text-xs font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                >
                  Batal
                </button>

                <button
                  type="button"
                  onClick={() => handleDuplicateAction('append')}
                  disabled={saving}
                  className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-2.5 text-xs font-bold text-blue-700 hover:bg-blue-100 disabled:opacity-50"
                >
                  Tetap Tambahkan
                </button>

                <button
                  type="button"
                  onClick={() => handleDuplicateAction('replace')}
                  disabled={saving}
                  className="rounded-xl bg-amber-500 px-4 py-2.5 text-xs font-bold text-white hover:bg-amber-600 disabled:opacity-50"
                >
                  Ganti Data Periode
                </button>
              </div>
            </div>
          </div>
        )}

        {saveResult && (
          <section className="tp-upload-success rounded-xl border border-emerald-200 bg-emerald-50 p-5">
            <div className="flex items-start gap-3">
              <div className="rounded-xl bg-white p-2.5 text-emerald-600 shadow-sm">
                <CheckCircle2 size={21} />
              </div>

              <div className="min-w-0 flex-1">
                <div className="text-[10px] font-medium uppercase tracking-[0.10em] text-emerald-700">
                  Database Save Success
                </div>

                <h2 className="mt-1 text-base font-extrabold text-slate-800">
                  Data Berhasil Disimpan
                </h2>

                <p className="mt-1 text-xs text-slate-500">
                  {saveResult.message || 'Data berhasil disimpan ke PostgreSQL.'}
                </p>

                <div className="mt-4 grid grid-cols-2 gap-3 text-xs md:grid-cols-7">
                  <div>
                    <p className="text-slate-400">Tabel</p>
                    <p className="mt-1 font-bold text-slate-800">
                      {saveResult.table_name || tableName}
                    </p>
                  </div>

                  <div>
                    <p className="text-slate-400">Bank</p>
                    <p className="mt-1 truncate font-bold text-slate-800">
                      {saveResult.bank_name || selectedBankName}
                      {saveResult.bank_id ? ` (${saveResult.bank_id})` : ''}
                    </p>
                  </div>

                  <div>
                    <p className="text-slate-400">Mode</p>
                    <p className="mt-1 font-bold text-slate-800">
                      {saveResult.table_mode === 'new' ? 'New Table' : 'Existing'}
                    </p>
                    {saveResult.duplicate_action && (
                      <p className="mt-0.5 text-[10px] font-semibold text-slate-400">
                        {saveResult.duplicate_action === 'replace'
                          ? `Replace ${saveResult.replaced_rows ?? 0} row lama`
                          : 'Append ke periode existing'}
                      </p>
                    )}
                  </div>

                  <div>
                    <p className="text-slate-400">Periode</p>
                    <p className="mt-1 font-bold text-slate-800">
                      {selectedMonthLabel} {saveResult.year || year}
                    </p>
                  </div>

                  <div>
                    <p className="text-slate-400">Data Awal</p>
                    <p className="mt-1 font-bold text-slate-800">
                      {saveResult.original_rows ?? '-'}
                    </p>
                  </div>

                  <div>
                    <p className="text-slate-400">Dihapus</p>
                    <p className="mt-1 font-bold text-red-600">
                      {saveResult.deleted_rows ?? 0}
                    </p>
                  </div>

                  <div>
                    <p className="text-slate-400">Disimpan</p>
                    <p className="mt-1 font-bold text-emerald-700">
                      {saveResult.inserted_rows ?? '-'}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </section>
        )}
      </main>
    </DashboardLayout>
  )
}

export default UploadData
