import { useMemo } from "react";

import { DependencyGraph } from "../api/client";

const NODE_WIDTH = 170;
const NODE_HEIGHT = 40;
const COL_GAP = 90;
const ROW_GAP = 16;
const PADDING = 24;

interface LaidOutNode {
  id: string;
  label: string;
  kind: string;
  x: number;
  y: number;
}

interface Layout {
  nodes: LaidOutNode[];
  positions: Map<string, LaidOutNode>;
  width: number;
  height: number;
}

/** Layers nodes left-to-right by longest-path-from-a-root (Kahn's algorithm), so an
 * import graph reads roughly in "what depends on what" order. Any leftover cycle is
 * broken by placing its nodes in the next free layer rather than looping forever. */
function layoutGraph(graph: DependencyGraph): Layout {
  const outEdges = new Map<string, string[]>();
  const inDegree = new Map<string, number>();
  for (const node of graph.nodes) {
    outEdges.set(node.id, []);
    inDegree.set(node.id, 0);
  }
  for (const edge of graph.edges) {
    outEdges.get(edge.source)?.push(edge.target);
    inDegree.set(edge.target, (inDegree.get(edge.target) ?? 0) + 1);
  }

  const remaining = new Map(inDegree);
  const layers: string[][] = [];
  const assigned = new Set<string>();

  while (assigned.size < graph.nodes.length) {
    let layer = graph.nodes.map((n) => n.id).filter((id) => !assigned.has(id) && (remaining.get(id) ?? 0) <= 0);
    if (layer.length === 0) {
      // Cycle: nothing has indegree 0 among what's left. Break it by taking whatever
      // is left, in a stable order.
      layer = graph.nodes.map((n) => n.id).filter((id) => !assigned.has(id));
    }
    layer.sort();
    layers.push(layer);
    for (const id of layer) {
      assigned.add(id);
      for (const target of outEdges.get(id) ?? []) {
        remaining.set(target, (remaining.get(target) ?? 0) - 1);
      }
    }
  }

  const nodeById = new Map(graph.nodes.map((n) => [n.id, n]));
  const positions = new Map<string, LaidOutNode>();
  const laidOut: LaidOutNode[] = [];
  let maxRows = 1;

  layers.forEach((layer, layerIndex) => {
    maxRows = Math.max(maxRows, layer.length);
    layer.forEach((id, rowIndex) => {
      const meta = nodeById.get(id)!;
      const node: LaidOutNode = {
        id,
        label: meta.label,
        kind: meta.kind,
        x: PADDING + layerIndex * (NODE_WIDTH + COL_GAP),
        y: PADDING + rowIndex * (NODE_HEIGHT + ROW_GAP),
      };
      positions.set(id, node);
      laidOut.push(node);
    });
  });

  return {
    nodes: laidOut,
    positions,
    width: PADDING * 2 + layers.length * NODE_WIDTH + Math.max(0, layers.length - 1) * COL_GAP,
    height: PADDING * 2 + maxRows * NODE_HEIGHT + Math.max(0, maxRows - 1) * ROW_GAP,
  };
}

interface GraphViewerProps {
  graph: DependencyGraph;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function GraphViewer({ graph, selectedId, onSelect }: GraphViewerProps) {
  const layout = useMemo(() => layoutGraph(graph), [graph]);

  const neighborIds = useMemo(() => {
    if (!selectedId) return new Set<string>();
    const set = new Set<string>();
    for (const edge of graph.edges) {
      if (edge.source === selectedId) set.add(edge.target);
      if (edge.target === selectedId) set.add(edge.source);
    }
    return set;
  }, [graph.edges, selectedId]);

  return (
    <div className="graph-scroll">
      <svg width={layout.width} height={layout.height} role="img" aria-label="Repository dependency graph">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--edge)" />
          </marker>
        </defs>

        {graph.edges.map((edge, i) => {
          const source = layout.positions.get(edge.source);
          const target = layout.positions.get(edge.target);
          if (!source || !target) return null;
          const x1 = source.x + NODE_WIDTH;
          const y1 = source.y + NODE_HEIGHT / 2;
          const x2 = target.x;
          const y2 = target.y + NODE_HEIGHT / 2;
          const highlighted = selectedId === edge.source || selectedId === edge.target;
          return (
            <path
              key={i}
              d={`M ${x1} ${y1} C ${x1 + 40} ${y1}, ${x2 - 40} ${y2}, ${x2} ${y2}`}
              fill="none"
              stroke={highlighted ? "var(--accent)" : "var(--edge)"}
              strokeWidth={highlighted ? 2 : 1}
              markerEnd="url(#arrow)"
            />
          );
        })}

        {layout.nodes.map((node) => {
          const isSelected = node.id === selectedId;
          const isNeighbor = neighborIds.has(node.id);
          return (
            <g
              key={node.id}
              transform={`translate(${node.x}, ${node.y})`}
              className={`graph-node${isSelected ? " selected" : ""}${isNeighbor ? " neighbor" : ""}`}
              onClick={() => onSelect(node.id)}
            >
              <title>{node.id}</title>
              <rect width={NODE_WIDTH} height={NODE_HEIGHT} rx={8} />
              <text x={NODE_WIDTH / 2} y={NODE_HEIGHT / 2 + 5} textAnchor="middle">
                {node.kind === "package" ? "📦 " : ""}
                {node.label.length > 20 ? node.label.slice(0, 18) + "…" : node.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
