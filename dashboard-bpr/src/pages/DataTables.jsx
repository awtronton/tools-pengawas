import {
  useEffect,
  useMemo,
  useState,
} from 'react'
import {
  Button,
} from '@vibe/core'
import {
  Columns3,
  Database,
  Eye,
  EyeOff,
  LockKeyhole,
  PencilLine,
  RefreshCw,
  Search,
  Table2,
  X,
} from 'lucide-react'

import DashboardLayout from '../layouts/DashboardLayout'
import WorkspacePageHeader from '../components/ui/WorkspacePageHeader'
import {
  getTableDetail,
  getTableSummaries,
  renameTableColumn,
  setTableColumnMasking,
} from '../services/dataWarehouseService'

import '../styles/data-tables-vibe.css'

function formatNumber(value) {
  if (value === null || value === undefined) {
    return '-'
  }

  return new Intl.NumberFormat('id-ID').format(
    Number(value),
  )
}

function periodLabel(table) {
  if (!table?.min_year && !table?.max_year) {
    return '-'
  }

  if (table.min_year === table.max_year) {
    return String(table.min_year)
  }

  return `${table.min_year ?? '-'}–${table.max_year ?? '-'}`
}

function DataTables() {
  const [tables, setTables] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [search, setSearch] = useState('')

  const [selectedTable, setSelectedTable] = useState('')
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [editingColumn, setEditingColumn] = useState('')
  const [editingValue, setEditingValue] = useState('')
  const [renameLoading, setRenameLoading] = useState(false)
  const [maskingColumn, setMaskingColumn] = useState('')
  const [message, setMessage] = useState('')

  const filteredTables = useMemo(() => {
    const keyword = search.trim().toLowerCase()

    if (!keyword) {
      return tables
    }

    return tables.filter((table) =>
      table.table_name
        .toLowerCase()
        .includes(keyword),
    )
  }, [tables, search])

  async function loadTables({
    preserveSelection = true,
  } = {}) {
    try {
      setLoading(true)
      setLoadError('')

      const result = await getTableSummaries()
      const rows = Array.isArray(result?.tables)
        ? result.tables
        : []

      setTables(rows)

      if (
        preserveSelection &&
        selectedTable &&
        rows.some(
          (item) => item.table_name === selectedTable,
        )
      ) {
        return
      }

      if (rows.length > 0) {
        await selectTable(rows[0].table_name)
      } else {
        setSelectedTable('')
        setDetail(null)
      }
    } catch (error) {
      console.error(error)
      setLoadError(
        error.message ||
          'Gagal membaca Data Tables.',
      )
    } finally {
      setLoading(false)
    }
  }

  async function selectTable(tableName) {
    try {
      setSelectedTable(tableName)
      setEditingColumn('')
      setEditingValue('')
      setMessage('')
      setDetailLoading(true)

      const result = await getTableDetail(
        tableName,
      )

      setDetail(result)
    } catch (error) {
      console.error(error)
      setDetail(null)
      setMessage(
        error.message ||
          'Gagal membaca detail tabel.',
      )
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    loadTables({
      preserveSelection: false,
    })
  }, [])

  function startRename(column) {
    setEditingColumn(column.column_name)
    setEditingValue(column.column_name)
    setMessage('')
  }

  function cancelRename() {
    setEditingColumn('')
    setEditingValue('')
  }

  async function saveRename(column) {
    const nextName = editingValue.trim()

    if (!nextName) {
      setMessage(
        'Nama kolom baru tidak boleh kosong.',
      )
      return
    }

    if (
      !/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(
        nextName,
      )
    ) {
      setMessage(
        'Gunakan huruf, angka, dan underscore; nama kolom tidak boleh diawali angka.',
      )
      return
    }

    if (nextName === column.column_name) {
      cancelRename()
      return
    }

    const duplicate = detail?.columns?.some(
      (item) =>
        item.column_name.toLowerCase() ===
          nextName.toLowerCase() &&
        item.column_name !== column.column_name,
    )

    if (duplicate) {
      setMessage(
        `Kolom '${nextName}' sudah tersedia.`,
      )
      return
    }

    const confirmed = window.confirm(
      `Ubah nama kolom?\n\n` +
        `Tabel: ${selectedTable}\n` +
        `${column.column_name} → ${nextName}\n\n` +
        'Perubahan akan diterapkan pada PostgreSQL dan schema mapping.',
    )

    if (!confirmed) return

    try {
      setRenameLoading(true)
      setMessage('')

      await renameTableColumn({
        tableName: selectedTable,
        oldName: column.column_name,
        newName: nextName,
      })

      await selectTable(selectedTable)
      await loadTables()

      setMessage(
        `Kolom '${column.column_name}' berhasil diubah menjadi '${nextName}'.`,
      )
    } catch (error) {
      console.error(error)
      setMessage(
        error.message ||
          'Gagal mengubah nama kolom.',
      )
    } finally {
      setRenameLoading(false)
      setEditingColumn('')
      setEditingValue('')
    }
  }


  async function toggleMasking(column) {
    if (!column.maskable) return

    const nextMasked = !column.masked

    if (!nextMasked) {
      const confirmed = window.confirm(
        `Tampilkan kembali data asli?\n\n` +
          `Tabel: ${selectedTable}\n` +
          `Kolom: ${column.column_name}\n\n` +
          'Data pada kolom ini akan kembali terlihat di Table Explorer.',
      )

      if (!confirmed) return
    }

    try {
      setMaskingColumn(column.column_name)
      setMessage('')

      await setTableColumnMasking({
        tableName: selectedTable,
        columnName: column.column_name,
        masked: nextMasked,
      })

      await selectTable(selectedTable)

      setMessage(
        nextMasked
          ? `Kolom '${column.column_name}' sekarang dimasking di Table Explorer.`
          : `Masking kolom '${column.column_name}' telah dinonaktifkan.`,
      )
    } catch (error) {
      console.error(error)
      setMessage(
        error.message ||
          'Gagal memperbarui masking kolom.',
      )
    } finally {
      setMaskingColumn('')
    }
  }

  return (
    <DashboardLayout>
      <main className="tp-data-tables mx-auto w-full max-w-[1480px] space-y-5">
        <WorkspacePageHeader
          eyebrow="Data Warehouse"
          title="Data Tables"
          description="Review seluruh tabel yang tersimpan di warehouse dan periksa konsistensi nama kolom pada tabel yang dipilih."
          icon={Table2}
          badge="Table Catalog"
        />

        {message && (
          <div className="tp-data-message">
            {message}
          </div>
        )}

        <section className="tp-data-tables-grid">
          <div className="tp-data-catalog">
            <div className="tp-data-panel-header">
              <div>
                <h2>Table catalog</h2>
                <p>
                  {tables.length} tabel tersedia
                  di PostgreSQL.
                </p>
              </div>

              <button
                type="button"
                className="tp-data-icon-button"
                onClick={() => loadTables()}
                disabled={loading}
                title="Refresh"
                aria-label="Refresh Data Tables"
              >
                <RefreshCw
                  size={16}
                  className={
                    loading ? 'animate-spin' : ''
                  }
                />
              </button>
            </div>

            <div className="tp-data-search">
              <Search size={16} />
              <input
                value={search}
                onChange={(event) =>
                  setSearch(event.target.value)
                }
                placeholder="Cari nama tabel..."
              />
            </div>

            {loadError && (
              <div className="tp-data-error">
                {loadError}
              </div>
            )}

            <div className="tp-data-catalog-table-wrap">
              <table className="tp-data-catalog-table">
                <thead>
                  <tr>
                    <th>Table</th>
                    <th className="text-right">
                      Rows
                    </th>
                    <th className="text-right">
                      Columns
                    </th>
                    <th className="text-right">
                      Banks
                    </th>
                    <th>Period</th>
                    <th>Schema</th>
                  </tr>
                </thead>

                <tbody>
                  {filteredTables.map(
                    (table) => (
                      <tr
                        key={table.table_name}
                        className={
                          selectedTable ===
                          table.table_name
                            ? 'is-selected'
                            : ''
                        }
                        onClick={() =>
                          selectTable(
                            table.table_name,
                          )
                        }
                      >
                        <td>
                          <div className="tp-table-name">
                            <Database size={14} />
                            {table.table_name}
                          </div>
                        </td>

                        <td className="text-right">
                          {formatNumber(
                            table.row_count,
                          )}
                        </td>

                        <td className="text-right">
                          {formatNumber(
                            table.column_count,
                          )}
                        </td>

                        <td className="text-right">
                          {formatNumber(
                            table.bank_count,
                          )}
                        </td>

                        <td>
                          {periodLabel(table)}
                        </td>

                        <td>
                          <span
                            className={`tp-schema-badge ${
                              table.schema_status ===
                              'mapped'
                                ? 'is-mapped'
                                : ''
                            }`}
                          >
                            {table.schema_status ===
                            'mapped'
                              ? 'Mapped'
                              : 'Unmapped'}
                          </span>
                        </td>
                      </tr>
                    ),
                  )}

                  {!loading &&
                    filteredTables.length === 0 && (
                      <tr>
                        <td
                          colSpan="6"
                          className="tp-data-empty"
                        >
                          Tidak ada tabel yang
                          sesuai pencarian.
                        </td>
                      </tr>
                    )}
                </tbody>
              </table>
            </div>
          </div>

          <aside className="tp-column-review">
            <div className="tp-data-panel-header">
              <div>
                <div className="tp-column-review-eyebrow">
                  Column Name Review
                </div>

                <h2>
                  {selectedTable || 'Pilih tabel'}
                </h2>

                <p>
                  Review nama kolom, rename,
                  dan tentukan kolom yang perlu
                  dimasking di Table Explorer.
                </p>
              </div>

              <Columns3 size={20} />
            </div>

            {detail?.summary && (
              <div className="tp-detail-summary">
                <div>
                  <span>Rows</span>
                  <strong>
                    {formatNumber(
                      detail.summary.row_count,
                    )}
                  </strong>
                </div>

                <div>
                  <span>Columns</span>
                  <strong>
                    {formatNumber(
                      detail.summary.column_count,
                    )}
                  </strong>
                </div>

                <div>
                  <span>Banks</span>
                  <strong>
                    {formatNumber(
                      detail.summary.bank_count,
                    )}
                  </strong>
                </div>

                <div>
                  <span>Period</span>
                  <strong>
                    {periodLabel(
                      detail.summary,
                    )}
                  </strong>
                </div>
              </div>
            )}

            <div className="tp-column-table-wrap">
              {detailLoading ? (
                <div className="tp-detail-loading">
                  Membaca schema...
                </div>
              ) : (
                <table className="tp-column-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Column Name</th>
                      <th>Type</th>
                      <th>Source</th>
                      <th>Masking</th>
                      <th className="text-right">
                        Action
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {(detail?.columns || []).map(
                      (column) => (
                        <tr
                          key={
                            column.column_name
                          }
                        >
                          <td className="tp-column-ordinal">
                            {column.ordinal}
                          </td>

                          <td>
                            {editingColumn ===
                            column.column_name ? (
                              <input
                                autoFocus
                                value={
                                  editingValue
                                }
                                onChange={(
                                  event,
                                ) =>
                                  setEditingValue(
                                    event.target
                                      .value,
                                  )
                                }
                                onKeyDown={(
                                  event,
                                ) => {
                                  if (
                                    event.key ===
                                    'Enter'
                                  ) {
                                    saveRename(
                                      column,
                                    )
                                  }

                                  if (
                                    event.key ===
                                    'Escape'
                                  ) {
                                    cancelRename()
                                  }
                                }}
                                className="tp-column-edit-input"
                              />
                            ) : (
                              <div className="tp-column-name-cell">
                                <span>
                                  {
                                    column.column_name
                                  }
                                </span>

                                {column.system_column && (
                                  <LockKeyhole
                                    size={12}
                                  />
                                )}
                              </div>
                            )}
                          </td>

                          <td>
                            <span className="tp-column-type">
                              {column.data_type}
                            </span>
                          </td>

                          <td>
                            <span className="tp-column-source">
                              {column.source_column ||
                                '-'}
                            </span>
                          </td>

                          <td>
                            {column.maskable ? (
                              <button
                                type="button"
                                className={`tp-masking-toggle ${
                                  column.masked
                                    ? 'is-masked'
                                    : ''
                                }`}
                                onClick={() =>
                                  toggleMasking(
                                    column,
                                  )
                                }
                                disabled={
                                  maskingColumn ===
                                  column.column_name
                                }
                                title={
                                  column.masked
                                    ? 'Nonaktifkan masking'
                                    : 'Aktifkan masking'
                                }
                              >
                                {column.masked ? (
                                  <EyeOff
                                    size={13}
                                  />
                                ) : (
                                  <Eye
                                    size={13}
                                  />
                                )}

                                <span>
                                  {column.masked
                                    ? 'Masked'
                                    : 'Visible'}
                                </span>
                              </button>
                            ) : (
                              <span className="tp-locked-label">
                                Locked
                              </span>
                            )}
                          </td>

                          <td className="text-right">
                            {editingColumn ===
                            column.column_name ? (
                              <div className="tp-inline-actions">
                                <Button
                                  type="button"
                                  size="small"
                                  disabled={
                                    renameLoading
                                  }
                                  onClick={() =>
                                    saveRename(
                                      column,
                                    )
                                  }
                                >
                                  Simpan
                                </Button>

                                <button
                                  type="button"
                                  className="tp-data-icon-button"
                                  onClick={
                                    cancelRename
                                  }
                                  disabled={
                                    renameLoading
                                  }
                                  title="Batal"
                                >
                                  <X
                                    size={14}
                                  />
                                </button>
                              </div>
                            ) : column.editable ? (
                              <button
                                type="button"
                                className="tp-edit-column-button"
                                onClick={() =>
                                  startRename(
                                    column,
                                  )
                                }
                              >
                                <PencilLine
                                  size={13}
                                />
                                Edit
                              </button>
                            ) : (
                              <span className="tp-locked-label">
                                Locked
                              </span>
                            )}
                          </td>
                        </tr>
                      ),
                    )}

                    {!detailLoading &&
                      (!detail?.columns ||
                        detail.columns.length ===
                          0) && (
                        <tr>
                          <td
                            colSpan="6"
                            className="tp-data-empty"
                          >
                            Pilih tabel untuk
                            melihat schema.
                          </td>
                        </tr>
                      )}
                  </tbody>
                </table>
              )}
            </div>

            <div className="tp-column-review-note">
              <LockKeyhole size={13} />
              <span>
                bank_id, bulan, dan tahun merupakan
                system columns dan tidak dapat
                diubah atau dimasking. Masking
                hanya memengaruhi data yang
                dikirim ke Table Explorer; nilai
                asli tetap tersimpan di PostgreSQL.
              </span>
            </div>
          </aside>
        </section>
      </main>
    </DashboardLayout>
  )
}

export default DataTables
