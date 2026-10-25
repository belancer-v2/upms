"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Tabs } from "@/components/ui";
import { api, money } from "@/lib/api";
import { useT } from "@/lib/i18n";

export type PlanData = { key: string; name: string; name_bn: string; monthly: Record<string, number>; setup: Record<string, number>; sms_included: Record<string, number>; features: string[] };
export type PlansResp = { bands: { key: string; label: string; max: number | null }[]; trial_days: number; yearly_months_paid: number; sms_pack: { count: number; price: number }; plans: PlanData[] };
export const FEATURE_ORDER = ["billing", "expenses", "notices", "resident_web", "reports", "staff", "assets", "tenant_dmp", "reminders", "caretaker_app", "cash_confirm", "policies", "resident_portal", "visitor", "amenities", "parking", "maintenance", "cash_otp", "priority_support"];
export const SOON = new Set(["resident_portal"]);

export function usePlans() {
  const [d, setD] = useState<PlansResp | null>(null);
  useEffect(() => { api<PlansResp>("/public/plans").then(setD).catch(() => {}); }, []);
  return d;
}

export function PricingCards({ compact = false }: { compact?: boolean }) {
  const { t, pick } = useT(); const d = usePlans();
  const [band, setBand] = useState("M"); const [cycle, setCycle] = useState<"monthly" | "yearly">("monthly");
  if (!d) return <p className="muted">{t("common.loading")}</p>;
  const xl = band === "XL";
  const prev: Record<string, string[]> = { basic: [], standard: ["basic"], pro: ["standard"] };
  const own = (p: PlanData) => { const inherited = new Set(prev[p.key].flatMap((k) => d.plans.find((x) => x.key === k)?.features ?? [])); return p.features.filter((f) => !inherited.has(f)); };
  return (
    <div>
      <div className="row wrap between" style={{ marginBottom: 26, gap: 16 }}>
        <div><div className="small muted" style={{ marginBottom: 6, fontWeight: 800 }}>{t("site.price.band")}</div>
          <Tabs value={band} onChange={setBand} items={d.bands.map((b) => ({ id: b.key, label: t(`site.price.band.${b.key}`) }))} /></div>
        <Tabs value={cycle} onChange={setCycle} items={[{ id: "monthly", label: t("site.price.monthly") }, { id: "yearly", label: t("site.price.yearly") }]} />
      </div>
      <div className="price-grid">
        {d.plans.map((p) => {
          const m = p.monthly[band]; const price = cycle === "yearly" ? m * d.yearly_months_paid : m;
          const pop = p.key === "standard";
          return (
            <div key={p.key} className={`card price ${pop ? "pop" : ""}`}>
              {pop && <span className="badge">{t("site.price.popular")}</span>}
              <div><h2>{pick(p.name, p.name_bn)}</h2><p className="muted small" style={{ margin: "4px 0 0" }}>{t(`site.plan.${p.key}.tag`)}</p></div>
              {xl ? <div className="amt" style={{ fontSize: 30 }}>{t("site.price.talk")}</div>
                : <div className="amt">{money(price)} <small>{cycle === "yearly" ? t("site.price.per_year") : t("site.price.per_month")}</small></div>}
              {!xl && <div className="small muted">{t("site.price.sms", { n: p.sms_included[band] })}<br />{t("site.price.setup", { amt: money(p.setup[band]) })}</div>}
              <Link href={xl ? "/demo" : `/signup?plan=${p.key}`} className={`btn ${pop ? "btn-primary" : "btn-outline"}`}>{xl ? t("site.price.talk") : t("site.price.trial")}</Link>
              {!compact && <ul className="feat-list">
                {prev[p.key].length > 0 && <li style={{ fontWeight: 800 }}>{pick(d.plans.find((x) => x.key === prev[p.key][0])!.name, d.plans.find((x) => x.key === prev[p.key][0])!.name_bn)} +</li>}
                {own(p).map((f) => <li key={f}>{t(`feat.${f}`)}{SOON.has(f) && <span className="chip mute" style={{ marginLeft: 6 }}>{t("site.price.soon")}</span>}</li>)}
              </ul>}
            </div>
          );
        })}
      </div>
      {xl && <p className="muted" style={{ marginTop: 16 }}>{t("site.price.xl")}</p>}
    </div>
  );
}

export function CompareTable() {
  const { t, pick } = useT(); const d = usePlans();
  if (!d) return null;
  return (
    <div className="table-wrap"><table className="t cmp">
      <thead><tr><th>{t("site.price.feature")}</th>{d.plans.map((p) => <th key={p.key} className="center">{pick(p.name, p.name_bn)}</th>)}</tr></thead>
      <tbody>{FEATURE_ORDER.map((f) => (
        <tr key={f}><td>{t(`feat.${f}`)}{SOON.has(f) && <span className="chip mute" style={{ marginLeft: 8 }}>{t("site.price.soon")}</span>}</td>
          {d.plans.map((p) => <td key={p.key} className="center">{p.features.includes(f) ? <span className="tick" aria-label={t("common.yes")}>✓</span> : <span className="dash" aria-label={t("common.no")}>–</span>}</td>)}</tr>
      ))}</tbody>
    </table></div>
  );
}

export function Faq({ items = [1, 2, 3, 4, 5, 6, 7, 8] }: { items?: number[] }) {
  const { t } = useT();
  return <div className="faq">{items.map((i) => <details key={i}><summary>{t(`site.faq.${i}.q`)}</summary><p>{t(`site.faq.${i}.a`)}</p></details>)}</div>;
}
