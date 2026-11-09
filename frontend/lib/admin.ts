"use client";

import { getToken } from "./auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function req(path: string, init?: RequestInit) {
  const t = getToken();
  const res = await fetch(`${API_BASE}/api/admin${path}`, {
    ...init,
    headers: { "content-type": "application/json", Authorization: `Bearer ${t}`, ...(init?.headers || {}) },
  });
  if (res.status === 401) throw new Error("unauth");
  if (res.status === 403) throw new Error("forbidden");
  if (!res.ok) throw new Error(`admin ${res.status}`);
  return res.json();
}

export type Overview = {
  tokens: number; signals: number; positions_open: number; positions_closed: number;
  users: number; payments_paid: number; articles: number; news: number;
  paper_equity: number | null; paper_realized: number | null;
};
export type AdminUser = {
  id: number; auth_method: string; subject: string; email: string | null;
  display_name: string | null; tier: string; tier_expires_at: string | null; created_at: string;
};
export type AdminPayment = {
  id: number; user_id: number; tier: string; status: string;
  amount_usd: number | null; invoice_id: string | null; created_at: string;
};

export const adminOverview = () => req("/overview") as Promise<Overview>;
export const adminUsers = () => req("/users") as Promise<AdminUser[]>;
export const adminPayments = () => req("/payments") as Promise<AdminPayment[]>;
export const adminFlags = () => req("/flags") as Promise<Record<string, unknown>>;
export const adminSetTier = (id: number, tier: string, days = 30) =>
  req(`/users/${id}/tier`, { method: "POST", body: JSON.stringify({ tier, days }) });
