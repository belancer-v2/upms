"use client";
import { useEffect, useState } from "react";
import { Btn, Card, Field, PageHead, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type S = Record<string, any>;

export default function InvoiceSettings() {
  const { t } = useT(); const { saas } = useAuth(); const toast = useToast(); const can = saas("SUPER_ADMIN", "SAAS_ADMIN");
  const [s, setS] = useState<S | null>(null); const [next, setNext] = useState("");
  useEffect(() => { api("/saas/invoices-doc/settings").then((d: S) => { setS(d); setNext(String(d.next_number)); }); }, []);
  if (!s) return <p className="muted">{t("common.loading")}</p>;
  const set = (k: string, v: any) => setS({ ...s, [k]: v });
  const text = (k: string, label: string, props: Record<string, any> = {}) => <Field label={label}><input className="input" disabled={!can} value={s[k] ?? ""} onChange={(e) => set(k, e.target.value)} {...props} /></Field>;
  const area = (k: string, label: string) => <Field label={label}><textarea className="input" disabled={!can} rows={4} value={s[k] ?? ""} onChange={(e) => set(k, e.target.value)} /></Field>;
  const save = async () => {
    try {
      const keys = ["legal_name", "legal_name_bn", "address", "address_bn", "phone", "email", "bin_no", "tin", "bank_details", "bkash_merchant", "nagad_merchant", "logo_url", "footer_text", "footer_text_bn", "invoice_prefix", "credit_prefix"];
      const body: S = Object.fromEntries(keys.map((k) => [k, s[k]]));
      body.default_vat_pct = Number(s.default_vat_pct); body.fy_start_month = Number(s.fy_start_month);
      if (Number(next) !== s.next_number) body.next_number = Number(next);
      const d = await api("/saas/invoices-doc/settings", { method: "PUT", body }); setS(d); setNext(String(d.next_number)); toast.show(t("set.saved"));
    } catch (e: any) { toast.show(e.message); }
  };
  const pickLogo = (f?: File) => {
    if (!f) return;
    if (f.size > 200_000) { toast.show(t("set.logo_big")); return; }
    const r = new FileReader(); r.onload = () => set("logo_url", String(r.result)); r.readAsDataURL(f);
  };
  return (
    <>
      <PageHead helpKey="saas-invoices" title={t("set.title")} sub={can ? t("set.sub") : t("set.readonly")} actions={can ? <Btn onClick={save}>{t("common.save")}</Btn> : undefined} />
      <div className="grid g2" style={{ alignItems: "start" }}>
        <Card><h3>{t("set.company")}</h3><div className="stack" style={{ marginTop: 12 }}>
          {text("legal_name", t("set.legal_name"))}{text("legal_name_bn", t("set.legal_name_bn"))}{text("address", t("set.address"))}{text("address_bn", t("set.address_bn"))}
          <div className="grid g2">{text("phone", t("set.phone"))}{text("email", t("set.email"))}</div></div></Card>
        <Card><h3>{t("set.tax")}</h3><div className="stack" style={{ marginTop: 12 }}>
          {text("bin_no", t("set.bin_no"))}{text("tin", t("set.tin"))}
          <Field label={t("set.vat")}><input className="input" type="number" min="0" max="100" step="0.5" disabled={!can} value={s.default_vat_pct} onChange={(e) => set("default_vat_pct", e.target.value)} /></Field></div></Card>
        <Card><h3>{t("set.pay")}</h3><div className="stack" style={{ marginTop: 12 }}>
          {area("bank_details", t("set.bank_details"))}<div className="grid g2">{text("bkash_merchant", t("set.bkash"))}{text("nagad_merchant", t("set.nagad"))}</div></div></Card>
        <Card><h3>{t("set.look")}</h3><div className="stack" style={{ marginTop: 12 }}>
          <Field label={t("set.logo")}>
            <div className="row wrap" style={{ gap: 10 }}>{s.logo_url && /* eslint-disable-next-line @next/next/no-img-element */ <img src={s.logo_url} alt="" style={{ maxHeight: 48, maxWidth: 160, objectFit: "contain", background: "#fff", borderRadius: 6, padding: 4 }} />}
              {can && <><label className="btn btn-outline btn-sm" style={{ cursor: "pointer" }}>{t("set.logo_pick")}<input type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" hidden onChange={(e) => pickLogo(e.target.files?.[0])} /></label>
                {s.logo_url && <Btn size="sm" variant="ghost" onClick={() => set("logo_url", "")}>{t("set.logo_clear")}</Btn>}</>}</div></Field>
          {area("footer_text", t("set.footer"))}{area("footer_text_bn", t("set.footer_bn"))}
          <div className="grid g2">{text("invoice_prefix", t("set.prefix"), { maxLength: 8 })}{text("credit_prefix", t("set.cprefix"), { maxLength: 8 })}</div>
          <div className="grid g2">
            <Field label={t("set.fy")}><select className="input" disabled={!can} value={s.fy_start_month} onChange={(e) => set("fy_start_month", e.target.value)}>{Array.from({ length: 12 }, (_, i) => <option key={i} value={i + 1}>{new Date(2026, i, 1).toLocaleDateString("en-GB", { month: "long" })}</option>)}</select></Field>
            <Field label={t("set.next")} hint={t("set.next_hint")}><input className="input" type="number" min={s.next_number} disabled={!can} value={next} onChange={(e) => setNext(e.target.value)} /></Field></div>
          <p className="small muted">{t("set.preview", { n: s.next_invoice_preview })}</p></div></Card>
      </div>
      {toast.node}
    </>
  );
}
