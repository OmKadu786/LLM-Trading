import os
import requests
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from tools.friction_engine import calculate_friction

load_dotenv()

_client: Optional["AlpacaClient"] = None

class AlpacaClient:
    def __init__(self):
        self.key = os.getenv("ALPACA_API_KEY")
        self.secret = os.getenv("ALPACA_API_SECRET")
        if not self.key or not self.secret:
            raise ValueError("ALPACA_API_KEY and ALPACA_API_SECRET must be set in .env")
        is_paper = os.getenv("ALPACA_LIVE", "false").lower() != "true"
        self.tc = TradingClient(api_key=self.key, secret_key=self.secret, paper=is_paper)
        self.dc = StockHistoricalDataClient(api_key=self.key, secret_key=self.secret)
        self.data_url = "https://data.alpaca.markets"
        print(f"✅ Alpaca ({'PAPER' if is_paper else '🔴 LIVE'} mode)")

    def _headers(self):
        return {"Apca-Api-Key-Id": self.key, "Apca-Api-Secret-Key": self.secret}

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
                "pnl_percent": float(p.unrealized_plpc) * 100,
                "side": p.side.value if hasattr(p, "side") else "long"
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
        # ── Friction Calculation ──────────────────────────────────────────────
        # Fetch live price to compute friction on actual position value
        raw_price = self.get_latest_price(symbol) or 0.0
        friction_side = "buy" if side == OrderSide.BUY else "sell"
        friction = calculate_friction(symbol, friction_side, qty, raw_price)
        f = friction.to_dict()

        print(f"\n💸 FRICTION [{symbol}] {friction_side.upper()} {qty} shares @ ${raw_price:.2f}")
        print(f"   Slippage:   ${f['friction_breakdown']['slippage_$']:.4f}")
        print(f"   Spread:     ${f['friction_breakdown']['spread_$']:.4f}")
        print(f"   Latency:    ${f['friction_breakdown']['latency_$']:.4f}")
        print(f"   SEC Fee:    ${f['friction_breakdown']['sec_fee_$']:.4f}")
        print(f"   FINRA TAF:  ${f['friction_breakdown']['finra_taf_$']:.4f}")
        print(f"   ─────────────────────────────────")
        print(f"   TOTAL DRAG: ${f['total_friction_$']:.4f} ({f['total_friction_%']:.4f}%) | Tier: {f['liquidity_tier']}")
        if f['partial_fill_risk_shares'] > 0:
            print(f"   ⚠️  Partial fill risk: {f['partial_fill_risk_shares']} shares may not fill in live trading")

        # ── Submit Order to Alpaca ────────────────────────────────────────────
        req_args = {"symbol": symbol, "qty": qty, "side": side, "time_in_force": TimeInForce.DAY}
        if take_profit:
            req_args["take_profit"] = TakeProfitRequest(limit_price=take_profit)
        if stop_loss:
            req_args["stop_loss"] = StopLossRequest(stop_price=stop_loss)

        order = self.tc.submit_order(MarketOrderRequest(**req_args))
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "qty": str(order.qty),
            "side": side.value,
            "status": str(order.status),
            "submitted_at": str(order.submitted_at),
            "friction": f,
        }

    def buy(self, symbol: str, qty: int, take_profit: Optional[float] = None, stop_loss: Optional[float] = None) -> Dict[str, Any]:
        return self._order(symbol, qty, OrderSide.BUY, take_profit, stop_loss)

    def sell(self, symbol: str, qty: int) -> Dict[str, Any]:
        return self._order(symbol, qty, OrderSide.SELL)

    def short_sell(self, symbol: str, qty: int, take_profit: Optional[float] = None, stop_loss: Optional[float] = None) -> Dict[str, Any]:
        # Shorting is just triggering a SELL without owning it. Bracket constraints apply in reverse.
        return self._order(symbol, qty, OrderSide.SELL, take_profit, stop_loss)

    def cover_short(self, symbol: str, qty: int) -> Dict[str, Any]:
        # Covering a short is just triggering a BUY.
        return self._order(symbol, qty, OrderSide.BUY)

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

    def get_market_movers(self) -> Dict[str, Any]:
        # Use popular high volatility tech identifiers as a focused screener
        symbols = "AAPL,MSFT,NVDA,TSLA,AMD,AMZN,META,GOOG,NFLX,COIN,MSTR,PLTR,SMCI,ARM,AVGO"
        url = f"{self.data_url}/v2/stocks/snapshots?symbols={symbols}"
        resp = requests.get(url, headers=self._headers())
        if resp.status_code != 200:
            return {"error": resp.text}
        
        data = resp.json()
        stats = []
        for sym, d in data.items():
            if "dailyBar" in d and "prevDailyBar" in d:
                c = float(d["dailyBar"]["c"])
                pc = float(d["prevDailyBar"]["c"])
                perc = ((c / pc) - 1.0) * 100.0 if pc > 0 else 0
                stats.append({"symbol": sym, "change_percent": perc, "price": c})
        
        stats.sort(key=lambda x: x["change_percent"], reverse=True)
        return {"top_gainers": stats[:5], "top_losers": stats[-5:]}

    def get_news(self, symbol: str, limit: int = 5) -> List[Dict[str, Any]]:
        url = f"{self.data_url}/v1beta1/news?symbols={symbol}&limit={limit}"
        resp = requests.get(url, headers=self._headers())
        if resp.status_code != 200:
            return [{"error": resp.text}]
        data = resp.json()
        return [{"headline": n["headline"], "summary": n["summary"], "created_at": n["created_at"]} for n in data.get("news", [])]

def get_alpaca_client() -> AlpacaClient:
    global _client
    if _client is None:
        _client = AlpacaClient()
    return _client
