import type { Metadata } from "next";
import Link from "next/link";
import { fetchTiers, type Tier } from "@/lib/api";
import ChoosePlan from "@/components/ChoosePlan";

export const metadata: Metadata = {
  title: "Pricing — Crypto Radar Plans",
  description:
    "ALTSR plans: real-time new-token radar, anti-scam screening, signals, Telegram alerts and paper trading. Pay with crypto. Not financial advice.",
  alternates: { canonical: "/pricing" },
};

export const revalidate = 3600;

const FALLBACK: Tier[] = [
  { id: "free", name: "Free", price_usd: 0, features: ["Лента с задержкой", "Базовый вердикт", "3 сигнала/день"] },
  { id: "pro", name: "Pro", price_usd: 29, features: ["Real-time лента", "Полная риск-карточка", "Сигналы без лимита", "Telegram-алерты", "Бумажный портфель"] },
  { id: "trader", name: "Trader", price_usd: 79, features: ["Всё из Pro", "Профили риска", "Несколько портфелей", "Ранний доступ", "API (лимит)"] },
  { id: "team", name: "Team / API", price_usd: 199, features: ["Всё из Trader", "Полный API + SLA", "От 5 мест"] },
];

export default async function Pricing() {
  let tiers = FALLBACK;
  try { tiers = await fetchTiers(); } catch { /* API down → fallback */ }

  return (
    <main className="mx-auto max-w-5xl px-6 py-14">
      <nav className="mb-8 flex items-center justify-between text-sm">
        <Link href="/" className="flex items-center gap-2 text-muted hover:text-ink">← ALTSR</Link>
        <Link href="/login" className="text-muted hover:text-ink">Войти</Link>
      </nav>
      <h1 className="mb-2 font-sg text-3xl font-bold">Тарифы</h1>
      <p className="mb-10 max-w-xl text-muted">
        Оплата криптой через NOWPayments. Это скрининг и симуляция, а не инвест-рекомендация.
      </p>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-4">
        {tiers.map((t) => (
          <div key={t.id} className="glass flex flex-col p-6" style={t.id === "pro" ? { borderColor: "rgba(139,92,246,.5)" } : undefined}>
            <div className="font-sg text-lg font-semibold">{t.name}</div>
            <div className="mb-4 mt-1 font-sg text-3xl font-bold">
              {t.price_usd > 0 ? `$${t.price_usd}` : "$0"}<span className="text-sm font-normal text-muted">/мес</span>
            </div>
            <ul className="mb-6 flex-1 space-y-2 text-sm text-[#cdd6e6]">
              {t.features.map((f) => (
                <li key={f} className="flex gap-2"><span className="text-pass">✓</span>{f}</li>
              ))}
            </ul>
            <ChoosePlan tier={t.id} price={t.price_usd} />
          </div>
        ))}
      </div>

      <p className="mt-10 text-xs leading-relaxed text-dim">
        Продажа аналитики по крипте в ряде юрисдикций регулируется. ALTSR не обещает доходность;
        ~98% новых токенов обнуляются. Оформите Terms of Service до коммерческого запуска.
      </p>
    </main>
  );
}
