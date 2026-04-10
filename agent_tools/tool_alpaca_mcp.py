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
    """Go Long: Buy shares via Alpaca. Args: symbol (e.g. 'AAPL'), amount (positive int), take_profit (optional limit price), stop_loss (optional stop price)."""
    if amount <= 0: return {"error": f"Amount must be positive, got {amount}"}
    try: return get_alpaca_client().buy(symbol, amount, take_profit=take_profit, stop_loss=stop_loss)
    except Exception as e: return {"error": str(e)}

@mcp.tool()
def sell(symbol: str, amount: int) -> Dict[str, Any]:
    """Sell/Close Long position shares. Amount must be positive int."""
    if amount <= 0: return {"error": f"Amount must be positive, got {amount}"}
    try: return get_alpaca_client().sell(symbol, amount)
    except Exception as e: return {"error": str(e)}

@mcp.tool()
def short_sell(symbol: str, amount: int, take_profit: float = None, stop_loss: float = None) -> Dict[str, Any]:
    """Go Short: Bet against a stock. Args: symbol, amount, take_profit (floor price), stop_loss (ceiling price)."""
    if amount <= 0: return {"error": f"Amount must be positive, got {amount}"}
    try: return get_alpaca_client().short_sell(symbol, amount, take_profit=take_profit, stop_loss=stop_loss)
    except Exception as e: return {"error": str(e)}

@mcp.tool()
def cover_short(symbol: str, amount: int) -> Dict[str, Any]:
    """Cover Short: Buy back shares to close a previously opened short position."""
    if amount <= 0: return {"error": f"Amount must be positive, got {amount}"}
    try: return get_alpaca_client().cover_short(symbol, amount)
    except Exception as e: return {"error": str(e)}

# ── Price & Screener Tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def get_top_movers() -> Dict[str, Any]:
    """Market Scanner: Returns today's top gainers and top losers among major tech and crypto-proxies to identify heavy momentum."""
    try: return get_alpaca_client().get_market_movers()
    except Exception as e: return {"error": str(e)}

@mcp.tool()
def get_asset_news(symbol: str) -> Dict[str, Any]:
    """Get the latest real-time, broker-native financial news headlines strictly related to the provided stock symbol."""
    try: return {"news": get_alpaca_client().get_news(symbol)}
    except Exception as e: return {"error": str(e)}

@mcp.tool()
def get_price_live(symbol: str, date: str) -> Dict[str, Any]:
    """Get live Alpaca quote for a symbol. Returns exact ask price."""
    price = get_alpaca_client().get_latest_price(symbol)
    if price is None:
        return {"error": f"Could not get price for {symbol}", "symbol": symbol}
    return {"symbol": symbol, "date": date, "live_ask_price": price}

@mcp.tool()
def get_price_history(symbol: str) -> Dict[str, Any]:
    """Get market momentum data: the last 7 days (Open/Close) and today's recent hourly intraday action."""
    try:
        from datetime import datetime
        client = get_alpaca_client()
        daily_bars = client.get_bars(symbol, timeframe="1Day", limit=7)
        last_7_days = [{"date": b["timestamp"].split(" ")[0], "open": b["open"], "close": b["close"]} for b in daily_bars]
        
        hourly_bars = client.get_bars(symbol, timeframe="1Hour", limit=12)
        intraday_today = []
        if hourly_bars:
            latest_day = hourly_bars[-1]["timestamp"].split(" ")[0]
            intraday_today = [{"time": b["timestamp"], "open": b["open"], "close": b["close"], "high": b["high"], "low": b["low"]}
                              for b in hourly_bars if b["timestamp"].startswith(latest_day)]

        return {"symbol": symbol, "last_7_days_trend": last_7_days, "intraday_today_hourly": intraday_today}
    except Exception as e:
        return {"error": str(e), "symbol": symbol}

if __name__ == "__main__":
    port = int(os.getenv("TRADE_HTTP_PORT", "8002"))
    mcp.run(transport="streamable-http", port=port)
