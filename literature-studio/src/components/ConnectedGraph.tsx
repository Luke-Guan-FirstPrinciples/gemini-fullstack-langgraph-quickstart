import { trimTitle } from "../lib/format";
import type { ConnectedPapersGraph, ConnectedPapersNode } from "../lib/types";

const WIDTH = 760;
const HEIGHT = 420;
const PADDING = 34;

interface ConnectedGraphProps {
  graph: ConnectedPapersGraph;
}

interface Point {
  x: number;
  y: number;
}

const toLabelSet = (
  nodes: ConnectedPapersNode[],
  startId: string,
): Set<string> => {
  const closest = [...nodes]
    .sort((left, right) => left.path_length - right.path_length)
    .slice(0, 6)
    .map((node) => node.id);

  closest.push(startId);
  return new Set(closest);
};

export function ConnectedGraph({ graph }: ConnectedGraphProps) {
  const nodes = Object.values(graph.nodes);
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

  nodes.forEach((node) => {
    const x = PADDING + ((node.pos[0] - minX) / spanX) * (WIDTH - PADDING * 2);
    const y = PADDING + ((node.pos[1] - minY) / spanY) * (HEIGHT - PADDING * 2);
    points.set(node.id, { x, y });
  });

  const labelSet = toLabelSet(nodes, graph.start_id);

  return (
    <div className="graph-card">
      <div className="graph-heading">
        <div>
          <p className="mini-label">Similarity graph</p>
          <h3>Connected Papers map</h3>
        </div>
        <p className="muted-copy">
          SVG projection of the paper graph returned by the API.
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

          const opacity = Math.min(0.42, 0.05 + weight * 0.18);

          return (
            <line
              key={`${from}-${to}-${index}`}
              x1={start.x}
              y1={start.y}
              x2={end.x}
              y2={end.y}
              stroke="url(#edgeGlow)"
              strokeOpacity={opacity}
              strokeWidth={1}
            />
          );
        })}

        {nodes.map((node) => {
          const point = points.get(node.id);
          if (!point) {
            return null;
          }

          const isStart = node.id === graph.start_id;
          const radius = isStart
            ? 7
            : Math.max(3, 7 - Math.min(node.path_length, 6) * 0.45);

          return (
            <g key={node.id}>
              <circle
                cx={point.x}
                cy={point.y}
                r={radius}
                fill={isStart ? "#f6b655" : "#53d0cf"}
                fillOpacity={isStart ? 1 : 0.78}
                stroke={isStart ? "#fff2cf" : "rgba(255,255,255,0.25)"}
                strokeWidth={isStart ? 1.6 : 0.85}
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
