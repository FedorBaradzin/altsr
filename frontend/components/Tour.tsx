"use client";

import { useCallback, useEffect, useState } from "react";
import { useLang } from "@/components/LangProvider";

const STEP_SELS = [
  '[data-tour="account"]',
  '[data-tour="paper"]',
  '[data-tour="feed"]',
  '[data-tour="right"]',
  '[data-tour="assistant"]',
];
const KEY = "altsr_tour_done";
const POPUP_W = 300;
const POPUP_H = 170;

export default function Tour() {
  const { t } = useLang();
  const [phase, setPhase] = useState<"welcome" | "tour" | null>(null);
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem(KEY)) setPhase("welcome");
  }, []);

  // Only READ the element's position — never scroll from here. This runs on
  // every scroll/resize event, so scrolling here would feed back into itself
  // and hang the page (the smooth scroll restarts on every frame it emits).
  const measure = useCallback(() => {
    const el = document.querySelector(STEP_SELS[i]);
    setRect(el ? el.getBoundingClientRect() : null);
  }, [i]);

  useEffect(() => {
    if (phase !== "tour") return;
    // Scroll to the step exactly once, when the step changes.
    const el = document.querySelector(STEP_SELS[i]);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    // Re-measure a few times while the smooth scroll settles, then track
    // further scroll/resize so the highlight follows without re-scrolling.
    const timers = [setTimeout(measure, 60), setTimeout(measure, 250), setTimeout(measure, 500)];
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      timers.forEach(clearTimeout);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [phase, i, measure]);

  const finish = () => { localStorage.setItem(KEY, "1"); setPhase(null); setI(0); };
  const start = () => { setI(0); setPhase("tour"); };

  const Replay = (
    <button onClick={start} aria-label={t("tour.replay")}
      className="glass fixed bottom-5 left-5 z-40 flex h-11 items-center gap-2 rounded-full px-4 text-sm">
      <span>🧭</span> {t("tour.replay")}
    </button>
  );

  if (phase === null) return Replay;

  if (phase === "welcome") {
    return (
      <>
        {Replay}
        <div className="fixed inset-0 z-50 flex items-center justify-center px-5" style={{ background: "rgba(3,4,9,.7)", backdropFilter: "blur(4px)" }}>
          <div className="glass w-full max-w-md p-7">
            <div className="mb-1 text-xs tracking-[2px] text-violet">{t("tour.welcomeEyebrow")}</div>
            <h2 className="mb-3 font-sg text-2xl font-bold">{t("tour.welcomeTitle")}</h2>
            <p className="mb-4 text-sm leading-relaxed text-muted">{t("tour.welcomeBody")}</p>
            <ul className="mb-6 space-y-1.5 text-sm text-[#cdd6e6]">
              <li>{t("tour.b1")}</li>
              <li>{t("tour.b2")}</li>
              <li>{t("tour.b3")}</li>
            </ul>
            <div className="flex gap-3">
              <button onClick={start} className="flex-1 rounded-xl px-4 py-2.5 text-sm font-semibold text-[#06231c]"
                style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}>{t("tour.start")}</button>
              <button onClick={finish} className="glass rounded-xl px-4 py-2.5 text-sm">{t("tour.skip")}</button>
            </div>
          </div>
        </div>
      </>
    );
  }

  // tour
  const n = STEP_SELS.length;
  const title = t(`tour.s${i + 1}.t`);
  const text = t(`tour.s${i + 1}.x`);
  const pad = 8;
  const vw = typeof window !== "undefined" ? window.innerWidth : 1200;
  const vh = typeof window !== "undefined" ? window.innerHeight : 800;
  const box = rect
    ? { left: Math.max(6, rect.left - pad), top: Math.max(6, rect.top - pad), width: rect.width + pad * 2, height: rect.height + pad * 2 }
    : null;
  // Prefer above the element; else below; then clamp fully inside the viewport
  // so the popup is never pushed off-screen by a tall target (e.g. the feed).
  let popTop = box ? (box.top > POPUP_H + 24 ? box.top - (POPUP_H - 20) : box.top + box.height + 12) : 120;
  popTop = Math.min(Math.max(12, popTop), vh - POPUP_H - 12);
  const popLeft = box ? Math.min(Math.max(12, box.left), vw - POPUP_W - 12) : 20;

  return (
    <>
      {Replay}
      <div className="fixed inset-0 z-50" style={{ background: "rgba(3,4,9,.55)" }} onClick={finish} />
      {box && (
        <div className="pointer-events-none fixed z-50 rounded-xl"
          style={{ left: box.left, top: box.top, width: box.width, height: box.height, border: "2px solid #22D3EE", boxShadow: "0 0 0 9999px rgba(3,4,9,.55), 0 0 24px rgba(34,211,238,.5)" }} />
      )}
      <div className="glass fixed z-[51] p-4" style={{ top: popTop, left: popLeft, width: POPUP_W }}>
        <div className="mb-1 text-[11px] text-dim">{t("tour.step", { i: i + 1, n })}</div>
        <div className="mb-1 font-sg font-semibold">{title}</div>
        <p className="mb-3 text-[13px] leading-snug text-muted">{text}</p>
        <div className="flex items-center justify-between">
          <button onClick={finish} className="text-xs text-dim hover:text-ink">{t("tour.skip")}</button>
          <div className="flex gap-2">
            {i > 0 && <button onClick={() => setI(i - 1)} className="glass rounded-lg px-3 py-1.5 text-xs">{t("tour.back")}</button>}
            {i < n - 1
              ? <button onClick={() => setI(i + 1)} className="rounded-lg px-3 py-1.5 text-xs font-semibold text-[#06231c]" style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}>{t("tour.next")}</button>
              : <button onClick={finish} className="rounded-lg px-3 py-1.5 text-xs font-semibold text-[#06231c]" style={{ background: "linear-gradient(135deg,#10B981,#22D3EE)" }}>{t("tour.done")}</button>}
          </div>
        </div>
      </div>
    </>
  );
}
