"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  adminOverview, adminUsers, adminPayments, adminFlags, adminSetTier,
  type Overview, type AdminUser, type AdminPayment,
} from "@/lib/admin";

const TIERS = ["free", "pro", "autonomous"];

export default function AdminPage() {
  const router = useRouter();
  const [tab, setTab] = useState<"overview" | "users" | "payments" | "flags">("overview");
  const [state, setState] = useState<"loading" | "ok" | "forbidden">("loading");
  const [ov, setOv] = useState<Overview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [payments, setPayments] = useState<AdminPayment[]>([]);
  const [flags, setFlags] = useState<Record<string, unknown>>({});

  useEffect(() => {
    adminOverview()
      .then((o) => { setOv(o); setState("ok"); })
      .catch((e) => {
        if (String(e).includes("unauth")) router.push("/login");
        else setState("forbidden");
      });
  }, [router]);

  useEffect(() => {
    if (state !== "ok") return;
    if (tab === "users") adminUsers().then(setUsers).catch(() => {});
    if (tab === "payments") adminPayments().then(setPayments).catch(() => {});
    if (tab === "flags") adminFlags().then(setFlags).catch(() => {});
  }, [tab, state]);

  const changeTier = async (id: number, tier: string) => {
    await adminSetTier(id, tier);
    setUsers((us) => us.map((u) => (u.id === id ? { ...u, tier } : u)));
  };

  if (state === "loading") return <Shell><p className="text-muted">Загрузка…</p></Shell>;
  if (state === "forbidden")
    return <Shell><p className="text-block">Нет доступа. Этот аккаунт не в списке администраторов (ADMIN_IDENTIFIERS).</p></Shell>;

  return (
    <Shell>
      <div className="mb-6 flex gap-2">
        {(["overview", "users", "payments", "flags"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`rounded-lg px-3 py-1.5 text-sm ${tab === t ? "text-ink" : "text-muted"}`}
            style={tab === t ? { background: "rgba(139,92,246,.18)", border: "1px solid rgba(139,92,246,.4)" } : { background: "rgba(10,12,22,.5)", border: "1px solid var(--line)" }}>
            {{ overview: "Обзор", users: "Пользователи", payments: "Платежи", flags: "Флаги" }[t]}
          </button>
        ))}
      </div>

      {tab === "overview" && ov && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {([
            ["Пользователи", ov.users], ["Оплаты", ov.payments_paid], ["Токены", ov.tokens],
            ["Сигналы", ov.signals], ["Позиции откр.", ov.positions_open], ["Позиции закр.", ov.positions_closed],
            ["Статьи", ov.articles], ["Новости", ov.news],
          ] as const).map(([l, v]) => (
            <div key={l} className="glass p-4">
              <div className="text-xs text-muted">{l}</div>
              <div className="font-sg text-2xl font-bold">{v}</div>
            </div>
          ))}
          <div className="glass p-4"><div className="text-xs text-muted">Бумажный кэш</div><div className="font-sg text-2xl font-bold">${ov.paper_equity ?? "—"}</div></div>
          <div className="glass p-4"><div className="text-xs text-muted">Реализ. P&L</div><div className="font-sg text-2xl font-bold">${ov.paper_realized ?? "—"}</div></div>
        </div>
      )}

      {tab === "users" && (
        <div className="glass overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] uppercase tracking-wider text-dim">
              <th className="px-4 py-3">ID</th><th className="px-4 py-3">Вход</th><th className="px-4 py-3">Идентификатор</th>
              <th className="px-4 py-3">Тариф</th><th className="px-4 py-3">Выдать</th>
            </tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t" style={{ borderColor: "var(--line)" }}>
                  <td className="px-4 py-2.5">{u.id}</td>
                  <td className="px-4 py-2.5">{u.auth_method}</td>
                  <td className="px-4 py-2.5 font-mono text-xs">{u.email || u.subject.slice(0, 18)}</td>
                  <td className="px-4 py-2.5">{u.tier}</td>
                  <td className="px-4 py-2.5">
                    <select defaultValue={u.tier} onChange={(e) => changeTier(u.id, e.target.value)}
                      className="rounded bg-[#0A0C16] px-2 py-1 text-xs" style={{ border: "1px solid var(--line)" }}>
                      {TIERS.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </td>
                </tr>
              ))}
              {users.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-muted">Нет пользователей.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {tab === "payments" && (
        <div className="glass overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] uppercase tracking-wider text-dim">
              <th className="px-4 py-3">ID</th><th className="px-4 py-3">User</th><th className="px-4 py-3">Тариф</th>
              <th className="px-4 py-3">Статус</th><th className="px-4 py-3">$</th><th className="px-4 py-3">Дата</th>
            </tr></thead>
            <tbody>
              {payments.map((p) => (
                <tr key={p.id} className="border-t" style={{ borderColor: "var(--line)" }}>
                  <td className="px-4 py-2.5">{p.id}</td><td className="px-4 py-2.5">{p.user_id}</td>
                  <td className="px-4 py-2.5">{p.tier}</td><td className="px-4 py-2.5">{p.status}</td>
                  <td className="px-4 py-2.5">{p.amount_usd ?? "—"}</td>
                  <td className="px-4 py-2.5 text-xs text-muted">{new Date(p.created_at).toLocaleString()}</td>
                </tr>
              ))}
              {payments.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-muted">Платежей пока нет.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {tab === "flags" && (
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {Object.entries(flags).map(([k, v]) => (
            <div key={k} className="glass flex items-center justify-between px-4 py-3 text-sm">
              <span className="text-muted">{k}</span>
              <span className="font-mono" style={{ color: v === true ? "#7df3c0" : v === false ? "#fca5a5" : "#EAF0FF" }}>{String(v)}</span>
            </div>
          ))}
          <p className="col-span-full mt-1 text-xs text-dim">Флаги меняются через .env + рестарт контейнеров.</p>
        </div>
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen" style={{ background: "#05060B" }}>
      <div className="mx-auto max-w-5xl px-6 py-8">
        <header className="mb-6 flex items-center justify-between">
          <Link href="/radar" className="flex items-center gap-2 text-sm text-muted hover:text-ink">← В приложение</Link>
          <h1 className="font-sg text-lg font-bold">Админ-панель</h1>
        </header>
        {children}
      </div>
    </main>
  );
}
