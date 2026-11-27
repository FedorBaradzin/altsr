"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/auth";
import {
  fetchReferralMe, requestPayout,
  type ReferralMe, type PayoutStatus,
} from "@/lib/referral";
import { useLang } from "@/components/LangProvider";
import LangSwitcher from "@/components/LangSwitcher";

const usd = (n: number) =>
  `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const pct = (frac: number) => `${Math.round(frac * 100)}%`;

// Статичная таблица уровней (как на лендинге). Проценты — информационно.
const TIER_ROWS: { tier: string; referrals: string; rate: string }[] = [
  { tier: "Starter", referrals: "1–4", rate: "10%" },
  { tier: "Bronze", referrals: "5–9", rate: "15%" },
  { tier: "Silver", referrals: "10–24", rate: "20%" },
  { tier: "Gold", referrals: "25+", rate: "30%" },
  { tier: "Individual", referrals: "—", rate: "30–50%" },
];

// Коды ошибок бэкенда → ключи сообщений (на текущем языке).
function payoutErrorKey(msg: string): string {
  const m = msg.toLowerCase();
  if (m.includes("balance")) return "ref.payout.noBalance";
  if (m.includes("pending")) return "ref.payout.hasPending";
  return "ref.payout.failed";
}

export default function ReferralPage() {
  const router = useRouter();
  const { t, lang } = useLang();
  const [state, setState] = useState<"loading" | "ok" | "anon" | "error">("loading");
  const [data, setData] = useState<ReferralMe | null>(null);
  const [copied, setCopied] = useState(false);
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const load = useCallback(() => {
    fetchReferralMe()
      .then((d) => { setData(d); setState("ok"); })
      .catch((e) => {
        if (String(e).includes("unauth")) setState("anon");
        else setState("error");
      });
  }, []);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    load();
  }, [router, load]);

  const fmtDate = (iso: string | null) =>
    iso
      ? new Date(iso).toLocaleDateString(lang === "ru" ? "ru-RU" : "en-US", {
          year: "numeric", month: "short", day: "numeric",
        })
      : "—";

  const statusLabel = (s: PayoutStatus) =>
    t(`ref.payout.status.${s}` as const) || s;
  const statusColor = (s: PayoutStatus) =>
    s === "paid" ? "#34D399" : s === "rejected" ? "#F87171" : "#FBBF24";

  const copyLink = async () => {
    if (!data?.link) return;
    try {
      await navigator.clipboard.writeText(data.link);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard недоступен — ссылка видна в поле, можно скопировать вручную */
    }
  };

  const submitPayout = async () => {
    setBusy(true); setNotice(null);
    try {
      await requestPayout(address.trim() || undefined);
      setNotice({ kind: "ok", text: t("ref.payout.created") });
      setAddress("");
      load();
    } catch (e) {
      setNotice({ kind: "err", text: t(payoutErrorKey((e as Error)?.message || "")) });
    } finally {
      setBusy(false);
    }
  };

  const canPayout = !!data && data.balance_usd > 0 && !data.payouts.some((p) => p.status === "pending");

  return (
    <main className="min-h-screen" style={{ background: "radial-gradient(60% 40% at 80% 0%,rgba(139,92,246,.08),transparent 60%),#05060B" }}>
      <div className="mx-auto max-w-3xl px-6 py-14">
        <nav className="mb-8 flex items-center justify-between text-sm">
          <Link href="/account" className="flex items-center gap-2 text-muted hover:text-ink">← {t("account.title")}</Link>
          <LangSwitcher />
        </nav>

        <h1 className="mb-2 font-sg text-3xl font-bold">{t("ref.title")}</h1>
        <p className="mb-10 max-w-xl text-muted">{t("ref.sub")}</p>

        {state === "loading" && <p className="text-muted">{t("ref.loading")}</p>}

        {state === "anon" && (
          <div className="glass p-6">
            <p className="mb-4 text-sm text-muted">{t("ref.sessionExpired")}</p>
            <Link href="/login" className="glass inline-block rounded-xl px-4 py-2.5 text-sm">{t("nav.login")}</Link>
          </div>
        )}

        {state === "error" && (
          <div className="glass p-6"><p className="text-sm text-block">{t("ref.error")}</p></div>
        )}

        {state === "ok" && data && (
          <div className="flex flex-col gap-5">
            {/* Referral link */}
            <section className="glass p-6">
              <div className="mb-2 text-xs uppercase tracking-wider text-dim">{t("ref.yourLink")}</div>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <input
                  readOnly
                  value={data.link}
                  onFocus={(e) => e.currentTarget.select()}
                  className="min-w-0 flex-1 truncate rounded-xl bg-[#0A0C16] px-4 py-2.5 font-mono text-xs text-[#cdd6e6]"
                  style={{ border: "1px solid var(--line)" }}
                />
                <button
                  onClick={copyLink}
                  className="shrink-0 rounded-xl px-4 py-2.5 text-sm font-semibold text-[#06231c]"
                  style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}
                >
                  {copied ? t("ref.copied") : t("ref.copy")}
                </button>
              </div>
              <div className="mt-4 flex flex-wrap gap-6 text-sm">
                <div>
                  <span className="text-muted">{t("ref.tier")}: </span>
                  <span className="font-sg font-semibold capitalize">{data.tier}</span>
                </div>
                <div>
                  <span className="text-muted">{t("ref.rate")}: </span>
                  <span className="font-sg font-semibold" style={{ color: "#22D3EE" }}>{pct(data.rate)}</span>
                </div>
              </div>
            </section>

            {/* Stats */}
            <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {([
                [t("ref.stat.total"), String(data.referrals_total)],
                [t("ref.stat.active"), String(data.referrals_active)],
                [t("ref.stat.earned"), usd(data.earned_total_usd)],
                [t("ref.stat.balance"), usd(data.balance_usd)],
              ] as const).map(([label, value]) => (
                <div key={label} className="glass p-4">
                  <div className="text-xs text-muted">{label}</div>
                  <div className="mt-1 font-sg text-2xl font-bold">{value}</div>
                </div>
              ))}
            </section>

            {/* Tiers reference */}
            <section className="glass overflow-hidden">
              <div className="px-6 pt-5 text-xs uppercase tracking-wider text-dim">{t("ref.tiers")}</div>
              <div className="overflow-x-auto">
                <table className="mt-3 w-full text-sm">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wider text-dim">
                      <th className="px-6 py-2">{t("ref.tiers.tier")}</th>
                      <th className="px-6 py-2">{t("ref.tiers.referrals")}</th>
                      <th className="px-6 py-2 text-right">{t("ref.tiers.rate")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {TIER_ROWS.map((r) => {
                      const current = r.tier.toLowerCase() === data.tier.toLowerCase();
                      return (
                        <tr key={r.tier} className="border-t" style={{ borderColor: "var(--line)" }}>
                          <td className="px-6 py-2.5">
                            <span className={current ? "font-semibold text-ink" : ""}>{r.tier}</span>
                            {current && (
                              <span className="ml-2 rounded-full px-2 py-0.5 text-[10px]" style={{ background: "rgba(34,211,238,.15)", color: "#67e8f9" }}>
                                {t("ref.rate")}
                              </span>
                            )}
                          </td>
                          <td className="px-6 py-2.5 text-muted">{r.referrals}</td>
                          <td className="px-6 py-2.5 text-right font-sg font-semibold">{r.rate}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="px-6 pb-5 pt-3 text-xs text-dim">{t("ref.tiers.individualNote")}</p>
            </section>

            {/* Recent earnings */}
            <section className="glass p-6">
              <div className="mb-3 text-xs uppercase tracking-wider text-dim">{t("ref.earnings")}</div>
              {data.earnings.length === 0 ? (
                <p className="text-sm text-muted">{t("ref.earnings.empty")}</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-[11px] uppercase tracking-wider text-dim">
                        <th className="py-2">{t("ref.earnings.amount")}</th>
                        <th className="py-2">{t("ref.earnings.rate")}</th>
                        <th className="py-2 text-right">{t("ref.earnings.date")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.earnings.map((e, i) => (
                        <tr key={i} className="border-t" style={{ borderColor: "var(--line)" }}>
                          <td className="py-2.5 font-semibold" style={{ color: "#34D399" }}>{usd(e.amount_usd)}</td>
                          <td className="py-2.5 text-muted">{pct(e.rate)}</td>
                          <td className="py-2.5 text-right text-xs text-muted">{fmtDate(e.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            {/* Payouts */}
            <section className="glass p-6">
              <div className="mb-3 text-xs uppercase tracking-wider text-dim">{t("ref.payout")}</div>

              <div className="mb-4 flex flex-wrap items-center justify-between gap-2 text-sm">
                <span className="text-muted">{t("ref.payout.available")}</span>
                <span className="font-sg text-xl font-bold">{usd(data.balance_usd)}</span>
              </div>

              <label className="mb-1 block text-xs text-muted" htmlFor="payout-address">{t("ref.payout.address")}</label>
              <input
                id="payout-address"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder={t("ref.payout.addressPh")}
                className="mb-3 w-full rounded-xl bg-[#0A0C16] px-4 py-2.5 font-mono text-xs text-[#cdd6e6] placeholder:text-dim"
                style={{ border: "1px solid var(--line)" }}
              />

              <button
                onClick={submitPayout}
                disabled={busy || !canPayout}
                className="rounded-xl px-5 py-2.5 text-sm font-semibold text-[#06231c] disabled:opacity-50"
                style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}
              >
                {busy ? t("ref.payout.requesting") : t("ref.payout.request")}
              </button>

              {!canPayout && data.balance_usd <= 0 && (
                <p className="mt-2 text-xs text-dim">{t("ref.payout.noBalance")}</p>
              )}
              {notice && (
                <p className="mt-3 text-sm" style={{ color: notice.kind === "ok" ? "#34D399" : "#F87171" }}>{notice.text}</p>
              )}

              {/* Payout history */}
              <div className="mt-6">
                <div className="mb-2 text-xs uppercase tracking-wider text-dim">{t("ref.payout.history")}</div>
                {data.payouts.length === 0 ? (
                  <p className="text-sm text-muted">{t("ref.payout.empty")}</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <tbody>
                        {data.payouts.map((p) => (
                          <tr key={p.id} className="border-t" style={{ borderColor: "var(--line)" }}>
                            <td className="py-2.5 font-semibold">{usd(p.amount_usd)}</td>
                            <td className="py-2.5">
                              <span className="rounded-md px-2 py-0.5 text-xs font-semibold"
                                style={{ background: `${statusColor(p.status)}22`, color: statusColor(p.status) }}>
                                {statusLabel(p.status)}
                              </span>
                            </td>
                            <td className="py-2.5 text-right text-xs text-muted">
                              {fmtDate(p.paid_at || p.created_at)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </section>
          </div>
        )}

        <p className="mt-10 text-xs leading-relaxed text-dim">{t("ref.disclaimer")}</p>
      </div>
    </main>
  );
}
