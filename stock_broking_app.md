# TiltLock — Low-Level Design, Deployment & Team Plan

> **Working name:** *TiltLock* (a TradeGuard-style paper broker). Rename freely — several existing
> products use the TradeGuard name, so pick something ownable before the demo video.
> **Team:** 2 people · **Deadline:** Fri Nov 27, 11:59 PM IST (confirm on hackathon Slack) · **Repo init:** Nov 21 ✓ (rule: ≥ Nov 12)

**One-line pitch:** a paper-trading stock broker with a discipline engine — hard guardrails that
physically block bad trading — where every feature is verified end-to-end by a coding-agent + Kane CLI loop,
triggerable from a prompt inside the app itself.

**Hackathon mapping:** Ships (working broker) · Verified (Kane flows over all guardrails) ·
Closed loop (prompt → agent change → Kane run → verdict fed back) · Craft (the ops console).

---

## Table of contents

1. [System architecture](#1-system-architecture)
2. [Monorepo layout](#2-monorepo-layout)
3. [Low-level design per component](#3-low-level-design-per-component)
4. [Database schema](#4-database-schema)
5. [API surface](#5-api-surface)
6. [Hosting & deployment on EC2](#6-hosting--deployment-on-ec2)
7. [Services & command cheat sheet](#7-services--command-cheat-sheet)
8. [Responsibility split (2 people)](#8-responsibility-split)
9. [Kane verification plan](#9-kane-verification-plan)
10. [Timeline: Nov 21 → 27](#10-timeline)
11. [Submission checklist](#11-submission-checklist)
12. [Open decisions](#12-open-decisions)

---

## 1. System architecture

```
                        INTERNET
                           │
                           ▼  ports 80/443 only
                 ┌──────────────────┐
                 │   EC2 (Ubuntu)   │
                 │                  │
   browser ────▶ │  nginx           │
                 │   ├── static     │  frontend/dist (React build, no dev server!)
                 │   └── /api/* ────┼──▶ uvicorn 127.0.0.1:8000 (FastAPI backend)
                 │                  │        │
                 │                  │        ├── SQLite file (EBS) ── $0, no service
                 │                  │        ├── PriceEngine (in-memory ticks)
                 │                  │
                 │   [admin-only, via app auth]          │
                 │   Change Loop:                       │
                 │     POST /api/ops/change-request      │
                 │        ├──▶ `opencode run "<prompt>"` │  ← agent edits code, uses
                 │        │     (OpenCode's own auth —   │    OpenCode's stored key,
                 │        │      NO key in our app)      │    never ours
                 │        ├──▶ git commit (auto)         │
                 │        └──▶ `kane-cli testmd run` ────┤  NDJSON verdict
                 │                  │        │           │    back to the page
                 └──────────────────┘        ▼           ▼
                                       verdict shown on the Ops page
```

**Rules of the architecture:**

- One repo, two deployables (backend process + static frontend). "Separate frontend/backend" =
  separate processes and packages, not separate repos (hackathon allows one submission per team).
- The browser only ever talks to nginx. Uvicorn binds to localhost. Kane drives the same public URL.
- The **only** exposed surface is the app. The agent (`opencode`) and Kane run as subprocesses on
  the box — neither is ever exposed as an HTTP service.
- The LLM API key lives **inside OpenCode's own config** on the EC2 user account
  (set up once via SSH). Our app code, env files and repo never contain it.
- Every module is a package with a pure-logic core (`service.py` / `engine.py`) and a thin
  adapter (`api.py`). Future microservice extraction = lift the package, swap direct calls for HTTP.

---

## 2. Monorepo layout

```
tiltlock/
├── DESIGN.md                  ← this file
├── PRD.md                     ← requirements + acceptance criteria (input to kane-cli design tests)
├── README.md                  ← setup, demo logins, one-command run (judges read this)
├── .env.example               ← every var, values empty; real .env is gitignored
├── backend/
│   ├── pyproject.toml         ← fastapi, uvicorn, sqlalchemy, pytest
│   └── app/
│       ├── main.py            ← FastAPI app; mounts routers; starts price tick task
│       ├── core/              ← config (env), db session/engine (WAL mode), constants
│       ├── auth/              ← service.py + api.py (signup/login/sessions)
│       ├── engines/
│       │   ├── prices/        ← engine.py (simulator) + api.py (quotes)
│       │   ├── orders/        ← service.py (lifecycle) + api.py
│       │   ├── guardrails/    ← rules.py (pure evaluate()) + api.py (status)
│       │   ├── ledger/        ← service.py (holdings/cash/P&L) + api.py (portfolio)
│       │   └── reporting/      ← api.py (order history)
│       ├── ops/               ← agent_runner.py + kane_bridge.py + api.py (admin routes)
│       ├── models.py          ← SQLAlchemy models (single source of truth)
│       ├── seed.py            ← instrument master + 3 personas; `python -m app.seed`
│       └── tests/             ← pytest: guardrail decisions, ledger invariants
├── frontend/
│   ├── package.json           ← vite + react + a chart lib (lightweight-charts or recharts)
│   └── src/
│       ├── api/client.ts      ← typed fetch wrappers (generated from OpenAPI)
│       ├── pages/              ← Login · Dashboard · StockDetail · Portfolio ·
│       │                          Orders · Discipline · Ops(admin)
│       └── components/         ← OrderTicket · QuoteTable · GuardrailBanner · Toast
└── kane/
    ├── tests/                 ← *_test.md flows (PRD-derived, committed)
    └── output-*/              ← replay recordings (committed per Kane docs)
```

---

## 3. Low-level design per component

Format per component: **Files · Responsibility · Core logic · Invariants · Edge cases**.

### 3.1 Auth & personas

| | |
|---|---|
| Files | `auth/service.py`, `auth/api.py`, `models.py` (users, sessions) |
| Responsibility | signup/login/logout, server-side session tokens, persona accounts |
| Core logic | signup: create user + **credit $100,000** (signup_credit txn) + default rules row. Login: verify hash (bcrypt), create session token (uuid4), set httpOnly cookie. Every request: cookie → session → user. |
| Personas | `fresh@demo` (clean) · `tilted@demo` (−$9,700 realized today, 9/10 trades) · `cooldown@demo` (3 straight losses, ~25 min cooldown left) — all password `demo1234`, listed in README for judges |
| Logins & passwords | **Username = email.** One `users` table for everyone (the `role` column separates traders from admins — no second table); passwords stored as bcrypt **hashes only**, never plaintext or logs; session = uuid4 token in an httpOnly cookie, row in `sessions` with expiry |
| Admin accounts | Seeded on the box from env vars `ADMIN_EMAILS` / `ADMIN_PASSWORD` (see §6.5) — **admin credentials live only on EC2, never in the repo or README** (the repo is public for judges). No endpoint can promote a user to admin |
| Signup policy | **Open signup — no invite system in v1.** Why: Kane flow #1 signs up mid-run, judges must be trading in <30 s, and invites are extra surface for zero judging credit. If this grows into a real product: add an `invite_codes` table + admin-generate endpoint (broker-style onboarding) |
| Edge cases | httpOnly + SameSite=Lax cookie (Kane's browser handles it like a normal user) · duplicate email → "email already registered" (assertable text) · demo personas are role `trader` — Ops routes 403 for them |

### 3.2 Market data engine — *future microservice #1 ("stock details updator")*

| | |
|---|---|
| Files | `engines/prices/engine.py`, `engines/prices/api.py` |
| Responsibility | all prices; deterministic; zero external calls |
| Core logic | In-memory dict per symbol: `price`. Tick every **3 s** via asyncio task: `price *= (1 + vol · gauss(rng(seed, tick#)))`. Seeded per symbol in `stocks` table → **same series every boot within a session**. 120 back-candles generated at boot from the same seed for charts. |
| Endpoints | `GET /api/stocks` (list + last price), `GET /api/stocks/{symbol}` (quote + candles) |
| Invariants | price never ≤ 0 (clamp) · ticks NEVER touch the DB (write volume stays human-paced) |
| Edge | unknown symbol → 404 `{detail: "unknown symbol"}` (Kane asserts this too) |

### 3.2b Instrument profiles & fundamentals (content data)

Rich per-stock detail page — everything simulated and seeded, zero external calls, no new runtime risk.

| | |
|---|---|
| Files | `engines/prices/fundamentals.py` (static lookups + derived math), served through the same `engines/prices/api.py` |
| Responsibility | company profile, live-derived valuation metrics, quarterly results for the bar chart |
| Stored (seeded once per symbol) | sector · 1–2 line description · annual EPS · shares outstanding · 52-week high/low · founded year |
| **Derived live** — moves with the sim price, like a real broker | **P/E = price ÷ EPS** (renders "—" when EPS ≤ 0) · **market cap = shares outstanding × price** · current price's position within the 52-wk range |
| Financials | 8 seeded quarters per symbol: revenue + net profit; a loss quarter renders as a negative bar — realistic and chart-friendly |
| Endpoint | folded into the existing `GET /api/stocks/{symbol}` → one response with quote + candles + profile + financials (frontend makes one call) |
| Kane value | visible labels: company name, sector, "P/E", "Market cap", "Quarterly results" → flow #11. Assert **presence and format, never exact P/E values** — the price ticks, so exact-number assertions would be flaky |
| Scope guard | ~1 h backend (2 tables + seed rows) + one bar-chart component on the existing StockDetail page. It must **not** displace guardrail work; if Sunday runs long this slips to Tuesday, never the core |

### 3.3 Order engine

| | |
|---|---|
| Files | `engines/orders/service.py`, `engines/orders/api.py` |
| Responsibility | the heart: validation → guardrail gate → fill → ledger update, atomically |
| Lifecycle | `NEW → [guardrails] → blocked` or `→ [validation] → rejected` or `→ FILLED` |
| Core logic | `place_order(user, symbol, side, qty)`: ① `guardrails.evaluate(...)` — block wins, nothing else runs ② validation (qty ≥ 1 integer; buy: cash ≥ qty·price; sell: holdings ≥ qty) ③ fill at engine price inside ONE DB transaction: insert order (status filled, filled_price, realized_pnl for sells), update holdings (weighted avg cost on buy; reduce on sell), insert cash txn (signed, balance_after) ④ recompute guardrail state ⑤ return order |
| Order types | v1: market only. `order_type` column exists so limit orders are additive later |
| Rejected reasons | `"Rejected: insufficient cash"` · `"Rejected: insufficient shares"` · `"Rejected: invalid quantity"` |
| Invariant | for every filled order: `Δcash + Δholdings_value = 0` on buy, and sell books `realized_pnl = qty·(price − avg_cost)` |

### 3.4 Guardrails engine — **the differentiator**

| | |
|---|---|
| Files | `engines/guardrails/rules.py` (pure), `engines/guardrails/state.py` (derives state), `engines/guardrails/api.py` |
| Interface | `evaluate(order, gstate, rules) → Decision(allowed: bool, rule: str, reason: str)` — **pure**, no DB, no clock (timestamps passed in) |
| State | `gstate` derived from today's filled orders: realized_pnl_sum, trades_used, last_3_sells, open_position_count, cooldown_until, equity |
| Rules (defaults) | ① **Kill switch**: realized loss today ≥ $10,000 → lock everything ② **Tilt cooldown**: last 3 sells all losses → lock 30 min (cooldown_until = ts of 3rd loss + 30) ③ **Overtrade cap**: 10 filled trades/day ④ **Position size cap**: buy cost > 20% of equity ⑤ **Max open positions**: 5 |
| Check order | kill switch → cooldown → trade cap → size cap → open positions (lock rules first, caps second) |
| **Reason strings (single source of truth — `core/constants.py`; frontend displays as-is, Kane asserts substrings, pytest asserts equality)** | `Blocked: daily loss limit reached. Trading locked until tomorrow.` · `Blocked: cooldown active after 3 consecutive losses. Try again in {mm:ss}.` · `Blocked: daily trade limit reached (10/10).` · `Blocked: order exceeds position size cap (20% of equity).` · `Blocked: max open positions reached (5).` |
| Edge cases | blocked attempts do **not** count toward the trade cap (only fills do) · v1 kill switch blocks buys AND sells (documented simplification; v2 allow reduce-only sells) · "today" = `date(created_at)`; see daily-reset gotcha in §6.6 |
| Why pure | trivially unit-testable (pytest covers every rule × state combo) and trivially explainable in the demo video |

### 3.5 Ledger & portfolio — *future microservice #2 ("portfolio of user & each stocks")*

| | |
|---|---|
| Files | `engines/ledger/service.py`, `engines/ledger/api.py` |
| Responsibility | cash balance, holdings, P&L — the books |
| Core logic | `portfolio(user)`: holdings joined with live prices → per-position unrealized P&L; cash from last txn `balance_after`; equity = cash + Σ(qty·price) |
| Invariants | `balance_after` always written (audit trail replays to current balance) · holdings row deleted at qty 0 |
| Edge | float money: store cents/round to 2 dp at write time; frontend formats only |

### 3.6 Reporting

`GET /api/orders` (desc, limit 50) with reason/filled price · `GET /api/guardrails/status` → per-rule
`{used, limit, remaining, locked}` for the Discipline page. Every backend state change must appear as
**text on screen** (toast/banner/row) — Kane can only assert what renders.

### 3.7 Change Loop Console — *prompt-to-change inside the app (their #4)*

**Purpose:** the hackathon's centerpiece. An admin page where you type
`"tighten the daily loss limit to $5,000 and update the banner text"` — the agent implements it,
Kane verifies it, the page shows the verdict. The whole closed loop visible in one screen recording.

```
Ops page (admin only)          backend                          box
┌──────────────┐   POST /api/ops/change-request  ┌─────────────────────────┐
│ prompt box ──┼───────────────────────────────▶ │ change_requests row      │
│              │   202 {id}                     │ status=running           │
│ polls every 2s│                               │                          │
│              │                                │ 1. subprocess:           │
│              │◀─ GET /api/ops/change-requests ─│  `opencode run "<prompt>"`│
│  ┌─ status ──┤    /{id}                       │   cwd=/opt/tiltlock      │
│  │ applied ✓ │                                │   (OpenCode uses its OWN │
│  │ commit a1b2                                │    stored key — never ours)│
│  │ kane: ✗ ✗ ✗                                │ 2. git add -A && commit  │
│  │ 1 failed step:                             │ 3. subprocess:            │
│  │ "banner text mismatch"                     │  `kane-cli testmd run    │
│  │ [view evidence]                           │   kane/tests/X_test.md   │
│  │ [revert]                                   │   --agent --headless`     │
│  └────────────┤                                │ 4. parse NDJSON run_end  │
└──────────────┘                                │ 5. status=applied/failed │
                                                 └─────────────────────────┘
```

| | |
|---|---|
| Files | `ops/agent_runner.py`, `ops/kane_bridge.py`, `ops/api.py` (admin routers) |
| Auth | role `admin` only (the two of you). Judge personas are `trader` and get 403 here |
| Agent invocation | `opencode run "<prompt>"` (OpenCode's official non-interactive mode, built for scripts/CI). Runs as the `tiltlock` user, cwd = repo checkout. **The API key never enters our app** — OpenCode holds its credentials in its own config on the box (set up once via SSH). Exact flags: check `opencode run --help`; keep the command template in one config var so it's swappable |
| Kane invocation | `kane-cli testmd run <file> --agent --headless` → parse NDJSON last lines → `{status, summary, failed_step_remark, credits}` |
| Safety rails | one change at a time (row lock) · every prompt + result logged in `change_requests` · auto `git commit` per change → **revert = `git revert`** (button on the page) · agent runs unprivileged, confined to the repo dir, no secrets in repo |
| Fail path | agent exits ≠ 0 or produces no diff → status=failed, message surfaced; Kane fail after apply → status stays `applied`, kane_status=failed, red verdict shown — **this is the footage you want on the bug wall** |
| Phasing | **v0 (Mon–Tue): the loop runs from SSH terminal only** (commands in §7) — it's the same subprocess calls, just manual. **v1 (Wed): the Ops page.** Never let the page block the core broker build |

### 3.8 Frontend pages

| Page | Contents | Kane-relevant text |
|---|---|---|
| Login/Signup | form, error text | "Signed in as X", "Cash: $100,000.00" |
| Dashboard | watchlist table w/ live prices, guardrail status bar | symbol rows, "trades today: N/10" |
| StockDetail | chart, quote, **fundamentals panel** (company, sector, live P/E, market cap, 52-wk range, quarterly results bars — §3.2b), **OrderTicket** (buy/sell, qty), block/reject banners | banners render backend reason strings verbatim · "P/E", "Market cap", "Quarterly results" labels (flow #11) |
| Portfolio | cash, holdings w/ live P&L, equity | row per holding, "Equity: $X" |
| Orders | history table: symbol, side, qty, price, status, reason | status + reason text |
| Discipline | per-rule cards: used/limit, loss so far, cooldown countdown | "locked until tomorrow", countdown |
| Ops (admin) | prompt box, change log w/ Kane verdicts, evidence links, revert | verdict text straight from NDJSON |

---

## 4. Database schema

SQLite file at `DB_PATH` (default `/opt/tiltlock/data/tiltlock.db`, on **EBS**). WAL mode enabled in
`core/db.py` (one pragma line — keeps it out of business logic; that line is the only SQLite-specific code).

```sql
CREATE TABLE users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  email         TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'trader',   -- 'trader' | 'admin'
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sessions (
  token      TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id),
  expires_at TEXT NOT NULL
);

CREATE TABLE stocks (                        -- instrument master ("stock registration")
  symbol     TEXT PRIMARY KEY,               -- 'AAPL', 'TSLA', ...
  name       TEXT NOT NULL,
  base_price REAL NOT NULL,
  volatility REAL NOT NULL DEFAULT 0.02,
  seed       INTEGER NOT NULL                -- deterministic price walk per symbol
);

CREATE TABLE stock_profiles (                -- 1:1 content data for the detail page (§3.2b)
  symbol              TEXT PRIMARY KEY REFERENCES stocks(symbol),
  description         TEXT NOT NULL,         -- 1-2 line company blurb
  sector              TEXT NOT NULL,         -- 'Technology', 'EV', 'Retail', ...
  eps                 REAL NOT NULL,         -- annual EPS; > 0 → live P/E = price / eps
  shares_outstanding  INTEGER NOT NULL,      -- market cap = shares × live price
  fifty_two_week_high REAL NOT NULL,
  fifty_two_week_low  REAL NOT NULL,
  founded_year        INTEGER
);

CREATE TABLE stock_financials (              -- quarterly results → bar chart (§3.2b)
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol     TEXT NOT NULL REFERENCES stocks(symbol),
  period     TEXT NOT NULL,                  -- '2025Q1' ... '2026Q4'
  revenue    REAL NOT NULL,
  net_profit REAL NOT NULL,                  -- may be negative → negative bar
  UNIQUE (symbol, period)
);

CREATE TABLE rules_config (
  user_id            INTEGER PRIMARY KEY REFERENCES users(id),
  daily_loss_limit   REAL    NOT NULL DEFAULT 10000,
  max_trades_per_day INTEGER NOT NULL DEFAULT 10,
  cooldown_minutes   INTEGER NOT NULL DEFAULT 30,
  loss_streak_trigger INTEGER NOT NULL DEFAULT 3,
  max_position_pct   REAL    NOT NULL DEFAULT 0.20,
  max_open_positions INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE holdings (
  user_id INTEGER NOT NULL REFERENCES users(id),
  symbol  TEXT NOT NULL REFERENCES stocks(symbol),
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  avg_cost REAL NOT NULL,
  PRIMARY KEY (user_id, symbol)
);

CREATE TABLE orders (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      INTEGER NOT NULL REFERENCES users(id),
  symbol       TEXT NOT NULL REFERENCES stocks(symbol),
  side         TEXT NOT NULL,                -- 'buy' | 'sell'
  quantity     INTEGER NOT NULL,
  order_type   TEXT NOT NULL DEFAULT 'market',
  limit_price  REAL,
  status       TEXT NOT NULL,                -- 'filled' | 'blocked' | 'rejected' | 'open' | 'cancelled'
  reason       TEXT,                        -- exact guardrail/validation string; Kane asserts this
  filled_price REAL,
  realized_pnl REAL,                        -- set on filled sells
  created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_orders_user_day ON orders(user_id, created_at);

CREATE TABLE cash_transactions (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       INTEGER NOT NULL REFERENCES users(id),
  amount        REAL NOT NULL,              -- signed
  kind          TEXT NOT NULL,              -- 'signup_credit' | 'buy' | 'sell'
  order_id      INTEGER REFERENCES orders(id),
  balance_after REAL NOT NULL,
  created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE change_requests (               -- ops/agent loop audit log
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  requested_by INTEGER NOT NULL REFERENCES users(id),
  prompt       TEXT NOT NULL,
  status       TEXT NOT NULL,               -- 'running' | 'applied' | 'failed' | 'reverted'
  git_commit   TEXT,
  kane_status  TEXT,                        -- 'passed' | 'failed' | 'not_run'
  kane_summary TEXT,                        -- failing step remark, from NDJSON
  created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**Seeding (`python -m app.seed`):** 8–10 symbols (AAPL, TSLA, MSFT, NVDA, AMZN, GOOG, META, NFLX) with
base prices/seeds, **plus per-symbol `stock_profiles` + 8 quarters of `stock_financials` (§3.2b)**; the 3 demo personas; `tilted@demo` gets 9 filled sells **today** whose
`realized_pnl` sums to **−$9,700** (plus supporting holdings/cash rows — books must balance);
`cooldown@demo` gets 3 loss sells, the last one 5 minutes ago → ~25 min of cooldown left at seed time.
Reseed on demand: `python -m app.seed --personas-only`.

**Guardrail state is derived, never stored**: daily loss = Σ realized_pnl of today's filled sells;
trades used = count of today's fills; streak = last 3 sells. Fewer counters = fewer consistency bugs.

---

## 5. API surface

All under `/api`, session-cookie auth. `POST /api/orders` returns **403** for guardrail blocks with
`{"status": "blocked", "reason": "<exact string>"}` and **400** for validation rejects — frontend
renders `reason` verbatim; Kane asserts substrings.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | /api/auth/signup | — | create account, credit $100k, set session |
| POST | /api/auth/login | — | session cookie |
| POST | /api/auth/logout | user | clear session |
| GET | /api/me | user | profile + rules + guardrail summary |
| GET | /api/stocks | user | quotes list |
| GET | /api/stocks/{symbol} | user | quote + candles + profile + financials (P/E & market cap derived live — §3.2b); 404 unknown symbol |
| GET | /api/portfolio | user | cash, holdings, P&L, equity |
| GET | /api/orders?limit=50 | user | order history |
| POST | /api/orders | user | place order → 201 filled / 403 blocked / 400 rejected |
| GET | /api/guardrails/status | user | per-rule used/limit/remaining/locked |
| POST | /api/admin/reset-personas | admin | reseed personas (see §6.6) |
| POST | /api/ops/change-request | **admin** | {prompt} → 202 {id} |
| GET | /api/ops/change-requests/{id} | **admin** | status, diff summary, kane verdict |
| POST | /api/ops/revert/{id} | **admin** | `git revert` that change |

---

## 6. Hosting & deployment on EC2

### 6.1 Instance
- Ubuntu 24.04, **t3.micro** (free-tier eligible if your AWS account qualifies; t3.small if you want
  headroom for `npm run build` on-box — or build locally and `scp dist/`).
- **EBS root volume** (default) — SQLite file lives here and survives reboots.
- Region: whichever is closest to you two (e.g. ap-south-1 Mumbai).

### 6.2 Security group
| Port | Source | Purpose |
|---|---|---|
| 22 | your two IPs only | SSH |
| 80 | 0.0.0.0/0 | nginx (HTTP) |
| 443 | 0.0.0.0/0 | nginx (if HTTPS added) |

Port 8000 (uvicorn) is **never** opened — it binds to 127.0.0.1.

### 6.3 nginx — one origin, no CORS
```nginx
server {
    listen 80;
    server_name _;
    root /opt/tiltlock/frontend/dist;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
    location / { try_files $uri /index.html; }   # SPA routing
}
```

### 6.4 systemd — uvicorn as a service
```ini
[Unit]
Description=TiltLock API
After=network.target

[Service]
User=tiltlock
WorkingDirectory=/opt/tiltlock/backend
EnvironmentFile=/etc/tiltlock/env        # chmod 600, root-owned
ExecStart=/opt/tiltlock/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

### 6.5 Environment file — `/etc/tiltlock/env` (gitignored everywhere)
| Var | Value | Notes |
|---|---|---|
| `APP_ENV` | `production` | |
| `SESSION_SECRET` | random 32+ chars | `openssl rand -hex 32` |
| `DB_PATH` | `/opt/tiltlock/data/tiltlock.db` | EBS |
| `ADMIN_EMAILS` | `you@x.com,teammate@x.com` | seeded admin logins — live only on the box |
| `ADMIN_PASSWORD` | strong random value | same — never in repo or README |
| `STARTING_CASH` | `100000` | |
| `AGENT_CMD` | `opencode run` | swappable template |
| `KANE_TIMEOUT_S` | `300` | per-subprocess cap |

**No LLM API key here.** OpenCode holds its own credentials in its config under the `tiltlock` user's
home (authenticate once via SSH: `opencode` → sign in). Kane authenticates the same way
(`kane-cli login --oauth`, run once interactively). Commit `.env.example` with empty values.

### 6.6 Deploy steps (Wednesday's runbook)
1. `ssh` in → `sudo apt update && sudo apt install -y nginx python3-venv nodejs npm git`
2. `sudo useradd -m tiltlock` → `sudo -u tiltlock git clone <repo> /opt/tiltlock`
3. Backend: `python3 -m venv .venv && .venv/bin/pip install -e ".[prod]"`
4. Frontend: `npm ci && npm run build` (produces `frontend/dist/`)
5. `python -m app.seed` → creates DB, symbols, personas
6. Write `/etc/tiltlock/env`, drop the nginx config, `systemctl enable --now tiltlock-api nginx`
7. One-time agent auth: `sudo -u tiltlock opencode` (sign in once) · `sudo -u tiltlock kane-cli login --oauth`
8. Verify: `curl http://localhost/api/stocks` from the box, then the public IP from your laptop

**Daily-reset gotcha (important):** guardrail state uses *today's* orders, so at midnight the tilted
persona loses its tilt. **Run `python -m app.seed --personas-only` (or the admin endpoint) right
before the demo recording and before judging starts.** Also re-run if a Kane flow consumes persona
state. This is why the reset is an admin endpoint, not just a script.

**Redeploy:** `git pull && systemctl restart tiltlock-api`; frontend: `npm ci && npm run build`.
**Rollback:** `git revert` / `git reset --hard <tag>` + restart. Tag each day: `day1`, `day2`, …

**HTTPS (optional, ~30 min, Wednesday only if core is green):** DuckDNS free subdomain
(`team.duckdns.org` → your elastic IP; allocate an Elastic IP so restarts don't change it) + **Caddy**
in front (auto Let's Encrypt). Plain HTTP on the public IP is fine for Kane and judges — don't spend
video-recording time on it.

---

## 7. Services & command cheat sheet

**Services on the box**

| Service | What it is | Runs as | When |
|---|---|---|---|
| nginx | static files + /api proxy | systemd | always |
| uvicorn | FastAPI backend | systemd (tiltlock user) | always |
| price ticks | asyncio task inside uvicorn | — | always |
| SQLite | file on EBS | — | — |
| `opencode run` | coding agent subprocess | tiltlock user, via Ops page or SSH | on demand |
| `kane-cli testmd run` | verification subprocess | tiltlock user, via Ops page or SSH | on demand |
| Caddy | HTTPS (optional) | systemd | if added |

**Commands both of you should know by heart**

```bash
# ── dev (your laptops) ───────────────────────────────────────────
cd backend  && uvicorn app.main:app --reload          # API on :8000
cd frontend && npm run dev                            # Vite on :5173, proxy /api → :8000
cd backend  && python -m app.seed                     # fresh local DB + personas
cd backend  && pytest                                 # guardrails + ledger unit tests

# ── the loop, manual (v0 — SSH into the box) ──────────────────────
sudo -u tiltlock opencode run "Make <change described precisely>"   # agent edits code
cd /opt/tiltlock && sudo -u tiltlock git log --oneline -3          # what changed
sudo -u tiltlock kane-cli testmd run kane/tests/<flow>_test.md \
     --agent --headless                                             # NDJSON verdict

# ── kane ─────────────────────────────────────────────────────────
kane-cli whoami && kane-cli balance                   # readiness: signed in? credits?
kane-cli testrun run --tags smoke --headless --agent  # run a suite
kane-cli evidence serve <path>                        # view a failure's evidence pack

# ── deploy / ops (Person A) ───────────────────────────────────────
git pull && systemctl restart tiltlock-api
(cd frontend && npm ci && npm run build)              # after frontend changes
journalctl -u tiltlock-api -f                         # logs
python -m app.seed --personas-only                     # re-tilt the personas (§6.6!)
```

**Credit budget:** 10,000 free credits. Each flow *authors* once (costs credits), then **replays from
recording at zero cost** — so the suite is cheap after day one. Budget ~6k for authoring + retries,
keep 4k reserve for Wednesday's deployed-URL re-run. If running low: DM hackathon Slack (they top up).

---

## 8. Responsibility split

**Person A — Backend & Infra** · **Person B — Frontend & Verification.** Swap titles freely; the split
is about ownership, not skill boxes.

| Area | Person A | Person B |
|---|---|---|
| Auth, models, seed, `core/` | ✅ owns | consumes |
| Price engine + quotes API | ✅ owns | |
| Order engine + validation | ✅ owns | |
| Guardrails rules (pure fns) + status API | ✅ owns | asserts reason strings match UI |
| Ledger / portfolio API | ✅ owns | |
| Ops: agent_runner + kane_bridge | ✅ owns | |
| EC2: nginx, systemd, deploy, security groups | ✅ owns | smoke-tests result |
| All 7 pages + components | | ✅ owns |
| Order ticket, banners, discipline cards | | ✅ owns |
| Ops page UI | | ✅ owns |
| Kane `_test.md` authoring + evidence pack capture | co-writes flows for API behavior | ✅ owns |
| PRD.md acceptance criteria | drafts backend ACs | drafts UI-flow ACs |
| Demo video (Thu) | records terminal/loop segments | edits + app walk-through |
| README (judges' entry point) | deploy/run section | demo logins + feature tour |

**Day-by-day (both columns = parallel work)**

| Day | A (backend) | B (frontend) |
|---|---|---|
| Sat 21 | models + core + auth + seed; OpenAPI contract published | Vite shell, router, login page, dashboard skeleton |
| Sun 22 | price engine + quotes/fundamentals endpoints (§3.2b) | dashboard quotes table, stock page + chart + fundamentals panel; **first Kane flow green** |
| Mon 23 | order engine + ledger, atomic txn; manual loop v0 works (opencode + kane via SSH) | order ticket, portfolio, toasts; happy-path flow green |
| Tue 24 | guardrails engine + status API; ops: agent_runner + kane_bridge | banners, discipline page, violation flows — **record red→green clips daily** |
| Wed 25 | deploy per §6.6 + ops page endpoints + suite vs deployed URL | Ops page UI, README, judge logins, HTTPS only if green |
| Thu 26 | video: loop segment (red→green), app segment; **submit** | |
| Fri 27 | emergency buffer only — do not touch a green build after Thu night | |

**Definition of Done for every feature** — all four, or it's not done:
1. Endpoint(s) return correct data (pytest for pure logic)
2. UI shows the outcome **as text**
3. A Kane `_test.md` covers it and passes
4. One-line note in README (feature list)

**Git protocol:** single `main`, small commits, prefixes `feat: / fix: / test: / ops: / docs:`.
Never commit `.env`, `.testmuai/evidence/`, or `*.db`. Push before ending each day (bug-wall clips
come from history). Sync on voice call ≥ 1×/day (5 min standup: what changed, what's blocked).

---

## 9. Kane verification plan

**Flows (tags for suite selection)**

| # | Flow | Persona | Asserts |
|---|---|---|---|
| 1 | `signup_credit_test.md` — signup | new | dashboard shows "Cash: $100,000.00" |
| 2 | `login_quote_test.md` — login + search | fresh | AAPL row + quote page price visible |
| 3 | `buy_fills_test.md` (smoke) | fresh | toast "Order filled", portfolio row, cash drops |
| 4 | `insufficient_cash_test.md` | fresh | banner "Rejected: insufficient cash" |
| 5 | `sell_roundtrip_test.md` (smoke) | fresh | holding closes, cash rises, orders row w/ price |
| 6 | `kill_switch_test.md` | tilted | any trade → "daily loss limit reached" + locked banner |
| 7 | `overtrade_test.md` | fresh | 10 fills OK, 11th → "daily trade limit reached (10/10)" |
| 8 | `cooldown_test.md` | cooldown | trade → "cooldown active" + visible countdown |
| 9 | `position_size_test.md` | fresh | oversized buy → "position size cap" |
| 10 | `unknown_symbol_test.md` | fresh | 404 message "unknown symbol" |
| 11 | `stock_fundamentals_test.md` | fresh | detail page shows company name, sector, a "P/E" value, "Market cap" and "Quarterly results" bars (presence/format only — price ticks) |

**The loop (what judges score):** PRD.md → `kane-cli context ingest` → `design tests` (or hand-write
the 10 above — both allowed; designed ones link to ACs and give coverage evidence) → commit as
`kane/tests/*_test.md` → after every feature change: run flow → read NDJSON → fix → re-run.

**Bug wall (start a shared doc Saturday):** every red→green moment gets one line: date, flow, failing
step remark, what the bug was, link to the evidence pack + a screen clip. This is raw material for the
video and proof of the loop.

**What to record as you go (for the video):** the terminal showing a Kane run failing (red), the
agent reading the remark and fixing, the re-run passing (green), and one Ops-page run of the same arc.
Don't try to recreate this on Thursday — capture it live.

---

## 10. Timeline

Saturday Nov 21 → deploy-ready Wed Nov 25, video Thu Nov 26, submit **Thu night**, Fri 27 buffer only.
Detail is in §8's day-by-day table — it's the same plan, don't fork it.

---

## 11. Submission checklist

- [ ] Repo public, initialized ≥ Nov 12 (Nov 21 ✓), commit history shows the build
- [ ] README: one-command run + judge logins (3 personas) + what Kane verified
- [ ] Live URL (public IP is fine) reachable in <30 s; `reset-personas` run before deadline
- [ ] 3-min video (unlisted, test in incognito): 0:00 pitch → 0:15 loop red→green → 1:45 guardrail
      demo w/ tilted persona → 2:45 suite green on deployed URL
- [ ] One paragraph: what, who, agent used, what Kane does
- [ ] SurveyMonkey form submitted **Thursday night** — not Friday 11:58 PM
- [ ] TestMu signup done + credits functional (eligibility requirement)
- [ ] Backup: recorded run of the suite in case the URL hiccups during judging

---

## 12. Open decisions (fill these in, then start building)

| Decision | Default in this doc | Change if… |
|---|---|---|
| Project name | TiltLock | pick before the video |
| Real names in §8 | "Person A/B" | swap in your names |
| Guardrail defaults | $10k loss, 10 trades, 30 min, 20%, 5 positions | any defaults fine — just keep personas consistent with them |
| Agent CLI | `opencode run` | any agent works; keep `AGENT_CMD` swappable |
| Instance size | t3.micro (free tier) | slow builds → build locally, scp dist/ |
| HTTPS | skip unless Wed is green | DuckDNS + Caddy path documented in §6.6 |

---

*This document is the team's single source of truth. When reality disagrees with it, fix the doc in the
same commit as the code.*
