"use client";
import { useState } from "react";
import { Btn, Card, Field } from "@/components/ui";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Demo() {
  const { t } = useT();
  const [f, setF] = useState({ name: "", phone: "", email: "", building: "", flats: "", city: "Dhaka", message: "" });
  const [state, setState] = useState<"idle" | "busy" | "done" | "err">("idle");
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setState("busy");
    try { await api("/public/leads", { body: { ...f, flats: Number(f.flats) || 0, source: "demo" } }); setState("done"); } catch { setState("err"); }
  };
  return (
    <section className="section"><div className="wrap-x" style={{ maxWidth: 720 }}>
      <div className="sec-head"><div className="eyebrow">{t("site.nav.demo")}</div><h2>{t("site.demo.title")}</h2><p>{t("site.demo.sub")}</p></div>
      {state === "done" ? <Card><h2>{t("site.demo.done")}</h2></Card> : (
        <Card><form onSubmit={submit}>
          <div className="grid g2"><Field label={t("site.demo.name")}><input className="input" required value={f.name} onChange={set("name")} /></Field><Field label={t("site.demo.phone")}><input className="input" required inputMode="tel" value={f.phone} onChange={set("phone")} /></Field></div>
          <Field label={t("site.demo.email")}><input className="input" type="email" value={f.email} onChange={set("email")} /></Field>
          <div className="grid g3"><Field label={t("site.demo.building")}><input className="input" value={f.building} onChange={set("building")} /></Field><Field label={t("site.demo.flats")}><input className="input" inputMode="numeric" value={f.flats} onChange={set("flats")} /></Field><Field label={t("site.demo.city")}><input className="input" value={f.city} onChange={set("city")} /></Field></div>
          <Field label={t("site.demo.msg")}><textarea className="input" value={f.message} onChange={set("message")} /></Field>
          {state === "err" && <p className="error">{t("site.demo.err")}</p>}
          <Btn type="submit" size="lg" disabled={state === "busy"}>{t("site.demo.send")}</Btn>
        </form></Card>)}
    </div></section>
  );
}
