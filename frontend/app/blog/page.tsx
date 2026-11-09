import type { Metadata } from "next";
import Link from "next/link";
import { cookies } from "next/headers";
import { fetchArticles } from "@/lib/api";
import LangSwitcher from "@/components/LangSwitcher";
import { LANG_COOKIE, normalizeLang, translate, type Lang } from "@/lib/i18n";

const BLOG_META: Record<Lang, { title: string; desc: string }> = {
  en: {
    title: "Crypto News & Token Research",
    desc: "Daily, original breakdowns of new-token catalysts — listings, exploits, unlocks and audits — with a screening-first, no-hype take. Not financial advice.",
  },
  ru: {
    title: "Крипто-новости и ресёрч токенов",
    desc: "Ежедневные оригинальные разборы катализаторов новых токенов — листинги, эксплойты, разблокировки и аудиты — со взглядом «скрининг прежде хайпа». Не инвест-рекомендация.",
  },
};

export function generateMetadata(): Metadata {
  const lang = normalizeLang(cookies().get(LANG_COOKIE)?.value);
  const m = BLOG_META[lang];
  return {
    title: m.title,
    description: m.desc,
    alternates: { canonical: "/blog", languages: { en: "/blog", ru: "/blog" } },
    openGraph: { title: m.title, description: m.desc, locale: lang === "ru" ? "ru_RU" : "en_US" },
  };
}

export const revalidate = 300;

function fmtDate(s: string, lang: Lang): string {
  try {
    return new Date(s).toLocaleDateString(lang === "ru" ? "ru-RU" : "en-US", {
      year: "numeric", month: "short", day: "numeric",
    });
  } catch { return ""; }
}

export default async function BlogIndex() {
  const lang = normalizeLang(cookies().get(LANG_COOKIE)?.value);
  const t = (k: string) => translate(lang, k);

  let items: Awaited<ReturnType<typeof fetchArticles>>["items"] = [];
  try { items = (await fetchArticles({ lang, limit: 50 })).items; } catch { /* API down at build */ }

  return (
    <main className="mx-auto max-w-3xl px-5 py-10">
      <nav className="mb-6 flex items-center justify-between text-sm text-muted">
        <Link href="/" className="hover:underline">{t("blog.back")}</Link>
        <LangSwitcher />
      </nav>
      <h1 className="mb-1 text-2xl font-semibold">{t("blog.title")}</h1>
      <p className="mb-8 text-sm text-muted">{t("blog.sub")}</p>

      {items.length === 0 ? (
        <p className="text-muted">{t("blog.empty")}</p>
      ) : (
        <ul className="space-y-5">
          {items.map((a) => (
            <li key={a.slug} className="border-t border-white/5 pt-5">
              <Link href={`/blog/${a.slug}`} className="text-lg font-medium hover:underline">
                {a.title}
              </Link>
              <p className="mt-1 text-sm text-muted">{a.meta_description}</p>
              <p className="mt-2 text-xs text-muted">
                {fmtDate(a.published_at, lang)}{a.source_name ? ` · ${t("blog.source")}: ${a.source_name}` : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
