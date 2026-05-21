import os, sys, json
from typing import Dict, Any
from fastmcp import FastMCP

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tools.alpaca_client import get_alpaca_client

mcp = FastMCP("Alpaca")


# ── Trade Tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def buy(symbol: str, amount: int, take_profit: float, stop_loss: float) -> Dict[str, Any]:
    """Go Long: Buy shares via Alpaca. Args: symbol (e.g. 'AAPL'), amount (positive int), take_profit (REQUIRED limit price), stop_loss (REQUIRED stop price)."""
    if amount <= 0: return {"error": f"Amount must be positive, got {amount}"}
    if not take_profit or not stop_loss: return {"error": "Strict Mode: Both take_profit and stop_loss bounds MUST be provided."}
    try: return get_alpaca_client().buy(symbol, amount, take_profit=take_profit, stop_loss=stop_loss)
    except Exception as e: return {"error": str(e)}

@mcp.tool()
def close_position(symbol: str) -> Dict[str, Any]:
    """Emergency Eject: Completely liquidate a specific open stock position at market price. This automatically shreds the existing Take Profit and Stop Loss brackets before selling."""
    try: return get_alpaca_client().close_position(symbol)
    except Exception as e: return {"error": str(e)}

@mcp.tool()
def update_brackets(symbol: str, new_stop_loss: float = None, new_take_profit: float = None) -> Dict[str, Any]:
    """Trail Profits: Update stop-loss and/or take-profit on an existing position's bracket orders. Use this to LOCK IN GAINS by raising the stop-loss closer to the current price when a trade is significantly profitable. Example: bought at $100, stop was $97, price is now $110 → raise stop to $107 to guarantee +$7/share profit. You may also widen take-profit if momentum is extremely strong."""
    if not new_stop_loss and not new_take_profit:
        return {"error": "Must provide at least one of new_stop_loss or new_take_profit"}
    try: return get_alpaca_client().update_brackets(symbol, new_stop_loss=new_stop_loss, new_take_profit=new_take_profit)
    except Exception as e: return {"error": str(e)}

@mcp.tool()
def place_trailing_stop(symbol: str, stop_price: float) -> Dict[str, Any]:
    """Protect Profits: Place a new GTC (good-til-cancelled) stop-sell order on your ENTIRE position for a symbol. Use this when a position has large unrealized gains but NO active stop-loss orders protecting it. Unlike bracket stops, this order survives overnight and won't expire. This is the PRIMARY tool for locking in profits on existing winning positions."""
    try: return get_alpaca_client().place_trailing_stop(symbol, stop_price)
    except Exception as e: return {"error": str(e)}


# ── Price & Screener Tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def get_market_scanner() -> Dict[str, Any]:
    """Market Scanner: Returns price and daily % change for ALL 50 tracked tech and crypto proxy stocks, sorted by momentum. Use this to find stable stocks, diversified setups, or high momentum plays."""
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
    """Get market momentum data: the last 7 days of Daily bars, and the last 2 days of 15-Minute intraday bars (Open, High, Low, Close, Volume)."""
    try:
        client = get_alpaca_client()
        daily_bars = client.get_bars(symbol, timeframe="1Day", limit=7)
        last_7_days = [{"date": b["timestamp"].split(" ")[0], "open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"], "volume": b["volume"]} for b in daily_bars]
        
        intraday_bars = client.get_bars(symbol, timeframe="15Min", limit=40)
        recent_15m = [{"time": b["timestamp"], "open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"], "volume": b["volume"]} for b in intraday_bars]

        return {"symbol": symbol, "daily_trend_7_days": last_7_days, "intraday_15min_bars": recent_15m}
    except Exception as e:
        return {"error": str(e), "symbol": symbol}

@mcp.tool()
def get_technical_indicators(symbol: str) -> Dict[str, Any]:
    """Get powerful technical indicators for a stock based on the 1-Hour timeframe (RSI, MACD, and 20-EMA / 50-EMA). 
    Use this to identify if a stock is Overbought (RSI > 70), Oversold (RSI < 30), or crossing moving averages."""
    try:
        import pandas as pd
        from ta.momentum import RSIIndicator
        from ta.trend import MACD, EMAIndicator
        
        client = get_alpaca_client()
        bars = client.get_bars(symbol, timeframe="1Hour", limit=100)
        if not bars or len(bars) < 50:
            return {"error": "Not enough data to calculate indicators."}
            
        df = pd.DataFrame(bars)
        
        # Calculate RSI (14 period)
        rsi_indicator = RSIIndicator(close=df['close'], window=14)
        df['RSI'] = rsi_indicator.rsi()
        
        # Calculate MACD
        macd_indicator = MACD(close=df['close'])
        df['MACD'] = macd_indicator.macd()
        df['MACD_Signal'] = macd_indicator.macd_signal()
        
        # Calculate EMAs
        df['EMA_20'] = EMAIndicator(close=df['close'], window=20).ema_indicator()
        df['EMA_50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()
        
        latest = df.iloc[-1]
        
        return {
            "symbol": symbol,
            "timestamp": latest['timestamp'],
            "current_price": latest['close'],
            "RSI_14": round(latest['RSI'], 2),
            "MACD": round(latest['MACD'], 4),
            "MACD_Signal": round(latest['MACD_Signal'], 4),
            "EMA_20_Support": round(latest['EMA_20'], 2),
            "EMA_50_Support": round(latest['EMA_50'], 2),
            "Interpretation": {
                "RSI": "Oversold/Buy" if latest['RSI'] < 30 else "Overbought/Sell" if latest['RSI'] > 70 else "Neutral",
                "MACD": "Bullish Momentum" if latest['MACD'] > latest['MACD_Signal'] else "Bearish Momentum",
                "Trend": "Bullish (Above EMA 20)" if latest['close'] > latest['EMA_20'] else "Bearish (Below EMA 20)"
            }
        }
    except Exception as e:
        return {"error": f"Failed to calculate indicators: {str(e)}", "symbol": symbol}

if __name__ == "__main__":
    port = int(os.getenv("TRADE_HTTP_PORT", "8002"))
    mcp.run(transport="streamable-http", port=port)
