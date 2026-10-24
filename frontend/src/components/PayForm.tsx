"use client";
import { useState } from "react";
import { type Inv, type Pay } from "@/components/billbits";
import { Btn, Field, Modal } from "@/components/ui";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export function PayForm({ inv, staff, onClose, onDone }: { inv: Inv; staff: boolean; onClose: () => void; onDone: (pending: boolean) => void }) {
  const { t } = useT(); const [f, setF] = useState({ amount: String(inv.balance / 100), method: "bkash", trx_id: "", note: "" }); const [err, setErr] = useState("");
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const go = async () => { try { const r = await api<Pay>(`/billing/invoices/${inv.id}/payments`, { body: { amount: Math.round(+f.amount * 100), method: f.method, trx_id: f.trx_id, note: f.note } }); onDone(r.status === "pending"); } catch (e: any) { setErr(e.message); } };
  return <Modal title={`${staff ? t("bill.record") : t("pay.i_paid")} · ${inv.unit} · ${inv.period}`} onClose={onClose}>
    {!staff && <p className="hint">{t("pay.how")}</p>}
    <div className="grid g2"><Field label={staff ? t("common.amount") : t("pay.amount")}><input className="input" inputMode="decimal" value={f.amount} onChange={set("amount")} /></Field>
      <Field label={t("bill.method")}><select className="input" value={f.method} onChange={set("method")}>{(staff ? ["cash", "bank", "bkash", "nagad"] : ["bkash", "nagad", "bank"]).map((m) => <option key={m} value={m}>{t(`bill.m.${m}`)}</option>)}</select></Field></div>
    {f.method !== "cash" && <Field label={t("bill.trx")} hint={t("bill.trx_hint")}><input className="input" value={f.trx_id} onChange={set("trx_id")} /></Field>}
    <Field label={t("bill.note")}><input className="input" value={f.note} onChange={set("note")} /></Field>
    {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn onClick={go} disabled={!(+f.amount > 0)}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
