"""
TASE Claude Trading Agent
Uses: IBKR TWS (execution) + yfinance (market data) + Claude API (analysis)

Requirements:
    pip install ib_insync yfinance anthropic pandas

Setup:
    1. Open TWS or IB Gateway
    2. Enable API: File > Global Configuration > API > Settings
       - Enable ActiveX and Socket Clients: ON
       - Socket port: 7497 (paper) or 7496 (live)
       - Allow connections from localhost: ON
    3. Set your ANTHROPIC_API_KEY environment variable
"""

import os
import json
import re
import time
import logging
from datetime import datetime
import pandas as pd
import yfinance as yf
from ib_insync import IB, Stock, LimitOrder, util
import anthropic
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# CONFIG — edit these
# ─────────────────────────────────────────────
PAPER_TRADING = os.environ.get("LIVE_TRADING", "").lower() != "true"  # live only if LIVE_TRADING=true
MAX_POSITION_ILS = int(os.environ.get("MAX_POSITION_ILS", "10000"))  # Max ₪ per single trade (hard limit)
PORTFOLIO_ILS = int(os.environ.get("PORTFOLIO_ILS", "50000"))     # Your total portfolio size in ₪ (set in .env)
RISK_LEVEL = "medium"          # "low" | "medium" | "high"
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# TASE stocks to watch (append .TA for yfinance, use base ticker for IBKR)
WATCHLIST = [
    "BEZQ",   # Bezeq
    "TEVA",   # Teva Pharmaceutical
    "NICE",   # NICE Systems
    "ESLT",   # Elbit Systems
    # "CHKP",   # Check Point — NYSE only, no TASE listing
    "POLI",   # Bank HaPoalim
    "LUMI",   # Bank Leumi
    "ARYT",   # Aryt Industries Ltd
    "RPOL",   # RP Optical Lab Ltd
    "IMCO",   # Imco Industries Ltd
    "NXSN",   # Next Vision Stabilized Systems
    "AVGL",   # Avi-Gail (defense)
    "REKA",   # Reka Defense
    "EMDV",   # Elad Defense
    "KARE",   # Kareen (defense electronics)
    "EVGN",   # Evogene (אבוג'ן)
    "MDIN",   # Modiin Yehsh (מודיעין יהש)
    # ── Defense & Security Tech ──────────────────
    "DRAL",   # Drall Electronic Industries
    "PLSN",   # Plasan (armor & protection systems)
    "ISRS",   # Israel Shipyards (naval defense)
    "TDRN",   # Tadiran Electronic Industries (defense comms)
    "CYBR",   # CyberArk (cyber defense)
    "GILT",   # Gilat Satellite Networks
    "SPEN",   # SpaceCom (satellite comms)
    "RATI",   # Rati (defense electronics)
    "CAMT",   # Camtek (defense-grade inspection systems)
    "NVMI",   # Nova Measuring Instruments (defense-grade semicon)
]

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("tase_agent.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# MARKET DATA (yfinance — free)
# ─────────────────────────────────────────────
def get_stock_data(ticker: str) -> dict:
    """Fetch TASE stock data via yfinance (free, end-of-day)."""
    try:
        yf_ticker = f"{ticker}.TA"
        stock = yf.Ticker(yf_ticker)
        hist = stock.history(period="20d")
        info = stock.info

        if hist.empty:
            log.warning(f"No data for {ticker}")
            return None

        # yfinance returns TASE prices in agorot — convert to ILS (÷100)
        closes = hist["Close"] / 100
        sma5 = closes.rolling(5).mean().iloc[-1]
        sma20 = closes.rolling(20).mean().iloc[-1]
        current_price = closes.iloc[-1]
        prev_price = closes.iloc[-2]
        pct_change = ((current_price - prev_price) / prev_price) * 100

        return {
            "ticker": ticker,
            "current_price_ils": round(current_price, 2),
            "prev_close_ils": round(prev_price, 2),
            "pct_change_today": round(pct_change, 2),
            "sma_5day": round(sma5, 2),
            "sma_20day": round(sma20, 2),
            "above_sma5": current_price > sma5,
            "above_sma20": current_price > sma20,
            "avg_volume_10d": int(hist["Volume"].tail(10).mean()),
            "volume_today": int(hist["Volume"].iloc[-1]),
            "high_20d": round(closes.tail(20).max(), 2),
            "low_20d": round(closes.tail(20).min(), 2),
            "pe_ratio": info.get("trailingPE"),
            "market_cap_ils": info.get("marketCap"),
        }
    except Exception as e:
        log.error(f"Error fetching data for {ticker}: {e}")
        return None


# ─────────────────────────────────────────────
# CLAUDE ANALYSIS
# ─────────────────────────────────────────────
def ask_claude(stock_data: dict, existing_positions: list) -> dict:
    """Send stock data to Claude for a trading decision."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system_prompt = """You are a conservative stock trading assistant for the Tel Aviv Stock Exchange (TASE).
Key facts:
- Market trades Sunday–Thursday (NOT Monday–Friday)
- All prices are in Israeli Shekels (ILS / ₪)
- Be conservative — capital preservation is priority
- Never recommend spending more than the max position size
- Respond ONLY with valid JSON, no extra text"""

    user_prompt = f"""Analyze this TASE stock and give a trading recommendation.

Stock data:
{json.dumps(stock_data, indent=2, default=str)}

Portfolio context:
- Total portfolio: ₪{PORTFOLIO_ILS:,}
- Max position size: ₪{MAX_POSITION_ILS:,}
- Risk level: {RISK_LEVEL}
- Current open positions: {existing_positions}

Respond with this exact JSON format:
{{
    "action": "buy" | "sell" | "hold",
    "quantity": <integer number of shares, 0 if hold>,
    "limit_price_ils": <limit order price in ILS, null if hold>,
    "stop_loss_ils": <stop loss price in ILS, null if hold>,
    "confidence": "low" | "medium" | "high",
    "reasoning": "<1-2 sentence explanation>"
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```json?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        decision = json.loads(raw)
        log.info(f"Claude decision for {stock_data['ticker']}: {decision}")
        return decision
    except json.JSONDecodeError as e:
        log.error(f"Claude returned invalid JSON: {e}")
        return {"action": "hold", "quantity": 0, "reasoning": "JSON parse error"}
    except Exception as e:
        log.error(f"Claude API error: {e}")
        return {"action": "hold", "quantity": 0, "reasoning": str(e)}


# ─────────────────────────────────────────────
# IBKR CONNECTION & EXECUTION
# ─────────────────────────────────────────────
def connect_ibkr() -> IB:
    """Connect to TWS. Make sure TWS is open and API is enabled."""
    ib = IB()
    port = 7497 if PAPER_TRADING else 7496
    try:
        ib.connect("127.0.0.1", port, clientId=10)
        log.info(f"Connected to IBKR TWS on port {port} ({'PAPER' if PAPER_TRADING else 'LIVE'})")
        return ib
    except Exception as e:
        log.error(f"Failed to connect to TWS: {e}")
        log.error("Make sure TWS is open and API is enabled (File > Global Configuration > API)")
        raise


def get_open_positions(ib: IB) -> list:
    """Get list of currently open TASE positions."""
    positions = []
    for pos in ib.positions():
        if pos.contract.currency == "ILS" or pos.contract.exchange == "TASE":
            positions.append({
                "ticker": pos.contract.symbol,
                "quantity": pos.position,
                "avg_cost": pos.avgCost
            })
    return positions


def place_order(ib: IB, ticker: str, action: str, quantity: int, limit_price: float) -> bool:
    """Place a limit order on TASE via IBKR."""
    if quantity <= 0:
        return False

    # Safety check: never exceed max position size
    order_value = quantity * limit_price
    if order_value > MAX_POSITION_ILS:
        log.warning(f"Order value ₪{order_value:.0f} exceeds max ₪{MAX_POSITION_ILS} — skipping")
        return False

    contract = Stock(ticker, "TASE", "ILS")
    order = LimitOrder(action.upper(), quantity, round(limit_price, 2))
    order.tif = "DAY"  # Day order only

    try:
        ib.qualifyContracts(contract)
        trade = ib.placeOrder(contract, order)
        ib.sleep(1)  # Give TWS a moment
        log.info(f"✅ Order placed: {action.upper()} {quantity}x {ticker} @ ₪{limit_price:.2f} (value: ₪{order_value:.0f})")
        return True
    except Exception as e:
        log.error(f"Order failed for {ticker}: {e}")
        return False


# ─────────────────────────────────────────────
# MAIN AGENT LOOP
# ─────────────────────────────────────────────
def is_tase_trading_day() -> bool:
    """TASE trades Sunday–Thursday only."""
    day = datetime.now().weekday()
    # Monday=0, ..., Friday=4, Saturday=5, Sunday=6
    return day != 4 and day != 5  # Skip Friday and Saturday


def run_agent():
    """Main agent: fetch data → ask Claude → execute trades."""
    log.info("=" * 50)
    log.info("TASE Claude Agent Starting")
    log.info(f"Mode: {'📄 PAPER TRADING' if PAPER_TRADING else '💰 LIVE TRADING'}")
    log.info(f"Watchlist: {WATCHLIST}")
    log.info("=" * 50)

    # Check trading day
    if not is_tase_trading_day():
        log.info("Today is Friday/Saturday — TASE is closed. Exiting.")
        return

    # Connect to IBKR TWS
    ib = connect_ibkr()

    try:
        # Get existing positions (so Claude knows what we hold)
        existing_positions = get_open_positions(ib)
        log.info(f"Current positions: {existing_positions}")

        results = []

        for ticker in WATCHLIST:
            log.info(f"\n--- Analyzing {ticker} ---")

            # 1. Fetch market data
            data = get_stock_data(ticker)
            if not data:
                continue

            log.info(f"{ticker}: ₪{data['current_price_ils']} ({data['pct_change_today']:+.1f}% today)")

            # 2. Ask Claude
            decision = ask_claude(data, existing_positions)

            # 3. Execute if Claude recommends action (and not just holding)
            if decision["action"] in ("buy", "sell") and decision.get("quantity", 0) > 0:
                if decision.get("confidence") == "low":
                    log.info(f"Skipping {ticker} — Claude confidence is low")
                    continue

                # ⚠️ Human confirmation for live trading
                if not PAPER_TRADING:
                    confirm = input(
                        f"\n⚠️  LIVE ORDER: {decision['action'].upper()} "
                        f"{decision['quantity']}x {ticker} @ ₪{decision['limit_price_ils']}\n"
                        f"Reason: {decision['reasoning']}\n"
                        f"Confirm? (yes/no): "
                    )
                    if confirm.lower() != "yes":
                        log.info("Order skipped by user.")
                        continue

                placed = place_order(
                    ib,
                    ticker,
                    decision["action"],
                    decision["quantity"],
                    decision["limit_price_ils"]
                )
                results.append({
                    "ticker": ticker,
                    "action": decision["action"],
                    "quantity": decision["quantity"],
                    "price": decision["limit_price_ils"],
                    "placed": placed,
                    "reason": decision["reasoning"]
                })
            else:
                log.info(f"HOLD {ticker} — {decision.get('reasoning', '')}")

            time.sleep(1)  # Be gentle with APIs

        # Summary
        log.info("\n" + "=" * 50)
        log.info("AGENT RUN COMPLETE")
        for r in results:
            status = "✅" if r["placed"] else "❌"
            log.info(f"{status} {r['action'].upper()} {r['quantity']}x {r['ticker']} @ ₪{r['price']}")
        if not results:
            log.info("No trades executed today.")
        log.info("=" * 50)

    finally:
        ib.disconnect()
        log.info("Disconnected from TWS")


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    run_agent()
