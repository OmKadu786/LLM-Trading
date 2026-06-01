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

## 📈 Backtest Results (Oct 1 – Nov 7, 2025)

The agent was tested over a 5-week period starting with **$10,000.00** of
initial capital.

- **Final Equity:** $10,838.93
- **Total Return:** **+8.39%** ✅
- **Peak Return:** **+10.49%** (Reached on Nov 05, 2025)

### Daily Equity Performance

| Date       | Total Equity ($) | Return (%) |
| :--------- | :--------------- | :--------- |
| 2025-10-01 | $10,065.67       | +0.66%     |
| 2025-10-02 | $10,055.45       | +0.55%     |
| 2025-10-03 | $10,004.05       | +0.04%     |
| 2025-10-06 | $10,215.09       | +2.15%     |
| 2025-10-07 | $10,199.71       | +2.00%     |
| 2025-10-08 | $10,285.43       | +2.85%     |
| 2025-10-09 | $10,302.28       | +3.02%     |
| 2025-10-10 | $10,097.13       | +0.97%     |
| 2025-10-13 | $10,194.99       | +1.95%     |
| 2025-10-14 | $10,236.13       | +2.36%     |
| 2025-10-15 | $10,269.39       | +2.69%     |
| 2025-10-16 | $10,246.90       | +2.47%     |
| 2025-10-17 | $10,327.98       | +3.28%     |
| 2025-10-20 | $10,467.57       | +4.68%     |
| 2025-10-21 | $10,459.74       | +4.60%     |
| 2025-10-22 | $10,332.84       | +3.33%     |
| 2025-10-23 | $10,437.64       | +4.38%     |
| 2025-10-24 | $10,576.31       | +5.76%     |
| 2025-10-27 | $10,837.25       | +8.37%     |
| 2025-10-28 | $11,003.14       | +10.03%    |
| 2025-10-29 | $11,027.33       | +10.27%    |
| 2025-10-30 | $10,967.51       | +9.68%     |
| 2025-10-31 | $10,972.03       | +9.72%     |
| 2025-11-03 | $11,018.25       | +10.18%    |
| 2025-11-04 | $10,912.78       | +9.13%     |
| 2025-11-05 | $11,049.44       | +10.49%    |
| 2025-11-06 | $10,885.14       | +8.85%     |
| 2025-11-07 | $10,838.93       | +8.39%     |

---

## 📊 Key Insights

1. **Concentration Alpha:** The agent generated its highest returns by
   concentrating into **NVDA** and **MSFT** during the late-October tech surge.
2. **Risk Mitigation:** When the market cooled in early November, the agent
   successfully pivoted to defensive Holdings (**XEL**, **PEP**) and increased
   its cash buffer, preventing a larger drawdown and locking in the 8% benchmark
   target.
3. **Cost Efficiency:** Using DeepSeek-V3 allowed for a full 1-month
   high-precision backtest for approximately **$3.00** in API tokens,
   significantly cheaper than equivalent models like GPT-4o.
