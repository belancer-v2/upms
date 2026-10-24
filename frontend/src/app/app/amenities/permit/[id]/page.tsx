"use client";
import { use, useEffect, useState } from "react";
import { Btn, Card } from "@/components/ui";
import { api, fdate } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type P = { permit_no: string; building: string; building_bn: string; address: string; amenity: string; amenity_bn: string; on_date: string; slot: string; hours: number[]; ext_hours: number; unit: string; holder: string; holder_bn: string;
  party: string; contact: string; purpose: string; guests: number; capacity: number; catering: boolean; rules: string; rules_bn: string; status: string };
const hh = (h: number) => `${String(h).padStart(2, "0")}:00`;

export default function Permit({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params); const { t, pick, lang, setLang } = useT(); const { prop } = useAuth(); const [p, setP] = useState<P | null>(null); const [err, setErr] = useState("");
  useEffect(() => { api<P>(`/amenities/bookings/${id}/permit`).then(setP).catch((e) => setErr(e.message)); }, [id, prop?.id]);
  if (err) return <p className="error">{err}</p>; if (!p) return <p className="muted">{t("common.loading")}</p>;
  const row = (k: string, v: React.ReactNode) => <div className="row between" style={{ padding: "9px 0", borderTop: "1px solid var(--line)", gap: 12 }}><span className="muted">{k}</span><b style={{ textAlign: "right" }}>{v}</b></div>;
  const end = p.hours[1] + p.ext_hours;
  return (<div style={{ maxWidth: 620, margin: "0 auto" }}>
    <div className="row no-print" style={{ marginBottom: 12, gap: 8 }}><Btn onClick={() => window.print()}>{t("common.print")}</Btn><Btn variant="outline" onClick={() => setLang(lang === "bn" ? "en" : "bn")}>{lang === "bn" ? "English" : "বাংলা"}</Btn></div>
    <Card>
      <div className="row between"><div><div className="eyebrow">{t("am.permit.title")}</div><h2 style={{ margin: "4px 0" }}>{pick(p.building, p.building_bn || p.building)}</h2><span className="small muted">{p.address}</span></div><b style={{ textAlign: "right" }}>{p.permit_no}</b></div>
      <div style={{ margin: "20px 0 6px", fontSize: 30, fontWeight: 800 }}>{pick(p.amenity, p.amenity_bn || p.amenity)}</div>
      <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 10 }}>{fdate(p.on_date)} · {hh(p.hours[0])}–{hh(end)}</div>
      {row(t("am.permit.holder"), `${pick(p.holder, p.holder_bn || p.holder)} · ${t("am.flat", { n: p.unit })}`)}
      {row(t("am.f.contact"), p.contact)}{row(t("am.f.purpose"), t(`am.purpose.${p.purpose}`))}
      {row(t("am.f.slot"), `${t(`am.slot.${p.slot}`)}${p.ext_hours ? ` + ${t("am.permit.ext", { n: p.ext_hours })}` : ""}`)}
      {row(t("am.permit.guests"), t("am.permit.max", { n: p.guests, m: p.capacity }))}
      {row(t("am.f.catering"), p.catering ? t("common.yes") : t("common.no"))}
      {(pick(p.rules, p.rules_bn)) && <div style={{ marginTop: 14 }}><b>{t("am.rules")}</b><p style={{ whiteSpace: "pre-wrap", margin: "4px 0 0" }}>{pick(p.rules, p.rules_bn)}</p></div>}
      <div style={{ marginTop: 16, padding: 12, border: "1px dashed var(--line)", borderRadius: 12 }}><b>{t("am.permit.guard")}</b>
        <div className="small" style={{ marginTop: 6 }}>☐ {t("am.permit.c1")}<br />☐ {t("am.permit.c2")}<br />☐ {t("am.permit.c3")}</div></div>
      <div className="row between" style={{ marginTop: 34 }}><span className="small muted" style={{ borderTop: "1px solid var(--text)", paddingTop: 4, minWidth: 160 }}>{t("am.permit.sig_host")}</span><span className="small muted" style={{ borderTop: "1px solid var(--text)", paddingTop: 4, minWidth: 160, textAlign: "right" }}>{t("am.permit.sig_guard")}</span></div>
    </Card></div>);
}
