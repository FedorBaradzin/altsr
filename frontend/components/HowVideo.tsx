"use client";

import { useEffect, useState } from "react";
import { useLang } from "@/components/LangProvider";

/**
 * Compact "platform video tour" band. Shows a small poster; clicking it opens
 * a modal that plays the tour video (or a styled placeholder until the clip is
 * uploaded). Drop the real files in /public and pass srcRu / srcEn.
 */
export default function HowVideo({ srcRu, srcEn }: { srcRu?: string; srcEn?: string }) {
  const { t, lang } = useLang();
  const [open, setOpen] = useState(false);
  const src = lang === "en" ? srcEn : srcRu;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [open]);

  return (
    <>
      {/* compact tour band */}
      <button
        onClick={() => setOpen(true)}
        className="glass flex w-full items-center gap-5 p-4 text-left transition hover:-translate-y-0.5"
      >
        <div
          className="relative h-[118px] w-[210px] flex-none overflow-hidden rounded-xl border border-line"
          style={{ background: "radial-gradient(120% 120% at 70% 30%,rgba(34,211,238,.25),transparent 55%),radial-gradient(120% 120% at 25% 75%,rgba(139,92,246,.3),transparent 60%),linear-gradient(160deg,#0a0e1c,#070912)" }}
        >
          <span className="tour-stars" aria-hidden />
          <span
            className="tour-play absolute left-1/2 top-1/2 flex h-12 w-12 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full text-[#061018]"
            style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24"><path d="M7 5 L19 12 L7 19 Z" fill="currentColor" /></svg>
          </span>
          <span className="absolute bottom-2 right-2 rounded-md px-2 py-1 font-mono text-[11px] text-ink" style={{ background: "rgba(0,0,0,.45)" }}>
            {t("howvideo.dur")}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 font-sg text-[11.5px] uppercase tracking-[.14em] text-cyan">▶ {t("howvideo.eyebrow")}</div>
          <div className="mb-1 font-sg text-xl font-bold">{t("howvideo.title")}</div>
          <div className="max-w-[520px] text-[13.5px] text-muted">{t("howvideo.sub")}</div>
        </div>
        <span className="glass hidden flex-none px-4 py-3 text-sm font-semibold md:inline-block">{t("howvideo.cta")} →</span>
      </button>

      {/* modal */}
      {open && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center p-5 md:p-8">
          <div className="absolute inset-0" style={{ background: "rgba(3,5,12,.82)", backdropFilter: "blur(10px)" }} onClick={() => setOpen(false)} />
          <div
            className="relative w-full max-w-4xl overflow-hidden rounded-2xl border"
            style={{ borderColor: "rgba(130,150,210,.22)", boxShadow: "0 40px 120px rgba(0,0,0,.7), 0 0 0 1px rgba(34,211,238,.12)", aspectRatio: "16 / 9", background: "#0A0C16", animation: "tourPop .35s cubic-bezier(.2,.8,.2,1)" }}
          >
            <button
              onClick={() => setOpen(false)}
              aria-label={t("howvideo.close")}
              className="glass absolute right-3 top-3 z-10 flex h-9 w-9 items-center justify-center rounded-lg"
            >
              ✕
            </button>
            {src ? (
              <video src={src} controls autoPlay playsInline className="h-full w-full bg-black" />
            ) : (
              <div
                className="flex h-full w-full flex-col items-center justify-center gap-4 px-6 text-center"
                style={{ background: "radial-gradient(120% 120% at 70% 20%,rgba(34,211,238,.18),transparent 55%),radial-gradient(120% 120% at 25% 80%,rgba(139,92,246,.22),transparent 60%),#070912" }}
              >
                <span className="tour-stars" aria-hidden />
                <div className="tour-play relative flex h-16 w-16 items-center justify-center rounded-full text-[#061018]" style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}>
                  <svg width="24" height="24" viewBox="0 0 24 24"><path d="M7 5 L19 12 L7 19 Z" fill="currentColor" /></svg>
                </div>
                <div className="relative font-sg text-lg font-semibold">{t("howvideo.title")}</div>
                <div className="relative max-w-sm text-sm text-muted">{t("howvideo.soon")}</div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
