"use client";
import { useEffect, useState } from "react";
import { type Inv } from "@/components/billbits";
import { Btn, Modal } from "@/components/ui";
import { api, money } from "@/lib/api";
import { useT } from "@/lib/i18n";

export type GwOptions = { enabled: boolean; providers: string[]; fee_mode: string; fee_bps: number };
/** Same integer rounding as the server: half up, in paisa. */
export const gwFee = (amount: number, bps: number) => Math.floor((amount * bps + 5000) / 10000);

/** Loads what the building allows. A building without the feature simply reports "off". */
export function useGateway(deps: unknown): GwOptions | null {
  const [o, setO] = useState<GwOptions | null>(null);
  useEffect(() => { api<GwOptions>("/gateway/options").then(setO).catch(() => setO(null)); }, [deps]);
  return o;
}

export function GatewayPay({ inv, opts, onClose }: { inv: Inv; opts: GwOptions; onClose: () => void }) {
  const { t } = useT(); const [p, setP] = useState(opts.providers[0]); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const fee = gwFee(inv.balance, opts.fee_bps); const payerPays = opts.fee_mode === "payer_pays" && fee > 0;
  const go = async () => { setBusy(true); try { const r = await api<{ redirect_url: string }>("/gateway/checkout", { body: { invoice_id: inv.id, provider: p } }); window.location.href = r.redirect_url; } catch (e: any) { setErr(e.message); setBusy(false); } };
  return <Modal title={`${t("gw.pay_title")} · ${inv.unit} · ${inv.period}`} onClose={onClose}>
    <p className="hint">{t("gw.choose")}</p>
    <div className="stack" style={{ gap: 8, marginBottom: 12 }}>{opts.providers.map((k) => {
      const f = payerPays ? fee : 0;
      return <label key={k} className="row between" style={{ padding: "10px 12px", border: `1px solid ${p === k ? "var(--brand)" : "var(--line)"}`, borderRadius: 10, cursor: "pointer", background: "var(--surface)" }}>
        <span className="row"><input type="radio" name="gw" checked={p === k} onChange={() => setP(k)} /> <b>{t(`gw.p.${k}`)}</b></span>
        <span className="small muted">{f ? t("gw.fee_line", { f: money(f) }) : t("gw.no_fee")}</span></label>; })}</div>
    <div className="row between" style={{ marginBottom: 12 }}><span>{t("gw.you_pay")}</span><b>{money(inv.balance + (payerPays ? fee : 0))}</b></div>
    <p className="small muted">{t("gw.sandbox_note")}</p>
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn onClick={go} disabled={busy}>{t("gw.go")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
