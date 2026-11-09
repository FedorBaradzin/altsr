import "./globals.css";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import Assistant from "@/components/Assistant";
import { LangProvider } from "@/components/LangProvider";
import { LANG_COOKIE, normalizeLang, type Lang } from "@/lib/i18n";

const SITE = process.env.NEXT_PUBLIC_SITE_URL || "https://altsr.space";

const META: Record<Lang, { title: string; desc: string }> = {
  en: {
    title: "ALTSR — Early Crypto Token Radar, Scam Screening & Signals",
    desc: "ALTSR scans brand-new crypto tokens in real time, screens them for scams and honeypots, scores risk, and simulates entries on paper. Screening over hype — not financial advice.",
  },
  ru: {
    title: "ALTSR — Ранний радар новых криптотокенов, анти-скам и сигналы",
    desc: "ALTSR находит новые криптотокены в реальном времени, проверяет на скам и ханипоты, оценивает риск и симулирует вход на бумаге. Скрининг вместо хайпа — не инвест-рекомендация.",
  },
};

export function generateMetadata(): Metadata {
  const lang = normalizeLang(cookies().get(LANG_COOKIE)?.value);
  const m = META[lang];
  return {
    metadataBase: new URL(SITE),
    title: { default: m.title, template: "%s · ALTSR" },
    description: m.desc,
    keywords: [
      "new crypto tokens", "early token radar", "crypto scam detector", "honeypot checker",
      "rug pull detector", "memecoin scanner", "crypto trading signals", "token risk score",
      "solana new tokens", "new dex pairs",
    ],
    applicationName: "ALTSR",
    alternates: {
      canonical: "/",
      languages: { en: "/", ru: "/" },
    },
    openGraph: {
      type: "website",
      siteName: "ALTSR",
      title: m.title,
      description: m.desc,
      url: SITE,
      locale: lang === "ru" ? "ru_RU" : "en_US",
    },
    twitter: {
      card: "summary_large_image",
      title: m.title,
      description: m.desc,
    },
    robots: { index: true, follow: true },
  };
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const lang = normalizeLang(cookies().get(LANG_COOKIE)?.value);
  return (
    <html lang={lang}>
      <body>
        <LangProvider initialLang={lang}>
          {children}
          <Assistant />
        </LangProvider>
      </body>
    </html>
  );
}
