import type { TrustHistoryPoint, TrustStatus } from "@/lib/fixtures";

interface TrustHistoryChartProps {
  history: TrustHistoryPoint[];
  width?: number;
  height?: number;
}

const DOT_FILL: Record<TrustStatus, string> = {
  pass: "#16a34a",
  warn: "#ca8a04",
  fail: "#dc2626",
};

/**
 * Minimal dependency-free sparkline — just inline SVG so we don't pull in
 * recharts/visx for a scaffold. The metric detail page renders this inside a
 * "Trust History" card.
 */
export function TrustHistoryChart({
  history,
  width = 560,
  height = 120,
}: TrustHistoryChartProps) {
  if (history.length === 0) {
    return (
      <div className="text-sm text-neutral-500">No trust history yet.</div>
    );
  }

  const padX = 12;
  const padY = 12;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const xs = history.map((_, i) =>
    history.length === 1 ? padX + innerW / 2 : padX + (i / (history.length - 1)) * innerW,
  );
  const ys = history.map((p) => padY + (1 - p.score) * innerH);

  const path = xs
    .map((x, i) => `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${ys[i].toFixed(1)}`)
    .join(" ");

  // Shade the "warning band" (trust 0.5 - 0.9) behind the line.
  const warnTop = padY + (1 - 0.9) * innerH;
  const warnBottom = padY + (1 - 0.5) * innerH;
  const failBottom = padY + innerH;

  return (
    <svg
      role="img"
      aria-label="Trust history sparkline"
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      className="max-w-full"
    >
      {/* bands */}
      <rect
        x={padX}
        y={padY}
        width={innerW}
        height={warnTop - padY}
        fill="#dcfce7"
        opacity={0.5}
      />
      <rect
        x={padX}
        y={warnTop}
        width={innerW}
        height={warnBottom - warnTop}
        fill="#fef9c3"
        opacity={0.5}
      />
      <rect
        x={padX}
        y={warnBottom}
        width={innerW}
        height={failBottom - warnBottom}
        fill="#fee2e2"
        opacity={0.5}
      />

      {/* trend line */}
      <path
        d={path}
        fill="none"
        stroke="#1f2937"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* points */}
      {history.map((p, i) => (
        <g key={p.date}>
          <circle
            cx={xs[i]}
            cy={ys[i]}
            r={4}
            fill={DOT_FILL[p.status]}
            stroke="#ffffff"
            strokeWidth={1}
          />
        </g>
      ))}

      {/* axis labels (first + last date) */}
      <text
        x={padX}
        y={height - 1}
        fontSize={10}
        fill="#737373"
      >
        {history[0].date}
      </text>
      <text
        x={width - padX}
        y={height - 1}
        fontSize={10}
        fill="#737373"
        textAnchor="end"
      >
        {history[history.length - 1].date}
      </text>
    </svg>
  );
}
