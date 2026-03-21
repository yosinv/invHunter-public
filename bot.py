"""
invHunter Telegram Bot
Commands:
  /start   - welcome
  /run     - full Claude analysis on all watchlist stocks
  /prices  - quick price snapshot, no Claude
  /help    - list commands
"""

import os
import json
import re
import logging
from dotenv import load_dotenv

load_dotenv()

import yfinance as yf
import anthropic
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────
WATCHLIST = [
    "BEZQ", "TEVA", "NICE", "ESLT", "POLI", "LUMI",
    "ARYT", "RPOL", "IMCO", "NXSN", "AVGL", "REKA", "EMDV", "KARE",
    "EVGN", "MDIN",
    "DRAL", "PLSN", "ISRS", "TDRN", "CYBR",
    "GILT", "SPEN", "RATI", "CAMT", "NVMI",
]
PORTFOLIO_ILS = 50000
MAX_POSITION_ILS = 10000
RISK_LEVEL = "medium"


# ─── Market Data ──────────────────────────────────
def get_stock_data(ticker: str) -> dict | None:
    stock = yf.Ticker(f"{ticker}.TA")
    hist = stock.history(period="20d")
    info = stock.info
    if hist.empty:
        return None
    # yfinance returns TASE prices in agorot — convert to ILS (÷100)
    closes = hist["Close"] / 100
    sma5 = closes.rolling(5).mean().iloc[-1]
    sma20 = closes.rolling(20).mean().iloc[-1]
    current = closes.iloc[-1]
    prev = closes.iloc[-2]
    pct = ((current - prev) / prev) * 100
    return {
        "ticker": ticker,
        "current_price_ils": round(current, 2),
        "pct_change_today": round(pct, 2),
        "sma_5day": round(sma5, 2),
        "sma_20day": round(sma20, 2),
        "above_sma5": bool(current > sma5),
        "above_sma20": bool(current > sma20),
        "avg_volume_10d": int(hist["Volume"].tail(10).mean()),
        "volume_today": int(hist["Volume"].iloc[-1]),
        "high_20d": round(closes.tail(20).max(), 2),
        "low_20d": round(closes.tail(20).min(), 2),
        "pe_ratio": info.get("trailingPE"),
        "market_cap_ils": info.get("marketCap"),
    }


# ─── Claude Analysis ──────────────────────────────
def ask_claude(data: dict) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system="You are a conservative stock trading assistant for the Tel Aviv Stock Exchange (TASE). Market trades Sunday-Thursday. All prices in ILS. Be conservative. Respond ONLY with valid JSON, no extra text.",
        messages=[{"role": "user", "content": f"""Analyze this TASE stock and give a trading recommendation.

Stock data:
{json.dumps(data, indent=2, default=str)}

Portfolio context:
- Total portfolio: ₪{PORTFOLIO_ILS:,}
- Max position size: ₪{MAX_POSITION_ILS:,}
- Risk level: {RISK_LEVEL}
- Current open positions: []

Respond with this exact JSON:
{{
    "action": "buy" | "sell" | "hold",
    "quantity": <integer, 0 if hold>,
    "limit_price_ils": <price in ILS, null if hold>,
    "stop_loss_ils": <stop loss in ILS, null if hold>,
    "confidence": "low" | "medium" | "high",
    "reasoning": "<1-2 sentences>"
}}"""}]
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"^```json?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


# ─── Bot Handlers ─────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *invHunter Bot*\n\n"
        "/run — full Claude analysis on all stocks\n"
        "/prices — quick price snapshot\n"
        "/help — this message",
        parse_mode="Markdown"
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)


async def cmd_prices(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📡 Fetching prices...")
    lines = ["📊 *TASE Prices*\n"]
    for ticker in WATCHLIST:
        data = get_stock_data(ticker)
        if not data:
            lines.append(f"❓ {ticker}: no data")
            continue
        arrow = "🟢" if data["pct_change_today"] > 0 else "🔴" if data["pct_change_today"] < 0 else "⚪"
        lines.append(f"{arrow} *{ticker}* ₪{data['current_price_ils']:,.0f} ({data['pct_change_today']:+.2f}%)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_run(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Running Claude analysis on all stocks... (this takes ~1 min)")

    buys = []
    holds = []
    errors = []

    for ticker in WATCHLIST:
        data = get_stock_data(ticker)
        if not data:
            errors.append(ticker)
            continue
        try:
            d = await ctx.application.loop.run_in_executor(None, ask_claude, data)
            if d["action"] == "buy":
                buys.append((ticker, data, d))
            else:
                holds.append((ticker, data, d))
        except Exception as e:
            log.error(f"{ticker} error: {e}")
            errors.append(ticker)

    # Send BUY signals first
    if buys:
        lines = ["🟢 *BUY SIGNALS*\n"]
        for ticker, data, d in buys:
            lines.append(
                f"*{ticker}* ₪{data['current_price_ils']:,.0f} ({data['pct_change_today']:+.2f}%)\n"
                f"  qty={d['quantity']} | limit=₪{d['limit_price_ils']} | stop=₪{d['stop_loss_ils']}\n"
                f"  confidence={d['confidence']}\n"
                f"  _{d['reasoning']}_\n"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    else:
        await update.message.reply_text("⚪ No BUY signals today.")

    # Send HOLD summary
    if holds:
        lines = ["⚪ *HOLDS*\n"]
        for ticker, data, d in holds:
            lines.append(f"• *{ticker}* ₪{data['current_price_ils']:,.0f} ({data['pct_change_today']:+.2f}%) — {d['confidence']} conf")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    if errors:
        await update.message.reply_text(f"❓ No data: {', '.join(errors)}")


# ─── Main ─────────────────────────────────────────
def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("prices", cmd_prices))
    app.add_handler(CommandHandler("run", cmd_run))
    log.info("invHunter bot started — waiting for commands")
    app.run_polling()


if __name__ == "__main__":
    main()
