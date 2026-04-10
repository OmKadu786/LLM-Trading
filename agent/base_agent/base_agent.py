"""
BaseAgent class - Base class for LIVE trading agents
Encapsulates core functionality including MCP tool management, AI agent creation, and trading execution
"""

import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.globals import set_verbose, set_debug
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from prompts.agent_prompt import STOP_SIGNAL, get_agent_system_prompt

load_dotenv()

class BaseAgent:
    """
    Base class for LIVE trading agents via Alpaca
    """

    def __init__(
        self,
        signature: str,
        basemodel: str,
        mcp_config: dict = None,
        log_path: str = None,
        max_steps: int = 30,
        max_retries: int = 3,
        base_delay: float = 1.0,
        initial_cash: float = 100000.0,
        init_date: str = "",
        verbose: bool = True
    ):
        self.signature = signature
        self.basemodel = basemodel
        self.market = "us"
        self.max_steps = max_steps
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.verbose = verbose
        self.mcp_config = mcp_config
        self.base_log_path = log_path or "./data/agent_data"

        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_base_url = os.getenv("OPENAI_API_BASE")

        self.client = None
        self.tools = None
        self.model = None
        self.agent_executor = None

    async def initialize(self) -> None:
        """Initialize MCP client and AI model"""
        print(f"🚀 Initializing agent: {self.signature}")
        if self.verbose:
            set_verbose(True)
            try: set_debug(True)
            except Exception: pass

        if not self.openai_api_key:
            raise ValueError("❌ OpenAI API key not set in environment.")

        try:
            self.client = MultiServerMCPClient(self.mcp_config)
            self.tools = await self.client.get_tools()
            print(f"✅ Loaded {len(self.tools) if self.tools else 0} MCP tools")
        except Exception as e:
            raise RuntimeError(f"❌ Failed to initialize MCP client: {e}")

        try:
            self.model = ChatOpenAI(
                model=self.basemodel,
                base_url=self.openai_base_url,
                api_key=self.openai_api_key,
                max_retries=3,
                timeout=120,
            )
        except Exception as e:
            raise RuntimeError(f"❌ Failed to initialize AI model: {e}")

    def _setup_logging(self, today_date: str) -> str:
        log_path = os.path.join(self.base_log_path, self.signature, "log", today_date)
        os.makedirs(log_path, exist_ok=True)
        return os.path.join(log_path, "log.jsonl")

    def _log_message(self, log_file: str, new_messages: list) -> None:
        log_entry = {
            "signature": self.signature,
            "new_messages": new_messages
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    async def run_trading_session(self, today_date: str) -> None:
        print(f"📈 Starting trading session: {today_date}")
        log_file = self._setup_logging(today_date)
        
        # Build standard Langchain prompt structure for tools
        sys_prompt = get_agent_system_prompt(today_date, self.signature, self.market)
        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("user", "{input}"),
            ("placeholder", "{agent_scratchpad}")
        ])

        # Create bulletproof Agent Executor
        agent = create_tool_calling_agent(self.model, self.tools, prompt)
        self.agent_executor = AgentExecutor(
            agent=agent, 
            tools=self.tools, 
            verbose=self.verbose, 
            max_iterations=self.max_steps,
            handle_parsing_errors=True
        )

        user_query = f"Please analyze the market conditions and execute trades for today ({today_date}). IMPORTANT: Output precisely '{STOP_SIGNAL}' and nothing else on its own line when you are absolutely finished and have no more trades to make."
        self._log_message(log_file, [{"role": "user", "content": user_query}])

        try:
            print("🤖 Agent Executor running autonomous loop...")
            response = await self.agent_executor.ainvoke({"input": user_query})
            
            agent_response = response.get("output", str(response))
            print("✅ Trading session ended.")
            self._log_message(log_file, [{"role": "assistant", "content": agent_response}])

        except Exception as e:
            print(f"❌ Trading session error: {str(e)}")
            raise

        print("✅ Trading execution completed")
