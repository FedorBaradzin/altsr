"use client";

import { useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
type Msg = { role: "user" | "assistant"; content: string };

export default function Assistant() {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([
    { role: "assistant", content: "Привет! Я консультант ALTSR. Спросите про скрининг, сигналы, бумажную симуляцию или тарифы." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    const history = msgs.slice(-8);
    setMsgs((m) => [...m, { role: "user", content: text }]);
    setInput(""); setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/assistant/chat`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: text, history }),
      });
      const data = await res.json();
      setMsgs((m) => [...m, { role: "assistant", content: data.answer || "…" }]);
    } catch {
      setMsgs((m) => [...m, { role: "assistant", content: "Связь прервалась, попробуйте ещё раз." }]);
    } finally {
      setBusy(false);
      setTimeout(() => boxRef.current?.scrollTo(0, boxRef.current.scrollHeight), 50);
    }
  };

  return (
    <>
      <button
        aria-label="Открыть консультанта"
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-5 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full text-2xl text-[#06231c] shadow-xl"
        style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)", boxShadow: "0 8px 30px rgba(139,92,246,.5)" }}
      >
        {open ? "✕" : "💬"}
      </button>

      {open && (
        <div className="glass fixed bottom-24 right-5 z-40 flex h-[460px] w-[340px] max-w-[92vw] flex-col overflow-hidden rounded-2xl">
          <div className="border-b px-4 py-3" style={{ borderColor: "var(--line)" }}>
            <div className="font-sg text-sm font-semibold">Консультант ALTSR · 24/7</div>
            <div className="text-[11px] text-muted">Отвечаю про платформу. Не инвест-совет.</div>
          </div>
          <div ref={boxRef} className="flex-1 space-y-2.5 overflow-y-auto px-3 py-3">
            {msgs.map((m, i) => (
              <div key={i} className={m.role === "user" ? "text-right" : ""}>
                <span
                  className="inline-block max-w-[85%] rounded-xl px-3 py-2 text-[13px] leading-snug"
                  style={m.role === "user"
                    ? { background: "rgba(139,92,246,.2)", color: "#EAF0FF" }
                    : { background: "rgba(10,12,22,.6)", color: "#cdd6e6", border: "1px solid var(--line)" }}
                >
                  {m.content}
                </span>
              </div>
            ))}
            {busy && <div className="text-[12px] text-muted">печатает…</div>}
          </div>
          <div className="flex gap-2 border-t p-2.5" style={{ borderColor: "var(--line)" }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Ваш вопрос…"
              className="flex-1 rounded-lg px-3 py-2 text-sm outline-none"
              style={{ background: "rgba(10,12,22,.6)", border: "1px solid var(--line)", color: "#EAF0FF" }}
            />
            <button onClick={send} disabled={busy}
              className="rounded-lg px-3 text-sm font-semibold text-[#06231c] disabled:opacity-60"
              style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}>→</button>
          </div>
        </div>
      )}
    </>
  );
}
