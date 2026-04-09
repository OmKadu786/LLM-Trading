import os
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

load_dotenv()

_client: Optional["AlpacaClient"] = None


class AlpacaClient:
    def __init__(self):
        key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_API_SECRET")
        if not key or not secret:
            raise ValueError("ALPACA_API_KEY and ALPACA_API_SECRET must be set in .env")
        is_paper = os.getenv("ALPACA_LIVE", "false").lower() != "true"
        self.tc = TradingClient(api_key=key, secret_key=secret, paper=is_paper)
        self.dc = StockHistoricalDataClient(api_key=key, secret_key=secret)
        print(f"✅ Alpaca ({'PAPER' if is_paper else '🔴 LIVE'} mode)")

    def get_account(self) -> Dict[str, Any]:
        a = self.tc.get_account()
        return {
            "cash": float(a.cash), 
            "equity": float(a.equity),
            "buying_power": float(a.buying_power), 
            "portfolio_value": float(a.portfolio_value),
            "daily_pnl": float(a.equity) - float(a.last_equity),
            "daily_pnl_percent": ((float(a.equity) / float(a.last_equity)) - 1) * 100 if float(a.last_equity) > 0 else 0
        }

    def get_positions(self) -> Dict[str, Any]:
        return {
            p.symbol: {
                "qty": float(p.qty),
                "entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "unrealized_pnl": float(p.unrealized_pl),
                "pnl_percent": float(p.unrealized_plpc) * 100
            } for p in self.tc.get_all_positions()
        }

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            p = self.tc.get_open_position(symbol)
            return {"symbol": p.symbol, "qty": int(p.qty), "avg_entry_price": float(p.avg_entry_price),
                    "current_price": float(p.current_price), "unrealized_pl": float(p.unrealized_pl)}
        except Exception:
            return None

    def _order(self, symbol: str, qty: int, side: OrderSide, take_profit: Optional[float] = None, stop_loss: Optional[float] = None) -> Dict[str, Any]:
        req_args = {"symbol": symbol, "qty": qty, "side": side, "time_in_force": TimeInForce.DAY}
        if take_profit:
            req_args["take_profit"] = TakeProfitRequest(limit_price=take_profit)
        if stop_loss:
            req_args["stop_loss"] = StopLossRequest(stop_price=stop_loss)
            
        order = self.tc.submit_order(MarketOrderRequest(**req_args))
        return {"id": str(order.id), "symbol": order.symbol, "qty": str(order.qty),
                "side": side.value, "status": str(order.status), "submitted_at": str(order.submitted_at)}

    def buy(self, symbol: str, qty: int, take_profit: Optional[float] = None, stop_loss: Optional[float] = None) -> Dict[str, Any]:
        return self._order(symbol, qty, OrderSide.BUY, take_profit, stop_loss)

    def sell(self, symbol: str, qty: int) -> Dict[str, Any]:
        return self._order(symbol, qty, OrderSide.SELL)

    def get_latest_price(self, symbol: str) -> Optional[float]:
        try:
            q = self.dc.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]
            return float(q.ask_price or q.bid_price)
        except Exception as e:
            print(f"⚠️ Price fetch failed for {symbol}: {e}")
            return None

    def get_bars(self, symbol: str, timeframe: str = "1Hour", limit: int = 20) -> List[Dict]:
        tf = {"1Min": TimeFrame.Minute, "1Hour": TimeFrame.Hour, "1Day": TimeFrame.Day}.get(timeframe, TimeFrame.Hour)
        bars = self.dc.get_stock_bars(StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, limit=limit))
        return [{"timestamp": str(b.timestamp), "open": float(b.open), "high": float(b.high),
                 "low": float(b.low), "close": float(b.close), "volume": int(b.volume)} for b in bars[symbol]]


def get_alpaca_client() -> AlpacaClient:
    global _client
    if _client is None:
        _client = AlpacaClient()
    return _client
