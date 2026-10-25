"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Bar, Btn, Card, Chip, Empty, Field, PageHead, Stat, Tabs } from "@/components/ui";
import { HBars, BarChart, LineChart, MovementChart, monthLabel } from "@/components/saascharts";
import { api, fdate, money, store } from "@/lib/api";
import { keyLabel } from "@/lib/act";
import { useT } from "@/lib/i18n";

type Meta = { reports: string[]; plans: string[]; bands: string[]; cities: string[]; role: string };
const todayISO = () => new Date().toISOString().slice(0, 10);
const yearAgoISO = () => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 11); return d.toISOString().slice(0, 10); };
const pct = (n: number | null | undefined) => (n === null || n === undefined ? "-" : `${n}%`);

export default function Reports() {
  const { t } = useT();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [tab, setTab] = useState("");
  const [f, setF] = useState({ from: yearAgoISO(), to: todayISO(), plan: "", band: "", city: "" });
  const [d, setD] = useState<any>(null); const [err, setErr] = useState("");
  const [q, setQ] = useState(""); const [page, setPage] = useState(1);
  useEffect(() => { api<Meta>("/saas/reports/meta").then((m) => { setMeta(m); setTab(m.reports[0] ?? ""); }); }, []);
  const qs = useMemo(() => {
    const p = new URLSearchParams({ from: f.from, to: f.to });
    (["plan", "band", "city"] as const).forEach((k) => f[k] && p.set(k, f[k]));
    return p;
  }, [f]);
  const load = useCallback(() => {
    if (!tab) return;
    const p = new URLSearchParams(qs);
    if (tab === "health") { p.set("q", q); p.set("page", String(page)); p.set("size", "10"); }
    setErr("");
    api(`/saas/reports/${tab}?${p}`).then(setD).catch((e) => { setD(null); setErr(e.message); });
  }, [tab, qs, q, page]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(1); }, [tab, qs, q]);

  const csv = async () => {
    const res = await fetch(`/api/saas/reports/${tab}/csv?${qs}${tab === "health" && q ? `&q=${encodeURIComponent(q)}` : ""}`, { headers: { Authorization: `Bearer ${store.token}` } });
    if (!res.ok) return;
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a"); a.href = url; a.download = `flatwise-${tab}-${f.from}-${f.to}.csv`; a.click(); URL.revokeObjectURL(url);
  };
  if (!meta) return <p className="muted">{t("common.loading")}</p>;
  const ok = !!d && d.report === tab;
  const funnelOnly = meta.reports.length === 1 && meta.reports[0] === "funnel";
  return (
    <>
      <style>{`.rep-print-head{display:none} @media print{.rep-print-head{display:block;margin-bottom:12px} .card{break-inside:avoid} @page{size:A4 landscape;margin:12mm}}`}</style>
      <PageHead helpKey="saas-invoices" title={t("rep.title")} sub={t("rep.sub")} actions={<div className="no-print row"><Btn variant="outline" onClick={() => window.print()}>{t("rep.print")}</Btn><Btn onClick={csv}>{t("rep.export")}</Btn></div>} />
      <div className="no-print" style={{ marginBottom: 14 }}><Tabs value={tab} onChange={setTab} items={meta.reports.map((r) => ({ id: r, label: t(`rep.t.${r}`) }))} /></div>
      <div className="no-print grid g4" style={{ marginBottom: 18, alignItems: "end" }}>
        <Field label={t("rep.from")}><input className="input" type="date" value={f.from} max={f.to} onChange={(e) => setF({ ...f, from: e.target.value })} /></Field>
        <Field label={t("rep.to")}><input className="input" type="date" value={f.to} min={f.from} onChange={(e) => setF({ ...f, to: e.target.value })} /></Field>
        {!funnelOnly && <Field label={t("rep.plan")}><select className="input" value={f.plan} onChange={(e) => setF({ ...f, plan: e.target.value })}><option value="">{t("rep.allplans")}</option>{meta.plans.map((p) => <option key={p} value={p}>{keyLabel(t, p)}</option>)}</select></Field>}
        <Field label={t("rep.band")}><select className="input" value={f.band} onChange={(e) => setF({ ...f, band: e.target.value })}><option value="">{t("rep.allbands")}</option>{meta.bands.map((b) => <option key={b} value={b}>{b}</option>)}</select></Field>
        <Field label={t("rep.city")}><select className="input" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}><option value="">{t("rep.allcities")}</option>{meta.cities.map((c) => <option key={c} value={c}>{c}</option>)}</select></Field>
      </div>
      <div className="rep-print-head"><b>FlatWise · {t(`rep.t.${tab}`)}</b><div className="small">{fdate(f.from)} - {fdate(f.to)}{f.plan ? ` · ${keyLabel(t, f.plan)}` : ""}{f.band ? ` · ${f.band}` : ""}{f.city ? ` · ${f.city}` : ""} · {t("rep.generated", { d: fdate(new Date().toISOString()) })}</div></div>
      {err && <p className="muted">{err}</p>}
      {!d && !err && <p className="muted">{t("common.loading")}</p>}
      {ok && tab === "revenue" && <Revenue d={d} />}
      {ok && tab === "mrr" && <Mrr d={d} />}
      {ok && tab === "customers" && <Customers d={d} />}
      {ok && tab === "collections" && <Collections d={d} />}
      {ok && tab === "credits" && <Credits d={d} />}
      {ok && tab === "funnel" && <Funnel d={d} />}
      {ok && tab === "health" && <Health d={d} q={q} setQ={setQ} page={page} setPage={setPage} />}
    </>
  );
}

function Revenue({ d }: { d: any }) {
  const { t } = useT();
  const labels = d.series.map((r: any) => monthLabel(r.month));
  const tot = d.totals;
  return (
    <div className="stack">
      <div className="grid g4">
        <Stat label={t("rep.rev.billed")} value={money(tot.billed)} /><Stat label={t("rep.rev.collected")} value={money(tot.collected)} note={`${t("rep.rev.rate")}: ${pct(tot.billed ? Math.round((tot.collected / tot.billed) * 100) : null)}`} />
        <Stat label={t("rep.rev.subscription")} value={money(tot.subscription)} /><Stat label={t("rep.rev.credits")} value={money(tot.credits)} note={`${t("rep.rev.setup")}: ${money(tot.setup)}`} />
      </div>
      <Card><h3>{t("rep.rev.chart")}</h3>
        <BarChart label={t("rep.rev.chart")} labels={labels} series={[{ name: t("rep.rev.billed"), color: "var(--primary)", values: d.series.map((r: any) => r.billed) }, { name: t("rep.rev.collected"), color: "var(--ok)", values: d.series.map((r: any) => r.collected) }]} /></Card>
      <div className="grid g2">
        <Card><h3>{t("rep.rev.type")}</h3>
          <BarChart label={t("rep.rev.type")} labels={labels} series={[{ name: t("rep.rev.subscription"), color: "var(--primary)", values: d.series.map((r: any) => r.subscription) }, { name: t("rep.rev.credits"), color: "var(--info)", values: d.series.map((r: any) => r.credits) }, { name: t("rep.rev.setup"), color: "var(--warn)", values: d.series.map((r: any) => r.setup) }]} /></Card>
        <div className="stack">
          <Card><h3>{t("rep.rev.byplan")}</h3>{d.by_plan.length ? <div style={{ marginTop: 12 }}><HBars rows={d.by_plan.map((p: any) => ({ key: p.key, label: keyLabel(t, p.key), value: p.amount }))} fmt={money} /></div> : <Empty>{t("rep.none")}</Empty>}</Card>
          <Card><h3>{t("rep.rev.bycity")}</h3>{d.by_city.length ? <div style={{ marginTop: 12 }}><HBars color="var(--info)" rows={d.by_city.map((p: any) => ({ key: p.key, label: p.key, value: p.amount }))} fmt={money} /></div> : <Empty>{t("rep.none")}</Empty>}</Card>
        </div>
      </div>
      <div className="table-wrap"><table className="t"><thead><tr><th>{t("rep.rev.month")}</th>{["billed", "collected", "subscription", "credits", "setup", "refunds"].map((k) => <th key={k} className="num">{t(`rep.rev.${k}`)}</th>)}</tr></thead>
        <tbody>{d.series.map((r: any) => <tr key={r.month}><td>{monthLabel(r.month)}</td>{["billed", "collected", "subscription", "credits", "setup", "refunds"].map((k) => <td key={k} className="num">{money(r[k])}</td>)}</tr>)}</tbody></table></div>
    </div>
  );
}

function Mrr({ d }: { d: any }) {
  const { t } = useT();
  const labels = d.series.map((r: any) => monthLabel(r.month));
  const col = (k: string) => d.series.map((r: any) => r[k]);
  return (
    <div className="stack">
      <div className="grid g4">
        <Stat label={t("rep.mrr.now")} value={money(d.current_mrr)} /><Stat label={t("rep.mrr.arr")} value={money(d.current_arr)} />
        <Stat label={t("rep.mrr.new")} value={money(d.totals.new)} note={`${t("rep.mrr.expansion")}: ${money(d.totals.expansion)}`} /><Stat label={t("rep.mrr.churn")} value={money(d.totals.churn)} note={`${t("rep.mrr.contraction")}: ${money(d.totals.contraction)}`} />
      </div>
      <Card><h3>{t("rep.mrr.chart")}</h3><LineChart label={t("rep.mrr.chart")} labels={labels} series={[{ name: "MRR", color: "var(--primary)", values: col("end") }, { name: "ARR / 12", color: "var(--info)", values: col("arr").map((v: number) => v / 12) }]} /></Card>
      <Card><h3>{t("rep.mrr.moves")}</h3>
        <MovementChart label={t("rep.mrr.moves")} labels={labels} ups={[{ name: t("rep.mrr.new"), color: "var(--ok)", values: col("new") }, { name: t("rep.mrr.expansion"), color: "var(--info)", values: col("expansion") }]}
          downs={[{ name: t("rep.mrr.contraction"), color: "var(--warn)", values: col("contraction") }, { name: t("rep.mrr.churn"), color: "var(--bad)", values: col("churn") }]} /></Card>
      <div className="grid g2">
        <Card><h3>{t("rep.mrr.byplan")}</h3>{d.by_plan.length ? <div style={{ marginTop: 12 }}><HBars rows={d.by_plan.map((p: any) => ({ key: p.key, label: keyLabel(t, p.key), value: p.amount }))} fmt={money} /></div> : <Empty>{t("rep.none")}</Empty>}</Card>
      </div>
      <div className="table-wrap"><table className="t"><thead><tr><th>{t("rep.rev.month")}</th>{["opening", "new", "expansion", "contraction", "churn", "closing"].map((k) => <th key={k} className="num">{t(`rep.mrr.${k}`)}</th>)}<th className="num">ARR</th><th className="num">{t("rep.mrr.customers")}</th></tr></thead>
        <tbody>{d.series.map((r: any) => <tr key={r.month}><td>{monthLabel(r.month)}</td><td className="num">{money(r.start)}</td><td className="num">{money(r.new)}</td><td className="num">{money(r.expansion)}</td><td className="num">{money(r.contraction)}</td><td className="num">{money(r.churn)}</td><td className="num"><b>{money(r.end)}</b></td><td className="num">{money(r.arr)}</td><td className="num">{r.customers_end}</td></tr>)}</tbody></table></div>
    </div>
  );
}

function Customers({ d }: { d: any }) {
  const { t } = useT();
  const c = d.counts;
  return (
    <div className="stack">
      <div className="grid g4">
        <Stat label={t("rep.cu.active")} value={c.active + c.past_due} note={c.past_due ? `${c.past_due} ${t("sub.past_due").toLowerCase()}` : undefined} /><Stat label={t("rep.cu.trial")} value={c.trial} />
        <Stat label={t("rep.cu.suspended")} value={c.suspended} /><Stat label={t("rep.cu.churned")} value={c.churned} />
      </div>
      <div className="grid g4">
        <Stat label={t("rep.cu.conv")} value={pct(d.conversion_pct)} note={`${d.trials_converted} / ${d.trials_started}`} /><Stat label={t("rep.cu.arpb")} value={money(d.arpb)} note={`${d.buildings_paying} ${t("saas.b.title").toLowerCase()}`} />
        <Stat label={t("rep.cu.arpf")} value={money(d.arpf)} note={`${d.flats_paying} ${t("saas.stat.flats").toLowerCase()}`} /><Stat label={t("rep.mrr.now")} value={money(d.mrr)} />
      </div>
      <p className="small muted">{t("rep.cu.note")}</p>
      <Card><h3>{t("rep.cu.byplan")}</h3>{d.by_plan.length ? <div className="table-wrap" style={{ marginTop: 10 }}><table className="t"><thead><tr><th>{t("rep.plan")}</th><th className="num">{t("rep.cu.customers")}</th><th className="num">MRR</th></tr></thead>
        <tbody>{d.by_plan.map((p: any) => <tr key={p.key}><td><b>{keyLabel(t, p.key)}</b></td><td className="num">{p.customers}</td><td className="num">{money(p.mrr)}</td></tr>)}</tbody></table></div> : <Empty>{t("rep.none")}</Empty>}</Card>
    </div>
  );
}

function Collections({ d }: { d: any }) {
  const { t } = useT();
  const max = Math.max(1, ...d.buckets.map((b: any) => b.amount));
  return (
    <div className="stack">
      <div className="grid g4">
        <Stat label={t("rep.co.outstanding")} value={money(d.outstanding)} note={`${d.count} ${t("rep.co.invoices").toLowerCase()}`} /><Stat label={t("rep.co.overdue")} value={money(d.overdue)} />
      </div>
      <Card><h3>{t("rep.co.ageing")}</h3><div className="stack" style={{ marginTop: 14 }}>
        {d.buckets.map((b: any) => <div key={b.key}><div className="row between small"><b>{t(`rep.co.b.${b.key}`)}</b><span>{b.count} · {money(b.amount)}</span></div><Bar pct={(b.amount / max) * 100} spark={b.key === "d90p" && b.amount > 0} /></div>)}</div></Card>
      <Card><h3>{t("rep.co.top")}</h3>{d.top_overdue.length ? <div className="table-wrap" style={{ marginTop: 10 }}><table className="t"><thead><tr><th>{t("rep.he.building")}</th><th>{t("rep.city")}</th><th className="num">{t("rep.co.invoices")}</th><th className="num">{t("common.amount")}</th><th className="num">{t("rep.co.oldest")}</th><th /></tr></thead>
        <tbody>{d.top_overdue.map((r: any) => <tr key={r.org_id}><td><Link href={`/app/saas/buildings/${r.org_id}`}><b>{r.name}</b></Link></td><td>{r.city}</td><td className="num">{r.invoices}</td><td className="num">{money(r.amount)}</td><td className="num"><Chip tone={r.oldest_days > 60 ? "bad" : "warn"}>{r.oldest_days}</Chip></td><td><Link href={`/app/saas/invoice/statement/${r.org_id}`}>{t("rep.co.statement")}</Link></td></tr>)}</tbody></table></div> : <Empty>{t("rep.none")}</Empty>}</Card>
    </div>
  );
}

function Credits({ d }: { d: any }) {
  const { t } = useT();
  const labels = d.sms.series.map((r: any) => monthLabel(r.month));
  const num = (n: number) => n.toLocaleString("en-US");
  const tot = d.sms.totals;
  return (
    <div className="stack">
      <div className="grid g4">
        <Stat label={`${t("rep.cr.sms")}: ${t("rep.cr.sold")}`} value={num(tot.purchased)} /><Stat label={t("rep.cr.allowance")} value={num(tot.allowance)} />
        <Stat label={t("rep.cr.consumed")} value={num(tot.consumed)} /><Stat label={t("rep.cr.sales")} value={money(tot.sales)} />
      </div>
      <Card><h3>{t("rep.cr.sms")} · {t("rep.cr.chart")}</h3>
        <BarChart fmt={num} label={t("rep.cr.chart")} labels={labels} series={[{ name: t("rep.cr.sold"), color: "var(--primary)", values: d.sms.series.map((r: any) => r.purchased) }, { name: t("rep.cr.allowance"), color: "var(--info)", values: d.sms.series.map((r: any) => r.allowance) }, { name: t("rep.cr.consumed"), color: "var(--warn)", values: d.sms.series.map((r: any) => r.consumed) }]} /></Card>
      {d.email && <Card><h3>{t("rep.cr.email")} · {t("rep.cr.chart")}</h3>
        <BarChart fmt={num} label={t("rep.cr.email")} labels={d.email.series.map((r: any) => monthLabel(r.month))} series={[{ name: t("rep.cr.sold"), color: "var(--primary)", values: d.email.series.map((r: any) => r.purchased) }, { name: t("rep.cr.allowance"), color: "var(--info)", values: d.email.series.map((r: any) => r.allowance) }, { name: t("rep.cr.consumed"), color: "var(--warn)", values: d.email.series.map((r: any) => r.consumed) }]} /></Card>}
      <div className="grid g2">
        <Card><h3>{t("rep.cr.top")}</h3>{d.top_consumers.length ? <div className="stack" style={{ marginTop: 10 }}>{d.top_consumers.map((r: any) => <div key={r.org_id} className="row between small"><Link href={`/app/saas/buildings/${r.org_id}`}><b>{r.name}</b></Link><span>{t("rep.cr.used")} {num(r.consumed)} · {t("rep.cr.balance")} {num(r.balance)}</span></div>)}</div> : <Empty>{t("rep.none")}</Empty>}</Card>
        <Card><h3>{t("rep.cr.low")}</h3>{d.lowest_balance.length ? <div className="stack" style={{ marginTop: 10 }}>{d.lowest_balance.map((r: any) => <div key={r.org_id} className="row between small"><Link href={`/app/saas/buildings/${r.org_id}`}><b>{r.name}</b></Link><Chip tone={r.balance < 100 ? "bad" : "warn"}>{num(r.balance)}</Chip></div>)}</div> : <Empty>{t("rep.none")}</Empty>}</Card>
      </div>
    </div>
  );
}

function Funnel({ d }: { d: any }) {
  const { t } = useT();
  const max = Math.max(1, ...d.stages.map((s: any) => s.reached));
  return (
    <div className="stack">
      <div className="grid g4">
        <Stat label={t("rep.fu.total")} value={d.total} /><Stat label={t("rep.fu.win")} value={pct(d.win_pct)} /><Stat label={t("lead.won")} value={d.stages.find((s: any) => s.stage === "won")?.now ?? 0} /><Stat label={t("rep.fu.lost")} value={d.lost} />
      </div>
      <div className="grid g2">
        <Card><h3>{t("rep.fu.chart")}</h3><div className="stack" style={{ marginTop: 14 }}>
          {d.stages.map((s: any) => <div key={s.stage}><div className="row between small"><b>{t(`lead.${s.stage}`)}</b><span>{s.reached}{s.conv_pct !== null ? ` · ${s.conv_pct}%` : ""}</span></div><Bar pct={(s.reached / max) * 100} spark={s.stage === "won"} /></div>)}</div></Card>
        <Card><h3>{t("rep.fu.stage")}</h3><div className="table-wrap" style={{ marginTop: 10 }}><table className="t"><thead><tr><th>{t("rep.fu.stage")}</th><th className="num">{t("rep.fu.now")}</th><th className="num">{t("rep.fu.reached")}</th><th className="num">{t("rep.fu.conv")}</th><th className="num">{t("rep.fu.days")}</th></tr></thead>
          <tbody>{d.stages.map((s: any) => <tr key={s.stage}><td><b>{t(`lead.${s.stage}`)}</b></td><td className="num">{s.now}</td><td className="num">{s.reached}</td><td className="num">{pct(s.conv_pct)}</td><td className="num">{s.avg_days ?? "-"}</td></tr>)}</tbody></table></div></Card>
      </div>
      <Card><h3>{t("rep.fu.bysource")}</h3>{d.by_source.length ? <div className="table-wrap" style={{ marginTop: 10 }}><table className="t"><thead><tr><th>{t("rep.fu.source")}</th><th className="num">{t("rep.fu.total")}</th><th className="num">{t("rep.fu.won")}</th><th className="num">{t("rep.fu.lost")}</th><th className="num">{t("rep.fu.win")}</th></tr></thead>
        <tbody>{d.by_source.map((s: any) => <tr key={s.source}><td><b>{keyLabel(t, s.source)}</b></td><td className="num">{s.total}</td><td className="num">{s.won}</td><td className="num">{s.lost}</td><td className="num">{s.win_pct}%</td></tr>)}</tbody></table></div> : <Empty>{t("rep.none")}</Empty>}</Card>
    </div>
  );
}

function Health({ d, q, setQ, page, setPage }: { d: any; q: string; setQ: (v: string) => void; page: number; setPage: (n: number) => void }) {
  const { t } = useT();
  const pages = Math.max(1, Math.ceil(d.total / d.size));
  return (
    <div>
      <div className="toolbar no-print"><input className="input" placeholder={t("common.search")} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("common.search")} /></div>
      <div className="table-wrap"><table className="t"><thead><tr><th>{t("rep.he.building")}</th><th>{t("rep.plan")}</th><th className="num">{t("rep.he.users")}</th><th className="num">{t("rep.he.active")}</th><th>{t("rep.he.login")}</th><th>{t("rep.he.paid")}</th><th className="num">{t("rep.he.features")}</th><th className="num">{t("rep.he.adopted")}</th></tr></thead>
        <tbody>{d.rows.map((r: any) => <tr key={r.id}><td><Link href={`/app/saas/buildings/${r.id}`}><b>{r.name}</b></Link><div className="small muted">{r.city}</div></td><td>{keyLabel(t, r.plan)} {r.band} <Chip tone={r.status === "active" ? "ok" : r.status === "trial" ? "info" : r.status === "past_due" ? "warn" : "mute"}>{t(`sub.${r.status}`)}</Chip></td>
          <td className="num">{r.users}</td><td className="num">{r.active_users}</td><td className="nowrap">{r.last_login ? fdate(r.last_login) : t("rep.he.never")}</td><td className="nowrap">{r.last_paid ? fdate(r.last_paid) : t("rep.he.never")}</td><td className="num">{r.features_on}</td><td className="num">{r.adopted}</td></tr>)}
          {!d.rows.length && <tr><td colSpan={8}><Empty>{t("rep.none")}</Empty></td></tr>}</tbody></table></div>
      {d.total > d.size && <div className="pager no-print"><span className="small muted">{t("common.total")}: {d.total} · {t("common.page", { n: page, m: pages })}</span>
        <div className="row"><Btn variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t("common.prev")}</Btn><Btn variant="ghost" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>{t("common.next")}</Btn></div></div>}
    </div>
  );
}
