"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchTopReels, reelUrl, type TopReel } from "@/lib/api";
import { getToken, fetchMe } from "@/lib/auth";
import LangSwitcher from "@/components/LangSwitcher";
import { useLang } from "@/components/LangProvider";

export default function ReelsPage() {
  const { t, lang } = useLang();
  const [items, setItems] = useState<TopReel[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [admin, setAdmin] = useState<boolean | null>(null);

  useEffect(() => {
    if (!getToken()) { setAdmin(false); return; }
    fetchMe()
      .then((m) => setAdmin(!!m?.is_admin))
      .catch(() => setAdmin(false));
  }, []);

  useEffect(() => {
    if (!admin) return;
    fetchTopReels(18)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]))
      .finally(() => setLoaded(true));
  }, [admin]);

  return (
    <main className="mx-auto max-w-5xl px-5 py-10" style={{ minHeight: "100vh", background: "radial-gradient(60% 40% at 80% 0%,rgba(139,92,246,.08),transparent 60%),#05060B" }}>
      <nav className="mb-6 flex items-center justify-between text-sm text-muted">
        <Link href="/radar" className="hover:underline">← ALTSR</Link>
        <LangSwitcher />
      </nav>

      <h1 className="mb-1 font-sg text-2xl font-bold">🎬 {t("reels.title")}</h1>
      <p className="mb-8 max-w-2xl text-sm text-muted">{t("reels.sub")}</p>

      {admin === false ? (
        <p className="text-muted">{t("reels.adminOnly")}</p>
      ) : admin === null ? (
        <p className="text-dim">…</p>
      ) : loaded && items.length === 0 ? (
        <p className="text-muted">{t("reels.empty")}</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((r) => (
            <div key={r.id} className="glass flex flex-col overflow-hidden rounded-2xl p-5">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-sg text-lg font-bold">${r.symbol}</div>
                  <div className="text-[11px] uppercase tracking-wider text-dim">{r.chain}</div>
                </div>
                <div className="text-right">
                  <div className="font-sg text-2xl font-bold" style={{ color: "#34D399" }}>+{r.pnl_pct}%</div>
                  <div className="text-xs" style={{ color: "#7df3c0" }}>+${Math.abs(r.pnl_usd).toLocaleString()} {t("reels.profit")}</div>
                </div>
              </div>
              {r.exit_reason && (
                <div className="mt-3 inline-block w-fit rounded-md px-2 py-0.5 text-[11px]" style={{ background: "rgba(139,92,246,.16)", color: "#c4b5fd" }}>
                  {r.exit_reason}
                </div>
              )}
              <a
                href={reelUrl(r.id, lang)}
                target="_blank"
                rel="noreferrer"
                className="mt-4 rounded-xl px-4 py-2.5 text-center text-sm font-semibold text-[#06231c]"
                style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}
              >
                {t("reels.open")}
              </a>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
