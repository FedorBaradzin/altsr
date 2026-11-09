"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const KEY = "altsr_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(KEY);
}
export function setToken(t: string) {
  window.localStorage.setItem(KEY, t);
}
export function clearToken() {
  window.localStorage.removeItem(KEY);
}

export type Me = {
  id: number; auth_method: string; email: string | null;
  display_name: string | null; tier: string; tier_expires_at: string | null;
};

export async function fetchMe(): Promise<Me | null> {
  const t = getToken();
  if (!t) return null;
  const res = await fetch(`${API_BASE}/api/auth/me`, { headers: { Authorization: `Bearer ${t}` } });
  if (!res.ok) return null;
  return res.json();
}

// Вход кошельком (EVM / window.ethereum): nonce → personal_sign → verify.
export async function loginWallet(): Promise<Me | null> {
  const eth = (window as any).ethereum;
  if (!eth) throw new Error("Кошелёк не найден. Установите MetaMask или совместимый.");
  const [address] = await eth.request({ method: "eth_requestAccounts" });
  const nr = await fetch(`${API_BASE}/api/auth/wallet/nonce`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ address }),
  });
  const { message } = await nr.json();
  const signature = await eth.request({ method: "personal_sign", params: [message, address] });
  const vr = await fetch(`${API_BASE}/api/auth/wallet/verify`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ address, signature }),
  });
  if (!vr.ok) throw new Error("Подпись не принята");
  const data = await vr.json();
  setToken(data.token);
  return data.user as Me;
}

export function googleLoginUrl(): string {
  return `${API_BASE}/api/auth/google/login`;
}

// Telegram Login Widget вызывает этот колбэк с данными пользователя.
export async function telegramVerify(data: Record<string, unknown>): Promise<Me | null> {
  const res = await fetch(`${API_BASE}/api/auth/telegram/verify`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) return null;
  const d = await res.json();
  setToken(d.token);
  return d.user as Me;
}

export async function checkout(tier: string): Promise<{ invoice_url: string | null }> {
  const t = getToken();
  if (!t) throw new Error("not-authed");
  const res = await fetch(`${API_BASE}/api/billing/checkout`, {
    method: "POST",
    headers: { "content-type": "application/json", Authorization: `Bearer ${t}` },
    body: JSON.stringify({ tier }),
  });
  if (!res.ok) throw new Error(`checkout ${res.status}`);
  return res.json();
}
