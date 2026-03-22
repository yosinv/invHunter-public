# 🕸️ Graph Arbitrage Scanner

A tool built into the invHunter dashboard that detects probability violations across related Polymarket prediction markets using graph theory and the Bellman-Ford algorithm.

---

## How It Works

### 1. Fetch Markets

Pulls **300 active, unclosed markets** from the [Polymarket Gamma API](https://gamma-api.polymarket.com/markets).

Only markets with a valid binary YES/NO price are included. Results are cached for 5 minutes.

---

### 2. Entity Tagging

Each market question is scanned for keywords and tagged with one or more **topics**:

| Topic | Example keywords |
|---|---|
| `trump` | trump, donald, white house |
| `iran` | iran, iranian, tehran |
| `israel` | israel, gaza, hamas, netanyahu, idf |
| `russia` | russia, putin, ukraine |
| `china` | china, beijing, taiwan, xi jinping |
| `fed` | federal reserve, fomc, interest rate, powell |
| `inflation` | inflation, cpi, pce, deflation |
| `recession` | recession, gdp, unemployment |
| `war` | war, conflict, military, invasion |
| `bitcoin` | bitcoin, btc, crypto, ethereum |
| `election` | election, vote, senate, congress |
| `ai` | artificial intelligence, openai, chatgpt |

Markets with no matching topic are excluded — they can't be meaningfully compared.

---

### 3. Graph Construction

A **directed graph** is built using [NetworkX](https://networkx.org/):

```
Nodes  →  individual markets
Edges  →  logical relationships between markets that share a topic
Weights → -log(probability of destination node's YES price)
```

The `-log(p)` weighting is the standard Bellman-Ford arbitrage trick borrowed from currency exchange arbitrage:

- In forex arb: multiply exchange rates around a cycle → if product > 1, profit exists
- In log space: sum the `-log` weights → if sum < 0 (negative cycle), arbitrage exists

Two markets that share a topic get a **bidirectional edge**, each direction weighted by the probability of the target market.

---

### 4. Detection Methods

#### Probability Violation Table

For every pair of related markets (sharing at least one topic), the scanner checks:

```
gap = |P(A) - P(B)|
```

If `gap ≥ threshold` (default 15%), the pair is flagged as a potential violation.

**Why does a gap matter?**
If Event A logically implies Event B, probability theory requires:

```
P(A) ≤ P(B)
```

When this is violated — meaning a more specific event is priced *higher* than a broader one — the market is internally inconsistent. That inconsistency can be traded.

Results are sorted by gap size (largest first) and color-coded:

| Color | Gap |
|---|---|
| 🟡 Orange | 15–20% |
| 🔴 Dark red | 20–30% |
| ⬛ Deep red | 30%+ |

#### Negative Cycle Detection

After the graph is built, Bellman-Ford is run on each connected subgraph:

```python
nx.find_negative_cycle(subgraph, source_node)
```

A **negative cycle** means there exists a path through a set of related markets where the product of their implied probabilities exceeds 1.0 — mathematically impossible, and therefore a guaranteed arbitrage in theory.

Each unique connected component is checked independently to avoid redundant computation.

---

### 5. Controls

| Control | What it does |
|---|---|
| **Min probability gap %** | Sets the threshold for flagging violations (5–50%). Lower = more signals, more noise. |
| **Min volume per market ($k)** | Filters out illiquid markets. Set to 0 to see everything. |
| **Scan button** | Triggers a fresh fetch + scan. Results persist in the session until you scan again. |

---

## Output Metrics

| Metric | Meaning |
|---|---|
| Markets scanned | Total markets with valid YES/NO prices and at least one topic tag |
| Relationships mapped | Total directed edges added to the graph |
| Violations found | Market pairs flagged above the gap threshold |
| Negative cycles | Connected subgraphs containing at least one Bellman-Ford negative cycle |

---

## Practical Limits

Theoretical violations don't always translate into profitable trades. Common reasons they fail:

- **Low liquidity** — not enough order book depth to fill both legs
- **Execution lag** — prices can move between placing the first and second order
- **Fees and slippage** — can erase thin margins on small gaps
- **Ambiguous resolution** — some markets resolve unexpectedly, adding hidden risk
- **Correlation, not implication** — two markets sharing a topic doesn't always mean one logically implies the other

Use violations as a **starting point for manual review**, not as automatic trade signals.

---

## Dependencies

- [`networkx`](https://networkx.org/) — graph construction and Bellman-Ford cycle detection
- [`requests`](https://requests.readthedocs.io/) — Polymarket API calls
- [`streamlit`](https://streamlit.io/) — dashboard UI
