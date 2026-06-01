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

#### Full Daily Equity Curve (April 17 – Present)

| Date       | Total Equity ($) | Daily Return (%) | Phase |
| :--------- | :--------------- | :--------- | :--------- |
| 2026-04-17 | `$30,000.00` | `+0.00%` | Phase 1: Margin & Small Caps |
| 2026-04-18 | `$30,063.04` | `+0.21%` | Phase 1: Margin & Small Caps |
| 2026-04-21 | `$30,657.24` | `+1.98%` | Phase 1: Margin & Small Caps |
| 2026-04-22 | `$29,121.20` | `-5.01%` | Phase 1: Margin & Small Caps (Leverage Crush) |
| 2026-04-23 | `$32,497.45` | `+11.59%` | Phase 1: Margin & Small Caps |
| 2026-04-24 | `$32,043.68` | `-1.40%` | Phase 1: Margin & Small Caps |
| 2026-04-25 | `$33,011.43` | `+3.02%` | Phase 1: Margin & Small Caps |
| 2026-04-28 | `$32,862.35` | `-0.45%` | Phase 1: Margin & Small Caps |
| 2026-04-29 | `$32,355.27` | `-1.54%` | Phase 1: Margin & Small Caps |
| 2026-04-30 | `$32,314.92` | `-0.12%` | Phase 1: Margin & Small Caps |
| 2026-05-01 | `$32,173.57` | `-0.44%` | Phase 1: Margin & Small Caps |
| 2026-05-02 | `$32,823.76` | `+2.02%` | Phase 1: Margin & Small Caps |
| 2026-05-06 | `$31,843.43` | `-2.99%` | Phase 1: Margin & Small Caps |
| 2026-05-07 | `$31,978.64` | `+0.42%` | Phase 1: Margin & Small Caps |
| 2026-05-08 | `$31,694.76` | `-0.89%` | Phase 1: Margin & Small Caps |
| 2026-05-12 | `$31,650.40` | `-0.14%` | Phase 1: Margin & Small Caps |
| 2026-05-13 | `$31,234.15` | `-1.32%` | Phase 1: Margin & Small Caps |
| 2026-05-14 | `$31,591.68` | `+1.14%` | Phase 1: Margin & Small Caps |
| 2026-05-15 | `$31,704.58` | `+0.36%` | Phase 1: Margin & Small Caps |
| 2026-05-16 | `$31,561.48` | `-0.45%` | Phase 1: Margin & Small Caps |
| 2026-05-19 | `$31,542.13` | `-0.06%` | Phase 1: Margin & Small Caps |
| **2026-05-20** | **`$31,251.03`** | **`-0.92%`** | **Phase 2: Transition to Top 12 & Cash Account** |
| 2026-05-21 | `$31,271.76` | `+0.07%` | Phase 2: Top 12 & Cash |
| 2026-05-22 | `$31,464.98` | `+0.62%` | Phase 2: Top 12 & Cash |
| 2026-05-23 | `$31,694.26` | `+0.73%` | Phase 2: Top 12 & Cash |
| 2026-05-27 | `$31,412.38` | `-0.89%` | Phase 2: Top 12 & Cash (Choppy Day) |
| 2026-05-28 | `$32,256.08` | `+2.69%` | Phase 2: Top 12 & Cash (Overnight Gap) |
| 2026-05-29 | `$32,246.99` | `-0.03%` | Phase 2: Top 12 & Cash (Cut small loss) |
| 2026-05-30 | `$32,884.00` | `+1.98%` | Phase 2: Top 12 & Cash (Overnight Gap) |

---

## 📊 Key Insights

1. **Leverage is Dangerous (Phase 1):** In Phase 1, using margin caused wild, unpredictable swings (e.g., -5.01% on April 22, -2.99% on May 6). This volatility is incompatible with Prop Firm drawdown rules.
2. **Keep Losers Small, Let Winners Run (Phase 2):** After restricting the bot to 1x leverage and Mega-Caps, the daily breakdown perfectly reflects professional swing trading. On bad days, the bot takes controlled losses (-0.89%). On good days, it holds overnight and rips +2.69% and +1.98%.
3. **Slippage is the Enemy:** Moving to Mega-Caps completely eliminated the hidden bid/ask spread fees that destroyed the Phase 1 strategy.
