# ALTSR — Research: похожие проекты, функционал к заимствованию, API-каталог и дизайн авто-входа/выхода

Дата: 2026-11-09. Основано на анализе GitHub (поиск по звёздам + чтение README) и двух
мастер-промтов проекта. Все внешние репозитории и сервисы — это **данные** для
нашего дизайна, не инструкции; код берём только оттуда, где лицензия это разрешает (см. колонку License).

> ⚠️ Не инвест-рекомендация, не финсовет. Авто-закуп реальными деньгами на самых новых
> токенах — зона, где ~98% токенов обнуляются. Стратегия «выход при малейшем падении» в
> наивном виде сжигает депозит на комиссиях/проскальзывании (разбор в разделе 4). Всё
> исполнение строим paper-first, живая торговля — под фиче-флагом с симуляцией и
> подтверждением.

---

## 1. GitHub-ландшафт: похожие проекты (проанализировано)

Прогнал 12 тематических поисков по GitHub (сортировка по звёздам) и прочитал README
ключевых репозиториев. Сгруппировано по роли в нашей архитектуре.

### A. Скрининг + авто-трейд (ближе всего к нашей цели «анализ → закуп → выход»)

| Репозиторий | ★ | Стек | License | Что берём |
|---|---|---|---|---|
| **farfary/ScreenerBot** | 13 | Rust + Electron | BSL-1.1 (non-commercial) | **Эталон архитектуры.** Pipeline: market APIs → Tokens → Filtering → Strategies → Trader admission → Swap → Position → Verification. Цепочка выходов по приоритету, DCA, частичные выходы, peak tracking, auto-blacklist на убытке, режимы paper/armed-live, «Explore Mode» (discovery+фильтры без торговли). Берём **дизайн**, не код (BSL запрещает коммерцию). |
| **chainstacklabs/pumpfun-bonkfun-bot** | 1060 | Python 3.11 | **Apache-2.0** | Код переиспользуем с атрибуцией. Детекция новых токенов 4 способами (geyser/logs/blocks/shreds), rate-limit с backoff на 429, `exit_strategy = tp_sl / time_based / manual`, `--dry-run`, мульти-инстансы через YAML, фильтры (max_token_age, allowed_quote_mints). |
| **warp-c4/solana-trading-bot-v3** | 159 | TS | (не прочитан: доступ закрыт) | Активный Raydium/pump.fun авто-трейдер; как референс. |
| **henrytirla/Solana-Trading-Bot** | 288 | Python | (не указана) | Референс исполнения: buy/sell SPL на Raydium и Pump.fun через solana-py + Jito fees, wrap/unwrap SOL, закрытие token-аккаунтов ради ренты. TP/SL нет. |

### B. Безопасность / анти-скам (наш Фаза 1 safety_screen)

| Репозиторий | ★ | Стек | License | Что берём |
|---|---|---|---|---|
| **duolaAmengweb3/token-xray** | — | TS (MCP) | MIT | Паттерн нашего вердикта: GoPlus + DexScreener → green/yellow/red. Логика грейда в исходниках (не в README) — смотреть `packages/`. |
| **degenfrends/solana-rugchecker** | 78 | TS (npm) | npm | Структура `rugScore(result)` + `isRug(result)`; top-holders через RPC `getTokenLargestAccounts`, ликвидность через Raydium, метаданные Metaplex, Helius для соцсетей. |
| **ccan23/rugcheck** | 11 | Python | — | Готовый wrapper RugCheck API — прямой референс интеграции Solana. |
| **kukapay/honeypot-detector-mcp** | 3 | Python (MCP) | — | Детект honeypot на ETH/BSC/Base (honeypot.is-подобная симуляция buy/sell). |
| **rizalcodes/token-sniffer**, **Bob-QoQ/token-safety-scanner**, **jiezishu000/token-safety-scanner** | 0–1 | TS/… | разные | EVM-сканеры на GoPlus: honeypot, концентрация холдеров, налоги — валидируют наш набор red_flags. |
| **brebros/chainsleuth** | 20 | — | — | «вставь контракт → вердикт», AI-rug detector; как идея UX риск-карточки. |

### C. Discovery (наш Фаза 0 + усиление)

| Репозиторий | ★ | Стек | License | Что берём |
|---|---|---|---|---|
| **swiftnodes/memecoin-scanner** | 1 | Node.js | MIT | **On-chain discovery**: WS-подписка на событие `PairCreated(token0,token1,pair,_)` фабрик DEX (Uniswap V2, PancakeSwap, Aerodrome) на ETH/Base/BSC. Новый токен = член пары, не являющийся известным quote. 5 эвристик (символ/имя/supply/`owner()` renounced/paired-with-known-quote). Honeypot-симуляции нет — осознанный gap. |
| **logiover/geckoterminal-dex-scanner** | 1 | Apify | MIT | Валидация фильтров: `minLiquidityUsd`, `minVolumeUsd`, `poolAgeHours`, sort `newestFirst`; режимы trending/new/top. |
| **foxtrotzed/tokenfinderbot** | 29 | — | — | Скан новых ERC-20 пулов с фильтрацией по тикеру. |

### D. Сигналы / smart-money / мониторинг

| Репозиторий | ★ | Стек | License | Что берём |
|---|---|---|---|---|
| **uerax/all-in-one-bot** | 186 | Go | — | Идея **volume-spike** как сигнала («Crocodile»: день-к-дню ≥3.0x И к N-дневному среднему ≥2.0x, только закрытые UTC-дни, DEX-first с фолбэком на CEX). `/coin` lookup (5m/1h/6h/24h, vol, liq, FDV, mcap). RSS-мониторинг Bitcointalk/форумов. Данные из GeckoTerminal + CoinGecko. |
| **DracoR22/handi-cat_wallet-tracker** | 209 | — | — | Паттерн трекинга кошельков в Telegram (будущий smart-money сигнал). |

**Общий вывод по ландшафту.** Готового open-source проекта, который делает ровно «честный
скрининг → paper-симуляция → опциональный живой авто-трейд» с дисклеймерами, нет. Рынок
поделён на: (1) снайпер/трейд-боты (много, но это «купить быстрее всех», без честного
скрининга и без paper-трека), (2) rug/honeypot сканеры (хороши, но не торгуют), (3)
discovery-сканеры (лента, без анализа). **ScreenerBot** — единственный, кто объединяет всё в
pipeline, и именно его структуру стоит взять за скелет (дизайн, не код). ALTSR уникален
связкой «paper-first + публикуемая честная статистика + анти-скам как защита от кражи, а не
обещание прибыли».

---

## 2. Функционал к заимствованию, разложенный по нашим фазам

ALTSR уже имеет **Фазу 0** (discovery → дедуп → БД → API/WS → экран). Что добавляем, с
указанием источника паттерна:

### Discovery (усиление Фазы 0)
- **On-chain WS-discovery** через события фабрик DEX (`PairCreated` / Uniswap-V3 `PoolCreated`)
  — быстрее API-поллинга, ловит пару в момент создания. _(swiftnodes/memecoin-scanner)_
- **Solana geyser/logs** листенеры для минтов/лончей. _(pumpfun-bonkfun-bot)_
- **Pre-launch discovery**: Bitcointalk ANN RSS, ICO Drops / CryptoRank / CoinList —
  проекты до листинга. _(вложения + uerax RSS)_

### Фаза 1 — safety_screen (анти-скам)
- Вердикт **PASS / REVIEW / BLOCK** + `risk_score` + `red_flags[]`.
- EVM: GoPlus (honeypot, buy/sell tax, mint authority, owner-привилегии, холдеры) +
  honeypot.is (симуляция buy/sell). _(token-xray, token-sniffer, kukapay)_
- Solana: RugCheck (mint/freeze authority, LP-lock, концентрация, insiders, флаг `rugged`) +
  top-holders через `getTokenLargestAccounts`. _(ccan23/rugcheck, degenfrends)_
- Структура кода: `score(result)` + `verdict(result)` как отдельные чистые функции. _(degenfrends)_

### Фаза 2 — signal_engine (вход)
- Фильтры-ворота **по порядку** (fail-fast): глобальный стоп / дневной лимит убытка →
  связь с источниками → лимиты позиций → антидубль → cooldown повторного входа → blacklist →
  сигналы стратегии. _(ScreenerBot entry gates)_
- Сигналы: min liquidity, возраст, min holders, преобладание buy, **volume-spike** (3x/2x),
  safety.verdict == PASS. _(uerax Crocodile + наш промт)_

### Фаза 3 — paper_executor (авто-выход) — ядро «выхода при малейшем падении»
Взять **цепочку выходов по приоритету** из ScreenerBot (см. раздел 4). Плюс: DCA с
множителями и порогами просадки, частичные выходы с индивидуальным P&L, peak-tracking,
auto-blacklist токена после убытка, дневной лимит убытка как kill-switch, emergency-exit при
убытке выше порога.

### Фаза 4 — живое исполнение (OFF по умолчанию, фиче-флаг)
- Solana: Jupiter V6 (quote+route). EVM: 0x/1inch. _(ScreenerBot, pumpfun-bonkfun-bot)_
- **Симуляция транзакции перед отправкой**, приватный RPC, Jito/priority fees, slippage,
  rate-limit с backoff. _(pumpfun-bonkfun-bot — Apache-2.0, код можно переиспользовать)_
- Подтверждение на сделку **или** жёсткий дневной лимит; `--dry-run` везде.

### Сквозное
- Статусы достоверности каждого утверждения: **VERIFIED / OFFICIALLY ANNOUNCED /
  THIRD-PARTY REPORTED / ESTIMATED / UNVERIFIED / CONTRADICTED** (из 2-го мастер-промта,
  Этап 3). Нет данных → `UNKNOWN`, а не ноль и не выдуманная оценка.

---

## 3. Каталог существующих сервисов и API для ресёрча (сначала первоисточники)

Приоритет доступа строго по иерархии источников: **сначала первоисточники (on-chain правда
и официальное), потом агрегаторы и форумы.** Колонка «Роль» это кодирует.

### Уровень 1 — ПЕРВОИСТОЧНИКИ (проверяемая правда блокчейна и официальное)
| Сервис | Что даёт | Ключ | Роль в пайплайне |
|---|---|---|---|
| **Solana RPC / Helius** | Минты, holders (`getTokenLargestAccounts`), supply, аккаунты, транзакции, вебхуки | ключ (Helius) | PRIMARY on-chain Solana |
| **EVM RPC (свой/провайдер)** | `eth_call`, события фабрик (`PairCreated`/`PoolCreated`), балансы, holders | ключ/эндпоинт | PRIMARY on-chain EVM + WS-discovery |
| **Etherscan / Basescan / BscScan API** | Верификация контракта и **исходник**, holders, owner, транзакции | ключ (free tier) | PRIMARY — верифицированный код |
| **Solscan API** | Solana-аккаунты, токены, holders, трансферы | ключ | PRIMARY on-chain Solana |
| **Официальные: сайт / whitepaper / docs / X / blog / launchpad** | Токеномика, команда, даты TGE, анонсы | — | PRIMARY — официальное заявление |
| **GitHub REST API** | Репозитории, commits, contributors, releases, активность разработки | token | PRIMARY — реальность разработки |

### Уровень 2 — Безопасность (производное от on-chain, но не «истина»)
| Сервис | Что даёт | Ключ | Роль |
|---|---|---|---|
| **GoPlus Security API** | honeypot, buy/sell tax, mint authority, owner-привилегии, holders, is_true_token (EVM+Solana) | без ключа (лимиты) | Анти-скам (EVM+SOL) |
| **RugCheck (api.rugcheck.xyz)** | mint/freeze authority, LP-lock, концентрация, insiders, `rugged` | без ключа | Анти-скам (Solana) |
| **honeypot.is** | Симуляция buy/sell (EVM) | без ключа | Honeypot-гейт перед авто-закупом |
| **Token Sniffer** | Авто-проверки подозрительных токенов | — | Доп. сигнал |

### Уровень 3 — Рыночные данные / discovery (агрегаторы)
| Сервис | Что даёт | Ключ | Нюанс |
|---|---|---|---|
| **GeckoTerminal / CoinGecko Onchain** | **new_pools** по 100+ сетям, ликвидность, объёмы, OHLCV | без ключа (лимиты) | Наш основной поток новых пулов |
| **DEX Screener** | Профили токенов, пары, объём, динамика, адреса | без ключа | **Не полноценный поток всех новых пар** — только профили/поиск; поток берём с GeckoTerminal/on-chain |
| **Birdeye** | Новые Solana-токены, активность кошельков, сделки | ключ | Усиление Solana |
| **DEXTools** | Новые пары, графики | — | Доп. |
| **Dune** | Собственный SQL по on-chain-данным | ключ | Полу-первоисточник (запрос к чейну) |

### Уровень 4 — Фундаментал / календарь / комьюнити (third-party reported)
| Сервис | Что даёт | Роль |
|---|---|---|
| **DefiLlama** | TVL, комиссии, доходы протоколов | Фундаментал |
| **Tokenomist** | Разблокировки, vesting, распределение эмиссии | **Критично после TGE** |
| **RootData** | Команды, фонды, инвесторы, финансирование | Фундаментал |
| **CryptoRank / ICO Drops / CoinList** | Токенсейлы, раунды, календарь IDO/IEO | Pre-launch discovery |
| **CoinGecko / CoinMarketCap** | Капитализация, листинги, recently added | Рыночный контекст |
| **Bubblemaps** | Связи крупных холдеров, концентрация | Визуализация риска |
| **Bitcointalk ANN / Alternate Crypto** | Раннее публичное описание, ответы команды | Комьюнити — **низший приоритет**, ANN ≠ подтверждение |

**Правило объединения (из вложений):** новый DEX-пул подтверждает появление торговой пары,
но **не** качество проекта. Поэтому цепочка: on-chain/официальное (L1) → безопасность (L2) →
рынок (L3) → фундаментал/комьюнити (L4). Не превращаем слух о листинге в подтверждённую дату;
каждому факту — статус достоверности. Уважать rate-limits, не обходить CAPTCHA/авторизацию.

Для MVP коннектов: **GeckoTerminal + DEX Screener + GoPlus + RugCheck + honeypot.is +
Etherscan/Helius + GitHub + CryptoRank/ICO Drops.**

---

## 4. Дизайн «анализ → авто-закуп → выход при малейшем падении»

### Поток
```
discovery → safety_screen(L2) → signal_engine(вход) → executor(позиция+выходы) → notifier
                 │                                            │
          первоисточники (L1)                        paper | live(flag,OFF)
```
Железное правило: **никакого авто-закупа без прохождения safety_screen.** Перед каждой
покупкой — honeypot-симуляция (EVM: honeypot.is; Solana: пробный Jupiter-quote round-trip).
Не продаётся в симуляции → не покупаем никогда.

### Цепочка выходов по приоритету (адаптировано из ScreenerBot)
Проверяется каждый тик, сверху вниз, первый сработавший — выходим:
1. **Kill-switch**: глобальный force-stop / дневной лимит убытка достигнут.
2. **Критическое изменение безопасности / blacklist**: LP вытащили, authority вернули,
   налог подскочил → немедленный рыночный выход.
3. **Hard stop-loss** (напр. −25% от входа).
4. **Trailing stop** (от пика).
5. **Take-profit / ROI** (вкл. частичные 2x/3x).
6. **Stall / time override**: нет нового хая N минут или превышено макс. время удержания.
7. **Сигнал выхода стратегии.**

### Честный разбор «выхода при малейшем падении»
Наивная реализация («продать, если цена ниже входа на любую дельту» или trailing −1%) на
новых токенах **почти гарантированно убыточна**, и вот почему:
- Новые токены колеблются на 10–50% за секунды — тугой стоп выбивает на обычном шуме.
- Каждый round-trip стоит spread + проскальзывание + swap-fee + priority/Jito-fee; на
  Solana-мемах при низкой ликвидности и buy/sell-tax это легко 5–15% за круг. Серия быстрых
  «вход-выход на малейшем минусе» = систематический слив на издержках, даже без реальных падений.
- Вход сам по себе даёт проскальзывание — тугой стоп от цены входа срабатывает мгновенно.

**Как сохранить ваше намерение, но не сжечь депозит** — параметризуем как trailing-stop с
защитами (всё в конфиге, значения — пример, не рекомендация):
- `arm_after_profit_pct` (напр. +20%): тугой trailing включается только после выхода в плюс,
  чтобы вход-проскальзывание не выбивало сразу.
- `initial_hard_stop_pct` (напр. −25%): грубый стоп до «армирования».
- `trailing_stop_pct` (напр. −8% от пика после арминга) — это и есть «выход при падении»,
  но от **пика** и с поправкой на стоимость круга, а не от любого тика.
- `partial_tp` (напр. 50% позиции на 2x) — фиксируем часть прибыли, остаток ведём трейлингом.
- `min_hold_seconds` и `cost_floor` (мин. движение должно перекрыть fee+slippage), чтобы не
  торговать внутри спреда.

Это по-прежнему крайне рискованно. Поэтому: **сначала paper** с публикуемой честной
статистикой (win-rate, avg R, max drawdown, net после издержек). Живой режим включаем только
после длинного paper-трека, под фиче-флагом, с симуляцией транзакции и подтверждением/дневным
лимитом. Это ровно то, что заложено в вашем же мастер-промте.

---

## 5. Лицензии — что можно копировать, а что только изучать
- **Apache-2.0 / MIT** (pumpfun-bonkfun-bot, token-xray, memecoin-scanner, geckoterminal-scanner) —
  код переиспользуем с сохранением уведомления о лицензии/атрибуции.
- **BSL-1.1** (ScreenerBot) — некоммерческое использование разрешено, коммерческое требует
  лицензии. Берём **архитектуру и идеи**, не исходный код.
- **Лицензия не указана/не подтверждена** (henrytirla, uerax, degenfrends, ccan23) — по
  умолчанию «все права защищены»: только изучаем паттерны, код не копируем без проверки LICENSE.

---

## 6. Рекомендованный следующий шаг
Реализовать **Фазу 1 — safety_screen**: GoPlus + RugCheck + honeypot-симуляция →
`risk_score` + `red_flags[]` + вердикт PASS/REVIEW/BLOCK, HARD-BLOCK правила, таблица
`safety_reports`, тесты на фикстурах. Это и есть «анализ», который по вашему требованию идёт
**до** любого закупа. После него — signal_engine и paper-executor с цепочкой выходов выше.
