"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Btn, Card, Chip, DataTable, Empty, Field, Modal, Tabs, useToast } from "@/components/ui";
import { EmailFrame, StatusChip, usePaged, type Block } from "@/components/mailbits";
import { Pager } from "@/components/pager";
import { api, fdate, ftime } from "@/lib/api";
import { useT } from "@/lib/i18n";

const B = "/saas/mail";
type Tpl = { id: number; key: string; name: string; name_bn: string; kind: string; subject_en: string; subject_bn: string; updated_at: string };
type Aud = { id: number; name: string; kind: string; params: Record<string, any>; count: number; created_at: string };
const STAGES = ["new", "contacted", "demo", "trial", "won", "lost"];

const STARTER_EN: Block[] = [{ type: "heading", text: "Hello {{name}}" }, { type: "paragraph", text: "Write your message here." }, { type: "button", label: "Open FlatWise", url: "{{link}}" }, { type: "divider" }, { type: "footer", text: "The FlatWise team" }];
const STARTER_BN: Block[] = [{ type: "heading", text: "{{name}}, আসসালামু আলাইকুম" }, { type: "paragraph", text: "এখানে আপনার বার্তা লিখুন।" }, { type: "button", label: "ফ্ল্যাটওয়াইজ খুলুন", url: "{{link}}" }, { type: "divider" }, { type: "footer", text: "ফ্ল্যাটওয়াইজ টিম" }];

export function TemplatesTab() {
  const { t, pick } = useT(); const router = useRouter(); const toast = useToast();
  const [rows, setRows] = useState<Tpl[]>([]); const [add, setAdd] = useState(false); const [f, setF] = useState({ key: "", name: "", kind: "promotional" });
  useEffect(() => { api<Tpl[]>(`${B}/templates`).then(setRows); }, []);
  const create = async () => {
    try {
      const r = await api<Tpl>(`${B}/templates`, { body: { ...f, name_bn: f.name, subject_en: f.name, subject_bn: f.name, blocks_en: STARTER_EN, blocks_bn: STARTER_BN } });
      router.push(`/app/saas/mail/templates/${r.id}`);
    } catch (e: any) { toast.show(e.message); }
  };
  return (
    <>
      <div className="row between wrap" style={{ marginBottom: 14 }}><p className="muted small" style={{ margin: 0 }}>{t("mail.tpl.sub")}</p><Btn onClick={() => setAdd(true)}>{t("mail.tpl.new")}</Btn></div>
      <DataTable rows={rows} onRow={(r) => router.push(`/app/saas/mail/templates/${r.id}`)} search={(r) => `${r.name} ${r.name_bn} ${r.key}`} cols={[
        { key: "name", head: t("common.name"), render: (r) => <b>{pick(r.name, r.name_bn)}</b> },
        { key: "kind", head: t("mail.kind"), render: (r) => <Chip tone={r.kind === "transactional" ? "info" : ""}>{t(`mail.kind.${r.kind}`)}</Chip> },
        { key: "subject", head: t("mail.subject"), render: (r) => <span className="small">{pick(r.subject_en, r.subject_bn)}</span> },
        { key: "updated_at", head: t("mail.updated"), render: (r) => fdate(r.updated_at) },
      ]} />
      {add && <Modal title={t("mail.tpl.new")} onClose={() => setAdd(false)}>
        <Field label={t("common.name")}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label={t("mail.tpl.key")} hint={t("mail.tpl.key_hint")}><input className="input" value={f.key} onChange={(e) => setF({ ...f, key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} /></Field>
        <Field label={t("mail.kind")}><select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="promotional">{t("mail.kind.promotional")}</option><option value="transactional">{t("mail.kind.transactional")}</option></select></Field>
        <div className="row"><Btn onClick={create} disabled={!f.name || f.key.length < 2}>{t("common.add")}</Btn><Btn variant="ghost" onClick={() => setAdd(false)}>{t("common.cancel")}</Btn></div></Modal>}
      {toast.node}
    </>
  );
}

function Recipients({ aud, onClose }: { aud: Aud; onClose: () => void }) {
  const { t } = useT();
  const p = usePaged<{ email: string; name: string; building: string; city: string; lang: string; suppressed: string }>(`${B}/audiences/${aud.id}/recipients`, {}, 10);
  return (
    <Modal title={aud.name} onClose={onClose}>
      <div className="toolbar"><input className="input" placeholder={t("common.search")} value={p.q} onChange={(e) => p.setQ(e.target.value)} /></div>
      <div className="table-wrap"><table className="t"><thead><tr><th>{t("auth.email")}</th><th>{t("common.name")}</th><th>{t("mail.aud.building")}</th><th>{t("mail.aud.lang")}</th></tr></thead>
        <tbody>{p.items.map((r) => <tr key={r.email}><td>{r.email}{r.suppressed && <> <Chip tone="warn">{t("mail.st.suppressed")}</Chip></>}</td><td>{r.name}</td><td>{r.building}</td><td>{r.lang.toUpperCase()}</td></tr>)}
          {!p.items.length && <tr><td colSpan={4}><Empty /></td></tr>}</tbody></table></div>
      <Pager page={p.page} size={p.size} total={p.total} onPage={p.setPage} />
    </Modal>
  );
}

export function AudiencesTab() {
  const { t } = useT(); const toast = useToast();
  const [rows, setRows] = useState<Aud[]>([]); const [view, setView] = useState<Aud | null>(null);
  const [seg, setSeg] = useState(false); const [csv, setCsv] = useState(false);
  const [plans, setPlans] = useState<{ key: string; name: string }[]>([]);
  const [f, setF] = useState<{ name: string; kind: string; stages: string[]; plan: string; city: string; band: string }>({ name: "", kind: "stage", stages: ["new"], plan: "standard", city: "Dhaka", band: "S" });
  const [c, setC] = useState({ name: "", csv: "", consent_source: "" }); const [res, setRes] = useState<any>(null);
  const load = () => api<Aud[]>(`${B}/audiences`).then(setRows);
  useEffect(() => { load(); api<any>("/public/plans").then((d) => setPlans(d.plans)); }, []);
  const params = () => (f.kind === "stage" ? { stages: f.stages } : f.kind === "plan" ? { plan: f.plan } : f.kind === "city" ? { city: f.city } : f.kind === "band" ? { band: f.band } : {});
  const create = async () => { try { await api(`${B}/audiences`, { body: { name: f.name, kind: f.kind, params: params() } }); setSeg(false); load(); } catch (e: any) { toast.show(e.message); } };
  const upload = async () => { try { setRes(await api(`${B}/audiences/csv`, { body: c })); load(); } catch (e: any) { toast.show(e.message); } };
  const readFile = (file?: File) => { if (file) file.text().then((x) => setC((o) => ({ ...o, csv: x }))); };
  const del = async (a: Aud) => { try { await api(`${B}/audiences/${a.id}`, { method: "DELETE" }); load(); } catch (e: any) { toast.show(e.message); } };
  const label = (a: Aud) => (a.kind === "stage" ? (a.params.stages ?? []).map((s: string) => t(`lead.${s}`)).join(", ") : a.kind === "plan" ? a.params.plan : a.kind === "city" ? a.params.city : a.kind === "band" ? a.params.band : "");
  return (
    <>
      <div className="row between wrap" style={{ marginBottom: 14 }}><p className="muted small" style={{ margin: 0 }}>{t("mail.aud.sub")}</p>
        <div className="row"><Btn variant="soft" onClick={() => { setRes(null); setC({ name: "", csv: "", consent_source: "" }); setCsv(true); }}>{t("mail.aud.csv")}</Btn><Btn onClick={() => setSeg(true)}>{t("mail.aud.new")}</Btn></div></div>
      <DataTable rows={rows} search={(r) => r.name} cols={[
        { key: "name", head: t("common.name"), render: (r) => <b>{r.name}</b> },
        { key: "kind", head: t("mail.aud.type"), render: (r) => <span><Chip>{t(`mail.aud.k.${r.kind}`)}</Chip> <span className="small muted">{label(r)}</span></span> },
        { key: "count", head: t("mail.aud.people"), num: true },
        { key: "act", head: "", render: (r) => <div className="row"><Btn size="sm" variant="ghost" onClick={() => setView(r)}>{t("mail.aud.view")}</Btn><Btn size="sm" variant="ghost" onClick={() => del(r)}>{t("common.delete")}</Btn></div> },
      ]} />
      {view && <Recipients aud={view} onClose={() => setView(null)} />}
      {seg && <Modal title={t("mail.aud.new")} onClose={() => setSeg(false)}>
        <Field label={t("common.name")}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label={t("mail.aud.type")}><select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>{["stage", "trial", "active", "churned", "plan", "city", "band"].map((k) => <option key={k} value={k}>{t(`mail.aud.k.${k}`)}</option>)}</select></Field>
        {f.kind === "stage" && <Field label={t("mail.aud.stages")}><div className="row wrap">{STAGES.map((s) => <label key={s} className="row" style={{ gap: 6 }}><input type="checkbox" checked={f.stages.includes(s)} onChange={(e) => setF({ ...f, stages: e.target.checked ? [...f.stages, s] : f.stages.filter((x) => x !== s) })} />{t(`lead.${s}`)}</label>)}</div></Field>}
        {f.kind === "plan" && <Field label={t("saas.b.plan")}><select className="input" value={f.plan} onChange={(e) => setF({ ...f, plan: e.target.value })}>{plans.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}</select></Field>}
        {f.kind === "city" && <Field label={t("saas.b.city")}><input className="input" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} /></Field>}
        {f.kind === "band" && <Field label={t("saas.d.band")}><select className="input" value={f.band} onChange={(e) => setF({ ...f, band: e.target.value })}>{["S", "M", "L", "XL"].map((b) => <option key={b} value={b}>{b}</option>)}</select></Field>}
        <div className="row"><Btn onClick={create} disabled={f.name.length < 2}>{t("common.save")}</Btn><Btn variant="ghost" onClick={() => setSeg(false)}>{t("common.cancel")}</Btn></div></Modal>}
      {csv && <Modal title={t("mail.aud.csv")} onClose={() => setCsv(false)}>
        {!res ? <>
          <p className="small muted">{t("mail.csv.help")}</p>
          <Field label={t("common.name")}><input className="input" value={c.name} onChange={(e) => setC({ ...c, name: e.target.value })} /></Field>
          <Field label={t("mail.csv.consent")} hint={t("mail.csv.consent_hint")}><input className="input" value={c.consent_source} onChange={(e) => setC({ ...c, consent_source: e.target.value })} /></Field>
          <Field label={t("mail.csv.file")}><input type="file" accept=".csv,text/csv,text/plain" onChange={(e) => readFile(e.target.files?.[0])} /></Field>
          <Field label={t("mail.csv.paste")}><textarea className="input" rows={6} value={c.csv} placeholder={"email,name,company,city\nrahim@example.bd,Rahim,Sunrise Tower,Dhaka"} onChange={(e) => setC({ ...c, csv: e.target.value })} /></Field>
          <div className="row"><Btn onClick={upload} disabled={c.name.length < 2 || !c.csv.trim() || !c.consent_source.trim()}>{t("mail.csv.import")}</Btn><Btn variant="ghost" onClick={() => setCsv(false)}>{t("common.cancel")}</Btn></div>
        </> : <>
          <dl className="kv"><dt>{t("mail.csv.rows")}</dt><dd>{res.total}</dd><dt>{t("mail.csv.accepted")}</dt><dd><b>{res.accepted}</b></dd><dt>{t("mail.csv.dupes")}</dt><dd>{res.duplicates}</dd><dt>{t("mail.csv.invalid")}</dt><dd>{res.invalid_count}</dd></dl>
          {res.invalid.length > 0 && <ul className="list-dot" style={{ marginTop: 12 }}>{res.invalid.slice(0, 10).map((r: any) => <li key={r.row}><span className="small">{t("mail.csv.row", { n: r.row })}: {r.email || "—"}</span></li>)}</ul>}
          <div className="row" style={{ marginTop: 14 }}><Btn onClick={() => setCsv(false)}>{t("common.close")}</Btn></div></>}
      </Modal>}
      {toast.node}
    </>
  );
}

type Sup = { id: number; email: string; reason: string; source: string; created_at: string };
export function SuppressionTab({ admin }: { admin: boolean }) {
  const { t } = useT(); const toast = useToast();
  const p = usePaged<Sup>(`${B}/suppression`, {}, 10); const [email, setEmail] = useState("");
  const add = async () => { try { await api(`${B}/suppression`, { body: { email, reason: "manual" } }); setEmail(""); p.reload(); } catch (e: any) { toast.show(e.message); } };
  const del = async (s: Sup) => { if (!confirm(t("mail.sup.confirm", { e: s.email }))) return; await api(`${B}/suppression/${s.id}`, { method: "DELETE" }); p.reload(); };
  return (
    <>
      <p className="muted small">{t("mail.sup.sub")}</p>
      <div className="toolbar"><input className="input" placeholder={t("common.search")} value={p.q} onChange={(e) => p.setQ(e.target.value)} aria-label={t("common.search")} />
        <input className="input" type="email" placeholder={t("auth.email")} value={email} onChange={(e) => setEmail(e.target.value)} /><Btn onClick={add} disabled={email.length < 5}>{t("mail.sup.add")}</Btn></div>
      <div className="table-wrap"><table className="t"><thead><tr><th>{t("auth.email")}</th><th>{t("mail.sup.reason")}</th><th>{t("mail.sup.source")}</th><th>{t("mail.updated")}</th><th /></tr></thead>
        <tbody>{p.items.map((s) => <tr key={s.id}><td>{s.email}</td><td><Chip tone={s.reason === "bounce" || s.reason === "complaint" ? "bad" : s.reason === "manual" ? "warn" : "mute"}>{t(`mail.sup.r.${s.reason}`)}</Chip></td><td className="small">{s.source}</td><td>{fdate(s.created_at)}</td>
          <td>{admin && <Btn size="sm" variant="ghost" onClick={() => del(s)}>{t("mail.sup.remove")}</Btn>}</td></tr>)}
          {!p.items.length && <tr><td colSpan={5}><Empty /></td></tr>}</tbody></table></div>
      <Pager page={p.page} size={p.size} total={p.total} onPage={p.setPage} />
      {toast.node}
    </>
  );
}

type Row = { id: number; campaign_id: number | null; template: string; kind: string; to_email: string; to_name: string; lang: string; subject: string; status: string; reason: string; is_test: boolean; sent_at: string | null; opened_at: string | null; clicked_at: string | null; bounced_at: string | null; unsubscribed_at: string | null; clicks: string[]; created_at: string };

export function EmailModal({ id, onClose }: { id: number; onClose: () => void }) {
  const { t } = useT(); const [d, setD] = useState<(Row & { html: string; text: string }) | null>(null); const [tab, setTab] = useState<"html" | "text">("html");
  useEffect(() => { api(`${B}/outbox/${id}`).then(setD); }, [id]);
  return (
    <Modal title={d?.subject ?? "…"} onClose={onClose}>
      {d && <>
        <dl className="kv" style={{ marginBottom: 12 }}><dt>{t("auth.email")}</dt><dd>{d.to_email}</dd><dt>{t("common.status")}</dt><dd><StatusChip s={d.status} />{d.reason && <span className="small muted"> · {d.reason}</span>}</dd>
          <dt>{t("mail.out.events")}</dt><dd className="small">{[d.sent_at && `${t("mail.ev.sent")} ${ftime(d.sent_at)}`, d.opened_at && `${t("mail.ev.opened")} ${ftime(d.opened_at)}`, d.clicked_at && `${t("mail.ev.clicked")} ${ftime(d.clicked_at)}`, d.bounced_at && t("mail.ev.bounced"), d.unsubscribed_at && t("mail.ev.unsubscribed")].filter(Boolean).join(" · ") || "—"}</dd></dl>
        <Tabs value={tab} onChange={setTab} items={[{ id: "html", label: t("mail.ed.html") }, { id: "text", label: t("mail.ed.text") }]} />
        <div style={{ marginTop: 12 }}>{tab === "html" ? <EmailFrame html={d.html} height={420} /> : <pre style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{d.text}</pre>}</div></>}
    </Modal>
  );
}

export function OutboxTab() {
  const { t } = useT(); const [status, setStatus] = useState(""); const [open, setOpen] = useState<number | null>(null);
  const p = usePaged<Row>(`${B}/outbox`, { status }, 10);
  return (
    <>
      <p className="muted small">{t("mail.out.sub")}</p>
      <div className="toolbar"><input className="input" placeholder={t("common.search")} value={p.q} onChange={(e) => p.setQ(e.target.value)} aria-label={t("common.search")} />
        <select className="input" style={{ maxWidth: 200 }} value={status} onChange={(e) => setStatus(e.target.value)} aria-label={t("common.status")}><option value="">{t("mail.out.all")}</option>{["sent", "bounced", "suppressed", "skipped", "queued", "failed"].map((s) => <option key={s} value={s}>{t(`mail.st.${s}`)}</option>)}</select></div>
      <div className="table-wrap"><table className="t"><thead><tr><th>{t("auth.email")}</th><th>{t("mail.subject")}</th><th>{t("common.status")}</th><th>{t("mail.out.engage")}</th><th>{t("mail.ev.sent")}</th></tr></thead>
        <tbody>{p.items.map((r) => <tr key={r.id} style={{ cursor: "pointer" }} onClick={() => setOpen(r.id)}><td>{r.to_email}{r.is_test && <> <Chip tone="info">{t("mail.out.test")}</Chip></>}</td><td className="small">{r.subject || "—"}</td><td><StatusChip s={r.status} /></td>
          <td className="small">{r.clicked_at ? t("mail.ev.clicked") : r.opened_at ? t("mail.ev.opened") : r.unsubscribed_at ? t("mail.ev.unsubscribed") : "—"}</td><td className="small">{ftime(r.sent_at ?? r.created_at)}</td></tr>)}
          {!p.items.length && <tr><td colSpan={5}><Empty /></td></tr>}</tbody></table></div>
      <Pager page={p.page} size={p.size} total={p.total} onPage={p.setPage} />
      {open !== null && <EmailModal id={open} onClose={() => setOpen(null)} />}
    </>
  );
}
