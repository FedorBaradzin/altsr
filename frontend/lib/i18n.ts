// Lightweight i18n for ALTSR (RU/EN). No external deps.
// Locale is stored in the `lang` cookie and read both on the server
// (landing, metadata) and on the client (LangProvider context).

export type Lang = "ru" | "en";
export const LANGS: Lang[] = ["ru", "en"];
export const DEFAULT_LANG: Lang = "ru";
export const LANG_COOKIE = "lang";

export function normalizeLang(v: string | undefined | null): Lang {
  return v === "en" ? "en" : "ru";
}

type Dict = Record<string, string>;

const ru: Dict = {
  "brand.tagline": "Early Crypto Radar",
  "nav.radar": "Радар",
  "nav.pricing": "Тарифы",
  "nav.blog": "Блог",
  "nav.about": "О системе",
  "nav.enter": "Войти в радар →",
  "nav.login": "Войти",
  "nav.account": "Аккаунт",

  "hero.eyebrow": "CRYPTO NEURAL UNIVERSE",
  "hero.title1": "Ранний радар",
  "hero.title2": "новых криптотокенов",
  "hero.sub":
    "Каждый токен — светящийся объект, экосистема — галактика. Находим новинки, проверяем на скам, даём сигнал и симулируем вход на бумаге.",

  "feat.discover.t": "Быстрый поиск новинок",
  "feat.discover.d": "Лента только что созданных пар в реальном времени.",
  "feat.safety.t": "Анти-скам скрининг",
  "feat.safety.d": "GoPlus · RugCheck · honeypot.is → вердикт PASS / REVIEW / BLOCK.",
  "feat.sim.t": "Симуляция стратегий",
  "feat.sim.d": "Бумажный вход/выход с честной статистикой до реальных денег.",

  "how.eyebrow": "КАК РАБОТАЕТ",
  "how.title": "Вселенная данных — в рабочем терминале",
  "pipe.discover.n": "Discover",
  "pipe.discover.s": "Поиск новинок",
  "pipe.safety.n": "Safety",
  "pipe.safety.s": "Анти-скам проверки",
  "pipe.signal.n": "Signal",
  "pipe.signal.s": "Оценка и рейтинг",
  "pipe.paper.n": "Paper",
  "pipe.paper.s": "Симуляция стратегии",
  "pipe.ai.n": "AI",
  "pipe.ai.s": "Новости, контекст, риск",
  "cta.openRadar": "Открыть радар",
  "cta.readBlog": "Читать блог",
  "disc.landing":
    "Не инвест-рекомендация. Торговля новыми токенами — крайне высокий риск полной потери средств. ~98% новых токенов обнуляются. Платформа про скрининг и симуляцию.",

  "dash.live": "live",
  "dash.paperAccount": "Бумажный счёт",
  "dash.return": "Доходность",
  "dash.winrate": "Win-rate",
  "dash.positions": "Позиции",
  "dash.positionsSuffix": "откр.",
  "dash.realizedPnl": "Реализ. P&L",
  "feed.title": "Лента токенов",
  "feed.noApi": "Нет связи с API ({err}). Запустите backend.",
  "feed.empty": "Лента наполнится, когда запущен discovery-воркер.",
  "col.token": "Токен",
  "col.verdict": "Вердикт",
  "col.signal": "Сигнал",
  "col.liq": "Ликв.",
  "act.buy": "купить ↗",
  "act.blocked": "заблок.",
  "panel.signals": "⚡ Сигналы",
  "panel.news": "📰 Новости",
  "empty.signals": "Пока нет BUY-сигналов.",
  "empty.news": "Нет новостей.",
  "disc.dash":
    "Не инвест-рекомендация. ~98% новых токенов обнуляются. PASS означает прохождение проверок, не гарантию роста. DYOR.",

  "drawer.intel": "TOKEN INTELLIGENCE",
  "drawer.liquidity": "Ликвидность",
  "drawer.checks": "Проверки",
  "drawer.pending": "Риск-отчёт ещё готовится.",
  "drawer.disclaimer":
    "Детекция ловит часть схем. PASS ≠ «безопасно» и тем более ≠ «вырастет». Не инвест-рекомендация.",

  "tour.replay": "Тур",
  "tour.welcomeEyebrow": "ДОБРО ПОЖАЛОВАТЬ",
  "tour.welcomeTitle": "Это ALTSR — ранний радар токенов",
  "tour.welcomeBody":
    "Находим новые монеты, проверяем на скам, даём сигнал и симулируем сделку на бумаге. Показать за минуту, что где находится?",
  "tour.b1": "🛡 Вердикт безопасности у каждого токена",
  "tour.b2": "⚡ Сигналы на вход + «где купить»",
  "tour.b3": "📄 Бумажный P&L без реальных денег",
  "tour.start": "Начать тур",
  "tour.skip": "Пропустить",
  "tour.back": "Назад",
  "tour.next": "Далее",
  "tour.done": "Готово",
  "tour.step": "Шаг {i} из {n}",
  "tour.s1.t": "Вход",
  "tour.s1.x": "Войдите кошельком, Google или Telegram — чтобы сохранять портфель и получать алерты.",
  "tour.s2.t": "Бумажный счёт",
  "tour.s2.x": "Ваш виртуальный депозит и P&L. Всё на симуляции — без реальных денег.",
  "tour.s3.t": "Лента токенов",
  "tour.s3.x":
    "Только что появившиеся монеты. Клик по строке откроет подробную риск-карточку. Бейдж PASS / REVIEW / BLOCK — вердикт анти-скам проверки (PASS ≠ «вырастет»).",
  "tour.s4.t": "Сигналы и новости",
  "tour.s4.x": "Справа — свежие BUY-сигналы с блоком «где купить» и новости с ИИ-разбором.",
  "tour.s5.t": "Консультант 24/7",
  "tour.s5.x": "Нажмите, чтобы спросить что угодно о платформе в любое время.",

  "blog.back": "← ALTSR",
  "blog.title": "Крипто-новости и ресёрч токенов",
  "blog.sub": "Оригинальные, нейтральные разборы событий по новым токенам. Скрининг вместо хайпа — не инвест-рекомендация.",
  "blog.empty": "Пока нет статей. Движок публикует новые материалы каждый день.",
  "blog.source": "источник",

  "nav.reels": "Рилсы",
  "reels.title": "Рилсы выгодных сделок",
  "reels.sub": "Лучшие прибыльные сделки бумажного счёта. Откройте рилс и запишите экран для Instagram / TikTok / Shorts.",
  "reels.empty": "Пока нет прибыльных закрытых сделок для рилсов. Загляните позже.",
  "reels.open": "Открыть рилс ↗",
  "reels.profit": "прибыль",

  "pricing.title": "Тарифы",
  "pricing.sub": "Оплата криптой через NOWPayments. Это скрининг и симуляция, а не инвест-рекомендация.",
  "pricing.perMonth": "/мес",
  "pricing.startFree": "Начать бесплатно",
  "pricing.payCrypto": "Оплатить криптой",
  "pricing.creating": "Создаём счёт…",
  "pricing.payUnavailable": "Оплата временно недоступна.",
  "pricing.invoiceFailed": "Не удалось создать счёт.",
  "pricing.disclaimer": "ALTSR не обещает доходность; ~98% новых токенов обнуляются. Оформите Terms of Service до коммерческого запуска.",

  "login.title": "Вход в радар",
  "login.sub": "Выберите способ входа. Ничего не нужно заполнять.",
  "login.disclaimer": "Продолжая, вы соглашаетесь, что ALTSR — инструмент скрининга и симуляции, а не инвест-рекомендация.",
  "auth.wallet": "Подключить кошелёк",
  "auth.connecting": "Подключение…",
  "auth.walletconnect": "WalletConnect (мобильный кошелёк)",
  "auth.google": "Войти через Google",
  "auth.googleSoon": "Google-вход скоро будет доступен",
  "auth.tgNeed": "Telegram-вход (настройка в процессе)",
  "auth.walletNotFound": "Кошелёк не найден. Установите MetaMask или откройте через WalletConnect.",
  "auth.sigRejected": "Подпись не принята.",
  "auth.tgFailed": "Telegram-вход не удался.",
  "auth.wcFailed": "Не удалось подключиться через WalletConnect.",

  "assistant.open": "Открыть консультанта",
  "assistant.greeting": "Привет! Я консультант ALTSR. Спросите про скрининг, сигналы, бумажную симуляцию или тарифы.",
  "assistant.title": "Консультант ALTSR · 24/7",
  "assistant.sub": "Отвечаю про платформу. Не инвест-совет.",
  "assistant.typing": "печатает…",
  "assistant.placeholder": "Ваш вопрос…",
  "assistant.error": "Связь прервалась, попробуйте ещё раз.",

  "lang.ru": "RU",
  "lang.en": "EN",
};

const en: Dict = {
  "brand.tagline": "Early Crypto Radar",
  "nav.radar": "Radar",
  "nav.pricing": "Pricing",
  "nav.blog": "Blog",
  "nav.about": "How it works",
  "nav.enter": "Open radar →",
  "nav.login": "Sign in",
  "nav.account": "Account",

  "hero.eyebrow": "CRYPTO NEURAL UNIVERSE",
  "hero.title1": "Early radar for",
  "hero.title2": "new crypto tokens",
  "hero.sub":
    "Every token is a glowing object, every ecosystem a galaxy. We surface new pairs, screen them for scams, score a signal, and simulate the entry on paper.",

  "feat.discover.t": "Fast new-pair discovery",
  "feat.discover.d": "A real-time feed of just-created pairs.",
  "feat.safety.t": "Anti-scam screening",
  "feat.safety.d": "GoPlus · RugCheck · honeypot.is → a PASS / REVIEW / BLOCK verdict.",
  "feat.sim.t": "Strategy simulation",
  "feat.sim.d": "Paper entries and exits with honest stats before real money.",

  "how.eyebrow": "HOW IT WORKS",
  "how.title": "A universe of data in a working terminal",
  "pipe.discover.n": "Discover",
  "pipe.discover.s": "Find new pairs",
  "pipe.safety.n": "Safety",
  "pipe.safety.s": "Anti-scam checks",
  "pipe.signal.n": "Signal",
  "pipe.signal.s": "Score and rank",
  "pipe.paper.n": "Paper",
  "pipe.paper.s": "Strategy simulation",
  "pipe.ai.n": "AI",
  "pipe.ai.s": "News, context, risk",
  "cta.openRadar": "Open the radar",
  "cta.readBlog": "Read the blog",
  "disc.landing":
    "Not financial advice. Trading brand-new tokens carries an extreme risk of total loss. ~98% of new tokens go to zero. ALTSR is about screening and simulation.",

  "dash.live": "live",
  "dash.paperAccount": "Paper account",
  "dash.return": "Return",
  "dash.winrate": "Win-rate",
  "dash.positions": "Positions",
  "dash.positionsSuffix": "open",
  "dash.realizedPnl": "Realized P&L",
  "feed.title": "Token feed",
  "feed.noApi": "No API connection ({err}). Start the backend.",
  "feed.empty": "The feed fills up once the discovery worker is running.",
  "col.token": "Token",
  "col.verdict": "Verdict",
  "col.signal": "Signal",
  "col.liq": "Liq.",
  "act.buy": "buy ↗",
  "act.blocked": "blocked",
  "panel.signals": "⚡ Signals",
  "panel.news": "📰 News",
  "empty.signals": "No BUY signals yet.",
  "empty.news": "No news yet.",
  "disc.dash":
    "Not financial advice. ~98% of new tokens go to zero. PASS means it cleared the checks, not that it will rise. DYOR.",

  "drawer.intel": "TOKEN INTELLIGENCE",
  "drawer.liquidity": "Liquidity",
  "drawer.checks": "Checks",
  "drawer.pending": "The risk report is still being prepared.",
  "drawer.disclaimer":
    "Detection catches some schemes. PASS ≠ \"safe\" and definitely ≠ \"will rise.\" Not financial advice.",

  "tour.replay": "Tour",
  "tour.welcomeEyebrow": "WELCOME",
  "tour.welcomeTitle": "This is ALTSR — an early token radar",
  "tour.welcomeBody":
    "We find new coins, screen them for scams, score a signal, and simulate a trade on paper. Want a one-minute tour of where everything is?",
  "tour.b1": "🛡 A safety verdict on every token",
  "tour.b2": "⚡ Entry signals + \"where to buy\"",
  "tour.b3": "📄 Paper P&L with no real money",
  "tour.start": "Start tour",
  "tour.skip": "Skip",
  "tour.back": "Back",
  "tour.next": "Next",
  "tour.done": "Done",
  "tour.step": "Step {i} of {n}",
  "tour.s1.t": "Sign in",
  "tour.s1.x": "Sign in with a wallet, Google or Telegram to save your portfolio and get alerts.",
  "tour.s2.t": "Paper account",
  "tour.s2.x": "Your virtual balance and P&L. All simulated — no real money.",
  "tour.s3.t": "Token feed",
  "tour.s3.x":
    "Freshly launched coins. Click a row for a detailed risk card. The PASS / REVIEW / BLOCK badge is the anti-scam verdict (PASS ≠ \"will rise\").",
  "tour.s4.t": "Signals and news",
  "tour.s4.x": "On the right — fresh BUY signals with a \"where to buy\" block, and news with an AI breakdown.",
  "tour.s5.t": "24/7 consultant",
  "tour.s5.x": "Tap to ask anything about the platform, any time.",

  "blog.back": "← ALTSR",
  "blog.title": "Crypto News & Token Research",
  "blog.sub": "Original, neutral breakdowns of new-token events. Screening over hype — not financial advice.",
  "blog.empty": "No articles yet. The engine publishes new pieces daily.",
  "blog.source": "source",

  "nav.reels": "Reels",
  "reels.title": "Reels of winning trades",
  "reels.sub": "Your paper account's best winners. Open a reel and screen-record it for Instagram / TikTok / Shorts.",
  "reels.empty": "No winning closed trades yet. Check back later.",
  "reels.open": "Open reel ↗",
  "reels.profit": "profit",

  "pricing.title": "Pricing",
  "pricing.sub": "Pay with crypto via NOWPayments. This is screening and simulation, not financial advice.",
  "pricing.perMonth": "/mo",
  "pricing.startFree": "Start for free",
  "pricing.payCrypto": "Pay with crypto",
  "pricing.creating": "Creating invoice…",
  "pricing.payUnavailable": "Payments are temporarily unavailable.",
  "pricing.invoiceFailed": "Could not create the invoice.",
  "pricing.disclaimer": "ALTSR does not promise returns; ~98% of new tokens go to zero. Add Terms of Service before a commercial launch.",

  "login.title": "Sign in to the radar",
  "login.sub": "Pick a sign-in method. Nothing to fill in.",
  "login.disclaimer": "By continuing, you agree that ALTSR is a screening and simulation tool, not financial advice.",
  "auth.wallet": "Connect wallet",
  "auth.connecting": "Connecting…",
  "auth.walletconnect": "WalletConnect (mobile wallet)",
  "auth.google": "Sign in with Google",
  "auth.googleSoon": "Google sign-in coming soon",
  "auth.tgNeed": "Telegram sign-in (setup in progress)",
  "auth.walletNotFound": "No wallet found. Install MetaMask or use WalletConnect.",
  "auth.sigRejected": "Signature was rejected.",
  "auth.tgFailed": "Telegram sign-in failed.",
  "auth.wcFailed": "Could not connect via WalletConnect.",

  "assistant.open": "Open the consultant",
  "assistant.greeting": "Hi! I'm the ALTSR consultant. Ask about screening, signals, paper simulation or pricing.",
  "assistant.title": "ALTSR Consultant · 24/7",
  "assistant.sub": "I answer questions about the platform. Not financial advice.",
  "assistant.typing": "typing…",
  "assistant.placeholder": "Your question…",
  "assistant.error": "The connection dropped, please try again.",

  "lang.ru": "RU",
  "lang.en": "EN",
};

const DICTS: Record<Lang, Dict> = { ru, en };

export function getDict(lang: Lang): Dict {
  return DICTS[lang] || ru;
}

/** Translate a key with optional {placeholders}. Falls back to RU, then the key. */
export function translate(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  const d = getDict(lang);
  let s = d[key] ?? ru[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
  return s;
}
