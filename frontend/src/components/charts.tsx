import type { TrendPoint } from "../lib/types";

export function BarList({ rows, unit = "", max }: { rows: { label: string; value: number; note?: string }[]; unit?: string; max?: number }) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="bars" aria-label="Bar chart">
      {rows.map((r) => (
        <li key={r.label}>
          <span className="bar-label" title={r.label}>
            {r.label}
          </span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${Math.max(2, Math.min(100, (r.value / top) * 100))}%` }} />
          </span>
          <span className="bar-value">
            {r.value}
            {unit}
            {r.note && <small> {r.note}</small>}
          </span>
        </li>
      ))}
    </ul>
  );
}

// The brand rose first, then hues far enough apart to tell five lines apart on white or dark.
const COLORS = ["#e0475e", "#0f8b8d", "#4f6bed", "#d98a1a", "#8b5cf6"];

/** Weekly counts per skill as an SVG line chart. */
export function TrendChart({ points }: { points: TrendPoint[] }) {
  const weeks = [...new Set(points.map((p) => p.week))].sort();
  const skills = [...new Set(points.map((p) => p.skill))];
  if (weeks.length === 0) return null;
  const W = 640, H = 220, pad = { l: 36, r: 12, t: 12, b: 28 };
  const max = Math.max(1, ...points.map((p) => p.jobs));
  const x = (i: number) => pad.l + (weeks.length === 1 ? (W - pad.l - pad.r) / 2 : (i / (weeks.length - 1)) * (W - pad.l - pad.r));
  const y = (v: number) => H - pad.b - (v / max) * (H - pad.t - pad.b);
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Weekly postings for ${skills.join(", ")}`}>
        <line x1={pad.l} y1={H - pad.b} x2={W - pad.r} y2={H - pad.b} className="axis" />
        <line x1={pad.l} y1={pad.t} x2={pad.l} y2={H - pad.b} className="axis" />
        <text x={pad.l - 6} y={pad.t + 4} textAnchor="end" className="tick">{max}</text>
        <text x={pad.l - 6} y={H - pad.b} textAnchor="end" className="tick">0</text>
        <text x={pad.l} y={H - 8} className="tick">{weeks[0]}</text>
        <text x={W - pad.r} y={H - 8} textAnchor="end" className="tick">{weeks[weeks.length - 1]}</text>
        {skills.map((skill, si) => {
          const series = weeks.map((w, i) => ({ i, v: points.find((p) => p.skill === skill && p.week === w)?.jobs ?? 0 }));
          return (
            <g key={skill} stroke={COLORS[si % COLORS.length]} fill={COLORS[si % COLORS.length]}>
              <polyline fill="none" strokeWidth="2" points={series.map((s) => `${x(s.i)},${y(s.v)}`).join(" ")} />
              {series.map((s) => (
                <circle key={s.i} cx={x(s.i)} cy={y(s.v)} r="3" stroke="none" />
              ))}
            </g>
          );
        })}
      </svg>
      <figcaption>
        {skills.map((s, i) => (
          <span key={s} className="legend">
            <i style={{ background: COLORS[i % COLORS.length] }} /> {s}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
