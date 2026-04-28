import json, requests, os, sys
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.friction_engine import calculate_friction

headers = {
    'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'),
    'APCA-API-SECRET-KEY': os.getenv('ALPACA_API_SECRET')
}

# Paginate all fills
all_fills = []
page_token = None
while True:
    params = {"page_size": 100}
    if page_token:
        params["page_token"] = page_token
    resp = requests.get('https://paper-api.alpaca.markets/v2/account/activities/FILL', headers=headers, params=params)
    fills = resp.json()
    if not isinstance(fills, list) or len(fills) == 0:
        break
    all_fills.extend(fills)
    if len(fills) < 100:
        break
    page_token = fills[-1]['id']

print(f"Total fills fetched: {len(all_fills)}")

# Merge partial fills into logical orders
orders = defaultdict(lambda: {'symbol':'','side':'','total_qty':0,'total_value':0,'time':''})
for f in all_fills:
    oid = f['order_id']
    o = orders[oid]
    o['symbol'] = f['symbol']
    o['side'] = f['side']
    o['total_qty'] += float(f['qty'])
    o['total_value'] += float(f['qty']) * float(f['price'])
    if not o['time'] or f['transaction_time'] > o['time']:
        o['time'] = f['transaction_time']

sorted_orders = sorted(orders.values(), key=lambda x: x['time'])

total_friction = 0.0
total_volume = 0.0
total_shares = 0

print(f"{'#':>3} | {'Date':>10} | {'Sym':>6} | {'Side':>4} | {'Qty':>5} | {'Price':>8} | {'Volume':>10} | {'Friction':>9} | {'%':>6}")
print("-" * 85)

for i, o in enumerate(sorted_orders, 1):
    sym = o['symbol']
    qty = int(o['total_qty'])
    avg_price = o['total_value'] / qty if qty > 0 else 0
    volume = qty * avg_price

    f = calculate_friction(sym, o['side'], qty, avg_price)
    d = f.to_dict()
    fric = d['total_friction_$']
    fric_pct = d['total_friction_%']

    total_friction += fric
    total_volume += volume
    total_shares += qty

    date = o['time'][:10]
    print(f"{i:>3} | {date} | {sym:>6} | {o['side']:>4} | {qty:>5} | ${avg_price:>7.2f} | ${volume:>9,.2f} | ${fric:>8.4f} | {fric_pct:>5.3f}%")

print("-" * 85)
print(f"TOTALS: {len(sorted_orders)} trades | {total_shares:,} shares | ${total_volume:,.2f} volume")
print(f"TOTAL FRICTION COST: ${total_friction:,.2f} ({total_friction/total_volume*100:.4f}% of volume)")
