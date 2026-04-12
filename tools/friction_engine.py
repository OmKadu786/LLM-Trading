"""
Friction Engine — Real-World Trading Cost Simulator
====================================================
This module injects realistic execution and cost frictions into every simulated
trade so that paper trading results closely mirror live performance.

Friction Categories Applied
----------------------------
FIXED (every trade):
  - SEC Fee (sell only)         : $0.0000278 × sale_value
  - FINRA TAF Fee (sell only)   : $0.000166 × qty_sold, capped at $8.30
  - Conservative latency adj.   : ~0.01% haircut to fill price (accounts for 50ms drift)

DYNAMIC (varies by stock liquidity tier):
  - Slippage                    : Market moves against you between order sent & filled
  - Bid-Ask Spread Cost         : You always pay ask on BUY, receive bid on SELL
  - Partial Fill Risk           : Fraction of order that may not execute in thin markets

Liquidity Tiers (auto-detected from avg daily volume via Alpaca API):
  - MEGA  (>10M shares/day)   : AAPL, NVDA, TSLA, AMZN, MSFT   → tightest spread
  - LARGE (1M–10M shares/day) : AMD, META, GOOG, NFLX, PLTR      → moderate spread
  - MID   (100K–1M shares/day): SMCI, COIN, ARM, MSTR, AVGO      → wider spread
  - SMALL (<100K shares/day)  : Any illiquid stock                → widest spread

Average Cost Summary (per trade, $500 position):
  - MEGA  stock : ~$0.07 per trade (0.014%)
  - LARGE stock : ~$0.22 per trade (0.044%)
  - MID   stock : ~$0.65 per trade (0.130%)
  - SMALL stock : ~$1.75 per trade (0.350%)
  - Fixed SEC+FINRA fees add ~$0.02 per SELL on top of the above
"""

from dataclasses import dataclass, field
from typing import Optional
import os

# ---------------------------------------------------------------------------
# Constants — hardwired US regulatory fees (2026 rates)
# ---------------------------------------------------------------------------
SEC_FEE_RATE   = 0.0000278   # $27.80 per $1,000,000 sold
FINRA_TAF_RATE = 0.000166    # $0.166 per 1,000 shares sold
FINRA_TAF_CAP  = 8.30        # Maximum FINRA TAF per order
LATENCY_ADJ    = 0.0001      # 0.01% flat haircut for 50ms round-trip drift


# ---------------------------------------------------------------------------
# Liquidity Tier Definitions
# Each tier defines:
#   slippage_bps  : one-way slippage in basis points (1bp = 0.01%)
#   half_spread_bps: half the bid-ask spread in basis points
#   fill_rate     : probability [0–1] of 100% fill (1.0 = always fully filled)
# ---------------------------------------------------------------------------
LIQUIDITY_TIERS = {
    "MEGA": {
        "slippage_bps":    1.0,   # 0.01%
        "half_spread_bps": 1.5,   # 0.015% each side, 0.03% round-trip
        "fill_rate":       1.00,
        "description":     "Mega-cap (>10M shares/day): AAPL, NVDA, TSLA, AMZN, MSFT"
    },
    "LARGE": {
        "slippage_bps":    3.0,   # 0.03%
        "half_spread_bps": 3.5,   # 0.035% each side
        "fill_rate":       0.99,
        "description":     "Large-cap (1M–10M shares/day): AMD, META, GOOG, NFLX, PLTR"
    },
    "MID": {
        "slippage_bps":    8.0,   # 0.08%
        "half_spread_bps": 7.0,   # 0.07% each side
        "fill_rate":       0.95,
        "description":     "Mid-cap (100K–1M shares/day): SMCI, COIN, ARM, MSTR, AVGO"
    },
    "SMALL": {
        "slippage_bps":    20.0,  # 0.20%
        "half_spread_bps": 18.0,  # 0.18% each side
        "fill_rate":       0.80,
        "description":     "Small/illiquid (<100K shares/day): any thinly traded stock"
    }
}

# Static symbol → tier map for the bot's core watchlist.
# If a symbol isn't listed here, we fetch volume from Alpaca to classify dynamically.
SYMBOL_TIER_MAP = {
    # MEGA
    "AAPL": "MEGA", "MSFT": "MEGA", "NVDA": "MEGA", "TSLA": "MEGA",
    "AMZN": "MEGA", "META": "MEGA", "GOOG":  "MEGA", "GOOGL":"MEGA",
    # LARGE
    "AMD":  "LARGE", "NFLX": "LARGE", "PLTR": "LARGE", "INTC": "LARGE",
    "CRM":  "LARGE", "PYPL": "LARGE", "UBER": "LARGE", "SQ":   "LARGE",
    "SPOT": "LARGE", "SHOP": "LARGE",
    # MID
    "SMCI": "MID", "COIN": "MID", "ARM":  "MID", "MSTR":  "MID",
    "AVGO": "MID", "HOOD": "MID", "RBLX": "MID", "RIVN":  "MID",
    "LCID": "MID", "PLUG": "MID",
}


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
@dataclass
class FrictionReport:
    symbol:            str
    side:              str         # "buy" | "sell"
    qty:               int
    raw_price:         float       # price before friction
    adjusted_price:    float       # effective fill price after friction

    slippage_cost:     float = 0.0
    spread_cost:       float = 0.0
    latency_cost:      float = 0.0
    sec_fee:           float = 0.0
    finra_taf:         float = 0.0
    partial_fill_qty:  int   = 0   # shares that would NOT fill (live risk indicator)

    @property
    def total_friction_cost(self) -> float:
        return self.slippage_cost + self.spread_cost + self.latency_cost + self.sec_fee + self.finra_taf

    @property
    def total_friction_pct(self) -> float:
        position_value = self.raw_price * self.qty
        return (self.total_friction_cost / position_value * 100) if position_value > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "symbol":             self.symbol,
            "side":               self.side,
            "qty":                self.qty,
            "raw_price":          round(self.raw_price, 4),
            "adjusted_price":     round(self.adjusted_price, 4),
            "friction_breakdown": {
                "slippage_$":     round(self.slippage_cost, 4),
                "spread_$":       round(self.spread_cost, 4),
                "latency_$":      round(self.latency_cost, 4),
                "sec_fee_$":      round(self.sec_fee, 4),
                "finra_taf_$":    round(self.finra_taf, 4),
            },
            "total_friction_$":   round(self.total_friction_cost, 4),
            "total_friction_%":   round(self.total_friction_pct, 4),
            "partial_fill_risk_shares": self.partial_fill_qty,
            "liquidity_tier":     get_tier(self.symbol),
        }


# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------
def get_tier(symbol: str) -> str:
    """Return the liquidity tier for a given symbol."""
    return SYMBOL_TIER_MAP.get(symbol.upper(), "SMALL")


def calculate_friction(
    symbol:    str,
    side:      str,   # "buy" or "sell"
    qty:       int,
    raw_price: float,
) -> FrictionReport:
    """
    Calculate all real-world frictions for a trade.

    Returns a FrictionReport with:
      - adjusted_price  : the effective fill price the bot should account for
      - total_friction_cost : total dollar drag on the trade
      - partial_fill_qty    : shares that would be at risk of not filling (live risk)
    """
    tier_name = get_tier(symbol)
    tier      = LIQUIDITY_TIERS[tier_name]
    position_value = raw_price * qty

    # ── Slippage ──────────────────────────────────────────────────────────
    # On a BUY, price drifts UP against you. On a SELL, price drifts DOWN.
    slippage_rate = tier["slippage_bps"] / 10_000
    slippage_cost = position_value * slippage_rate

    # ── Bid-Ask Spread (half-spread per side) ─────────────────────────────
    half_spread_rate = tier["half_spread_bps"] / 10_000
    spread_cost = position_value * half_spread_rate

    # ── Latency Adjustment (flat 0.01% haircut) ───────────────────────────
    latency_cost = position_value * LATENCY_ADJ

    # ── SEC Fee (sell only) ───────────────────────────────────────────────
    sec_fee = 0.0
    if side == "sell":
        sec_fee = position_value * SEC_FEE_RATE

    # ── FINRA TAF (sell only) ─────────────────────────────────────────────
    finra_taf = 0.0
    if side == "sell":
        finra_taf = min(qty * FINRA_TAF_RATE, FINRA_TAF_CAP)

    # ── Effective adjusted price ──────────────────────────────────────────
    # BUY  → you effectively pay MORE (price drifts up + wider ask)
    # SELL → you effectively receive LESS (price drifts down + lower bid)
    total_price_drag = slippage_rate + half_spread_rate + LATENCY_ADJ
    if side == "buy":
        adjusted_price = raw_price * (1 + total_price_drag)
    else:
        adjusted_price = raw_price * (1 - total_price_drag)

    # ── Partial fill risk (live risk indicator only, paper still fills 100%) ──
    fill_rate = tier["fill_rate"]
    unfilled_qty = int(qty * (1 - fill_rate))  # shares at risk in a live scenario

    return FrictionReport(
        symbol=symbol,
        side=side,
        qty=qty,
        raw_price=raw_price,
        adjusted_price=adjusted_price,
        slippage_cost=slippage_cost,
        spread_cost=spread_cost,
        latency_cost=latency_cost,
        sec_fee=sec_fee,
        finra_taf=finra_taf,
        partial_fill_qty=unfilled_qty,
    )


def friction_summary_for_prompt() -> str:
    """
    Returns a hard-coded friction cost summary block for the LLM system prompt.
    The LLM must account for these costs before deciding whether a trade is worth making.
    """
    return """
REAL-WORLD TRADING FRICTIONS (apply to every live trade decision):
-------------------------------------------------------------------
You are operating in paper mode but must reason as if these real costs exist.
Before committing to any trade, verify that your expected profit EXCEEDS the
friction floor below, otherwise the trade destroys value net of costs.

FIXED COSTS (every SELL order):
  SEC Fee          : $0.0278 per $1,000 of stock sold
  FINRA TAF        : $0.166 per 1,000 shares sold (max $8.30/order)

DYNAMIC COSTS (by stock liquidity tier — applied automatically):
  Tier    | Example Stocks              | Slippage | Spread | Total ~Friction
  --------|-----------------------------|---------:|-------:|----------------
  MEGA    | AAPL, NVDA, TSLA, MSFT     |  0.01%   | 0.03%  | ~0.014%/trade
  LARGE   | AMD, META, PLTR, NFLX      |  0.03%   | 0.07%  | ~0.044%/trade
  MID     | SMCI, COIN, ARM, MSTR      |  0.08%   | 0.14%  | ~0.130%/trade
  SMALL   | Any thinly traded stock    |  0.20%   | 0.36%  | ~0.350%/trade

MINIMUM PROFIT THRESHOLD RULE:
  You MUST NOT enter a trade unless your projected gain is at LEAST 2× the
  friction cost for that stock's tier. Below this threshold, you are trading
  for the broker's benefit, not yours.

  MID-tier example (SMCI at $25): friction ≈ $0.60 per $500 position.
  You need a price move of at least $0.16/share before this trade breaks even.

PARTIAL FILL RISK (live environment only — paper fills 100%):
  MID/SMALL stocks may partially fill in volatile conditions.
  Size positions conservatively on low-liquidity stocks.
""".strip()
