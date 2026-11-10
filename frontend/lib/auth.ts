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

// Общий поток: nonce → personal_sign → verify. Работает с любым EIP-1193
// провайдером (инъектированный кошелёк или WalletConnect).
// Ошибки бросаются кодами ("no_wallet"/"sig_rejected"/"wc_failed") — текст
// подбирается на стороне UI по текущему языку.
async function signInWithProvider(provider: any, address: string): Promise<Me | null> {
  const nr = await fetch(`${API_BASE}/api/auth/wallet/nonce`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ address }),
  });
  const { message } = await nr.json();
  const signature = await provider.request({ method: "personal_sign", params: [message, address] });
  const vr = await fetch(`${API_BASE}/api/auth/wallet/verify`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ address, signature }),
  });
  if (!vr.ok) throw new Error("sig_rejected");
  const data = await vr.json();
  setToken(data.token);
  return data.user as Me;
}

// Инъектированный кошелёк (MetaMask и совместимые, window.ethereum).
export async function loginWallet(): Promise<Me | null> {
  const eth = (window as any).ethereum;
  if (!eth) throw new Error("no_wallet");
  const [address] = await eth.request({ method: "eth_requestAccounts" });
  return signInWithProvider(eth, address);
}

// WalletConnect — QR для мобильных кошельков. Провайдер грузится лениво.
export async function loginWalletConnect(): Promise<Me | null> {
  const projectId = process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID;
  if (!projectId) throw new Error("wc_failed");
  const { EthereumProvider } = await import("@walletconnect/ethereum-provider");
  const provider = await EthereumProvider.init({
    projectId,
    chains: [1],
    optionalChains: [1, 8453, 56],
    showQrModal: true,
    metadata: {
      name: "ALTSR",
      description: "Early Crypto Radar",
      url: "https://altsr.space",
      icons: ["https://altsr.space/icon.svg"],
    },
  });
  await provider.connect();
  const address = (provider.accounts && provider.accounts[0]) as string | undefined;
  if (!address) throw new Error("wc_failed");
  return signInWithProvider(provider, address);
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
