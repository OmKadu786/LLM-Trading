import os, json, requests
from collections import defaultdict
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

headers = {
    "APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"),
    "APCA-API-SECRET-KEY": os.getenv("ALPACA_API_SECRET")
}

def get_table():
    # Get all fills
    res = requests.get("https://paper-api.alpaca.markets/v2/account/activities/FILL", headers=headers)
    fills = res.json()
    
    # Get current positions
    res_pos = requests.get("https://paper-api.alpaca.markets/v2/positions", headers=headers)
    positions = {p['symbol']: p for p in res_pos.json()}

    # Group by symbol
    trades = defaultdict(list)
    for f in fills:
        trades[f['symbol']].append(f)
    
    table = "| Symbol | Action | Qty | Avg Price | Total Value | Realized P&L | Unrealized P&L | Status |\n"
    table += "|--------|--------|-----|-----------|-------------|--------------|----------------|--------|\n"
    
    total_realized = 0.0
    total_unrealized = 0.0

    for symbol, sym_fills in trades.items():
        # Sort by time
        sym_fills.sort(key=lambda x: x['transaction_time'])
        
        long_qty = 0
        cost_basis = 0.0
        realized_pl = 0.0
        
        for f in sym_fills:
            qty = float(f['qty'])
            price = float(f['price'])
            if f['side'] == 'buy':
                cost_basis += qty * price
                long_qty += qty
            elif f['side'] == 'sell':
                # Avg cost
                avg_cost = cost_basis / long_qty if long_qty > 0 else 0
                trade_pl = (price - avg_cost) * qty
                realized_pl += trade_pl
                long_qty -= qty
                cost_basis -= avg_cost * qty
                
        # Check open positions
        unrealized_pl = 0.0
        status = "Closed"
        
        if symbol in positions:
            pos = positions[symbol]
            unrealized_pl = float(pos['unrealized_pl'])
            status = f"Open ({pos['qty']} sh)"
            avg_price = float(pos['avg_entry_price'])
            qty = float(pos['qty'])
            total_val = float(pos['market_value'])
            table += f"| **{symbol}** | HOLD | {qty} | ${avg_price:.2f} | ${total_val:.2f} | ${realized_pl:.2f} | ${unrealized_pl:.2f} | {status} |\n"
        else:
            table += f"| **{symbol}** | CLOSED | 0 | - | $0.00 | ${realized_pl:.2f} | $0.00 | {status} |\n"
            
        total_realized += realized_pl
        total_unrealized += unrealized_pl
        
    table += f"| **TOTAL** | | | | | **${total_realized:.2f}** | **${total_unrealized:.2f}** | |\n"
    
    print(table)

if __name__ == "__main__":
    get_table()
