import type { Metadata } from "next";
import Link from "next/link";
import { cookies } from "next/headers";
import AuthButtons from "@/components/AuthButtons";
import LangSwitcher from "@/components/LangSwitcher";
import { LANG_COOKIE, normalizeLang, translate } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "Sign in",
  robots: { index: false, follow: false },
};

export default function LoginPage() {
  const lang = normalizeLang(cookies().get(LANG_COOKIE)?.value);
  const t = (k: string) => translate(lang, k);

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <div className="mb-8 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl font-sg font-bold text-[#0a0b16]"
            style={{ background: "linear-gradient(135deg,#10B981,#22D3EE)" }}>◎</div>
          <div><div className="font-sg font-bold">ALTSR</div><div className="-mt-0.5 text-[11px] text-muted">{t("brand.tagline")}</div></div>
        </Link>
        <LangSwitcher />
      </div>
      <h1 className="mb-1 font-sg text-2xl font-bold">{t("login.title")}</h1>
      <p className="mb-7 text-sm text-muted">{t("login.sub")}</p>
      <AuthButtons />
      <p className="mt-6 text-xs text-dim">{t("login.disclaimer")}</p>
    </main>
  );
}
