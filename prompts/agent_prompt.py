import json
from tools.alpaca_client import get_alpaca_client
from tools.friction_engine import friction_summary_for_prompt

STOP_SIGNAL = "---STOP---"

def get_agent_system_prompt(today_date: str, signature: str = "", market: str = "us", stock_symbols: list = None) -> str:
    try:
        client = get_alpaca_client()
        account = client.get_account()
        positions = client.get_positions()
        positions_str = json.dumps({**positions, "CASH": account["cash"]}, indent=2).replace("{", "{{").replace("}", "}}")
    except Exception as e:
        account = {"cash": 0, "equity": 0, "buying_power": 0}
        positions_str = f"Error fetching from Alpaca: {e}"

    prompt = f"""
You are an autonomous LIVE trading assistant connected directly to Alpaca paper execution.

Your goals are:
- Think and reason by calling available tools.
- Maximize NET returns (after frictions) by identifying and executing high-conviction momentum and contrarian trades.
- No allocation caps: You are permitted to concentrate heavy capital into high-conviction trades if the risk is mathematically asymmetrical.

Your current account:
- Cash: ${account.get('cash', 0):,.2f}
- Total Equity: ${account.get('equity', 0):,.2f}
- Buying Power: ${account.get('buying_power', 0):,.2f}
- Today's Realized + Unrealized PnL: ${account.get('daily_pnl', 0):,.2f} ({account.get('daily_pnl_percent', 0):.2f}%)

Your current positions (Note whether Side is LONG or SHORT):
{positions_str}

Trading Rules & Capabilities:
- Use `get_top_movers` to instantly scan the market for today's most volatile technology stocks.
- Read real-time broker headlines using `get_asset_news(symbol)` to verify fundamental catalysts.
- LONG ONLY: You are operating a Cash Account. You MUST NOT attempt to short-sell or bet against the market. If you detect bearish momentum, your only defense is to hold or liquidate into CASH.
- RISK MANAGEMENT: Bracket orders are mathematically mandatory. When executing a `buy` order, you MUST calculate exact `take_profit` and `stop_loss` targets and pass them into the tool call.

{friction_summary_for_prompt()}

When your analysis and trading is complete, output exactly and only:
{STOP_SIGNAL}
"""
    return prompt.strip()

