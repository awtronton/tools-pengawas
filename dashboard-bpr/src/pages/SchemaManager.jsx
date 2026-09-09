import {
  useEffect,
  useMemo,
  useState,
} from 'react'
import {
  Button,
  Dropdown,
} from '@vibe/core'
import {
  AlertCircle,
  ArrowRightLeft,
  Braces,
  Columns3,
  Database,
  EyeOff,
  GitBranch,
  Layers3,
  Link2,
  LockKeyhole,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Table2,
  Trash2,
  Workflow,
} from 'lucide-react'

import DashboardLayout from '../layouts/DashboardLayout'
import WorkspacePageHeader from '../components/ui/WorkspacePageHeader'
import CardinalityHelper from '../components/schema/CardinalityHelper'
import RelationshipCanvas from '../components/schema/RelationshipCanvas'
import VisualSqlBuilder from '../components/schema/VisualSqlBuilder'
import {
  createTableRelationship,
  deleteTableRelationship,
  getTableDetail,
  getTableRelationships,
  getTables,
  updateTableRelationship,
} from '../services/dataWarehouseService'

import '../styles/schema-manager-vibe.css'

const cardinalityOptions = [
  {
    value: 'one_to_one',
    label: 'One-to-One (1:1)',
  },
  {
    value: 'one_to_many',
    label: 'One-to-Many (1:N)',
  },
  {
    value: 'many_to_one',
    label: 'Many-to-One (N:1)',
  },
  {
    value: 'many_to_many',
    label: 'Many-to-Many (N:N)',
  },
]

const cardinalityLabel = Object.fromEntries(
  cardinalityOptions.map((item) => [
    item.value,
    item.label,
  ]),
)

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

function periodLabel(summary) {
  if (
    !summary?.min_year &&
    !summary?.max_year
  ) {
    return '-'
  }

  if (
    summary.min_year ===
    summary.max_year
  ) {
    return String(summary.min_year)
  }

  return `${summary.min_year ?? '-'}–${summary.max_year ?? '-'}`
}

function normalizeRelationshipType(value) {
  const type = String(
    value || '',
  ).toUpperCase()

  if (
    /SMALLINT|INTEGER|BIGINT|NUMERIC|DECIMAL|REAL|FLOAT|DOUBLE/.test(
      type,
    )
  ) {
    return 'numeric'
  }

  if (
    /CHAR|TEXT|STRING|VARCHAR/.test(
      type,
    )
  ) {
    return 'text'
  }

  if (/TIMESTAMP/.test(type)) {
    return 'timestamp'
  }

  if (/^DATE/.test(type)) {
    return 'date'
  }

  if (/BOOL/.test(type)) {
    return 'boolean'
  }

  return type
}

function emptyRelationshipPair() {
  return {
    source_column: '',
    target_column: '',
  }
}

function SchemaManager() {
  const [activeTab, setActiveTab] =
    useState('review')

  const [tables, setTables] = useState([])
  const [selectedTable, setSelectedTable] =
    useState('')
  const [detail, setDetail] = useState(null)

  const [search, setSearch] = useState('')
  const [columnFilter, setColumnFilter] =
    useState('all')

  const [relationships, setRelationships] =
    useState([])

  const [sourceTable, setSourceTable] =
    useState('')
  const [targetTable, setTargetTable] =
    useState('')
  const [columnPairs, setColumnPairs] =
    useState([
      emptyRelationshipPair(),
    ])
  const [cardinality, setCardinality] =
    useState('one_to_many')
  const [relationshipName, setRelationshipName] =
    useState('')
  const [canvasDraft, setCanvasDraft] =
    useState(null)

  const [sourceDetail, setSourceDetail] =
    useState(null)
  const [targetDetail, setTargetDetail] =
    useState(null)

  const [loadingTables, setLoadingTables] =
    useState(true)
  const [loadingDetail, setLoadingDetail] =
    useState(false)
  const [
    loadingRelationships,
    setLoadingRelationships,
  ] = useState(false)
  const [savingRelationship, setSavingRelationship] =
    useState(false)

  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const tableOptions = useMemo(
    () =>
      tables.map((table) => ({
        value: table,
        label: table,
      })),
    [tables],
  )

  const filterOptions = [
    {
      value: 'all',
      label: 'Semua kolom',
    },
    {
      value: 'business',
      label: 'Business columns',
    },
    {
      value: 'system',
      label: 'System columns',
    },
    {
      value: 'masked',
      label: 'Masked columns',
    },
    {
      value: 'unmapped',
      label: 'Unmapped columns',
    },
  ]

  const columns = detail?.columns || []

  const schemaStats = useMemo(() => {
    const businessColumns = columns.filter(
      (column) => !column.system_column,
    )

    const mappedBusinessColumns =
      businessColumns.filter((column) =>
        Boolean(column.source_column),
      )

    const maskedColumns = columns.filter(
      (column) => column.masked,
    )

    const systemColumns = columns.filter(
      (column) => column.system_column,
    )

    const mappingCoverage =
      businessColumns.length > 0
        ? Math.round(
            (mappedBusinessColumns.length /
              businessColumns.length) *
              100,
          )
        : 100

    return {
      businessColumns: businessColumns.length,
      maskedColumns: maskedColumns.length,
      systemColumns: systemColumns.length,
      mappingCoverage,
    }
  }, [columns])

  const filteredColumns = useMemo(() => {
    const keyword =
      search.trim().toLowerCase()

    return columns.filter((column) => {
      const matchesSearch =
        !keyword ||
        column.column_name
          .toLowerCase()
          .includes(keyword) ||
        String(
          column.source_column || '',
        )
          .toLowerCase()
          .includes(keyword) ||
        String(column.data_type || '')
          .toLowerCase()
          .includes(keyword)

      if (!matchesSearch) return false

      if (columnFilter === 'business') {
        return !column.system_column
      }

      if (columnFilter === 'system') {
        return column.system_column
      }

      if (columnFilter === 'masked') {
        return column.masked
      }

      if (columnFilter === 'unmapped') {
        return (
          !column.system_column &&
          !column.source_column
        )
      }

      return true
    })
  }, [
    columns,
    search,
    columnFilter,
  ])

  const sourceColumnOptions = useMemo(
    () =>
      (sourceDetail?.columns || []).map(
        (column) => ({
          value: column.column_name,
          label: column.column_name,
          dataType: column.data_type,
          masked: column.masked,
        }),
      ),
    [sourceDetail],
  )

  const targetColumnOptions = useMemo(
    () =>
      (targetDetail?.columns || []).map(
        (column) => ({
          value: column.column_name,
          label: column.column_name,
          dataType: column.data_type,
          masked: column.masked,
        }),
      ),
    [targetDetail],
  )

  const relationshipPairDetails =
    useMemo(
      () =>
        columnPairs.map((pair) => {
          const source =
            sourceColumnOptions.find(
              (option) =>
                option.value ===
                pair.source_column,
            ) || null

          const target =
            targetColumnOptions.find(
              (option) =>
                option.value ===
                pair.target_column,
            ) || null

          const compatible =
            source && target
              ? normalizeRelationshipType(
                  source.dataType,
                ) ===
                normalizeRelationshipType(
                  target.dataType,
                )
              : null

          return {
            ...pair,
            source,
            target,
            compatible,
          }
        }),
      [
        columnPairs,
        sourceColumnOptions,
        targetColumnOptions,
      ],
    )

  const periodKeyAvailable =
    useMemo(() => {
      const required = [
        'bank_id',
        'bulan',
        'tahun',
      ]

      const sourceSet = new Set(
        sourceColumnOptions.map(
          (option) => option.value,
        ),
      )
      const targetSet = new Set(
        targetColumnOptions.map(
          (option) => option.value,
        ),
      )

      return required.every(
        (column) =>
          sourceSet.has(column) &&
          targetSet.has(column),
      )
    }, [
      sourceColumnOptions,
      targetColumnOptions,
    ])

  async function loadTables({
    preserveSelection = true,
  } = {}) {
    try {
      setLoadingTables(true)
      setError('')

      const response = await getTables()
      const rows = Array.isArray(
        response?.tables,
      )
        ? response.tables
        : []

      setTables(rows)

      if (
        preserveSelection &&
        selectedTable &&
        rows.includes(selectedTable)
      ) {
        return
      }

      if (rows.length > 0) {
        setSelectedTable(rows[0])

        setSourceTable(
          (current) =>
            current || rows[0],
        )

        setTargetTable(
          (current) =>
            current ||
            rows[Math.min(1, rows.length - 1)],
        )
      } else {
        setSelectedTable('')
        setDetail(null)
      }
    } catch (err) {
      console.error(err)
      setError(
        err.message ||
          'Gagal membaca daftar tabel.',
      )
    } finally {
      setLoadingTables(false)
    }
  }

  async function loadDetail(tableName) {
    if (!tableName) {
      setDetail(null)
      return
    }

    try {
      setLoadingDetail(true)
      setError('')

      const response =
        await getTableDetail(tableName)

      setDetail(response)
    } catch (err) {
      console.error(err)
      setDetail(null)
      setError(
        err.message ||
          'Gagal membaca schema tabel.',
      )
    } finally {
      setLoadingDetail(false)
    }
  }

  async function loadRelationshipDetail(
    tableName,
    setter,
  ) {
    if (!tableName) {
      setter(null)
      return
    }

    try {
      const response =
        await getTableDetail(tableName)

      setter(response)
    } catch (err) {
      console.error(err)
      setError(
        err.message ||
          'Gagal membaca column relationship.',
      )
    }
  }

  async function loadRelationships() {
    try {
      setLoadingRelationships(true)
      setError('')

      const response =
        await getTableRelationships()

      setRelationships(
        Array.isArray(
          response?.relationships,
        )
          ? response.relationships
          : [],
      )
    } catch (err) {
      console.error(err)
      setError(
        err.message ||
          'Gagal membaca relationship.',
      )
    } finally {
      setLoadingRelationships(false)
    }
  }

  useEffect(() => {
    loadTables({
      preserveSelection: false,
    })
    loadRelationships()
  }, [])

  useEffect(() => {
    setSearch('')
    setColumnFilter('all')
    loadDetail(selectedTable)
  }, [selectedTable])

  useEffect(() => {
    setColumnPairs([
      emptyRelationshipPair(),
    ])
    loadRelationshipDetail(
      sourceTable,
      setSourceDetail,
    )
  }, [sourceTable])

  useEffect(() => {
    setColumnPairs([
      emptyRelationshipPair(),
    ])
    loadRelationshipDetail(
      targetTable,
      setTargetDetail,
    )
  }, [targetTable])

  useEffect(() => {
    if (
      !canvasDraft ||
      !sourceDetail ||
      !targetDetail
    ) {
      return
    }

    const sourceReady =
      sourceDetail?.summary
        ?.table_name ===
      canvasDraft.sourceTable

    const targetReady =
      targetDetail?.summary
        ?.table_name ===
      canvasDraft.targetTable

    if (
      !sourceReady ||
      !targetReady
    ) {
      return
    }

    const sourceExists =
      (sourceDetail.columns || []).some(
        (column) =>
          column.column_name ===
          canvasDraft.sourceColumn,
      )

    const targetExists =
      (targetDetail.columns || []).some(
        (column) =>
          column.column_name ===
          canvasDraft.targetColumn,
      )

    if (
      sourceExists &&
      targetExists
    ) {
      setColumnPairs([
        {
          source_column:
            canvasDraft.sourceColumn,
          target_column:
            canvasDraft.targetColumn,
        },
      ])

      setMessage(
        'Connection dari canvas sudah dipilih sebagai key pertama. Tambahkan key lain bila relationship memerlukan composite key.',
      )
    }

    setCanvasDraft(null)
  }, [
    canvasDraft,
    sourceDetail,
    targetDetail,
  ])

  function applyCanvasConnection(
    draft,
  ) {
    setError('')
    setMessage('')

    setSourceTable(
      draft.sourceTable,
    )
    setTargetTable(
      draft.targetTable,
    )
    setCanvasDraft(draft)
  }

  function updateRelationshipPair(
    index,
    field,
    value,
  ) {
    setColumnPairs((current) =>
      current.map((pair, pairIndex) =>
        pairIndex === index
          ? {
              ...pair,
              [field]: value,
            }
          : pair,
      ),
    )
  }

  function addRelationshipPair() {
    setColumnPairs((current) => [
      ...current,
      emptyRelationshipPair(),
    ])
  }

  function removeRelationshipPair(index) {
    setColumnPairs((current) => {
      if (current.length <= 1) {
        return [
          emptyRelationshipPair(),
        ]
      }

      return current.filter(
        (_, pairIndex) =>
          pairIndex !== index,
      )
    })
  }

  function applyPeriodCompositeKey() {
    if (!periodKeyAvailable) {
      return
    }

    setColumnPairs(
      [
        'bank_id',
        'bulan',
        'tahun',
      ].map((column) => ({
        source_column: column,
        target_column: column,
      })),
    )

    setMessage(
      'Composite key bank_id + bulan + tahun diterapkan.',
    )
  }

  async function saveRelationship() {
    if (
      !sourceTable ||
      !targetTable
    ) {
      setError(
        'Source Table dan Target Table harus dipilih.',
      )
      return
    }

    const incompletePair =
      columnPairs.some(
        (pair) =>
          !pair.source_column ||
          !pair.target_column,
      )

    if (incompletePair) {
      setError(
        'Setiap pasangan join harus memiliki Source Column dan Target Column.',
      )
      return
    }

    const signatures =
      columnPairs.map(
        (pair) =>
          `${pair.source_column}::${pair.target_column}`,
      )

    if (
      new Set(signatures).size !==
      signatures.length
    ) {
      setError(
        'Pasangan join tidak boleh duplikat.',
      )
      return
    }

    const invalidSelfPair =
      sourceTable === targetTable &&
      columnPairs.some(
        (pair) =>
          pair.source_column ===
          pair.target_column,
      )

    if (invalidSelfPair) {
      setError(
        'Source dan target tidak boleh merupakan kolom yang sama.',
      )
      return
    }

    try {
      setSavingRelationship(true)
      setError('')
      setMessage('')

      const primaryPair =
        columnPairs[0]

      const response =
        await createTableRelationship({
          relationship_name:
            relationshipName.trim() || null,
          source_table: sourceTable,
          source_column:
            primaryPair.source_column,
          target_table: targetTable,
          target_column:
            primaryPair.target_column,
          column_pairs:
            columnPairs.map(
              (pair) => ({
                source_column:
                  pair.source_column,
                target_column:
                  pair.target_column,
              }),
            ),
          cardinality,
        })

      setRelationshipName('')
      setColumnPairs([
        emptyRelationshipPair(),
      ])
      await loadRelationships()

      const warning =
        response?.relationship
          ?.compatibility_message

      const pairCount =
        response?.relationship
          ?.pair_count ||
        columnPairs.length

      setMessage(
        warning
          ? `Relationship ${pairCount} key disimpan. ${warning}`
          : `Relationship ${pairCount} key berhasil disimpan.`,
      )
    } catch (err) {
      console.error(err)
      setError(
        err.message ||
          'Gagal membuat relationship.',
      )
    } finally {
      setSavingRelationship(false)
    }
  }

  async function toggleRelationship(
    relationship,
  ) {
    try {
      setError('')
      setMessage('')

      await updateTableRelationship(
        relationship.id,
        {
          is_active:
            !relationship.is_active,
        },
      )

      await loadRelationships()
    } catch (err) {
      console.error(err)
      setError(
        err.message ||
          'Gagal memperbarui relationship.',
      )
    }
  }

  async function removeRelationship(
    relationship,
  ) {
    const pairSummary = (
      relationship.column_pairs || [
        {
          source_column:
            relationship.source_column,
          target_column:
            relationship.target_column,
        },
      ]
    )
      .map(
        (pair) =>
          `${relationship.source_table}.${pair.source_column} ↔ ` +
          `${relationship.target_table}.${pair.target_column}`,
      )
      .join('\n')

    const confirmed = window.confirm(
      `Hapus relationship?\n\n` +
        `${relationship.relationship_name}\n` +
        pairSummary,
    )

    if (!confirmed) return

    try {
      setError('')
      setMessage('')

      await deleteTableRelationship(
        relationship.id,
      )

      await loadRelationships()

      setMessage(
        'Relationship berhasil dihapus.',
      )
    } catch (err) {
      console.error(err)
      setError(
        err.message ||
          'Gagal menghapus relationship.',
      )
    }
  }

  return (
    <DashboardLayout>
      <main className="tp-schema-manager mx-auto w-full max-w-[1480px] space-y-5">
        <WorkspacePageHeader
          eyebrow="Data Warehouse"
          title="Schema Manager"
          description="Review schema, definisikan relationship antar tabel, dan siapkan semantic layer untuk Visual SQL Builder."
          icon={Braces}
          badge="Schema Workspace"
        />

        <nav className="tp-schema-tabs">
          <button
            type="button"
            className={`tp-schema-tab ${
              activeTab === 'review'
                ? 'is-active'
                : ''
            }`}
            onClick={() =>
              setActiveTab('review')
            }
          >
            <Columns3 size={14} />
            Schema Review
          </button>

          <button
            type="button"
            className={`tp-schema-tab ${
              activeTab === 'relationships'
                ? 'is-active'
                : ''
            }`}
            onClick={() =>
              setActiveTab('relationships')
            }
          >
            <GitBranch size={14} />
            Relationship Designer
            <span>Foundation</span>
          </button>

          <button
            type="button"
            className={`tp-schema-tab ${
              activeTab === 'sql'
                ? 'is-active'
                : ''
            }`}
            onClick={() =>
              setActiveTab('sql')
            }
          >
            <Workflow size={14} />
            Visual SQL Builder
            <span>Foundation</span>
          </button>
        </nav>

        {error && (
          <div className="tp-schema-error">
            <AlertCircle size={14} />
            {error}
          </div>
        )}

        {message && (
          <div className="tp-schema-message">
            {message}
          </div>
        )}

        {activeTab === 'review' ? (
          <>
            <section className="tp-schema-toolbar">
              <div className="tp-schema-table-select">
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
                    loadingTables ||
                    tableOptions.length === 0
                  }
                  className="tp-vibe-dropdown"
                />
              </div>

              <div className="tp-schema-search">
                <Search size={16} />
                <input
                  value={search}
                  onChange={(event) =>
                    setSearch(
                      event.target.value,
                    )
                  }
                  placeholder="Cari column, source, atau datatype..."
                  disabled={!selectedTable}
                />
              </div>

              <div className="tp-schema-filter">
                <label>View</label>

                <Dropdown
                  options={filterOptions}
                  value={
                    filterOptions.find(
                      (option) =>
                        option.value ===
                        columnFilter,
                    ) || filterOptions[0]
                  }
                  onChange={(option) =>
                    setColumnFilter(
                      option?.value || 'all',
                    )
                  }
                  searchable={false}
                  clearable={false}
                  disabled={!selectedTable}
                  className="tp-vibe-dropdown"
                />
              </div>

              <button
                type="button"
                className="tp-schema-refresh"
                onClick={() => {
                  loadTables()
                  loadDetail(selectedTable)
                }}
                disabled={
                  !selectedTable ||
                  loadingTables ||
                  loadingDetail
                }
                title="Refresh schema"
              >
                <RefreshCw
                  size={16}
                  className={
                    loadingTables ||
                    loadingDetail
                      ? 'animate-spin'
                      : ''
                  }
                />
              </button>
            </section>

            {detail?.summary && (
              <section className="tp-schema-overview">
                <div className="tp-schema-overview-title">
                  <div>
                    <span>
                      Schema Overview
                    </span>
                    <h2>
                      {selectedTable}
                    </h2>
                  </div>

                  <ShieldCheck
                    size={19}
                  />
                </div>

                <div className="tp-schema-metrics">
                  <div>
                    <span>Rows</span>
                    <strong>
                      {formatNumber(
                        detail.summary
                          .row_count,
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>Columns</span>
                    <strong>
                      {formatNumber(
                        detail.summary
                          .column_count,
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>Business</span>
                    <strong>
                      {formatNumber(
                        schemaStats
                          .businessColumns,
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>System</span>
                    <strong>
                      {formatNumber(
                        schemaStats
                          .systemColumns,
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>Masked</span>
                    <strong>
                      {formatNumber(
                        schemaStats
                          .maskedColumns,
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>Mapping</span>
                    <strong>
                      {schemaStats
                        .mappingCoverage}
                      %
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
              </section>
            )}

            <section className="tp-schema-review-panel">
              <div className="tp-schema-review-header">
                <div>
                  <h2>Column Schema</h2>
                  <p>
                    {
                      filteredColumns.length
                    }{' '}
                    dari {columns.length} kolom
                    ditampilkan.
                  </p>
                </div>

                <div className="tp-schema-readonly-badge">
                  <LockKeyhole
                    size={12}
                  />
                  Review-only
                </div>
              </div>

              <div className="tp-schema-table-wrap">
                <table className="tp-schema-table">
                  <thead>
                    <tr>
                      <th className="tp-schema-ordinal">
                        #
                      </th>
                      <th>
                        Database Column
                      </th>
                      <th>
                        Source Column
                      </th>
                      <th>
                        Source Ordinal
                      </th>
                      <th>Data Type</th>
                      <th>Nullable</th>
                      <th>Role</th>
                      <th>Masking</th>
                      <th>Mapping</th>
                    </tr>
                  </thead>

                  <tbody>
                    {loadingDetail ? (
                      <tr>
                        <td
                          colSpan="9"
                          className="tp-schema-empty"
                        >
                          Membaca schema...
                        </td>
                      </tr>
                    ) : filteredColumns
                        .length === 0 ? (
                      <tr>
                        <td
                          colSpan="9"
                          className="tp-schema-empty"
                        >
                          Tidak ada kolom yang
                          sesuai dengan filter.
                        </td>
                      </tr>
                    ) : (
                      filteredColumns.map(
                        (column) => {
                          const mapped =
                            Boolean(
                              column.source_column,
                            )

                          return (
                            <tr
                              key={
                                column.column_name
                              }
                            >
                              <td className="tp-schema-ordinal">
                                {
                                  column.ordinal
                                }
                              </td>

                              <td>
                                <div className="tp-schema-column-name">
                                  {column.system_column ? (
                                    <LockKeyhole
                                      size={12}
                                    />
                                  ) : (
                                    <Table2
                                      size={12}
                                    />
                                  )}

                                  <span>
                                    {
                                      column.column_name
                                    }
                                  </span>
                                </div>
                              </td>

                              <td>
                                <span className="tp-schema-source">
                                  {column.source_column ||
                                    (column.system_column
                                      ? 'System generated'
                                      : '—')}
                                </span>
                              </td>

                              <td>
                                <span className="tp-schema-source-ordinal">
                                  {column.source_ordinal ??
                                    '—'}
                                </span>
                              </td>

                              <td>
                                <span className="tp-schema-type">
                                  {
                                    column.data_type
                                  }
                                </span>
                              </td>

                              <td>
                                <span
                                  className={`tp-schema-status ${
                                    column.nullable
                                      ? 'is-neutral'
                                      : 'is-required'
                                  }`}
                                >
                                  {column.nullable
                                    ? 'Yes'
                                    : 'No'}
                                </span>
                              </td>

                              <td>
                                <span
                                  className={`tp-schema-status ${
                                    column.system_column
                                      ? 'is-system'
                                      : 'is-business'
                                  }`}
                                >
                                  {column.system_column
                                    ? 'System'
                                    : 'Business'}
                                </span>
                              </td>

                              <td>
                                {column.masked ? (
                                  <span className="tp-schema-mask is-masked">
                                    <EyeOff
                                      size={11}
                                    />
                                    Masked
                                  </span>
                                ) : (
                                  <span className="tp-schema-mask">
                                    Visible
                                  </span>
                                )}
                              </td>

                              <td>
                                <span
                                  className={`tp-schema-status ${
                                    column.system_column
                                      ? 'is-system'
                                      : mapped
                                        ? 'is-mapped'
                                        : 'is-warning'
                                  }`}
                                >
                                  {column.system_column
                                    ? 'System'
                                    : mapped
                                      ? 'Mapped'
                                      : 'Unmapped'}
                                </span>
                              </td>
                            </tr>
                          )
                        },
                      )
                    )}
                  </tbody>
                </table>
              </div>

              <footer className="tp-schema-review-footer">
                <div>
                  <Layers3 size={13} />
                  Source mapping berasal dari
                  warehouse_schema_mapping.
                </div>

                <div>
                  <Database size={13} />
                  Relationship metadata tidak
                  mengubah PostgreSQL Foreign
                  Key.
                </div>
              </footer>
            </section>
          </>
        ) : activeTab === 'relationships' ? (
          <section className="tp-relationship-workspace">
            <div className="tp-relationship-intro">
              <div>
                <span>
                  Relationship Designer
                </span>
                <h2>
                  Semantic Relationships
                </h2>
                <p>
                  Definisikan hubungan antar
                  column sebagai metadata
                  aplikasi. Foreign Key fisik
                  PostgreSQL tidak dibuat.
                </p>
              </div>

              <div className="tp-relationship-canvas-note">
                <GitBranch size={17} />
                React Flow + ELK canvas
              </div>
            </div>

            <RelationshipCanvas
              tables={tables}
              relationships={relationships}
              onConnectionDraft={
                applyCanvasConnection
              }
            />

            <div className="tp-relationship-layout">
              <div className="tp-relationship-builder">
                <div className="tp-relationship-section-title">
                  <Plus size={14} />
                  Create Relationship
                </div>

                <div className="tp-relationship-table-grid">
                  <div className="tp-relationship-field">
                    <label>
                      Source Table
                    </label>

                    <Dropdown
                      options={tableOptions}
                      value={
                        tableOptions.find(
                          (option) =>
                            option.value ===
                            sourceTable,
                        ) || null
                      }
                      onChange={(option) =>
                        setSourceTable(
                          option?.value ||
                            '',
                        )
                      }
                      searchable
                      clearable={false}
                      className="tp-vibe-dropdown"
                    />
                  </div>

                  <div className="tp-relationship-table-connector">
                    <ArrowRightLeft
                      size={17}
                    />
                  </div>

                  <div className="tp-relationship-field">
                    <label>
                      Target Table
                    </label>

                    <Dropdown
                      options={tableOptions}
                      value={
                        tableOptions.find(
                          (option) =>
                            option.value ===
                            targetTable,
                        ) || null
                      }
                      onChange={(option) =>
                        setTargetTable(
                          option?.value ||
                            '',
                        )
                      }
                      searchable
                      clearable={false}
                      className="tp-vibe-dropdown"
                    />
                  </div>
                </div>

                <div className="tp-relationship-pairs-panel">
                  <div className="tp-relationship-pairs-header">
                    <div>
                      <strong>
                        Join Column Pairs
                      </strong>
                      <span>
                        Satu relationship dapat menggunakan satu atau beberapa key.
                      </span>
                    </div>

                    <div className="tp-relationship-pairs-actions">
                      {periodKeyAvailable && (
                        <button
                          type="button"
                          className="tp-relationship-period-key"
                          onClick={
                            applyPeriodCompositeKey
                          }
                        >
                          bank_id + bulan + tahun
                        </button>
                      )}

                      <button
                        type="button"
                        className="tp-relationship-add-pair"
                        onClick={
                          addRelationshipPair
                        }
                        disabled={
                          !sourceTable ||
                          !targetTable ||
                          columnPairs.length >=
                            12
                        }
                      >
                        <Plus size={12} />
                        Add Column Pair
                      </button>
                    </div>
                  </div>

                  <div className="tp-relationship-pair-list">
                    {relationshipPairDetails.map(
                      (pair, index) => (
                        <div
                          key={`pair-${index}`}
                          className="tp-relationship-pair-row"
                        >
                          <div className="tp-relationship-field">
                            <label>
                              Source Column{' '}
                              {index + 1}
                            </label>

                            <Dropdown
                              options={
                                sourceColumnOptions
                              }
                              value={
                                sourceColumnOptions.find(
                                  (option) =>
                                    option.value ===
                                    pair.source_column,
                                ) || null
                              }
                              onChange={(option) =>
                                updateRelationshipPair(
                                  index,
                                  'source_column',
                                  option?.value ||
                                    '',
                                )
                              }
                              searchable
                              clearable={false}
                              disabled={
                                !sourceTable
                              }
                              className="tp-vibe-dropdown"
                            />

                            {pair.source && (
                              <small className="tp-relationship-pair-type">
                                {
                                  pair.source
                                    .dataType
                                }
                                {pair.source
                                  .masked
                                  ? ' · masked'
                                  : ''}
                              </small>
                            )}
                          </div>

                          <div className="tp-relationship-pair-connector">
                            <Link2 size={13} />
                          </div>

                          <div className="tp-relationship-field">
                            <label>
                              Target Column{' '}
                              {index + 1}
                            </label>

                            <Dropdown
                              options={
                                targetColumnOptions
                              }
                              value={
                                targetColumnOptions.find(
                                  (option) =>
                                    option.value ===
                                    pair.target_column,
                                ) || null
                              }
                              onChange={(option) =>
                                updateRelationshipPair(
                                  index,
                                  'target_column',
                                  option?.value ||
                                    '',
                                )
                              }
                              searchable
                              clearable={false}
                              disabled={
                                !targetTable
                              }
                              className="tp-vibe-dropdown"
                            />

                            {pair.target && (
                              <small className="tp-relationship-pair-type">
                                {
                                  pair.target
                                    .dataType
                                }
                                {pair.target
                                  .masked
                                  ? ' · masked'
                                  : ''}
                              </small>
                            )}
                          </div>

                          <div
                            className={`tp-relationship-pair-status ${
                              pair.compatible ===
                              false
                                ? 'is-warning'
                                : pair.compatible
                                  ? 'is-compatible'
                                  : ''
                            }`}
                            title={
                              pair.compatible ===
                              false
                                ? 'Datatype berbeda'
                                : pair.compatible
                                  ? 'Datatype compatible'
                                  : 'Pilih kedua kolom'
                            }
                          >
                            {pair.compatible ===
                            false ? (
                              <AlertCircle
                                size={13}
                              />
                            ) : (
                              <ShieldCheck
                                size={13}
                              />
                            )}
                          </div>

                          <button
                            type="button"
                            className="tp-relationship-remove-pair"
                            onClick={() =>
                              removeRelationshipPair(
                                index,
                              )
                            }
                            disabled={
                              columnPairs.length <=
                              1
                            }
                            title="Hapus pasangan kolom"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      ),
                    )}
                  </div>

                  <div className="tp-relationship-pairs-note">
                    <Link2 size={12} />
                    Kondisi join akan dibentuk dengan
                    {' '}
                    <strong>AND</strong>
                    {' '}
                    untuk seluruh pasangan key.
                  </div>
                </div>

                <div className="tp-relationship-meta-grid">
                  <div className="tp-relationship-field">
                    <label>
                      Cardinality
                    </label>

                    <Dropdown
                      options={
                        cardinalityOptions
                      }
                      value={
                        cardinalityOptions.find(
                          (option) =>
                            option.value ===
                            cardinality,
                        ) ||
                        cardinalityOptions[1]
                      }
                      onChange={(option) =>
                        setCardinality(
                          option?.value ||
                            'one_to_many',
                        )
                      }
                      searchable={false}
                      clearable={false}
                      className="tp-vibe-dropdown"
                    />
                  </div>

                  <div className="tp-relationship-field">
                    <label>
                      Relationship Name
                    </label>

                    <input
                      value={
                        relationshipName
                      }
                      onChange={(event) =>
                        setRelationshipName(
                          event.target.value,
                        )
                      }
                      placeholder="Opsional — otomatis jika kosong"
                      className="tp-relationship-name-input"
                    />
                  </div>
                </div>

                <CardinalityHelper
                  cardinality={
                    cardinality
                  }
                />

                {relationshipPairDetails.some(
                  (pair) =>
                    pair.source &&
                    pair.target,
                ) && (
                  <div
                    className={`tp-relationship-composite-summary ${
                      relationshipPairDetails.some(
                        (pair) =>
                          pair.compatible ===
                          false,
                      )
                        ? 'is-warning'
                        : 'is-compatible'
                    }`}
                  >
                    <div>
                      <strong>
                        {
                          relationshipPairDetails
                            .filter(
                              (pair) =>
                                pair.source &&
                                pair.target,
                            )
                            .length
                        }{' '}
                        join key
                      </strong>
                      <span>
                        {
                          sourceTable
                        }
                        {' ↔ '}
                        {
                          targetTable
                        }
                      </span>
                    </div>

                    <small>
                      {relationshipPairDetails.some(
                        (pair) =>
                          pair.compatible ===
                          false,
                      )
                        ? 'Ada pasangan datatype berbeda. Relationship tetap dapat disimpan, tetapi query mungkin memerlukan casting.'
                        : 'Seluruh pasangan key yang terisi memiliki datatype compatible.'}
                    </small>
                  </div>
                )}

                <div className="tp-relationship-builder-footer">
                  <span>
                    Masking status column
                    tidak diubah oleh
                    relationship.
                  </span>

                  <Button
                    type="button"
                    onClick={
                      saveRelationship
                    }
                    disabled={
                      savingRelationship
                    }
                  >
                    {savingRelationship
                      ? 'Menyimpan...'
                      : 'Add Relationship'}
                  </Button>
                </div>
              </div>

              <div className="tp-relationship-list-panel">
                <div className="tp-relationship-list-header">
                  <div>
                    <h3>
                      Saved Relationships
                    </h3>
                    <p>
                      {
                        relationships.length
                      }{' '}
                      relationship tersimpan.
                    </p>
                  </div>

                  <button
                    type="button"
                    className="tp-schema-refresh"
                    onClick={
                      loadRelationships
                    }
                    disabled={
                      loadingRelationships
                    }
                    title="Refresh relationships"
                  >
                    <RefreshCw
                      size={15}
                      className={
                        loadingRelationships
                          ? 'animate-spin'
                          : ''
                      }
                    />
                  </button>
                </div>

                <div className="tp-relationship-list">
                  {loadingRelationships ? (
                    <div className="tp-schema-empty">
                      Membaca relationship...
                    </div>
                  ) : relationships.length ===
                    0 ? (
                    <div className="tp-relationship-empty">
                      <GitBranch
                        size={22}
                      />
                      <strong>
                        Belum ada relationship
                      </strong>
                      <span>
                        Buat relationship pertama
                        dari form di sebelah kiri.
                      </span>
                    </div>
                  ) : (
                    relationships.map(
                      (relationship) => (
                        <article
                          key={
                            relationship.id
                          }
                          className={`tp-relationship-card ${
                            relationship.is_active
                              ? ''
                              : 'is-inactive'
                          }`}
                        >
                          <div className="tp-relationship-card-top">
                            <div>
                              <h4>
                                {
                                  relationship.relationship_name
                                }
                              </h4>

                              <span>
                                {
                                  cardinalityLabel[
                                    relationship
                                      .cardinality
                                  ] ||
                                  relationship.cardinality
                                }
                                {' · '}
                                {
                                  relationship.pair_count ||
                                  relationship.column_pairs
                                    ?.length ||
                                  1
                                } key
                              </span>
                            </div>

                            <span
                              className={`tp-relationship-active-badge ${
                                relationship.is_active
                                  ? 'is-active'
                                  : ''
                              }`}
                            >
                              {relationship.is_active
                                ? 'Active'
                                : 'Inactive'}
                            </span>
                          </div>

                          <div className="tp-relationship-card-tables">
                            <div>
                              <Database size={12} />
                              <strong>
                                {
                                  relationship.source_table
                                }
                              </strong>
                            </div>

                            <ArrowRightLeft
                              size={14}
                            />

                            <div>
                              <Database size={12} />
                              <strong>
                                {
                                  relationship.target_table
                                }
                              </strong>
                            </div>
                          </div>

                          <div className="tp-relationship-card-keys">
                            {(
                              relationship.column_pairs || [
                                {
                                  source_column:
                                    relationship.source_column,
                                  source_data_type:
                                    relationship.source_data_type,
                                  target_column:
                                    relationship.target_column,
                                  target_data_type:
                                    relationship.target_data_type,
                                  compatible:
                                    relationship.compatible,
                                },
                              ]
                            ).map(
                              (pair, pairIndex) => (
                                <div
                                  key={`${relationship.id}-pair-${pairIndex}`}
                                  className={`tp-relationship-card-key-row ${
                                    pair.compatible ===
                                    false
                                      ? 'is-warning'
                                      : ''
                                  }`}
                                >
                                  <span>
                                    {
                                      pair.source_column
                                    }
                                  </span>

                                  <small>
                                    {
                                      pair.source_data_type
                                    }
                                  </small>

                                  <Link2 size={11} />

                                  <span>
                                    {
                                      pair.target_column
                                    }
                                  </span>

                                  <small>
                                    {
                                      pair.target_data_type
                                    }
                                  </small>
                                </div>
                              ),
                            )}
                          </div>

                          {!relationship.compatible && (
                            <div className="tp-relationship-card-warning">
                              <AlertCircle
                                size={12}
                              />
                              Datatype berbeda.
                              Casting mungkin
                              diperlukan pada
                              Visual SQL Builder.
                            </div>
                          )}

                          {(relationship.source_masked ||
                            relationship.target_masked) && (
                            <div className="tp-relationship-card-masked">
                              <EyeOff
                                size={11}
                              />
                              Relationship
                              melibatkan masked
                              column.
                            </div>
                          )}

                          <div className="tp-relationship-card-actions">
                            <button
                              type="button"
                              className="tp-relationship-text-action"
                              onClick={() =>
                                toggleRelationship(
                                  relationship,
                                )
                              }
                            >
                              {relationship.is_active
                                ? 'Disable'
                                : 'Enable'}
                            </button>

                            <button
                              type="button"
                              className="tp-relationship-delete"
                              onClick={() =>
                                removeRelationship(
                                  relationship,
                                )
                              }
                            >
                              <Trash2
                                size={12}
                              />
                              Delete
                            </button>
                          </div>
                        </article>
                      ),
                    )
                  )}
                </div>
              </div>
            </div>

            <div className="tp-relationship-foundation-note">
              <Link2 size={13} />
              Canvas menggunakan React Flow
              untuk interaction, Mermaid-style
              Crow's Foot untuk cardinality,
              dan ELK.js untuk Auto Layout.
              Relationship tetap merupakan
              semantic metadata, bukan Foreign
              Key PostgreSQL.
            </div>
          </section>
        ) : (
          <VisualSqlBuilder
            tables={tables}
            relationships={relationships}
          />
        )}
      </main>
    </DashboardLayout>
  )
}

export default SchemaManager
