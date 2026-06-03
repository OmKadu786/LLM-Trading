# AI-Trader: Quantitative LLM Day-Trading Engine

> **Notice to Future AI Assistants:** This document contains the critical state,
> logic architecture, and strategic parameters of the AI-Trader project. Read
> this thoroughly before making any modifications to the codebase.

## 1. Project Overview

**AI-Trader** is an autonomous, LLM-driven day-trading engine designed
specifically to pass Prop Firm evaluations (such as Trade The Pool / TTP). It
operates autonomously via GitHub Actions, analyzes market data using technical
indicators, and executes trades via the Alpaca API.

The core objective of the AI is to consistently achieve a **+0.66% daily account
profit** while adhering to strict prop-firm risk management rules (e.g., no
weekend holding, managing commission friction).

## 2. Core Trading Strategy

### 2.1 The "Top 12 Mega-Cap" Universe

The bot's trading universe is strictly restricted to the 12 most liquid US
equities: `AAPL, MSFT, NVDA, AMZN, META, GOOG, GOOGL, TSLA, LLY, AVGO, JPM, V`

- **Why:** In early testing, the bot lost significant capital
  (-$324/day) to Bid/Ask spread friction on illiquid small-cap stocks. By restricting to Mega-Caps, slippage and spread are reduced to near-zero ($0.01).

### 2.2 Portfolio Allocation & Overtrading

- **All-In Authorized:** The AI is explicitly permitted to use 100% of the
  account's cash on a single ticker if it identifies an "A+" setup.
  Diversification is not forced.
- **Overtrading Protection:** Because the bot runs every 5 minutes, it is
  strictly instructed via `agent_prompt.py` to hold existing profitable trends
  and avoid churning the account to death with commissions ($0.005/share TTP
  structure).

### 2.3 Risk Management & Liquidations

- **The 0.66% Daily Take-Profit:** The `check_target_sync()` function monitors
  the account equity. If the daily PnL crosses +0.66%, the script bypasses the
  AI and instantly liquidates all positions to lock in the win.
- **Overnight Holding:** The AI is permitted to hold positions overnight
  (Mon-Thu) if it confidently expects a gap-up.
- **Friday Weekend Hard-Stop:** Prop firms strictly forbid holding positions
  over the weekend. A hard-stop is baked into `main.py`: Every Friday at 3:45 PM
  ET, the bot automatically closes all open positions and cancels all pending
  orders, going 100% to cash.

## 3. Infrastructure & Execution

### 3.1 Deployment (GitHub Actions)

The entire engine runs for free on **GitHub Actions** via the
`.github/workflows/trade.yml` file.

- **Cron Schedule:** `*/5 13-21 * * 1-5`
- **Behavior:** It boots up an ephemeral ubuntu runner every 5 minutes during US
  Market Hours (9:00 AM - 5:00 PM ET). It installs dependencies, loads secrets
  into a `.env`, and runs `main.py --cron-hourly`.

### 3.2 The LLM Engine

- **Model:** DeepSeek (accessed via the OpenAI SDK wrapper).
- **Cost:** Extremely cheap ($0.14 per 1M tokens), allowing high-frequency
  5-minute technical checks without burning capital.
- **Framework:** Langchain Orchestration + FastMCP (Model Context Protocol).

## 4. MCP Tools (What the AI can do)

The AI has access to a suite of native Python tools (`tool_alpaca_mcp.py`),
including:

- **Execution:** `buy`, `close_position`, `update_brackets`,
  `place_trailing_stop`.
- **Data Gathering:**
  - `get_asset_news`: Real-time broker native headlines.
  - `get_price_history`: Feeds the AI three specific timeframes: 50 Daily bars,
    50 1-Hour bars, and 10 15-Minute bars. This gives both macro-trend and
    granular intraday visibility.
- **Quantitative Indicators (`get_technical_indicators`):** Utilizes the `ta`
  Python library to calculate 1-Hour timeframe metrics:
  - **RSI (14):** Identifies Overbought (>70) / Oversold (<30) conditions.
  - **MACD:** Evaluates bullish/bearish momentum crossovers.
  - **EMA (20 & 50):** Determines moving average support.
  - **VWAP (Volume Weighted Average Price):** The ultimate volume benchmark.

## 5. Next Steps / Known Limitations

- **The 5-Minute Blind Spot:** Because GitHub Actions runs on a cron schedule,
  there is a maximum 5-minute delay between market events and bot reaction. If a
  massive spike occurs in between those 5 minutes, the bot will miss it. _(Note:
  If millisecond reaction time becomes required, the architecture must be
  migrated from GitHub Actions to a continuous 24/7 Web Service like Render)._
