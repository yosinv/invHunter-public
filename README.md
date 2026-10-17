# invHunter 📈

An AI-powered algorithmic trading platform for the **Tel Aviv Stock Exchange (TASE)** and **Polymarket prediction markets**.
Uses Claude AI to analyze stocks, detect arbitrage opportunities, make trading decisions, and notify you via Telegram, email, and Mac notifications.

> ⚠️ **Disclaimer — read before running.** This is a personal research project, not financial advice.
> It turns LLM output into buy/sell signals and can place real orders through Interactive Brokers.
> LLMs make mistakes, market data can be wrong or stale, and you can lose money. Run it in paper
> trading mode, review every signal yourself, and use it entirely at your own risk. The authors accept
> no liability for any losses. See [LICENSE](LICENSE).

---

## How It Works

```
yfinance (free, end-of-day data)
        │
        ▼
  get_stock_data()        ← fetches prices, SMAs, volume, P/E (agorot → ILS ÷100)
        │
        ▼
   ask_claude()           ← sends data to Claude API → gets buy/sell/hold JSON
        │
   decision JSON
        │
   ┌────┴────┐
 hold      buy/sell
   │           │
 log it    place_order()  ← executes limit order via IBKR TWS
```

Every trading day (Sun–Thu), the agent:
1. Fetches end-of-day data for each stock in your watchlist
2. Sends it to Claude with your portfolio context
3. Gets a structured decision back (action, quantity, price, stop-loss, reasoning)
4. Skips low-confidence signals
5. Saves analysis to `analysis/YYYY-MM-DD_HH-MM-SS.json`
6. Places limit orders via Interactive Brokers TWS (paper or live)

---

## Project Structure

```
invHunter/
├── tase_claude_agent.py   # Main trading agent (CLI)
├── dashboard.py           # Streamlit web dashboard
├── bot.py                 # Telegram bot (remote control)
├── notify.py              # Morning alert: Mac + Telegram + Email
├── requirements.txt       # Python dependencies
├── .env.example           # Template for your .env
├── LICENSE                # MIT
├── GRAPH_ARB_SCANNER.md   # Graph arbitrage scanner documentation
├── analysis/              # Saved Claude analysis runs (gitignored)
├── .env                   # Your credentials (gitignored)
└── .venv/                 # Python virtual environment (gitignored)
```

---

## Setup

### 1. Clone & create virtual environment

```bash
git clone https://github.com/yosinv/invHunter-public.git
cd invHunter-public
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure credentials

Copy `.env.example` to `.env` and fill it in:

```env
# Anthropic (Claude API)
ANTHROPIC_API_KEY=sk-ant-...

# Telegram bot
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id     # the bot ONLY answers these chat IDs (comma-separated)

# Trading limits & mode
PORTFOLIO_ILS=50000
MAX_POSITION_ILS=10000
LIVE_TRADING=false                # must be exactly "true" to allow live orders

# Email (Gmail)
EMAIL_FROM=you@gmail.com
EMAIL_TO=you@gmail.com
EMAIL_PASSWORD=your-app-password   # Gmail App Password, not your login password
EMAIL_SMTP=smtp.gmail.com
EMAIL_PORT=587
```

#### Getting credentials:

| Credential | How to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API Keys |
| `TELEGRAM_BOT_TOKEN` | Message `@BotFather` on Telegram → `/newbot` |
| `TELEGRAM_CHAT_ID` | Message `@userinfobot` on Telegram |
| `EMAIL_PASSWORD` | Google Account → Security → App Passwords |

### 4. Configure IBKR TWS

1. Open **Trader Workstation (TWS)**
2. Go to: `File → Global Configuration → API → Settings`
3. Enable **ActiveX and Socket Clients** ✓
4. Set port: `7497` (paper trading) or `7496` (live)
5. Enable **Allow connections from localhost only** ✓
6. Restart TWS

### 5. Edit your config

Portfolio size, position cap and live/paper mode come from `.env` (see above).
Open `tase_claude_agent.py` to adjust the risk level and watchlist:

```python
RISK_LEVEL = "medium"         # "low" | "medium" | "high"

WATCHLIST = [
    "BEZQ",   # Bezeq
    "TEVA",   # Teva Pharmaceutical
    # ... add/remove tickers here
]
```

> **TASE ticker format:** Use the base ticker (e.g. `BEZQ`), not the `.TA` suffix.
> **Price note:** yfinance returns TASE prices in agorot — the agent divides by 100 automatically to get ILS.

---

## Running

### Streamlit Dashboard (recommended)

```bash
source .venv/bin/activate
streamlit run dashboard.py
```

Opens at **http://localhost:8501**. Features:
- Live price table with SMA indicators
- Claude analysis with per-stock BUY/HOLD/SELL decisions
- Execute button per BUY signal → sends limit order to IBKR TWS
- Show Latest Analysis button → loads last saved run
- Paper/Live toggle in sidebar
- Polymarket Graph Arbitrage Scanner

### Telegram Bot

```bash
source .venv/bin/activate
python bot.py
```

Commands:

| Command | What it does |
|---|---|
| `/start` | Welcome message + command list |
| `/prices` | Instant price snapshot for all watchlist stocks |
| `/run` | Full Claude analysis — saves to file, sends BUY signals + full summary |
| `/last` | Show the last saved analysis |
| `/help` | List commands |

### CLI Agent (headless)

```bash
source .venv/bin/activate
python tase_claude_agent.py
```

Runs the full analysis loop and places orders via TWS. Requires TWS to be open.

### Morning Reminder

```bash
python notify.py
```

Sends a "time to run invHunter" alert via Mac notification, Telegram, and email.

---

## Automation

Cron job at 09:00 Israel time (06:00 UTC) every Sunday–Thursday:

```
0 6 * * 0-4 /path/to/invHunter/.venv/bin/python notify.py >> notify.log 2>&1
```

To add: `crontab -e`

---

## Watchlist

| Ticker | Company | Sector |
|---|---|---|
| BEZQ | Bezeq | Telecom |
| TEVA | Teva Pharmaceutical | Pharma |
| NICE | NICE Systems | Tech / Security |
| ESLT | Elbit Systems | Defense |
| POLI | Bank HaPoalim | Banking |
| LUMI | Bank Leumi | Banking |
| ARYT | Aryt Industries | Defense |
| RPOL | RP Optical Lab | Defense / Optics |
| IMCO | Imco Industries | Industrial |
| NXSN | Next Vision Stabilized Systems | Defense / Optics |
| AVGL | Avi-Gail | Defense |
| REKA | Reka Defense | Defense |
| EMDV | Elad Defense | Defense |
| KARE | Kareen | Defense Electronics |
| EVGN | Evogene | Biotech |
| MDIN | Modiin Yehsh | Real Estate |
| DRAL | Drall Electronic Industries | Defense |
| PLSN | Plasan | Defense (Armor) |
| ISRS | Israel Shipyards | Defense / Naval |
| TDRN | Tadiran Electronics | Defense / Comms |
| CYBR | CyberArk | Cyber Security |
| GILT | Gilat Satellite Networks | Defense / Satellite |
| SPEN | SpaceCom | Defense / Satellite |
| RATI | Rati | Defense Electronics |
| CAMT | Camtek | Defense Tech |
| NVMI | Nova Measuring Instruments | Defense Tech |

---

## Graph Arbitrage Scanner (Polymarket)

Built into the dashboard. Detects probability violations across related Polymarket prediction markets using graph theory and the Bellman-Ford algorithm.

- Fetches 300 active markets from the Polymarket Gamma API
- Tags each market by topic (Israel, Iran, Trump, Fed, Bitcoin, etc.)
- Builds a directed graph — edges weighted by `-log(probability)`
- Flags pairs where `|P(A) - P(B)| ≥ threshold` (default 15%)
- Detects negative cycles (guaranteed theoretical arbitrage) via Bellman-Ford

See [GRAPH_ARB_SCANNER.md](GRAPH_ARB_SCANNER.md) for full documentation.

---

## Safety Features

- **Paper trading by default** — live orders are impossible unless `LIVE_TRADING=true` is set in `.env`
- **Telegram allowlist** — the bot ignores every chat not listed in `TELEGRAM_CHAT_ID` and refuses to start without it
- **Hard position cap** — `MAX_POSITION_ILS` enforced in code, Claude cannot exceed it
- **Low-confidence skip** — `confidence: low` signals are never executed
- **Manual confirmation** — live orders require `yes` in terminal (CLI) or Execute button click (dashboard)
- **Credentials in `.env`** — never committed to git
- **Analysis saved locally** — every run saved to `analysis/` folder, gitignored

---

## Data Sources

| Source | What | Cost |
|---|---|---|
| yfinance | End-of-day TASE prices, volume, P/E | Free |
| Claude API (Anthropic) | Trading decisions | Pay per use |
| IBKR TWS API | Order execution | Free with IBKR account |
| Polymarket Gamma API | Prediction market prices | Free |

---

## Requirements

- Python 3.10+
- Interactive Brokers account + TWS installed
- Anthropic API key with credits
- Telegram bot (optional, for remote control)
- Gmail account with App Password (optional, for email alerts)
