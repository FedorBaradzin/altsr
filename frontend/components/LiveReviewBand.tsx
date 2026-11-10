"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchTokens, type Token } from "@/lib/api";
import { useLang } from "@/components/LangProvider";

const FREE_LIMIT = 10;

const vcol = (v: string | null) =>
  v === "PASS" ? "#34D399" : v === "REVIEW" ? "#FBBF24" : v === "BLOCK" ? "#F87171" : "#8B5CF6";

const fmt = (n: number | null) =>
  n == null ? "—" : n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `$${(n / 1e3).toFixed(0)}K` : `$${n.toFixed(0)}`;

function Coin({ tok, i }: { tok: Token; i: number }) {
  const c = vcol(tok.verdict);
  return (
    <div
      className="review-coin glass relative flex flex-col gap-2 rounded-2xl p-4"
      style={{ animationDelay: `${(i % 5) * 0.4}s`, boxShadow: `0 0 0 1px ${c}22, 0 10px 40px -12px ${c}44` }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className="flex h-8 w-8 items-center justify-center rounded-full text-[11px] font-bold text-[#06231c]"
            style={{ background: `linear-gradient(135deg, ${c}, #22D3EE)` }}
          >
            {(tok.symbol || "?").slice(0, 2).toUpperCase()}
          </span>
          <div>
            <div className="font-sg text-sm font-bold leading-none">{tok.symbol || "—"}</div>
            <div className="mt-0.5 text-[10px] uppercase tracking-wider text-dim">{tok.chain}</div>
          </div>
        </div>
        <span
          className="rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
          style={{ background: `${c}22`, color: c }}
        >
          {tok.verdict}
        </span>
      </div>
      <div className="flex items-end justify-between">
        <div>
          <div className="text-[10px] text-dim">risk</div>
          <div className="font-sg text-lg font-bold" style={{ color: c }}>
            {tok.risk_score ?? "—"}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] text-dim">ликв.</div>
          <div className="font-sg text-sm font-semibold">{fmt(tok.liquidity_usd)}</div>
        </div>
        {tok.signal_confidence != null && (
          <div className="text-right">
            <div className="text-[10px] text-dim">buy</div>
            <div className="font-sg text-sm font-semibold text-violet">
              {Math.round(tok.signal_confidence * 100)}%
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function LiveReviewBand() {
  const { t } = useLang();
  const [items, setItems] = useState<Token[]>([]);
  const [locked, setLocked] = useState(0);

  useEffect(() => {
    fetchTokens({ minLiquidity: 1000, limit: 80 })
      .then((r) => {
        const reviewed = r.items.filter((x) => x.verdict);
        // PASS first, then REVIEW, then BLOCK; within group by liquidity desc.
        const rank: Record<string, number> = { PASS: 0, REVIEW: 1, BLOCK: 2 };
        reviewed.sort(
          (a, b) =>
            (rank[a.verdict ?? ""] ?? 3) - (rank[b.verdict ?? ""] ?? 3) ||
            (b.liquidity_usd ?? 0) - (a.liquidity_usd ?? 0),
        );
        setItems(reviewed.slice(0, FREE_LIMIT));
        setLocked(Math.max(0, (r.total || reviewed.length) - FREE_LIMIT));
      })
      .catch(() => {});
  }, []);

  if (items.length === 0) return null;

  return (
    <section className="relative mx-auto max-w-6xl px-6 py-16">
      <style>{`
        @keyframes reviewFloat { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-10px)} }
        .review-coin{ animation: reviewFloat 6s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce){ .review-coin{ animation: none; } }
      `}</style>

      <p className="mb-1 text-xs tracking-[3px] text-violet">{t("live.eyebrow")}</p>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
        <h2 className="max-w-xl font-sg text-2xl font-bold md:text-3xl">{t("live.title")}</h2>
        <span className="flex items-center gap-2 text-sm text-[#7df3c0]">
          <span className="h-2 w-2 rounded-full" style={{ background: "#34D399", boxShadow: "0 0 0 4px rgba(52,211,153,.15)" }} />
          {t("live.badge")}
        </span>
      </div>

      <div className="relative">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {items.map((tok, i) => (
            <Coin key={tok.id} tok={tok} i={i} />
          ))}
        </div>

        {locked > 0 && (
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="glass h-[108px] rounded-2xl"
                style={{ filter: "blur(7px)", opacity: 0.5, background: "linear-gradient(135deg,rgba(139,92,246,.2),rgba(34,211,238,.12))" }}
              />
            ))}
            <div className="pointer-events-none absolute inset-x-0 bottom-0 flex h-[150px] flex-col items-center justify-center gap-3"
              style={{ background: "linear-gradient(180deg,transparent,rgba(5,6,11,.82) 55%,#05060B)" }}>
              <div className="pointer-events-auto flex flex-col items-center gap-3 text-center">
                <p className="text-sm text-muted">
                  🔒 {t("live.lockedPre")} <b className="text-ink">{locked.toLocaleString()}</b> {t("live.lockedPost")}
                </p>
                <Link
                  href="/login"
                  className="rounded-xl px-6 py-3 font-sg text-sm font-semibold text-[#06231c]"
                  style={{ background: "linear-gradient(135deg,#10B981,#22D3EE)", boxShadow: "0 10px 40px -8px rgba(34,211,238,.5)" }}
                >
                  {t("live.unlock")}
                </Link>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
