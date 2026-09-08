import {
  memo,
} from 'react'
import {
  Handle,
  Position,
} from '@xyflow/react'
import {
  Database,
  EyeOff,
  LockKeyhole,
} from 'lucide-react'

function SchemaTableNode({
  data,
  selected,
}) {
  const columns = data?.columns || []

  return (
    <div
      className={`tp-flow-table-node ${
        selected ? 'is-selected' : ''
      }`}
    >
      <div className="tp-flow-table-node-header">
        <div>
          <Database size={14} />

          <strong>
            {data.tableName}
          </strong>
        </div>

        <span>
          {columns.length} cols
        </span>
      </div>

      <div className="tp-flow-table-node-columns">
        {columns.map((column) => (
          <div
            key={column.column_name}
            className={`tp-flow-table-column ${
              column.masked
                ? 'is-masked'
                : ''
            }`}
          >
            <Handle
              id={`target::${column.column_name}`}
              type="target"
              position={Position.Left}
              className="tp-flow-column-handle is-target"
              title={`Target: ${column.column_name}`}
            />

            <div className="tp-flow-column-name">
              {column.system_column && (
                <LockKeyhole
                  size={10}
                />
              )}

              {column.masked && (
                <EyeOff size={10} />
              )}

              <span>
                {column.column_name}
              </span>
            </div>

            <small>
              {column.data_type}
            </small>

            <Handle
              id={`source::${column.column_name}`}
              type="source"
              position={Position.Right}
              className="tp-flow-column-handle is-source"
              title={`Source: ${column.column_name}`}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

export default memo(SchemaTableNode)
