export type Token = {
  id: number;
  chain: string;
  address: string;
  symbol: string | null;
  name: string | null;
  created_at: string | null;
  liquidity_usd: number | null;
  fdv: number | null;
  pair_address: string | null;
  dex: string | null;
  source: string;
  discovered_at: string;
  seen_count: number;
  links: Record<string, unknown>;
  verdict: "PASS" | "REVIEW" | "BLOCK" | null;
  risk_score: number | null;
  signal_confidence: number | null;
  is_malicious?: boolean;
};

export type TokenList = {
  items: Token[];
  total: number;
  limit: number;
  offset: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
export const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE || "ws://localhost:8000";

export async function fetchTokens(params: {
  chain?: string;
  minLiquidity?: number;
  verdict?: string;
  limit?: number;
}): Promise<TokenList> {
  const q = new URLSearchParams();
  if (params.chain) q.set("chain", params.chain);
  if (params.minLiquidity != null) q.set("min_liquidity", String(params.minLiquidity));
  if (params.verdict) q.set("verdict", params.verdict);
  q.set("limit", String(params.limit ?? 50));
  const res = await fetch(`${API_BASE}/api/tokens?${q.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

// Прямая ссылка «купить» (своп) по сети. Информация, не призыв покупать.
export type PaperSummary = {
  start_balance: number;
  cash: number;
  equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  return_pct: number;
  open_positions: number;
  closed_positions: number;
  wins: number;
  losses: number;
  win_rate: number | null;
  avg_win_pct: number | null;
  avg_loss_pct: number | null;
  plan: string[];
  disclaimer: string;
};

export async function fetchPaperSummary(): Promise<PaperSummary> {
  const res = await fetch(`${API_BASE}/api/paper/summary`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export type Tier = { id: string; name: string; price_usd: number; features: string[] };
export async function fetchTiers(): Promise<Tier[]> {
  const res = await fetch(`${API_BASE}/api/billing/tiers`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export type Signal = {
  id: number;
  token_id: number;
  chain: string;
  address: string;
  side: string;
  confidence: number;
  symbol: string | null;
  reasons: string[];
  venues: { type: string; name: string; url: string; note?: string }[];
};
export type NewsItem = {
  id: number;
  source: string;
  url: string;
  title: string;
  catalyst: string | null;
  sentiment: number | null;
  urgency: string | null;
  credibility: string | null;
};

export type Safety = {
  token_id: number;
  chain: string;
  address: string;
  risk_score: number;
  verdict: string;
  sources: string | null;
  flags: { code: string; severity: string; message: string }[];
  is_malicious?: boolean;
};
export async function fetchSafety(tokenId: number): Promise<Safety | null> {
  const res = await fetch(`${API_BASE}/api/tokens/${tokenId}/safety`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export async function fetchSignals(limit = 20): Promise<{ items: Signal[]; total: number }> {
  const res = await fetch(`${API_BASE}/api/signals?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}
export async function fetchNews(limit = 20): Promise<{ items: NewsItem[]; total: number }> {
  const res = await fetch(`${API_BASE}/api/news?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export type ArticleCard = {
  slug: string;
  lang: string;
  title: string;
  meta_description: string;
  source_name: string | null;
  published_at: string;
};
export type Article = ArticleCard & {
  keywords: string | null;
  body: string;
  source_url: string | null;
};

export async function fetchArticles(params: { lang?: string; limit?: number } = {}): Promise<{
  items: ArticleCard[];
  total: number;
}> {
  const q = new URLSearchParams();
  if (params.lang) q.set("lang", params.lang);
  q.set("limit", String(params.limit ?? 20));
  const res = await fetch(`${API_BASE}/api/articles?${q.toString()}`, { next: { revalidate: 300 } });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export async function fetchArticle(slug: string): Promise<Article | null> {
  const res = await fetch(`${API_BASE}/api/articles/${slug}`, { next: { revalidate: 300 } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export function buyUrl(t: Token): string {
  if (t.chain === "solana") return `https://jup.ag/swap/SOL-${t.address}`;
  if (t.chain === "bsc") return `https://pancakeswap.finance/swap?outputCurrency=${t.address}`;
  const uni: Record<string, string> = {
    ethereum: "mainnet", base: "base", polygon: "polygon", arbitrum: "arbitrum",
  };
  if (uni[t.chain])
    return `https://app.uniswap.org/swap?outputCurrency=${t.address}&chain=${uni[t.chain]}`;
  return `https://dexscreener.com/${t.chain}/${t.pair_address || t.address}`;
}

export function explorerUrl(t: Token): string {
  if (t.chain === "solana") return `https://solscan.io/token/${t.address}`;
  if (t.chain === "ethereum") return `https://etherscan.io/token/${t.address}`;
  if (t.chain === "base") return `https://basescan.org/token/${t.address}`;
  if (t.chain === "bsc") return `https://bscscan.com/token/${t.address}`;
  return `https://dexscreener.com/${t.chain}/${t.address}`;
}

export type TopReel = {
  id: number;
  symbol: string;
  chain: string;
  pnl_pct: number;
  pnl_usd: number;
  exit_reason: string | null;
  closed_at: string | null;
  reel_url: string;
};

export async function fetchTopReels(limit = 12): Promise<{ items: TopReel[]; total: number }> {
  const res = await fetch(`${API_BASE}/api/paper/reels/top?limit=${limit}`, { next: { revalidate: 120 } });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export function reelUrl(id: number, lang: string): string {
  return `${API_BASE}/api/paper/positions/${id}/reel?lang=${lang}`;
}

// --- Public journal of winning trades ---
export type JournalTrade = {
  id: number;
  symbol: string | null;
  chain: string;
  pnl_pct: number | null;
  realized_pnl_usd: number;
  exit_reason: string | null;
  opened_at: string;
  closed_at: string | null;
};

export async function fetchWinningTrades(limit = 50): Promise<JournalTrade[]> {
  const res = await fetch(`${API_BASE}/api/paper/positions?status=closed&limit=${limit}`, {
    next: { revalidate: 60 },
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  const data = await res.json();
  const items: JournalTrade[] = (data.items ?? data ?? []) as JournalTrade[];
  return items
    .filter((p) => (p.realized_pnl_usd ?? 0) > 0)
    .sort((a, b) => (b.pnl_pct ?? 0) - (a.pnl_pct ?? 0));
}
