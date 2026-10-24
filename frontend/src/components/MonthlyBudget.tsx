"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, Field, useToast } from "@/components/ui";
import { api, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type Grid = { year: number; categories: string[]; yearly: Record<string, number>; total: number; months: { month: number; locked: boolean; source: string; lines: Record<string, number>; total: number }[] };
type Vs = { months: { month: number; locked: boolean; budget: number; actual: number; pct: number; status: "under" | "near" | "over"; categories: Record<string, { budget: number; actual: number; pct: number; status: string }> }[] };
const tone = (s: string) => (s === "over" ? "bad" : s === "near" ? "warn" : "ok") as "bad" | "warn" | "ok";
const barColor = (s: string) => (s === "over" ? "var(--bad)" : s === "near" ? "var(--warn)" : "var(--ok)");
const toPaisa = (v: string) => Math.max(0, Math.round(+(v || 0) * 100));

export default function MonthlyBudget() {
  const { t } = useT(); const { has, prop } = useAuth(); const toast = useToast();
  const canEdit = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "TREASURER"); const canLock = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT");
  const now = new Date(); const [year, setYear] = useState(now.getFullYear());
  const [grid, setGrid] = useState<Grid | null>(null); const [vs, setVs] = useState<Vs | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({}); const [from, setFrom] = useState(1); const [override, setOverride] = useState(false);
  const key = (m: number, c: string) => `${m}:${c}`;

  const load = useCallback(async () => {
    const g = await api<Grid>(`/finance/budget/monthly?year=${year}`); setGrid(g); setDraft({});
    setVs(await api<Vs>(`/finance/budget/monthly/vs-actual?year=${year}`));
  }, [year]);
  useEffect(() => { load().catch((e) => toast.show(e.message)); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [load, prop?.id]);

  const val = (m: number, c: string) => draft[key(m, c)] ?? String((grid?.months[m - 1].lines[c] ?? 0) / 100);
  const dirty = Object.keys(draft).length > 0;
  const run = async (fn: () => Promise<void>) => { try { await fn(); } catch (e: any) { toast.show(e.message); } };
  const save = () => run(async () => {
    const months: Record<number, Record<string, number>> = {};
    for (const k of Object.keys(draft)) { const [m, c] = k.split(":"); (months[+m] ??= {})[c] = toPaisa(draft[k]); }
    await api("/finance/budget/monthly", { method: "PUT", body: { year, months, override } }); toast.show(t("bud.saved")); await load();
  });
  const copy = (mode: "month" | "even_split") => run(async () => {
    const r = await api<{ copied: number[]; skipped: number[] }>("/finance/budget/monthly/copy-forward", { body: { year, mode, from_month: from, override } });
    toast.show([t("bud.copied", { n: r.copied.length }), r.skipped.length ? t("bud.skipped", { n: r.skipped.length }) : ""].join(" ")); await load();
  });
  const lock = (m: number, locked: boolean) => run(async () => { await api("/finance/budget/monthly/lock", { body: { year, month: m, locked } }); await load(); });
  const closed = (m: number) => new Date(year, m, 0) < new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const cur = (m: number) => year === now.getFullYear() && m === now.getMonth() + 1;
  const hi = (m: number) => (cur(m) ? { background: "var(--blush)" } : undefined);
  const cell = { padding: "6px 8px", borderTop: "1px solid var(--line)", whiteSpace: "nowrap" } as const;

  if (!grid) return <Card>{t("bud.loading")}{toast.node}</Card>;
  const overCats = (m: number) => Object.entries(vs?.months[m - 1]?.categories ?? {}).filter(([, v]) => v.status === "over").map(([c]) => t(`fin.cat.${c}`));
  return (<div className="stack">
    <Card>
      <div className="row between wrap"><div><h3>{t("bud.title")}</h3><p className="hint">{t("bud.note")}</p></div>
        <div className="row" style={{ alignItems: "flex-end" }}><Field label={t("bud.year")}><select className="input" value={year} onChange={(e) => setYear(+e.target.value)}>{[-1, 0, 1].map((d) => <option key={d} value={now.getFullYear() + d}>{now.getFullYear() + d}</option>)}</select></Field></div></div>
      <div style={{ overflowX: "auto", marginTop: 10 }}>
        <table style={{ borderCollapse: "collapse", minWidth: 980, width: "100%" }}>
          <thead><tr><th style={{ ...cell, borderTop: 0, textAlign: "left", position: "sticky", left: 0, background: "var(--surface)", zIndex: 1 }}>{t("bud.category")}</th>
            {grid.months.map((m) => <th key={m.month} style={{ ...cell, borderTop: 0, textAlign: "center", ...hi(m.month) }}>{t(`bud.m.${m.month}`)}{cur(m.month) && <div className="small muted">{t("bud.now")}</div>}
              <div>{m.locked ? <Chip tone="mute">{t("bud.locked")}</Chip> : m.source === "yearly" ? <span className="small muted">{t("bud.from_yearly")}</span> : null}</div></th>)}
            <th style={{ ...cell, borderTop: 0, textAlign: "right" }}>{t("bud.total")}</th></tr></thead>
          <tbody>{grid.categories.map((c) => (<tr key={c}><td style={{ ...cell, fontWeight: 600, position: "sticky", left: 0, background: "var(--surface)" }}>{t(`fin.cat.${c}`)}</td>
            {grid.months.map((m) => <td key={m.month} style={{ ...cell, ...hi(m.month) }}><input className="input" inputMode="decimal" aria-label={`${t(`fin.cat.${c}`)} ${t(`bud.m.${m.month}`)}`} style={{ width: 92, textAlign: "right", padding: "6px 8px" }}
              disabled={!canEdit || (m.locked && !override)} value={val(m.month, c)} onChange={(e) => setDraft({ ...draft, [key(m.month, c)]: e.target.value })} /></td>)}
            <td style={{ ...cell, textAlign: "right", fontWeight: 700 }}>{money(grid.months.reduce((a, m) => a + toPaisa(val(m.month, c)), 0))}</td></tr>))}
            <tr><td style={{ ...cell, fontWeight: 700, position: "sticky", left: 0, background: "var(--surface)" }}>{t("bud.total")}</td>
              {grid.months.map((m) => <td key={m.month} style={{ ...cell, textAlign: "right", fontWeight: 700, ...hi(m.month) }}>{money(grid.categories.reduce((a, c) => a + toPaisa(val(m.month, c)), 0))}</td>)}
              <td style={{ ...cell, textAlign: "right", fontWeight: 700 }}>{money(grid.months.reduce((a, m) => a + grid.categories.reduce((b, c) => b + toPaisa(val(m.month, c)), 0), 0))}</td></tr>
            {canLock && <tr><td style={{ ...cell }} />{grid.months.map((m) => <td key={m.month} style={{ ...cell, textAlign: "center", ...hi(m.month) }}>{m.locked ? <Btn size="sm" variant="outline" onClick={() => lock(m.month, false)}>{t("bud.unlock")}</Btn> : closed(m.month) ? <Btn size="sm" variant="soft" onClick={() => lock(m.month, true)}>{t("bud.lock")}</Btn> : null}</td>)}<td style={cell} /></tr>}
          </tbody></table></div>
      {canEdit && <div className="row between wrap" style={{ marginTop: 12, gap: 10 }}>
        <div className="row wrap" style={{ gap: 8, alignItems: "center" }}>
          <label className="small row" style={{ gap: 6 }}>{t("bud.copy_from")}<select className="input" value={from} onChange={(e) => setFrom(+e.target.value)} style={{ width: "auto" }}>{grid.months.map((m) => <option key={m.month} value={m.month}>{t(`bud.m.${m.month}`)}</option>)}</select></label>
          <Btn variant="soft" size="sm" title={t("bud.copy_hint")} disabled={dirty || from >= 12} onClick={() => copy("month")}>{t("bud.copy")}</Btn>
          <Btn variant="soft" size="sm" title={t("bud.split_hint")} disabled={dirty} onClick={() => copy("even_split")}>{t("bud.split")}</Btn>
          <label className="small row" style={{ gap: 6 }}><input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} />{t("bud.override")}</label></div>
        <div className="row" style={{ alignItems: "center" }}>{dirty && <span className="small muted">{t("bud.unsaved")}</span>}<Btn onClick={save} disabled={!dirty}>{t("bud.save")}</Btn></div></div>}
      <p className="hint" style={{ marginTop: 8 }}>{t("bud.lock_hint")}</p>
    </Card>

    <Card><h3>{t("bud.vs")}</h3>
      <div style={{ overflowX: "auto", marginTop: 12 }}><div className="row" style={{ gap: 10, alignItems: "stretch", minWidth: 980 }}>{(vs?.months ?? []).map((m) => { const oc = overCats(m.month); return (
        <div key={m.month} style={{ flex: 1, minWidth: 74, padding: 8, borderRadius: 12, border: "1px solid var(--line)", ...hi(m.month) }}>
          <div className="small" style={{ fontWeight: 700, textAlign: "center" }}>{t(`bud.m.${m.month}`)}</div>
          <div style={{ height: 8, borderRadius: 5, background: "var(--line)", margin: "8px 0" }} title={`${t("bud.actual")} ${money(m.actual)} / ${t("bud.budget")} ${money(m.budget)}`}><div style={{ height: "100%", width: `${Math.min(100, m.pct)}%`, borderRadius: 5, background: barColor(m.status) }} /></div>
          <div className="small muted" style={{ textAlign: "center" }}>{t("bud.used", { n: m.pct })}</div>
          <div className="small" style={{ textAlign: "center" }}>{money(m.actual)}</div><div className="small muted" style={{ textAlign: "center" }}>{money(m.budget)}</div>
          <div style={{ textAlign: "center", marginTop: 6 }}><Chip tone={tone(m.status)}>{t(`bud.st.${m.status}`)}</Chip></div>
          {oc.length > 0 && <div className="small" style={{ color: "var(--bad)", marginTop: 6 }}>{oc.join(", ")}</div>}</div>); })}</div></div>
    </Card>
    {toast.node}
  </div>);
}
