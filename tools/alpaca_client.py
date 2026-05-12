import os
import requests
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, StopOrderRequest, LimitOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
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
        if take_profit and stop_loss:
            req_args["order_class"] = OrderClass.BRACKET
            req_args["take_profit"] = TakeProfitRequest(limit_price=take_profit)
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

    def close_position(self, symbol: str) -> Dict[str, Any]:
        """Emergency Eject: Cancels all open brackets and liquidates the full position."""
        try:
            # ── Friction Logging ──────────────────────────────────────────────
            pos = self.get_position(symbol)
            qty = pos["qty"] if pos else 0
            if qty > 0:
                raw_price = self.get_latest_price(symbol) or 0.0
                f = calculate_friction(symbol, "sell", qty, raw_price).to_dict()
                print(f"\n💸 FRICTION (FORCE CLOSE) [{symbol}] SELL {qty} shares @ ${raw_price:.2f}")
                print(f"   TOTAL DRAG: ${f['total_friction_$']:.4f} ({f['total_friction_%']:.4f}%)")
            
            # ── Execute Force Close ───────────────────────────────────────────
            req = self.tc.close_position(symbol_or_asset_id=symbol)
            return {"status": "success", "message": f"Successfully cancelled open brackets and liquidated full {symbol} position.", "order_details": str(req)}
        except Exception as e:
            return {"error": str(e)}

    def update_brackets(self, symbol: str, new_stop_loss: Optional[float] = None, new_take_profit: Optional[float] = None) -> Dict[str, Any]:
        """Update stop-loss and/or take-profit on existing bracket orders for a position."""
        base = os.getenv("ALPACA_API_BASE_URL", "https://paper-api.alpaca.markets/v2")
        headers = {"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret}

        # Get open orders for this symbol
        resp = requests.get(f"{base}/orders", headers=headers, params={"status": "open", "symbols": symbol})
        if resp.status_code != 200:
            return {"error": f"Failed to fetch orders: {resp.text}"}

        orders = resp.json()
        results = {"symbol": symbol, "updates": []}

        for order in orders:
            order_type = order.get("type", "")
            order_side = order.get("side", "")

            # Stop-loss leg: type=stop, side=sell
            if order_type == "stop" and order_side == "sell" and new_stop_loss is not None:
                old_price = order.get("stop_price")
                patch = requests.patch(
                    f"{base}/orders/{order['id']}", headers=headers,
                    json={"stop_price": str(new_stop_loss)}
                )
                if patch.status_code == 200:
                    results["updates"].append({"type": "stop_loss", "old": old_price, "new": new_stop_loss, "status": "updated"})
                    print(f"🔒 TRAIL [{symbol}] Stop-loss: ${old_price} → ${new_stop_loss}")
                else:
                    results["updates"].append({"type": "stop_loss", "error": patch.text})

            # Take-profit leg: type=limit, side=sell
            elif order_type == "limit" and order_side == "sell" and new_take_profit is not None:
                old_price = order.get("limit_price")
                patch = requests.patch(
                    f"{base}/orders/{order['id']}", headers=headers,
                    json={"limit_price": str(new_take_profit)}
                )
                if patch.status_code == 200:
                    results["updates"].append({"type": "take_profit", "old": old_price, "new": new_take_profit, "status": "updated"})
                    print(f"🎯 TRAIL [{symbol}] Take-profit: ${old_price} → ${new_take_profit}")
                else:
                    results["updates"].append({"type": "take_profit", "error": patch.text})

        if not results["updates"]:
            return {"error": f"No open bracket orders found for {symbol}. Consider using close_position and re-entering with new brackets."}

        return results

    def place_trailing_stop(self, symbol: str, stop_price: float, qty: Optional[int] = None) -> Dict[str, Any]:
        """Place a standalone stop-sell order on an existing position to lock in profits."""
        try:
            # If no qty given, protect the entire position
            if qty is None:
                pos = self.get_position(symbol)
                if not pos:
                    return {"error": f"No open position found for {symbol}"}
                qty = pos["qty"]

            raw_price = self.get_latest_price(symbol) or 0.0
            if stop_price >= raw_price:
                return {"error": f"Stop price ${stop_price} must be below current price ${raw_price}"}

            order = self.tc.submit_order(
                StopOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC,  # Good-til-cancelled — survives overnight!
                    stop_price=stop_price,
                )
            )
            print(f"\n🔒 TRAILING STOP [{symbol}] {qty} shares @ ${stop_price} (current: ${raw_price:.2f})")
            return {
                "status": "success",
                "symbol": symbol,
                "qty": qty,
                "stop_price": stop_price,
                "current_price": raw_price,
                "protected_profit_per_share": round(stop_price - (self.get_position(symbol) or {}).get("avg_entry_price", 0), 2),
                "order_id": str(order.id),
            }
        except Exception as e:
            return {"error": str(e)}

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
        # Top 50 major US Equities by Market Cap / Volatility (Core S&P 500 + Crypto Proxies)
        # Strictly Top 12 Mega-Cap universe (Magnificent 7 + top leaders). 
        # Volatile proxies (MSTR, SMCI, COIN, PLTR, ARM) are BANNED to eliminate spread friction.
        symbols = "AAPL,MSFT,NVDA,AMZN,META,GOOG,GOOGL,TSLA,LLY,AVGO,JPM,V"
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
        return {"all_tracked_stocks": stats}

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
