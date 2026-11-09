/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000",
    NEXT_PUBLIC_WS_BASE: process.env.NEXT_PUBLIC_WS_BASE || "ws://localhost:8000",
    NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL || "https://altsr.app",
    NEXT_PUBLIC_TELEGRAM_BOT: process.env.NEXT_PUBLIC_TELEGRAM_BOT || "",
  },
};
module.exports = nextConfig;
