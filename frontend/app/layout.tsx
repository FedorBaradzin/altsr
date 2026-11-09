import "./globals.css";
import type { Metadata } from "next";
import Assistant from "@/components/Assistant";

const SITE = process.env.NEXT_PUBLIC_SITE_URL || "https://altsr.app";

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: {
    default: "ALTSR — Early Crypto Token Radar, Scam Screening & Signals",
    template: "%s · ALTSR",
  },
  description:
    "ALTSR scans brand-new crypto tokens in real time, screens them for scams and honeypots, scores risk, and simulates entries on paper. Screening over hype — not financial advice.",
  keywords: [
    "new crypto tokens", "early token radar", "crypto scam detector", "honeypot checker",
    "rug pull detector", "memecoin scanner", "crypto trading signals", "token risk score",
    "solana new tokens", "new dex pairs",
  ],
  applicationName: "ALTSR",
  alternates: {
    canonical: "/",
    languages: { "en": "/", "ru": "/ru" },
  },
  openGraph: {
    type: "website",
    siteName: "ALTSR",
    title: "ALTSR — Early Crypto Token Radar & Scam Screening",
    description:
      "Find new tokens early, screen out scams, get signals, and paper-trade before risking real money.",
    url: SITE,
  },
  twitter: {
    card: "summary_large_image",
    title: "ALTSR — Early Crypto Token Radar",
    description: "New-token radar with anti-scam screening, signals and paper simulation.",
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <Assistant />
      </body>
    </html>
  );
}
