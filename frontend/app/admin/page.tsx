"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  adminOverview, adminUsers, adminPayments, adminFlags, adminSetTier,
  adminReferrals, adminSetReferralRate, adminReferralPayouts, adminSetReferralPayoutStatus,
  type Overview, type AdminUser, type AdminPayment,
  type AdminReferral, type AdminReferralPayout,
} from "@/lib/admin";

const TIERS = ["free", "pro", "autonomous"];

const usd = (n: number | null | undefined) =>
  n == null ? "—" : `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const ratePct = (frac: number | null) => (frac == null ? "—" : `${Math.round(frac * 100)}%`);

export default function AdminPage() {
  const router = useRouter();
  const [tab, setTab] = useState<"overview" | "users" | "payments" | "referrals" | "flags">("overview");
  const [state, setState] = useState<"loading" | "ok" | "forbidden">("loading");
  const [ov, setOv] = useState<Overview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [payments, setPayments] = useState<AdminPayment[]>([]);
  const [referrals, setReferrals] = useState<AdminReferral[]>([]);
  const [refPayouts, setRefPayouts] = useState<AdminReferralPayout[]>([]);
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
    if (tab === "referrals") {
      adminReferrals().then(setReferrals).catch(() => {});
      adminReferralPayouts("pending").then(setRefPayouts).catch(() => {});
    }
    if (tab === "flags") adminFlags().then(setFlags).catch(() => {});
  }, [tab, state]);

  const changeTier = async (id: number, tier: string) => {
    await adminSetTier(id, tier);
    setUsers((us) => us.map((u) => (u.id === id ? { ...u, tier } : u)));
  };

  // rate приходит/уходит как доля (0.30–0.50); в UI редактируем в процентах.
  const changeRate = async (userId: number, rate: number | null) => {
    await adminSetReferralRate(userId, rate);
    setReferrals((rs) => rs.map((r) => (r.user_id === userId ? { ...r, rate_override: rate } : r)));
  };

  const changePayout = async (id: number, status: "paid" | "rejected") => {
    await adminSetReferralPayoutStatus(id, status);
    setRefPayouts((ps) => ps.filter((p) => p.id !== id));
  };

  if (state === "loading") return <Shell><p className="text-muted">Загрузка…</p></Shell>;
  if (state === "forbidden")
    return <Shell><p className="text-block">Нет доступа. Этот аккаунт не в списке администраторов (ADMIN_IDENTIFIERS).</p></Shell>;

  return (
    <Shell>
      <div className="mb-6 flex gap-2">
        {(["overview", "users", "payments", "referrals", "flags"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`rounded-lg px-3 py-1.5 text-sm ${tab === t ? "text-ink" : "text-muted"}`}
            style={tab === t ? { background: "rgba(139,92,246,.18)", border: "1px solid rgba(139,92,246,.4)" } : { background: "rgba(10,12,22,.5)", border: "1px solid var(--line)" }}>
            {{ overview: "Обзор", users: "Пользователи", payments: "Платежи", referrals: "Рефералы", flags: "Флаги" }[t]}
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

      {tab === "referrals" && (
        <div className="flex flex-col gap-6">
          {/* Referrers + individual rate override */}
          <div>
            <h2 className="mb-2 font-sg text-sm font-semibold text-muted">Рефереры</h2>
            <div className="glass overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-[11px] uppercase tracking-wider text-dim">
                  <th className="px-4 py-3">Пользователь</th><th className="px-4 py-3">Активных</th>
                  <th className="px-4 py-3">Заработано</th><th className="px-4 py-3">Баланс</th>
                  <th className="px-4 py-3">Ставка</th><th className="px-4 py-3">Individual (30–50%)</th>
                </tr></thead>
                <tbody>
                  {referrals.map((r) => (
                    <tr key={r.user_id} className="border-t align-middle" style={{ borderColor: "var(--line)" }}>
                      <td className="px-4 py-2.5 font-mono text-xs">{r.display}</td>
                      <td className="px-4 py-2.5">{r.referrals_active}</td>
                      <td className="px-4 py-2.5">{usd(r.earned_total_usd)}</td>
                      <td className="px-4 py-2.5">{usd(r.balance_usd)}</td>
                      <td className="px-4 py-2.5">
                        {r.rate_override == null
                          ? <span className="text-dim">авто</span>
                          : <span style={{ color: "#67e8f9" }}>{ratePct(r.rate_override)}</span>}
                      </td>
                      <td className="px-4 py-2.5"><RateEditor value={r.rate_override} onSave={(v) => changeRate(r.user_id, v)} /></td>
                    </tr>
                  ))}
                  {referrals.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-muted">Рефереров пока нет.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pending payouts */}
          <div>
            <h2 className="mb-2 font-sg text-sm font-semibold text-muted">Выплаты в обработке</h2>
            <div className="glass overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-[11px] uppercase tracking-wider text-dim">
                  <th className="px-4 py-3">ID</th><th className="px-4 py-3">Реферер</th><th className="px-4 py-3">$</th>
                  <th className="px-4 py-3">Адрес</th><th className="px-4 py-3">Дата</th><th className="px-4 py-3">Действие</th>
                </tr></thead>
                <tbody>
                  {refPayouts.map((p) => (
                    <tr key={p.id} className="border-t" style={{ borderColor: "var(--line)" }}>
                      <td className="px-4 py-2.5">{p.id}</td>
                      <td className="px-4 py-2.5 font-mono text-xs">{p.referrer_display}</td>
                      <td className="px-4 py-2.5 font-semibold">{usd(p.amount_usd)}</td>
                      <td className="px-4 py-2.5 max-w-[14rem] truncate font-mono text-xs text-muted">{p.address || "—"}</td>
                      <td className="px-4 py-2.5 text-xs text-muted">{new Date(p.created_at).toLocaleString()}</td>
                      <td className="px-4 py-2.5">
                        <div className="flex gap-2">
                          <button onClick={() => changePayout(p.id, "paid")}
                            className="rounded px-2.5 py-1 text-xs font-semibold" style={{ background: "rgba(52,211,153,.16)", color: "#34D399", border: "1px solid rgba(52,211,153,.4)" }}>
                            Выплачено
                          </button>
                          <button onClick={() => changePayout(p.id, "rejected")}
                            className="rounded px-2.5 py-1 text-xs font-semibold" style={{ background: "rgba(248,113,113,.14)", color: "#F87171", border: "1px solid rgba(248,113,113,.4)" }}>
                            Отклонить
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {refPayouts.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-muted">Нет выплат в обработке.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
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

// Инлайн-редактор индивидуальной ставки. В UI — проценты (30–50),
// наружу — доля (0.30–0.50) или null (сброс на авто-ставку).
function RateEditor({ value, onSave }: { value: number | null; onSave: (v: number | null) => Promise<void> }) {
  const [pctValue, setPctValue] = useState<string>(value == null ? "" : String(Math.round(value * 100)));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(false);

  const save = async () => {
    const n = Number(pctValue);
    if (!Number.isFinite(n) || n < 30 || n > 50) { setErr(true); return; }
    setErr(false); setBusy(true);
    try { await onSave(Math.round(n) / 100); } finally { setBusy(false); }
  };
  const clear = async () => {
    setErr(false); setBusy(true);
    try { await onSave(null); setPctValue(""); } finally { setBusy(false); }
  };

  return (
    <div className="flex items-center gap-2">
      <input
        type="number" min={30} max={50} step={1} value={pctValue}
        onChange={(e) => setPctValue(e.target.value)} placeholder="30–50"
        className="w-20 rounded bg-[#0A0C16] px-2 py-1 text-xs"
        style={{ border: `1px solid ${err ? "#F87171" : "var(--line)"}` }}
      />
      <span className="text-xs text-dim">%</span>
      <button onClick={save} disabled={busy}
        className="rounded px-2.5 py-1 text-xs font-semibold disabled:opacity-50"
        style={{ background: "rgba(139,92,246,.18)", color: "#c4b5fd", border: "1px solid rgba(139,92,246,.4)" }}>
        Задать
      </button>
      <button onClick={clear} disabled={busy}
        className="rounded px-2.5 py-1 text-xs text-muted hover:text-ink disabled:opacity-50"
        style={{ border: "1px solid var(--line)" }}>
        Сброс
      </button>
    </div>
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
