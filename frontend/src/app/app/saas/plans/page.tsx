"use client";
import { useEffect, useState } from "react";
import { Btn, Card, PageHead, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type P = { key: string; name: string; name_bn: string; monthly: Record<string, number>; setup: Record<string, number>; sms_included: Record<string, number>; email_included?: Record<string, number>; features: string[]; subscribers: number };

export default function Plans() {
  const { t, pick } = useT(); const { saas } = useAuth(); const toast = useToast(); const can = saas("SUPER_ADMIN");
  const [d, setD] = useState<{ all_features: string[]; plans: P[] } | null>(null);
  useEffect(() => { api("/saas/plans").then(setD); }, []);
  if (!d) return <p className="muted">{t("common.loading")}</p>;
  const edit = (k: string, fn: (p: P) => void) => setD({ ...d, plans: d.plans.map((p) => { if (p.key !== k) return p; const c = JSON.parse(JSON.stringify(p)); fn(c); return c; }) });
  const save = async (p: P) => { await api(`/saas/plans/${p.key}`, { method: "PUT", body: { monthly: p.monthly, setup: p.setup, sms_included: p.sms_included, email_included: p.email_included ?? {}, features: p.features } }); toast.show(t("saas.plans.saved")); };
  const num = (p: P, field: "monthly" | "setup", b: string, scale = 100) => <input className="input" style={{ width: "100%", minWidth: 0, textAlign: "right", paddingInline: 8 }} type="number" disabled={!can} aria-label={`${t(field === "monthly" ? "saas.plans.monthly" : "saas.plans.setup")} ${b}`} value={Math.round((p[field][b] ?? 0) / scale)} onChange={(e) => edit(p.key, (c) => { c[field][b] = Number(e.target.value) * scale; })} />;
  const email = (p: P, b: string) => <input className="input" style={{ width: "100%", minWidth: 0, textAlign: "right", paddingInline: 8 }} type="number" min={0} disabled={!can} aria-label={`${t("saas.plans.email")} ${b}`} value={p.email_included?.[b] ?? 0} onChange={(e) => edit(p.key, (c) => { c.email_included = { ...(c.email_included ?? {}), [b]: Math.max(0, Number(e.target.value)) }; })} />;
  return (
    <>
      <PageHead helpKey="saas-plans" title={t("saas.plans.title")} sub={can ? t("saas.plans.sub") : t("saas.plans.readonly")} />
      <div className="grid g3" style={{ alignItems: "start" }}>
        {d.plans.map((p) => (
          <Card key={p.key} style={{ minWidth: 0 }}><div className="row between"><h2>{pick(p.name, p.name_bn)}</h2><span className="chip info">{t("saas.plans.subs", { n: p.subscribers })}</span></div>
            <div role="group" aria-label={t("saas.plans.title")} style={{ display: "grid", gridTemplateColumns: "28px repeat(3, minmax(0, 1fr))", gap: "6px 8px", alignItems: "end", margin: "14px 0" }}>
              <span />{["saas.plans.monthly", "saas.plans.setup", "saas.plans.email"].map((k) => <span key={k} className="tiny muted" style={{ fontWeight: 800, lineHeight: 1.25 }}>{t(k)}</span>)}
              {["S", "M", "L"].flatMap((b) => [<b key={`${b}l`} style={{ alignSelf: "center" }}>{b}</b>, <div key={`${b}m`}>{num(p, "monthly", b)}</div>, <div key={`${b}s`}>{num(p, "setup", b)}</div>, <div key={`${b}e`}>{email(p, b)}</div>])}
            </div>
            <p className="small muted" style={{ margin: "0 0 8px" }}>{t("saas.plans.sms")}: S {p.sms_included.S} · M {p.sms_included.M} · L {p.sms_included.L}</p>
            <div className="small" style={{ fontWeight: 800, margin: "12px 0 6px" }}>{t("saas.plans.features")}</div>
            <div className="col" style={{ gap: 4 }}>{d.all_features.map((f) => <label key={f} className="row" style={{ gap: 8, fontSize: 13.5 }}><input type="checkbox" disabled={!can} checked={p.features.includes(f)} onChange={(e) => edit(p.key, (c) => { c.features = e.target.checked ? [...c.features, f] : c.features.filter((x) => x !== f); })} />{t(`feat.${f}`)}</label>)}</div>
            {can && <div style={{ marginTop: 16 }}><Btn onClick={() => save(p)}>{t("common.save")}</Btn></div>}</Card>
        ))}
      </div>{toast.node}
    </>
  );
}
