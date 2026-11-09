"use client";

import { createContext, useContext, useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { type Lang, LANG_COOKIE, translate, normalizeLang } from "@/lib/i18n";

type Ctx = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
};

const LangCtx = createContext<Ctx | null>(null);

function writeCookie(lang: Lang) {
  // 1 year, site-wide
  document.cookie = `${LANG_COOKIE}=${lang};path=/;max-age=31536000;samesite=lax`;
}

export function LangProvider({
  initialLang,
  children,
}: {
  initialLang: Lang;
  children: React.ReactNode;
}) {
  const [lang, setLangState] = useState<Lang>(normalizeLang(initialLang));
  const router = useRouter();

  const setLang = useCallback(
    (l: Lang) => {
      const next = normalizeLang(l);
      setLangState(next);
      writeCookie(next);
      // Re-render server components (landing, metadata) with the new locale.
      router.refresh();
    },
    [router],
  );

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => translate(lang, key, vars),
    [lang],
  );

  const value = useMemo<Ctx>(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <LangCtx.Provider value={value}>{children}</LangCtx.Provider>;
}

export function useLang(): Ctx {
  const ctx = useContext(LangCtx);
  if (!ctx) {
    // Safe fallback if a client component renders outside the provider.
    return {
      lang: "ru",
      setLang: () => {},
      t: (key, vars) => translate("ru", key, vars),
    };
  }
  return ctx;
}
