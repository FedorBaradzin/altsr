import Link from "next/link";
import { cookies } from "next/headers";
import GalaxyHero from "@/components/GalaxyHero";
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
        <h2 className="mb-8 font-sg text-2xl font-bold">{t("how.title")}</h2>
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
