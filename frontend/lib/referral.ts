"use client";

import { getToken } from "./auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// Та же схема, что и lib/admin.ts: Bearer-токен + понятные коды ошибок.
async function req(path: string, init?: RequestInit) {
  const t = getToken();
  const res = await fetch(`${API_BASE}/api/referral${path}`, {
    ...init,
    headers: { "content-type": "application/json", Authorization: `Bearer ${t}`, ...(init?.headers || {}) },
  });
  if (res.status === 401) throw new Error("unauth");
  if (!res.ok) {
    // Бэкенд может вернуть {detail|error} — пробрасываем для точного сообщения.
    let detail = "";
    try {
      const body = await res.json();
      detail = (body?.detail || body?.error || "") as string;
    } catch {
      /* тело не JSON */
    }
    throw new Error(detail || `referral ${res.status}`);
  }
  return res.json();
}

export type PayoutStatus = "pending" | "paid" | "rejected";

export type ReferralEarning = {
  amount_usd: number;
  rate: number; // доля, напр. 0.20
  created_at: string;
};

export type ReferralPayout = {
  id: number;
  amount_usd: number;
  status: PayoutStatus;
  created_at: string;
  paid_at: string | null;
};

export type ReferralMe = {
  code: string;
  link: string;
  referrals_total: number;
  referrals_active: number;
  tier: string;
  rate: number; // доля, напр. 0.20
  earned_total_usd: number;
  paid_total_usd: number;
  balance_usd: number;
  earnings: ReferralEarning[];
  payouts: ReferralPayout[];
};

export const fetchReferralMe = () => req("/me") as Promise<ReferralMe>;

export const requestPayout = (address?: string) =>
  req("/payout", { method: "POST", body: JSON.stringify({ address }) }) as Promise<ReferralPayout>;
