"""
invHunter Dashboard — Streamlit
Run: streamlit run dashboard.py
"""

import os
import json
import math
import re
import time
from datetime import datetime
from pathlib import Path

import networkx as nx
import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

import anthropic

# ─── Config ───────────────────────────────────────────────────────────────────
WATCHLIST = [
    "BEZQ", "TEVA", "NICE", "ESLT", "POLI", "LUMI",
    "ARYT", "RPOL", "IMCO", "NXSN", "AVGL", "REKA", "EMDV", "KARE",
    "EVGN", "MDIN",
    "DRAL", "PLSN", "ISRS", "TDRN", "CYBR",
    "GILT", "SPEN", "RATI", "CAMT", "NVMI",
]
PORTFOLIO_ILS = int(os.environ.get("PORTFOLIO_ILS", "50000"))      # set in .env
MAX_POSITION_ILS = int(os.environ.get("MAX_POSITION_ILS", "10000"))  # set in .env
RISK_LEVEL = "medium"

SECTOR_MAP = {
    "BEZQ": "Telecom", "TEVA": "Pharma", "NICE": "Tech",
    "ESLT": "Defense", "POLI": "Banking", "LUMI": "Banking",
    "ARYT": "Defense", "RPOL": "Defense / Optics", "IMCO": "Industrial",
    "NXSN": "Defense / Optics", "AVGL": "Defense", "REKA": "Defense",
    "EMDV": "Defense", "KARE": "Defense Electronics",
    "EVGN": "Biotech", "MDIN": "Real Estate",
    "DRAL": "Defense", "PLSN": "Defense", "ISRS": "Defense / Naval",
    "TDRN": "Defense / Comms", "CYBR": "Cyber Security",
    "GILT": "Defense / Satellite", "SPEN": "Defense / Satellite",
    "RATI": "Defense Electronics", "CAMT": "Defense Tech",
    "NVMI": "Defense Tech",
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
            # yfinance returns TASE prices in agorot — convert to ILS (÷100)
            closes = hist["Close"] / 100
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
    raw = re.sub(r"^```json?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Controls")
    run_analysis = st.button("🤖 Run Claude Analysis", type="primary", use_container_width=True)
    show_last = st.button("📂 Show Latest Analysis", use_container_width=True)
    refresh = st.button("🔄 Refresh Prices", use_container_width=True)
    st.divider()
    st.markdown("**Filter by sector:**")
    sectors = ["All"] + sorted(set(SECTOR_MAP.values()))
    selected_sector = st.selectbox("Sector", sectors)
    st.divider()
    st.markdown("**IBKR Connection**")
    live_allowed = os.environ.get("LIVE_TRADING", "").lower() == "true"
    paper_mode = st.toggle("Paper Trading", value=True, disabled=not live_allowed,
                           help=None if live_allowed else "Set LIVE_TRADING=true in .env to enable live orders")
    if not live_allowed:
        paper_mode = True
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

# ─── Load latest saved analysis ───────────────────────────────────────────────
if show_last:
    analysis_dir = Path(__file__).parent / "analysis"
    files = sorted(analysis_dir.glob("*.json"), reverse=True) if analysis_dir.exists() else []
    if not files:
        st.warning("No saved analysis found. Run Claude Analysis first.")
    else:
        saved = json.loads(files[0].read_text())
        ts = saved.get("timestamp", "")[:19].replace("T", " ")
        st.success(f"📂 Loaded: **{files[0].name}** — {ts}")
        st.session_state["analysis"] = [
            {
                "Ticker": r["ticker"],
                "Sector": SECTOR_MAP.get(r["ticker"], "—"),
                "Price (₪)": r.get("price_ils", 0),
                "Change %": r.get("pct_change", 0),
                "Action": r["action"].upper(),
                "Qty": r.get("quantity", 0),
                "Limit (₪)": r.get("limit_price_ils"),
                "Stop (₪)": r.get("stop_loss_ils"),
                "Confidence": r.get("confidence", "—"),
                "Reasoning": r.get("reasoning", ""),
            }
            for r in saved.get("results", [])
        ]

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

    # Auto-save to analysis/ folder
    from pathlib import Path
    analysis_dir = Path(__file__).parent / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    save_path = analysis_dir / f"{ts}.json"
    save_data = {
        "timestamp": datetime.now().isoformat(),
        "portfolio_ils": PORTFOLIO_ILS,
        "max_position_ils": MAX_POSITION_ILS,
        "results": [
            {
                "ticker": r["Ticker"],
                "action": r["Action"].lower(),
                "quantity": r["Qty"],
                "limit_price_ils": r["Limit (₪)"],
                "stop_loss_ils": r["Stop (₪)"],
                "confidence": r["Confidence"],
                "reasoning": r["Reasoning"],
                "price_ils": r["Price (₪)"],
                "pct_change": r["Change %"],
            }
            for r in results
        ],
    }
    save_path.write_text(json.dumps(save_data, indent=2, default=str))
    st.toast(f"💾 Saved: {save_path.name}", icon="✅")

def place_order_ibkr(ticker: str, action: str, quantity: int, limit_price: float, port: int) -> str:
    """Connect to IBKR TWS and place a limit order. Returns status message."""
    if quantity <= 0 or not limit_price:
        return "❌ Invalid order — no quantity or price"
    order_value = quantity * limit_price
    if order_value > MAX_POSITION_ILS:
        return f"❌ Order value ₪{order_value:,.0f} exceeds max ₪{MAX_POSITION_ILS:,}"
    try:
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())
        from ib_insync import IB, Stock, LimitOrder
        ib = IB()
        ib.connect("127.0.0.1", port, clientId=20)
        contract = Stock(ticker, "TASE", "ILS")
        ib.qualifyContracts(contract)
        order = LimitOrder(action.upper(), quantity, round(limit_price, 2))
        order.tif = "DAY"
        ib.placeOrder(contract, order)
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

st.divider()

# ─── Polymarket ───────────────────────────────────────────────────────────────
st.subheader("🎯 Polymarket — Prediction Markets")

POLYMARKET_TAGS = ["israel", "middle east", "economy", "finance", "fed", "inflation", "war", "tech"]

@st.cache_data(ttl=300)
def fetch_polymarket_markets(limit: int = 50) -> pd.DataFrame:
    try:
        resp = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={"limit": limit, "active": "true", "closed": "false"},
            timeout=10,
        )
        resp.raise_for_status()
        markets = resp.json()
    except Exception as e:
        return pd.DataFrame(), str(e)

    rows = []
    for m in markets:
        outcomes = m.get("outcomes", "[]")
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except Exception:
                outcomes = []
        prices = m.get("outcomePrices", "[]")
        if isinstance(prices, str):
            try:
                prices = json.loads(prices)
            except Exception:
                prices = []

        yes_price = None
        no_price = None
        if len(outcomes) == 2 and len(prices) == 2:
            for idx, o in enumerate(outcomes):
                if str(o).lower() == "yes":
                    try:
                        yes_price = round(float(prices[idx]) * 100, 1)
                    except Exception:
                        pass
                elif str(o).lower() == "no":
                    try:
                        no_price = round(float(prices[idx]) * 100, 1)
                    except Exception:
                        pass

        volume = m.get("volumeNum") or m.get("volume")
        try:
            volume = float(volume) if volume else 0.0
        except Exception:
            volume = 0.0

        rows.append({
            "Market": m.get("question", "—"),
            "YES %": yes_price,
            "NO %": no_price,
            "Volume ($)": volume,
            "End Date": (m.get("endDate") or "")[:10],
            "URL": m.get("url", ""),
        })

    df_pm = pd.DataFrame(rows)
    if not df_pm.empty:
        df_pm = df_pm.sort_values("Volume ($)", ascending=False).reset_index(drop=True)
    return df_pm, None


with st.spinner("Fetching Polymarket data..."):
    pm_df, pm_err = fetch_polymarket_markets()

if pm_err:
    st.error(f"Polymarket fetch error: {pm_err}")
elif pm_df.empty:
    st.warning("No Polymarket data available.")
else:
    poly_col1, poly_col2 = st.columns([3, 1])
    with poly_col1:
        pm_search = st.text_input("Filter markets", placeholder="e.g. israel, fed, crypto…", label_visibility="collapsed")
    with poly_col2:
        pm_limit = st.selectbox("Show", [25, 50, 100], index=1, label_visibility="collapsed")

    filtered = pm_df.head(pm_limit)
    if pm_search.strip():
        mask = filtered["Market"].str.contains(pm_search.strip(), case=False, na=False)
        filtered = filtered[mask]

    def pm_yes_color(val):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return ""
        if val >= 70:
            return "color: #22c55e; font-weight: bold"
        if val <= 30:
            return "color: #ef4444"
        return "color: #facc15"

    def pm_no_color(val):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return ""
        if val >= 70:
            return "color: #ef4444; font-weight: bold"
        if val <= 30:
            return "color: #22c55e"
        return "color: #facc15"

    display_pm = filtered[["Market", "YES %", "NO %", "Volume ($)", "End Date"]].copy()

    styled_pm = display_pm.style \
        .map(pm_yes_color, subset=["YES %"]) \
        .map(pm_no_color, subset=["NO %"]) \
        .format({
            "YES %": lambda x: f"{x:.1f}%" if x is not None and not (isinstance(x, float) and pd.isna(x)) else "—",
            "NO %": lambda x: f"{x:.1f}%" if x is not None and not (isinstance(x, float) and pd.isna(x)) else "—",
            "Volume ($)": lambda x: f"${x:,.0f}" if x else "—",
        })

    st.dataframe(styled_pm, use_container_width=True, hide_index=True)
    st.caption(f"Showing {len(filtered)} of {len(pm_df)} active markets · Refreshes every 5 min")

st.divider()

# ─── Graph Arbitrage Scanner ───────────────────────────────────────────────────
st.subheader("🕸️ Graph Arbitrage Scanner")
st.caption("Detects probability violations across related Polymarket markets using graph theory")

# Topics used to detect logical relationships between markets
ENTITY_KEYWORDS = {
    "trump":      ["trump", "donald", "white house", "oval office"],
    "iran":       ["iran", "iranian", "tehran"],
    "russia":     ["russia", "russian", "putin", "ukraine", "moscow"],
    "china":      ["china", "chinese", "beijing", "taiwan", "xi jinping"],
    "israel":     ["israel", "israeli", "gaza", "hamas", "netanyahu", "idf", "west bank"],
    "fed":        ["federal reserve", "fed rate", "fomc", "interest rate", "powell"],
    "inflation":  ["inflation", "cpi", "pce", "deflation", "price index"],
    "recession":  ["recession", "gdp", "economic contraction", "unemployment"],
    "bitcoin":    ["bitcoin", "btc", "crypto", "ethereum", "eth"],
    "election":   ["election", "vote", "ballot", "democrat", "republican", "senate", "congress"],
    "war":        ["war", "conflict", "military", "invasion", "attack", "strike"],
    "ai":         ["artificial intelligence", "ai ", "openai", "chatgpt", "llm"],
}


def get_entities(question: str) -> frozenset:
    q = question.lower()
    return frozenset(k for k, kws in ENTITY_KEYWORDS.items() if any(kw in q for kw in kws))


@st.cache_data(ttl=300)
def fetch_markets_for_arb(limit: int = 300):
    try:
        resp = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={"limit": limit, "active": "true", "closed": "false"},
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        return [], str(e)

    nodes = []
    for m in raw:
        outcomes = m.get("outcomes", "[]")
        if isinstance(outcomes, str):
            try: outcomes = json.loads(outcomes)
            except: outcomes = []
        prices = m.get("outcomePrices", "[]")
        if isinstance(prices, str):
            try: prices = json.loads(prices)
            except: prices = []

        yes_prob = None
        if len(outcomes) == 2 and len(prices) == 2:
            for idx, o in enumerate(outcomes):
                if str(o).lower() == "yes":
                    try: yes_prob = float(prices[idx])
                    except: pass

        if yes_prob is None or yes_prob <= 0 or yes_prob >= 1:
            continue

        entities = get_entities(m.get("question", ""))
        if not entities:
            continue

        vol = m.get("volumeNum") or m.get("volume") or 0
        try: vol = float(vol)
        except: vol = 0.0

        nodes.append({
            "id":       m.get("id", ""),
            "question": m.get("question", ""),
            "yes_prob": yes_prob,
            "entities": entities,
            "volume":   vol,
            "url":      m.get("url", ""),
        })

    return nodes, None


def scan_arbitrage(nodes: list, min_gap: float = 0.15, min_vol: float = 0):
    G = nx.DiGraph()

    for i, n in enumerate(nodes):
        G.add_node(i, **{k: v for k, v in n.items() if k != "entities"})

    violations = []
    edges_added = 0

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            a, b = nodes[i], nodes[j]
            shared = a["entities"] & b["entities"]
            if not shared:
                continue

            pa, pb = a["yes_prob"], b["yes_prob"]
            diff = abs(pa - pb)

            # Add directed edges with -log(p) weights (Bellman-Ford arb detection)
            G.add_edge(i, j, weight=-math.log(pb), shared=shared)
            G.add_edge(j, i, weight=-math.log(pa), shared=shared)
            edges_added += 1

            # Flag pairs where probabilities are suspiciously far apart
            if diff >= min_gap:
                higher = a if pa >= pb else b
                lower  = b if pa >= pb else a
                if min(higher["volume"], lower["volume"]) >= min_vol:
                    violations.append({
                        "Topic":      ", ".join(sorted(shared)),
                        "Market A":   higher["question"][:90],
                        "P(A) %":     round(higher["yes_prob"] * 100, 1),
                        "Market B":   lower["question"][:90],
                        "P(B) %":     round(lower["yes_prob"] * 100, 1),
                        "Gap %":      round(diff * 100, 1),
                        "Vol A ($)":  round(higher["volume"]),
                        "Vol B ($)":  round(lower["volume"]),
                    })

    violations.sort(key=lambda x: x["Gap %"], reverse=True)

    # Negative cycle detection via Bellman-Ford (samples connected subgraphs)
    neg_cycles = 0
    seen_nodes = set()
    for start in list(G.nodes()):
        if start in seen_nodes:
            continue
        component = nx.descendants(G, start) | {start}
        seen_nodes |= component
        sub = G.subgraph(component).copy()
        try:
            nx.find_negative_cycle(sub, start)
            neg_cycles += 1
        except nx.NetworkXError:
            pass
        except nx.exception.NetworkXUnbounded:
            neg_cycles += 1

    return violations, neg_cycles, edges_added


if "arb_results" not in st.session_state:
    st.session_state["arb_results"] = None

arb_col1, arb_col2, arb_col3 = st.columns([2, 2, 1])
with arb_col1:
    min_gap_pct = st.slider("Min probability gap %", 5, 50, 15, 5)
with arb_col2:
    min_vol_k = st.slider("Min volume per market ($k)", 0, 500, 0, 10)
with arb_col3:
    run_arb = st.button("🔍 Scan for Arb", type="primary", use_container_width=True)

if run_arb:
    with st.spinner("Fetching 300 markets and building probability graph…"):
        arb_nodes, arb_err = fetch_markets_for_arb(300)
    if arb_err:
        st.error(f"Fetch error: {arb_err}")
    else:
        with st.spinner(f"Scanning {len(arb_nodes)} markets for probability violations…"):
            viols, neg_cyc, n_edges = scan_arbitrage(
                arb_nodes,
                min_gap=min_gap_pct / 100,
                min_vol=min_vol_k * 1000,
            )
        st.session_state["arb_results"] = {
            "violations": viols,
            "neg_cycles": neg_cyc,
            "n_edges": n_edges,
            "n_nodes": len(arb_nodes),
        }

if st.session_state["arb_results"]:
    r = st.session_state["arb_results"]
    viols = r["violations"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Markets scanned",        r["n_nodes"])
    m2.metric("Relationships mapped",   r["n_edges"])
    m3.metric("Violations found",       len(viols))
    m4.metric("Negative cycles",        r["neg_cycles"])

    if viols:
        st.success(f"🟡 {len(viols)} potential arbitrage opportunity{'s' if len(viols) != 1 else ''} detected")
        viol_df = pd.DataFrame(viols)

        def gap_color(val):
            if val >= 30: return "background-color: #7f1d1d; color: white"
            if val >= 20: return "background-color: #991b1b; color: white"
            return "background-color: #b45309; color: white"

        styled_viols = viol_df.style \
            .map(gap_color, subset=["Gap %"]) \
            .format({
                "P(A) %":    "{:.1f}%",
                "P(B) %":    "{:.1f}%",
                "Gap %":     "{:.1f}%",
                "Vol A ($)": "${:,.0f}",
                "Vol B ($)": "${:,.0f}",
            })

        st.dataframe(styled_viols, use_container_width=True, hide_index=True)
        st.caption(
            "A violation means two logically related markets have a probability gap that may be exploitable. "
            "Higher gap = stronger signal. Always verify liquidity before trading."
        )
    else:
        st.info("No violations found with current filters. Try lowering the minimum gap.")
