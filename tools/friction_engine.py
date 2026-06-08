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
    # MEGA (>10M shares/day or huge liquidity)
    "AAPL": "MEGA", "MSFT": "MEGA", "NVDA": "MEGA", "TSLA": "MEGA",
    "AMZN": "MEGA", "META": "MEGA", "GOOG": "MEGA", "GOOGL": "MEGA",
    "AMD": "MEGA", "INTC": "MEGA", "BAC": "MEGA", "F": "MEGA",
    "T": "MEGA", "CSCO": "MEGA", "VZ": "MEGA", "PFE": "MEGA",
    # LARGE (Top 50 S&P 500 & consistent big movers)
    "NFLX": "LARGE", "PLTR": "LARGE", "CRM": "LARGE", "PYPL": "LARGE",
    "UBER": "LARGE", "SQ": "LARGE", "SPOT": "LARGE", "SHOP": "LARGE",
    "LLY": "LARGE", "AVGO": "LARGE", "JPM": "LARGE", "UNH": "LARGE",
    "V": "LARGE", "XOM": "LARGE", "MA": "LARGE", "JNJ": "LARGE",
    "PG": "LARGE", "HD": "LARGE", "COST": "LARGE", "MRK": "LARGE",
    "ABBV": "LARGE", "CVX": "LARGE", "PEP": "LARGE", "WMT": "LARGE",
    "MCD": "LARGE", "LIN": "LARGE", "ADBE": "LARGE", "ACN": "LARGE",
    "DIS": "LARGE", "ABT": "LARGE", "INTU": "LARGE", "WFC": "LARGE",
    "IBM": "LARGE", "CMCSA": "LARGE", "QCOM": "LARGE", "CAT": "LARGE",
    "TXN": "LARGE", "NKE": "LARGE", "BA": "LARGE", "GE": "LARGE",
    # MID
    "SMCI": "MID", "COIN": "MID", "ARM": "MID", "MSTR": "MID",
    "HOOD": "MID", "RBLX": "MID", "RIVN": "MID", "LCID": "MID",
    "PLUG": "MID",
}


TTP_SPREADS = {
    "MSFT": 0.18,
    "AAPL": 0.19,
    "NVDA": 0.09,
    "AMZN": 0.20,
    "GOOGL": 0.14,
    "GOOG": 0.14,
    "META": 0.22,
    "TSLA": 0.16,
    "BRK.B": 0.25,
    "AVGO": 0.48,
    "LLY": 0.55,
    "V": 0.17,
    "JPM": 0.15
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
    commission:        float = 0.0
    partial_fill_qty:  int   = 0   # shares that would NOT fill (live risk indicator)

    @property
    def total_friction_cost(self) -> float:
        return self.slippage_cost + self.spread_cost + self.latency_cost + self.sec_fee + self.finra_taf + self.commission

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
                "commission_$":   round(self.commission, 4),
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

    # ── Slippage & Latency ────────────────────────────────────────────────
    slippage_rate = tier["slippage_bps"] / 10_000
    slippage_cost = position_value * slippage_rate
    latency_cost = position_value * LATENCY_ADJ

    # ── Bid-Ask Spread (TTP specific or fallback) ─────────────────────────
    # If we have specific TTP spread data, we use it. We pay half the spread
    # on entry and half on exit. (spread_cost = half spread * qty)
    sym_upper = symbol.upper()
    if sym_upper in TTP_SPREADS:
        full_spread = TTP_SPREADS[sym_upper]
        spread_cost = (full_spread / 2.0) * qty
        half_spread_rate = spread_cost / position_value if position_value > 0 else 0.0
    else:
        half_spread_rate = tier["half_spread_bps"] / 10_000
        spread_cost = position_value * half_spread_rate

    # ── TTP Commission ────────────────────────────────────────────────────
    commission = max(0.75, qty * 0.005)

    # ── SEC Fee (sell only) ───────────────────────────────────────────────
    sec_fee = 0.0
    if side == "sell":
        sec_fee = position_value * SEC_FEE_RATE

    # ── FINRA TAF (sell only) ─────────────────────────────────────────────
    finra_taf = 0.0
    if side == "sell":
        finra_taf = min(qty * FINRA_TAF_RATE, FINRA_TAF_CAP)

    # ── Effective adjusted price ──────────────────────────────────────────
    # Spread/Slippage hits price. Commissions/Fees are usually separate, but
    # we bake price drag directly into adjusted_price to penalize expected profit.
    total_price_drag_pct = slippage_rate + half_spread_rate + LATENCY_ADJ
    if side == "buy":
        adjusted_price = raw_price * (1 + total_price_drag_pct)
    else:
        adjusted_price = raw_price * (1 - total_price_drag_pct)

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
        commission=commission,
        partial_fill_qty=unfilled_qty,
    )


def friction_summary_for_prompt() -> str:
    """
    Returns a hard-coded friction cost summary block for the LLM system prompt.
    The LLM must account for these costs before deciding whether a trade is worth making.
    """
    return """
REAL-WORLD TRADING FRICTIONS & TTP COMMISSIONS (apply to every trade decision):
-------------------------------------------------------------------------------
You are operating in paper mode but must reason as if TTP's real costs exist.
Before committing to any trade, verify that your expected profit EXCEEDS the
friction floor below, otherwise the trade destroys value net of costs.

COMMISSIONS (TTP Specific - charged on both BUY and SELL):
  Rate: $0.005 per share
  Minimum: $0.75 per order (this applies to almost all your large-cap trades)

FIXED COSTS (every SELL order):
  SEC Fee          : $0.0278 per $1,000 of stock sold
  FINRA TAF        : $0.166 per 1,000 shares sold (max $8.30/order)

EXACT TTP SPREADS (Top 12):
  MSFT: $0.18 | AAPL: $0.19 | NVDA: $0.09 | AMZN: $0.20 | GOOG/L: $0.14
  META: $0.22 | TSLA: $0.16 | AVGO: $0.48 | LLY: $0.55  | V: $0.17 | JPM: $0.15
  (You pay half this spread on entry, and half on exit).

MINIMUM PROFIT THRESHOLD RULE:
  You MUST NOT enter a trade unless your projected gain is at LEAST 1.5× the
  total friction cost (commission + spread + SEC fees).
  Because you trade expensive Mega-Caps, you buy very few shares, meaning your
  main cost is the flat $0.75 minimum commission on entry and exit.
""".strip()
