"use client";
import { use } from "react";
import { Logo } from "@/components/Logo";
import { Toggles } from "@/components/Toggles";
import { useT } from "@/lib/i18n";

const OUTCOMES = ["success", "fail", "cancel", "error"] as const;
const COLOR: Record<string, string> = { success: "var(--ok)", fail: "var(--bad)", cancel: "var(--muted)", error: "var(--warn, var(--muted))" };

/** Where bKash and SSLCommerz send the customer's browser back to. The server has already checked the payment with the provider; this page only tells the result. */
export default function PayReturn({ params }: { params: Promise<{ outcome: string }> }) {
  const { outcome } = use(params); const { t } = useT();
  const o = (OUTCOMES as readonly string[]).includes(outcome) ? outcome : "error";
  return (<div style={{ maxWidth: 480, margin: "0 auto", padding: "20px 16px 60px" }}>
    <div className="row between" style={{ marginBottom: 24 }}><Logo /><Toggles /></div>
    <div className="card stack">
      <h1 role="status" style={{ margin: 0, fontSize: 26, color: COLOR[o] }}>{t(`pay.ret.${o}`)}</h1>
      <p>{t(`pay.ret.${o}_sub`)}</p>
      <a className="btn btn-primary" href="/app/pay">{t("pay.ret.back")}</a>
    </div>
  </div>);
}
