"""
invHunter Dashboard — Streamlit
Run: streamlit run dashboard.py
"""

import os
import json
import time
from datetime import datetime

import pandas as pd
import streamlit as st
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

import anthropic
from ib_insync import IB, Stock, LimitOrder

# ─── Config ───────────────────────────────────────────────────────────────────
WATCHLIST = [
    "BEZQ", "TEVA", "NICE", "ESLT", "POLI", "LUMI",
    "ARYT", "RPOL", "IMCO", "NXSN", "AVGL", "REKA", "EMDV", "KARE",
]
PORTFOLIO_ILS = 50000
MAX_POSITION_ILS = 10000
RISK_LEVEL = "medium"

SECTOR_MAP = {
    "BEZQ": "Telecom", "TEVA": "Pharma", "NICE": "Tech",
    "ESLT": "Defense", "POLI": "Banking", "LUMI": "Banking",
    "ARYT": "Defense", "RPOL": "Defense / Optics", "IMCO": "Industrial",
    "NXSN": "Defense / Optics", "AVGL": "Defense", "REKA": "Defense",
    "EMDV": "Defense", "KARE": "Defense Electronics",
}

# ─── Page setup ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="invHunter",
    page_icon="📈",
    layout="wide",
)

st.title("📈 invHunter — TASE Trading Dashboard")
st.caption(f"Portfolio: ₪{PORTFOLIO_ILS:,}  |  Max position: ₪{MAX_POSITION_ILS:,}  |  Risk: {RISK_LEVEL}  |  Updated: {datetime.now().strftime('%H:%M:%S')}")


# ─── Market data ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)  # cache 5 min
def fetch_all_prices():
    rows = []
    for ticker in WATCHLIST:
        try:
            stock = yf.Ticker(f"{ticker}.TA")
            hist = stock.history(period="20d")
            info = stock.info
            if hist.empty:
                continue
            closes = hist["Close"]
            sma5 = closes.rolling(5).mean().iloc[-1]
            sma20 = closes.rolling(20).mean().iloc[-1]
            current = closes.iloc[-1]
            prev = closes.iloc[-2]
            pct = ((current - prev) / prev) * 100
            rows.append({
                "Ticker": ticker,
                "Sector": SECTOR_MAP.get(ticker, "—"),
                "Price (₪)": round(current, 2),
                "Change %": round(pct, 2),
                "SMA5": round(sma5, 2),
                "SMA20": round(sma20, 2),
                "▲ SMA5": current > sma5,
                "▲ SMA20": current > sma20,
                "Volume": int(hist["Volume"].iloc[-1]),
                "Avg Vol 10d": int(hist["Volume"].tail(10).mean()),
                "20d High": round(closes.tail(20).max(), 2),
                "20d Low": round(closes.tail(20).min(), 2),
                "P/E": info.get("trailingPE"),
                "_current": current,
                "_sma5": sma5,
                "_sma20": sma20,
                "_pct": pct,
                "_vol": int(hist["Volume"].iloc[-1]),
                "_avgvol": int(hist["Volume"].tail(10).mean()),
                "_high20": round(closes.tail(20).max(), 2),
                "_low20": round(closes.tail(20).min(), 2),
                "_pe": info.get("trailingPE"),
            })
        except Exception as e:
            st.warning(f"{ticker}: {e}")
    return pd.DataFrame(rows)


def ask_claude_single(data: dict) -> dict:
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
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Controls")
    run_analysis = st.button("🤖 Run Claude Analysis", type="primary", use_container_width=True)
    refresh = st.button("🔄 Refresh Prices", use_container_width=True)
    st.divider()
    st.markdown("**Filter by sector:**")
    sectors = ["All"] + sorted(set(SECTOR_MAP.values()))
    selected_sector = st.selectbox("Sector", sectors)
    st.divider()
    st.markdown("**IBKR Connection**")
    paper_mode = st.toggle("Paper Trading", value=True)
    ibkr_port = 7497 if paper_mode else 7496
    st.caption(f"Port: {ibkr_port} ({'📄 Paper' if paper_mode else '💰 LIVE'})")
    if not paper_mode:
        st.error("⚠️ LIVE MODE — real money")
    st.divider()
    st.markdown("**Settings**")
    st.metric("Portfolio", f"₪{PORTFOLIO_ILS:,}")
    st.metric("Max Position", f"₪{MAX_POSITION_ILS:,}")
    st.metric("Risk Level", RISK_LEVEL.capitalize())

if refresh:
    st.cache_data.clear()

# ─── Load prices ──────────────────────────────────────────────────────────────
with st.spinner("Fetching market data..."):
    df = fetch_all_prices()

if df.empty:
    st.error("No market data available.")
    st.stop()

if selected_sector != "All":
    df = df[df["Sector"] == selected_sector]

# ─── KPI row ──────────────────────────────────────────────────────────────────
gainers = (df["Change %"] > 0).sum()
losers = (df["Change %"] < 0).sum()
above_sma20 = df["▲ SMA20"].sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Stocks tracked", len(df))
col2.metric("Gainers today", int(gainers), delta=f"{gainers} up")
col3.metric("Losers today", int(losers), delta=f"-{losers} down", delta_color="inverse")
col4.metric("Above SMA20", int(above_sma20))

st.divider()

# ─── Price table ──────────────────────────────────────────────────────────────
st.subheader("📊 Live Prices")

display_cols = ["Ticker", "Sector", "Price (₪)", "Change %", "SMA5", "SMA20", "▲ SMA5", "▲ SMA20", "Volume", "P/E"]
display_df = df[display_cols].copy()


def color_change(val):
    if isinstance(val, float):
        color = "color: #22c55e" if val > 0 else "color: #ef4444" if val < 0 else ""
        return color
    return ""


def color_bool(val):
    if val is True:
        return "color: #22c55e"
    if val is False:
        return "color: #ef4444"
    return ""


styled = display_df.style \
    .map(color_change, subset=["Change %"]) \
    .map(color_bool, subset=["▲ SMA5", "▲ SMA20"]) \
    .format({
        "Price (₪)": "₪{:,.2f}",
        "Change %": "{:+.2f}%",
        "SMA5": "₪{:,.2f}",
        "SMA20": "₪{:,.2f}",
        "Volume": "{:,}",
        "P/E": lambda x: f"{x:.1f}" if x else "—",
    })

st.dataframe(styled, use_container_width=True, hide_index=True)

st.divider()

# ─── Claude Analysis ──────────────────────────────────────────────────────────
st.subheader("🤖 Claude Analysis")

if run_analysis:
    results = []
    progress = st.progress(0, text="Analyzing stocks...")
    total = len(df)

    for i, row in df.iterrows():
        ticker = row["Ticker"]
        progress.progress((list(df.index).index(i) + 1) / total, text=f"Analyzing {ticker}...")
        data = {
            "ticker": ticker,
            "current_price_ils": row["_current"],
            "pct_change_today": row["_pct"],
            "sma_5day": row["_sma5"],
            "sma_20day": row["_sma20"],
            "above_sma5": bool(row["▲ SMA5"]),
            "above_sma20": bool(row["▲ SMA20"]),
            "avg_volume_10d": row["_avgvol"],
            "volume_today": row["_vol"],
            "high_20d": row["_high20"],
            "low_20d": row["_low20"],
            "pe_ratio": row["_pe"],
        }
        try:
            decision = ask_claude_single(data)
            results.append({
                "Ticker": ticker,
                "Sector": row["Sector"],
                "Price (₪)": row["_current"],
                "Change %": row["_pct"],
                "Action": decision["action"].upper(),
                "Qty": decision["quantity"],
                "Limit (₪)": decision["limit_price_ils"],
                "Stop (₪)": decision["stop_loss_ils"],
                "Confidence": decision["confidence"],
                "Reasoning": decision["reasoning"],
            })
        except Exception as e:
            results.append({
                "Ticker": ticker, "Sector": row["Sector"],
                "Price (₪)": row["_current"], "Change %": row["_pct"],
                "Action": "ERROR", "Qty": 0, "Limit (₪)": None,
                "Stop (₪)": None, "Confidence": "—", "Reasoning": str(e),
            })
        time.sleep(0.5)

    progress.empty()
    st.session_state["analysis"] = results

def place_order_ibkr(ticker: str, action: str, quantity: int, limit_price: float, port: int) -> str:
    """Connect to IBKR TWS and place a limit order. Returns status message."""
    if quantity <= 0 or not limit_price:
        return "❌ Invalid order — no quantity or price"
    order_value = quantity * limit_price
    if order_value > MAX_POSITION_ILS:
        return f"❌ Order value ₪{order_value:,.0f} exceeds max ₪{MAX_POSITION_ILS:,}"
    try:
        ib = IB()
        ib.connect("127.0.0.1", port, clientId=20)
        contract = Stock(ticker, "TASE", "ILS")
        ib.qualifyContracts(contract)
        order = LimitOrder(action.upper(), quantity, round(limit_price, 2))
        order.tif = "DAY"
        trade = ib.placeOrder(contract, order)
        ib.sleep(1)
        ib.disconnect()
        return f"✅ Order placed: {action.upper()} {quantity}x {ticker} @ ₪{limit_price:,.2f} (₪{order_value:,.0f})"
    except Exception as e:
        return f"❌ IBKR error: {e}"


if "analysis" in st.session_state:
    results = st.session_state["analysis"]
    res_df = pd.DataFrame(results)

    # ── BUY signals — individual approve/reject ────────────────────────────────
    buys = res_df[res_df["Action"] == "BUY"]
    if not buys.empty:
        st.success(f"🟢 {len(buys)} BUY signal(s) — review and execute below")

        for _, row in buys.iterrows():
            ticker = row["Ticker"]
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 2, 2, 3])
                c1.metric(ticker, f"₪{row['Price (₪)']:,.2f}", f"{row['Change %']:+.2f}%")
                c2.metric("Qty", int(row["Qty"]))
                c3.metric("Limit", f"₪{row['Limit (₪)']:,.2f}" if row["Limit (₪)"] else "—")
                c4.metric("Stop", f"₪{row['Stop (₪)']:,.2f}" if row["Stop (₪)"] else "—")
                st.caption(f"Confidence: **{row['Confidence']}** — {row['Reasoning']}")

                order_value = (row["Qty"] or 0) * (row["Limit (₪)"] or 0)
                st.caption(f"Order value: ₪{order_value:,.0f}  |  Mode: {'📄 Paper' if paper_mode else '💰 LIVE'}")

                col_exec, col_skip = st.columns([1, 4])
                if col_exec.button(f"Execute {ticker}", key=f"exec_{ticker}", type="primary"):
                    with st.spinner(f"Sending order for {ticker} to IBKR..."):
                        result = place_order_ibkr(
                            ticker, "BUY",
                            int(row["Qty"]),
                            row["Limit (₪)"],
                            ibkr_port
                        )
                    if "✅" in result:
                        st.success(result)
                    else:
                        st.error(result)
                col_skip.button(f"Skip {ticker}", key=f"skip_{ticker}")
    else:
        st.info("⚪ No BUY signals")

    st.divider()
    st.markdown("**All decisions:**")

    def action_color(val):
        if val == "BUY":
            return "background-color: #166534; color: white"
        if val == "SELL":
            return "background-color: #991b1b; color: white"
        return ""

    styled_res = res_df.style \
        .map(action_color, subset=["Action"]) \
        .format({
            "Price (₪)": "₪{:,.2f}",
            "Change %": "{:+.2f}%",
            "Limit (₪)": lambda x: f"₪{x:,.2f}" if x else "—",
            "Stop (₪)": lambda x: f"₪{x:,.2f}" if x else "—",
            "Qty": lambda x: str(int(x)) if x else "0",
        })
    st.dataframe(styled_res, use_container_width=True, hide_index=True)
else:
    st.info("Click **Run Claude Analysis** in the sidebar to get trading recommendations.")
