"use client";
import { useRef, useState } from "react";
import { Avatar, authHeaders, refreshPhotos, type PersonKind } from "@/components/Avatar";
import { Btn } from "@/components/ui";
import { useT } from "@/lib/i18n";

const MAX = 2 * 1024 * 1024;

/** Photo picker for one person: checks type and size in the browser, then uploads. The server checks again. */
export function AvatarUploader({ kind, id, name, hasPhoto, ver, onChange }: { kind: PersonKind; id: number; name: string; hasPhoto: boolean; ver: number; onChange: (r: any) => void }) {
  const { t } = useT(); const ref = useRef<HTMLInputElement>(null); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const done = async (r: any) => { await refreshPhotos(); onChange(r); };
  const pick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; e.target.value = ""; setErr("");
    if (!f) return;
    if (!["image/jpeg", "image/png"].includes(f.type)) return setErr(t("prof.bad_type"));
    if (f.size > MAX) return setErr(t("prof.too_big"));
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", f);
      const res = await fetch(`/api/profiles/${kind}/${id}/photo`, { method: "POST", headers: authHeaders(), body: fd });
      if (!res.ok) { const j = await res.json().catch(() => ({})); throw new Error(res.status === 413 ? t("prof.too_big") : res.status === 422 ? t("prof.bad_type") : j.detail || res.statusText); }
      await done(await res.json());
    } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true); setErr("");
    try { const res = await fetch(`/api/profiles/${kind}/${id}/photo`, { method: "DELETE", headers: authHeaders() }); if (!res.ok) throw new Error(res.statusText); await done(await res.json()); }
    catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };
  return (
    <div className="row" style={{ gap: 16, alignItems: "center" }}>
      <Avatar kind={kind} id={id} name={name} size={84} ver={hasPhoto ? ver : 0} />
      <div className="stack" style={{ gap: 6 }}>
        <div className="row wrap">
          <Btn size="sm" variant="soft" disabled={busy} onClick={() => ref.current?.click()}>{hasPhoto ? t("prof.change") : t("prof.upload")}</Btn>
          {hasPhoto && <Btn size="sm" variant="ghost" disabled={busy} onClick={remove}>{t("prof.remove")}</Btn>}
        </div>
        <span className="hint">{t("prof.photo_hint")}</span>
        {err && <span className="error" role="alert">{err}</span>}
        <input ref={ref} type="file" accept="image/jpeg,image/png" hidden onChange={pick} aria-label={t("prof.photo")} />
      </div>
    </div>
  );
}
