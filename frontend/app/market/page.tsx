"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  fetchMarket, fetchMarketCategories, fetchOhlcv,
  type MarketRow, type MarketCategory, type Candle,
} from "@/lib/api";
import { useLang } from "@/components/LangProvider";
import LangSwitcher from "@/components/LangSwitcher";

// ---- helpers ----
const fmt = (n: number | null | undefined) =>
  n == null ? "—" : n >= 1e9 ? `$${(n / 1e9).toFixed(2)}B` : n >= 1e6 ? `$${(n / 1e6).toFixed(2)}M` : n >= 1e3 ? `$${(n / 1e3).toFixed(1)}K` : `$${Math.round(n)}`;
const age = (h: number | null | undefined) => {
  if (h == null) return "—";
  if (h < 1) return `${Math.max(1, Math.round(h * 60))}m`;
  if (h < 48) return `${Math.round(h)}h`;
  return `${Math.round(h / 24)}d`;
};
const vcol = (v: string | null) =>
  v === "PASS" ? "#34D399" : v === "REVIEW" ? "#FBBF24" : v === "BLOCK" ? "#F87171" : "#66708C";
const chcol = (c: number | null | undefined) =>
  c == null ? "#9AA6C4" : c > 0 ? "#34D399" : c < 0 ? "#F87171" : "#9AA6C4";
const CHAINS = [
  { k: "", ru: "Все", en: "All" },
  { k: "solana", ru: "Solana", en: "Solana" },
  { k: "bsc", ru: "BNB", en: "BNB" },
  { k: "base", ru: "Base", en: "Base" },
  { k: "eth", ru: "Ethereum", en: "Ethereum" },
];

type TabKey = "trending" | "new" | "gainers" | "revival" | "categories";

function Badge({ v, risk }: { v: string | null; risk: number | null }) {
  const c = vcol(v);
  const label = v ?? "—";
  return (
    <span className="rounded-md px-2 py-0.5 text-[11px] font-semibold" style={{ background: `${c}1f`, color: c }}>
      {label}{risk != null ? ` · ${risk}` : ""}
    </span>
  );
}

// ---- Свечной график (реальные OHLCV из нашего /api/public/ohlcv) ----
function ChartModal({ row, lang, onClose }: { row: MarketRow; lang: "ru" | "en"; onClose: () => void }) {
  const cref = useRef<HTMLCanvasElement | null>(null);
  const [tf, setTf] = useState<"minute" | "hour" | "day">("hour");
  const [msg, setMsg] = useState<string>(lang === "en" ? "Loading…" : "Загрузка…");
  const tr = (ru: string, en: string) => (lang === "en" ? en : ru);

  const draw = useCallback((candles: Candle[]) => {
    const cv = cref.current;
    if (!cv) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = cv.clientWidth, h = cv.clientHeight;
    cv.width = w * dpr; cv.height = h * dpr;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!candles.length) return;
    const padT = 12, padB = 26, padR = 58, plotW = w - padR, priceH = (h - padT - padB) * 0.76, volH = (h - padT - padB) * 0.24;
    let lo = Infinity, hi = -Infinity, vmax = 0;
    candles.forEach((c) => { if (c[3] < lo) lo = c[3]; if (c[2] > hi) hi = c[2]; if (c[5] > vmax) vmax = c[5]; });
    if (!(hi > lo)) { hi = lo + 1; lo -= 1; }
    const py = (p: number) => padT + ((hi - p) / (hi - lo)) * priceH;
    const grid = "rgba(130,150,210,.10)", muted = "#66708C";
    ctx.font = "10px 'JetBrains Mono',monospace"; ctx.textBaseline = "middle";
    for (let i = 0; i <= 4; i++) {
      const pv = hi - ((hi - lo) * i) / 4, yy = py(pv);
      ctx.strokeStyle = grid; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(plotW, yy); ctx.stroke();
      ctx.fillStyle = muted; ctx.textAlign = "left";
      ctx.fillText(fmtPrice(pv), plotW + 6, yy);
    }
    const n = candles.length, slot = plotW / n, bw = Math.max(1.5, Math.min(10, slot * 0.6));
    candles.forEach((c, i) => {
      const x = i * slot + slot / 2, o = c[1], hg = c[2], lw = c[3], cl = c[4], v = c[5];
      const up = cl >= o, col = up ? "#34D399" : "#F87171";
      ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x, py(hg)); ctx.lineTo(x, py(lw)); ctx.stroke();
      const y1 = py(Math.max(o, cl)), y2 = py(Math.min(o, cl));
      ctx.fillStyle = col; ctx.fillRect(x - bw / 2, y1, bw, Math.max(1, y2 - y1));
      if (vmax > 0) { const vh = (v / vmax) * volH; ctx.globalAlpha = 0.3; ctx.fillRect(x - bw / 2, h - padB - vh, bw, vh); ctx.globalAlpha = 1; }
    });
    ctx.fillStyle = muted; ctx.textAlign = "center";
    [0, Math.floor(n / 2), n - 1].forEach((idx) => {
      const c = candles[idx]; if (!c) return;
      const d = new Date(c[0] * 1000);
      const lab = tf === "day" ? `${d.getDate()}/${d.getMonth() + 1}` : `${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
      ctx.fillText(lab, Math.min(plotW - 14, Math.max(14, idx * slot + slot / 2)), h - 6);
    });
  }, [tf]);

  useEffect(() => {
    let alive = true;
    setMsg(lang === "en" ? "Loading…" : "Загрузка…");
    const pool = row.pair_address || row.address;
    fetchOhlcv(row.chain, pool, tf, 120).then((d) => {
      if (!alive) return;
      if (!d.candles.length) { setMsg(tr("График временно недоступен (лимит источника).", "Chart temporarily unavailable (source limit).")); return; }
      setMsg(""); requestAnimationFrame(() => draw(d.candles));
    }).catch(() => { if (alive) setMsg(tr("График временно недоступен.", "Chart temporarily unavailable.")); });
    return () => { alive = false; };
  }, [row, tf, draw, lang]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const TFS: { k: "minute" | "hour" | "day"; label: string }[] = [
    { k: "minute", label: tr("Минуты", "Min") },
    { k: "hour", label: tr("Часы", "Hour") },
    { k: "day", label: tr("Дни", "Day") },
  ];

  return (
    <div onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(3,4,10,.72)", backdropFilter: "blur(6px)" }}>
      <div className="glass w-full max-w-[720px] rounded-2xl p-4" style={{ border: "1px solid rgba(130,150,210,.16)" }}>
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-sg font-bold text-ink">{row.symbol || "—"}</span>
            <span className="text-xs text-dim uppercase">{row.chain}</span>
            {row.change_24h != null && (
              <span className="text-xs font-semibold" style={{ color: chcol(row.change_24h) }}>
                {row.change_24h > 0 ? "+" : ""}{row.change_24h}% · 24ч
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {TFS.map((f) => (
              <button key={f.k} onClick={() => setTf(f.k)}
                className="rounded-md px-2 py-1 text-[11px]"
                style={{ background: tf === f.k ? "rgba(139,92,246,.22)" : "transparent", color: tf === f.k ? "#C4B5FD" : "#9AA6C4" }}>
                {f.label}
              </button>
            ))}
            <button onClick={onClose} className="ml-1 rounded-md px-2 py-1 text-sm text-muted hover:text-ink">✕</button>
          </div>
        </div>
        <div className="relative" style={{ height: 300 }}>
          <canvas ref={cref} style={{ width: "100%", height: "100%", display: "block" }} />
          {msg && <div className="absolute inset-0 flex items-center justify-center text-sm text-muted">{msg}</div>}
        </div>
        <div className="mt-2 text-[11px] text-dim">
          {tr("Реальные ончейн-свечи из GeckoTerminal. Это движение цены токена — не прибыль и не обещание доходности.",
              "Real on-chain candles from GeckoTerminal. Token price action — not profit, not a promise of returns.")}
        </div>
      </div>
    </div>
  );
}

function fmtPrice(p: number) {
  if (!isFinite(p)) return "—";
  if (p >= 1) return p.toFixed(p >= 100 ? 1 : 3);
  if (p >= 1e-4) return p.toFixed(6);
  return p.toExponential(2);
}

export default function MarketPage() {
  const { lang } = useLang();
  const tr = (ru: string, en: string) => (lang === "en" ? en : ru);
  const [tab, setTab] = useState<TabKey>("trending");
  const [chain, setChain] = useState<string>("");
  const [rows, setRows] = useState<MarketRow[]>([]);
  const [cats, setCats] = useState<MarketCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [chartRow, setChartRow] = useState<MarketRow | null>(null);

  const TABS: { k: TabKey; ru: string; en: string }[] = [
    { k: "trending", ru: "Тренды", en: "Trending" },
    { k: "new", ru: "Новые пулы", en: "New Pools" },
    { k: "gainers", ru: "Растущие", en: "Top Gainers" },
    { k: "revival", ru: "Возрождение", en: "Revival" },
    { k: "categories", ru: "Категории", en: "Categories" },
  ];

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === "categories") {
        const d = await fetchMarketCategories();
        setCats(d.categories); setRows([]);
      } else {
        const d = await fetchMarket(tab, chain || undefined, 40);
        setRows(d.tokens); setCats([]);
      }
    } catch { /* тихо: показываем пусто */ }
    setLoading(false);
  }, [tab, chain]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (tab === "categories") return;
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load, tab]);

  const openChart = (r: MarketRow) => setChartRow(r);

  return (
    <main className="min-h-screen" style={{ background: "radial-gradient(60% 40% at 80% 0%,rgba(139,92,246,.08),transparent 60%),#05060B" }}>
      <div className="mx-auto max-w-[1360px] px-4 py-7 sm:px-6">
        {/* header */}
        <header className="mb-6 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl font-sg font-bold text-[#0a0b16]" style={{ background: "linear-gradient(135deg,#10B981,#22D3EE)" }}>◎</div>
            <div><div className="font-sg font-bold text-ink">ALTSR</div><div className="-mt-0.5 text-[10px] text-muted">{tr("Рынок", "Market")}</div></div>
          </Link>
          <nav className="flex items-center gap-5 text-sm text-muted">
            <Link href="/radar" className="hidden hover:text-ink sm:inline">{tr("Радар", "Radar")}</Link>
            <Link href="/pricing" className="hidden hover:text-ink sm:inline">{tr("Тарифы", "Pricing")}</Link>
            <LangSwitcher />
            <Link href="/radar" className="glass rounded-lg px-4 py-2 text-sm text-ink">{tr("Войти в радар →", "Open radar →")}</Link>
          </nav>
        </header>

        {/* title */}
        <div className="mb-5">
          <h1 className="font-sg text-2xl font-bold text-ink sm:text-3xl">{tr("Рынок", "Market")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            {tr("Что движется прямо сейчас — на наших ончейн-данных, с анти-скам вердиктом на каждом токене. Клик по строке → реальный свечной график.",
                "What's moving right now — on our on-chain data, with an anti-scam verdict on every token. Click a row for a real candlestick chart.")}
          </p>
          <p className="mt-1 text-[12px] text-dim">
            {tr("Рост 24ч — реальное движение цены токена, не прибыль и не обещание доходности. PASS ≠ «вырастет».",
                "24h change is real token price action, not profit or a promise. PASS ≠ \"will rise\".")}
          </p>
        </div>

        {/* tabs */}
        <div className="mb-4 flex flex-wrap gap-2">
          {TABS.map((tb) => (
            <button key={tb.k} onClick={() => setTab(tb.k)}
              className="rounded-xl px-4 py-2 text-sm font-medium transition"
              style={{
                background: tab === tb.k ? "linear-gradient(135deg,rgba(139,92,246,.28),rgba(34,211,238,.18))" : "rgba(20,25,44,.55)",
                color: tab === tb.k ? "#EAF0FF" : "#9AA6C4",
                border: `1px solid ${tab === tb.k ? "rgba(139,92,246,.45)" : "rgba(130,150,210,.12)"}`,
              }}>
              {tr(tb.ru, tb.en)}
            </button>
          ))}
        </div>

        {/* chain filter (hidden on categories) */}
        {tab !== "categories" && (
          <div className="mb-4 flex flex-wrap gap-2">
            {CHAINS.map((c) => (
              <button key={c.k} onClick={() => setChain(c.k)}
                className="rounded-lg px-3 py-1 text-[12px]"
                style={{
                  background: chain === c.k ? "rgba(34,211,238,.16)" : "transparent",
                  color: chain === c.k ? "#67E8F9" : "#66708C",
                  border: `1px solid ${chain === c.k ? "rgba(34,211,238,.3)" : "rgba(130,150,210,.12)"}`,
                }}>
                {tr(c.ru, c.en)}
              </button>
            ))}
          </div>
        )}

        {/* content */}
        {tab === "categories" ? (
          <CategoriesView cats={cats} loading={loading} lang={lang} onOpen={(c, a, p) => openChart({ chain: c, address: a, pair_address: p } as MarketRow)} />
        ) : (
          <MarketTable rows={rows} loading={loading} tab={tab} lang={lang} onChart={openChart} />
        )}
      </div>

      {chartRow && <ChartModal row={chartRow} lang={lang} onClose={() => setChartRow(null)} />}
    </main>
  );
}

function MarketTable({ rows, loading, tab, lang, onChart }:
  { rows: MarketRow[]; loading: boolean; tab: TabKey; lang: "ru" | "en"; onChart: (r: MarketRow) => void }) {
  const tr = (ru: string, en: string) => (lang === "en" ? en : ru);
  if (loading && !rows.length) return <div className="glass rounded-2xl p-10 text-center text-muted">{tr("Загрузка…", "Loading…")}</div>;
  if (!rows.length) return (
    <div className="glass rounded-2xl p-10 text-center text-muted">
      {tr("Пока нет данных для этого раздела. Радар пополняет базу — зайдите чуть позже.",
          "No data for this section yet. The radar keeps filling the base — check back shortly.")}
    </div>
  );
  return (
    <div className="glass overflow-hidden rounded-2xl" style={{ border: "1px solid rgba(130,150,210,.12)" }}>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-dim">
            <th className="px-4 py-3">#</th>
            <th className="px-4 py-3">{tr("Токен", "Token")}</th>
            <th className="px-4 py-3">{tr("Возраст", "Age")}</th>
            <th className="hidden px-4 py-3 sm:table-cell">{tr("Ликвидность", "Liquidity")}</th>
            <th className="px-4 py-3 text-right">{tr("Рост 24ч", "24h")}</th>
            <th className="px-4 py-3">{tr("Вердикт", "Verdict")}</th>
            <th className="hidden px-4 py-3 md:table-cell">Smart</th>
            <th className="px-4 py-3 text-right"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.chain}:${r.address}:${i}`} onClick={() => onChart(r)}
              className="cursor-pointer border-t transition hover:bg-[rgba(139,92,246,.06)]" style={{ borderColor: "rgba(130,150,210,.08)" }}>
              <td className="px-4 py-3 text-dim">{i + 1}</td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-ink">{r.symbol || "—"}</span>
                  {tab === "revival" && r.bucket && (
                    <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: r.bucket === "revived" ? "rgba(52,211,153,.16)" : "rgba(251,191,36,.16)", color: r.bucket === "revived" ? "#34D399" : "#FBBF24" }}>
                      {r.bucket === "revived" ? tr("возродился", "revived") : tr("возрождается", "reviving")}
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-dim uppercase">{r.chain}</div>
              </td>
              <td className="px-4 py-3 text-muted">{age(r.age_hours)}</td>
              <td className="hidden px-4 py-3 text-muted sm:table-cell">{fmt(r.liquidity_usd)}</td>
              <td className="px-4 py-3 text-right font-semibold" style={{ color: chcol(r.change_24h) }}>
                {r.change_24h == null ? "—" : `${r.change_24h > 0 ? "+" : ""}${r.change_24h}%`}
              </td>
              <td className="px-4 py-3"><Badge v={r.verdict} risk={r.risk_score} /></td>
              <td className="hidden px-4 py-3 text-muted md:table-cell">{r.smart_wallets > 0 ? `🧠 ${r.smart_wallets}` : "—"}</td>
              <td className="px-4 py-3 text-right">
                <span className="rounded-md px-2 py-1 text-[11px]" style={{ background: "rgba(34,211,238,.12)", color: "#67E8F9" }}>
                  {tr("График", "Chart")}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CategoriesView({ cats, loading, lang, onOpen }:
  { cats: MarketCategory[]; loading: boolean; lang: "ru" | "en"; onOpen: (chain: string, address: string, pair: string | null) => void }) {
  const tr = (ru: string, en: string) => (lang === "en" ? en : ru);
  if (loading && !cats.length) return <div className="glass rounded-2xl p-10 text-center text-muted">{tr("Загрузка…", "Loading…")}</div>;
  if (!cats.length) return <div className="glass rounded-2xl p-10 text-center text-muted">{tr("Категории пока пустые.", "No categories yet.")}</div>;
  return (
    <>
      <p className="mb-3 text-[12px] text-dim">
        {tr("Наша группировка по теме из токенов, которые мы видели (не алгоритм Gecko). Клик по токену → график.",
            "Our theme grouping from tokens we've seen (not Gecko's algorithm). Click a token for a chart.")}
      </p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cats.map((c) => (
          <div key={c.key} className="glass rounded-2xl p-4" style={{ border: "1px solid rgba(130,150,210,.12)" }}>
            <div className="mb-2 flex items-baseline justify-between">
              <span className="font-sg font-bold text-ink">{c.title}</span>
              <span className="text-[11px] text-dim">{c.count} · {fmt(c.liq)}</span>
            </div>
            <div className="flex flex-col gap-1.5">
              {c.samples.map((s, i) => (
                <button key={`${s.address}:${i}`} onClick={() => onOpen(s.chain, s.address, s.pair_address)}
                  className="flex items-center justify-between rounded-lg px-2 py-1.5 text-left transition hover:bg-[rgba(139,92,246,.07)]">
                  <span className="text-sm text-ink">{s.symbol || "—"}<span className="ml-1 text-[10px] text-dim uppercase">{s.chain}</span></span>
                  <span className="text-xs font-semibold" style={{ color: chcol(s.change_24h) }}>
                    {s.change_24h == null ? "—" : `${s.change_24h > 0 ? "+" : ""}${s.change_24h}%`}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
