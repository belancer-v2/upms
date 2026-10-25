"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Btn } from "@/components/ui";
import { api, fdate } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type P = { id: number; name: string; name_bn: string; shift_ids: number[]; headcount: number };
type Sh = { id: number; name: string; name_bn: string; start: string; end: string };
type S = { id: number; date: string; post_id: number; shift_id: number; name: string; name_bn: string; agency: string; agency_bn: string; status: string; substitute: boolean };
type R = { start: string; end: string; days: string[]; posts: P[]; shifts: Sh[]; slots: S[]; building: string; building_bn: string };

function Sheet() {
  const { t, pick, lang } = useT(); const { prop } = useAuth(); const q = useSearchParams().get("start") ?? ""; const [r, setR] = useState<R | null>(null); const [err, setErr] = useState("");
  useEffect(() => { api<R>(`/agency/roster${q ? `?start=${q}` : ""}`).then(setR).catch((e) => setErr(e.message)); }, [q, prop?.id]);
  if (err) return <p className="error">{err}</p>; if (!r) return <p className="muted">{t("common.loading")}</p>;
  const day = (iso: string) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", timeZone: "UTC" });
  return (<div style={{ maxWidth: 1100, margin: "0 auto" }}>
    <div className="row between no-print" style={{ marginBottom: 12 }}><span /><Btn onClick={() => window.print()}>{t("common.print")}</Btn></div>
    <h1 style={{ textAlign: "center", margin: "0 0 4px" }}>{pick(r.building, r.building_bn || r.building)}</h1>
    <h2 style={{ textAlign: "center", margin: "0 0 4px" }}>{t("ag.print.title")}</h2>
    <p style={{ textAlign: "center" }} className="muted">{fdate(r.start)} – {fdate(r.end)}</p>
    <div className="table-wrap"><table className="t" style={{ minWidth: 820 }}>
      <thead><tr><th>{t("ag.post")} / {t("ag.shift")}</th>{r.days.map((d) => <th key={d}>{day(d)}</th>)}</tr></thead>
      <tbody>{r.posts.flatMap((p) => r.shifts.filter((s) => !p.shift_ids.length || p.shift_ids.includes(s.id)).map((s) => (
        <tr key={`${p.id}-${s.id}`}><td><b>{pick(p.name, p.name_bn || p.name)}</b><br /><span className="small muted">{pick(s.name, s.name_bn || s.name)} · {s.start}–{s.end}</span></td>
          {r.days.map((d) => <td key={d} style={{ verticalAlign: "top" }}>{r.slots.filter((x) => x.post_id === p.id && x.shift_id === s.id && x.date === d && x.status !== "absent" && x.status !== "leave").map((x) => <div key={x.id}><b>{pick(x.name, x.name_bn || x.name)}</b>{x.substitute ? ` (${t("ag.substitute")})` : ""}{x.agency && <div className="tiny muted">{pick(x.agency, x.agency_bn || x.agency)}</div>}</div>)}</td>)}</tr>)))}</tbody></table></div>
    <p className="small muted" style={{ marginTop: 12 }}>{t("ag.print.footer")}</p>
  </div>);
}

export default function RosterPrint() { return <Suspense fallback={null}><Sheet /></Suspense>; }
