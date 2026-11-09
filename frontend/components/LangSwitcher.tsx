"use client";

import { useLang } from "@/components/LangProvider";
import { LANGS, type Lang } from "@/lib/i18n";

export default function LangSwitcher({ className = "" }: { className?: string }) {
  const { lang, setLang, t } = useLang();
  return (
    <div
      className={`inline-flex items-center rounded-full p-0.5 text-xs ${className}`}
      style={{ background: "rgba(20,25,44,.55)", border: "1px solid rgba(130,150,210,.18)" }}
      role="group"
      aria-label="Language"
    >
      {LANGS.map((l: Lang) => {
        const active = l === lang;
        return (
          <button
            key={l}
            onClick={() => !active && setLang(l)}
            aria-pressed={active}
            className="rounded-full px-2.5 py-1 font-semibold transition-colors"
            style={
              active
                ? { background: "linear-gradient(135deg,#8B5CF6,#22D3EE)", color: "#06231c" }
                : { color: "#9AA6C4" }
            }
          >
            {t(`lang.${l}`)}
          </button>
        );
      })}
    </div>
  );
}
