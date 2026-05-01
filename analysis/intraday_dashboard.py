import os, sys, requests, json, webbrowser
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

KEY = os.getenv("ALPACA_API_KEY")
SECRET = os.getenv("ALPACA_API_SECRET")
HEADERS = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET}
BASE = "https://paper-api.alpaca.markets/v2"

def get_monthly_intraday_data():
    print("📡 Fetching 30-day intraday data...")
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=29)
    
    params = {
        "timeframe": "5Min",
        "date_start": start_dt.strftime("%Y-%m-%d"),
        "date_end": end_dt.strftime("%Y-%m-%d"),
        "extended_hours": "true"
    }
    
    r = requests.get(f"{BASE}/account/portfolio/history", headers=HEADERS, params=params)
    if r.status_code != 200:
        print(f"❌ Error fetching data: {r.text}")
        return None
        
    return r.json()

def generate_dashboard(data):
    if not data or "timestamp" not in data or not data["timestamp"]:
        print("⚠️ No data available.")
        return

    # Group by date string (YYYY-MM-DD)
    daily_data = defaultdict(lambda: {"labels": [], "equity": [], "start_eq": None})
    
    prev_eq = None
    prev_date_str = None
    
    for i, ts in enumerate(data["timestamp"]):
        eq = data["equity"][i]
        if eq <= 0: continue
            
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        # Convert to local time
        local_dt = dt.astimezone()
        date_str = local_dt.strftime("%Y-%m-%d")
        time_str = local_dt.strftime("%I:%M %p")
        
        day_dict = daily_data[date_str]
        
        # When entering a new day, the baseline is the final equity of the PREVIOUS day
        if date_str != prev_date_str:
            if prev_eq is not None:
                day_dict["start_eq"] = prev_eq
            else:
                day_dict["start_eq"] = eq
            prev_date_str = date_str
            
        prev_eq = eq
        
        day_dict["labels"].append(time_str)
        day_dict["equity"].append(round(eq, 2))

    # Calculate metrics for each day
    for date_str, day_dict in daily_data.items():
        equity = day_dict["equity"]
        start_eq = day_dict["start_eq"]
        
        day_dict["min_eq"] = min(equity)
        day_dict["max_eq"] = max(equity)
        day_dict["end_eq"] = equity[-1]
        day_dict["day_return"] = round(day_dict["end_eq"] - start_eq, 2)
        day_dict["day_return_pct"] = round((day_dict["day_return"] / start_eq) * 100, 2) if start_eq > 0 else 0
        
        # Calculate pct change array for chart tooltips
        day_dict["pct_change"] = [round(((eq / start_eq) - 1) * 100, 2) for eq in equity]

    # Convert to JSON for JS
    dates = sorted(list(daily_data.keys()), reverse=True) # newest first
    if not dates:
        print("⚠️ No valid equity data found.")
        return
        
    js_data = json.dumps(daily_data)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <title>Intraday Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; background: #0a0a0f; color: #e4e4e7; padding: 30px; margin: 0; }}
        .header {{ margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid rgba(255,255,255,0.05); display: flex; justify-content: space-between; align-items: center; }}
        .title {{ font-size: 24px; font-weight: 800; color: #fff; }}
        .date-select {{ background: #18181b; color: #fff; border: 1px solid rgba(255,255,255,0.1); padding: 10px 15px; border-radius: 8px; font-family: 'Inter'; font-size: 16px; font-weight: 600; cursor: pointer; outline: none; }}
        .date-select:hover {{ border-color: rgba(250, 204, 21, 0.5); }}
        .stats {{ display: flex; gap: 20px; margin-top: 15px; flex-wrap: wrap; }}
        .stat-box {{ flex: 1; background: rgba(255,255,255,0.03); padding: 15px 25px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.05); min-width: 150px; }}
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
        <div class="title">Intraday Tracker</div>
        <select id="dateSelect" class="date-select" onchange="updateDashboard()">
            {''.join([f'<option value="{d}">{d}</option>' for d in dates])}
        </select>
    </div>

    <div class="stats">
        <div class="stat-box">
            <div class="stat-label">Day Start Equity</div>
            <div class="stat-value" id="valStart">--</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Day End/Current</div>
            <div class="stat-value" id="valEnd">--</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Net Profit (Day)</div>
            <div class="stat-value" id="valNet">--</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Intraday High</div>
            <div class="stat-value grn" id="valHigh">--</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Intraday Low</div>
            <div class="stat-value red" id="valLow">--</div>
        </div>
    </div>

    <div class="chart-container">
        <canvas id="intradayChart"></canvas>
    </div>

    <script>
        const dailyData = {js_data};
        let chartInstance = null;
        
        Chart.defaults.color = '#71717a';
        Chart.defaults.font.family = 'Inter';

        function formatCurrency(val) {{
            return '$' + val.toLocaleString('en-US', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
        }}

        function updateDashboard() {{
            const selectedDate = document.getElementById('dateSelect').value;
            const data = dailyData[selectedDate];
            
            // Update stats
            document.getElementById('valStart').innerText = formatCurrency(data.start_eq);
            document.getElementById('valEnd').innerText = formatCurrency(data.end_eq);
            
            const netEl = document.getElementById('valNet');
            const sign = data.day_return >= 0 ? '+' : '';
            netEl.innerText = sign + formatCurrency(data.day_return) + ' (' + sign + data.day_return_pct + '%)';
            netEl.className = 'stat-value ' + (data.day_return >= 0 ? 'grn' : 'red');
            
            document.getElementById('valHigh').innerText = formatCurrency(data.max_eq);
            document.getElementById('valLow').innerText = formatCurrency(data.min_eq);
            
            // Update chart
            const ctx = document.getElementById('intradayChart').getContext('2d');
            
            if (chartInstance) {{
                chartInstance.destroy();
            }}
            
            const gradient = ctx.createLinearGradient(0, 0, 0, 500);
            gradient.addColorStop(0, 'rgba(250, 204, 21, 0.2)');
            gradient.addColorStop(1, 'rgba(250, 204, 21, 0)');

            chartInstance = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: data.labels,
                    datasets: [
                        {{
                            label: 'Equity',
                            data: data.equity,
                            borderColor: '#facc15',
                            backgroundColor: gradient,
                            borderWidth: 2,
                            pointRadius: 0,
                            pointHoverRadius: 5,
                            pointHoverBackgroundColor: '#facc15',
                            fill: true,
                            tension: 0.1
                        }},
                        {{
                            label: 'Open',
                            data: data.equity.map(() => data.start_eq),
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
                            titleColor: '#a1a1aa',
                            bodyColor: '#fff',
                            borderColor: 'rgba(255,255,255,0.1)',
                            borderWidth: 1,
                            padding: 12,
                            displayColors: false,
                            callbacks: {{
                                label: function(context) {{
                                    if (context.datasetIndex === 1) return null; // skip dashed line
                                    const val = context.parsed.y;
                                    const pct = data.pct_change[context.dataIndex];
                                    const sign = pct >= 0 ? '+' : '';
                                    return formatCurrency(val) + ' (' + sign + pct.toFixed(2) + '%)';
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        y: {{ grid: {{ color: 'rgba(255,255,255,0.03)' }} }},
                        x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 12 }} }}
                    }}
                }}
            }});
        }}

        // Initialize on load
        window.onload = updateDashboard;
    </script>
</body>
</html>
"""

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intraday.html")
    with open(out_path, "w") as f:
        f.write(html)
    
    print(f"✅ Multi-day Intraday dashboard generated: {out_path}")
    webbrowser.open(f"file://{out_path}")

if __name__ == "__main__":
    data = get_monthly_intraday_data()
    if data:
        generate_dashboard(data)
