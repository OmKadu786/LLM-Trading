import os, sys, requests, json
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../.env'))

KEY = os.getenv("ALPACA_API_KEY")
SECRET = os.getenv("ALPACA_API_SECRET")
HEADERS = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET}
BASE = "https://paper-api.alpaca.markets/v2"

# 1. Fetch 1D history
r_daily = requests.get(f"{BASE}/account/portfolio/history", headers=HEADERS, params={"period": "1M", "timeframe": "1D"})
daily_baseline_data = r_daily.json()

official_baselines = {}
for ts, eq in zip(daily_baseline_data.get("timestamp", []), daily_baseline_data.get("equity", [])):
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    date_str = dt.astimezone().strftime("%Y-%m-%d")
    official_baselines[date_str] = eq

# 2. Fetch 5Min history
end_dt = datetime.now()
start_dt = end_dt - timedelta(days=29)

params = {
    "timeframe": "5Min",
    "date_start": start_dt.strftime("%Y-%m-%d"),
    "date_end": end_dt.strftime("%Y-%m-%d"),
    "extended_hours": "true"
}

r = requests.get(f"{BASE}/account/portfolio/history", headers=HEADERS, params=params)
data = r.json()

daily_data = defaultdict(lambda: {"equity": []})
for ts, eq in zip(data["timestamp"], data["equity"]):
    if eq <= 20000: continue # SKIP THE GARBAGE DAYS
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    date_str = dt.astimezone().strftime("%Y-%m-%d")
    daily_data[date_str]["equity"].append(eq)

dates = sorted(list(daily_data.keys()))

sim_eq = 30000.0
held_cash_overnight = False

print(f"{'Date':<12} | {'Gap %':<7} | {'Target%':<7} | {'Hit?':<5} | {'Sim P&L ($)':<12} | {'Sim (%)':<8} | {'Friction':<10}")
print("-" * 80)

for i, date_str in enumerate(dates):
    raw_eq_array = daily_data[date_str]["equity"]
    
    # Actuals (Leveraged)
    if i == 0:
        actual_prev_eq = 30000.0
    else:
        actual_prev_eq = official_baselines.get(dates[i-1], raw_eq_array[0])
        if actual_prev_eq < 20000: actual_prev_eq = 30000.0
        
    raw_open_eq = raw_eq_array[0]
    
    # Create unleveraged equity array by dividing percentage moves by 3.1
    eq_array = []
    for eq in raw_eq_array:
        move_pct = (eq / raw_open_eq) - 1
        unlev_move_pct = move_pct / 3.1
        eq_array.append(raw_open_eq * (1 + unlev_move_pct))
        
    # Unleveraged actual gap
    raw_gap_pct = (raw_open_eq / actual_prev_eq) - 1 if actual_prev_eq > 0 else 0
    actual_gap_pct = raw_gap_pct / 3.1
    
    actual_open_eq = eq_array[0]
    actual_close_eq = eq_array[-1]
    actual_prev_unlev = actual_open_eq / (1 + actual_gap_pct)
    
    actual_day_pnl_val = actual_close_eq - actual_prev_unlev
    actual_day_pnl_pct = (actual_day_pnl_val / actual_prev_unlev) * 100
    
    daily_friction_cost = 0.0
    
    # Simulation Start
    if held_cash_overnight:
        sim_open_eq = sim_eq # No gap because we held cash!
        # Re-entry friction: 1x leverage * 0.1% spread = 0.1% of equity
        re_entry_friction = sim_open_eq * 0.001
        sim_open_eq -= re_entry_friction
        daily_friction_cost += re_entry_friction
        sim_gap_pct = 0.0
    else:
        sim_open_eq = sim_eq * (1 + actual_gap_pct)
        sim_gap_pct = actual_gap_pct * 100
        
    # Target calculate using exact requested formula (scaled down for 1x leverage)
    target_pct = 1.0
    if sim_open_eq < sim_eq:
        gap_down_pct = ((sim_eq - sim_open_eq) / sim_eq) * 100
        target_pct = 1.0 - gap_down_pct
        
    liquidated = False
    sim_close_eq = sim_open_eq * (actual_close_eq / actual_open_eq)
    
    for bar_eq in eq_array:
        bar_intraday_pct = bar_eq / actual_open_eq
        sim_bar_eq = sim_open_eq * bar_intraday_pct
        
        sim_current_pnl_pct = ((sim_bar_eq / sim_eq) - 1) * 100
        
        if sim_current_pnl_pct >= target_pct:
            # Simulate a live monitor hitting the target exactly
            sim_close_eq = sim_eq * (1 + (target_pct / 100))
            
            # Liquidation friction: 1x leverage * 0.1% spread = 0.1% of equity
            liq_friction = sim_close_eq * 0.001
            sim_close_eq -= liq_friction
            daily_friction_cost += liq_friction
            
            liquidated = True
            break
            
    # Calculate daily Sim PnL (including frictions)
    sim_day_pnl_val = sim_close_eq - sim_eq
    sim_day_pnl_pct = (sim_day_pnl_val / sim_eq) * 100
            
    held_cash_overnight = liquidated
    sim_eq = sim_close_eq
    
    hit_str = "YES" if liquidated else "NO"
    
    sim_pnl_str = f"${sim_day_pnl_val:+.2f}"
    fric_str = f"-${daily_friction_cost:.2f}"
    
    print(f"{date_str:<12} | {sim_gap_pct:>6.2f}% | {target_pct:>6.2f}% | {hit_str:<5} | {sim_pnl_str:<12} | {sim_day_pnl_pct:>+6.2f}% | {fric_str:<10}")

print("-" * 80)
print(f"SIMULATED Current Equity: ${sim_eq:,.2f}")
