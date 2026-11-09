import Link from "next/link";
import GalaxyHero from "@/components/GalaxyHero";

const FEATURES = [
  ["⚡", "Быстрый поиск новинок", "Лента только что созданных пар в реальном времени."],
  ["🛡", "Анти-скам скрининг", "GoPlus · RugCheck · honeypot.is → вердикт PASS / REVIEW / BLOCK."],
  ["📈", "Симуляция стратегий", "Бумажный вход/выход с честной статистикой до реальных денег."],
];
const PIPELINE = [
  ["Discover", "Поиск новинок", "#22D3EE"],
  ["Safety", "Анти-скам проверки", "#34D399"],
  ["Signal", "Оценка и рейтинг", "#8B5CF6"],
  ["Paper", "Симуляция стратегии", "#FBBF24"],
  ["AI", "Новости, контекст, риск", "#A78BFA"],
];

export default function Landing() {
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
            <div><div className="font-sg text-lg font-bold">ALTSR</div><div className="-mt-0.5 text-[11px] text-muted">Early Crypto Radar</div></div>
          </div>
          <nav className="hidden items-center gap-7 text-sm text-muted md:flex">
            <Link href="/app" className="hover:text-ink">Радар</Link>
            <Link href="/pricing" className="hover:text-ink">Тарифы</Link>
            <Link href="/blog" className="hover:text-ink">Блог</Link>
            <a href="#how" className="hover:text-ink">О системе</a>
          </nav>
          <Link href="/app" className="glass px-4 py-2 text-sm">Войти в радар →</Link>
        </header>

        <div className="absolute left-5 top-[26%] z-10 max-w-[620px] rounded-3xl p-7 md:left-9 md:p-8"
          style={{ background: "linear-gradient(100deg,rgba(5,6,11,.78) 0%,rgba(5,6,11,.72) 44%,rgba(5,6,11,.4) 68%,transparent 94%)", backdropFilter: "blur(6px)" }}>
          <p className="mb-2 text-xs tracking-[3px] text-violet">CRYPTO NEURAL UNIVERSE</p>
          <h1 className="font-sg text-[clamp(34px,5vw,60px)] font-bold leading-[1.03]"
            style={{ textShadow: "0 2px 30px rgba(5,6,11,.75)" }}>
            Ранний радар <span className="grad-text">новых криптотокенов</span>
          </h1>
          <p className="mb-6 mt-4 max-w-[440px] text-[16px] leading-relaxed text-muted">
            Каждый токен — светящийся объект, экосистема — галактика. Находим новинки, проверяем
            на скам, даём сигнал и симулируем вход на бумаге.
          </p>
          <div className="flex flex-wrap gap-6">
            {FEATURES.map(([i, t]) => (
              <div key={t} className="flex items-center gap-3 text-sm text-[#C7D0EA]">
                <span className="glass flex h-9 w-9 items-center justify-center">{i}</span>{t}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section id="how" className="mx-auto max-w-5xl px-6 py-20">
        <p className="mb-1 text-xs tracking-[3px] text-violet">КАК РАБОТАЕТ</p>
        <h2 className="mb-8 font-sg text-2xl font-bold">Вселенная данных — в рабочем терминале</h2>
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
          <Link href="/app" className="rounded-xl px-5 py-3 font-sg text-sm font-semibold text-[#06231c]"
            style={{ background: "linear-gradient(135deg,#10B981,#22D3EE)" }}>Открыть радар</Link>
          <Link href="/blog" className="glass px-5 py-3 text-sm">Читать блог</Link>
        </div>
        <p className="mt-8 text-xs leading-relaxed text-dim">
          Не инвест-рекомендация. Торговля новыми токенами — крайне высокий риск полной потери
          средств. ~98% новых токенов обнуляются. Платформа про скрининг и симуляцию.
        </p>
      </section>
    </main>
  );
}
