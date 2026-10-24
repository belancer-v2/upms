"use client";
import { useCallback, useEffect, useState } from "react";
import { AudiencesTab, OutboxTab, SuppressionTab, TemplatesTab } from "@/components/mailtabs";
import { StatusChip, pct, usePaged } from "@/components/mailbits";
import { Pager } from "@/components/pager";
import { Bar, Btn, Card, Chip, DataTable, Empty, Field, Modal, PageHead, Stat, Tabs, useToast } from "@/components/ui";
import { api, fdate, ftime } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

const B = "/saas/mail";
type Stats = { id: number; name: string; status: string; recipients: number; queued: number; suppressed: number; skipped: number; sent: number; delivered: number; opened: number; clicked: number; bounced: number; unsubscribed: number;
  rates: { delivered: number; opened: number; clicked: number; bounced: number; unsubscribed: number }; top_links: { url: string; clicks: number }[] };
type Camp = { id: number; name: string; status: string; audience_id: number; audience: string; template_id: number; template: string; template_bn: string; kind: string; lang_rule: string; scheduled_at: string | null; throttle_per_hour: number; simulate: boolean; created_at: string; started_at: string | null; stats: Stats };
type Settings = { weekly_cap: number; throttle_per_hour: number; provider: string; company: string; address: string };
type Tab = "campaigns" | "templates" | "audiences" | "suppression" | "outbox";

export default function Mail() {
  const { t } = useT(); const { saas } = useAuth();
  const edit = saas("SUPER_ADMIN", "SAAS_ADMIN", "SAAS_SALES"); const admin = saas("SUPER_ADMIN", "SAAS_ADMIN");
  const [tab, setTab] = useState<Tab>("campaigns");
  const items: { id: Tab; label: string }[] = [{ id: "campaigns", label: t("mail.tab.campaigns") }, ...(edit ? [
    { id: "templates" as Tab, label: t("mail.tab.templates") }, { id: "audiences" as Tab, label: t("mail.tab.audiences") }, { id: "suppression" as Tab, label: t("mail.tab.suppression") }, { id: "outbox" as Tab, label: t("mail.tab.outbox") }] : [])];
  return (
    <>
      <PageHead title={t("mail.title")} sub={t("mail.sub")} />
      <div style={{ marginBottom: 18, overflowX: "auto" }}><Tabs value={tab} onChange={setTab} items={items} /></div>
      {tab === "campaigns" && <Campaigns edit={edit} admin={admin} />}
      {tab === "templates" && edit && <TemplatesTab />}
      {tab === "audiences" && edit && <AudiencesTab />}
      {tab === "suppression" && edit && <SuppressionTab admin={admin} />}
      {tab === "outbox" && edit && <OutboxTab />}
    </>
  );
}

function Campaigns({ edit, admin }: { edit: boolean; admin: boolean }) {
  const { t, pick } = useT(); const toast = useToast();
  const [rows, setRows] = useState<Camp[]>([]); const [cmp, setCmp] = useState<Stats[]>([]); const [open, setOpen] = useState<number | null>(null); const [add, setAdd] = useState(false);
  const [set, setSet] = useState<Settings | null>(null); const [setOpenSettings, setSettingsOpen] = useState(false);
  const load = useCallback(() => { api<Camp[]>(`${B}/campaigns`).then(setRows); api<Stats[]>(`${B}/stats/compare`).then(setCmp); api<Settings>(`${B}/settings`).then(setSet); }, []);
  useEffect(() => { load(); }, [load]);
  const runDue = async () => { const r = await api<{ ran: unknown[] }>(`${B}/run-due`, { method: "POST", body: {} }); toast.show(t("mail.camp.ran", { n: r.ran.length })); load(); };
  const sentRows = rows.filter((r) => r.stats.sent > 0);
  const tot = sentRows.reduce((a, r) => ({ sent: a.sent + r.stats.sent, delivered: a.delivered + r.stats.delivered, opened: a.opened + r.stats.opened, clicked: a.clicked + r.stats.clicked }), { sent: 0, delivered: 0, opened: 0, clicked: 0 });
  return (
    <>
      <div className="grid g4" style={{ marginBottom: 18 }}>
        <Stat label={t("mail.stat.sent")} value={tot.sent} note={t("mail.stat.camps", { n: sentRows.length })} />
        <Stat label={t("mail.stat.delivered")} value={tot.sent ? pct((100 * tot.delivered) / tot.sent) : "–"} />
        <Stat label={t("mail.stat.opened")} value={tot.delivered ? pct((100 * tot.opened) / tot.delivered) : "–"} />
        <Stat label={t("mail.stat.clicked")} value={tot.delivered ? pct((100 * tot.clicked) / tot.delivered) : "–"} />
      </div>
      <div className="row between wrap" style={{ marginBottom: 14 }}>
        <p className="muted small" style={{ margin: 0 }}>{edit ? t("mail.camp.sub") : t("mail.camp.readonly")}{set && <> · <Chip tone="mute">{t("mail.provider", { p: set.provider })}</Chip></>}</p>
        {edit && <div className="row wrap">{admin && <Btn variant="ghost" onClick={() => setSettingsOpen(true)}>{t("mail.set.title")}</Btn>}<Btn variant="soft" onClick={runDue}>{t("mail.camp.run_due")}</Btn><Btn onClick={() => setAdd(true)}>{t("mail.camp.new")}</Btn></div>}
      </div>
      <DataTable rows={rows} search={(r) => `${r.name} ${r.audience} ${r.template}`} onRow={(r) => setOpen(r.id)} cols={[
        { key: "name", head: t("common.name"), render: (r) => <div><b>{r.name}</b><div className="small muted">{r.audience} · {pick(r.template, r.template_bn)}</div></div> },
        { key: "status", head: t("common.status"), render: (r) => <div><StatusChip s={r.status} />{r.scheduled_at && r.status === "scheduled" && <div className="small muted">{ftime(r.scheduled_at)}</div>}</div> },
        { key: "sent", head: t("mail.stat.sent"), num: true, render: (r) => r.stats.sent },
        { key: "open", head: t("mail.stat.opened"), num: true, render: (r) => (r.stats.delivered ? pct(r.stats.rates.opened) : "–") },
        { key: "click", head: t("mail.stat.clicked"), num: true, render: (r) => (r.stats.delivered ? pct(r.stats.rates.clicked) : "–") },
        { key: "bounce", head: t("mail.stat.bounced"), num: true, render: (r) => (r.stats.sent ? pct(r.stats.rates.bounced) : "–") },
      ]} />
      {cmp.length > 1 && <Card style={{ marginTop: 20 }}>
        <h3 style={{ margin: "0 0 4px" }}>{t("mail.cmp.title")}</h3><p className="small muted">{t("mail.cmp.sub")}</p>
        <div className="col" style={{ gap: 14 }}>{cmp.map((c) => <div key={c.id}>
          <div className="row between"><b className="small">{c.name}</b><span className="small muted">{t("mail.stat.sent")} {c.sent}</span></div>
          {([["opened", c.rates.opened], ["clicked", c.rates.clicked], ["bounced", c.rates.bounced]] as const).map(([k, v]) => <div key={k} className="row" style={{ gap: 10, marginTop: 4 }}><span className="small muted" style={{ width: 70 }}>{t(`mail.stat.${k}`)}</span><div style={{ flex: 1 }}><Bar pct={v} /></div><span className="small" style={{ width: 52, textAlign: "right" }}>{pct(v)}</span></div>)}
        </div>)}</div></Card>}
      {open !== null && <CampaignModal id={open} edit={edit} onClose={() => setOpen(null)} onChange={load} />}
      {add && <NewCampaign onClose={() => setAdd(false)} onDone={() => { setAdd(false); load(); }} />}
      {setOpenSettings && set && <SettingsModal s={set} onClose={() => setSettingsOpen(false)} onDone={() => { setSettingsOpen(false); load(); }} />}
      {toast.node}
    </>
  );
}

function SettingsModal({ s, onClose, onDone }: { s: Settings; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const toast = useToast(); const [f, setF] = useState({ weekly_cap: s.weekly_cap, throttle_per_hour: s.throttle_per_hour });
  const save = async () => { try { await api(`${B}/settings`, { method: "PUT", body: f }); onDone(); } catch (e: any) { toast.show(e.message); } };
  return (
    <Modal title={t("mail.set.title")} onClose={onClose}>
      <Field label={t("mail.set.cap")} hint={t("mail.set.cap_hint")}><input className="input" type="number" min={1} max={14} value={f.weekly_cap} onChange={(e) => setF({ ...f, weekly_cap: Number(e.target.value) })} /></Field>
      <Field label={t("mail.set.throttle")} hint={t("mail.set.throttle_hint")}><input className="input" type="number" min={1} value={f.throttle_per_hour} onChange={(e) => setF({ ...f, throttle_per_hour: Number(e.target.value) })} /></Field>
      <p className="small muted">{s.company} · {s.address}</p>
      <div className="row"><Btn onClick={save}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div>{toast.node}
    </Modal>
  );
}

function NewCampaign({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t, pick } = useT(); const toast = useToast();
  const [auds, setAuds] = useState<{ id: number; name: string; count: number }[]>([]); const [tpls, setTpls] = useState<{ id: number; name: string; name_bn: string; kind: string }[]>([]);
  const [f, setF] = useState({ name: "", audience_id: 0, template_id: 0, lang_rule: "recipient", when: "now", at: "", throttle_per_hour: 0, simulate: true });
  useEffect(() => { api<any[]>(`${B}/audiences`).then(setAuds); api<any[]>(`${B}/templates`).then(setTpls); }, []);
  const save = async (sendNow: boolean) => {
    try {
      const c = await api<Camp>(`${B}/campaigns`, { body: { name: f.name, audience_id: f.audience_id, template_id: f.template_id, lang_rule: f.lang_rule, throttle_per_hour: f.throttle_per_hour, simulate: f.simulate, scheduled_at: f.when === "later" && f.at ? new Date(f.at).toISOString() : null } });
      if (sendNow) await api(`${B}/campaigns/${c.id}/send`, { method: "POST", body: {} });
      onDone();
    } catch (e: any) { toast.show(e.message); }
  };
  const ok = f.name.length >= 2 && f.audience_id && f.template_id && (f.when === "now" || f.at);
  return (
    <Modal title={t("mail.camp.new")} onClose={onClose}>
      <Field label={t("common.name")}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
      <Field label={t("mail.camp.audience")}><select className="input" value={f.audience_id} onChange={(e) => setF({ ...f, audience_id: Number(e.target.value) })}><option value={0}>—</option>{auds.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.count})</option>)}</select></Field>
      <Field label={t("mail.camp.template")}><select className="input" value={f.template_id} onChange={(e) => setF({ ...f, template_id: Number(e.target.value) })}><option value={0}>—</option>{tpls.map((x) => <option key={x.id} value={x.id}>{pick(x.name, x.name_bn)} · {t(`mail.kind.${x.kind}`)}</option>)}</select></Field>
      <Field label={t("mail.camp.lang")} hint={t("mail.camp.lang_hint")}><select className="input" value={f.lang_rule} onChange={(e) => setF({ ...f, lang_rule: e.target.value })}><option value="recipient">{t("mail.camp.lang.recipient")}</option><option value="bn">{t("mail.camp.lang.bn")}</option><option value="en">{t("mail.camp.lang.en")}</option></select></Field>
      <Field label={t("mail.camp.when")}><div className="row wrap"><select className="input" style={{ maxWidth: 180 }} value={f.when} onChange={(e) => setF({ ...f, when: e.target.value })}><option value="now">{t("mail.camp.now")}</option><option value="later">{t("mail.camp.later")}</option></select>
        {f.when === "later" && <input className="input" style={{ maxWidth: 240 }} type="datetime-local" value={f.at} onChange={(e) => setF({ ...f, at: e.target.value })} />}</div></Field>
      <Field label={t("mail.camp.throttle")} hint={t("mail.camp.throttle_hint")}><input className="input" type="number" min={0} value={f.throttle_per_hour} onChange={(e) => setF({ ...f, throttle_per_hour: Number(e.target.value) })} /></Field>
      <label className="row" style={{ gap: 8, marginBottom: 14 }}><input type="checkbox" checked={f.simulate} onChange={(e) => setF({ ...f, simulate: e.target.checked })} />{t("mail.camp.simulate")}</label>
      <div className="row wrap"><Btn disabled={!ok} onClick={() => save(f.when === "now")}>{f.when === "now" ? t("mail.camp.send") : t("mail.camp.schedule")}</Btn>{f.when === "now" && <Btn variant="soft" disabled={!ok} onClick={() => save(false)}>{t("mail.camp.draft")}</Btn>}<Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div>
      {toast.node}
    </Modal>
  );
}

function CampaignModal({ id, edit, onClose, onChange }: { id: number; edit: boolean; onClose: () => void; onChange: () => void }) {
  const { t, pick } = useT(); const toast = useToast();
  const [c, setC] = useState<Camp | null>(null); const [status, setStatus] = useState("");
  const load = useCallback(() => api<Camp>(`${B}/campaigns/${id}`).then(setC), [id]);
  useEffect(() => { load(); }, [load]);
  const p = usePaged<any>(`${B}/campaigns/${id}/results`, { status }, 8);
  const act = async (what: "send" | "cancel" | "test") => {
    try {
      const r = await api<any>(`${B}/campaigns/${id}/${what}`, { method: "POST", body: {} });
      if (what === "test") toast.show(t("mail.camp.tested", { e: r.to })); else { load(); p.reload(); onChange(); }
    } catch (e: any) { toast.show(e.message); }
  };
  if (!c) return null;
  const s = c.stats; const live = ["draft", "scheduled"].includes(c.status);
  return (
    <Modal title={c.name} onClose={onClose}>
      <div className="row wrap" style={{ marginBottom: 12 }}><StatusChip s={c.status} /><Chip tone="mute">{t(`mail.kind.${c.kind}`)}</Chip><span className="small muted">{c.audience} · {pick(c.template, c.template_bn)} · {t(`mail.camp.lang.${c.lang_rule}`)}</span></div>
      {c.scheduled_at && c.status === "scheduled" && <p className="small">{t("mail.camp.scheduled_for", { d: ftime(c.scheduled_at) })}</p>}
      {edit && <div className="row wrap" style={{ marginBottom: 14 }}>
        <Btn size="sm" variant="soft" onClick={() => act("test")}>{t("mail.camp.test")}</Btn>
        {live && <Btn size="sm" onClick={() => act("send")}>{t("mail.camp.send")}</Btn>}
        {(live || c.status === "sending") && <Btn size="sm" variant="danger" onClick={() => confirm(t("mail.camp.cancel_ask")) && act("cancel")}>{t("mail.camp.cancel")}</Btn>}</div>}
      <div className="grid g3" style={{ gap: 10, marginBottom: 14 }}>
        {([["sent", s.sent], ["delivered", s.delivered], ["opened", s.opened], ["clicked", s.clicked], ["bounced", s.bounced], ["unsubscribed", s.unsubscribed]] as const).map(([k, v]) => (
          <div key={k} className="card" style={{ padding: 12, boxShadow: "none" }}><div className="small muted">{t(`mail.stat.${k}`)}</div><b style={{ fontSize: 22 }}>{v}</b>
            {k !== "sent" && s.sent > 0 && <div className="small muted">{pct(s.rates[k])}</div>}</div>))}
      </div>
      <p className="small muted">{t("mail.camp.held", { a: s.suppressed, b: s.skipped, c: s.queued })}</p>
      {s.top_links.length > 0 && <><h3 style={{ margin: "14px 0 6px", fontSize: 16 }}>{t("mail.camp.top_links")}</h3><ul className="list-dot">{s.top_links.map((l) => <li key={l.url}><span className="small" style={{ wordBreak: "break-all" }}>{l.url} <b>· {l.clicks}</b></span></li>)}</ul></>}
      <h3 style={{ margin: "14px 0 6px", fontSize: 16 }}>{t("mail.camp.results")}</h3>
      <div className="toolbar"><input className="input" placeholder={t("common.search")} value={p.q} onChange={(e) => p.setQ(e.target.value)} aria-label={t("common.search")} />
        <select className="input" style={{ maxWidth: 170 }} value={status} onChange={(e) => setStatus(e.target.value)} aria-label={t("common.status")}><option value="">{t("mail.out.all")}</option>{["sent", "bounced", "suppressed", "skipped", "queued"].map((x) => <option key={x} value={x}>{t(`mail.st.${x}`)}</option>)}</select></div>
      <div className="table-wrap"><table className="t"><thead><tr><th>{t("auth.email")}</th><th>{t("common.status")}</th><th>{t("mail.out.engage")}</th></tr></thead>
        <tbody>{p.items.map((r: any) => <tr key={r.id}><td className="small">{r.to_email}</td><td><StatusChip s={r.status} />{r.reason && <span className="small muted"> {r.reason}</span>}</td>
          <td className="small">{r.clicked_at ? t("mail.ev.clicked") : r.opened_at ? t("mail.ev.opened") : r.delivered_at ? t("mail.ev.delivered") : "—"}</td></tr>)}
          {!p.items.length && <tr><td colSpan={3}><Empty /></td></tr>}</tbody></table></div>
      <Pager page={p.page} size={p.size} total={p.total} onPage={p.setPage} />
      <p className="small muted" style={{ marginTop: 8 }}>{c.started_at ? t("mail.camp.started", { d: fdate(c.started_at) }) : ""}</p>
      {toast.node}
    </Modal>
  );
}
