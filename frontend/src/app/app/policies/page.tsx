"use client";
import { useCallback, useEffect, useState } from "react";
import { Bar, Btn, Card, Chip, Empty, Field, Modal, PageHead, Tabs, useToast } from "@/components/ui";
import { api, fdate, ftime } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type P = { id: number; title: string; title_bn: string; version: number; body: string; body_bn: string; change_note: string; published_at: string; accepted: boolean; accepted_before: boolean; accepted_count?: number; audience_count?: number };
type H = { versions: { version: number; change_note: string; published_at: string; by: string; accepted_count: number; accepted?: { name: string; at: string }[] }[]; pending: string[] };

export default function Policies() {
  const { t, pick } = useT(); const { prop, has } = useAuth(); const toast = useToast();
  const manage = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY"); const [rows, setRows] = useState<P[] | null>(null); const [form, setForm] = useState<{ p?: P } | null>(null); const [hist, setHist] = useState<P | null>(null);
  const load = useCallback(() => api<P[]>("/policies").then(setRows), []);
  useEffect(() => { load(); }, [load, prop?.id]);
  if (!rows) return <p className="muted">{t("common.loading")}</p>;
  return (<>
    <PageHead title={t("pl.title")} sub={t("pl.sub")} actions={manage && <Btn onClick={() => setForm({})}>{t("pl.new")}</Btn>} />
    {rows.length === 0 && <Card><Empty>{t("pl.empty")}</Empty></Card>}
    <div className="stack">{rows.map((p) => (<Card key={p.id}>
      <div className="row between wrap"><div><h3 style={{ margin: 0 }}>{pick(p.title, p.title_bn || p.title)}</h3><span className="small muted">{t("pl.version", { n: p.version })} · {t("pl.published", { d: fdate(p.published_at) })}{p.change_note && ` · ${p.change_note}`}</span></div>
        {p.accepted ? <Chip tone="ok">{t("pl.accepted", { n: p.version })}</Chip> : p.accepted_before ? <Chip tone="warn">{t("pl.again")}</Chip> : null}</div>
      <p style={{ whiteSpace: "pre-wrap", margin: "14px 0" }}>{pick(p.body, p.body_bn || p.body)}</p>
      <div className="row between wrap" style={{ gap: 12 }}>
        {p.audience_count !== undefined && <div style={{ minWidth: 240 }}><div className="small"><b>{t("pl.accepted_n", { a: p.accepted_count ?? 0, n: p.audience_count })}</b></div><Bar pct={p.audience_count ? (100 * (p.accepted_count ?? 0)) / p.audience_count : 0} spark /></div>}
        <div className="row">{!p.accepted && <Btn onClick={async () => { try { await api(`/policies/${p.id}/accept`, { method: "POST" }); load(); } catch (e: any) { toast.show(e.message); } }}>{t("pl.accept")}</Btn>}
          {p.audience_count !== undefined && <Btn variant="soft" onClick={() => setHist(p)}>{t("pl.history")}</Btn>}{manage && <Btn variant="outline" onClick={() => setForm({ p })}>{t("pl.new_version")}</Btn>}</div></div></Card>))}</div>
    {form && <PolicyForm p={form.p} onClose={() => setForm(null)} onDone={() => { setForm(null); toast.show(t("pl.saved")); load(); }} />}
    {hist && <History p={hist} onClose={() => setHist(null)} />}
    {toast.node}
  </>);
}

function PolicyForm({ p, onClose, onDone }: { p?: P; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [lang, setLang] = useState<"en" | "bn">("en"); const [f, setF] = useState({ title: p?.title ?? "", title_bn: p?.title_bn ?? "", body: p?.body ?? "", body_bn: p?.body_bn ?? "", change_note: "" }); const [err, setErr] = useState("");
  const go = async () => { try { if (p) await api(`/policies/${p.id}/versions`, { body: { body: f.body, body_bn: f.body_bn, change_note: f.change_note } }); else await api("/policies", { body: f }); onDone(); } catch (e: any) { setErr(e.message); } };
  return <Modal title={p ? `${t("pl.new_version")} · ${p.title}` : t("pl.new")} onClose={onClose}>
    {p && <p className="hint">{t("pl.version_rule")}</p>}
    {!p && <Field label={t("pl.title_f")}><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>}
    <div style={{ marginBottom: 12 }}><Tabs value={lang} onChange={setLang} items={[{ id: "en", label: t("nt.f.lang_en") }, { id: "bn", label: t("nt.f.lang_bn") }]} /></div>
    {lang === "en" ? <Field label={t("pl.body")}><textarea className="input" rows={7} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></Field> : <Field label={t("pl.body")}><textarea className="input" rows={7} value={f.body_bn} onChange={(e) => setF({ ...f, body_bn: e.target.value })} /></Field>}
    {p && <Field label={t("pl.change")}><input className="input" value={f.change_note} onChange={(e) => setF({ ...f, change_note: e.target.value })} /></Field>}
    {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn onClick={go} disabled={f.body.trim().length < 10 || (!p && f.title.trim().length < 3)}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
function History({ p, onClose }: { p: P; onClose: () => void }) {
  const { t } = useT(); const [h, setH] = useState<H | null>(null);
  useEffect(() => { api<H>(`/policies/${p.id}/history`).then(setH); }, [p.id]);
  if (!h) return null;
  return <Modal title={`${p.title} · ${t("pl.history")}`} onClose={onClose}><div style={{ maxHeight: 420, overflowY: "auto" }}>
    {h.versions.map((v) => (<div key={v.version} style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}><div className="row between"><b>{t("pl.version", { n: v.version })}</b><span className="small muted">{fdate(v.published_at)} · {v.by}</span></div><div className="small muted">{v.change_note}</div>
      <div className="small" style={{ marginTop: 4 }}>{t("pl.accepted_by")}: {v.accepted_count}{v.accepted && v.accepted.length > 0 && <span className="muted"> · {v.accepted.map((a) => `${a.name} (${ftime(a.at)})`).slice(0, 4).join(", ")}</span>}</div></div>))}
    {h.pending.length > 0 && <div style={{ marginTop: 12 }}><b>{t("pl.pending")}</b><div className="small muted">{h.pending.join(", ")}</div></div>}</div></Modal>;
}
