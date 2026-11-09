import type { Metadata } from "next";
import Link from "next/link";
import AuthButtons from "@/components/AuthButtons";

export const metadata: Metadata = {
  title: "Войти",
  description: "Вход в ALTSR: кошелёк, Google или Telegram.",
  robots: { index: false, follow: false },
};

export default function LoginPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <Link href="/" className="mb-8 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl font-sg font-bold text-[#0a0b16]"
          style={{ background: "linear-gradient(135deg,#10B981,#22D3EE)" }}>◎</div>
        <div><div className="font-sg font-bold">ALTSR</div><div className="-mt-0.5 text-[11px] text-muted">Early Crypto Radar</div></div>
      </Link>
      <h1 className="mb-1 font-sg text-2xl font-bold">Вход в радар</h1>
      <p className="mb-7 text-sm text-muted">Выберите способ входа. Ничего не нужно заполнять.</p>
      <AuthButtons />
      <p className="mt-6 text-xs text-dim">
        Продолжая, вы соглашаетесь, что ALTSR — инструмент скрининга и симуляции, а не инвест-рекомендация.
      </p>
    </main>
  );
}
