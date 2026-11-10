"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getToken, clearToken, fetchMe, type Me } from "@/lib/auth";
import { useLang } from "@/components/LangProvider";
import LangSwitcher from "@/components/LangSwitcher";

export default function AccountPage() {
  const router = useRouter();
  const { t, lang } = useLang();
  const [state, setState] = useState<"loading" | "ok" | "anon">("loading");
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    fetchMe()
      .then((u) => {
        if (!u) { setState("anon"); return; }
        setMe(u); setState("ok");
      })
      .catch(() => setState("anon"));
  }, [router]);

  const logout = () => {
    clearToken();
    router.push("/");
  };

  // Человекочитаемый идентификатор: email → имя → #id.
  const identity = me ? (me.email || me.display_name || `#${me.id}`) : "";

  // Срок подписки: форматируем в локали и помечаем, если уже истёк.
  const expires = me?.tier_expires_at ? new Date(me.tier_expires_at) : null;
  const expired = expires ? expires.getTime() < Date.now() : false;
  const expiresLabel = expires
    ? expires.toLocaleDateString(lang === "ru" ? "ru-RU" : "en-US", {
        year: "numeric", month: "long", day: "numeric",
      })
    : null;

  return (
    <main className="min-h-screen" style={{ background: "radial-gradient(60% 40% at 80% 0%,rgba(139,92,246,.08),transparent 60%),#05060B" }}>
      <div className="mx-auto max-w-2xl px-6 py-14">
        <nav className="mb-8 flex items-center justify-between text-sm">
          <Link href="/radar" className="flex items-center gap-2 text-muted hover:text-ink">← ALTSR</Link>
          <LangSwitcher />
        </nav>

        <h1 className="mb-2 font-sg text-3xl font-bold">{t("account.title")}</h1>
        <p className="mb-10 max-w-xl text-muted">{t("account.sub")}</p>

        {state === "loading" && <p className="text-muted">{t("account.loading")}</p>}

        {state === "anon" && (
          <div className="glass p-6">
            <p className="mb-4 text-sm text-muted">{t("account.sessionExpired")}</p>
            <Link href="/login" className="glass inline-block rounded-xl px-4 py-2.5 text-sm">{t("nav.login")}</Link>
          </div>
        )}

        {state === "ok" && me && (
          <div className="flex flex-col gap-5">
            {/* Current plan */}
            <section className="glass p-6">
              <div className="mb-1 text-xs uppercase tracking-wider text-dim">{t("account.plan")}</div>
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="font-sg text-2xl font-bold capitalize">{me.tier}</div>
                <Link href="/pricing"
                  className="rounded-xl px-4 py-2.5 text-sm font-semibold text-[#06231c]"
                  style={{ background: "linear-gradient(135deg,#8B5CF6,#22D3EE)" }}>
                  {t("account.changePlan")}
                </Link>
              </div>
            </section>

            {/* Subscription status */}
            <section className="glass p-6">
              <div className="mb-1 text-xs uppercase tracking-wider text-dim">{t("account.subscription")}</div>
              {expiresLabel ? (
                <div className="text-sm text-[#cdd6e6]">
                  {expired
                    ? <span className="text-block">{t("account.expiredOn", { date: expiresLabel })}</span>
                    : <span>{t("account.activeUntil", { date: expiresLabel })}</span>}
                </div>
              ) : (
                <div className="text-sm text-muted">{t("account.noExpiry")}</div>
              )}
            </section>

            {/* Account details */}
            <section className="glass p-6">
              <div className="mb-3 text-xs uppercase tracking-wider text-dim">{t("account.details")}</div>
              <dl className="flex flex-col gap-3 text-sm">
                <div className="flex items-center justify-between gap-4">
                  <dt className="text-muted">{t("account.identity")}</dt>
                  <dd className="truncate font-mono text-xs text-[#cdd6e6]">{identity}</dd>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <dt className="text-muted">{t("account.authMethod")}</dt>
                  <dd className="capitalize text-[#cdd6e6]">{me.auth_method}</dd>
                </div>
                {me.is_admin && (
                  <div className="flex items-center justify-between gap-4">
                    <dt className="text-muted">{t("account.role")}</dt>
                    <dd className="flex items-center gap-3">
                      <span className="rounded-full px-2.5 py-0.5 text-xs" style={{ background: "rgba(139,92,246,.18)", color: "#c4b5fd" }}>
                        {t("account.admin")}
                      </span>
                      <Link href="/admin" className="text-xs text-muted underline hover:text-ink">{t("account.adminPanel")}</Link>
                    </dd>
                  </div>
                )}
              </dl>
            </section>

            {/* Logout */}
            <button onClick={logout}
              className="glass rounded-xl px-5 py-3 text-sm font-semibold text-block hover:text-ink">
              {t("account.logout")}
            </button>
          </div>
        )}

        <p className="mt-10 text-xs leading-relaxed text-dim">{t("account.disclaimer")}</p>
      </div>
    </main>
  );
}
