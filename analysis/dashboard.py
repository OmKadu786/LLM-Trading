"""
AI-Trader Portfolio Dashboard v2
Run: python3 dashboard.py
"""
import json, requests, os, webbrowser, math, sys
from datetime import datetime, timezone
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.friction_engine import calculate_friction

KEY = os.getenv("ALPACA_API_KEY")
SECRET = os.getenv("ALPACA_API_SECRET")
HEADERS = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET}
BASE = "https://paper-api.alpaca.markets/v2"

def api(url, params=None):
    r = requests.get(url, headers=HEADERS, params=params or {})
    return r.json() if r.status_code == 200 else {}

# ── Fetch Data ─────────────────────────────────────────────────────────────
print("📡 Fetching data...")
account = api(f"{BASE}/account")
positions = api(f"{BASE}/positions")
history_daily = api(f"{BASE}/account/portfolio/history", {"period": "1M", "timeframe": "1D"})
history_hourly = api(f"{BASE}/account/portfolio/history", {"period": "1W", "timeframe": "1H"})

# Fetch SPY for alpha calc
spy_data = api(f"https://data.alpaca.markets/v2/stocks/SPY/bars", {"timeframe": "1Day", "limit": 30})

# Fetch all fills
all_fills = []
page_token = None
while True:
    params = {"page_size": 100}
    if page_token: params["page_token"] = page_token
    fills = api(f"{BASE}/account/activities/FILL", params)
    if not isinstance(fills, list) or len(fills) == 0: break
    all_fills.extend(fills)
    if len(fills) < 100: break
    page_token = fills[-1]['id']

print(f"   {len(all_fills)} fills fetched")

# ── Process Fills → Orders ─────────────────────────────────────────────────
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

# ── Friction Calculation ───────────────────────────────────────────────────
print("💸 Calculating friction...")
total_friction = 0.0
total_sec_fee = 0.0
total_finra_taf = 0.0
total_slippage = 0.0
total_spread = 0.0
total_latency = 0.0
total_volume = 0.0
total_shares = 0

for o in sorted_orders:
    qty = int(o['total_qty'])
    avg_price = o['total_value'] / qty if qty > 0 else 0
    volume = qty * avg_price
    f = calculate_friction(o['symbol'], o['side'], qty, avg_price)
    d = f.to_dict()
    fb = d['friction_breakdown']
    total_friction += d['total_friction_$']
    total_sec_fee += fb['sec_fee_$']
    total_finra_taf += fb['finra_taf_$']
    total_slippage += fb['slippage_$']
    total_spread += fb['spread_$']
    total_latency += fb['latency_$']
    total_volume += volume
    total_shares += qty

# ── Trade Win/Loss (round trips) ──────────────────────────────────────────
print("📊 Calculating trade P&L...")
inventory = defaultdict(lambda: {'qty': 0, 'cost': 0.0})
trade_details = []  # detailed trade info for leaderboard

for o in sorted_orders:
    sym = o['symbol']
    qty = o['total_qty']
    avg_price = o['total_value'] / qty if qty > 0 else 0
    inv = inventory[sym]
    if o['side'] == 'buy':
        inv['qty'] += qty
        inv['cost'] += o['total_value']
    elif o['side'] == 'sell' and inv['qty'] > 0:
        avg_cost = inv['cost'] / inv['qty']
        pnl = (avg_price - avg_cost) * qty
        trade_details.append({
            'symbol': sym, 'qty': int(qty), 'entry': round(avg_cost, 2),
            'exit': round(avg_price, 2), 'pnl': round(pnl, 2),
            'pnl_pct': round((avg_price / avg_cost - 1) * 100, 2) if avg_cost > 0 else 0,
            'date': o['time'][:10]
        })
        inv['qty'] -= qty
        inv['cost'] -= avg_cost * qty

trade_pnls = [t['pnl'] for t in trade_details]
winning_trades = [p for p in trade_pnls if p > 0]
losing_trades = [p for p in trade_pnls if p <= 0]
trade_win_rate = len(winning_trades) / len(trade_pnls) * 100 if trade_pnls else 0
avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0
avg_loss = sum(losing_trades) / len(losing_trades) if losing_trades else 0
top_winners = sorted(trade_details, key=lambda x: x['pnl'], reverse=True)[:5]
top_losers = sorted(trade_details, key=lambda x: x['pnl'])[:5]

# ── Daily equity data ─────────────────────────────────────────────────────
daily_labels, daily_equity, daily_pnl, daily_pnl_pct = [], [], [], []
daily_returns = []
if history_daily and "timestamp" in history_daily:
    prev_eq = None
    for i, ts in enumerate(history_daily["timestamp"]):
        eq = history_daily["equity"][i]
        if eq <= 0: continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        daily_labels.append(dt.strftime("%b %d"))
        daily_equity.append(round(eq, 2))
        daily_pnl.append(round(history_daily["profit_loss"][i], 2))
        daily_pnl_pct.append(round(history_daily["profit_loss_pct"][i] * 100, 2))
        if prev_eq and prev_eq > 0:
            daily_returns.append((eq - prev_eq) / prev_eq)
        prev_eq = eq

# Hourly data
hourly_labels, hourly_equity = [], []
if history_hourly and "timestamp" in history_hourly:
    for i, ts in enumerate(history_hourly["timestamp"]):
        eq = history_hourly["equity"][i]
        if eq <= 0: continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        hourly_labels.append(dt.strftime("%b %d %H:%M"))
        hourly_equity.append(round(eq, 2))

# ── Sharpe Ratio ──────────────────────────────────────────────────────────
risk_free_daily = 0.05 / 252  # 5% annual risk-free
if len(daily_returns) >= 2:
    mean_r = sum(daily_returns) / len(daily_returns)
    std_r = math.sqrt(sum((r - mean_r)**2 for r in daily_returns) / (len(daily_returns) - 1))
    sharpe = ((mean_r - risk_free_daily) / std_r) * math.sqrt(252) if std_r > 0 else 0
else:
    sharpe = 0

# ── Alpha (vs SPY) ───────────────────────────────────────────────────────
spy_return = 0
if spy_data and "bars" in spy_data and spy_data["bars"]:
    bars = spy_data["bars"]
    if len(bars) >= 2:
        spy_start = float(bars[0]["c"])
        spy_end = float(bars[-1]["c"])
        spy_return = (spy_end - spy_start) / spy_start * 100

equity = float(account.get("equity", 0))
base_value = 30000.0
total_return = equity - base_value
total_return_pct = (total_return / base_value) * 100
trading_days = len(daily_labels)
# Annualize both returns for fair alpha comparison
ann_factor = 252 / max(trading_days, 1)
portfolio_ann = total_return_pct * ann_factor
spy_ann = spy_return * ann_factor
alpha = total_return_pct - spy_return  # simple alpha over the period

# ── Positions ─────────────────────────────────────────────────────────────
pos_data = []
for p in (positions if isinstance(positions, list) else []):
    upl = float(p["unrealized_pl"])
    pos_data.append({
        "symbol": p["symbol"], "qty": int(float(p["qty"])),
        "entry": round(float(p["avg_entry_price"]), 2),
        "current": round(float(p["current_price"]), 2),
        "value": round(float(p["market_value"]), 2),
        "pnl": round(upl, 2),
        "pnl_pct": round(float(p["unrealized_plpc"]) * 100, 2),
    })
pos_data.sort(key=lambda x: x["pnl"], reverse=True)

# ── Key metrics ───────────────────────────────────────────────────────────
best_day = max(daily_pnl) if daily_pnl else 0
worst_day = min(daily_pnl) if daily_pnl else 0
win_days = sum(1 for x in daily_pnl if x > 0)
lose_days = sum(1 for x in daily_pnl if x < 0)

# ── Generate HTML ─────────────────────────────────────────────────────────
print("🎨 Generating dashboard...")

html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI-Trader Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',sans-serif;background:#0a0a0f;color:#e4e4e7;min-height:100vh;padding:24px}}
.hdr{{display:flex;justify-content:space-between;align-items:center;margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid rgba(255,255,255,0.06)}}
.hdr h1{{font-size:26px;font-weight:800;background:linear-gradient(135deg,#818cf8,#c084fc,#f472b6);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.badge{{background:rgba(34,197,94,0.15);color:#4ade80;padding:6px 14px;border-radius:20px;font-size:12px;font-weight:600;border:1px solid rgba(34,197,94,0.2)}}
.grid{{display:grid;gap:14px;margin-bottom:24px}}
.g6{{grid-template-columns:repeat(6,1fr)}}
.g4{{grid-template-columns:repeat(4,1fr)}}
.g3{{grid-template-columns:repeat(3,1fr)}}
.g2{{grid-template-columns:1fr 1fr}}
@media(max-width:1100px){{.g6,.g4{{grid-template-columns:repeat(3,1fr)}}}}
@media(max-width:700px){{.g6,.g4,.g3,.g2{{grid-template-columns:1fr}}}}
.card{{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:18px;backdrop-filter:blur(10px);transition:border-color .3s}}
.card:hover{{border-color:rgba(129,140,248,0.3)}}
.card .lbl{{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:#52525b;margin-bottom:6px}}
.card .val{{font-size:26px;font-weight:800;letter-spacing:-1px}}
.card .sub{{font-size:12px;margin-top:3px;font-weight:500}}
.grn{{color:#4ade80}}.red{{color:#f87171}}.pur{{color:#a78bfa}}.blu{{color:#60a5fa}}.ylw{{color:#fbbf24}}.cyn{{color:#22d3ee}}
.sec{{margin-bottom:24px}}
.sec h2{{font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#52525b;margin-bottom:14px}}
.cbox{{background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:20px}}
.tabs{{display:flex;gap:6px;margin-bottom:14px}}
.tab{{padding:5px 14px;border-radius:7px;font-size:12px;font-weight:500;cursor:pointer;border:1px solid rgba(255,255,255,0.1);background:transparent;color:#71717a;transition:all .2s}}
.tab.on{{background:rgba(129,140,248,0.15);color:#818cf8;border-color:rgba(129,140,248,0.3)}}
canvas{{max-height:320px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:8px 10px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#3f3f46;border-bottom:1px solid rgba(255,255,255,0.06)}}
td{{padding:10px;border-bottom:1px solid rgba(255,255,255,0.03);font-weight:500}}
tr:hover td{{background:rgba(255,255,255,0.02)}}
.bar{{display:inline-block;height:5px;border-radius:3px;margin-left:6px;vertical-align:middle}}
.foot{{text-align:center;padding:20px;color:#27272a;font-size:11px;margin-top:16px}}
</style></head><body>

<div class="hdr">
  <h1>🤖 AI-Trader Dashboard</h1>
  <span class="badge">📡 PAPER &bull; {datetime.now().strftime("%b %d, %Y %I:%M %p")}</span>
</div>

<!-- ROW 1: Key Metrics -->
<div class="grid g6">
  <div class="card"><div class="lbl">Portfolio</div><div class="val">${equity:,.2f}</div><div class="sub {'grn' if total_return>=0 else 'red'}">{'↑' if total_return>=0 else '↓'} ${abs(total_return):,.2f}</div></div>
  <div class="card"><div class="lbl">Total Return</div><div class="val {'grn' if total_return>=0 else 'red'}">{total_return_pct:+.2f}%</div><div class="sub" style="color:#52525b">{trading_days} trading days</div></div>
  <div class="card"><div class="lbl">Sharpe Ratio</div><div class="val {'grn' if sharpe>1 else 'ylw' if sharpe>0 else 'red'}">{sharpe:.2f}</div><div class="sub" style="color:#52525b">annualized</div></div>
  <div class="card"><div class="lbl">Alpha vs SPY</div><div class="val {'grn' if alpha>0 else 'red'}">{alpha:+.2f}%</div><div class="sub" style="color:#52525b">SPY: {spy_return:+.2f}%</div></div>
  <div class="card"><div class="lbl">Best Day</div><div class="val grn">+${best_day:,.0f}</div><div class="sub" style="color:#52525b">single session</div></div>
  <div class="card"><div class="lbl">Worst Day</div><div class="val red">${worst_day:,.0f}</div><div class="sub" style="color:#52525b">single session</div></div>
</div>

<!-- ROW 2: Trade Stats -->
<div class="sec"><h2>Trade Performance</h2></div>
<div class="grid g4">
  <div class="card"><div class="lbl">Trade Win Rate</div><div class="val {'grn' if trade_win_rate>=50 else 'red'}">{trade_win_rate:.0f}%</div><div class="sub" style="color:#52525b">{len(winning_trades)}W / {len(losing_trades)}L of {len(trade_pnls)} trades</div></div>
  <div class="card"><div class="lbl">Avg Win</div><div class="val grn">+${avg_win:,.2f}</div><div class="sub" style="color:#52525b">per winning trade</div></div>
  <div class="card"><div class="lbl">Avg Loss</div><div class="val red">${avg_loss:,.2f}</div><div class="sub" style="color:#52525b">per losing trade</div></div>
  <div class="card"><div class="lbl">Win/Loss Ratio</div><div class="val pur">{abs(avg_win/avg_loss) if avg_loss != 0 else 0:.2f}x</div><div class="sub" style="color:#52525b">avg win ÷ avg loss</div></div>
</div>

<!-- ROW 3: Friction/Costs -->
<div class="sec"><h2>Trading Costs (Live Market Estimate)</h2></div>
<div class="grid g6">
  <div class="card"><div class="lbl">Total Friction</div><div class="val ylw">${total_friction:,.2f}</div><div class="sub" style="color:#52525b">{(total_friction/total_volume*100) if total_volume > 0 else 0:.3f}% of volume</div></div>
  <div class="card"><div class="lbl">SEC Fee</div><div class="val" style="color:#71717a">${total_sec_fee:,.2f}</div><div class="sub" style="color:#52525b">sell-side only</div></div>
  <div class="card"><div class="lbl">FINRA TAF</div><div class="val" style="color:#71717a">${total_finra_taf:,.2f}</div><div class="sub" style="color:#52525b">per-share fee</div></div>
  <div class="card"><div class="lbl">Slippage</div><div class="val" style="color:#71717a">${total_slippage:,.2f}</div><div class="sub" style="color:#52525b">market impact</div></div>
  <div class="card"><div class="lbl">Spread Cost</div><div class="val" style="color:#71717a">${total_spread:,.2f}</div><div class="sub" style="color:#52525b">bid-ask spread</div></div>
  <div class="card"><div class="lbl">Latency Cost</div><div class="val" style="color:#71717a">${total_latency:,.2f}</div><div class="sub" style="color:#52525b">execution delay</div></div>
</div>

<!-- Equity Curve — FULL WIDTH -->
<div class="cbox" style="margin-bottom:16px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
    <h2 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#52525b;margin:0">Equity Curve</h2>
    <div class="tabs"><button class="tab on" onclick="showD()">Daily</button><button class="tab" onclick="showH()">Hourly</button></div>
  </div>
  <canvas id="eq"></canvas>
</div>

<!-- Cumulative Return — FULL WIDTH -->
<div class="cbox" style="margin-bottom:16px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
    <h2 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#52525b;margin:0">Cumulative Return (%)</h2>
    <div class="tabs"><button class="tab on" id="cumD" onclick="showCumD()">Daily</button><button class="tab" id="cumH" onclick="showCumH()">Hourly</button></div>
  </div>
  <canvas id="cum"></canvas>
</div>

<!-- Daily P&L + Positions — side by side -->
<div class="grid g2" style="margin-top:8px">
  <div class="cbox">
    <h2 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#52525b;margin-bottom:14px">Daily P&L</h2>
    <canvas id="pnl"></canvas>
  </div>
  <div class="cbox">
    <h2 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#52525b;margin-bottom:14px">Open Positions</h2>
    <table><thead><tr><th>Symbol</th><th>Qty</th><th>Entry</th><th>Now</th><th>P&L</th></tr></thead><tbody>
"""

for p in pos_data:
    c = "grn" if p["pnl"] >= 0 else "red"
    bw = min(abs(p["pnl_pct"]) * 4, 60)
    bc = '#4ade80' if p['pnl'] >= 0 else '#f87171'
    html += f'<tr><td style="font-weight:700">{p["symbol"]}</td><td>{p["qty"]}</td><td style="color:#52525b">${p["entry"]:,.2f}</td><td>${p["current"]:,.2f}</td><td class="{c}">{p["pnl_pct"]:+.2f}% <span style="color:#52525b">(${p["pnl"]:+,.2f})</span><span class="bar" style="width:{bw}px;background:{bc}"></span></td></tr>\n'

html += f"""</tbody></table></div></div>

<!-- Top Trades Leaderboard -->
<div class="sec" style="margin-top:24px"><h2>Trade Leaderboard</h2></div>
<div class="grid g2">
  <div class="cbox">
    <h2 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#4ade80;margin-bottom:14px">🏆 Top Winning Trades</h2>
    <table><thead><tr><th>Date</th><th>Symbol</th><th>Qty</th><th>Entry</th><th>Exit</th><th>P&L</th></tr></thead><tbody>
"""

for t in top_winners:
    html += f'<tr><td style="color:#52525b">{t["date"]}</td><td style="font-weight:700">{t["symbol"]}</td><td>{t["qty"]}</td><td style="color:#52525b">${t["entry"]:,.2f}</td><td>${t["exit"]:,.2f}</td><td class="grn">+${t["pnl"]:,.2f} <span style="color:#52525b">({t["pnl_pct"]:+.2f}%)</span></td></tr>\n'

html += """</tbody></table></div>
  <div class="cbox">
    <h2 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#f87171;margin-bottom:14px">💀 Top Losing Trades</h2>
    <table><thead><tr><th>Date</th><th>Symbol</th><th>Qty</th><th>Entry</th><th>Exit</th><th>P&L</th></tr></thead><tbody>
"""

for t in top_losers:
    html += f'<tr><td style="color:#52525b">{t["date"]}</td><td style="font-weight:700">{t["symbol"]}</td><td>{t["qty"]}</td><td style="color:#52525b">${t["entry"]:,.2f}</td><td>${t["exit"]:,.2f}</td><td class="red">${t["pnl"]:,.2f} <span style="color:#52525b">({t["pnl_pct"]:+.2f}%)</span></td></tr>\n'

html += f"""</tbody></table></div></div>

<div class="foot">AI-Trader &bull; DeepSeek V3 &bull; Alpaca Paper &bull; {len(sorted_orders)} trades &bull; {total_shares:,} shares &bull; ${total_volume:,.0f} volume</div>

<script>
const dL={json.dumps(daily_labels)},dE={json.dumps(daily_equity)},dP={json.dumps(daily_pnl)},dPp={json.dumps(daily_pnl_pct)};
const hL={json.dumps(hourly_labels)},hE={json.dumps(hourly_equity)};
Chart.defaults.color='#52525b';Chart.defaults.borderColor='rgba(255,255,255,0.03)';Chart.defaults.font.family='Inter';
const gr=(ctx,c1,c2)=>{{const g=ctx.chart.ctx.createLinearGradient(0,0,0,ctx.chart.height);g.addColorStop(0,c1);g.addColorStop(1,c2);return g}};

let eq=new Chart(document.getElementById('eq'),{{type:'line',data:{{labels:dL,datasets:[{{data:dE,borderColor:'#818cf8',backgroundColor:ctx=>gr(ctx,'rgba(129,140,248,0.12)','rgba(129,140,248,0)'),borderWidth:2.5,fill:true,tension:.4,pointRadius:4,pointBackgroundColor:'#818cf8',pointBorderColor:'#0a0a0f',pointBorderWidth:2}},{{data:dE.map(()=>30000),borderColor:'rgba(255,255,255,0.08)',borderWidth:1,borderDash:[6,4],pointRadius:0,fill:false}}]}},options:{{responsive:true,plugins:{{legend:{{display:false}},tooltip:{{backgroundColor:'#18181b',borderColor:'rgba(255,255,255,0.1)',borderWidth:1,callbacks:{{label:c=>'$'+c.parsed.y.toLocaleString('en-US',{{minimumFractionDigits:2}})}}}}}},scales:{{y:{{ticks:{{callback:v=>'$'+(v/1000).toFixed(1)+'k'}}}},x:{{grid:{{display:false}}}}}}}}}});

function showD(){{eq.data.labels=dL;eq.data.datasets[0].data=dE;eq.data.datasets[1].data=dE.map(()=>30000);eq.update();document.querySelectorAll('#eq').parentElement.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));document.querySelectorAll('.tab')[0].classList.add('on')}}
function showH(){{eq.data.labels=hL;eq.data.datasets[0].data=hE;eq.data.datasets[1].data=hE.map(()=>30000);eq.update();document.querySelectorAll('#eq').parentElement.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));document.querySelectorAll('.tab')[1].classList.add('on')}}

new Chart(document.getElementById('pnl'),{{type:'bar',data:{{labels:dL,datasets:[{{data:dP,backgroundColor:dP.map(v=>v>=0?'rgba(74,222,128,0.7)':'rgba(248,113,113,0.7)'),borderColor:dP.map(v=>v>=0?'#4ade80':'#f87171'),borderWidth:1,borderRadius:6}}]}},options:{{responsive:true,plugins:{{legend:{{display:false}},tooltip:{{backgroundColor:'#18181b',callbacks:{{label:c=>(c.parsed.y>=0?'+$':'-$')+Math.abs(c.parsed.y).toLocaleString('en-US',{{minimumFractionDigits:2}})}}}}}},scales:{{y:{{ticks:{{callback:v=>(v>=0?'+$':'-$')+Math.abs(v/1000).toFixed(1)+'k'}}}},x:{{grid:{{display:false}}}}}}}}}});

const cm=dE.map(e => (e - 30000) / 300);
const cmH=hE.map(e => (e - 30000) / 300);

let cumChart=new Chart(document.getElementById('cum'),{{type:'line',data:{{labels:dL,datasets:[{{data:cm,borderColor:'#c084fc',backgroundColor:ctx=>gr(ctx,'rgba(192,132,252,0.1)','rgba(192,132,252,0)'),borderWidth:2.5,fill:true,tension:.4,pointRadius:4,pointBackgroundColor:'#c084fc',pointBorderColor:'#0a0a0f',pointBorderWidth:2}},{{data:cm.map(()=>0),borderColor:'rgba(255,255,255,0.06)',borderWidth:1,borderDash:[6,4],pointRadius:0,fill:false}}]}},options:{{responsive:true,plugins:{{legend:{{display:false}},tooltip:{{backgroundColor:'#18181b',callbacks:{{label:c=>c.parsed.y.toFixed(2)+'%'}}}}}},scales:{{y:{{ticks:{{callback:v=>v.toFixed(1)+'%'}}}},x:{{grid:{{display:false}}}}}}}}}});

function showCumD(){{cumChart.data.labels=dL;cumChart.data.datasets[0].data=cm;cumChart.data.datasets[1].data=cm.map(()=>0);cumChart.update();document.getElementById('cumD').classList.add('on');document.getElementById('cumH').classList.remove('on')}}
function showCumH(){{cumChart.data.labels=hL;cumChart.data.datasets[0].data=cmH;cumChart.data.datasets[1].data=cmH.map(()=>0);cumChart.update();document.getElementById('cumH').classList.add('on');document.getElementById('cumD').classList.remove('on')}}

</script></body></html>"""

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
with open(out, "w") as f:
    f.write(html)
print(f"✅ Dashboard saved: {out}")
webbrowser.open(f"file://{out}")
