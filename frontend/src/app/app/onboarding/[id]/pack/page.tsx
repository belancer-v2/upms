"use client";
import { use, useEffect, useState } from "react";
import { Btn } from "@/components/ui";
import { api, fdate, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type P = { building: string; building_bn: string; address: string; unit: string; floor: number; block: string; area_sqft: number; bedrooms: number; owners: { name: string; name_bn: string; phone: string }[]; tenant: { name: string; phone: string; nid: string };
  details: Record<string, any>; rent: number; advance: number; start_date: string; lease_months: number; docs: { kind: string; status: string }[]; police_ref: string; printed_on: string };
export default function Pack({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params); const { t, pick } = useT(); const { prop } = useAuth(); const [p, setP] = useState<P | null>(null); const [err, setErr] = useState("");
  useEffect(() => { api<P>(`/onboarding/cases/${id}/pack`).then(setP).catch((e) => setErr(e.message)); }, [id, prop?.id]);
  if (err) return <p className="error">{err}</p>; if (!p) return <p className="muted">{t("common.loading")}</p>;
  const d = p.details; const row = (k: string, v: React.ReactNode) => <tr><td style={{ width: "38%", color: "var(--muted)", padding: "7px 10px", borderTop: "1px solid var(--line)" }}>{k}</td><td style={{ padding: "7px 10px", borderTop: "1px solid var(--line)", fontWeight: 700 }}>{v || "–"}</td></tr>;
  const sec = (title: string, body: React.ReactNode) => <div style={{ marginTop: 18 }}><h3 style={{ margin: "0 0 4px", color: "var(--wine, #691542)" }}>{title}</h3><table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14.5 }}><tbody>{body}</tbody></table></div>;
  return (<div style={{ maxWidth: 780, margin: "0 auto" }}>
    <div className="row between no-print" style={{ marginBottom: 12 }}><span className="hint" style={{ margin: 0 }}>{t("dmp.contains_id")}</span><Btn onClick={() => window.print()}>{t("dmp.print")}</Btn></div>
    <div className="card" style={{ padding: 28 }}><div className="eyebrow">{t("dmp.sub")}</div><h1 style={{ margin: "4px 0 2px", fontSize: 24 }}>{t("dmp.title")}</h1><span className="small muted">{t("dmp.printed", { d: fdate(p.printed_on) })}{p.police_ref && ` · ${p.police_ref}`}</span>
      {sec(t("dmp.a"), <>{row(t("ob.f.unit"), `${p.unit} · ${t("dmp.floor")} ${p.floor} · ${t("dmp.block")} ${p.block}`)}{row(t("shell.building"), pick(p.building, p.building_bn || p.building))}{row(t("port.address"), p.address)}{row(`${t("dmp.area")} / ${t("dmp.beds")}`, `${p.area_sqft} sq ft · ${p.bedrooms}`)}</>)}
      {sec(t("dmp.b"), p.owners.map((o, i) => <tr key={i}><td colSpan={2} style={{ padding: "7px 10px", borderTop: "1px solid var(--line)", fontWeight: 700 }}>{pick(o.name, o.name_bn || o.name)} · {o.phone}</td></tr>))}
      {sec(t("dmp.c"), <>{row(t("ob.f.name"), p.tenant.name)}{row(t("ob.f.phone"), p.tenant.phone)}{row(t("ob.fld.nid"), p.tenant.nid)}{row(t("ob.fld.father_name"), d.father_name)}{row(t("ob.fld.mother_name"), d.mother_name)}{row(t("ob.fld.profession"), d.profession)}{row(t("ob.fld.employer"), d.employer)}{row(t("ob.fld.permanent_address"), d.permanent_address)}{row(t("ob.fld.previous_address"), d.previous_address)}</>)}
      {sec(t("dmp.d"), (d.family ?? []).length ? d.family.map((f: any, i: number) => <tr key={i}><td colSpan={2} style={{ padding: "7px 10px", borderTop: "1px solid var(--line)", fontWeight: 700 }}>{f.name} · {f.relation} · {f.age}</td></tr>) : row("", t("dmp.none")))}
      {sec(t("dmp.e"), <>{row(t("ob.fld.emergency_name"), `${d.emergency_name} · ${d.emergency_phone}`)}{row(t("ob.fld.reference_name"), `${d.reference_name} · ${d.reference_phone}`)}</>)}
      {sec(t("dmp.g"), <>{row(t("ob.rent"), money(p.rent))}{row(t("ob.advance"), money(p.advance))}{row(t("ob.start"), fdate(p.start_date))}{row(t("ob.f.lease"), String(p.lease_months))}</>)}
      {sec(t("dmp.f"), p.docs.map((x) => row(t(`ob.doc.${x.kind}`), t("dmp.status_attached"))))}
      <div className="row between" style={{ marginTop: 44, gap: 16 }}>{[t("dmp.sign_tenant"), t("dmp.sign_owner"), t("dmp.sign_office")].map((s) => <div key={s} style={{ flex: 1, borderTop: "1.5px solid var(--text, #222)", paddingTop: 6, textAlign: "center" }} className="small">{s}</div>)}</div></div></div>);
}
