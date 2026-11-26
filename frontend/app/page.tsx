import Link from "next/link";
import { cookies } from "next/headers";
import GalaxyHero from "@/components/GalaxyHero";
import HowVideo from "@/components/HowVideo";
import LiveReviewBand from "@/components/LiveReviewBand";
import LangSwitcher from "@/components/LangSwitcher";
import { LANG_COOKIE, normalizeLang, translate } from "@/lib/i18n";

export default function Landing() {
  const lang = normalizeLang(cookies().get(LANG_COOKIE)?.value);
  const t = (k: string) => translate(lang, k);

  const FEATURES: [string, string][] = [
    ["⚡", t("feat.discover.t")],
    ["🛡", t("feat.safety.t")],
    ["📈", t("feat.sim.t")],
  ];
  const PIPELINE: [string, string, string][] = [
    [t("pipe.discover.n"), t("pipe.discover.s"), "#22D3EE"],
    [t("pipe.safety.n"), t("pipe.safety.s"), "#34D399"],
    [t("pipe.signal.n"), t("pipe.signal.s"), "#8B5CF6"],
    [t("pipe.paper.n"), t("pipe.paper.s"), "#FBBF24"],
    [t("pipe.ai.n"), t("pipe.ai.s"), "#A78BFA"],
  ];

  return (
    <main>
      {/* HERO */}
      <section className="relative h-screen min-h-[620px] overflow-hidden">
        <GalaxyHero />
        <div className="pointer-events-none absolute inset-0"
          style={{ background: "linear-gradient(180deg,transparent 55%,rgba(5,6,11,.75) 88%,#05060B 100%)" }} />

        <header className="absolute left-0 right-0 top-0 z-10 flex items-center justify-between px-6 py-5 md:px-9">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl font-sg text-xl font-bold text-[#0a0b16]"
              style={{ background: "linear-gradient(135deg,#10B981,#22D3EE)", boxShadow: "0 0 30px rgba(139,92,246,.5)" }}>◎</div>
            <div><div className="font-sg text-lg font-bold">ALTSR</div><div className="-mt-0.5 text-[11px] text-muted">{t("brand.tagline")}</div></div>
          </div>
          <nav className="hidden items-center gap-7 text-sm text-muted md:flex">
            <Link href="/radar" className="hover:text-ink">{t("nav.radar")}</Link>
            <a href="/landing/cabinet/index.html#market" className="hover:text-ink">{t("nav.market")}</a>
            <Link href="/pricing" className="hover:text-ink">{t("nav.pricing")}</Link>
            <Link href="/blog" className="hover:text-ink">{t("nav.blog")}</Link>
            <Link href="/journal" className="hover:text-ink">{t("nav.journal")}</Link>
            <a href="#how" className="hover:text-ink">{t("nav.about")}</a>
            <a href="https://t.me/altsr_manager" target="_blank" rel="noreferrer" className="hover:text-ink">{t("nav.support")}</a>
          </nav>
          <div className="flex items-center gap-3">
            <LangSwitcher />
            <Link href="/radar" className="glass px-4 py-2 text-sm">{t("nav.enter")}</Link>
          </div>
        </header>

        <div className="absolute left-5 top-[26%] z-10 max-w-[620px] rounded-3xl p-7 md:left-9 md:p-8"
          style={{ background: "linear-gradient(100deg,rgba(5,6,11,.78) 0%,rgba(5,6,11,.72) 44%,rgba(5,6,11,.4) 68%,transparent 94%)", backdropFilter: "blur(6px)" }}>
          <p className="mb-2 text-xs tracking-[3px] text-violet">{t("hero.eyebrow")}</p>
          <h1 className="font-sg text-[clamp(34px,5vw,60px)] font-bold leading-[1.03]"
            style={{ textShadow: "0 2px 30px rgba(5,6,11,.75)" }}>
            {t("hero.title1")} <span className="grad-text">{t("hero.title2")}</span>
          </h1>
          <p className="mb-6 mt-4 max-w-[440px] text-[16px] leading-relaxed text-muted">
            {t("hero.sub")}
          </p>
          <div className="flex flex-wrap gap-6">
            {FEATURES.map(([i, label]) => (
              <div key={label} className="flex items-center gap-3 text-sm text-[#C7D0EA]">
                <span className="glass flex h-9 w-9 items-center justify-center">{i}</span>{label}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* LIVE REVIEW BAND — real coins getting reviewed, with freemium lock */}
      <LiveReviewBand />

      {/* HOW IT WORKS */}
      <section id="how" className="mx-auto max-w-5xl px-6 py-20">
        <p className="mb-1 text-xs tracking-[3px] text-violet">{t("how.eyebrow")}</p>
        <h2 className="mb-6 font-sg text-2xl font-bold">{t("how.title")}</h2>

        {/* compact platform video tour — click opens the clip in a modal */}
        <div className="mb-8">
          <HowVideo />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {PIPELINE.map(([name, sub, color], i) => (
            <div key={name} className="flex items-center gap-3">
              <div className="min-w-[150px] flex-1 rounded-xl p-4" style={{ background: `${color}14`, border: `1px solid ${color}33` }}>
                <div className="text-[11px]" style={{ color }}>0{i}</div>
                <b className="font-sg">{name}</b>
                <div className="mt-0.5 text-xs text-muted">{sub}</div>
              </div>
              {i < PIPELINE.length - 1 && <span className="text-dim">→</span>}
            </div>
          ))}
        </div>
        <div className="mt-10 flex flex-wrap gap-3">
          <Link href="/radar" className="rounded-xl px-5 py-3 font-sg text-sm font-semibold text-[#06231c]"
            style={{ background: "linear-gradient(135deg,#10B981,#22D3EE)" }}>{t("cta.openRadar")}</Link>
          <Link href="/blog" className="glass px-5 py-3 text-sm">{t("cta.readBlog")}</Link>
        </div>
        <p className="mt-8 text-xs leading-relaxed text-dim">
          {t("disc.landing")}
        </p>
      </section>

      {/* WHAT'S NEW — recently shipped features */}
      <section id="whatsnew" className="mx-auto max-w-5xl px-6 pb-20">
        <p className="mb-1 text-xs tracking-[3px] text-violet">{lang === "en" ? "WHAT'S NEW" : "ЧТО НОВОГО"}</p>
        <h2 className="mb-6 font-sg text-2xl font-bold">{lang === "en" ? "Fresh in ALTSR" : "Свежее в ALTSR"}</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {([
            ["📊", lang === "en" ? "Market sections" : "Разделы «Рынок»",
              lang === "en" ? "Trending, New Pools, Top Gainers, Revival and Categories — live on-chain data, right in your cabinet." : "Тренды, Новые пулы, Растущие, Возрождение и Категории — живые ончейн-данные прямо в кабинете."],
            ["🕯", lang === "en" ? "Real candlestick charts" : "Свечные графики",
              lang === "en" ? "Click any token for a real OHLCV chart from on-chain data." : "Клик по токену — реальный свечной график по ончейн-данным."],
            ["🛡", lang === "en" ? "Anti-scam verdict on every token" : "Анти-скам вердикт на каждом токене",
              lang === "en" ? "PASS / REVIEW / BLOCK plus smart-money count on every row." : "PASS / REVIEW / BLOCK и счётчик smart-money в каждой строке."],
            ["📈", lang === "en" ? "Richer metrics" : "Больше метрик",
              lang === "en" ? "1h / 6h / 24h change, 24h volume and liquidity — no key needed." : "Рост за 1ч / 6ч / 24ч, объём и ликвидность — без платного ключа."],
            ["🤝", lang === "en" ? "Referral −5% discount" : "Реферальная скидка −5%",
              lang === "en" ? "Join via a referral link and get 5% off your plan." : "Приходишь по ссылке реферала — получаешь 5% скидку на тариф."],
            ["🤖", lang === "en" ? "Autotrade on top coins" : "Автотрейд по топ-монетам",
              lang === "en" ? "Paper autotrade now trades the top-by-volume universe. Paper only." : "Бумажный автотрейд торгует топ-монеты по объёму. Только симуляция."],
          ] as [string, string, string][]).map(([icon, title, desc]) => (
            <div key={title} className="glass rounded-2xl p-5">
              <div className="mb-2 text-2xl">{icon}</div>
              <b className="font-sg">{title}</b>
              <p className="mt-1 text-sm text-muted">{desc}</p>
            </div>
          ))}
        </div>
        <div className="mt-8">
          <a href="/landing/cabinet/index.html#market" className="inline-block rounded-xl px-5 py-3 font-sg text-sm font-semibold text-[#06231c]"
            style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}>
            {lang === "en" ? "Open Market →" : "Открыть «Рынок» →"}
          </a>
        </div>
      </section>

      {/* FOOTER — contact manager on Telegram */}
      <footer className="border-t border-line px-6 py-10 text-center">
        <a href="https://t.me/altsr_manager" target="_blank" rel="noreferrer"
          className="inline-flex items-center gap-2 rounded-xl px-5 py-3 font-sg text-sm font-semibold text-[#06231c]"
          style={{ background: "linear-gradient(135deg,#10B981,#22D3EE)" }}>
          ✈ {t("contact.manager")} — @altsr_manager
        </a>
        <p className="mt-3 text-xs text-muted">{t("contact.support247")}</p>
        <p className="mt-5 text-xs text-dim">© 2026 ALTSR · Crypto Neural Universe</p>
      </footer>
    </main>
  );
}
