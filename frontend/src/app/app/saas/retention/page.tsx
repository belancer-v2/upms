"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, DataTable, Field, PageHead, useToast } from "@/components/ui";
import { api, fdate, ftime } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type Counts = Record<string, number>;
type Ret = { settings: { visitor_months: number; outbox_months: number; former_months: number }; preview: { visitors: Counts; outbox: Counts; former_residents: Counts }; last_run: { at: string } | null; min_months: number; max_months: number };
type Req = { id: number; user_id: number; name: string; email: string; reason: string; status: string; requested_at: string; note: string; blockers: string[] };

export default function Retention() {
  const { t } = useT(); const { saas } = useAuth(); const toast = useToast(); const can = saas("SUPER_ADMIN", "SAAS_ADMIN");
  const [r, setR] = useState<Ret | null>(null); const [f, setF] = useState({ visitor_months: "24", outbox_months: "12", former_months: "36" }); const [reqs, setReqs] = useState<Req[]>([]); const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const d = await api<Ret>("/saas/retention"); setR(d);
    setF({ visitor_months: String(d.settings.visitor_months), outbox_months: String(d.settings.outbox_months), former_months: String(d.settings.former_months) });
    setReqs(await api<Req[]>("/saas/deletions?status=all").catch(() => []));
  }, []);
  useEffect(() => { load().catch((e) => toast.show(e.message)); }, [load]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!r) return <p className="muted">{t("common.loading")}</p>;
  const act = async (fn: () => Promise<unknown>, ok: string) => { setBusy(true); try { await fn(); toast.show(ok); await load(); } catch (e: any) { toast.show(e.message); } finally { setBusy(false); } };
  const save = () => act(() => api("/saas/retention", { method: "PUT", body: { visitor_months: Number(f.visitor_months), outbox_months: Number(f.outbox_months), former_months: Number(f.former_months) } }), t("dx.ret.saved"));
  const run = () => { if (confirm(t("dx.ret.confirm"))) act(() => api("/saas/retention/run", { body: { dry_run: false } }), t("dx.ret.ran")); };
  const total = Object.values(r.preview).flatMap((c) => Object.values(c)).reduce((a, b) => a + b, 0);
  const num = (k: keyof typeof f, label: string) => <Field label={label} hint={t("dx.ret.hint")}><input className="input" type="number" min={0} max={r.max_months} disabled={!can} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>;
  const sections: [string, string, Counts][] = [["v", "visitors", r.preview.visitors], ["o", "outbox", r.preview.outbox], ["f", "former_residents", r.preview.former_residents]];
  return (
    <>
      <PageHead helpKey="saas-retention" title={t("dx.ret.title")} sub={t("dx.ret.sub")} />
      <div className="grid g2" style={{ alignItems: "start" }}>
        <Card>
          <div className="stack">{num("visitor_months", t("dx.ret.visitor"))}{num("outbox_months", t("dx.ret.outbox"))}{num("former_months", t("dx.ret.former"))}
            <div className="row between wrap"><span><b>{t("dx.ret.audit")}</b></span><Chip tone="ok">{t("dx.ret.audit_val")}</Chip></div>
            {can ? <Btn onClick={save} disabled={busy}>{t("dx.ret.save")}</Btn> : <p className="small muted">{t("dx.ret.readonly")}</p>}</div>
        </Card>
        <Card>
          <h3>{t("dx.ret.due")}</h3>
          {total === 0 ? <p className="muted">{t("dx.ret.nothing")}</p> : <ul className="list-dot" style={{ marginTop: 10 }}>{sections.flatMap(([p, , c]) => Object.entries(c).filter(([, n]) => n > 0).map(([k, n]) => <li key={p + k}><span>{t(`dx.ret.${p}.${k}`)}: <b>{n}</b></span></li>))}</ul>}
          <p className="small muted" style={{ marginTop: 10 }}>{r.last_run ? t("dx.ret.last", { d: ftime(r.last_run.at) }) : t("dx.ret.never")}</p>
          {can && <div className="row wrap" style={{ marginTop: 10 }}><Btn variant="outline" onClick={load} disabled={busy}>{t("dx.ret.preview")}</Btn><Btn variant="danger" onClick={run} disabled={busy || total === 0}>{t("dx.ret.run")}</Btn></div>}
          <p className="small muted" style={{ marginTop: 12 }}>{t("dx.ret.sched")}</p>
        </Card>
      </div>
      <Card style={{ marginTop: 18 }}>
        <h3>{t("dx.req.title")}</h3><p className="muted small" style={{ marginTop: 6 }}>{t("dx.req.sub")}</p>
        <DataTable rows={reqs} pageSize={8} search={(x) => `${x.name} ${x.email}`} cols={[
          { key: "who", head: t("dx.req.col.who"), render: (x) => <span><b>{x.name}</b><br /><span className="small muted">{x.email}</span></span> },
          { key: "when", head: t("dx.req.col.when"), render: (x) => <span className="nowrap">{fdate(x.requested_at)}</span> },
          { key: "reason", head: t("dx.req.col.reason"), render: (x) => x.reason || "–" },
          { key: "st", head: t("dx.req.col.status"), render: (x) => <Chip tone={x.status === "pending" ? "warn" : x.status === "completed" ? "ok" : "mute"}>{t(`dx.del.st.${x.status}`)}</Chip> },
          { key: "act", head: "", render: (x) => x.status !== "pending" || !can ? null : x.blockers.length ? <Chip tone="bad">{t("dx.req.blocked", { b: x.blockers.map((b) => t(`dx.del.b.${b}`)).join(" ") })}</Chip> : (
            <span className="row" style={{ gap: 6 }}>
              <Btn size="sm" variant="danger" disabled={busy} onClick={() => confirm(t("dx.req.confirm", { n: x.name })) && act(() => api(`/saas/deletions/${x.id}/process`, { method: "POST", body: undefined }), t("dx.req.done"))}>{t("dx.req.erase")}</Btn>
              <Btn size="sm" variant="ghost" disabled={busy} onClick={() => { const note = prompt(t("dx.req.reason")); if (note && note.trim().length >= 3) act(() => api(`/saas/deletions/${x.id}/reject`, { body: { note } }), t("dx.req.refused")); }}>{t("dx.req.refuse")}</Btn></span>) }]} />
      </Card>
      {toast.node}
    </>
  );
}
