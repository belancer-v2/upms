"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Honeypot, useFormGuard } from "@/lib/formguard";
import { usePlans } from "@/components/site/Pricing";
import { Btn, Card, Field } from "@/components/ui";
import { api, money, store } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

function Form() {
  const { t, lang, pick } = useT(); const router = useRouter(); const sp = useSearchParams(); const { reload } = useAuth(); const d = usePlans();
  const [f, setF] = useState({ name: "", email: "", phone: "", password: "", building: "", address: "", city: "Dhaka", flats: "40", plan: sp.get("plan") ?? "standard" });
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false); const guard = useFormGuard();
  const [sent, setSent] = useState<{ email: string; link: string } | null>(null);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const flats = Number(f.flats) || 0;
  const band = flats <= 30 ? "S" : flats <= 80 ? "M" : flats <= 200 ? "L" : "XL";
  const plan = d?.plans.find((p) => p.key === f.plan);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const r = await api("/public/signup", { body: { ...f, flats, lang, ...guard.extra } });
      if (r.verification_required) { setSent({ email: r.email ?? f.email, link: r.demo_link ?? "" }); return; }     // the trial starts once the email is confirmed
      store.token = r.token; store.hint = true; await reload(); router.push("/app");
    }
    catch (x: any) { setErr(x?.message || t("site.signup.err")); } finally { setBusy(false); }
  };
  if (sent) return (
    <section className="section"><div className="wrap-x" style={{ maxWidth: 620 }}>
      <Card><h2>{t("authx.signup.check")}</h2><p style={{ marginTop: 8 }} role="status">{t("authx.signup.sent", { email: sent.email })}</p>
        {sent.link && <p className="hint" style={{ marginTop: 10 }}>{t("authx.signup.demo")}: <a href={sent.link.replace(/^https?:\/\/[^/]+/, "")}>{t("authx.verify.title")}</a></p>}</Card>
    </div></section>
  );
  return (
    <section className="section"><div className="wrap-x" style={{ maxWidth: 820 }}>
      <div className="sec-head"><div className="eyebrow">{t("site.nav.trial")}</div><h2>{t("site.signup.title")}</h2><p>{t("site.signup.sub")}</p></div>
      <form onSubmit={submit} className="stack">
        <Honeypot value={guard.hp} onChange={guard.setHp} />
        <Card><h3 style={{ marginBottom: 14 }}>{t("site.signup.you")}</h3>
          <div className="grid g2"><Field label={t("site.demo.name")}><input className="input" required value={f.name} onChange={set("name")} /></Field><Field label={t("site.demo.phone")}><input className="input" inputMode="tel" value={f.phone} onChange={set("phone")} /></Field></div>
          <div className="grid g2"><Field label={t("auth.email")}><input className="input" type="email" required value={f.email} onChange={set("email")} /></Field><Field label={t("site.signup.password")}><input className="input" type="password" minLength={8} required value={f.password} onChange={set("password")} /></Field></div></Card>
        <Card><h3 style={{ marginBottom: 14 }}>{t("site.signup.bld")}</h3>
          <div className="grid g2"><Field label={t("site.demo.building")}><input className="input" required value={f.building} onChange={set("building")} /></Field><Field label={t("site.signup.address")}><input className="input" value={f.address} onChange={set("address")} /></Field></div>
          <div className="grid g3"><Field label={t("site.demo.city")}><input className="input" value={f.city} onChange={set("city")} /></Field><Field label={t("site.demo.flats")}><input className="input" inputMode="numeric" required value={f.flats} onChange={set("flats")} /></Field>
            <Field label={t("site.signup.plan")}><select className="input" value={f.plan} onChange={set("plan")}>{d?.plans.map((p) => <option key={p.key} value={p.key}>{pick(p.name, p.name_bn)}</option>)}</select></Field></div>
          <p className="small muted">{t("site.signup.band")}: <b>{t(`site.price.band.${band}`)}</b>{plan && band !== "XL" && <> · {money(plan.monthly[band])} {t("site.price.per_month")} {t("site.price.trial") && ""}</>}</p></Card>
        {err && <p className="error" role="alert">{err}</p>}
        <div className="row wrap between"><Btn type="submit" size="lg" disabled={busy}>{t("site.signup.create")}</Btn><span className="small muted">{t("site.signup.have")} <Link href="/login">{t("site.nav.signin")}</Link></span></div>
        <p className="hint">{t("site.signup.after")}</p>
      </form>
    </div></section>
  );
}
export default function Signup() { return <Suspense><Form /></Suspense>; }
