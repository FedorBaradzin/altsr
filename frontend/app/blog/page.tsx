import type { Metadata } from "next";
import Link from "next/link";
import { fetchArticles } from "@/lib/api";

export const metadata: Metadata = {
  title: "Crypto News & Token Research",
  description:
    "Daily, original breakdowns of new-token catalysts — listings, exploits, unlocks and audits — with a screening-first, no-hype take. Not financial advice.",
  alternates: { canonical: "/blog" },
};

export const revalidate = 300;

function fmtDate(s: string): string {
  try { return new Date(s).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }); }
  catch { return ""; }
}

export default async function BlogIndex() {
  let items: Awaited<ReturnType<typeof fetchArticles>>["items"] = [];
  try { items = (await fetchArticles({ limit: 50 })).items; } catch { /* API down at build */ }

  return (
    <main className="mx-auto max-w-3xl px-5 py-10">
      <nav className="mb-6 text-sm text-muted"><Link href="/" className="hover:underline">← ALTSR</Link></nav>
      <h1 className="mb-1 text-2xl font-semibold">Crypto News &amp; Token Research</h1>
      <p className="mb-8 text-sm text-muted">
        Original, neutral breakdowns of new-token events. Screening over hype — not financial advice.
      </p>

      {items.length === 0 ? (
        <p className="text-muted">No articles yet. The engine publishes new pieces daily.</p>
      ) : (
        <ul className="space-y-5">
          {items.map((a) => (
            <li key={a.slug} className="border-t border-white/5 pt-5">
              <Link href={`/blog/${a.slug}`} className="text-lg font-medium hover:underline">
                {a.title}
              </Link>
              <p className="mt-1 text-sm text-muted">{a.meta_description}</p>
              <p className="mt-2 text-xs text-muted">
                {fmtDate(a.published_at)}{a.source_name ? ` · source: ${a.source_name}` : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
