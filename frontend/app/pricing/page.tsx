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
    ru: ["Лента с задержкой", "Базовый вердикт", "3 сигнала/день", "Демо бумажной торговли"],
    en: ["Delayed feed", "Basic verdict", "3 signals/day", "Paper-trading demo"] } },
  { id: "pro", name: "Pro", price: 49, highlight: true, features: {
    ru: ["Real-time лента", "Полная риск-карточка", "Сигналы без лимита", "Telegram-алерты", "Бумажный портфель", "История и фильтры"],
    en: ["Real-time feed", "Full risk card", "Unlimited signals", "Telegram alerts", "Paper portfolio", "History & filters"] } },
  { id: "autonomous", name: "Autonomous", price: 89, features: {
    ru: ["Всё из Pro", "Подвязка Telegram (бот + уведомления)", "Автоторговля (Delegation / Vault)", "Онлайн-поддержка 24/7", "Прямая связь в Telegram", "Расширенный риск-контроль"],
    en: ["Everything in Pro", "Telegram integration (bot + alerts)", "Autotrading (Delegation / Vault)", "24/7 online support", "Direct Telegram support", "Advanced risk controls"] } },
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

      <div className="mx-auto grid max-w-4xl grid-cols-1 gap-5 md:grid-cols-3">
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
