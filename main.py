import asyncio, os, sys, json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from agent.base_agent.base_agent import BaseAgent
from tools.alpaca_client import get_alpaca_client
import requests

LIQUIDATED_TODAY_DATE = None

async def monitor_target():
    global LIQUIDATED_TODAY_DATE
    print("🎯 Live target monitor active (Checking every 5s)")
    
    while True:
        try:
            alpaca = get_alpaca_client()
            clock = alpaca.tc.get_clock()
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            if not clock.is_open or LIQUIDATED_TODAY_DATE == today_str:
                await asyncio.sleep(60)
                continue
                
            a = alpaca.tc.get_account()
            last_eq = float(a.last_equity)
            curr_eq = float(a.equity)
            daily_pnl_pct = ((curr_eq / last_eq) - 1) * 100 if last_eq > 0 else 0
            
            target_pct = 1.5
            r = requests.get(
                "https://paper-api.alpaca.markets/v2/account/portfolio/history",
                headers={"APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"), "APCA-API-SECRET-KEY": os.getenv("ALPACA_API_SECRET")},
                params={"period": "1D", "timeframe": "1Min"}
            )
            if r.status_code == 200:
                hist = r.json()
                if hist.get("equity") and len(hist["equity"]) > 0:
                    today_open = float(hist["equity"][0])
                    if last_eq > today_open:
                        gap_down_pct = ((last_eq - today_open) / last_eq) * 100
                        target_pct = 1.5 - gap_down_pct
                        
            if daily_pnl_pct >= target_pct:
                print(f"\n🚨 INSTANT TARGET HIT: PnL is {daily_pnl_pct:.2f}%. Target was {target_pct:.2f}%. Liquidating ALL positions instantly!")
                alpaca.tc.close_all_positions(cancel_orders=True)
                LIQUIDATED_TODAY_DATE = today_str
                
        except Exception as e:
            pass
            
        await asyncio.sleep(5)



async def run_live_session():
    config = json.loads((project_root / "configs" / "default_config.json").read_text())
    # Find the enabled model
    model = next(m for m in config["models"] if m.get("enabled"))
    acfg = config.get("agent_config", {})
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    global LIQUIDATED_TODAY_DATE
    if LIQUIDATED_TODAY_DATE == datetime.now().strftime("%Y-%m-%d"):
        print("🛑 Session skipped. Target was already hit today.")
        return

    try:
        alpaca = get_alpaca_client()
        acct = alpaca.get_account()
    except Exception as e:
        print(f"❌ Alpaca connection failed: {e}")
        return

    # Both price + trade point to the single merged MCP server on TRADE_HTTP_PORT
    alpaca_url = f"http://localhost:{os.getenv('TRADE_HTTP_PORT', '8002')}/mcp"
    mcp_config = {
        "math":   {"transport": "streamable_http", "url": f"http://localhost:{os.getenv('MATH_HTTP_PORT','8004')}/mcp"},
        "search": {"transport": "streamable_http", "url": f"http://localhost:{os.getenv('SEARCH_HTTP_PORT','8001')}/mcp"},
        "alpaca": {"transport": "streamable_http", "url": alpaca_url},
    }

    agent = BaseAgent(
        signature=model["signature"], 
        basemodel=model["basemodel"],
        mcp_config=mcp_config,
        log_path=config.get("log_config", {}).get("log_path", "./data/agent_data"),
        max_steps=acfg.get("max_steps", 30), 
        max_retries=acfg.get("max_retries", 3),
        base_delay=acfg.get("base_delay", 1.0), 
        initial_cash=acct["cash"],
        verbose=acfg.get("verbose", True),
    )

    os.environ["IS_LIVE"] = "true"

    await agent.initialize()
    print(f"\n{'='*50}\n🚀 LIVE SESSION: {now}\n{'='*50}\n")
    await agent.run_trading_session(now)


async def run_loop(interval_minutes: int = 60):
    print(f"🔄 Live loop — every {interval_minutes} min")
    while True:
        try:
            client = get_alpaca_client()
            clock = client.tc.get_clock()
            if clock.is_open:
                print(f"📈 Market is OPEN. Starting session...")
                await run_live_session()
            else:
                next_open = clock.next_open.strftime('%Y-%m-%d %H:%M:%S %Z')
                print(f"⏰ Market is CLOSED. Next open: {next_open}")
        except Exception as e:
            print(f"❌ Session failed: {e}")
        await asyncio.sleep(interval_minutes * 60)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true", help="Run once and exit")
    p.add_argument("--interval", type=int, default=15, help="Interval in minutes between runs")
    args = p.parse_args()
    
    async def main_runner():
        asyncio.create_task(monitor_target())
        if args.once:
            await run_live_session()
        else:
            await run_loop(args.interval)

    asyncio.run(main_runner())
