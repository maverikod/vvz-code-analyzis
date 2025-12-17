"""
Restart server and test semantic_search.

This script restarts the MCP server and then tests semantic_search functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from code_analysis.core.server_control import ServerControl

# Config path
CONFIG_PATH = project_root / "config.json"


def restart_server() -> bool:
    """
    Restart MCP server.

    Returns:
        True if restart was successful, False otherwise
    """
    print("🔄 Restarting MCP server...")
    
    control = ServerControl(CONFIG_PATH)
    
    # Check status first
    status = control.status()
    print(f"Current status: {status.get('message', 'Unknown')}")
    
    # Restart
    result = control.restart()
    
    if result.get("success"):
        print(f"✅ {result.get('message', 'Server restarted')}")
        if "pid" in result:
            print(f"   PID: {result['pid']}")
        if "log_file" in result:
            print(f"   Log: {result['log_file']}")
        
        # Wait a bit for server to fully start
        print("⏳ Waiting for server to start...")
        time.sleep(3)
        
        # Verify server is running
        status = control.status()
        if status.get("running"):
            print(f"✅ Server is running (PID: {status.get('pid')})")
            return True
        else:
            print(f"❌ Server failed to start: {status.get('message')}")
            return False
    else:
        print(f"❌ Failed to restart server: {result.get('message')}")
        return False


def main():
    """Main entry point."""
    print("=" * 80)
    print("RESTART SERVER AND TEST SEMANTIC SEARCH")
    print("=" * 80)
    print()
    
    # Restart server
    if not restart_server():
        print("\n❌ Server restart failed. Cannot proceed with testing.")
        sys.exit(1)
    
    print()
    print("=" * 80)
    print("Now run the semantic search test:")
    print("=" * 80)
    print()
    print("python scripts/test_semantic_search_real_server.py --query 'code analysis' --k 3")
    print()


if __name__ == "__main__":
    main()

