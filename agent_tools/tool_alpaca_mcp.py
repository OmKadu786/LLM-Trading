"""
Single Alpaca MCP server — handles both price data AND trade execution.
Replaces tool_trade_alpaca.py + tool_get_price_alpaca.py (two files → one).
Run on TRADE_HTTP_PORT (8002 by default).
"""
import os, sys, json
from typing import Dict, Any
from fastmcp import FastMCP

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tools.alpaca_client import get_alpaca_client

mcp = FastMCP("Alpaca")



# ── Trade Tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def buy(symbol: str, amount: int, take_profit: float = None, stop_loss: float = None) -> Dict[str, Any]:
    """Buy shares via Alpaca. Args: symbol (e.g. 'AAPL'), amount (positive int), take_profit (optional limit price), stop_loss (optional stop price)."""
    if amount <= 0:
        return {"error": f"Amount must be positive, got {amount}"}
    c = get_alpaca_client()
    price = c.get_latest_price(symbol)
    if price is None:
        return {"error": f"Could not get price for {symbol}"}
    acct = c.get_account()
    if price * amount > acct["buying_power"]:
        return {"error": "Insufficient buying power", "required": price * amount,
                "buying_power": acct["buying_power"]}
    try:
        result = c.buy(symbol, amount, take_profit=take_profit, stop_loss=stop_loss)
        return result
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def sell(symbol: str, amount: int) -> Dict[str, Any]:
    """Sell shares via Alpaca. Args: symbol (e.g. 'AAPL'), amount (positive int)."""
    if amount <= 0:
        return {"error": f"Amount must be positive, got {amount}"}
    c = get_alpaca_client()
    pos = c.get_position(symbol)
    if not pos or pos["qty"] < amount:
        return {"error": f"Insufficient shares", "have": pos["qty"] if pos else 0}
    try:
        result = c.sell(symbol, amount)
        return result
    except Exception as e:
        return {"error": str(e)}


# ── Price Tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def get_price_live(symbol: str, date: str) -> Dict[str, Any]:
    """Get live Alpaca quote for a symbol. Returns open price; high/low/close unavailable live."""
    price = get_alpaca_client().get_latest_price(symbol)
    if price is None:
        return {"error": f"Could not get price for {symbol}", "symbol": symbol}
    return {"symbol": symbol, "date": date,
            "ohlcv": {"open": price, "high": "N/A (live)", "low": "N/A (live)",
                      "close": "N/A (live)", "volume": "N/A (live)"}}


@mcp.tool()
def get_price_history(symbol: str) -> Dict[str, Any]:
    """Get market momentum data: the last 7 days (Open/Close) and today's recent hourly intraday action."""
    try:
        from datetime import datetime
        client = get_alpaca_client()
        
        # 1. Get last 7 daily bars
        daily_bars = client.get_bars(symbol, timeframe="1Day", limit=7)
        last_7_days = [{"date": b["timestamp"].split(" ")[0], "open": b["open"], "close": b["close"]} for b in daily_bars]
        
        # 2. Get today's recent hourly bars
        hourly_bars = client.get_bars(symbol, timeframe="1Hour", limit=12)
        
        # Filter to only get the most recent trading day's hourly bars
        intraday_today = []
        if hourly_bars:
            latest_day = hourly_bars[-1]["timestamp"].split(" ")[0]
            intraday_today = [
                {"time": b["timestamp"], "open": b["open"], "close": b["close"], "high": b["high"], "low": b["low"]}
                for b in hourly_bars if b["timestamp"].startswith(latest_day)
            ]

        return {
            "symbol": symbol,
            "last_7_days_trend": last_7_days,
            "intraday_today_hourly": intraday_today
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}


if __name__ == "__main__":
    port = int(os.getenv("TRADE_HTTP_PORT", "8002"))
    mcp.run(transport="streamable-http", port=port)
