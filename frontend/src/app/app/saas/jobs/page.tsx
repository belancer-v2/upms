"use client";
import { useCallback, useEffect, useState } from "react";
import { Pager } from "@/components/pager";
import { Btn, Card, Chip, PageHead, useToast } from "@/components/ui";
import { api, ftime } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Run = { id: number; name: string; status: string; trigger: string; started_at: string; finished_at: string | null; result: Record<string, unknown>; error: string };
type Job = { name: string; title: string; schedule: string; last: Run | null; last_ok_at: string | null; failed_today: number };
type Alert = { id: number; kind: string; severity: string; message: string; created_at: string };
const TONE: Record<string, "ok" | "warn" | "bad" | "mute"> = { ok: "ok", warn: "warn", failed: "bad", running: "mute", skipped: "mute" };
const SIZE = 10;

export default function JobsPage() {
  const { t } = useT(); const toast = useToast();
  const [jobs, setJobs] = useState<Job[] | null>(null); const [busy, setBusy] = useState(""); const [filter, setFilter] = useState("");
  const [runs, setRuns] = useState<{ total: number; rows: Run[] }>({ total: 0, rows: [] }); const [page, setPage] = useState(1);
  const [alerts, setAlerts] = useState<{ total: number; rows: Alert[] }>({ total: 0, rows: [] });
  const load = useCallback(() => {
    api<{ jobs: Job[] }>("/saas/jobs").then((d) => setJobs(d.jobs));
    api(`/saas/jobs/runs?page=${page}&size=${SIZE}${filter ? `&name=${filter}` : ""}`).then(setRuns);
    api("/saas/jobs/alerts?size=5").then(setAlerts);
  }, [page, filter]);
  useEffect(load, [load]);
  const run = async (name: string) => {
    setBusy(name);
    try { const r = await api<{ status: string }>(`/saas/jobs/${name}/run`, { method: "POST", body: {} }); toast.show(t("jobs.ran", { s: t(`jobs.s.${r.status}`) })); }
    catch (e: any) { toast.show(e.message); } finally { setBusy(""); load(); }
  };
  const resolve = async (id: number) => { await api(`/saas/jobs/alerts/${id}/resolve`, { method: "POST", body: {} }); load(); };
  const short = (r: Record<string, unknown>) => Object.entries(r || {}).filter(([, v]) => typeof v !== "object").slice(0, 4).map(([k, v]) => `${k}: ${v}`).join(" · ");
  if (!jobs) return <p className="muted">{t("common.loading")}</p>;
  return (<>
    <PageHead title={t("jobs.title")} sub={t("jobs.sub")} />
    {alerts.total > 0 && <Card><h3>{t("jobs.alerts")} · {t("jobs.open_alerts", { n: alerts.total })}</h3><div className="stack" style={{ marginTop: 8 }}>
      {alerts.rows.map((a) => <div key={a.id} className="row between wrap"><span><Chip tone={a.severity === "error" ? "bad" : "warn"}>{a.kind}</Chip> {a.message} <span className="small muted">{ftime(a.created_at)}</span></span>
        <Btn size="sm" variant="ghost" onClick={() => resolve(a.id)}>{t("jobs.resolve")}</Btn></div>)}</div></Card>}
    <Card><div style={{ overflowX: "auto" }}><table className="table"><thead><tr><th>{t("jobs.name")}</th><th>{t("jobs.schedule")}</th><th>{t("jobs.last")}</th><th>{t("jobs.status")}</th><th>{t("jobs.result")}</th><th /></tr></thead><tbody>
      {jobs.map((j) => <tr key={j.name}>
        <td><b>{j.name}</b><div className="small muted">{j.title}</div></td><td className="small">{j.schedule}</td>
        <td className="small">{j.last ? ftime(j.last.started_at) : t("jobs.never")}</td>
        <td>{j.last && <Chip tone={TONE[j.last.status] ?? "mute"}>{t(`jobs.s.${j.last.status}`)}</Chip>}{j.failed_today > 0 && <div className="small" style={{ color: "var(--bad)" }}>{t("jobs.failed_today", { n: j.failed_today })}</div>}</td>
        <td className="small">{j.last?.error ? <span style={{ color: "var(--bad)" }}>{j.last.error.split("\n")[0]}</span> : short(j.last?.result ?? {})}</td>
        <td><Btn size="sm" variant="soft" disabled={busy === j.name} onClick={() => run(j.name)}>{busy === j.name ? t("jobs.running") : t("jobs.run")}</Btn></td></tr>)}
    </tbody></table></div></Card>
    <Card><div className="row between wrap"><h3>{t("jobs.history")}</h3>
      <select className="input" style={{ maxWidth: 240 }} value={filter} onChange={(e) => { setFilter(e.target.value); setPage(1); }} aria-label={t("jobs.name")}>
        <option value="">{t("jobs.all")}</option>{jobs.map((j) => <option key={j.name} value={j.name}>{j.name}</option>)}</select></div>
      <div style={{ overflowX: "auto" }}><table className="table"><thead><tr><th>{t("jobs.name")}</th><th>{t("jobs.started")}</th><th>{t("jobs.status")}</th><th>{t("jobs.result")}</th></tr></thead><tbody>
        {runs.rows.map((r) => <tr key={r.id}><td>{r.name}<div className="small muted">{t(`jobs.trigger.${r.trigger}`)}</div></td><td className="small">{ftime(r.started_at)}</td>
          <td><Chip tone={TONE[r.status] ?? "mute"}>{t(`jobs.s.${r.status}`)}</Chip></td>
          <td className="small">{r.error ? <details><summary style={{ color: "var(--bad)" }}>{t("jobs.error")}</summary><pre style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>{r.error}</pre></details> : short(r.result)}</td></tr>)}
      </tbody></table></div>
      <Pager page={page} size={SIZE} total={runs.total} onPage={setPage} /></Card>
    {toast.node}
  </>);
}
