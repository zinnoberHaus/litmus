import type { LineageEdge, LineageNode } from "@/lib/fixtures";

interface LineageGraphProps {
  nodes: LineageNode[];
  edges: LineageEdge[];
}

const KIND_STYLES: Record<LineageNode["kind"], string> = {
  source: "fill-blue-50 stroke-blue-300",
  transform: "fill-neutral-50 stroke-neutral-300",
  metric: "fill-green-50 stroke-green-400",
};

const KIND_LABEL: Record<LineageNode["kind"], string> = {
  source: "source",
  transform: "transform",
  metric: "metric",
};

/**
 * Lays the nodes out left-to-right in the order they appear in the `nodes`
 * array. For a scaffold this is plenty — for production, swap in an actual
 * DAG layout (dagre/elkjs) or render on the server from the Python API.
 */
export function LineageGraph({ nodes, edges }: LineageGraphProps) {
  const cellW = 170;
  const cellH = 70;
  const gap = 40;
  const padX = 20;
  const padY = 30;

  const width = padX * 2 + nodes.length * cellW + (nodes.length - 1) * gap;
  const height = padY * 2 + cellH;

  const xFor = (i: number) => padX + i * (cellW + gap);
  const y = padY;
  const idToIndex = new Map(nodes.map((n, i) => [n.id, i]));

  return (
    <svg
      role="img"
      aria-label="Lineage graph"
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      className="max-w-full"
    >
      <defs>
        <marker
          id="arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#525252" />
        </marker>
      </defs>

      {/* edges */}
      {edges.map((e) => {
        const fromIdx = idToIndex.get(e.from);
        const toIdx = idToIndex.get(e.to);
        if (fromIdx === undefined || toIdx === undefined) return null;
        const x1 = xFor(fromIdx) + cellW;
        const x2 = xFor(toIdx);
        const y1 = y + cellH / 2;
        return (
          <line
            key={`${e.from}-${e.to}`}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y1}
            stroke="#525252"
            strokeWidth={1.25}
            markerEnd="url(#arrow)"
          />
        );
      })}

      {/* nodes */}
      {nodes.map((n, i) => (
        <g key={n.id} transform={`translate(${xFor(i)}, ${y})`}>
          <rect
            width={cellW}
            height={cellH}
            rx={8}
            ry={8}
            className={KIND_STYLES[n.kind]}
            strokeWidth={1}
          />
          <text
            x={cellW / 2}
            y={cellH / 2 - 4}
            textAnchor="middle"
            fontSize={13}
            fontWeight={600}
            fill="#171717"
          >
            {n.label}
          </text>
          <text
            x={cellW / 2}
            y={cellH / 2 + 14}
            textAnchor="middle"
            fontSize={10}
            fill="#737373"
          >
            {KIND_LABEL[n.kind]}
          </text>
        </g>
      ))}
    </svg>
  );
}
