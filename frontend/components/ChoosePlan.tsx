"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { getToken, checkout } from "@/lib/auth";
import { useLang } from "@/components/LangProvider";

export default function ChoosePlan({ tier, price }: { tier: string; price: number }) {
  const router = useRouter();
  const { t } = useLang();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (price <= 0) {
    return (
      <button onClick={() => router.push("/login")}
        className="glass w-full rounded-xl px-4 py-2.5 text-sm">
        {t("pricing.startFree")}
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
      else setErr(t("pricing.payUnavailable"));
    } catch (e) {
      if (String(e).includes("not-authed")) router.push("/login");
      else setErr(t("pricing.invoiceFailed"));
    } finally { setBusy(false); }
  };

  return (
    <div>
      <button onClick={choose} disabled={busy}
        className="w-full rounded-xl px-4 py-2.5 text-sm font-semibold text-[#06231c] disabled:opacity-60"
        style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}>
        {busy ? t("pricing.creating") : `${t("pricing.payCrypto")} · $${price}${t("pricing.perMonth")}`}
      </button>
      {err && <p className="mt-2 text-xs text-block">{err}</p>}
    </div>
  );
}
