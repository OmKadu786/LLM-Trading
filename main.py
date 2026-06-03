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

LIQUIDATED_TODAY_DATE    = None   # tracks the calendar date of last liquidation
POST_LIQ_BASE_EQ        = None   # equity snapshot right after liquidation (new baseline)
POST_LIQ_UNIX_TIME      = None   # unix timestamp of liquidation (filter history after this)

def check_target_sync() -> bool:
    """Dual-Guard: checks max daily loss + trailing profit stop.
    After a mid-day liquidation, all math resets to the post-liquidation equity
    baseline so new trades made later that day have full protection."""
    try:
        import pytz
        from datetime import datetime
        global POST_LIQ_BASE_EQ, POST_LIQ_UNIX_TIME

        alpaca = get_alpaca_client()
        clock = alpaca.tc.get_clock()
        if not clock.is_open:
            return False

        # --- FRIDAY WEEKEND HARD STOP ---
        et_tz = pytz.timezone('US/Eastern')
        now_et = datetime.now(et_tz)
        if now_et.weekday() == 4 and now_et.hour == 15 and now_et.minute >= 45:
            print("🛑 [WEEKEND HARD STOP] Liquidating all positions before weekend!")
            alpaca.tc.close_all_positions(cancel_orders=True)
            return True

        a = alpaca.tc.get_account()
        last_eq = float(a.last_equity)
        curr_eq = float(a.equity)

        # Use post-liquidation baseline if we already liquidated today,
        # otherwise fall back to yesterday's closing equity.
        base_eq = POST_LIQ_BASE_EQ if POST_LIQ_BASE_EQ else last_eq
        daily_pnl_pct = ((curr_eq / base_eq) - 1) * 100 if base_eq > 0 else 0

        # --- 1. MAX DAILY LOSS GUARD ---
        MAX_LOSS_PCT = -1.50
        if daily_pnl_pct <= MAX_LOSS_PCT:
            print(f"\n☠️ MAX DAILY LOSS HIT: PnL is {daily_pnl_pct:.2f}% from base. Liquidating ALL positions!")
            alpaca.tc.close_all_positions(cancel_orders=True)
            return True

        # --- 2. TRAILING PROFIT GUARD ---
        r = requests.get(
            "https://paper-api.alpaca.markets/v2/account/portfolio/history",
            headers={"APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"),
                     "APCA-API-SECRET-KEY": os.getenv("ALPACA_API_SECRET")},
            params={"period": "1D", "timeframe": "1Min"}
        )

        if r.status_code == 200:
            hist = r.json()
            raw_eq   = hist.get("equity", []) or []
            raw_ts   = hist.get("timestamp", []) or []

            # If we liquidated mid-day, only look at history AFTER that moment
            # so the old morning peak doesn't immediately re-trigger the stop.
            if POST_LIQ_UNIX_TIME and raw_ts:
                eq_list = [
                    e for e, t in zip(raw_eq, raw_ts)
                    if e is not None and t >= POST_LIQ_UNIX_TIME
                ]
            else:
                eq_list = [e for e in raw_eq if e is not None]

            if eq_list:
                peak_eq      = max(max(eq_list), curr_eq)
                peak_pnl_pct = ((peak_eq / base_eq) - 1) * 100 if base_eq > 0 else 0

                print(f"📊 Target Check: Current {daily_pnl_pct:.2f}% | Peak {peak_pnl_pct:.2f}% (base: ${base_eq:,.2f})")

                if peak_pnl_pct >= 1.00:
                    trailing_stop_pct = peak_pnl_pct - 0.85
                    print(f"📈 Trailing Guard Active! Floor at: +{trailing_stop_pct:.2f}%")

                    if daily_pnl_pct <= trailing_stop_pct:
                        print(f"\n🚨 TRAILING STOP HIT: {daily_pnl_pct:.2f}%. Locking in profits!")
                        alpaca.tc.close_all_positions(cancel_orders=True)
                        return True

        return False
    except Exception as e:
        print(f"Target check failed: {e}")
        return False

async def monitor_target():
    global LIQUIDATED_TODAY_DATE, POST_LIQ_BASE_EQ, POST_LIQ_UNIX_TIME
    print("🎯 Live target monitor active (Checking every 5s)")

    while True:
        try:
            alpaca    = get_alpaca_client()
            clock     = alpaca.tc.get_clock()
            today_str = datetime.now().strftime("%Y-%m-%d")

            # Reset all liquidation state at the start of a new calendar day
            if LIQUIDATED_TODAY_DATE != today_str:
                POST_LIQ_BASE_EQ   = None
                POST_LIQ_UNIX_TIME = None
                # (don't reset LIQUIDATED_TODAY_DATE here — it resets implicitly
                #  the next time we liquidate on a new date)

            if not clock.is_open:
                await asyncio.sleep(60)
                continue

            # Always check — no per-day lockout
            if check_target_sync():
                LIQUIDATED_TODAY_DATE = today_str
                # Capture the new equity baseline immediately after selling
                a = get_alpaca_client().tc.get_account()
                POST_LIQ_BASE_EQ   = float(a.equity)
                POST_LIQ_UNIX_TIME = int(datetime.now().timestamp())
                print(f"🔄 Guard reset. New baseline: ${POST_LIQ_BASE_EQ:,.2f}. Monitoring resumes immediately.")

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
    p.add_argument("--cron-hourly", action="store_true", help="Run full trading session")
    p.add_argument("--cron-check", action="store_true", help="Run target monitor only")
    p.add_argument("--interval", type=int, default=60, help="Interval in minutes between runs")
    args = p.parse_args()
    
    async def main_runner():
        if args.cron_hourly or args.cron_check:
            print("🕒 Running GitHub Actions Check...")
            hit_target = check_target_sync()
            if hit_target:
                print("🎯 Target already hit! Exiting.")
                return
            
            if args.cron_hourly:
                print("⏰ Running full AI trading session...")
                await run_live_session()
            else:
                print("⏸️ Mid-hour interval. Checked target, no trades needed. Exiting.")
        elif args.once:
            asyncio.create_task(monitor_target())
            await run_live_session()
        else:
            asyncio.create_task(monitor_target())
            await run_loop(args.interval)

    asyncio.run(main_runner())
