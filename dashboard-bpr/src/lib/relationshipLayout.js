import ELK from 'elkjs/lib/elk.bundled.js'

const elk = new ELK()

function nodeHeight(node) {
  const columnCount =
    node?.data?.columns?.length || 0

  return 48 + columnCount * 31
}

export async function layoutRelationshipGraph(
  nodes,
  edges,
  direction = 'RIGHT',
) {
  if (!nodes.length) {
    return nodes
  }

  const graph = {
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': direction,
      'elk.spacing.nodeNode': '70',
      'elk.layered.spacing.nodeNodeBetweenLayers':
        '110',
      'elk.layered.nodePlacement.strategy':
        'NETWORK_SIMPLEX',
      'elk.layered.crossingMinimization.strategy':
        'LAYER_SWEEP',
    },
    children: nodes.map((node) => ({
      id: node.id,
      width: 282,
      height: nodeHeight(node),
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      sources: [edge.source],
      targets: [edge.target],
    })),
  }

  const layouted =
    await elk.layout(graph)

  const positionById =
    Object.fromEntries(
      (layouted.children || []).map(
        (item) => [
          item.id,
          {
            x: item.x || 0,
            y: item.y || 0,
          },
        ],
      ),
    )

  return nodes.map((node) => ({
    ...node,
    position:
      positionById[node.id] ||
      node.position,
  }))
}
