"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { loginWallet, loginWalletConnect, googleLoginUrl, telegramVerify } from "@/lib/auth";
import { useLang } from "@/components/LangProvider";

const ERR_KEY: Record<string, string> = {
  no_wallet: "auth.walletNotFound",
  sig_rejected: "auth.sigRejected",
  wc_failed: "auth.wcFailed",
};

export default function AuthButtons() {
  const router = useRouter();
  const { t } = useLang();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<null | "wallet" | "wc">(null);

  const run = async (kind: "wallet" | "wc", fn: () => Promise<unknown>) => {
    setErr(null); setBusy(kind);
    try { await fn(); router.push("/app"); }
    catch (e) {
      const code = (e as Error)?.message || "";
      setErr(ERR_KEY[code] ? t(ERR_KEY[code]) : String(code || e));
    } finally { setBusy(null); }
  };

  // Telegram widget callback (глобальный, как требует виджет).
  if (typeof window !== "undefined") {
    (window as any).onTelegramAuth = async (user: Record<string, unknown>) => {
      const me = await telegramVerify(user);
      if (me) router.push("/app"); else setErr(t("auth.tgFailed"));
    };
  }

  const tgBot = process.env.NEXT_PUBLIC_TELEGRAM_BOT;
  const wcEnabled = !!process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID;
  const googleEnabled = process.env.NEXT_PUBLIC_GOOGLE_ENABLED === "true";

  return (
    <div className="flex flex-col gap-3">
      <button onClick={() => run("wallet", loginWallet)} disabled={!!busy}
        className="rounded-xl px-5 py-3 text-sm font-semibold text-[#06231c] disabled:opacity-60"
        style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}>
        {busy === "wallet" ? t("auth.connecting") : t("auth.wallet")}
      </button>

      {wcEnabled && (
        <button onClick={() => run("wc", loginWalletConnect)} disabled={!!busy}
          className="glass rounded-xl px-5 py-3 text-sm disabled:opacity-60">
          {busy === "wc" ? t("auth.connecting") : t("auth.walletconnect")}
        </button>
      )}

      {googleEnabled ? (
        <a href={googleLoginUrl()} className="glass rounded-xl px-5 py-3 text-center text-sm">
          {t("auth.google")}
        </a>
      ) : (
        <div className="glass rounded-xl px-5 py-3 text-center text-sm text-muted opacity-70">
          {t("auth.googleSoon")}
        </div>
      )}

      {tgBot ? (
        <div
          dangerouslySetInnerHTML={{
            __html: `<script async src="https://telegram.org/js/telegram-widget.js?22" data-telegram-login="${tgBot}" data-size="large" data-onauth="onTelegramAuth(user)" data-request-access="write"></script>`,
          }}
        />
      ) : (
        <div className="glass rounded-xl px-5 py-3 text-center text-sm text-muted">
          {t("auth.tgNeed")}
        </div>
      )}
      {err && <p className="text-sm text-block">{err}</p>}
    </div>
  );
}
