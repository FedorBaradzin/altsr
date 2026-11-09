"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { loginWallet, googleLoginUrl, telegramVerify } from "@/lib/auth";

export default function AuthButtons() {
  const router = useRouter();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const wallet = async () => {
    setErr(null); setBusy(true);
    try { await loginWallet(); router.push("/app"); }
    catch (e) { setErr(String((e as Error).message || e)); }
    finally { setBusy(false); }
  };

  // Telegram widget callback (глобальный, как требует виджет).
  if (typeof window !== "undefined") {
    (window as any).onTelegramAuth = async (user: Record<string, unknown>) => {
      const me = await telegramVerify(user);
      if (me) router.push("/app"); else setErr("Telegram-вход не удался");
    };
  }
  const tgBot = process.env.NEXT_PUBLIC_TELEGRAM_BOT;

  return (
    <div className="flex flex-col gap-3">
      <button onClick={wallet} disabled={busy}
        className="rounded-xl px-5 py-3 text-sm font-semibold text-[#06231c] disabled:opacity-60"
        style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}>
        {busy ? "Подключение…" : "Подключить кошелёк"}
      </button>
      <a href={googleLoginUrl()} className="glass rounded-xl px-5 py-3 text-center text-sm">
        Войти через Google
      </a>
      {tgBot ? (
        <div
          dangerouslySetInnerHTML={{
            __html: `<script async src="https://telegram.org/js/telegram-widget.js?22" data-telegram-login="${tgBot}" data-size="large" data-onauth="onTelegramAuth(user)" data-request-access="write"></script>`,
          }}
        />
      ) : (
        <div className="glass rounded-xl px-5 py-3 text-center text-sm text-muted">
          Telegram-вход (нужен NEXT_PUBLIC_TELEGRAM_BOT)
        </div>
      )}
      {err && <p className="text-sm text-block">{err}</p>}
    </div>
  );
}
