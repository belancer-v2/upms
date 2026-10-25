"use client";
import { useCallback, useEffect, useState } from "react";
import { Bar, Btn, Card, Chip, DataTable, Empty, Field, Modal, PageHead, Stat, useToast } from "@/components/ui";
import { api, ftime, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { periodLabel } from "@/lib/act";
import { useT } from "@/lib/i18n";

type Entry = { id: number; unit: string; amount: number; status: string; mode: string; collector: string; at: string; locked: boolean; expired: boolean; tries_left: number };
type Cust = { limit: number; rows: { collector_id: number; name: string; held: number; handover: number; pending: number; limit: number }[] };
type Rem = { id: number; collector: string; amount: number; status: string; at: string; entries: number };
type OpenInv = { id: number; unit: string; period: string; balance: number; overdue: boolean };
const tone = (s: string) => (s === "held" || s === "accepted" || s === "remitted" ? "ok" : s === "cancelled" || s === "rejected" ? "bad" : "warn") as "ok" | "bad" | "warn";

export default function Cash() {
  const { t } = useT(); const { prop, has, feature } = useAuth(); const toast = useToast();
  const collector = has("CARETAKER", "PROPERTY_ADMIN", "AGENCY_MANAGER"); const decider = has("TREASURER", "PROPERTY_ADMIN", "AGENCY_MANAGER");
  const [cust, setCust] = useState<Cust | null>(null); const [ents, setEnts] = useState<Entry[]>([]); const [rems, setRems] = useState<Rem[]>([]); const [open, setOpen] = useState<OpenInv[]>([]);
  const [code, setCode] = useState<Entry | null>(null); const [inv, setInv] = useState(""); const [amt, setAmt] = useState(""); const [err, setErr] = useState(""); const [demo, setDemo] = useState("");
  const otp = feature("cash_otp");
  const load = useCallback(async () => {
    setCust(await api("/cash/custody")); setEnts(await api("/cash/entries")); setRems(await api("/cash/remittances"));
    if (collector) setOpen(await api("/cash/open-invoices"));
  }, [collector]);
  useEffect(() => { load(); }, [load, prop?.id]);
  if (!cust) return <p className="muted">{t("common.loading")}</p>;
  const mine = cust.rows[0];
  const pick = (id: string) => { setInv(id); const x = open.find((o) => String(o.id) === id); setAmt(x ? String(x.balance / 100) : ""); };
  const take = async () => { setErr(""); setDemo(""); try { const r = await api("/cash/entries", { body: { invoice_id: +inv, amount: Math.round(+amt * 100) } }); setInv(""); setAmt(""); toast.show(r.mode === "otp" ? t("cash.sent_code") : t("cash.link_note")); if (r.demo_code) setDemo(r.demo_code); load(); } catch (e: any) { setErr(e.message); } };
  const act = async (path: string, ok?: string) => { try { await api(path, { method: "POST" }); if (ok) toast.show(ok); load(); } catch (e: any) { toast.show(e.message); } };

  return (<>
    <PageHead helpKey="cash-desk" title={t("cash.title")} sub={t("cash.sub")} actions={collector && mine && mine.held > 0 ? <Btn onClick={() => act("/cash/remittances", t("cash.hand_done"))}>{t("cash.hand")}</Btn> : undefined} />
    <div className="grid g3" style={{ marginBottom: 16 }}>{cust.rows.length === 0 && <Card><Empty /></Card>}
      {cust.rows.map((r) => (<Card key={r.collector_id}><div className="row between"><h3 style={{ margin: 0 }}>{r.name}</h3><span className="small muted">{t("cash.limit", { a: money(r.limit) })}</span></div>
        <div style={{ fontSize: 28, fontWeight: 800, margin: "8px 0" }}>{money(r.held + r.pending)}</div><Bar pct={((r.held + r.pending) / r.limit) * 100} spark />
        <div className="small muted" style={{ marginTop: 10 }}>{t("cash.held")}: <b>{money(r.held)}</b> · {t("cash.pending")}: <b>{money(r.pending)}</b> · {t("cash.handover")}: <b>{money(r.handover)}</b></div></Card>))}</div>

    {collector && (<Card style={{ marginBottom: 16 }}><h3>{t("cash.collect")}</h3>
      <div className="grid g3" style={{ marginTop: 10, alignItems: "end" }}>
        <Field label={t("cash.flat")}><select className="input" value={inv} onChange={(e) => pick(e.target.value)}><option value="">{t("cash.pick")}</option>{open.map((o) => <option key={o.id} value={o.id}>{o.unit} · {periodLabel(t, o.period)} · {money(o.balance)}</option>)}</select></Field>
        <Field label={t("cash.amount")}><input className="input" inputMode="decimal" value={amt} onChange={(e) => setAmt(e.target.value)} /></Field>
        <div style={{ marginBottom: 14 }}><Btn onClick={take} disabled={!inv || !(+amt > 0)}>{otp ? t("cash.take") : t("cash.take_link")}</Btn></div></div>
      {!otp && <p className="hint">{t("cash.link_note")}</p>}{demo && <p className="hint"><Chip tone="info">{t("cash.demo_code", { c: demo })}</Chip></p>}{err && <p className="error" role="alert">{err}</p>}</Card>)}

    <h3 style={{ margin: "20px 0 10px" }}>{t("cash.entries")}</h3>
    <DataTable rows={ents} pageSize={8} search={(r) => `${r.unit} ${r.collector}`} cols={[
      { key: "at", head: t("cash.when"), render: (r) => <span className="nowrap">{ftime(r.at)}</span> }, { key: "u", head: t("bill.flat"), render: (r) => <b>{r.unit}</b> }, { key: "by", head: t("cash.by"), render: (r) => r.collector },
      { key: "a", head: t("common.amount"), num: true, render: (r) => money(r.amount) }, { key: "s", head: t("common.status"), render: (r) => <><Chip tone={tone(r.status)}>{t(`cash.st.${r.status}`)}</Chip>{r.locked && <span className="small muted"> · {t("cash.locked")}</span>}{r.expired && !r.locked && <span className="small muted"> · {t("cash.expired")}</span>}</> },
      { key: "act", head: "", render: (r) => r.status === "pending" && collector ? <div className="row">{r.mode === "otp" && !r.locked && (r.expired ? <Btn size="sm" variant="soft" onClick={async () => { try { const x = await api("/cash/entries/" + r.id + "/resend", { method: "POST" }); if (x.demo_code) setDemo(x.demo_code); toast.show(t("cash.sent_code")); load(); } catch (e: any) { toast.show(e.message); } }}>{t("cash.resend")}</Btn> : <Btn size="sm" onClick={() => setCode(r)}>{t("cash.enter_code")}</Btn>)}<Btn size="sm" variant="ghost" onClick={() => act(`/cash/entries/${r.id}/cancel`)}>{t("cash.cancel")}</Btn></div> : null }]} />

    <h3 style={{ margin: "24px 0 10px" }}>{t("cash.handovers")}</h3>
    <DataTable rows={rems} pageSize={6} cols={[{ key: "at", head: t("cash.when"), render: (r) => <span className="nowrap">{ftime(r.at)}</span> }, { key: "by", head: t("cash.by"), render: (r) => r.collector }, { key: "n", head: "", render: (r) => `${r.entries} ${t("cash.entries").toLowerCase()}` },
      { key: "a", head: t("common.amount"), num: true, render: (r) => <b>{money(r.amount)}</b> }, { key: "s", head: t("common.status"), render: (r) => <Chip tone={tone(r.status)}>{t(`cash.st.${r.status}`)}</Chip> },
      { key: "act", head: "", render: (r) => r.status === "submitted" && decider ? <div className="row"><Btn size="sm" onClick={() => act(`/cash/remittances/${r.id}/accept`)}>{t("cash.accept")}</Btn><Btn size="sm" variant="outline" onClick={() => act(`/cash/remittances/${r.id}/reject`)}>{t("cash.reject")}</Btn></div> : null }]} />

    {code && <CodeModal entry={code} onClose={() => setCode(null)} onDone={() => { setCode(null); toast.show(t("cash.confirmed")); load(); }} onFail={load} />}
    {toast.node}
  </>);
}

function CodeModal({ entry, onClose, onDone, onFail }: { entry: Entry; onClose: () => void; onDone: () => void; onFail: () => void }) {
  const { t } = useT(); const [c, setC] = useState(""); const [err, setErr] = useState("");
  const go = async () => { try { await api(`/cash/entries/${entry.id}/code`, { body: { code: c } }); onDone(); } catch (e: any) { setErr(e.message); onFail(); } };
  return <Modal title={`${t("cash.enter_code")} · ${entry.unit} · ${money(entry.amount)}`} onClose={onClose}>
    <Field label={t("cash.code")}><input className="input" inputMode="numeric" maxLength={6} value={c} onChange={(e) => setC(e.target.value.replace(/\D/g, ""))} autoFocus style={{ fontSize: 24, letterSpacing: 6, fontWeight: 800 }} /></Field>
    <p className="hint">{t("cash.tries", { n: entry.tries_left })}</p>{err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn onClick={go} disabled={c.length !== 6}>{t("bill.verify")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
