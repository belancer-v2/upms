"use client";
import { useEffect, useState } from "react";
import { Btn, Card, Field } from "@/components/ui";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

/** The website lead form (name, phone, building and a message). Sends the honeypot and the signed form token the API expects. */
export function LeadForm({ source, doneKey, errKey, msgKey, sendKey = "s2.contact.send" }: { source: string; doneKey: string; errKey: string; msgKey: string; sendKey?: string }) {
  const { t } = useT();
  const [f, setF] = useState({ name: "", phone: "", email: "", building: "", flats: "", city: "Dhaka", message: "", hp: "" });
  const [ft, setFt] = useState(""); const [state, setState] = useState<"idle" | "busy" | "done" | "err">("idle");
  useEffect(() => { api<{ ft: string }>("/public/form-token").then((d) => setFt(d.ft)).catch(() => {}); }, []);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setState("busy");
    try { await api("/public/leads", { body: { ...f, flats: Number(f.flats) || 0, source, ft } }); setState("done"); } catch { setState("err"); }
  };
  if (state === "done") return <Card><h3>{t(doneKey)}</h3></Card>;
  return (
    <Card><form onSubmit={submit}>
      <div className="grid g2"><Field label={t("site.demo.name")}><input className="input" required value={f.name} onChange={set("name")} /></Field><Field label={t("site.demo.phone")}><input className="input" required inputMode="tel" value={f.phone} onChange={set("phone")} /></Field></div>
      <Field label={t("site.demo.email")}><input className="input" type="email" value={f.email} onChange={set("email")} /></Field>
      <div className="grid g3"><Field label={t("site.demo.building")}><input className="input" value={f.building} onChange={set("building")} /></Field><Field label={t("site.demo.flats")}><input className="input" inputMode="numeric" value={f.flats} onChange={set("flats")} /></Field><Field label={t("site.demo.city")}><input className="input" value={f.city} onChange={set("city")} /></Field></div>
      <Field label={t(msgKey)}><textarea className="input" value={f.message} onChange={set("message")} /></Field>
      <div aria-hidden style={{ position: "absolute", left: "-9999px", height: 0, overflow: "hidden" }}><label>Website<input tabIndex={-1} autoComplete="off" value={f.hp} onChange={set("hp")} /></label></div>
      {state === "err" && <p className="error" role="alert">{t(errKey)}</p>}
      <Btn type="submit" size="lg" disabled={state === "busy"}>{t(sendKey)}</Btn>
    </form></Card>
  );
}
