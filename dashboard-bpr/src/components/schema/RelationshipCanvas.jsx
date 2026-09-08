import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  GitBranch,
  LayoutDashboard,
  Plus,
  Search,
} from 'lucide-react'

import {
  getTableDetail,
} from '../../services/dataWarehouseService'
import SchemaTableNode from './SchemaTableNode'
import RelationshipEdge from './RelationshipEdge'
import {
  layoutRelationshipGraph,
} from '../../lib/relationshipLayout'

const nodeTypes = {
  schemaTable: SchemaTableNode,
}

const edgeTypes = {
  relationship: RelationshipEdge,
}

function nodeId(tableName) {
  return `table::${tableName}`
}

function tableNameFromNodeId(value) {
  return String(value || '').replace(
    /^table::/,
    '',
  )
}

function columnFromHandle(
  handleId,
) {
  return String(handleId || '').replace(
    /^(source|target)::/,
    '',
  )
}

function relationshipEdge(
  relationship,
) {
  return {
    id: `relationship::${relationship.id}`,
    type: 'relationship',
    source: nodeId(
      relationship.source_table,
    ),
    target: nodeId(
      relationship.target_table,
    ),
    sourceHandle:
      `source::${relationship.source_column}`,
    targetHandle:
      `target::${relationship.target_column}`,
    data: {
      relationship,
    },
  }
}

function RelationshipCanvas({
  tables,
  relationships,
  onConnectionDraft,
  onRelationshipSelect,
}) {
  const [nodes, setNodes, onNodesChange] =
    useNodesState([])
  const [edges, setEdges, onEdgesChange] =
    useEdgesState([])

  const [tableSearch, setTableSearch] =
    useState('')
  const [loadingTable, setLoadingTable] =
    useState('')
  const [flowInstance, setFlowInstance] =
    useState(null)

  const detailsRef = useRef({})

  const filteredTables = useMemo(() => {
    const keyword =
      tableSearch.trim().toLowerCase()

    if (!keyword) return tables

    return tables.filter((table) =>
      table
        .toLowerCase()
        .includes(keyword),
    )
  }, [tables, tableSearch])

  const canvasTableNames = useMemo(
    () =>
      new Set(
        nodes.map((node) =>
          tableNameFromNodeId(node.id),
        ),
      ),
    [nodes],
  )

  const ensureDetail = useCallback(
    async (tableName) => {
      if (
        detailsRef.current[tableName]
      ) {
        return detailsRef.current[
          tableName
        ]
      }

      const detail =
        await getTableDetail(tableName)

      detailsRef.current[tableName] =
        detail

      return detail
    },
    [],
  )

  const addTable = useCallback(
    async (
      tableName,
      {
        position = null,
      } = {},
    ) => {
      if (!tableName) return

      if (
        nodes.some(
          (node) =>
            node.id === nodeId(tableName),
        )
      ) {
        return
      }

      try {
        setLoadingTable(tableName)

        const detail =
          await ensureDetail(tableName)

        setNodes((current) => {
          if (
            current.some(
              (node) =>
                node.id ===
                nodeId(tableName),
            )
          ) {
            return current
          }

          const offset =
            current.length

          return [
            ...current,
            {
              id: nodeId(tableName),
              type: 'schemaTable',
              position:
                position || {
                  x:
                    70 +
                    (offset % 3) * 330,
                  y:
                    60 +
                    Math.floor(
                      offset / 3,
                    ) *
                      180,
                },
              data: {
                tableName,
                columns:
                  detail?.columns || [],
              },
            },
          ]
        })
      } finally {
        setLoadingTable('')
      }
    },
    [
      ensureDetail,
      nodes,
      setNodes,
    ],
  )

  const ensureRelationshipTables =
    useCallback(async () => {
      const names = Array.from(
        new Set(
          relationships.flatMap(
            (relationship) => [
              relationship.source_table,
              relationship.target_table,
            ],
          ),
        ),
      )

      if (
        names.length === 0 &&
        nodes.length === 0
      ) {
        names.push(
          ...tables.slice(0, 2),
        )
      }

      for (const name of names) {
        if (
          !nodes.some(
            (node) =>
              node.id === nodeId(name),
          )
        ) {
          await addTable(name)
        }
      }
    }, [
      relationships,
      tables,
      nodes,
      addTable,
    ])

  useEffect(() => {
    setEdges(
      relationships.map(
        relationshipEdge,
      ),
    )
  }, [
    relationships,
    setEdges,
  ])

  useEffect(() => {
    ensureRelationshipTables()
  }, [
    relationships,
    tables,
  ])

  const autoLayout =
    useCallback(async () => {
      const nextNodes =
        await layoutRelationshipGraph(
          nodes,
          edges,
        )

      setNodes(nextNodes)

      window.setTimeout(() => {
        flowInstance?.fitView({
          padding: 0.16,
          duration: 350,
        })
      }, 60)
    }, [
      nodes,
      edges,
      flowInstance,
      setNodes,
    ])

  const onConnect =
    useCallback(
      (connection) => {
        const sourceTable =
          tableNameFromNodeId(
            connection.source,
          )
        const targetTable =
          tableNameFromNodeId(
            connection.target,
          )
        const sourceColumn =
          columnFromHandle(
            connection.sourceHandle,
          )
        const targetColumn =
          columnFromHandle(
            connection.targetHandle,
          )

        if (
          !sourceTable ||
          !targetTable ||
          !sourceColumn ||
          !targetColumn
        ) {
          return
        }

        if (
          sourceTable ===
            targetTable &&
          sourceColumn ===
            targetColumn
        ) {
          return
        }

        onConnectionDraft?.({
          sourceTable,
          sourceColumn,
          targetTable,
          targetColumn,
        })
      },
      [onConnectionDraft],
    )

  const validConnection =
    useCallback((connection) => {
      if (
        !connection.source ||
        !connection.target ||
        !connection.sourceHandle ||
        !connection.targetHandle
      ) {
        return false
      }

      return !(
        connection.source ===
          connection.target &&
        connection.sourceHandle
          .replace(/^source::/, '') ===
          connection.targetHandle
            .replace(/^target::/, '')
      )
    }, [])

  return (
    <section className="tp-flow-designer">
      <aside className="tp-flow-library">
        <div className="tp-flow-library-header">
          <div>
            <span>
              Table Library
            </span>

            <strong>
              {tables.length} tables
            </strong>
          </div>
        </div>

        <div className="tp-flow-library-search">
          <Search size={14} />

          <input
            value={tableSearch}
            onChange={(event) =>
              setTableSearch(
                event.target.value,
              )
            }
            placeholder="Cari tabel..."
          />
        </div>

        <div className="tp-flow-library-list">
          {filteredTables.map(
            (table) => {
              const added =
                canvasTableNames.has(
                  table,
                )

              return (
                <button
                  key={table}
                  type="button"
                  className={`tp-flow-library-item ${
                    added
                      ? 'is-added'
                      : ''
                  }`}
                  onClick={() =>
                    addTable(table)
                  }
                  disabled={
                    added ||
                    loadingTable === table
                  }
                >
                  <GitBranch
                    size={12}
                  />

                  <span>
                    {table}
                  </span>

                  <small>
                    {added ? (
                      'On canvas'
                    ) : (
                      <Plus
                        size={12}
                      />
                    )}
                  </small>
                </button>
              )
            },
          )}
        </div>
      </aside>

      <div className="tp-flow-canvas-shell">
        <div className="tp-flow-canvas-toolbar">
          <div>
            <strong>
              Relationship Canvas
            </strong>

            <span>
              Drag dari handle kanan
              Source Column ke handle
              kiri Target Column.
            </span>
          </div>

          <button
            type="button"
            className="tp-flow-layout-button"
            onClick={autoLayout}
            disabled={
              nodes.length === 0
            }
          >
            <LayoutDashboard
              size={13}
            />
            Auto layout
          </button>
        </div>

        <div className="tp-flow-canvas">
          {nodes.length === 0 && (
            <div className="tp-flow-empty-cue">
              <GitBranch size={20} />
              <strong>Canvas masih kosong</strong>
              <span>
                Tambahkan tabel dari Table Library untuk mulai membuat relationship.
              </span>
            </div>
          )}

          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={
              onNodesChange
            }
            onEdgesChange={
              onEdgesChange
            }
            onConnect={onConnect}
            isValidConnection={
              validConnection
            }
            onInit={
              setFlowInstance
            }
            onEdgeClick={(
              _event,
              edge,
            ) =>
              onRelationshipSelect?.(
                edge.data
                  ?.relationship,
              )
            }
            fitView
            fitViewOptions={{
              padding: 0.18,
            }}
            minZoom={0.2}
            maxZoom={1.6}
            nodesConnectable
            nodesDraggable
            elementsSelectable
          >
            <Background
              gap={20}
              size={1}
            />

            <MiniMap
              pannable
              zoomable
              nodeStrokeWidth={2}
            />

            <Controls
              showInteractive={false}
            />
          </ReactFlow>
        </div>
      </div>
    </section>
  )
}

export default RelationshipCanvas
