"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Bar, Btn, Card, Chip } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { SETUP_STEPS, type SetupState } from "@/lib/setupDefaults";

/** Dashboard card for a building whose setup is not finished. A brand-new building is sent to the wizard once per browser session. */
export function SetupCard() {
  const { t } = useT(); const { prop, has } = useAuth(); const router = useRouter();
  const [s, setS] = useState<SetupState | null>(null);
  const manager = has("PROPERTY_ADMIN", "AGENCY_MANAGER");
  useEffect(() => {
    if (!prop || !manager) return;
    api<SetupState>("/setup").then((d) => {
      setS(d);
      let seen = false; try { seen = sessionStorage.getItem(`fw_setup_seen_${prop.id}`) === "1"; sessionStorage.setItem(`fw_setup_seen_${prop.id}`, "1"); } catch { /* private window */ }
      if (d.applicable && !d.completed && !d.dismissed && d.percent === 0 && !seen) router.replace("/app/setup");
    }).catch(() => {});
  }, [prop?.id, manager]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!s || !s.applicable || s.completed || s.dismissed) return null;
  const done = s.steps.filter((x) => x.state !== "todo").length;
  const hide = async () => { try { setS(await api<SetupState>("/setup/dismiss", { method: "POST", body: undefined })); } catch { /* keep showing */ } };
  return (
    <Card style={{ marginBottom: 18 }}>
      <div className="row between wrap" style={{ gap: 10 }}><div><h3>{t("su.card.title")}</h3><p className="muted small" style={{ margin: "4px 0 0" }}>{t("su.card.sub", { n: done, m: SETUP_STEPS.length })}</p></div>
        <div className="row wrap" style={{ gap: 8 }}><Link className="btn btn-primary btn-sm" href="/app/setup">{t("su.card.go")}</Link><Btn size="sm" variant="ghost" onClick={hide}>{t("su.card.hide")}</Btn></div></div>
      <div style={{ margin: "12px 0" }}><Bar pct={(done / SETUP_STEPS.length) * 100} spark /></div>
      <div className="row wrap" style={{ gap: 8 }}>{s.steps.map((x) => <Chip key={x.step} tone={x.state === "todo" ? "warn" : x.state === "skipped" ? "mute" : "ok"}>{x.state === "todo" ? "○" : "✓"} {t(`su.s.${x.step}`)}</Chip>)}</div>
    </Card>
  );
}
