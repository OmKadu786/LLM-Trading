# AI Trader - LLM Powered Quantitative Trading

## 📌 Overview
This repository is an implementation and extension of the research conducted by [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader). It features an autonomous trading agent powered by Large Language Models (LLMs) that makes real-time trading decisions based on live price data, financial news, and technical analysis.

This specific implementation is optimized for the **US Nasdaq-100 Market** using the **DeepSeek-V3** reasoning model.

---

## 🧠 Trading Logic & Strategy

The agent operates on an hourly frequency using a **multi-step reasoning loop** (Chain-of-Thought):

1.  **Data Gathering:** The agent pulls hourly OHLC prices for the top 100 Nasdaq stocks.
2.  **Information Retrieval:** It uses a search tool to scan for macro-economic news and stock-specific catalysts (earnings, product launches, etc.).
3.  **Analytical Reasoning:** Utilizing a dedicated Math tool, the agent calculates technical indicators like RSI and moving averages.
4.  **Strategic Execution:** The agent follows a **"Barbell Strategy"**—concentrating capital into high-conviction technology leaders (like NVDA, MSFT) while maintaining a safety net of defensive consumer staples and utilities (like PEP, XEL).

---

## 🛠 Technologies & APIs

-   **Model:** `DeepSeek-V3` (Reasoning Model)
-   **Market Data:** [Alpha Vantage](https://www.alphavantage.co/)
-   **News/Search:** [Jina Search](https://jina.ai/)
-   **Architecture:** [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) - Used to connect the AI to specialized tools (Price, Trade, Search, Math).
-   **Execution:** Python 3.x

---

## 📈 Backtest Results (Oct 1 – Nov 7, 2025)

The agent was tested over a 5-week period starting with **$10,000.00** of initial capital.

-   **Final Equity:** $10,838.93
-   **Total Return:** **+8.39%** ✅
-   **Peak Return:** **+10.49%** (Reached on Nov 05, 2025)

### Daily Equity Performance

| Date | Total Equity ($) | Return (%) |
| :--- | :--- | :--- |
| 2025-10-01 | $10,065.67 | +0.66% |
| 2025-10-02 | $10,055.45 | +0.55% |
| 2025-10-03 | $10,004.05 | +0.04% |
| 2025-10-06 | $10,215.09 | +2.15% |
| 2025-10-07 | $10,199.71 | +2.00% |
| 2025-10-08 | $10,285.43 | +2.85% |
| 2025-10-09 | $10,302.28 | +3.02% |
| 2025-10-10 | $10,097.13 | +0.97% |
| 2025-10-13 | $10,194.99 | +1.95% |
| 2025-10-14 | $10,236.13 | +2.36% |
| 2025-10-15 | $10,269.39 | +2.69% |
| 2025-10-16 | $10,246.90 | +2.47% |
| 2025-10-17 | $10,327.98 | +3.28% |
| 2025-10-20 | $10,467.57 | +4.68% |
| 2025-10-21 | $10,459.74 | +4.60% |
| 2025-10-22 | $10,332.84 | +3.33% |
| 2025-10-23 | $10,437.64 | +4.38% |
| 2025-10-24 | $10,576.31 | +5.76% |
| 2025-10-27 | $10,837.25 | +8.37% |
| 2025-10-28 | $11,003.14 | +10.03% |
| 2025-10-29 | $11,027.33 | +10.27% |
| 2025-10-30 | $10,967.51 | +9.68% |
| 2025-10-31 | $10,972.03 | +9.72% |
| 2025-11-03 | $11,018.25 | +10.18% |
| 2025-11-04 | $10,912.78 | +9.13% |
| 2025-11-05 | $11,049.44 | +10.49% |
| 2025-11-06 | $10,885.14 | +8.85% |
| 2025-11-07 | $10,838.93 | +8.39% |

---

## 📊 Key Insights

1.  **Concentration Alpha:** The agent generated its highest returns by concentrating into **NVDA** and **MSFT** during the late-October tech surge.
2.  **Risk Mitigation:** When the market cooled in early November, the agent successfully pivoted to defensive Holdings (**XEL**, **PEP**) and increased its cash buffer, preventing a larger drawdown and locking in the 8% benchmark target.
3.  **Cost Efficiency:** Using DeepSeek-V3 allowed for a full 1-month high-precision backtest for approximately **$3.00** in API tokens, significantly cheaper than equivalent models like GPT-4o.
