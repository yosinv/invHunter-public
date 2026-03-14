# invHunter 📈

An AI-powered algorithmic trading agent for the **Tel Aviv Stock Exchange (TASE)**.
Uses Claude AI to analyze stocks, make trading decisions, and notify you via Telegram, email, and Mac notifications.

---

## How It Works

```
yfinance (free, end-of-day data)
        │
        ▼
  get_stock_data()        ← fetches prices, SMAs, volume, P/E
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
3. Gets a structured trading decision back (action, quantity, price, stop-loss, reasoning)
4. Skips low-confidence signals
5. Asks for manual confirmation before placing live orders
6. Places limit orders via Interactive Brokers TWS

---

## Project Structure

```
invHunter/
├── tase_claude_agent.py   # Main trading agent
├── bot.py                 # Telegram bot (interactive remote control)
├── notify.py              # Morning alert: Mac + Telegram + Email
├── SETUP.txt              # Quick setup reference
├── .env                   # Your credentials (gitignored)
└── .venv/                 # Python virtual environment (gitignored)
```

---

## Setup

### 1. Clone & create virtual environment

```bash
git clone https://github.com/yosinv/invHunter.git
cd invHunter
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install ib_insync yfinance anthropic pandas python-dotenv python-telegram-bot requests
```

### 3. Configure credentials

Create a `.env` file in the project root:

```env
# Anthropic (Claude API)
ANTHROPIC_API_KEY=sk-ant-...

# Telegram bot
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id

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

Open `tase_claude_agent.py` and adjust:

```python
PAPER_TRADING = True          # Start with True — switch to False only when ready
MAX_POSITION_ILS = 10000      # Max ₪ per trade
PORTFOLIO_ILS = 50000         # Your total portfolio size
RISK_LEVEL = "medium"         # "low" | "medium" | "high"

WATCHLIST = [
    "BEZQ",   # Bezeq
    "TEVA",   # Teva Pharmaceutical
    # ... add/remove tickers here
]
```

> **TASE ticker format:** Use the base ticker (e.g. `BEZQ`), not the `.TA` suffix — the agent appends it automatically for yfinance.

---

## Running

### Run the trading agent

```bash
source .venv/bin/activate
python tase_claude_agent.py
```

Make sure TWS is open and connected before running.

### Start the Telegram bot

```bash
source .venv/bin/activate
python bot.py
```

Then from Telegram, send commands to your bot:

| Command | What it does |
|---|---|
| `/start` | Welcome message + command list |
| `/prices` | Instant price snapshot for all watchlist stocks |
| `/run` | Full Claude analysis — sends buy signals and hold summary |
| `/help` | List commands |

### Send a morning reminder

```bash
python notify.py
```

Sends a "time to run invHunter" alert via Mac notification, Telegram, and email.

---

## Automation (run every trading day)

A cron job fires at 09:00 Israel time (06:00 UTC) every Sunday–Thursday:

```
0 6 * * 0-4 /path/to/invHunter/.venv/bin/python notify.py >> notify.log 2>&1
```

To add it: `crontab -e`

---

## Watchlist

Current stocks tracked:

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

---

## Safety Features

- **Paper trading by default** — `PAPER_TRADING = True` until you explicitly switch
- **Hard position cap** — `MAX_POSITION_ILS` is enforced in code, Claude cannot exceed it
- **Low-confidence skip** — signals with `confidence: low` are never executed
- **Manual confirmation** — live orders require you to type `yes` in the terminal before placing
- **Credentials in `.env`** — never committed to git (`.gitignore`d)

---

## Data Sources

| Source | What | Cost |
|---|---|---|
| yfinance | End-of-day prices, volume, P/E | Free |
| Claude API (Anthropic) | Trading decisions | Pay per use |
| IBKR TWS API | Order execution, real-time data | Free with IBKR account |

> TASE end-of-day data via Yahoo Finance uses `.TA` suffix tickers (e.g. `BEZQ.TA`).
> Real-time data requires an active IBKR account with TWS running.

---

## Requirements

- Python 3.10+
- Interactive Brokers account + TWS installed
- Anthropic API key with credits
- Telegram bot (optional, for remote control)
- Gmail account with App Password (optional, for email alerts)
