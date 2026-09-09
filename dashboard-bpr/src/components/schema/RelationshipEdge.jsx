import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
} from '@xyflow/react'

const cardinalityShort = {
  one_to_one: '1:1',
  one_to_many: '1:N',
  many_to_one: 'N:1',
  many_to_many: 'N:N',
}

function endType(
  cardinality,
  side,
) {
  if (side === 'source') {
    return [
      'many_to_one',
      'many_to_many',
    ].includes(cardinality)
      ? 'many'
      : 'one'
  }

  return [
    'one_to_many',
    'many_to_many',
  ].includes(cardinality)
    ? 'many'
    : 'one'
}

function MarkerDefinition({
  id,
  type,
  stroke,
}) {
  if (type === 'many') {
    return (
      <marker
        id={id}
        markerWidth="15"
        markerHeight="15"
        refX="10"
        refY="7.5"
        orient="auto-start-reverse"
        markerUnits="strokeWidth"
      >
        <path
          d="M 11 7.5 L 2 1.5 M 11 7.5 L 2 7.5 M 11 7.5 L 2 13.5"
          fill="none"
          stroke={stroke}
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </marker>
    )
  }

  return (
    <marker
      id={id}
      markerWidth="12"
      markerHeight="15"
      refX="8"
      refY="7.5"
      orient="auto-start-reverse"
      markerUnits="strokeWidth"
    >
      <path
        d="M 3 2 L 3 13 M 7 2 L 7 13"
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </marker>
  )
}

function RelationshipEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}) {
  const relationship =
    data?.relationship || {}

  const [
    path,
    labelX,
    labelY,
  ] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })

  const inactive =
    relationship.is_active === false

  const incompatible =
    relationship.compatible === false

  const stroke = selected
    ? '#0073ea'
    : incompatible
      ? '#c07a20'
      : inactive
        ? '#a7aab4'
        : '#5f6f85'

  const sourceMarkerId =
    `tp-source-${id.replace(
      /[^A-Za-z0-9_-]/g,
      '-',
    )}`

  const targetMarkerId =
    `tp-target-${id.replace(
      /[^A-Za-z0-9_-]/g,
      '-',
    )}`

  return (
    <>
      <defs>
        <MarkerDefinition
          id={sourceMarkerId}
          type={endType(
            relationship.cardinality,
            'source',
          )}
          stroke={stroke}
        />

        <MarkerDefinition
          id={targetMarkerId}
          type={endType(
            relationship.cardinality,
            'target',
          )}
          stroke={stroke}
        />
      </defs>

      <BaseEdge
        id={id}
        path={path}
        markerStart={`url(#${sourceMarkerId})`}
        markerEnd={`url(#${targetMarkerId})`}
        style={{
          stroke,
          strokeWidth: selected
            ? 2.2
            : 1.6,
          strokeDasharray:
            inactive
              ? '6 5'
              : undefined,
        }}
      />

      <EdgeLabelRenderer>
        <div
          className={`tp-flow-edge-label ${
            incompatible
              ? 'is-warning'
              : ''
          } ${
            inactive
              ? 'is-inactive'
              : ''
          }`}
          style={{
            transform:
              `translate(-50%, -50%) ` +
              `translate(${labelX}px, ${labelY}px)`,
          }}
        >
          {cardinalityShort[
            relationship.cardinality
          ] ||
            relationship.cardinality}
          {(relationship.pair_count ||
            relationship.column_pairs
              ?.length ||
            1) > 1
            ? ` · ${
                relationship.pair_count ||
                relationship.column_pairs
                  ?.length
              } keys`
            : ''}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

export default RelationshipEdge
