import type { MetadataRoute } from "next";
import { fetchArticles } from "@/lib/api";

const SITE = process.env.NEXT_PUBLIC_SITE_URL || "https://altsr.app";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base: MetadataRoute.Sitemap = [
    { url: `${SITE}/`, changeFrequency: "hourly", priority: 1 },
    { url: `${SITE}/blog`, changeFrequency: "daily", priority: 0.8 },
  ];
  try {
    const { items } = await fetchArticles({ limit: 100 });
    for (const a of items) {
      base.push({
        url: `${SITE}/blog/${a.slug}`,
        lastModified: a.published_at,
        changeFrequency: "weekly",
        priority: 0.6,
      });
    }
  } catch {
    /* API недоступен на билде — отдаём базовый sitemap */
  }
  return base;
}
