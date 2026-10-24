"use client";
import { useEffect, useState } from "react";
import { Btn, Card, PageHead, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type P = { key: string; name: string; name_bn: string; monthly: Record<string, number>; setup: Record<string, number>; sms_included: Record<string, number>; features: string[]; subscribers: number };

export default function Plans() {
  const { t, pick } = useT(); const { saas } = useAuth(); const toast = useToast(); const can = saas("SUPER_ADMIN");
  const [d, setD] = useState<{ all_features: string[]; plans: P[] } | null>(null);
  useEffect(() => { api("/saas/plans").then(setD); }, []);
  if (!d) return <p className="muted">{t("common.loading")}</p>;
  const edit = (k: string, fn: (p: P) => void) => setD({ ...d, plans: d.plans.map((p) => { if (p.key !== k) return p; const c = JSON.parse(JSON.stringify(p)); fn(c); return c; }) });
  const save = async (p: P) => { await api(`/saas/plans/${p.key}`, { method: "PUT", body: { monthly: p.monthly, setup: p.setup, sms_included: p.sms_included, features: p.features } }); toast.show(t("saas.plans.saved")); };
  const num = (p: P, field: "monthly" | "setup", b: string, scale = 100) => <input className="input" style={{ width: 110, textAlign: "right" }} type="number" disabled={!can} value={Math.round((p[field][b] ?? 0) / scale)} onChange={(e) => edit(p.key, (c) => { c[field][b] = Number(e.target.value) * scale; })} />;
  return (
    <>
      <PageHead title={t("saas.plans.title")} sub={can ? t("saas.plans.sub") : t("saas.plans.readonly")} />
      <div className="grid g3" style={{ alignItems: "start" }}>
        {d.plans.map((p) => (
          <Card key={p.key}><div className="row between"><h2>{pick(p.name, p.name_bn)}</h2><span className="chip info">{t("saas.plans.subs", { n: p.subscribers })}</span></div>
            <table className="t" style={{ margin: "12px 0" }}><thead><tr><th>{t("saas.d.band")}</th><th className="num">{t("saas.plans.monthly")}</th><th className="num">{t("saas.plans.setup")}</th></tr></thead>
              <tbody>{["S", "M", "L"].map((b) => <tr key={b}><td><b>{b}</b></td><td className="num">{num(p, "monthly", b)}</td><td className="num">{num(p, "setup", b)}</td></tr>)}</tbody></table>
            <p className="small muted" style={{ margin: "0 0 8px" }}>{t("saas.plans.sms")}: S {p.sms_included.S} · M {p.sms_included.M} · L {p.sms_included.L}</p>
            <div className="small" style={{ fontWeight: 800, margin: "12px 0 6px" }}>{t("saas.plans.features")}</div>
            <div className="col" style={{ gap: 4 }}>{d.all_features.map((f) => <label key={f} className="row" style={{ gap: 8, fontSize: 13.5 }}><input type="checkbox" disabled={!can} checked={p.features.includes(f)} onChange={(e) => edit(p.key, (c) => { c.features = e.target.checked ? [...c.features, f] : c.features.filter((x) => x !== f); })} />{t(`feat.${f}`)}</label>)}</div>
            {can && <div style={{ marginTop: 16 }}><Btn onClick={() => save(p)}>{t("common.save")}</Btn></div>}</Card>
        ))}
      </div>{toast.node}
    </>
  );
}
