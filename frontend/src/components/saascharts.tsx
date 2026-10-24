"use client";
/** Small SVG charts for the SaaS reports. No chart library. Colours come from the theme tokens, so light and dark both work. */
import type { ReactNode } from "react";

export const SERIES_COLORS = ["var(--primary)", "var(--info)", "var(--ok)", "var(--warn)", "var(--bad)"];
const W = 720, H = 240, PL = 54, PR = 12, PT = 14, PB = 30;

const nice = (max: number) => {
  if (max <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(max)));
  const n = max / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
};
/** Short axis label for paisa: 12.5k, 3.2L (lakh), 1.1Cr (crore), in Latin digits. */
export const shortBdt = (paisa: number) => {
  const v = Math.abs(paisa) / 100, s = paisa < 0 ? "-" : "";
  if (v >= 1e7) return `${s}${+(v / 1e7).toFixed(1)}Cr`;
  if (v >= 1e5) return `${s}${+(v / 1e5).toFixed(1)}L`;
  if (v >= 1e3) return `${s}${+(v / 1e3).toFixed(1)}k`;
  return `${s}${Math.round(v)}`;
};
export const monthLabel = (ym: string) => new Date(Number(ym.slice(0, 4)), Number(ym.slice(5, 7)) - 1, 1).toLocaleDateString("en-GB", { month: "short", year: "2-digit" });

export function Legend({ items }: { items: { name: string; color: string }[] }) {
  return <div className="row wrap" style={{ gap: 14, marginBottom: 6 }}>{items.map((s) => <span key={s.name} className="small row" style={{ gap: 6 }}><i style={{ width: 12, height: 12, borderRadius: 3, background: s.color, display: "inline-block" }} />{s.name}</span>)}</div>;
}

function Frame({ children, label }: { children: ReactNode; label: string }) {
  return <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} style={{ width: "100%", height: "auto", display: "block" }}>{children}</svg>;
}

function Axis({ min, max, fmt }: { min: number; max: number; fmt: (n: number) => string }) {
  const ticks = [0, 1, 2, 3, 4].map((i) => min + ((max - min) * i) / 4);
  const y = (v: number) => PT + (1 - (v - min) / (max - min || 1)) * (H - PT - PB);
  return <g>{ticks.map((v) => <g key={v}><line x1={PL} x2={W - PR} y1={y(v)} y2={y(v)} style={{ stroke: "var(--line)" }} strokeWidth={1} /><text x={PL - 6} y={y(v) + 4} textAnchor="end" fontSize={11} style={{ fill: "var(--muted)" }}>{fmt(v)}</text></g>)}</g>;
}

/** Grouped bars: one group per label, one bar per series. */
export function BarChart({ labels, series, fmt = shortBdt, label }: { labels: string[]; series: { name: string; color: string; values: number[] }[]; fmt?: (n: number) => string; label: string }) {
  const max = nice(Math.max(1, ...series.flatMap((s) => s.values)));
  const gw = (W - PL - PR) / Math.max(1, labels.length), bw = Math.min(26, (gw - 8) / series.length);
  const y = (v: number) => PT + (1 - v / max) * (H - PT - PB);
  return (
    <div><Legend items={series} />
      <Frame label={label}><Axis min={0} max={max} fmt={fmt} />
        {labels.map((l, i) => {
          const x0 = PL + i * gw + (gw - bw * series.length) / 2;
          return <g key={l}>{series.map((s, k) => <rect key={s.name} x={x0 + k * bw} y={y(s.values[i])} width={bw - 2} height={Math.max(0, H - PB - y(s.values[i]))} rx={3} style={{ fill: s.color }}><title>{`${l} · ${s.name}: ${fmt(s.values[i])}`}</title></rect>)}
            <text x={PL + i * gw + gw / 2} y={H - 10} textAnchor="middle" fontSize={11} style={{ fill: "var(--muted)" }}>{l}</text></g>;
        })}
      </Frame></div>
  );
}

/** Lines with dots, one per series. */
export function LineChart({ labels, series, fmt = shortBdt, label }: { labels: string[]; series: { name: string; color: string; values: number[] }[]; fmt?: (n: number) => string; label: string }) {
  const max = nice(Math.max(1, ...series.flatMap((s) => s.values)));
  const x = (i: number) => PL + ((W - PL - PR) * (labels.length === 1 ? 0.5 : i / (labels.length - 1)));
  const y = (v: number) => PT + (1 - v / max) * (H - PT - PB);
  return (
    <div><Legend items={series} />
      <Frame label={label}><Axis min={0} max={max} fmt={fmt} />
        {series.map((s) => <g key={s.name}><polyline fill="none" strokeWidth={2.5} strokeLinejoin="round" style={{ stroke: s.color }} points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />
          {s.values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={3.5} style={{ fill: s.color }}><title>{`${labels[i]} · ${s.name}: ${fmt(v)}`}</title></circle>)}</g>)}
        {labels.map((l, i) => (labels.length <= 12 || i % 2 === 0) && <text key={l} x={x(i)} y={H - 10} textAnchor="middle" fontSize={11} style={{ fill: "var(--muted)" }}>{l}</text>)}
      </Frame></div>
  );
}

/** Movement chart: gains stack above zero, losses stack below, a line marks the net change. */
export function MovementChart({ labels, ups, downs, label, fmt = shortBdt }: { labels: string[]; ups: { name: string; color: string; values: number[] }[]; downs: { name: string; color: string; values: number[] }[]; label: string; fmt?: (n: number) => string }) {
  const sum = (ss: { values: number[] }[], i: number) => ss.reduce((a, s) => a + s.values[i], 0);
  const top = nice(Math.max(1, ...labels.map((_, i) => sum(ups, i)))), bot = nice(Math.max(0, ...labels.map((_, i) => sum(downs, i))));
  const min = bot ? -bot : 0;
  const y = (v: number) => PT + (1 - (v - min) / (top - min || 1)) * (H - PT - PB);
  const gw = (W - PL - PR) / Math.max(1, labels.length), bw = Math.min(30, gw - 10);
  return (
    <div><Legend items={[...ups, ...downs]} />
      <Frame label={label}><Axis min={min} max={top} fmt={fmt} />
        <line x1={PL} x2={W - PR} y1={y(0)} y2={y(0)} style={{ stroke: "var(--muted)" }} strokeWidth={1.2} />
        {labels.map((l, i) => {
          const x0 = PL + i * gw + (gw - bw) / 2; let up = 0, dn = 0;
          return <g key={l}>
            {ups.map((s) => { const v = s.values[i], r = <rect key={s.name} x={x0} y={y(up + v)} width={bw} height={Math.max(0, y(up) - y(up + v))} style={{ fill: s.color }}><title>{`${l} · ${s.name}: ${fmt(v)}`}</title></rect>; up += v; return r; })}
            {downs.map((s) => { const v = s.values[i], r = <rect key={s.name} x={x0} y={y(0) + (y(-dn) - y(0))} width={bw} height={Math.max(0, y(-dn - v) - y(-dn))} style={{ fill: s.color }}><title>{`${l} · ${s.name}: -${fmt(v)}`}</title></rect>; dn += v; return r; })}
            <text x={PL + i * gw + gw / 2} y={H - 10} textAnchor="middle" fontSize={11} style={{ fill: "var(--muted)" }}>{l}</text></g>;
        })}
        <polyline fill="none" strokeWidth={2} strokeDasharray="5 4" style={{ stroke: "var(--text)" }} points={labels.map((_, i) => `${PL + i * gw + gw / 2},${y(sum(ups, i) - sum(downs, i))}`).join(" ")} />
      </Frame></div>
  );
}

/** Horizontal bars with a value on the right; the CSS .bar from the design system. */
export function HBars({ rows, fmt, color = "var(--primary)" }: { rows: { key: string; label: string; value: number }[]; fmt: (n: number) => string; color?: string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return <div className="stack" style={{ gap: 10 }}>{rows.map((r) => <div key={r.key}><div className="row between small"><b>{r.label}</b><span>{fmt(r.value)}</span></div>
    <div style={{ height: 10, borderRadius: 6, background: "var(--line)", marginTop: 4 }}><i style={{ display: "block", height: "100%", width: `${Math.max(2, (r.value / max) * 100)}%`, borderRadius: 6, background: color }} /></div></div>)}</div>;
}
