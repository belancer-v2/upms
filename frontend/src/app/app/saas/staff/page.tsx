"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, Chip, DataTable, Field, Modal, PageHead, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { SAAS_LIST } from "@/lib/i18n/roles";

type S = { id: number; name: string; name_bn: string; email: string; phone: string; role: string; active: boolean };

export default function Staff() {
  const { t, pick } = useT(); const { saas, user } = useAuth(); const toast = useToast(); const sup = saas("SUPER_ADMIN");
  const [rows, setRows] = useState<S[]>([]); const [add, setAdd] = useState(false); const [f, setF] = useState({ name: "", email: "", role: "SAAS_USER", password: "" });
  const load = useCallback(() => api<S[]>("/saas/staff").then(setRows), []);
  useEffect(() => { load(); }, [load]);
  const create = async () => { try { await api("/saas/staff", { body: f }); setAdd(false); setF({ name: "", email: "", role: "SAAS_USER", password: "" }); load(); } catch (e: any) { toast.show(e.message); } };
  return (
    <>
      <PageHead title={t("saas.staff.title")} sub={t("saas.staff.sub")} actions={sup && <Btn onClick={() => setAdd(true)}>{t("saas.staff.add")}</Btn>} />
      <DataTable rows={rows} cols={[
        { key: "name", head: t("common.name"), render: (r) => <b>{pick(r.name, r.name_bn)}</b> }, { key: "email", head: t("auth.email") },
        { key: "role", head: t("saas.staff.role"), render: (r) => <Chip>{t(`role.${r.role}`)}</Chip> },
        { key: "active", head: t("common.status"), render: (r) => <Chip tone={r.active ? "ok" : "mute"}>{r.active ? t("saas.staff.active") : "–"}</Chip> },
        { key: "act", head: "", render: (r) => sup && r.id !== user?.id ? <Btn size="sm" variant="ghost" onClick={async () => { await api(`/saas/staff/${r.id}`, { method: "PATCH", body: { active: !r.active } }); load(); }}>{r.active ? t("saas.staff.deactivate") : t("saas.staff.activate")}</Btn> : null },
      ]} />
      {add && <Modal title={t("saas.staff.add")} onClose={() => setAdd(false)}>
        <Field label={t("common.name")}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label={t("auth.email")}><input className="input" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label={t("saas.staff.role")}><select className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{SAAS_LIST.map((r) => <option key={r} value={r}>{t(`role.${r}`)}</option>)}</select></Field>
        <Field label={t("saas.staff.pw")}><input className="input" type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <div className="row"><Btn onClick={create}>{t("common.save")}</Btn><Btn variant="ghost" onClick={() => setAdd(false)}>{t("common.cancel")}</Btn></div></Modal>}
      {toast.node}
    </>
  );
}
