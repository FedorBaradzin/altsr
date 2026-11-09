"use client";

import { useCallback, useEffect, useState } from "react";

type Step = { sel: string; title: string; text: string };
const STEPS: Step[] = [
  { sel: '[data-tour="account"]', title: "Вход", text: "Войдите кошельком, Google или Telegram — чтобы сохранять портфель и получать алерты." },
  { sel: '[data-tour="paper"]', title: "Бумажный счёт", text: "Ваш виртуальный депозит и P&L. Всё на симуляции — без реальных денег." },
  { sel: '[data-tour="feed"]', title: "Лента токенов", text: "Только что появившиеся монеты. Клик по строке откроет подробную риск-карточку. Бейдж PASS / REVIEW / BLOCK — вердикт анти-скам проверки (PASS ≠ «вырастет»)." },
  { sel: '[data-tour="right"]', title: "Сигналы и новости", text: "Справа — свежие BUY-сигналы с блоком «где купить» и новости с ИИ-разбором." },
  { sel: '[aria-label="Открыть консультанта"]', title: "Консультант 24/7", text: "Нажмите, чтобы спросить что угодно о платформе в любое время." },
];
const KEY = "altsr_tour_done";

export default function Tour() {
  const [phase, setPhase] = useState<"welcome" | "tour" | null>(null);
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem(KEY)) setPhase("welcome");
  }, []);

  const measure = useCallback(() => {
    const el = document.querySelector(STEPS[i]?.sel);
    if (el) { el.scrollIntoView({ behavior: "smooth", block: "center" }); setRect(el.getBoundingClientRect()); }
    else setRect(null);
  }, [i]);

  useEffect(() => {
    if (phase !== "tour") return;
    const t = setTimeout(measure, 120);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => { clearTimeout(t); window.removeEventListener("resize", measure); window.removeEventListener("scroll", measure, true); };
  }, [phase, i, measure]);

  const finish = () => { localStorage.setItem(KEY, "1"); setPhase(null); setI(0); };
  const start = () => { setI(0); setPhase("tour"); };

  const Replay = (
    <button onClick={start} aria-label="Тур по интерфейсу"
      className="glass fixed bottom-5 left-5 z-40 flex h-11 items-center gap-2 rounded-full px-4 text-sm">
      <span>🧭</span> Тур
    </button>
  );

  if (phase === null) return Replay;

  if (phase === "welcome") {
    return (
      <>
        {Replay}
        <div className="fixed inset-0 z-50 flex items-center justify-center px-5" style={{ background: "rgba(3,4,9,.7)", backdropFilter: "blur(4px)" }}>
          <div className="glass w-full max-w-md p-7">
            <div className="mb-1 text-xs tracking-[2px] text-violet">ДОБРО ПОЖАЛОВАТЬ</div>
            <h2 className="mb-3 font-sg text-2xl font-bold">Это ALTSR — ранний радар токенов</h2>
            <p className="mb-4 text-sm leading-relaxed text-muted">
              Находим новые монеты, проверяем на скам, даём сигнал и симулируем сделку на бумаге.
              Показать за минуту, что где находится?
            </p>
            <ul className="mb-6 space-y-1.5 text-sm text-[#cdd6e6]">
              <li>🛡 Вердикт безопасности у каждого токена</li>
              <li>⚡ Сигналы на вход + «где купить»</li>
              <li>📄 Бумажный P&L без реальных денег</li>
            </ul>
            <div className="flex gap-3">
              <button onClick={start} className="flex-1 rounded-xl px-4 py-2.5 text-sm font-semibold text-[#06231c]"
                style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}>Начать тур</button>
              <button onClick={finish} className="glass rounded-xl px-4 py-2.5 text-sm">Пропустить</button>
            </div>
          </div>
        </div>
      </>
    );
  }

  // tour
  const step = STEPS[i];
  const pad = 8;
  const box = rect
    ? { left: Math.max(6, rect.left - pad), top: Math.max(6, rect.top - pad), width: rect.width + pad * 2, height: rect.height + pad * 2 }
    : null;
  const popTop = box ? (box.top > 220 ? box.top - 150 : box.top + box.height + 12) : 120;
  const popLeft = box ? Math.min(Math.max(12, box.left), (typeof window !== "undefined" ? window.innerWidth : 1200) - 312) : 20;

  return (
    <>
      {Replay}
      <div className="fixed inset-0 z-50" style={{ background: "rgba(3,4,9,.55)" }} onClick={finish} />
      {box && (
        <div className="pointer-events-none fixed z-50 rounded-xl"
          style={{ left: box.left, top: box.top, width: box.width, height: box.height, border: "2px solid #22D3EE", boxShadow: "0 0 0 9999px rgba(3,4,9,.55), 0 0 24px rgba(34,211,238,.5)" }} />
      )}
      <div className="glass fixed z-[51] w-[300px] p-4" style={{ top: popTop, left: popLeft }}>
        <div className="mb-1 text-[11px] text-dim">Шаг {i + 1} из {STEPS.length}</div>
        <div className="mb-1 font-sg font-semibold">{step.title}</div>
        <p className="mb-3 text-[13px] leading-snug text-muted">{step.text}</p>
        <div className="flex items-center justify-between">
          <button onClick={finish} className="text-xs text-dim hover:text-ink">Пропустить</button>
          <div className="flex gap-2">
            {i > 0 && <button onClick={() => setI(i - 1)} className="glass rounded-lg px-3 py-1.5 text-xs">Назад</button>}
            {i < STEPS.length - 1
              ? <button onClick={() => setI(i + 1)} className="rounded-lg px-3 py-1.5 text-xs font-semibold text-[#06231c]" style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}>Далее</button>
              : <button onClick={finish} className="rounded-lg px-3 py-1.5 text-xs font-semibold text-[#06231c]" style={{ background: "linear-gradient(135deg,#10B981,#22D3EE)" }}>Готово</button>}
          </div>
        </div>
      </div>
    </>
  );
}
