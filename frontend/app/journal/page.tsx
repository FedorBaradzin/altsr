"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchWinningTrades, type JournalTrade } from "@/lib/api";
import LangSwitcher from "@/components/LangSwitcher";
import { useLang } from "@/components/LangProvider";

function heldLabel(opened: string, closed: string | null): string {
  if (!closed) return "—";
  const mins = Math.max(0, Math.round((+new Date(closed) - +new Date(opened)) / 60000));
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  return `${h}h ${mins % 60}m`;
}

export default function JournalPage() {
  const { t } = useLang();
  const [items, setItems] = useState<JournalTrade[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetchWinningTrades(100)
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoaded(true));
  }, []);

  return (
    <main
      className="mx-auto max-w-5xl px-5 py-10"
      style={{ minHeight: "100vh", background: "radial-gradient(60% 40% at 80% 0%,rgba(52,211,153,.08),transparent 60%),#05060B" }}
    >
      <nav className="mb-6 flex items-center justify-between text-sm text-muted">
        <Link href="/radar" className="hover:underline">← ALTSR</Link>
        <LangSwitcher />
      </nav>

      <div className="mb-8 flex items-end justify-between gap-4">
        <div>
          <h1 className="mb-1 font-sg text-2xl font-bold">📖 {t("journal.title")}</h1>
          <p className="max-w-2xl text-sm text-muted">{t("journal.sub")}</p>
        </div>
        {loaded && items.length > 0 && (
          <div className="shrink-0 text-right">
            <div className="font-sg text-3xl font-bold" style={{ color: "#34D399" }}>{items.length}</div>
            <div className="text-[11px] uppercase tracking-wider text-dim">{t("journal.count")}</div>
          </div>
        )}
      </div>

      {loaded && items.length === 0 ? (
        <p className="text-muted">{t("journal.empty")}</p>
      ) : (
        <div className="overflow-hidden rounded-2xl" style={{ border: "1px solid rgba(255,255,255,.07)" }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-dim" style={{ background: "rgba(255,255,255,.03)" }}>
                <th className="px-4 py-3">Token</th>
                <th className="px-4 py-3 text-right">{t("journal.pnl")}</th>
                <th className="hidden px-4 py-3 sm:table-cell">{t("journal.reason")}</th>
                <th className="hidden px-4 py-3 text-right md:table-cell">{t("journal.held")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} style={{ borderTop: "1px solid rgba(255,255,255,.05)" }}>
                  <td className="px-4 py-3">
                    <span className="font-sg font-bold">${p.symbol || "—"}</span>
                    <span className="ml-2 text-[11px] uppercase tracking-wider text-dim">{p.chain}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="font-sg font-bold" style={{ color: "#34D399" }}>
                      +{(p.pnl_pct ?? 0).toFixed(1)}%
                    </div>
                    <div className="text-[11px]" style={{ color: "#7df3c0" }}>
                      +${Math.abs(p.realized_pnl_usd).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </div>
                  </td>
                  <td className="hidden px-4 py-3 text-muted sm:table-cell">{p.exit_reason || "—"}</td>
                  <td className="hidden px-4 py-3 text-right text-muted md:table-cell">{heldLabel(p.opened_at, p.closed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
