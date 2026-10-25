"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Btn, Chip, Empty } from "@/components/ui";
import { ApiError, api, ftime, store } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type Row = { id: number; device: string; ip: string; created_at: string; last_used_at: string; current: boolean };

/** My profile: every device the account is signed in on, with sign-out for one device, for the others, or for all. */
export function SessionsPanel() {
  const { t } = useT(); const { logout } = useAuth();
  const [rows, setRows] = useState<Row[] | null>(null); const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  const load = useCallback(() => api<Row[]>("/me/sessions").then(setRows).catch((e: ApiError) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const out = async (id: number) => { try { await api(`/me/sessions/${id}`, { method: "DELETE" }); setMsg(t("authx.sessions.done")); load(); } catch (e) { setErr((e as ApiError).message); } };
  const others = async () => { try { await api("/me/sessions/revoke-all", { body: { keep_current: true } }); setMsg(t("authx.sessions.done")); load(); } catch (e) { setErr((e as ApiError).message); } };
  const all = async () => {
    if (!window.confirm(t("authx.sessions.confirm_all"))) return;
    try { await api("/me/sessions/revoke-all", { body: { keep_current: false } }); store.token = ""; store.hint = false; window.location.href = "/login"; } catch (e) { setErr((e as ApiError).message); }
  };
  return (
    <div>
      <div className="row between wrap" style={{ gap: 10, marginBottom: 4 }}>
        <h3>{t("authx.sessions.title")}</h3>
        <Link href="/change-password" className="btn btn-soft btn-sm">{t("authx.sessions.change")}</Link>
      </div>
      <p className="hint" style={{ marginBottom: 10 }}>{t("authx.sessions.sub")}</p>
      {err && <p className="error" role="alert">{err}</p>}
      {msg && <p className="hint" role="status">{msg}</p>}
      {rows === null ? <div className="empty">{t("common.loading")}</div> : rows.length === 0 ? <Empty /> : (
        <div>
          {rows.map((r) => (
            <div key={r.id} className="row between wrap" style={{ padding: "10px 0", borderTop: "1px solid var(--line)", gap: 10 }}>
              <div>
                <b>{r.device || "—"}</b> {r.current && <Chip tone="ok">{t("authx.sessions.this")}</Chip>}
                <div className="small muted">{t("authx.sessions.ip")}: {r.ip || "—"} · {t("authx.sessions.last")}: {ftime(r.last_used_at)}</div>
              </div>
              {r.current ? <Btn variant="ghost" size="sm" onClick={logout}>{t("auth.signout")}</Btn> : <Btn variant="ghost" size="sm" onClick={() => out(r.id)}>{t("authx.sessions.out")}</Btn>}
            </div>
          ))}
          <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
            {rows.length > 1 && <Btn variant="outline" size="sm" onClick={others}>{t("authx.sessions.others")}</Btn>}
            <Btn variant="danger" size="sm" onClick={all}>{t("authx.sessions.all")}</Btn>
          </div>
        </div>
      )}
    </div>
  );
}
