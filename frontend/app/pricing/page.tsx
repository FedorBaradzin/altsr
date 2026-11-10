import type { Metadata } from "next";
import Link from "next/link";
import { cookies } from "next/headers";
import ChoosePlan from "@/components/ChoosePlan";
import { LANG_COOKIE, normalizeLang, translate, type Lang } from "@/lib/i18n";
import LangSwitcher from "@/components/LangSwitcher";

export const metadata: Metadata = {
  title: "Pricing — Crypto Radar Plans",
  description:
    "ALTSR plans: real-time new-token radar, anti-scam screening, signals, Telegram alerts and paper trading. Pay with crypto. Not financial advice.",
  alternates: { canonical: "/pricing", languages: { en: "/pricing", ru: "/pricing" } },
};

type Plan = { id: string; name: string; price: number; highlight?: boolean; features: Record<Lang, string[]> };

const PLANS: Plan[] = [
  { id: "free", name: "Free", price: 0, features: {
    ru: ["Лента с задержкой", "Базовый вердикт", "3 сигнала/день"],
    en: ["Delayed feed", "Basic verdict", "3 signals/day"] } },
  { id: "pro", name: "Pro", price: 29, highlight: true, features: {
    ru: ["Real-time лента", "Полная риск-карточка", "Сигналы без лимита", "Telegram-алерты", "Бумажный портфель"],
    en: ["Real-time feed", "Full risk card", "Unlimited signals", "Telegram alerts", "Paper portfolio"] } },
  { id: "trader", name: "Trader", price: 79, features: {
    ru: ["Всё из Pro", "Профили риска", "Несколько портфелей", "Ранний доступ", "API (лимит)"],
    en: ["Everything in Pro", "Risk profiles", "Multiple portfolios", "Early access", "API (rate-limited)"] } },
  { id: "team", name: "Team / API", price: 199, features: {
    ru: ["Всё из Trader", "Полный API + SLA", "От 5 мест"],
    en: ["Everything in Trader", "Full API + SLA", "5+ seats"] } },
];

export default function Pricing() {
  const lang = normalizeLang(cookies().get(LANG_COOKIE)?.value);
  const t = (k: string) => translate(lang, k);

  return (
    <main className="mx-auto max-w-5xl px-6 py-14">
      <nav className="mb-8 flex items-center justify-between text-sm">
        <Link href="/" className="flex items-center gap-2 text-muted hover:text-ink">← ALTSR</Link>
        <div className="flex items-center gap-4">
          <LangSwitcher />
          <Link href="/login" className="text-muted hover:text-ink">{t("nav.login")}</Link>
        </div>
      </nav>
      <h1 className="mb-2 font-sg text-3xl font-bold">{t("pricing.title")}</h1>
      <p className="mb-10 max-w-xl text-muted">{t("pricing.sub")}</p>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-4">
        {PLANS.map((p) => (
          <div key={p.id} className="glass flex flex-col p-6" style={p.highlight ? { borderColor: "rgba(139,92,246,.5)" } : undefined}>
            <div className="font-sg text-lg font-semibold">{p.name}</div>
            <div className="mb-4 mt-1 font-sg text-3xl font-bold">
              {p.price > 0 ? `$${p.price}` : "$0"}<span className="text-sm font-normal text-muted">{t("pricing.perMonth")}</span>
            </div>
            <ul className="mb-6 flex-1 space-y-2 text-sm text-[#cdd6e6]">
              {p.features[lang].map((f) => (
                <li key={f} className="flex gap-2"><span className="text-pass">✓</span>{f}</li>
              ))}
            </ul>
            <ChoosePlan tier={p.id} price={p.price} />
          </div>
        ))}
      </div>

      <p className="mt-10 text-xs leading-relaxed text-dim">{t("pricing.disclaimer")}</p>
    </main>
  );
}
