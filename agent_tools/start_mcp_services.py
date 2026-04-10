#!/usr/bin/env python3
"""
MCP Service Startup Script (Python Version)
Start all MCP services: Math, Search, Alpaca
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class MCPServiceManager:
    def __init__(self):
        self.services = {}
        self.running = True

        # Set default ports
        self.ports = {
            "math": int(os.getenv("MATH_HTTP_PORT", "8004")),
            "search": int(os.getenv("SEARCH_HTTP_PORT", "8001")),
            "alpaca": int(os.getenv("TRADE_HTTP_PORT", "8002")),
        }

        # Service configurations
        mcp_server_dir = os.path.dirname(os.path.abspath(__file__))
        self.service_configs = {
            "math": {"script": os.path.join(mcp_server_dir, "tool_math.py"), "name": "Math", "port": self.ports["math"]},
            "search": {"script": os.path.join(mcp_server_dir, "tool_jina_search.py"), "name": "JinaSearch", "port": self.ports["search"]},  
            "alpaca": {"script": os.path.join(mcp_server_dir, "tool_alpaca_mcp.py"), "name": "AlpacaLive", "port": self.ports["alpaca"]},
        }

        # Create logs directory
        self.log_dir = Path("../logs")
        self.log_dir.mkdir(exist_ok=True)

        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        print("\n🛑 Received stop signal, shutting down all services...")
        self.stop_all_services()
        sys.exit(0)

    def is_port_available(self, port):
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", port))
            sock.close()
            return result != 0
        except:
            return False

    def check_port_conflicts(self):
        conflicts = []
        for service_id, config in self.service_configs.items():
            if not self.is_port_available(config["port"]):
                conflicts.append((config["name"], config["port"]))

        if conflicts:
            print("⚠️  Port conflicts detected:")
            for name, port in conflicts:
                print(f"   - {name}: Port {port} is already in use")
            
            response = input("\n❓ Do you want to automatically find available ports? (y/n): ")
            if response.lower() == "y":
                for service_id, config in self.service_configs.items():
                    port = config["port"]
                    if not self.is_port_available(port):
                        new_port = port
                        while not self.is_port_available(new_port):
                            new_port += 1
                            if new_port > port + 100:
                                return False
                        print(f"   ✅ {config['name']}: Changed port from {port} to {new_port}")
                        config["port"] = new_port
                        self.ports[service_id] = new_port
                return True
            return False
        return True

    def start_service(self, service_id, config):
        script_path = config["script"]
        service_name = config["name"]
        port = config["port"]

        if not Path(script_path).exists():
            print(f"❌ Script file not found: {script_path}")
            return False

        try:
            log_file = self.log_dir / f"{service_id}.log"
            with open(log_file, "w") as f:
                process = subprocess.Popen(
                    [sys.executable, script_path], stdout=f, stderr=subprocess.STDOUT, cwd=os.getcwd()
                )
            self.services[service_id] = {"process": process, "name": service_name, "port": port, "log_file": log_file}
            print(f"✅ {service_name} service started (PID: {process.pid}, Port: {port})")
            return True
        except Exception as e:
            print(f"❌ Failed to start {service_name} service: {e}")
            return False

    def check_service_health(self, service_id):
        if service_id not in self.services: return False
        service = self.services[service_id]
        if service["process"].poll() is not None: return False
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", service["port"]))
            sock.close()
            return result == 0
        except: return False

    def start_all_services(self):
        if not self.check_port_conflicts(): return
        print("\n🔄 Starting services...")
        success_count = sum(1 for sid, cfg in self.service_configs.items() if self.start_service(sid, cfg))
        
        if success_count == 0:
            print("\n❌ No services started successfully")
            return

        time.sleep(3)
        healthy_count = sum(1 for sid in self.services if self.check_service_health(sid))

        if healthy_count > 0:
            print(f"\n🎉 {healthy_count}/{len(self.services)} MCP services running!")
            self.keep_alive()
        else:
            self.stop_all_services()

    def keep_alive(self):
        try:
            while self.running:
                time.sleep(5)
                stopped = [s["name"] for s in self.services.values() if s["process"].poll() is not None]
                if stopped:
                    print(f"\n⚠️  Following service(s) stopped unexpectedly: {', '.join(stopped)}")
                    if len(stopped) == len(self.services):
                        self.running = False
                        break
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_all_services()

    def stop_all_services(self):
        for service in self.services.values():
            try:
                service["process"].terminate()
                service["process"].wait(timeout=5)
            except subprocess.TimeoutExpired:
                service["process"].kill()
        print("✅ All services stopped")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        pass
    else:
        MCPServiceManager().start_all_services()

if __name__ == "__main__":
    main()
