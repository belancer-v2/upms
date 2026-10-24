"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Btn, Field, Modal, useToast } from "@/components/ui";
import { CreditSheet, InvoiceSheet, SHEET_CSS } from "@/components/invoicedoc";
import { api, store } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function InvoiceDoc() {
  const { t } = useT(); const toast = useToast();
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<any>(null); const [cn, setCn] = useState<any>(null); const [err, setErr] = useState("");
  const [modal, setModal] = useState<"" | "void" | "refund">(""); const [reason, setReason] = useState(""); const [amt, setAmt] = useState("");
  const load = useCallback(async () => {
    try {
      setD(await api(`/saas/invoices-doc/${id}`));
      const c = new URLSearchParams(window.location.search).get("cn");
      setCn(c ? await api(`/saas/invoices-doc/credit-note/${c}`) : null);
    } catch (e: any) { setErr(e.message); }
  }, [id]);
  useEffect(() => { load(); }, [load]);
  if (err) return <p className="muted">{err}</p>;
  if (!d) return <p className="muted">{t("common.loading")}</p>;
  const act = async (fn: () => Promise<any>, ok?: string) => { try { const r = await fn(); if (ok) toast.show(ok); await load(); return r; } catch (e: any) { toast.show(e.message); } };
  const issue = async () => { const r = await act(() => api(`/saas/invoices-doc/${id}/issue`, { body: {} })); if (r) toast.show(t("idoc.issued_ok", { n: r.doc_no })); };
  const setLang = (lang: string) => act(() => api(`/saas/invoices-doc/${id}/lang`, { method: "PUT", body: { lang } }));
  const email = async () => { const r = await act(() => api(`/saas/invoices-doc/${id}/email`, { body: {} })); if (r) toast.show(r.sent ? t("idoc.emailed") : t("idoc.not_emailed")); };
  const doVoid = async () => { await act(() => api(`/saas/invoices-doc/${id}/void`, { body: { reason: reason || "Invoice voided" } })); setModal(""); setReason(""); };
  const doRefund = async () => { await act(() => api(`/saas/invoices-doc/${id}/refund`, { body: { amount: amt ? Math.round(Number(amt) * 100) : null, reason: reason || "Refund" } })); setModal(""); setReason(""); setAmt(""); };
  const statementCsv = async () => {
    const res = await fetch(`/api/saas/invoices-doc/statement/${d.customer.id}/csv`, { headers: { Authorization: `Bearer ${store.token}` } });
    if (!res.ok) return; const url = URL.createObjectURL(await res.blob()); const a = document.createElement("a"); a.href = url; a.download = `flatwise-statement-${d.customer.id}.csv`; a.click(); URL.revokeObjectURL(url);
  };
  return (
    <>
      <style>{SHEET_CSS}</style>
      <div className="no-print" style={{ maxWidth: "210mm", margin: "0 auto 14px" }}>
        <div className="row wrap" style={{ gap: 8 }}>
          <Link href="/app/saas/invoices" className="btn btn-ghost btn-sm">{t("idoc.act.back")}</Link>
          <Btn onClick={() => window.print()}>{t("idoc.act.print")}</Btn>
          {!d.issued && <Btn variant="outline" onClick={issue}>{t("idoc.act.issue")}</Btn>}
          {d.issued && <Btn variant="outline" onClick={email}>{t("idoc.act.email")}</Btn>}
          {d.stamp === "due" && <Btn variant="danger" onClick={() => setModal("void")}>{t("idoc.act.void")}</Btn>}
          {d.stamp === "paid" && d.credited < d.total && <Btn variant="outline" onClick={() => setModal("refund")}>{t("idoc.act.refund")}</Btn>}
          <Link href={`/app/saas/invoice/statement/${d.customer.id}`} className="btn btn-ghost btn-sm">{t("idoc.act.statement")}</Link>
          <Btn variant="ghost" size="sm" onClick={statementCsv}>{t("idoc.act.csv")}</Btn>
          <span className="row" style={{ gap: 6, marginLeft: "auto" }}><span className="small muted">{t("idoc.lang")}</span>
            {(["en", "bn"] as const).map((l) => <Btn key={l} size="sm" variant={d.lang === l ? "primary" : "ghost"} onClick={() => setLang(l)}>{t(`set.lang.${l}`)}</Btn>)}</span>
        </div>
        {!d.issued && <p className="small muted" style={{ marginTop: 10 }}>{t("idoc.notissued")}</p>}
        {d.credit_notes.length > 0 && <div className="small row wrap" style={{ marginTop: 8, gap: 10 }}>{t("idoc.credits")}: <Link href={`/app/saas/invoice/${id}`}>{d.doc_no}</Link>{d.credit_notes.map((c: any) => <a key={c.id} href={`/app/saas/invoice/${id}?cn=${c.id}`}>{c.doc_no}</a>)}</div>}
      </div>
      {cn ? <CreditSheet d={cn} inv={d} /> : <InvoiceSheet d={d} />}
      {modal && <Modal title={modal === "void" ? t("idoc.act.void") : t("idoc.act.refund")} onClose={() => setModal("")}>
        {modal === "void" && <p className="muted">{t("idoc.confirm_void")}</p>}
        {modal === "refund" && <Field label={t("idoc.refund_amt")}><input className="input" type="number" min="1" value={amt} onChange={(e) => setAmt(e.target.value)} /></Field>}
        <Field label={t("idoc.reason")}><input className="input" value={reason} placeholder={t("idoc.reason_ph")} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="row"><Btn variant={modal === "void" ? "danger" : "primary"} onClick={modal === "void" ? doVoid : doRefund}>{modal === "void" ? t("idoc.act.void") : t("idoc.act.refund")}</Btn><Btn variant="ghost" onClick={() => setModal("")}>{t("common.cancel")}</Btn></div></Modal>}
      {toast.node}
    </>
  );
}
