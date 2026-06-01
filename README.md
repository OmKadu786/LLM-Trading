# AI Trader - LLM Powered Quantitative Trading

## 📌 Overview

This repository is an implementation and extension of the research conducted by
[HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader). It features an autonomous
trading agent powered by Large Language Models (LLMs) that makes real-time
trading decisions based on live price data, financial news, and technical
analysis.

This specific implementation is optimized for the **US Nasdaq-100 Market** using
the **DeepSeek-V3 Chat** model. While utilizing the chat variant for
tool-calling stability, the system implements an **agentic reasoning loop** that
allows the model to perform multi-step analysis similar to dedicated reasoning
models.

---

## 🧠 Trading Logic & Strategy

The agent has been completely overhauled into a high-frequency, Prop-Firm-optimized swing trader running every **15 minutes**.

### 1. The "Top 12 Mega-Cap" Universe
To eliminate slippage and high friction costs (which destroy small-cap strategies), the bot is strictly restricted to trading only the most liquid Mega-Cap stocks: `AAPL, MSFT, NVDA, AMZN, META, GOOG, GOOGL, TSLA, LLY, AVGO, JPM, V`.

### 2. Quantitative Engine (Technical Analysis)
The agent utilizes `pandas_ta` to pull granular 15-minute, 1-hour, and Daily candles, calculating real-time:
*   **VWAP** (Volume Weighted Average Price)
*   **RSI (14)** and **MACD** for momentum divergence
*   **EMA (20 & 50)** for trend confirmation

### 3. Execution & Allocation
*   **All-In Conviction:** The agent is authorized to deploy up to 100% of the portfolio into a single stock if the technical setup is A+.
*   **Overnight Swing Trading:** The agent intentionally holds strong momentum stocks overnight to capture massive morning gap-ups.

### 4. The "Dual-Guard" Risk Management System
To survive Prop Firm evaluations (like Trade The Pool), the core execution script (`main.py`) acts as a strict supervisor over the LLM:
*   **Trailing Profit Guard:** If the daily account PnL hits `+1.00%`, a trailing stop activates. It ratchets exactly `-0.85%` behind the absolute daily peak. This gives winners infinite upside (e.g., catching +3.0% gap-ups) while guaranteeing profits are locked in if the market reverses.
*   **Max Daily Loss:** A hard `-1.50%` kill switch. If the account drops 1.5% in a single day, the script instantly dumps all positions and puts the AI to sleep to prevent revenge trading.
*   **Weekend Hard-Stop:** The bot automatically liquidates all holdings at 3:45 PM ET on Fridays to prevent holding risk over the weekend.

### 5. Infrastructure Hack
To bypass GitHub Actions throttling on free tiers (which drop `*/15` schedules at the top of the hour), the cron job is specifically offset to run at `:02, :17, :32, :47`. This sneaks the execution requests past GitHub's load balancers.

---

## 🛠 Technologies & APIs

- **Model:** `DeepSeek-V3` (Reasoning Model)

- **News/Search:** [Jina Search](https://jina.ai/)
- **Architecture:**
  [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) - Used to
  connect the AI to specialized tools (Price, Trade, Search, Math).
- **Execution:** Python 3.x

---

## 📈 Live Paper Performance (April 17, 2026 – Present)

The agent has been running live in a paper trading environment, undergoing a massive architectural shift mid-flight.

### Phase 1: The "Wild West" (April 17 – May 19)
*   **Strategy:** Trading a universe of 100+ stocks, utilizing leverage (margin), and running without robust technical indicators.
*   **Outcome:** The system suffered from massive "friction" (bid/ask spread slippage and high commission fees on small-cap stocks). Leverage caused outsized drawdowns on choppy days.

### Phase 2: The "Mega-Cap Upgrade" (May 20 – Present)
*   **The Pivot:** On May 20th, leverage was strictly disabled (reverting to a 1x Cash Account) and the universe was restricted entirely to the **Top 12 Mega-Caps**. Technical indicators (VWAP, RSI, MACD) and Overnight Swing permissions were injected into the AI's brain.
*   **Outcome:** The win rate and profitability skyrocketed as friction costs dropped to near zero. 

**Performance Since May 20th Upgrade:**
*   **Total Trades:** 96
*   **Gross P&L:** +$1,477.74
*   **TTP Commissions:** -$72.00
*   **Total Net P&L:** **+$1,405.74**

#### Daily Breakdown (Since Upgrade)
| Date       | Market Condition | Net P&L | Bot Action |
| :--------- | :--------------- | :--------- | :--------- |
| 2026-05-20 | Choppy / Red     | `-$21.50`  | Cut small losses instantly |
| 2026-05-21 | Trending Up      | `+$61.32`  | Scalped, held overnight |
| 2026-05-22 | Morning Gap      | `+$225.62` | Liquidated gap-up |
| 2026-05-26 | Choppy / Red     | `-$299.83` | Cut losses, held TSLA overnight |
| 2026-05-27 | Massive Gap-Up   | `+$829.44` | Sold TSLA at peak |
| 2026-05-28 | Choppy / Recovery| `-$104.90` | Cut MSFT loss, re-bought dip |
| 2026-05-29 | Massive Gap-Up   | `+$715.59` | Sold MSFT gap-up |

---

## 📊 Key Insights

1. **Keep Losers Small, Let Winners Run:** The Phase 2 daily breakdown perfectly reflects professional swing trading. On bad days, the bot cuts losses at -$100 to -$300. On good days, it holds overnight and rips +$700 to +$800.
2. **Slippage is the Enemy:** Moving to Mega-Caps completely eliminated the hidden bid/ask spread fees that destroyed the Phase 1 strategy.
3. **Patience Pays:** By implementing a 15-minute execution cycle and explicitly telling the AI "not to overtrade", commission bloat was eliminated, allowing the bot to simply sit in cash or confidently hold a strong position without churning fees.
