"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { getToken, checkout } from "@/lib/auth";

export default function ChoosePlan({ tier, price }: { tier: string; price: number }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (price <= 0) {
    return (
      <button onClick={() => router.push("/login")}
        className="glass w-full rounded-xl px-4 py-2.5 text-sm">
        Начать бесплатно
      </button>
    );
  }

  const choose = async () => {
    setErr(null);
    if (!getToken()) { router.push("/login"); return; }
    setBusy(true);
    try {
      const { invoice_url } = await checkout(tier);
      if (invoice_url) window.location.href = invoice_url;
      else setErr("Оплата временно недоступна (NOWPayments не настроен).");
    } catch (e) {
      if (String(e).includes("not-authed")) router.push("/login");
      else setErr("Не удалось создать счёт.");
    } finally { setBusy(false); }
  };

  return (
    <div>
      <button onClick={choose} disabled={busy}
        className="w-full rounded-xl px-4 py-2.5 text-sm font-semibold text-[#06231c] disabled:opacity-60"
        style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}>
        {busy ? "Создаём счёт…" : `Оплатить криптой · $${price}/мес`}
      </button>
      {err && <p className="mt-2 text-xs text-block">{err}</p>}
    </div>
  );
}
