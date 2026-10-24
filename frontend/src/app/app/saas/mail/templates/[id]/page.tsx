"use client";
import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { Block, EmailFrame } from "@/components/mailbits";
import { Btn, Card, Chip, Field, PageHead, Tabs, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

const B = "/saas/mail";
type Tpl = { id: number; key: string; name: string; name_bn: string; kind: string; subject_en: string; subject_bn: string; blocks_en: Block[]; blocks_bn: Block[] };
const TYPES: Block["type"][] = ["heading", "paragraph", "button", "image", "divider", "footer"];
const VARS = ["name", "building", "plan", "trial_days_left", "link"];

export default function TemplateEditor({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params); const { t } = useT(); const toast = useToast();
  const [tpl, setTpl] = useState<Tpl | null>(null); const [lang, setLang] = useState<"en" | "bn">("en");
  const [theme, setTheme] = useState<"light" | "dark">("light"); const [mobile, setMobile] = useState(false); const [view, setView] = useState<"html" | "text">("html");
  const [prev, setPrev] = useState<{ html: string; text: string; subject: string } | null>(null); const [dirty, setDirty] = useState(false);
  useEffect(() => { api<Tpl>(`${B}/templates/${id}`).then(setTpl).catch(() => toast.show(t("mail.ed.nope"))); /* eslint-disable-next-line */ }, [id]);
  const blocks = tpl ? (lang === "en" ? tpl.blocks_en : tpl.blocks_bn) : [];
  const subject = tpl ? (lang === "en" ? tpl.subject_en : tpl.subject_bn) : "";
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => {
    if (!tpl) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => { api(`${B}/templates/${id}/preview`, { body: { lang, theme, subject, blocks, kind: tpl.kind } }).then(setPrev).catch(() => {}); }, 300);
    return () => clearTimeout(timer.current);
    // eslint-disable-next-line
  }, [tpl, lang, theme]);
  if (!tpl) return <>{toast.node}</>;
  const setBlocks = (b: Block[]) => { setTpl({ ...tpl, [lang === "en" ? "blocks_en" : "blocks_bn"]: b }); setDirty(true); };
  const setSubject = (s: string) => { setTpl({ ...tpl, [lang === "en" ? "subject_en" : "subject_bn"]: s }); setDirty(true); };
  const upd = (i: number, patch: Partial<Block>) => setBlocks(blocks.map((b, k) => (k === i ? { ...b, ...patch } : b)));
  const move = (i: number, d: number) => { const j = i + d; if (j < 0 || j >= blocks.length) return; const c = [...blocks]; [c[i], c[j]] = [c[j], c[i]]; setBlocks(c); };
  const add = (type: Block["type"]) => setBlocks([...blocks, type === "divider" ? { type } : { type, text: "", label: "", url: type === "button" ? "{{link}}" : "", alt: "" }]);
  const save = async () => {
    try { const r = await api<Tpl>(`${B}/templates/${id}`, { method: "PUT", body: { key: tpl.key, name: tpl.name, name_bn: tpl.name_bn, kind: tpl.kind, subject_en: tpl.subject_en, subject_bn: tpl.subject_bn, blocks_en: tpl.blocks_en, blocks_bn: tpl.blocks_bn } }); setTpl(r); setDirty(false); toast.show(t("saas.toast.saved")); }
    catch (e: any) { toast.show(e.message); }
  };
  const test = async () => { try { await api(`${B}/templates/${id}/test`, { body: { lang } }); toast.show(t("mail.ed.tested")); } catch (e: any) { toast.show(e.message); } };
  return (
    <>
      <PageHead title={lang === "bn" && tpl.name_bn ? tpl.name_bn : tpl.name} sub={t("mail.ed.sub")} eyebrow={t(`mail.kind.${tpl.kind}`)}
        actions={<><Link href="/app/saas/mail" className="btn btn-ghost">{t("common.back")}</Link><Btn variant="soft" onClick={test} disabled={dirty}>{t("mail.ed.test")}</Btn><Btn onClick={save} disabled={!dirty}>{t("common.save")}</Btn></>} />
      <div className="row between wrap" style={{ marginBottom: 14 }}>
        <Tabs value={lang} onChange={setLang} items={[{ id: "en", label: "English" }, { id: "bn", label: "বাংলা" }]} />
        {dirty && <Chip tone="warn">{t("mail.ed.unsaved")}</Chip>}
      </div>
      <div className="grid g2" style={{ alignItems: "start", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))" }}>
        <Card>
          <Field label={t("mail.subject")}><input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} /></Field>
          <p className="small muted">{t("mail.ed.vars")} {VARS.map((v) => <code key={v} style={{ marginRight: 6 }}>{`{{${v}}}`}</code>)}</p>
          <div className="col" style={{ gap: 12 }}>
            {blocks.map((b, i) => (
              <div key={i} style={{ border: "1.5px solid var(--line)", borderRadius: 14, padding: 12, background: "var(--surface2)" }}>
                <div className="row between" style={{ marginBottom: 8 }}><b className="small">{t(`mail.blk.${b.type}`)}</b>
                  <div className="row" style={{ gap: 4 }}><Btn size="sm" variant="ghost" onClick={() => move(i, -1)} disabled={i === 0} aria-label={t("mail.ed.up")}>↑</Btn><Btn size="sm" variant="ghost" onClick={() => move(i, 1)} disabled={i === blocks.length - 1} aria-label={t("mail.ed.down")}>↓</Btn><Btn size="sm" variant="ghost" onClick={() => setBlocks(blocks.filter((_, k) => k !== i))} aria-label={t("common.delete")}>✕</Btn></div></div>
                {(b.type === "heading" || b.type === "footer") && <input className="input" value={b.text ?? ""} onChange={(e) => upd(i, { text: e.target.value })} aria-label={t(`mail.blk.${b.type}`)} />}
                {b.type === "paragraph" && <textarea className="input" rows={4} value={b.text ?? ""} onChange={(e) => upd(i, { text: e.target.value })} aria-label={t("mail.blk.paragraph")} />}
                {b.type === "button" && <div className="col" style={{ gap: 8 }}><input className="input" placeholder={t("mail.blk.label")} value={b.label ?? ""} onChange={(e) => upd(i, { label: e.target.value })} /><input className="input" placeholder="https://… / {{link}}" value={b.url ?? ""} onChange={(e) => upd(i, { url: e.target.value })} /></div>}
                {b.type === "image" && <div className="col" style={{ gap: 8 }}><input className="input" placeholder="https://…" value={b.url ?? ""} onChange={(e) => upd(i, { url: e.target.value })} /><input className="input" placeholder={t("mail.blk.alt")} value={b.alt ?? ""} onChange={(e) => upd(i, { alt: e.target.value })} /></div>}
                {b.type === "divider" && <hr className="fw-ln" style={{ border: 0, borderTop: "1px solid var(--line)" }} />}
              </div>
            ))}
            {!blocks.length && <div className="empty">{t("mail.ed.empty")}</div>}
          </div>
          <div className="row wrap" style={{ marginTop: 14 }}>{TYPES.map((x) => <Btn key={x} size="sm" variant="outline" onClick={() => add(x)}>+ {t(`mail.blk.${x}`)}</Btn>)}</div>
          <p className="small muted" style={{ marginTop: 12 }}>{t("mail.ed.legal")}</p>
        </Card>
        <div style={{ position: "sticky", top: 12 }}>
          <div className="row between wrap" style={{ marginBottom: 10 }}>
            <div className="seg" role="group" aria-label={t("mail.ed.theme")}><button className={theme === "light" ? "on" : ""} onClick={() => setTheme("light")}>{t("mail.ed.light")}</button><button className={theme === "dark" ? "on" : ""} onClick={() => setTheme("dark")}>{t("mail.ed.dark")}</button></div>
            <div className="seg" role="group" aria-label={t("mail.ed.device")}><button className={!mobile ? "on" : ""} onClick={() => setMobile(false)}>{t("mail.ed.desktop")}</button><button className={mobile ? "on" : ""} onClick={() => setMobile(true)}>{t("mail.ed.mobile")}</button></div>
            <div className="seg" role="group"><button className={view === "html" ? "on" : ""} onClick={() => setView("html")}>{t("mail.ed.html")}</button><button className={view === "text" ? "on" : ""} onClick={() => setView("text")}>{t("mail.ed.text")}</button></div>
          </div>
          {prev && <p className="small" style={{ margin: "0 0 8px" }}><b>{t("mail.subject")}:</b> {prev.subject}</p>}
          {prev ? (view === "html" ? <EmailFrame html={prev.html} mobile={mobile} height={620} /> : <Card><pre style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 13, fontFamily: "inherit" }}>{prev.text}</pre></Card>) : <div className="empty">{t("common.loading")}</div>}
        </div>
      </div>
      {toast.node}
    </>
  );
}
