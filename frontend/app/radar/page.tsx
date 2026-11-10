"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  fetchTokens, fetchPaperSummary, fetchSignals, fetchNews, fetchSafety,
  buyUrl,
  type Token, type PaperSummary, type Signal, type NewsItem, type Safety,
} from "@/lib/api";
import { getToken, setToken, fetchMe, type Me } from "@/lib/auth";
import Tour from "@/components/Tour";
import LangSwitcher from "@/components/LangSwitcher";
import { useLang } from "@/components/LangProvider";

const vcol = (v: string | null) =>
  v === "PASS" ? "#34D399" : v === "REVIEW" ? "#FBBF24" : v === "BLOCK" ? "#F87171" : "#8B5CF6";
const fmt = (n: number | null) =>
  n == null ? "—" : n >= 1e6 ? `$${(n / 1e6).toFixed(2)}M` : n >= 1e3 ? `$${(n / 1e3).toFixed(1)}K` : `$${n.toFixed(0)}`;

function Badge({ v, risk }: { v: string | null; risk: number | null }) {
  if (!v) return <span className="text-dim">—</span>;
  const c = vcol(v);
  return <span className="rounded-md px-2 py-0.5 text-xs font-semibold" style={{ background: `${c}22`, color: c }}>{v}{risk != null ? ` · ${risk}` : ""}</span>;
}

export default function Dashboard() {
  const { t } = useLang();
  const [tokens, setTokens] = useState<Token[]>([]);
  const [paper, setPaper] = useState<PaperSummary | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [sel, setSel] = useState<{ t: Token; s: Safety | null } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    // Токен из редиректа (Google/кошелёк): #token=...
    if (typeof window !== "undefined" && window.location.hash.startsWith("#token=")) {
      setToken(decodeURIComponent(window.location.hash.slice(7)));
      history.replaceState(null, "", window.location.pathname);
    }
    if (getToken()) fetchMe().then(setMe).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    try {
      const [tk, p, s, n] = await Promise.all([
        fetchTokens({ limit: 40 }), fetchPaperSummary().catch(() => null),
        fetchSignals(10).catch(() => ({ items: [] as Signal[], total: 0 })),
        fetchNews(8).catch(() => ({ items: [] as NewsItem[], total: 0 })),
      ]);
      setTokens(tk.items); setPaper(p); setSignals(s.items); setNews(n.items); setErr(null);
    } catch (e) { setErr(String(e)); }
  }, []);

  useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id); }, [load]);

  const openRisk = async (tk: Token) => setSel({ t: tk, s: await fetchSafety(tk.id).catch(() => null) });

  return (
    <main className="min-h-screen" style={{ background: "radial-gradient(60% 40% at 80% 0%,rgba(139,92,246,.08),transparent 60%),#05060B" }}>
      <div className="mx-auto max-w-[1360px] px-6 py-7">
        <header className="mb-5 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl font-sg font-bold text-[#0a0b16]" style={{ background: "linear-gradient(135deg,#10B981,#22D3EE)" }}>◎</div>
            <div><div className="font-sg font-bold">ALTSR</div><div className="-mt-0.5 text-[10px] text-muted">{t("brand.tagline")}</div></div>
          </Link>
          <nav data-tour="account" className="flex items-center gap-5 text-sm text-muted">
            <Link href="/pricing" className="hidden hover:text-ink sm:inline">{t("nav.pricing")}</Link>
            <Link href="/blog" className="hidden hover:text-ink sm:inline">{t("nav.blog")}</Link>
            <Link href="/journal" className="hidden hover:text-ink sm:inline">{t("nav.journal")}</Link>
            {me?.is_admin && (
              <Link href="/reels" className="hidden hover:text-ink sm:inline">{t("nav.reels")}</Link>
            )}
            <LangSwitcher />
            {me ? (
              <Link href="/account" className="rounded-full px-3 py-1 text-xs hover:brightness-110" style={{ background: "rgba(139,92,246,.18)", color: "#c4b5fd" }}>
                {me.display_name || t("nav.account")} · {me.tier}
              </Link>
            ) : (
              <Link href="/login" className="glass px-3 py-1.5 text-xs">{t("nav.login")}</Link>
            )}
            <span className="flex items-center gap-2 text-[#7df3c0]"><span className="h-2 w-2 rounded-full" style={{ background: "#34D399", boxShadow: "0 0 0 4px rgba(52,211,153,.15)" }} />{t("dash.live")}</span>
          </nav>
        </header>

        {/* stat strip */}
        {paper && (
          <div data-tour="paper" className="glass mb-5 flex flex-wrap items-center gap-5 px-5 py-4">
            <div className="pr-4" style={{ borderRight: "1px solid var(--line)" }}>
              <div className="text-[11px] text-muted">{t("dash.paperAccount")}</div>
              <div className="font-sg text-xl font-bold">${paper.equity.toLocaleString()}</div>
            </div>
            <Stat l={t("dash.return")} v={`${paper.return_pct >= 0 ? "+" : ""}${paper.return_pct}%`} up={paper.return_pct >= 0} />
            <Stat l={t("dash.winrate")} v={paper.win_rate != null ? `${Math.round(paper.win_rate * 100)}%` : "—"} />
            <Stat l={t("dash.positions")} v={`${paper.open_positions} ${t("dash.positionsSuffix")}`} />
            <Stat l={t("dash.realizedPnl")} v={`${paper.realized_pnl >= 0 ? "+$" : "−$"}${Math.abs(paper.realized_pnl).toLocaleString()}`} up={paper.realized_pnl >= 0} />
          </div>
        )}

        <div className="grid grid-cols-1 gap-[18px] lg:grid-cols-[1.55fr_1fr]">
          {/* feed */}
          <div data-tour="feed" className="glass overflow-hidden">
            <div className="flex items-center justify-between border-b px-5 py-4" style={{ borderColor: "var(--line)" }}>
              <h2 className="font-sg text-[15px] font-semibold">{t("feed.title")}</h2>
            </div>
            {err && <p className="px-5 py-3 text-sm text-block">{t("feed.noApi", { err })}</p>}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-[11px] uppercase tracking-wider text-dim">
                  <th className="px-5 py-3 font-semibold">{t("col.token")}</th><th className="px-2 py-3 font-semibold">{t("col.verdict")}</th>
                  <th className="px-2 py-3 font-semibold">{t("col.signal")}</th><th className="px-2 py-3 text-right font-semibold">{t("col.liq")}</th>
                  <th className="px-5 py-3 font-semibold" />
                </tr></thead>
                <tbody>
                  {(me && me.tier !== "free" ? tokens : tokens.slice(0, 10)).map((tk) => (
                    <tr key={tk.id} className="cursor-pointer border-t hover:bg-violet/5" style={{ borderColor: "var(--line)" }} onClick={() => openRisk(tk)}>
                      <td className="px-5 py-3"><b className="font-sg">{tk.symbol || tk.address.slice(0, 8)}</b> <span className="text-[11px] text-dim">· {tk.chain}</span></td>
                      <td className="px-2 py-3"><Badge v={tk.verdict} risk={tk.risk_score} /></td>
                      <td className="px-2 py-3">{tk.signal_confidence != null ? <span className="rounded-md px-2 py-0.5 text-xs font-semibold" style={{ background: "rgba(139,92,246,.18)", color: "#c4b5fd" }}>⚡ {Math.round(tk.signal_confidence * 100)}%</span> : <span className="text-dim">—</span>}</td>
                      <td className="px-2 py-3 text-right font-sg">{fmt(tk.liquidity_usd)}</td>
                      <td className="px-5 py-3">{tk.verdict === "BLOCK" ? <span className="text-dim">{t("act.blocked")}</span> : <a href={buyUrl(tk)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="rounded-lg px-3 py-1 text-xs" style={{ background: "rgba(139,92,246,.16)", border: "1px solid rgba(139,92,246,.4)", color: "#d8ccff" }}>{t("act.buy")}</a>}</td>
                    </tr>
                  ))}
                  {(!me || me.tier === "free") && tokens.length > 10 && (
                    <tr>
                      <td colSpan={5} className="px-5 py-6">
                        <div className="flex flex-col items-center gap-3 text-center">
                          <div className="flex w-full max-w-md flex-col gap-2 opacity-50" style={{ filter: "blur(6px)" }}>
                            <div className="h-6 rounded" style={{ background: "rgba(139,92,246,.2)" }} />
                            <div className="h-6 rounded" style={{ background: "rgba(34,211,238,.14)" }} />
                          </div>
                          <p className="text-sm text-muted">🔒 {t("feed.lockedPre")} {tokens.length - 10}+ {t("feed.lockedPost")}</p>
                          <a href="/login" className="rounded-xl px-5 py-2.5 text-sm font-semibold text-[#06231c]" style={{ background: "linear-gradient(135deg,#10B981,#22D3EE)" }}>{t("feed.unlock")}</a>
                        </div>
                      </td>
                    </tr>
                  )}
                  {tokens.length === 0 && !err && <tr><td colSpan={5} className="px-5 py-10 text-center text-muted">{t("feed.empty")}</td></tr>}
                </tbody>
              </table>
            </div>
          </div>

          {/* right column */}
          <div data-tour="right" className="flex flex-col gap-[18px]">
            <Panel title={t("panel.signals")}>
              {signals.length === 0 ? <Empty text={t("empty.signals")} /> : signals.slice(0, 4).map((s) => (
                <div key={s.id} className="border-t px-5 py-3" style={{ borderColor: "var(--line)" }}>
                  <div className="flex items-center justify-between"><b className="font-sg">{s.symbol || s.address.slice(0, 8)} <span className="text-[11px] text-dim">{s.chain}</span></b>
                    <span className="rounded-md px-2 py-0.5 text-xs font-semibold" style={{ background: "rgba(139,92,246,.18)", color: "#c4b5fd" }}>BUY {Math.round(s.confidence * 100)}%</span></div>
                  {s.venues?.[0] && <a href={s.venues[0].url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs text-cyan">{s.venues[0].name} · {t("act.buy")}</a>}
                </div>
              ))}
            </Panel>

            <Panel title={t("panel.news")}>
              {news.length === 0 ? <Empty text={t("empty.news")} /> : news.slice(0, 5).map((n) => (
                <div key={n.id} className="border-t px-5 py-3" style={{ borderColor: "var(--line)" }}>
                  <div className="text-[13.5px]">{n.title}</div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5 text-[11px]">
                    {n.catalyst && <span className="rounded px-2 py-0.5" style={{ background: "rgba(10,12,22,.5)", border: "1px solid var(--line)", color: "#EAF0FF" }}>{n.catalyst}</span>}
                    {n.urgency && <span className="rounded px-2 py-0.5" style={{ background: "rgba(10,12,22,.5)", border: "1px solid var(--line)", color: n.urgency === "high" ? "#fca5a5" : "#fcd34d" }}>{n.urgency}</span>}
                  </div>
                </div>
              ))}
            </Panel>
          </div>
        </div>

        <div className="mt-5 flex gap-2.5 rounded-xl px-4 py-3 text-[12.5px] leading-relaxed" style={{ background: "rgba(251,191,36,.14)", border: "1px solid rgba(251,191,36,.26)", color: "#fce3ad" }}>
          <span>⚠</span><span>{t("disc.dash")}</span>
        </div>
      </div>

      {/* risk drawer */}
      {sel && (
        <>
          <div className="fixed inset-0 z-20" style={{ background: "rgba(3,4,9,.6)", backdropFilter: "blur(3px)" }} onClick={() => setSel(null)} />
          <aside className="fixed right-0 top-0 z-30 h-full w-[420px] max-w-[92vw] overflow-y-auto p-6" style={{ background: "#0A0C16", borderLeft: "1px solid var(--line)" }}>
            <button onClick={() => setSel(null)} className="glass absolute right-4 top-4 h-8 w-8 rounded-lg">✕</button>
            <div className="text-xs tracking-[2px] text-violet">{t("drawer.intel")}</div>
            <h2 className="mt-1 font-sg text-2xl font-bold">{sel.t.symbol || sel.t.address.slice(0, 8)} <Badge v={sel.t.verdict} risk={sel.t.risk_score} /></h2>
            <div className="mb-4 font-mono text-xs text-dim">{sel.t.chain} · {sel.t.address.slice(0, 20)}…</div>
            {(sel.t.verdict === "BLOCK" || sel.t.is_malicious || sel.s?.is_malicious) && (
              <div className="mb-4 flex items-start gap-2 rounded-lg px-3 py-2 text-[13px] font-medium" style={{ background: "rgba(248,113,113,.12)", border: "1px solid rgba(248,113,113,.45)", color: "#fca5a5" }}>
                <span>⚠</span><span>{t("safety.scam")}</span>
              </div>
            )}
            <div className="mb-3 flex items-center gap-4">
              <Ring v={sel.t.verdict} risk={sel.t.risk_score ?? 0} />
              <div><div className="text-xs text-muted">{t("drawer.liquidity")}</div><div className="font-sg text-xl font-bold">{fmt(sel.t.liquidity_usd)}</div></div>
            </div>
            {sel.s?.flags?.length ? (
              <>
                <div className="mb-2 mt-4 text-[11px] uppercase tracking-wider text-dim">{t("drawer.checks")}</div>
                {sel.s.flags.map((f, i) => (
                  <div key={i} className="flex gap-2 py-1 text-[13px]"><span style={{ color: f.severity === "hard" ? "#fca5a5" : f.severity === "soft" ? "#fcd34d" : "#9AA6C4" }}>{f.severity === "hard" ? "✕" : f.severity === "soft" ? "!" : "·"}</span><span>{f.message}</span></div>
                ))}
              </>
            ) : <p className="mt-4 text-sm text-muted">{t("drawer.pending")}</p>}
            {sel.t.verdict !== "BLOCK" && <a href={buyUrl(sel.t)} target="_blank" rel="noreferrer" className="mt-5 inline-block rounded-lg px-4 py-2 text-sm" style={{ background: "rgba(139,92,246,.16)", border: "1px solid rgba(139,92,246,.4)", color: "#d8ccff" }}>{t("act.buy")}</a>}
            <p className="mt-5 text-[11px] leading-relaxed text-dim">{t("drawer.disclaimer")}</p>
          </aside>
        </>
      )}
      <Tour />
    </main>
  );
}

function Stat({ l, v, up }: { l: string; v: string; up?: boolean }) {
  return <div className="min-w-[100px]"><div className="text-[11px] text-muted">{l}</div><div className="font-sg text-lg font-bold" style={up != null ? { color: up ? "#7df3c0" : "#fca5a5" } : undefined}>{v}</div></div>;
}
function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="glass overflow-hidden"><div className="border-b px-5 py-4" style={{ borderColor: "var(--line)" }}><h3 className="font-sg text-[15px] font-semibold">{title}</h3></div>{children}</div>;
}
function Empty({ text }: { text: string }) {
  return <p className="px-5 py-6 text-sm text-muted">{text}</p>;
}
function Ring({ v, risk }: { v: string | null; risk: number }) {
  const c = vcol(v), deg = Math.round(risk * 3.6);
  return (
    <div className="flex h-[88px] w-[88px] items-center justify-center rounded-full" style={{ background: `conic-gradient(${c} 0 ${deg}deg, rgba(130,150,210,.12) ${deg}deg 360deg)` }}>
      <div className="flex h-[66px] w-[66px] flex-col items-center justify-center rounded-full" style={{ background: "#0A0C16" }}>
        <div className="font-sg text-xl font-bold">{risk}</div><div className="text-[10px] text-dim">risk</div>
      </div>
    </div>
  );
}
