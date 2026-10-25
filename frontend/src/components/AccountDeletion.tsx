"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, Field, useToast } from "./ui";
import { api } from "@/lib/api";
import { fdate } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Req = { id: number; status: string; reason: string; requested_at: string; processed_at: string | null; note: string };
type State = { request: Req | null; blockers: string[] };

/** "Delete my account" on the profile page: ask, see the state, withdraw. FlatWise staff process the request. */
export function AccountDeletion() {
  const { t } = useT(); const toast = useToast();
  const [s, setS] = useState<State | null>(null); const [open, setOpen] = useState(false); const [pw, setPw] = useState(""); const [reason, setReason] = useState(""); const [busy, setBusy] = useState(false);
  const load = useCallback(() => api<State>("/me/deletion").then(setS).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  if (!s) return null;
  const pending = s.request?.status === "pending";
  const send = async () => {
    setBusy(true);
    try { await api("/me/deletion", { body: { password: pw, reason } }); setOpen(false); setPw(""); toast.show(t("dx.del.sent")); await load(); }
    catch (e: any) { toast.show(e.message === "last_admin" ? t("dx.del.b.last_admin") : e.message === "saas_staff" ? t("dx.del.b.saas_staff") : e.message); } finally { setBusy(false); }
  };
  const withdraw = async () => { try { await api("/me/deletion", { method: "DELETE" }); toast.show(t("dx.del.withdrawn")); await load(); } catch (e: any) { toast.show(e.message); } };
  return (
    <Card style={{ gridColumn: "1 / -1" }}>
      <h3>{t("dx.del.title")}</h3>
      <p className="muted small" style={{ marginTop: 6 }}>{t("dx.del.sub")}</p>
      {s.request && s.request.status !== "cancelled" && <p><Chip tone={pending ? "warn" : s.request.status === "completed" ? "ok" : "bad"}>{t(`dx.del.st.${s.request.status}`)}</Chip> <span className="small muted">{fdate(s.request.requested_at)}{s.request.note ? ` · ${s.request.note}` : ""}</span></p>}
      {s.blockers.map((b) => <p key={b} className="small" role="note" style={{ color: "var(--warn)" }}>{t(`dx.del.b.${b}`)}</p>)}
      {pending ? <Btn variant="ghost" onClick={withdraw}>{t("dx.del.withdraw")}</Btn>
        : s.blockers.length === 0 && (open ? (
          <div className="stack" style={{ maxWidth: 460 }}>
            <Field label={t("dx.del.password")}><input className="input" type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
            <Field label={t("dx.del.reason")}><input className="input" maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
            <div className="row wrap"><Btn variant="danger" onClick={send} disabled={busy || !pw}>{t("dx.del.send")}</Btn><Btn variant="ghost" onClick={() => setOpen(false)}>{t("common.cancel")}</Btn></div>
          </div>) : <Btn variant="outline" onClick={() => setOpen(true)}>{t("dx.del.open")}</Btn>)}
      {toast.node}
    </Card>
  );
}
