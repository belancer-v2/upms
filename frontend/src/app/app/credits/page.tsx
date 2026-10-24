"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Pager } from "@/components/pager";
import { Btn, Card, Chip, Empty, Field, Modal, PageHead, Stat, useToast } from "@/components/ui";
import { api, fdate, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type Pack = { id: number; kind: string; name: string; name_bn: string; credits: number; price: number; vat: number; total: number };
type Kind = { balance: number; threshold: number; is_low: boolean; total: number; by_purpose: Record<string, number> };
type Sum = { can_manage: boolean; vat_bps: number; providers: string[]; pay_to: Record<string, string>; sms: Kind; email: Kind; packs: Pack[] };
type Buy = { id: number; kind: string; pack_name: string; pack_name_bn: string; credits: number; total: number; method: string; status: string; trx_id: string; invoice_id: number | null; invoice: string; created_at: string };
const PURPOSES = ["reminders", "notices", "otp", "payslips", "onboarding", "other"];
const tone = (s: string) => (s === "paid" ? "ok" : s === "pending" ? "warn" : s === "rejected" || s === "failed" ? "bad" : "mute") as "ok" | "warn" | "bad" | "mute";

/** Horizontal bars, one per purpose. Same colour token for every bar; the number sits at the end so nothing relies on colour alone. */
function UsageBars({ k }: { k: Kind }) {
  const { t } = useT(); const max = Math.max(1, ...Object.values(k.by_purpose));
  if (!k.total) return <p className="small muted">{t("cr.usage_none")}</p>;
  return <div className="stack" style={{ gap: 8 }} role="list">{PURPOSES.filter((p) => k.by_purpose[p]).map((p) => (
    <div key={p} role="listitem" className="row" style={{ gap: 10 }}><span className="small" style={{ width: 110 }}>{t(`cr.purpose.${p}`)}</span>
      <div style={{ flex: 1 }}><div className="bar"><i style={{ width: `${Math.max(2, (k.by_purpose[p] / max) * 100)}%` }} /></div></div><b className="small" style={{ width: 56, textAlign: "right" }}>{k.by_purpose[p].toLocaleString("en-US")}</b></div>))}</div>;
}

export default function Credits() {
  const { t, pick } = useT(); const toast = useToast(); const { prop } = useAuth();
  const [s, setS] = useState<Sum | null>(null); const [err, setErr] = useState("");
  const [buy, setBuy] = useState<Pack | null>(null); const [how, setHow] = useState<"online" | "transfer">("online"); const [prov, setProv] = useState("bkash"); const [man, setMan] = useState("bkash");
  const [trx, setTrx] = useState(""); const [amt, setAmt] = useState(""); const [note, setNote] = useState(""); const [busy, setBusy] = useState(false); const [ferr, setFerr] = useState("");
  const [thr, setThr] = useState({ sms: "", email: "" });
  const [rows, setRows] = useState<Buy[]>([]); const [total, setTotal] = useState(0); const [page, setPage] = useState(1); const [q, setQ] = useState(""); const size = 8;
  const loadSum = useCallback(() => api<Sum>("/credits/summary").then((d) => { setS(d); setThr({ sms: String(d.sms.threshold), email: String(d.email.threshold) }); }).catch((e) => setErr(e.message)), []);
  const loadRows = useCallback(() => api<{ total: number; rows: Buy[] }>(`/credits/purchases?page=${page}&size=${size}&q=${encodeURIComponent(q)}`).then((d) => { setRows(d.rows); setTotal(d.total); }).catch(() => {}), [page, q]);
  useEffect(() => { loadSum(); }, [loadSum, prop?.id]);
  useEffect(() => { loadRows(); }, [loadRows, prop?.id]);
  if (err) return <p className="error" role="alert">{err}</p>; if (!s) return <p className="muted">{t("common.loading")}</p>;
  const vatP = `${(s.vat_bps / 100).toLocaleString("en-US", { maximumFractionDigits: 2 })}%`;
  const open = (p: Pack) => { setBuy(p); setHow("online"); setFerr(""); setTrx(""); setAmt((p.total / 100).toFixed(2)); setNote(""); };
  const go = async () => {
    if (!buy) return; setBusy(true); setFerr("");
    try {
      if (how === "online") { const r = await api<{ redirect_url: string }>("/credits/checkout", { body: { pack_id: buy.id, provider: prov } }); window.location.href = r.redirect_url; return; }
      await api("/credits/manual", { body: { pack_id: buy.id, method: man, trx_id: trx.trim(), amount: Math.round(parseFloat(amt || "0") * 100), note } });
      setBuy(null); toast.show(t("cr.manual_sent")); loadSum(); loadRows();
    } catch (e: any) { setFerr(e.message); } finally { setBusy(false); }
  };
  const saveThr = async () => { try { await api("/credits/threshold", { method: "PUT", body: { sms_low: parseInt(thr.sms || "0", 10), email_low: parseInt(thr.email || "0", 10) } }); toast.show(t("cr.thr_saved")); loadSum(); } catch (e: any) { toast.show(e.message); } };
  const lows = (["sms", "email"] as const).filter((k) => s[k].is_low);
  const packName = (p: { name: string; name_bn: string }) => pick(p.name, p.name_bn || p.name);
  return (
    <>
      <PageHead title={t("cr.title")} sub={t("cr.sub")} />
      {s.can_manage && lows.map((k) => <div key={k} role="alert" className="card" style={{ marginBottom: 12, borderColor: "var(--warn)", background: "var(--warn-bg)", color: "var(--warn)", fontWeight: 700 }}>
        {t("cr.alert", { k: t(`cr.${k}`), n: s[k].balance.toLocaleString("en-US"), t: s[k].threshold.toLocaleString("en-US") })}</div>)}
      <div className="grid g2" style={{ marginBottom: 18 }}>
        {(["sms", "email"] as const).map((k) => <Card key={k}><Stat label={t(`cr.${k}`)} value={s[k].balance.toLocaleString("en-US")} note={<>{t("cr.used30")}: {s[k].total.toLocaleString("en-US")} <Chip tone={s[k].is_low ? "warn" : "ok"}>{s[k].is_low ? t("cr.low") : t("cr.ok")}</Chip></>} />
          <h3 style={{ margin: "16px 0 8px", fontSize: 15 }}>{t("cr.usage")}</h3><UsageBars k={s[k]} /></Card>)}
      </div>
      {s.can_manage && <Card className="stack" style={{ marginBottom: 18 }}><div><h3>{t("cr.threshold")}</h3><p className="small muted">{t("cr.threshold_sub")}</p></div>
        <div className="row wrap" style={{ alignItems: "flex-end" }}>
          <Field label={t("cr.thr_sms")}><input className="input" type="number" min={0} style={{ width: 150 }} value={thr.sms} onChange={(e) => setThr({ ...thr, sms: e.target.value })} /></Field>
          <Field label={t("cr.thr_email")}><input className="input" type="number" min={0} style={{ width: 150 }} value={thr.email} onChange={(e) => setThr({ ...thr, email: e.target.value })} /></Field>
          <Btn onClick={saveThr}>{t("common.save")}</Btn></div></Card>}
      <h2 style={{ margin: "8px 0 12px" }}>{t("cr.packs")}</h2>
      {s.packs.length === 0 ? <Empty>{t("cr.nopacks")}</Empty> : (["sms", "email"] as const).map((k) => <div key={k} style={{ marginBottom: 16 }}>
        <div className="eyebrow" style={{ marginBottom: 8 }}>{t(`cr.${k}`)}</div>
        <div className="grid g3">{s.packs.filter((p) => p.kind === k).map((p) => <Card key={p.id} className="stack">
          <div><b style={{ fontSize: 18 }}>{packName(p)}</b><div className="small muted">{t("cr.credits", { n: p.credits.toLocaleString("en-US") })}</div></div>
          <div><span style={{ fontSize: 26, fontWeight: 900 }}>{money(p.total)}</span>{p.vat > 0 && <div className="small muted">{t("cr.price")} {money(p.price)} · {t("cr.per_vat", { p: vatP })} {money(p.vat)}</div>}</div>
          <Btn onClick={() => open(p)}>{t("cr.buy")}</Btn></Card>)}</div></div>)}
      <div className="row between wrap" style={{ margin: "24px 0 12px" }}><h2>{t("cr.history")}</h2>
        <input className="input" style={{ maxWidth: 260 }} placeholder={t("cr.search")} aria-label={t("cr.search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} /></div>
      {rows.length === 0 ? <Empty /> : <div className="table-wrap"><table className="t"><thead><tr>
        <th>{t("cr.col.when")}</th><th>{t("cr.col.pack")}</th><th>{t("cr.col.method")}</th><th>{t("cr.col.trx")}</th><th className="num">{t("cr.col.total")}</th><th>{t("cr.col.status")}</th><th>{t("cr.col.invoice")}</th></tr></thead><tbody>
        {rows.map((r) => <tr key={r.id}><td className="nowrap">{fdate(r.created_at)}</td><td>{packName({ name: r.pack_name, name_bn: r.pack_name_bn })}</td><td>{t(`cr.m.${r.method}`)}</td><td>{r.trx_id}</td>
          <td className="num">{money(r.total)}</td><td><Chip tone={tone(r.status)}>{t(`cr.st.${r.status}`)}</Chip></td>
          <td>{r.invoice_id ? <Link href={`/app/credits/invoice/${r.invoice_id}`}>{r.invoice || t("cr.view")}</Link> : ""}</td></tr>)}</tbody></table></div>}
      <Pager page={page} size={size} total={total} onPage={setPage} />
      {buy && <Modal title={t("cr.pay_title", { pack: packName(buy) })} onClose={() => setBuy(null)}>
        <div className="stack" style={{ gap: 8, marginBottom: 12 }}>
          <div className="row between"><span>{t("cr.price")}</span><span>{money(buy.price)}</span></div>
          {buy.vat > 0 && <div className="row between"><span>{t("cr.vat")} {vatP}</span><span>{money(buy.vat)}</span></div>}
          <div className="row between"><b>{t("cr.you_pay")}</b><b>{money(buy.total)}</b></div></div>
        <p className="hint">{t("cr.pay_how")}</p>
        <div className="row" style={{ marginBottom: 12 }}><Btn variant={how === "online" ? "primary" : "outline"} onClick={() => setHow("online")}>{t("cr.online")}</Btn><Btn variant={how === "transfer" ? "primary" : "outline"} onClick={() => setHow("transfer")}>{t("cr.transfer")}</Btn></div>
        {how === "online" ? <>
          <div className="stack" style={{ gap: 8, marginBottom: 12 }}>{s.providers.map((k) => <label key={k} className="row" style={{ padding: "10px 12px", border: `1px solid ${prov === k ? "var(--brand)" : "var(--line)"}`, borderRadius: 10, cursor: "pointer", background: "var(--surface)" }}>
            <input type="radio" name="prov" checked={prov === k} onChange={() => setProv(k)} /> <b>{t(`cr.m.${k}`)}</b></label>)}</div>
          <p className="small muted">{t("cr.sandbox_note")}</p></> : <>
          <Field label={t("cr.col.method")}><select className="input" value={man} onChange={(e) => setMan(e.target.value)}>{["bkash", "nagad", "bank"].map((k) => <option key={k} value={k}>{t(`cr.m.${k}`)}</option>)}</select></Field>
          {s.pay_to[man] && <p className="small">{t("cr.send_to")}: <b>{s.pay_to[man]}</b> · {money(buy.total)}</p>}
          <Field label={t("cr.trx")}><input className="input" value={trx} onChange={(e) => setTrx(e.target.value)} /></Field>
          <Field label={t("cr.sent_amount")}><input className="input" inputMode="decimal" value={amt} onChange={(e) => setAmt(e.target.value)} /></Field>
          <Field label={t("cr.note")}><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field></>}
        {ferr && <p className="error" role="alert">{ferr}</p>}
        <div className="row"><Btn onClick={go} disabled={busy || (how === "transfer" && trx.trim().length < 4)}>{how === "online" ? t("cr.go") : t("cr.submit_manual")}</Btn><Btn variant="ghost" onClick={() => setBuy(null)}>{t("common.cancel")}</Btn></div></Modal>}
      {toast.node}
    </>
  );
}
