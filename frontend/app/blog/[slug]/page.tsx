import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchArticle } from "@/lib/api";
import { mdToHtml } from "@/lib/md";

export const revalidate = 300;

type Props = { params: { slug: string } };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const a = await fetchArticle(params.slug).catch(() => null);
  if (!a) return { title: "Article not found" };
  return {
    title: a.title,
    description: a.meta_description,
    keywords: a.keywords || undefined,
    alternates: { canonical: `/blog/${a.slug}` },
    openGraph: {
      type: "article",
      title: a.title,
      description: a.meta_description,
      publishedTime: a.published_at,
      url: `/blog/${a.slug}`,
    },
    twitter: { card: "summary_large_image", title: a.title, description: a.meta_description },
  };
}

export default async function ArticlePage({ params }: Props) {
  const a = await fetchArticle(params.slug).catch(() => null);
  if (!a) notFound();

  const SITE = process.env.NEXT_PUBLIC_SITE_URL || "https://altsr.app";
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    headline: a.title,
    description: a.meta_description,
    datePublished: a.published_at,
    inLanguage: a.lang,
    publisher: { "@type": "Organization", name: "ALTSR" },
    mainEntityOfPage: `${SITE}/blog/${a.slug}`,
    isAccessibleForFree: true,
  };

  return (
    <main className="mx-auto max-w-2xl px-5 py-10">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <nav className="mb-6 text-sm text-muted"><Link href="/blog" className="hover:underline">← Blog</Link></nav>
      <article
        className="prose-altsr"
        dangerouslySetInnerHTML={{ __html: mdToHtml(a.body) }}
      />
      {a.source_url && (
        <p className="mt-8 text-xs text-muted">
          Original report:{" "}
          <a href={a.source_url} target="_blank" rel="noopener nofollow" className="underline">
            {a.source_name || "source"}
          </a>
        </p>
      )}
    </main>
  );
}
