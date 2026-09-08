import {
  useEffect,
  useMemo,
  useState,
} from 'react'
import {
  Dropdown,
} from '@vibe/core'
import {
  ArrowDown,
  ArrowUp,
  ChevronsLeft,
  ChevronsRight,
  ChevronLeft,
  ChevronRight,
  Database,
  EyeOff,
  PanelRightOpen,
  RefreshCw,
  RotateCcw,
  Search,
  SlidersHorizontal,
  X,
} from 'lucide-react'

import DashboardLayout from '../layouts/DashboardLayout'
import WorkspacePageHeader from '../components/ui/WorkspacePageHeader'
import {
  exploreTable,
  getBanks,
  getTableExplorerOptions,
  getTables,
} from '../services/dataWarehouseService'

import '../styles/table-explorer-vibe.css'

const monthLabels = {
  1: 'Januari',
  2: 'Februari',
  3: 'Maret',
  4: 'April',
  5: 'Mei',
  6: 'Juni',
  7: 'Juli',
  8: 'Agustus',
  9: 'September',
  10: 'Oktober',
  11: 'November',
  12: 'Desember',
}

function formatNumber(value) {
  if (
    value === null ||
    value === undefined
  ) {
    return '-'
  }

  return new Intl.NumberFormat('id-ID').format(
    Number(value),
  )
}

function displayValue(value) {
  if (
    value === null ||
    value === undefined ||
    value === ''
  ) {
    return '—'
  }

  if (typeof value === 'object') {
    return JSON.stringify(value)
  }

  return String(value)
}

function TableExplorer() {
  const [tables, setTables] = useState([])
  const [banks, setBanks] = useState([])
  const [selectedTable, setSelectedTable] = useState('')

  const [options, setOptions] = useState(null)
  const [result, setResult] = useState(null)

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [bankId, setBankId] = useState('')
  const [month, setMonth] = useState('')
  const [year, setYear] = useState('')

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [sortColumn, setSortColumn] = useState('')
  const [sortDirection, setSortDirection] = useState('asc')

  const [selectedRow, setSelectedRow] = useState(null)
  const [loadingMeta, setLoadingMeta] = useState(true)
  const [loadingData, setLoadingData] = useState(false)
  const [error, setError] = useState('')

  const tableOptions = useMemo(
    () =>
      tables.map((table) => ({
        value: table,
        label: table,
      })),
    [tables],
  )

  const bankNameById = useMemo(
    () =>
      Object.fromEntries(
        banks.map((bank) => [
          String(bank.bank_id),
          bank.bank_name,
        ]),
      ),
    [banks],
  )

  const bankOptions = useMemo(
    () => [
      {
        value: '',
        label: 'Semua bank',
      },
      ...((options?.filters?.bank_ids || []).map(
        (id) => ({
          value: String(id),
          label:
            bankNameById[String(id)] ||
            String(id),
        }),
      )),
    ],
    [options, bankNameById],
  )

  const monthOptions = useMemo(
    () => [
      {
        value: '',
        label: 'Semua bulan',
      },
      ...((options?.filters?.months || []).map(
        (value) => ({
          value: Number(value),
          label:
            monthLabels[Number(value)] ||
            String(value),
        }),
      )),
    ],
    [options],
  )

  const yearOptions = useMemo(
    () => [
      {
        value: '',
        label: 'Semua tahun',
      },
      ...((options?.filters?.years || []).map(
        (value) => ({
          value: Number(value),
          label: String(value),
        }),
      )),
    ],
    [options],
  )

  const pageSizeOptions = [
    { value: 20, label: '20 rows' },
    { value: 50, label: '50 rows' },
    { value: 100, label: '100 rows' },
  ]

  const columns =
    options?.columns || []

  const rows =
    result?.rows || []

  const pagination =
    result?.pagination || {
      page: 1,
      page_size: pageSize,
      total_rows: 0,
      total_pages: 1,
    }

  async function loadInitial() {
    try {
      setLoadingMeta(true)
      setError('')

      const [tableResponse, bankResponse] =
        await Promise.all([
          getTables(),
          getBanks(),
        ])

      const tableList = Array.isArray(
        tableResponse?.tables,
      )
        ? tableResponse.tables
        : []

      const bankList = Array.isArray(
        bankResponse?.banks,
      )
        ? bankResponse.banks
        : []

      setTables(tableList)
      setBanks(bankList)

      if (tableList.length > 0) {
        setSelectedTable(
          (current) =>
            current || tableList[0],
        )
      }
    } catch (err) {
      console.error(err)
      setError(
        err.message ||
          'Gagal memuat Table Explorer.',
      )
    } finally {
      setLoadingMeta(false)
    }
  }

  async function loadOptions(tableName) {
    if (!tableName) return

    try {
      setLoadingMeta(true)
      setError('')

      const response =
        await getTableExplorerOptions(
          tableName,
        )

      setOptions(response)
    } catch (err) {
      console.error(err)
      setOptions(null)
      setError(
        err.message ||
          'Gagal membaca schema tabel.',
      )
    } finally {
      setLoadingMeta(false)
    }
  }

  async function loadData() {
    if (!selectedTable) return

    try {
      setLoadingData(true)
      setError('')

      const response = await exploreTable({
        tableName: selectedTable,
        page,
        pageSize,
        search: debouncedSearch,
        bankId,
        month,
        year,
        sortColumn,
        sortDirection,
      })

      setResult(response)

      if (
        response?.pagination?.page &&
        response.pagination.page !== page
      ) {
        setPage(response.pagination.page)
      }
    } catch (err) {
      console.error(err)
      setResult(null)
      setError(
        err.message ||
          'Gagal membaca isi tabel.',
      )
    } finally {
      setLoadingData(false)
    }
  }

  useEffect(() => {
    loadInitial()
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(
      () => {
        setDebouncedSearch(
          search.trim(),
        )
        setPage(1)
      },
      350,
    )

    return () =>
      window.clearTimeout(timer)
  }, [search])

  useEffect(() => {
    if (!selectedTable) return

    setBankId('')
    setMonth('')
    setYear('')
    setSearch('')
    setDebouncedSearch('')
    setPage(1)
    setPageSize(20)
    setSortColumn('')
    setSortDirection('asc')
    setSelectedRow(null)
    setResult(null)

    loadOptions(selectedTable)
  }, [selectedTable])

  useEffect(() => {
    loadData()
  }, [
    selectedTable,
    debouncedSearch,
    bankId,
    month,
    year,
    page,
    pageSize,
    sortColumn,
    sortDirection,
  ])

  function resetFilters() {
    setSearch('')
    setDebouncedSearch('')
    setBankId('')
    setMonth('')
    setYear('')
    setPage(1)
    setSortColumn('')
    setSortDirection('asc')
    setSelectedRow(null)
  }

  function toggleSort(columnName) {
    setPage(1)

    if (sortColumn !== columnName) {
      setSortColumn(columnName)
      setSortDirection('asc')
      return
    }

    if (sortDirection === 'asc') {
      setSortDirection('desc')
      return
    }

    setSortColumn('')
    setSortDirection('asc')
  }

  function sortIcon(columnName) {
    if (sortColumn !== columnName) {
      return null
    }

    return sortDirection === 'desc'
      ? <ArrowDown size={12} />
      : <ArrowUp size={12} />
  }

  return (
    <DashboardLayout>
      <main className="tp-table-explorer mx-auto w-full max-w-[1480px] space-y-5">
        <WorkspacePageHeader
          eyebrow="Data Warehouse"
          title="Table Explorer"
          description="Browse isi tabel warehouse, filter berdasarkan bank dan periode, lakukan pencarian, sorting, serta inspeksi detail row."
          icon={Database}
          badge="Data Browser"
        />

        {error && (
          <div className="tp-explorer-error">
            {error}
          </div>
        )}

        <section className="tp-explorer-toolbar">
          <div className="tp-explorer-toolbar-top">
            <div className="tp-explorer-table-select">
              <label>Table</label>

              <Dropdown
                options={tableOptions}
                value={
                  tableOptions.find(
                    (option) =>
                      option.value ===
                      selectedTable,
                  ) || null
                }
                onChange={(option) =>
                  setSelectedTable(
                    option?.value || '',
                  )
                }
                searchable
                clearable={false}
                disabled={
                  loadingMeta ||
                  tableOptions.length === 0
                }
                className="tp-vibe-dropdown"
              />
            </div>

            <div className="tp-explorer-search">
              <Search size={16} />
              <input
                value={search}
                onChange={(event) =>
                  setSearch(event.target.value)
                }
                placeholder="Cari nilai di kolom yang tidak dimasking..."
                disabled={!selectedTable}
              />

              {search && (
                <button
                  type="button"
                  onClick={() => setSearch('')}
                  aria-label="Hapus pencarian"
                  title="Hapus pencarian"
                >
                  <X size={14} />
                </button>
              )}
            </div>

            <button
              type="button"
              className="tp-explorer-icon-button"
              onClick={() => {
                loadOptions(selectedTable)
                loadData()
              }}
              disabled={
                !selectedTable ||
                loadingData
              }
              title="Refresh data"
            >
              <RefreshCw
                size={16}
                className={
                  loadingData
                    ? 'animate-spin'
                    : ''
                }
              />
            </button>
          </div>

          <div className="tp-explorer-filters">
            <div className="tp-explorer-filter-title">
              <SlidersHorizontal size={14} />
              Filters
            </div>

            <div className="tp-explorer-filter-control">
              <label>Bank</label>
              <Dropdown
                options={bankOptions}
                value={
                  bankOptions.find(
                    (option) =>
                      option.value ===
                      bankId,
                  ) || bankOptions[0]
                }
                onChange={(option) => {
                  setBankId(
                    option?.value || '',
                  )
                  setPage(1)
                }}
                searchable
                clearable={false}
                disabled={!selectedTable}
                className="tp-vibe-dropdown"
              />
            </div>

            <div className="tp-explorer-filter-control">
              <label>Bulan</label>
              <Dropdown
                options={monthOptions}
                value={
                  monthOptions.find(
                    (option) =>
                      option.value ===
                      month,
                  ) || monthOptions[0]
                }
                onChange={(option) => {
                  setMonth(
                    option?.value ?? '',
                  )
                  setPage(1)
                }}
                searchable={false}
                clearable={false}
                disabled={!selectedTable}
                className="tp-vibe-dropdown"
              />
            </div>

            <div className="tp-explorer-filter-control">
              <label>Tahun</label>
              <Dropdown
                options={yearOptions}
                value={
                  yearOptions.find(
                    (option) =>
                      option.value ===
                      year,
                  ) || yearOptions[0]
                }
                onChange={(option) => {
                  setYear(
                    option?.value ?? '',
                  )
                  setPage(1)
                }}
                searchable={false}
                clearable={false}
                disabled={!selectedTable}
                className="tp-vibe-dropdown"
              />
            </div>

            <button
              type="button"
              className="tp-explorer-reset-button"
              onClick={resetFilters}
              disabled={!selectedTable}
            >
              <RotateCcw size={13} />
              Reset
            </button>
          </div>
        </section>

        <section className="tp-explorer-data-panel">
          <div className="tp-explorer-data-header">
            <div>
              <h2>
                {selectedTable ||
                  'Table data'}
              </h2>

              <p>
                {formatNumber(
                  pagination.total_rows,
                )}{' '}
                rows
                {debouncedSearch ||
                bankId ||
                month ||
                year
                  ? ' sesuai filter'
                  : ' total'}
              </p>
            </div>

            <div className="tp-explorer-page-size">
              <span>Show</span>

              <Dropdown
                options={pageSizeOptions}
                value={
                  pageSizeOptions.find(
                    (option) =>
                      option.value ===
                      pageSize,
                  ) || pageSizeOptions[0]
                }
                onChange={(option) => {
                  setPageSize(
                    Number(
                      option?.value || 20,
                    ),
                  )
                  setPage(1)
                }}
                searchable={false}
                clearable={false}
                className="tp-vibe-dropdown"
              />
            </div>
          </div>

          <div className="tp-explorer-table-wrap">
            <table className="tp-explorer-table">
              <thead>
                <tr>
                  <th className="tp-explorer-row-number">
                    #
                  </th>

                  {columns.map((column) => (
                    <th
                      key={column.column_name}
                    >
                      <button
                        type="button"
                        className={`tp-explorer-sort-button ${
                          column.masked
                            ? 'is-masked'
                            : ''
                        }`}
                        onClick={() => {
                          if (!column.masked) {
                            toggleSort(
                              column.column_name,
                            )
                          }
                        }}
                        disabled={column.masked}
                        title={
                          column.masked
                            ? 'Kolom dimasking'
                            : `Sort ${column.column_name}`
                        }
                      >
                        <span className="tp-explorer-header-label">
                          {column.column_name}

                          {column.masked && (
                            <EyeOff
                              size={11}
                            />
                          )}
                        </span>

                        {!column.masked &&
                          sortIcon(
                            column.column_name,
                          )}
                      </button>
                    </th>
                  ))}

                  <th className="tp-explorer-inspect-column">
                    Inspect
                  </th>
                </tr>
              </thead>

              <tbody>
                {loadingData ? (
                  <tr>
                    <td
                      colSpan={
                        columns.length + 2
                      }
                      className="tp-explorer-empty"
                    >
                      Membaca data...
                    </td>
                  </tr>
                ) : rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={
                        columns.length + 2
                      }
                      className="tp-explorer-empty"
                    >
                      Tidak ada data yang sesuai
                      dengan filter.
                    </td>
                  </tr>
                ) : (
                  rows.map((row, index) => {
                    const rowNumber =
                      (pagination.page - 1) *
                        pagination.page_size +
                      index +
                      1

                    return (
                      <tr
                        key={`${pagination.page}-${index}`}
                        onClick={() =>
                          setSelectedRow({
                            row,
                            rowNumber,
                          })
                        }
                      >
                        <td className="tp-explorer-row-number">
                          {formatNumber(
                            rowNumber,
                          )}
                        </td>

                        {columns.map(
                          (column) => (
                            <td
                              key={
                                column.column_name
                              }
                              className={
                                column.masked
                                  ? 'tp-explorer-masked-cell'
                                  : ''
                              }
                              title={
                                column.masked
                                  ? 'Data dimasking'
                                  : displayValue(
                                      row[
                                        column
                                          .column_name
                                      ],
                                    )
                              }
                            >
                              <span className="tp-explorer-cell-value">
                                {displayValue(
                                  row[
                                    column
                                      .column_name
                                  ],
                                )}
                              </span>
                            </td>
                          ),
                        )}

                        <td className="tp-explorer-inspect-column">
                          <button
                            type="button"
                            className="tp-explorer-inspect-button"
                            onClick={(event) => {
                              event.stopPropagation()
                              setSelectedRow({
                                row,
                                rowNumber,
                              })
                            }}
                            title="Inspect row"
                          >
                            <PanelRightOpen
                              size={14}
                            />
                          </button>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="tp-explorer-pagination">
            <div className="tp-explorer-pagination-info">
              Page{' '}
              <strong>
                {pagination.page}
              </strong>{' '}
              of{' '}
              <strong>
                {pagination.total_pages}
              </strong>
            </div>

            <div className="tp-explorer-pagination-actions">
              <button
                type="button"
                onClick={() => setPage(1)}
                disabled={
                  pagination.page <= 1 ||
                  loadingData
                }
                title="Halaman pertama"
              >
                <ChevronsLeft size={15} />
              </button>

              <button
                type="button"
                onClick={() =>
                  setPage((current) =>
                    Math.max(
                      1,
                      current - 1,
                    ),
                  )
                }
                disabled={
                  pagination.page <= 1 ||
                  loadingData
                }
                title="Halaman sebelumnya"
              >
                <ChevronLeft size={15} />
              </button>

              <span>
                {pagination.page} /{' '}
                {pagination.total_pages}
              </span>

              <button
                type="button"
                onClick={() =>
                  setPage((current) =>
                    Math.min(
                      pagination.total_pages,
                      current + 1,
                    ),
                  )
                }
                disabled={
                  pagination.page >=
                    pagination.total_pages ||
                  loadingData
                }
                title="Halaman berikutnya"
              >
                <ChevronRight size={15} />
              </button>

              <button
                type="button"
                onClick={() =>
                  setPage(
                    pagination.total_pages,
                  )
                }
                disabled={
                  pagination.page >=
                    pagination.total_pages ||
                  loadingData
                }
                title="Halaman terakhir"
              >
                <ChevronsRight size={15} />
              </button>
            </div>
          </div>
        </section>

        {selectedRow && (
          <>
            <button
              type="button"
              className="tp-explorer-drawer-backdrop"
              onClick={() =>
                setSelectedRow(null)
              }
              aria-label="Tutup row inspector"
            />

            <aside className="tp-explorer-drawer">
              <div className="tp-explorer-drawer-header">
                <div>
                  <span>Row Inspector</span>
                  <h3>
                    Row #
                    {formatNumber(
                      selectedRow.rowNumber,
                    )}
                  </h3>
                </div>

                <button
                  type="button"
                  onClick={() =>
                    setSelectedRow(null)
                  }
                  title="Tutup"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="tp-explorer-drawer-meta">
                <Database size={13} />
                {selectedTable}
              </div>

              <div className="tp-explorer-drawer-fields">
                {columns.map((column) => (
                  <div
                    key={column.column_name}
                    className="tp-explorer-drawer-field"
                  >
                    <div className="tp-explorer-drawer-field-header">
                      <span>
                        {column.column_name}
                      </span>

                      <div className="tp-explorer-drawer-field-meta">
                        {column.masked && (
                          <span className="tp-explorer-masked-badge">
                            <EyeOff
                              size={9}
                            />
                            Masked
                          </span>
                        )}

                        <small>
                          {column.data_type}
                        </small>
                      </div>
                    </div>

                    <div className="tp-explorer-drawer-value">
                      {displayValue(
                        selectedRow.row[
                          column.column_name
                        ],
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </aside>
          </>
        )}
      </main>
    </DashboardLayout>
  )
}

export default TableExplorer
