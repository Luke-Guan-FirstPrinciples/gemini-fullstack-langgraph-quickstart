import { useState } from "react";
import { trimTitle } from "../lib/format";
import type { ConnectedPapersGraph, ConnectedPapersNode } from "../lib/types";

const WIDTH = 760;
const HEIGHT = 420;
const PADDING = 34;

interface ConnectedGraphProps {
  graph: ConnectedPapersGraph;
  highlightedNodeIds?: string[];
  onSelectNode?: (nodeId: string) => void;
  selectedNodeId?: string | null;
}

interface Point {
  x: number;
  y: number;
}

const toLabelSet = (
  nodes: ConnectedPapersNode[],
  startId: string,
  selectedNodeId: string | null,
  highlightedNodeIds: string[],
): Set<string> => {
  const closest = [...nodes]
    .sort((left, right) => left.path_length - right.path_length)
    .slice(0, 6)
    .map((node) => node.id);

  closest.push(startId);
  if (selectedNodeId) {
    closest.push(selectedNodeId);
  }
  closest.push(...highlightedNodeIds.slice(0, 5));
  return new Set(closest);
};

export function ConnectedGraph({
  graph,
  highlightedNodeIds = [],
  onSelectNode,
  selectedNodeId = null,
}: ConnectedGraphProps) {
  const nodes = Object.values(graph.nodes);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  if (nodes.length === 0) {
    return null;
  }

  const xValues = nodes.map((node) => node.pos[0]);
  const yValues = nodes.map((node) => node.pos[1]);

  const minX = Math.min(...xValues);
  const maxX = Math.max(...xValues);
  const minY = Math.min(...yValues);
  const maxY = Math.max(...yValues);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;

  const points = new Map<string, Point>();
  const connections = new Map<string, Set<string>>();

  nodes.forEach((node) => {
    const x = PADDING + ((node.pos[0] - minX) / spanX) * (WIDTH - PADDING * 2);
    const y = PADDING + ((node.pos[1] - minY) / spanY) * (HEIGHT - PADDING * 2);
    points.set(node.id, { x, y });
    connections.set(node.id, new Set());
  });

  graph.edges.forEach(([from, to]) => {
    connections.get(from)?.add(to);
    connections.get(to)?.add(from);
  });

  const activeNodeId = hoveredNodeId ?? selectedNodeId ?? graph.start_id;
  const activeNode = graph.nodes[activeNodeId] ?? graph.nodes[graph.start_id];
  const activeConnections = connections.get(activeNode.id) ?? new Set<string>();
  const focusSet = new Set<string>([
    activeNode.id,
    ...activeConnections,
    ...highlightedNodeIds,
  ]);
  const labelSet = toLabelSet(nodes, graph.start_id, selectedNodeId, highlightedNodeIds);

  return (
    <div className="graph-card">
      <div className="graph-heading">
        <div>
          <p className="mini-label">Similarity graph</p>
          <h3>Connected Papers map</h3>
        </div>
        <p className="muted-copy">
          Click a node to pin its neighborhood. Hovering temporarily previews a
          different local cluster.
        </p>
      </div>

      <div className="graph-legend">
        <span className="graph-legend-item start">Seed paper</span>
        <span className="graph-legend-item active">Focused node</span>
        <span className="graph-legend-item related">Related neighborhood</span>
      </div>

      <div className="graph-focus-card">
        <p className="mini-label">Focused node</p>
        <h3>{activeNode.title}</h3>
        <p className="muted-copy">
          {activeNode.year ?? "n/a"} · {activeConnections.size} direct graph links · path
          length {activeNode.path_length.toFixed(2)}
        </p>
      </div>

      <svg
        className="graph-svg"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Connected Papers graph view"
      >
        <defs>
          <linearGradient id="edgeGlow" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="rgba(246, 182, 85, 0.28)" />
            <stop offset="100%" stopColor="rgba(83, 208, 207, 0.12)" />
          </linearGradient>
        </defs>

        {graph.edges.slice(0, 700).map(([from, to, weight], index) => {
          const start = points.get(from);
          const end = points.get(to);

          if (!start || !end) {
            return null;
          }

          const edgeIsActive =
            (from === activeNode.id && activeConnections.has(to)) ||
            (to === activeNode.id && activeConnections.has(from)) ||
            (focusSet.has(from) && focusSet.has(to));
          const opacity = edgeIsActive
            ? Math.min(0.8, 0.12 + weight * 0.28)
            : Math.min(0.12, 0.02 + weight * 0.08);

          return (
            <line
              key={`${from}-${to}-${index}`}
              x1={start.x}
              y1={start.y}
              x2={end.x}
              y2={end.y}
              stroke="url(#edgeGlow)"
              strokeOpacity={opacity}
              strokeWidth={edgeIsActive ? 1.6 : 1}
            />
          );
        })}

        {nodes.map((node) => {
          const point = points.get(node.id);
          if (!point) {
            return null;
          }

          const isStart = node.id === graph.start_id;
          const isSelected = node.id === selectedNodeId;
          const isActive = node.id === activeNode.id;
          const isRelated = focusSet.has(node.id);
          const radius = isStart
            ? 7
            : isActive
              ? 8
              : Math.max(3, 7 - Math.min(node.path_length, 6) * 0.45);
          const fill = isStart ? "#f6b655" : isActive ? "#ff7a6b" : "#53d0cf";
          const fillOpacity = isActive ? 0.98 : isRelated ? 0.88 : 0.34;
          const stroke = isSelected
            ? "#fff8da"
            : isActive
              ? "#ffe2dc"
              : "rgba(255,255,255,0.25)";

          return (
            <g
              key={node.id}
              className="graph-node"
              onClick={() => onSelectNode?.(node.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectNode?.(node.id);
                }
              }}
              onMouseEnter={() => setHoveredNodeId(node.id)}
              onMouseLeave={() => setHoveredNodeId(null)}
              role="button"
              tabIndex={0}
            >
              <circle
                cx={point.x}
                cy={point.y}
                r={radius}
                fill={fill}
                fillOpacity={isStart ? 1 : fillOpacity}
                stroke={isStart ? "#fff2cf" : stroke}
                strokeWidth={isSelected || isActive || isStart ? 1.8 : 0.85}
              >
                <title>{node.title}</title>
              </circle>

              {labelSet.has(node.id) ? (
                <text
                  x={point.x + 9}
                  y={point.y - 8}
                  fill={isStart ? "#fff7df" : "#d7f9f8"}
                  fontSize="11"
                >
                  {trimTitle(node.title, isStart ? 36 : 26)}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
