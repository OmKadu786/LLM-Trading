import os, sys, requests, json, argparse, webbrowser
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

KEY = os.getenv("ALPACA_API_KEY")
SECRET = os.getenv("ALPACA_API_SECRET")
HEADERS = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET}
BASE = "https://paper-api.alpaca.markets/v2"

def get_intraday_history(target_date):
    # target_date format: YYYY-MM-DD
    print(f"📡 Fetching intraday data for {target_date}...")
    
    # We fetch 5-min candles for the specific day
    params = {
        "timeframe": "5Min",
        "date_start": target_date,
        "date_end": target_date,
        "extended_hours": "true"
    }
    
    r = requests.get(f"{BASE}/account/portfolio/history", headers=HEADERS, params=params)
    if r.status_code != 200:
        print(f"❌ Error fetching data: {r.text}")
        return None
        
    return r.json()

def generate_dashboard(data, target_date):
    if not data or "timestamp" not in data or not data["timestamp"]:
        print("⚠️ No data available for this date. The market might have been closed, or the date is in the future.")
        return

    labels = []
    equity = []
    
    start_eq = None
    for i, ts in enumerate(data["timestamp"]):
        eq = data["equity"][i]
        if eq <= 0: continue
        if start_eq is None: start_eq = eq
            
        # Convert timestamp to local time string
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        labels.append(dt.strftime("%I:%M %p"))
        equity.append(round(eq, 2))
        
    if not equity:
        print("⚠️ No valid equity data found.")
        return

    min_eq = min(equity)
    max_eq = max(equity)
    end_eq = equity[-1]
    
    day_return = end_eq - start_eq
    day_return_pct = (day_return / start_eq) * 100 if start_eq > 0 else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <title>Intraday Dashboard - {target_date}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; background: #0a0a0f; color: #e4e4e7; padding: 30px; margin: 0; }}
        .header {{ margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid rgba(255,255,255,0.05); }}
        .title {{ font-size: 24px; font-weight: 800; color: #fff; margin-bottom: 10px; }}
        .stats {{ display: flex; gap: 40px; margin-top: 15px; }}
        .stat-box {{ background: rgba(255,255,255,0.03); padding: 15px 25px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.05); }}
        .stat-label {{ font-size: 11px; text-transform: uppercase; color: #a1a1aa; font-weight: 600; letter-spacing: 1px; margin-bottom: 5px; }}
        .stat-value {{ font-size: 22px; font-weight: 800; }}
        .grn {{ color: #4ade80; }}
        .red {{ color: #f87171; }}
        .chart-container {{ background: rgba(255,255,255,0.02); padding: 20px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.05); margin-top: 20px; }}
        canvas {{ width: 100%; height: 500px !important; }}
    </style>
</head>
<body>

    <div class="header">
        <div class="title">Intraday Tracker: {target_date}</div>
        <div class="stats">
            <div class="stat-box">
                <div class="stat-label">Day Start Equity</div>
                <div class="stat-value">${start_eq:,.2f}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Day End Equity</div>
                <div class="stat-value">${end_eq:,.2f}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Net Profit (Day)</div>
                <div class="stat-value {'grn' if day_return >= 0 else 'red'}">${day_return:+,.2f} ({day_return_pct:+.2f}%)</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Intraday High</div>
                <div class="stat-value grn">${max_eq:,.2f}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Intraday Low</div>
                <div class="stat-value red">${min_eq:,.2f}</div>
            </div>
        </div>
    </div>

    <div class="chart-container">
        <canvas id="intradayChart"></canvas>
    </div>

    <script>
        const labels = {json.dumps(labels)};
        const data = {json.dumps(equity)};
        const startEq = {start_eq};
        
        Chart.defaults.color = '#71717a';
        Chart.defaults.font.family = 'Inter';

        const ctx = document.getElementById('intradayChart').getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, 500);
        gradient.addColorStop(0, 'rgba(250, 204, 21, 0.2)'); // Yellow/Gold tint
        gradient.addColorStop(1, 'rgba(250, 204, 21, 0)');

        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: labels,
                datasets: [
                    {{
                        label: 'Equity',
                        data: data,
                        borderColor: '#facc15',
                        backgroundColor: gradient,
                        borderWidth: 2,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        fill: true,
                        tension: 0.1
                    }},
                    {{
                        label: 'Open',
                        data: data.map(() => startEq),
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1,
                        borderDash: [5, 5],
                        pointRadius: 0,
                        fill: false
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                interaction: {{
                    intersect: false,
                    mode: 'index',
                }},
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{
                        backgroundColor: '#18181b',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1,
                        callbacks: {{
                            label: (ctx) => '$' + ctx.parsed.y.toLocaleString(undefined, {{minimumFractionDigits: 2}})
                        }}
                    }}
                }},
                scales: {{
                    y: {{
                        grid: {{ color: 'rgba(255,255,255,0.03)' }}
                    }},
                    x: {{
                        grid: {{ display: false }},
                        ticks: {{ maxTicksLimit: 12 }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intraday.html")
    with open(out_path, "w") as f:
        f.write(html)
    
    print(f"✅ Intraday dashboard generated: {out_path}")
    webbrowser.open(f"file://{out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate an intraday equity dashboard.")
    parser.add_argument("--date", type=str, help="Date in YYYY-MM-DD format. Defaults to today.", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    data = get_intraday_history(args.date)
    if data:
        generate_dashboard(data, args.date)
