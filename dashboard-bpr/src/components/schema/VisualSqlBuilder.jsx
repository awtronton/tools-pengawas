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
  ArrowRight,
  Check,
  ChevronDown,
  Clipboard,
  Code2,
  Database,
  EyeOff,
  GitBranch,
  Link2,
  Plus,
  RotateCcw,
  ShieldCheck,
  Table2,
  Trash2,
} from 'lucide-react'

import {
  getTableDetail,
} from '../../services/dataWarehouseService'

const JOIN_OPTIONS = [
  {
    value: 'INNER JOIN',
    label: 'INNER JOIN',
    description:
      'Hanya row yang memiliki pasangan pada kedua sisi.',
  },
  {
    value: 'LEFT JOIN',
    label: 'LEFT JOIN',
    description:
      'Semua row dari dataset kiri tetap dipertahankan.',
  },
  {
    value: 'RIGHT JOIN',
    label: 'RIGHT JOIN',
    description:
      'Semua row dari tabel yang baru ditambahkan tetap dipertahankan.',
  },
  {
    value: 'FULL OUTER JOIN',
    label: 'FULL OUTER JOIN',
    description:
      'Mempertahankan seluruh row dari kedua sisi, termasuk yang tidak memiliki pasangan.',
  },
  {
    value: 'LEFT ANTI JOIN',
    label: 'LEFT ANTI JOIN',
    description:
      'Hanya mempertahankan row dari dataset kiri yang tidak memiliki pasangan pada tabel baru.',
  },
  {
    value: 'RIGHT ANTI JOIN',
    label: 'RIGHT ANTI JOIN',
    description:
      'Hanya mempertahankan row dari tabel baru yang tidak memiliki pasangan pada dataset kiri.',
  },
  {
    value: 'FULL ANTI JOIN',
    label: 'FULL ANTI JOIN',
    description:
      'Mempertahankan row yang tidak memiliki pasangan dari kedua sisi dan membuang row yang match.',
  },
]

function quoteIdentifier(value) {
  return `"${String(value).replaceAll(
    '"',
    '""',
  )}"`
}

function columnKey(
  tableName,
  columnName,
) {
  return `${tableName}::${columnName}`
}

function relationLabel(
  relationship,
) {
  return (
    `${relationship.source_table}.` +
    `${relationship.source_column} ↔ ` +
    `${relationship.target_table}.` +
    `${relationship.target_column}`
  )
}

function cardinalityLabel(value) {
  const labels = {
    one_to_one: '1:1',
    one_to_many: '1:N',
    many_to_one: 'N:1',
    many_to_many: 'N:N',
  }

  return labels[value] || value
}

function getJoinCandidate(
  relationship,
  includedTables,
) {
  const sourceIncluded =
    includedTables.has(
      relationship.source_table,
    )

  const targetIncluded =
    includedTables.has(
      relationship.target_table,
    )

  if (
    sourceIncluded === targetIncluded
  ) {
    return null
  }

  return {
    relationship,
    existingTable: sourceIncluded
      ? relationship.source_table
      : relationship.target_table,
    newTable: sourceIncluded
      ? relationship.target_table
      : relationship.source_table,
  }
}

function buildQueryPlan(
  baseTable,
  joins,
  relationshipsById,
) {
  if (!baseTable) {
    return {
      tables: [],
      steps: [],
      error: null,
    }
  }

  const tables = [baseTable]
  const included = new Set([
    baseTable,
  ])
  const steps = []

  for (const join of joins) {
    const relationship =
      relationshipsById[
        join.relationshipId
      ]

    if (!relationship) {
      return {
        tables,
        steps,
        error:
          'Salah satu relationship tidak lagi tersedia.',
      }
    }

    const candidate =
      getJoinCandidate(
        relationship,
        included,
      )

    if (!candidate) {
      return {
        tables,
        steps,
        error:
          'Urutan join tidak valid atau membentuk cycle. Reset join dan pilih relationship yang menghubungkan satu tabel existing ke satu tabel baru.',
      }
    }

    included.add(
      candidate.newTable,
    )
    tables.push(candidate.newTable)

    steps.push({
      ...join,
      relationship,
      existingTable:
        candidate.existingTable,
      newTable:
        candidate.newTable,
    })
  }

  return {
    tables,
    steps,
    error: null,
  }
}

function buildSql({
  baseTable,
  queryPlan,
  selectedColumns,
  tableDetails,
}) {
  if (!baseTable) {
    return ''
  }

  const aliasByTable = {}

  queryPlan.tables.forEach(
    (tableName, index) => {
      aliasByTable[tableName] =
        `t${index + 1}`
    },
  )

  const selected = []

  for (const tableName of queryPlan.tables) {
    const detail =
      tableDetails[tableName]

    for (const column of (
      detail?.columns || []
    )) {
      const key = columnKey(
        tableName,
        column.column_name,
      )

      if (!selectedColumns.has(key)) {
        continue
      }

      selected.push({
        tableName,
        columnName:
          column.column_name,
        alias:
          `${tableName}__${column.column_name}`,
      })
    }
  }

  const selectSql =
    selected.length > 0
      ? selected
          .map(
            (column) =>
              `    ${
                aliasByTable[
                  column.tableName
                ]
              }.${quoteIdentifier(
                column.columnName,
              )} AS ${quoteIdentifier(
                column.alias,
              )}`,
          )
          .join(',\n')
      : '    -- pilih minimal satu output column'

  const lines = [
    'SELECT',
    selectSql,
    `FROM ${quoteIdentifier(
      baseTable,
    )} AS ${aliasByTable[baseTable]}`,
  ]

  const antiFilters = []

  for (const step of queryPlan.steps) {
    const relationship =
      step.relationship

    const newAlias =
      aliasByTable[step.newTable]

    const sourceAlias =
      aliasByTable[
        relationship.source_table
      ]

    const targetAlias =
      aliasByTable[
        relationship.target_table
      ]

    const isLeftAnti =
      step.joinType ===
      'LEFT ANTI JOIN'

    const isRightAnti =
      step.joinType ===
      'RIGHT ANTI JOIN'

    const isFullAnti =
      step.joinType ===
      'FULL ANTI JOIN'

    const sqlJoinType =
      isLeftAnti
        ? 'LEFT JOIN'
        : isRightAnti
          ? 'RIGHT JOIN'
          : isFullAnti
            ? 'FULL OUTER JOIN'
            : step.joinType

    lines.push(
      `${sqlJoinType} ${quoteIdentifier(
        step.newTable,
      )} AS ${newAlias}`,
    )

    lines.push(
      `    ON ${sourceAlias}.${quoteIdentifier(
        relationship.source_column,
      )} = ${targetAlias}.${quoteIdentifier(
        relationship.target_column,
      )}`,
    )

    if (isLeftAnti) {
      const newColumn =
        relationship.source_table ===
        step.newTable
          ? relationship.source_column
          : relationship.target_column

      antiFilters.push(
        `${newAlias}.${quoteIdentifier(
          newColumn,
        )} IS NULL`,
      )
    }

    if (isRightAnti) {
      const existingAlias =
        aliasByTable[
          step.existingTable
        ]

      const existingColumn =
        relationship.source_table ===
        step.existingTable
          ? relationship.source_column
          : relationship.target_column

      antiFilters.push(
        `${existingAlias}.${quoteIdentifier(
          existingColumn,
        )} IS NULL`,
      )
    }

    if (isFullAnti) {
      antiFilters.push(
        `(${sourceAlias}.${quoteIdentifier(
          relationship.source_column,
        )} IS NULL OR ${targetAlias}.${quoteIdentifier(
          relationship.target_column,
        )} IS NULL)`,
      )
    }
  }

  if (antiFilters.length > 0) {
    lines.push('WHERE')

    lines.push(
      antiFilters
        .map(
          (filter, index) =>
            `${index === 0 ? '    ' : '    AND '}${filter}`,
        )
        .join('\n'),
    )
  }

  return `${lines.join('\n')};`
}

function VisualSqlBuilder({
  tables,
  relationships,
}) {
  const activeRelationships =
    useMemo(
      () =>
        relationships.filter(
          (relationship) =>
            relationship.is_active,
        ),
      [relationships],
    )

  const relationshipsById =
    useMemo(
      () =>
        Object.fromEntries(
          activeRelationships.map(
            (relationship) => [
              String(
                relationship.id,
              ),
              relationship,
            ],
          ),
        ),
      [activeRelationships],
    )

  const [baseTable, setBaseTable] =
    useState('')
  const [joins, setJoins] =
    useState([])
  const [
    relationshipToAdd,
    setRelationshipToAdd,
  ] = useState('')
  const [nextJoinType, setNextJoinType] =
    useState('LEFT JOIN')

  const [
    tableDetails,
    setTableDetails,
  ] = useState({})
  const [
    loadingDetails,
    setLoadingDetails,
  ] = useState(false)

  const [
    selectedColumns,
    setSelectedColumns,
  ] = useState(new Set())

  const [copyState, setCopyState] =
    useState('idle')

  const tableOptions = useMemo(
    () =>
      tables.map((table) => ({
        value: table,
        label: table,
      })),
    [tables],
  )

  const queryPlan = useMemo(
    () =>
      buildQueryPlan(
        baseTable,
        joins,
        relationshipsById,
      ),
    [
      baseTable,
      joins,
      relationshipsById,
    ],
  )

  const includedTableSet =
    useMemo(
      () =>
        new Set(
          queryPlan.tables,
        ),
      [queryPlan.tables],
    )

  const availableRelationshipCandidates =
    useMemo(() => {
      if (!baseTable) {
        return []
      }

      return activeRelationships
        .filter(
          (relationship) =>
            !joins.some(
              (join) =>
                String(
                  join.relationshipId,
                ) ===
                String(
                  relationship.id,
                ),
            ),
        )
        .map((relationship) =>
          getJoinCandidate(
            relationship,
            includedTableSet,
          ),
        )
        .filter(Boolean)
    }, [
      activeRelationships,
      baseTable,
      includedTableSet,
      joins,
    ])

  const relationshipOptions =
    useMemo(
      () =>
        availableRelationshipCandidates.map(
          (candidate) => ({
            value: String(
              candidate.relationship.id,
            ),
            label:
              `${candidate.existingTable} → ` +
              `${candidate.newTable} | ` +
              relationLabel(
                candidate.relationship,
              ),
          }),
        ),
      [
        availableRelationshipCandidates,
      ],
    )

  const sql = useMemo(
    () =>
      buildSql({
        baseTable,
        queryPlan,
        selectedColumns,
        tableDetails,
      }),
    [
      baseTable,
      queryPlan,
      selectedColumns,
      tableDetails,
    ],
  )

  const selectedColumnCount =
    selectedColumns.size

  const maskedColumnCount =
    useMemo(() => {
      let count = 0

      for (const tableName of queryPlan.tables) {
        for (const column of (
          tableDetails[tableName]
            ?.columns || []
        )) {
          if (column.masked) {
            count += 1
          }
        }
      }

      return count
    }, [
      queryPlan.tables,
      tableDetails,
    ])

  useEffect(() => {
    if (
      baseTable ||
      tables.length === 0
    ) {
      return
    }

    setBaseTable(tables[0])
  }, [
    baseTable,
    tables,
  ])

  useEffect(() => {
    setJoins([])
    setRelationshipToAdd('')
    setSelectedColumns(
      new Set(),
    )
  }, [baseTable])

  useEffect(() => {
    const neededTables =
      queryPlan.tables.filter(
        (tableName) =>
          !tableDetails[tableName],
      )

    if (
      neededTables.length === 0
    ) {
      return
    }

    let cancelled = false

    async function load() {
      try {
        setLoadingDetails(true)

        const responses =
          await Promise.all(
            neededTables.map(
              async (tableName) => [
                tableName,
                await getTableDetail(
                  tableName,
                ),
              ],
            ),
          )

        if (cancelled) return

        setTableDetails(
          (current) => ({
            ...current,
            ...Object.fromEntries(
              responses,
            ),
          }),
        )
      } finally {
        if (!cancelled) {
          setLoadingDetails(false)
        }
      }
    }

    load()

    return () => {
      cancelled = true
    }
  }, [
    queryPlan.tables,
    tableDetails,
  ])

  useEffect(() => {
    const validKeys = new Set()

    for (const tableName of queryPlan.tables) {
      for (const column of (
        tableDetails[tableName]
          ?.columns || []
      )) {
        validKeys.add(
          columnKey(
            tableName,
            column.column_name,
          ),
        )
      }
    }

    setSelectedColumns(
      (current) => {
        const next = new Set(
          Array.from(
            current,
          ).filter((key) =>
            validKeys.has(key),
          ),
        )

        return next
      },
    )
  }, [
    queryPlan.tables,
    tableDetails,
  ])

  function addJoin() {
    if (!relationshipToAdd) {
      return
    }

    setJoins((current) => [
      ...current,
      {
        relationshipId:
          relationshipToAdd,
        joinType: nextJoinType,
      },
    ])

    setRelationshipToAdd('')
    setNextJoinType('LEFT JOIN')
  }

  function removeJoin(index) {
    setJoins((current) =>
      current.slice(0, index),
    )

    setRelationshipToAdd('')
  }

  function updateJoinType(
    index,
    joinType,
  ) {
    setJoins((current) =>
      current.map(
        (join, itemIndex) =>
          itemIndex === index
            ? {
                ...join,
                joinType,
              }
            : join,
      ),
    )
  }

  function toggleColumn(
    tableName,
    column,
  ) {
    if (column.masked) {
      return
    }

    const key = columnKey(
      tableName,
      column.column_name,
    )

    setSelectedColumns(
      (current) => {
        const next =
          new Set(current)

        if (next.has(key)) {
          next.delete(key)
        } else {
          next.add(key)
        }

        return next
      },
    )
  }

  function toggleTableColumns(
    tableName,
  ) {
    const columns =
      (
        tableDetails[tableName]
          ?.columns || []
      ).filter(
        (column) =>
          !column.masked,
      )

    const keys = columns.map(
      (column) =>
        columnKey(
          tableName,
          column.column_name,
        ),
    )

    const allSelected =
      keys.length > 0 &&
      keys.every((key) =>
        selectedColumns.has(key),
      )

    setSelectedColumns(
      (current) => {
        const next =
          new Set(current)

        for (const key of keys) {
          if (allSelected) {
            next.delete(key)
          } else {
            next.add(key)
          }
        }

        return next
      },
    )
  }

  function resetBuilder() {
    setJoins([])
    setRelationshipToAdd('')
    setNextJoinType('LEFT JOIN')
    setSelectedColumns(
      new Set(),
    )
    setCopyState('idle')
  }

  async function copySql() {
    if (!sql) return

    try {
      await navigator.clipboard.writeText(
        sql,
      )
      setCopyState('copied')

      window.setTimeout(
        () =>
          setCopyState('idle'),
        1500,
      )
    } catch {
      setCopyState('failed')
    }
  }

  return (
    <section className="tp-sql-builder">
      <div className="tp-sql-builder-intro">
        <div>
          <span>
            Visual SQL Builder
          </span>

          <h2>
            Build query from saved relationships
          </h2>

          <p>
            Susun join dan output column tanpa menulis SQL secara manual. SQL pada tahap ini hanya preview dan belum dieksekusi ke database.
          </p>
        </div>

        <div className="tp-sql-builder-stage">
          Step 6D · Foundation
        </div>
      </div>

      <div className="tp-sql-builder-grid">
        <div className="tp-sql-builder-workspace">
          <section className="tp-sql-section">
            <div className="tp-sql-section-heading">
              <div className="tp-sql-step-number">
                1
              </div>

              <div>
                <h3>
                  Base Table
                </h3>
                <p>
                  Tabel pertama yang menjadi titik awal query.
                </p>
              </div>
            </div>

            <div className="tp-sql-base-row">
              <Dropdown
                options={tableOptions}
                value={
                  tableOptions.find(
                    (option) =>
                      option.value ===
                      baseTable,
                  ) || null
                }
                onChange={(option) =>
                  setBaseTable(
                    option?.value || '',
                  )
                }
                searchable
                clearable={false}
                className="tp-vibe-dropdown"
              />

              <button
                type="button"
                className="tp-sql-reset-button"
                onClick={resetBuilder}
              >
                <RotateCcw size={13} />
                Reset Query
              </button>
            </div>
          </section>

          <section className="tp-sql-section">
            <div className="tp-sql-section-heading">
              <div className="tp-sql-step-number">
                2
              </div>

              <div>
                <h3>
                  Join Path
                </h3>
                <p>
                  Tambahkan tabel berdasarkan relationship aktif yang sudah dibuat di Relationship Designer.
                </p>
              </div>
            </div>

            <div className="tp-sql-path">
              {baseTable && (
                <div className="tp-sql-path-table is-base">
                  <Database size={13} />

                  <div>
                    <strong>
                      {baseTable}
                    </strong>

                    <span>
                      Base
                    </span>
                  </div>
                </div>
              )}

              {queryPlan.steps.map(
                (step, index) => {
                  const joinOption =
                    JOIN_OPTIONS.find(
                      (option) =>
                        option.value ===
                        step.joinType,
                    ) ||
                    JOIN_OPTIONS[1]

                  return (
                    <div
                      key={
                        step.relationshipId
                      }
                      className="tp-sql-join-step"
                    >
                      <div className="tp-sql-path-connector">
                        <ArrowRight
                          size={14}
                        />

                        <span>
                          {
                            step.joinType
                          }
                        </span>
                      </div>

                      <div className="tp-sql-join-card">
                        <div className="tp-sql-join-card-main">
                          <div className="tp-sql-path-table">
                            <Database
                              size={13}
                            />

                            <div>
                              <strong>
                                {
                                  step.newTable
                                }
                              </strong>

                              <span>
                                {cardinalityLabel(
                                  step.relationship
                                    .cardinality,
                                )}
                              </span>
                            </div>
                          </div>

                          <button
                            type="button"
                            className="tp-sql-remove-join"
                            onClick={() =>
                              removeJoin(
                                index,
                              )
                            }
                            title="Hapus join ini dan seluruh join setelahnya"
                          >
                            <Trash2
                              size={12}
                            />
                          </button>
                        </div>

                        <div className="tp-sql-join-condition">
                          <Link2
                            size={11}
                          />

                          <span>
                            {relationLabel(
                              step.relationship,
                            )}
                          </span>
                        </div>

                        <div className="tp-sql-join-type-row">
                          <Dropdown
                            options={
                              JOIN_OPTIONS
                            }
                            value={
                              JOIN_OPTIONS.find(
                                (option) =>
                                  option.value ===
                                  step.joinType,
                              ) ||
                              JOIN_OPTIONS[1]
                            }
                            onChange={(
                              option,
                            ) =>
                              updateJoinType(
                                index,
                                option?.value ||
                                  'LEFT JOIN',
                              )
                            }
                            searchable={
                              false
                            }
                            clearable={
                              false
                            }
                            className="tp-vibe-dropdown"
                          />

                          <small>
                            {
                              joinOption.description
                            }
                          </small>
                        </div>
                      </div>
                    </div>
                  )
                },
              )}
            </div>

            <div className="tp-sql-add-join">
              <div className="tp-sql-add-relationship">
                <label>
                  Relationship
                </label>

                <Dropdown
                  options={
                    relationshipOptions
                  }
                  value={
                    relationshipOptions.find(
                      (option) =>
                        option.value ===
                        relationshipToAdd,
                    ) || null
                  }
                  onChange={(option) =>
                    setRelationshipToAdd(
                      option?.value || '',
                    )
                  }
                  searchable
                  clearable
                  disabled={
                    relationshipOptions.length ===
                    0
                  }
                  placeholder={
                    relationshipOptions.length ===
                    0
                      ? 'Tidak ada relationship lanjutan'
                      : 'Pilih relationship'
                  }
                  className="tp-vibe-dropdown"
                />
              </div>

              <div className="tp-sql-add-type">
                <label>
                  Join Type
                </label>

                <Dropdown
                  options={JOIN_OPTIONS}
                  value={
                    JOIN_OPTIONS.find(
                      (option) =>
                        option.value ===
                        nextJoinType,
                    ) ||
                    JOIN_OPTIONS[1]
                  }
                  onChange={(option) =>
                    setNextJoinType(
                      option?.value ||
                        'LEFT JOIN',
                    )
                  }
                  searchable={false}
                  clearable={false}
                  className="tp-vibe-dropdown"
                />
              </div>

              <Button
                type="button"
                onClick={addJoin}
                disabled={
                  !relationshipToAdd
                }
              >
                <Plus size={13} />
                Add Join
              </Button>
            </div>

            {activeRelationships.length ===
              0 && (
              <div className="tp-sql-inline-warning">
                <AlertCircle
                  size={13}
                />
                Belum ada relationship aktif. Buat relationship terlebih dahulu pada Relationship Designer.
              </div>
            )}

            {queryPlan.error && (
              <div className="tp-sql-inline-warning">
                <AlertCircle
                  size={13}
                />
                {queryPlan.error}
              </div>
            )}
          </section>

          <section className="tp-sql-section">
            <div className="tp-sql-section-heading">
              <div className="tp-sql-step-number">
                3
              </div>

              <div>
                <h3>
                  Output Columns
                </h3>
                <p>
                  Pilih column yang akan muncul pada hasil query.
                </p>
              </div>
            </div>

            {loadingDetails && (
              <div className="tp-sql-loading">
                Membaca schema tabel...
              </div>
            )}

            <div className="tp-sql-column-groups">
              {queryPlan.tables.map(
                (tableName) => {
                  const columns =
                    tableDetails[
                      tableName
                    ]?.columns || []

                  const visibleColumns =
                    columns.filter(
                      (column) =>
                        !column.masked,
                    )

                  const allSelected =
                    visibleColumns.length >
                      0 &&
                    visibleColumns.every(
                      (column) =>
                        selectedColumns.has(
                          columnKey(
                            tableName,
                            column.column_name,
                          ),
                        ),
                    )

                  return (
                    <div
                      key={tableName}
                      className="tp-sql-column-group"
                    >
                      <div className="tp-sql-column-group-header">
                        <div>
                          <Table2
                            size={13}
                          />

                          <strong>
                            {tableName}
                          </strong>

                          <span>
                            {
                              columns.length
                            }{' '}
                            columns
                          </span>
                        </div>

                        <button
                          type="button"
                          onClick={() =>
                            toggleTableColumns(
                              tableName,
                            )
                          }
                          disabled={
                            visibleColumns.length ===
                            0
                          }
                        >
                          {allSelected
                            ? 'Clear'
                            : 'Select all'}
                        </button>
                      </div>

                      <div className="tp-sql-column-list">
                        {columns.map(
                          (column) => {
                            const key =
                              columnKey(
                                tableName,
                                column.column_name,
                              )

                            const selected =
                              selectedColumns.has(
                                key,
                              )

                            return (
                              <button
                                key={key}
                                type="button"
                                className={`tp-sql-column-item ${
                                  selected
                                    ? 'is-selected'
                                    : ''
                                } ${
                                  column.masked
                                    ? 'is-masked'
                                    : ''
                                }`}
                                onClick={() =>
                                  toggleColumn(
                                    tableName,
                                    column,
                                  )
                                }
                                disabled={
                                  column.masked
                                }
                                title={
                                  column.masked
                                    ? 'Masked column belum dapat dipilih sebagai output pada Step 6D.'
                                    : column.column_name
                                }
                              >
                                <span className="tp-sql-column-checkbox">
                                  {selected && (
                                    <Check
                                      size={10}
                                    />
                                  )}
                                </span>

                                <span className="tp-sql-column-item-name">
                                  {column.masked && (
                                    <EyeOff
                                      size={10}
                                    />
                                  )}

                                  {
                                    column.column_name
                                  }
                                </span>

                                <small>
                                  {
                                    column.data_type
                                  }
                                </small>
                              </button>
                            )
                          },
                        )}
                      </div>
                    </div>
                  )
                },
              )}
            </div>

            {maskedColumnCount > 0 && (
              <div className="tp-sql-mask-note">
                <ShieldCheck
                  size={12}
                />

                {maskedColumnCount} masked column terdeteksi. Pada foundation ini masked column tidak dapat dipilih sebagai output untuk mencegah bypass masking.
              </div>
            )}
          </section>
        </div>

        <aside className="tp-sql-preview-panel">
          <div className="tp-sql-preview-heading">
            <div>
              <Code2 size={15} />

              <div>
                <strong>
                  SQL Preview
                </strong>

                <span>
                  Generated · read-only
                </span>
              </div>
            </div>

            <button
              type="button"
              className="tp-sql-copy-button"
              onClick={copySql}
              disabled={!sql}
            >
              {copyState ===
              'copied' ? (
                <Check
                  size={12}
                />
              ) : (
                <Clipboard
                  size={12}
                />
              )}

              {copyState ===
              'copied'
                ? 'Copied'
                : 'Copy'}
            </button>
          </div>

          <div className="tp-sql-preview-summary">
            <div>
              <span>
                Tables
              </span>

              <strong>
                {
                  queryPlan.tables
                    .length
                }
              </strong>
            </div>

            <div>
              <span>
                Joins
              </span>

              <strong>
                {
                  queryPlan.steps
                    .length
                }
              </strong>
            </div>

            <div>
              <span>
                Output
              </span>

              <strong>
                {
                  selectedColumnCount
                }
              </strong>
            </div>
          </div>

          <pre className="tp-sql-code-preview">
            <code>
              {sql ||
                '-- pilih Base Table untuk memulai'}
            </code>
          </pre>

          <div className="tp-sql-preview-footer">
            <GitBranch
              size={12}
            />

            SQL dibentuk hanya dari tabel, relationship, join type, dan column yang dipilih melalui UI. LEFT/RIGHT/FULL ANTI JOIN diterjemahkan ke pola JOIN + IS NULL yang kompatibel dengan PostgreSQL.
          </div>

          <div className="tp-sql-next-stage">
            <span>
              Next
            </span>

            <strong>
              Step 6E
            </strong>

            <p>
              Data Preview, validation row count, duplicate/null warning, alias management, dan filter/WHERE.
            </p>
          </div>
        </aside>
      </div>
    </section>
  )
}

export default VisualSqlBuilder
