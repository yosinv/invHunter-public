"""
invHunter Telegram Bot
Commands:
  /start    - welcome
  /run      - full Claude analysis, saved to analysis/ folder
  /last     - show last saved analysis
  /prices   - quick price snapshot, no Claude
  /help     - list commands
"""

import os
import json
import re
import asyncio
import logging
from datetime import datetime
from pathlib import Path
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

ANALYSIS_DIR = Path(__file__).parent / "analysis"
ANALYSIS_DIR.mkdir(exist_ok=True)

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
    closes = hist["Close"] / 100  # agorot → ILS
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


# ─── Save analysis to file ────────────────────────
def save_analysis(results: list) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = ANALYSIS_DIR / f"{ts}.json"
    payload = {
        "timestamp": datetime.now().isoformat(),
        "portfolio_ils": PORTFOLIO_ILS,
        "max_position_ils": MAX_POSITION_ILS,
        "results": results,
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    log.info(f"Analysis saved to {path}")
    return path


def load_last_analysis() -> dict | None:
    files = sorted(ANALYSIS_DIR.glob("*.json"), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text())


# ─── Format helpers ───────────────────────────────
def format_result_line(r: dict) -> str:
    action = r["action"].upper()
    icon = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⚪"
    price = r.get("price_ils", 0)
    pct = r.get("pct_change", 0)
    conf = r.get("confidence", "")
    return f"{icon} *{r['ticker']}* ₪{price:,.2f} ({pct:+.2f}%) — {action} [{conf}]"


# ─── Bot Handlers ─────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *invHunter Bot*\n\n"
        "/run — full Claude analysis (saved to file)\n"
        "/last — show last saved analysis\n"
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
        lines.append(f"{arrow} *{ticker}* ₪{data['current_price_ils']:,.2f} ({data['pct_change_today']:+.2f}%)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_run(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Running Claude analysis on all stocks... (~2 min)")

    results = []

    for ticker in WATCHLIST:
        data = get_stock_data(ticker)
        if not data:
            results.append({"ticker": ticker, "action": "error", "confidence": "—", "reasoning": "No data"})
            continue
        try:
            d = await asyncio.to_thread(ask_claude, data)
            results.append({
                "ticker": ticker,
                "action": d["action"],
                "quantity": d.get("quantity", 0),
                "limit_price_ils": d.get("limit_price_ils"),
                "stop_loss_ils": d.get("stop_loss_ils"),
                "confidence": d.get("confidence", ""),
                "reasoning": d.get("reasoning", ""),
                "price_ils": data["current_price_ils"],
                "pct_change": data["pct_change_today"],
            })
        except Exception as e:
            log.error(f"{ticker} error: {e}")
            results.append({"ticker": ticker, "action": "error", "confidence": "—", "reasoning": str(e)})

    # Save to file
    saved_path = save_analysis(results)

    # Send BUY signals
    buys = [r for r in results if r["action"] == "buy"]
    errors = [r for r in results if r["action"] == "error"]

    if buys:
        lines = [f"🟢 *{len(buys)} BUY SIGNAL(S)*\n"]
        for r in buys:
            lines.append(
                f"*{r['ticker']}* ₪{r['price_ils']:,.2f} ({r['pct_change']:+.2f}%)\n"
                f"  qty={r['quantity']} | limit=₪{r['limit_price_ils']} | stop=₪{r['stop_loss_ils']}\n"
                f"  confidence={r['confidence']}\n"
                f"  _{r['reasoning']}_\n"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    else:
        await update.message.reply_text("⚪ No BUY signals today.")

    # Send full analysis summary
    lines = ["📋 *Full Analysis*\n"]
    for r in results:
        icon = "🟢" if r["action"] == "buy" else "🔴" if r["action"] == "sell" else "⚪" if r["action"] == "hold" else "❓"
        price = r.get("price_ils", 0)
        pct = r.get("pct_change", 0)
        lines.append(f"{icon} *{r['ticker']}* ₪{price:,.2f} ({pct:+.2f}%) — {r['action'].upper()} [{r['confidence']}]")
        lines.append(f"   _{r['reasoning'][:80]}_")

    # Telegram has 4096 char limit — split if needed
    msg = "\n".join(lines)
    if len(msg) > 4000:
        chunks = []
        chunk = []
        for line in lines:
            chunk.append(line)
            if len("\n".join(chunk)) > 3800:
                chunks.append("\n".join(chunk[:-1]))
                chunk = [line]
        chunks.append("\n".join(chunk))
        for c in chunks:
            await update.message.reply_text(c, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")

    await update.message.reply_text(f"💾 Saved: `{saved_path.name}`", parse_mode="Markdown")

    if errors:
        await update.message.reply_text(f"❓ Errors: {', '.join(r['ticker'] for r in errors)}")


async def cmd_last(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    analysis = load_last_analysis()
    if not analysis:
        await update.message.reply_text("No saved analysis yet. Run /run first.")
        return

    ts = analysis.get("timestamp", "unknown")[:19].replace("T", " ")
    results = analysis.get("results", [])

    lines = [f"📂 *Last analysis* — {ts}\n"]
    for r in results:
        icon = "🟢" if r["action"] == "buy" else "🔴" if r["action"] == "sell" else "⚪" if r["action"] == "hold" else "❓"
        price = r.get("price_ils", 0)
        pct = r.get("pct_change", 0)
        lines.append(f"{icon} *{r['ticker']}* ₪{price:,.2f} ({pct:+.2f}%) — {r['action'].upper()} [{r['confidence']}]")
        lines.append(f"   _{r['reasoning'][:80]}_")

    msg = "\n".join(lines)
    if len(msg) > 4000:
        chunks, chunk = [], []
        for line in lines:
            chunk.append(line)
            if len("\n".join(chunk)) > 3800:
                chunks.append("\n".join(chunk[:-1]))
                chunk = [line]
        chunks.append("\n".join(chunk))
        for c in chunks:
            await update.message.reply_text(c, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")


# ─── Main ─────────────────────────────────────────
def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("prices", cmd_prices))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("last", cmd_last))
    log.info("invHunter bot started — waiting for commands")
    app.run_polling()


if __name__ == "__main__":
    main()
