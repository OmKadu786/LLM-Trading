import asyncio, os, sys, json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from agent.base_agent.base_agent import BaseAgent
from tools.alpaca_client import get_alpaca_client


async def run_live_session():
    config = json.loads((project_root / "configs" / "default_config.json").read_text())
    # Find the enabled model
    model = next(m for m in config["models"] if m.get("enabled"))
    acfg = config.get("agent_config", {})
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        acct = get_alpaca_client().get_account()
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
    p.add_argument("--interval", type=int, default=60, help="Interval in minutes between runs")
    args = p.parse_args()
    asyncio.run(run_live_session() if args.once else run_loop(args.interval))
