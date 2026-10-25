"use client";
import { useCallback, useEffect, useState } from "react";
import { Bar, Btn, Card, Chip, Empty, Field, Modal, PageHead, Tabs, useToast } from "@/components/ui";
import { api, fdate, ftime } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type N = { id: number; title: string; title_bn: string; body: string; body_bn: string; audience: string; priority: string; pinned: boolean; at: string; by: string; read: boolean; reach?: { total: number; read: number; app: number; link: number; no_phone: number } };
type Who = { id: number; name: string; unit: string; phone: string; via: string; read_at: string | null; sms_at: string | null; has_login: boolean };

export default function Notices() {
  const { t, pick } = useT(); const { prop, has } = useAuth(); const toast = useToast();
  const publish = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY"); const [rows, setRows] = useState<N[] | null>(null); const [open, setOpen] = useState<number | null>(null); const [form, setForm] = useState(false); const [who, setWho] = useState<N | null>(null);
  const load = useCallback(() => api<N[]>("/notices").then(setRows), []);
  useEffect(() => { load(); }, [load, prop?.id]);
  if (!rows) return <p className="muted">{t("common.loading")}</p>;
  const toggle = async (n: N) => { const next = open === n.id ? null : n.id; setOpen(next); if (next && !n.read) { await api(`/notices/${n.id}/read`, { method: "POST" }); load(); } };
  return (<>
    <PageHead helpKey="notices-read-proof" title={t("nt.title")} sub={t("nt.sub")} actions={publish && <Btn onClick={() => setForm(true)}>{t("nt.new")}</Btn>} />
    {rows.length === 0 && <Card><Empty>{t("nt.empty")}</Empty></Card>}
    <div className="stack">{rows.map((n) => (
      <Card key={n.id} style={{ borderColor: n.priority === "urgent" ? "var(--bad)" : undefined }}>
        <div className="row between wrap" style={{ cursor: "pointer", gap: 12 }} onClick={() => toggle(n)}>
          <div style={{ flex: 1, minWidth: 220 }}><div className="row wrap" style={{ gap: 8, marginBottom: 6 }}>{n.priority === "urgent" && <Chip tone="bad">{t("nt.urgent")}</Chip>}{n.pinned && <Chip tone="info">{t("nt.pinned")}</Chip>}<Chip tone="mute">{t(`nt.aud.${n.audience}`)}</Chip>{!n.read && !publish && <Chip tone="warn">{t("nt.new_badge")}</Chip>}</div>
            <h3 style={{ margin: 0 }}>{pick(n.title, n.title_bn || n.title)}</h3><span className="small muted">{fdate(n.at)} · {t("nt.by", { n: n.by })}</span></div>
          {n.reach && <div style={{ minWidth: 220 }}><div className="small" style={{ marginBottom: 6 }}><b>{t("nt.reach", { r: n.reach.read, t: n.reach.total })}</b></div><Bar pct={n.reach.total ? (100 * n.reach.read) / n.reach.total : 0} spark /><div className="small muted" style={{ marginTop: 4 }}>{t("nt.via", { a: n.reach.app, l: n.reach.link })}</div></div>}</div>
        {open === n.id && (<div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--line)" }}><p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{pick(n.body, n.body_bn || n.body)}</p>
          {n.reach && <div className="row wrap" style={{ marginTop: 14 }}><Btn size="sm" variant="soft" onClick={() => setWho(n)}>{t("nt.who")} · {n.reach.total - n.reach.read}</Btn>{publish && <><Btn size="sm" variant="ghost" onClick={async () => { await api(`/notices/${n.id}/pin`, { method: "POST" }); load(); }}>{n.pinned ? t("nt.unpin") : t("nt.pin")}</Btn><Btn size="sm" variant="ghost" onClick={async () => { await api(`/notices/${n.id}/archive`, { method: "POST" }); load(); }}>{t("nt.archive")}</Btn></>}</div>}</div>)}
      </Card>))}</div>
    {form && <NewNotice onClose={() => setForm(false)} onDone={(n) => { setForm(false); toast.show(t("nt.published", { n })); load(); }} />}
    {who && <Reach n={who} canSms={publish} onClose={() => setWho(null)} onDone={(m) => { toast.show(m); load(); }} />}
    {toast.node}
  </>);
}

function NewNotice({ onClose, onDone }: { onClose: () => void; onDone: (sms: number) => void }) {
  const { t } = useT(); const [lang, setLang] = useState<"en" | "bn">("en"); const [f, setF] = useState({ title: "", title_bn: "", body: "", body_bn: "", audience: "all", priority: "normal", sms: false }); const [err, setErr] = useState("");
  const go = async () => { try { const r = await api<{ sms_sent: number }>("/notices", { body: f }); onDone(r.sms_sent); } catch (e: any) { setErr(e.message); } };
  return <Modal title={t("nt.new")} onClose={onClose}>
    <div style={{ marginBottom: 12 }}><Tabs value={lang} onChange={setLang} items={[{ id: "en", label: t("nt.f.lang_en") }, { id: "bn", label: t("nt.f.lang_bn") }]} /></div>
    {lang === "en" ? <><Field label={t("nt.f.title")}><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field><Field label={t("nt.f.body")}><textarea className="input" rows={5} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></Field></>
      : <><Field label={t("nt.f.title")}><input className="input" value={f.title_bn} onChange={(e) => setF({ ...f, title_bn: e.target.value })} /></Field><Field label={t("nt.f.body")} hint={t("nt.f.bn_hint")}><textarea className="input" rows={5} value={f.body_bn} onChange={(e) => setF({ ...f, body_bn: e.target.value })} /></Field></>}
    <div className="grid g2"><Field label={t("nt.audience")}><select className="input" value={f.audience} onChange={(e) => setF({ ...f, audience: e.target.value })}>{["all", "owners", "tenants", "committee"].map((a) => <option key={a} value={a}>{t(`nt.aud.${a}`)}</option>)}</select></Field>
      <Field label={t("nt.priority")}><select className="input" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}><option value="normal">{t("nt.normal")}</option><option value="urgent">{t("nt.urgent")}</option></select></Field></div>
    <label className="row" style={{ marginBottom: 12 }}><input type="checkbox" checked={f.sms} onChange={(e) => setF({ ...f, sms: e.target.checked })} /> {t("nt.f.sms")}</label>
    {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn onClick={go} disabled={f.title.trim().length < 3 || f.body.trim().length < 3}>{t("nt.new")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}

function Reach({ n, canSms, onClose, onDone }: { n: N; canSms: boolean; onClose: () => void; onDone: (m: string) => void }) {
  const { t } = useT(); const [d, setD] = useState<{ read: Who[]; not_read: Who[] } | null>(null); const [tab, setTab] = useState<"not" | "read">("not");
  useEffect(() => { api(`/notices/${n.id}/reach`).then(setD); }, [n.id]);
  if (!d) return null;
  const rows = tab === "not" ? d.not_read : d.read;
  return <Modal title={pickTitle(n)} onClose={onClose}>
    <div className="row between wrap" style={{ marginBottom: 12 }}><Tabs value={tab} onChange={setTab} items={[{ id: "not", label: `${t("nt.not_read")} · ${d.not_read.length}` }, { id: "read", label: `${t("nt.read")} · ${d.read.length}` }]} />
      {canSms && tab === "not" && <Btn size="sm" onClick={async () => { const r = await api<{ sent: number }>(`/notices/${n.id}/nudge`, { method: "POST" }); onDone(t("nt.nudge_done", { n: r.sent })); onClose(); }}>{t("nt.nudge")}</Btn>}</div>
    <div style={{ maxHeight: 360, overflowY: "auto" }}>{rows.map((r) => (<div key={r.id} className="row between" style={{ padding: "8px 0", borderTop: "1px solid var(--line)", gap: 10 }}><div><b>{r.name}</b> {r.unit && <span className="muted small">· {r.unit}</span>}<br /><span className="small muted">{r.phone || "–"}</span></div>
      <div style={{ textAlign: "right" }}>{tab === "read" ? <><Chip tone="ok">{t(r.via === "app" ? "nt.via_app" : "nt.via_link")}</Chip><div className="small muted">{ftime(r.read_at)}</div></> : <>{r.sms_at ? <Chip tone="info">{t("nt.sms_sent")}</Chip> : !r.has_login ? <Chip tone="mute">{t("nt.no_login")}</Chip> : null}</>}</div></div>))}</div></Modal>;
  function pickTitle(x: N) { return x.title; }
}
